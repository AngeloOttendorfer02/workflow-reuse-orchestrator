"""Durable intent/result boundaries, interrupted effects, lineage and progress."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from workflow_reuse_orchestrator.domain.budgets import RequestBudget, ResourceUsage
from workflow_reuse_orchestrator.domain.outcomes import (
    AttemptSpec,
    JobResult,
    JobSpec,
    Receipt,
    RequestSpec,
    RunSpec,
    ScopeSpec,
)
from workflow_reuse_orchestrator.experiments.stages import JobBlockedError, JobRunner
from workflow_reuse_orchestrator.storage import ResultStore, StorageIntegrityError


def declare(store: ResultStore) -> None:
    store.declare_run(
        RunSpec(
            run_id="run",
            purpose="development",
            configuration_sha256="a" * 64,
            code_version="fixture-v1",
        )
    )
    store.declare_scope(ScopeSpec(scope_id="main", run_id="run", family="main", fold_id="main"))


def spec(job_id: str, **kwargs: Any) -> JobSpec:
    return JobSpec(
        job_id=job_id,
        scope_id="main",
        stage="fixture-stage",
        phase="startup",
        method_id="fixture-method",
        effect="local",
        **kwargs,
    )


def measured() -> JobResult:
    return JobResult(result={"value": 42})


def test_resume_completed_units_without_duplicate_effects(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite3"
    effects = []
    first, second = spec("first"), spec("second")
    with ResultStore(path) as store:
        declare(store)
        runner = JobRunner(store)
        runner.run(first, lambda: (effects.append("first"), measured())[1])
        store.declare_job(second)  # Process ends before the second unit starts.
    with ResultStore(path) as store:
        declare(store)
        progress = []
        runner = JobRunner(store, progress=progress.append)
        runner.run(first, lambda: pytest.fail("Completed effect must never be replayed"))
        runner.run(second, lambda: (effects.append("second"), measured())[1])
        assert effects == ["first", "second"]
        assert progress[0]["event"] == "resumed_completed"
        assert progress[-1]["phase"] == "startup"
        assert progress[-1]["fold_id"] == "main"
        assert progress[-1]["progress"]["jobs"] == {
            "planned": 2,
            "pending": 0,
            "running": 0,
            "succeeded": 2,
            "failed": 0,
            "unknown": 0,
        }
        assert [event["event_type"] for event in store.events("first")] == [
            "declared",
            "started",
            "completed",
        ]
        store.verify_integrity()


def test_intent_is_committed_and_readable_before_effect(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite3"
    with ResultStore(path) as store:
        declare(store)

        def operation() -> JobResult:
            with ResultStore(path, read_only=True) as observer:
                assert observer.job("model").status == "running"
                assert observer.events("model")[-1]["event_type"] == "started"
                assert observer.progress()["usage"]["model_calls"] == 1
                assert observer.progress()["usage"]["input_tokens"] is None
            return JobResult(
                result={"answer": "fixture"},
                usage=ResourceUsage(model_calls=1, input_tokens=7, output_tokens=2),
            )

        job = JobSpec.model_validate(spec("model").model_dump() | {"effect": "model"})
        JobRunner(store).run(job, operation)


def test_hard_interruption_remains_unknown_and_requires_linked_retry(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite3"
    original = JobSpec.model_validate(spec("original").model_dump() | {"effect": "model"})
    with ResultStore(path) as store:
        declare(store)
        store.declare_job(original)
        store.start_job("original")  # Crash at any point before the result transaction.
    before = path.read_bytes()
    with ResultStore(path, read_only=True) as store:
        assert store.job("original").status == "running"  # Inspection does not recover/mutate.
    assert path.read_bytes() == before
    with ResultStore(path) as store:
        assert store.recover_running(run_id="run") == 1
        assert store.recover_running(run_id="run") == 0
        unknown = store.job("original")
        assert unknown.status == "unknown"
        assert unknown.usage.model_calls == 1
        assert unknown.usage.input_tokens is unknown.usage.output_tokens is None
        assert not unknown.wall_time_available
        with pytest.raises(JobBlockedError, match="explicit retry"):
            JobRunner(store).run(original, lambda: pytest.fail("Unknown effect cannot replay"))
        retry = JobSpec.model_validate(
            original.model_dump() | {"job_id": "retry", "retry_of": "original"}
        )
        result = JobResult(usage=ResourceUsage(model_calls=1, input_tokens=9, output_tokens=3))
        JobRunner(store).run(retry, lambda: result)
        assert store.job("original") == unknown
        progress = store.progress()
        assert progress["jobs"]["unknown"] == progress["jobs"]["succeeded"] == 1
        assert progress["usage"]["model_calls"] == 2
        assert progress["usage"]["input_tokens"] is None
        assert progress["usage"]["wall_seconds"] is None
        assert store.job("retry").spec.retry_of == "original"
        store.verify_integrity()


@pytest.mark.parametrize(
    "effect,status", [("local", "failed"), ("model", "unknown"), ("tool", "unknown")]
)
def test_exceptions_and_cancellation_preserve_admission(
    tmp_path: Path, effect: str, status: str
) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        job = JobSpec.model_validate(spec("cancel").model_dump() | {"effect": effect})

        def cancel() -> JobResult:
            raise KeyboardInterrupt("cancel fixture")

        with pytest.raises(KeyboardInterrupt, match="cancel fixture"):
            JobRunner(store).run(job, cancel)
        record = store.job("cancel")
        assert record.status == status
        assert record.wall_time_available
        assert record.usage.model_calls == int(effect == "model")
        assert record.usage.tool_calls == int(effect == "tool")
        store.verify_integrity()


def test_completion_and_mirror_receipts_are_one_transaction(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        store.declare_job(spec("unit"))
        store.start_job("unit")
        original = Receipt(
            receipt_id="mirror", kind="fixture", status="succeeded", payload={"value": 1}
        )
        store.put_receipt(original)
        changed = Receipt.model_validate(original.model_dump() | {"payload": {"value": 2}})
        with pytest.raises(StorageIntegrityError, match="Receipt changed"):
            store.finish_job("unit", measured(), receipts=(changed,))
        assert store.job("unit").status == "running"
        assert len(store.events("unit")) == 2
        assert store.receipt("mirror") == original
        store.finish_job("unit", measured(), receipts=(original,))
        assert store.job("unit").status == "succeeded"
        assert len(store.events("unit")) == 3


def test_result_save_failure_keeps_available_measured_usage(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        mirror = Receipt(receipt_id="mirror", kind="fixture", status="succeeded", payload={"v": 1})
        store.put_receipt(mirror)
        changed = Receipt.model_validate(mirror.model_dump() | {"payload": {"v": 2}})
        job = JobSpec.model_validate(spec("model").model_dump() | {"effect": "model"})
        with pytest.raises(StorageIntegrityError):
            JobRunner(store).run(
                job,
                lambda: JobResult(
                    usage=ResourceUsage(model_calls=1, input_tokens=17, output_tokens=4)
                ),
                completed_receipts=lambda _: (changed,),
            )
        record = store.job("model")
        assert record.status == "unknown"
        assert record.usage.input_tokens == 17
        assert record.usage.output_tokens == 4
        assert len(store.events("model")) == 3
        store.verify_integrity()


def test_start_receipt_conflict_rolls_back_intent_and_blocks_callback(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        mirror = Receipt(receipt_id="mirror", kind="fixture", status="started", payload={})
        store.put_receipt(mirror)
        changed = Receipt.model_validate(mirror.model_dump() | {"payload": {"v": 2}})
        with pytest.raises(StorageIntegrityError):
            JobRunner(store).run(
                spec("unit"),
                lambda: pytest.fail("No intent, no effect"),
                started_receipts=(changed,),
            )
        assert store.job("unit").status == "pending"
        assert len(store.events("unit")) == 1


def test_terminal_jobs_and_identity_cannot_be_overwritten(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        job = spec("unit")
        result = JobRunner(store).run(job, measured)
        with pytest.raises(ValueError, match="terminal"):
            store.finish_job("unit", measured())
        with pytest.raises(StorageIntegrityError, match="identity changed"):
            store.declare_job(JobSpec.model_validate(job.model_dump() | {"stage": "changed"}))
        assert JobRunner(store).run(job, lambda: pytest.fail("No replay")) == result
        failed = JobSpec.model_validate(job.model_dump() | {"job_id": "failed"})
        JobRunner(store).run(failed, lambda: JobResult(status="failed", error="known failure"))
        assert (
            JobRunner(store)
            .run(failed, lambda: pytest.fail("Known failures remain completed"))
            .status
            == "failed"
        )


def test_request_attempt_and_retry_lineage(request_budget: RequestBudget, tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        request = RequestSpec(
            request_id="r1",
            scope_id="main",
            task_id="task",
            method_id="fixture-method",
            budget=request_budget,
        )
        store.declare_request(request)
        store.declare_attempt(AttemptSpec(attempt_id="a1", request_id="r1", kind="reuse"))
        job = JobSpec.model_validate(
            spec("model").model_dump() | {"effect": "model", "request_id": "r1", "attempt_id": "a1"}
        )
        store.declare_job(job)
        store.start_job("model")
        store.recover_running(run_id="run")
        with pytest.raises(ValueError, match="unknown request"):
            store.declare_job(JobSpec.model_validate(job.model_dump() | {"job_id": "silent"}))
        store.declare_request(
            RequestSpec.model_validate(request.model_dump() | {"request_id": "r2"})
        )
        store.declare_attempt(AttemptSpec(attempt_id="a2", request_id="r2", kind="primary"))
        retry = JobSpec.model_validate(
            job.model_dump()
            | {"job_id": "retry", "retry_of": "model", "request_id": "r2", "attempt_id": "a2"}
        )
        store.declare_job(retry)
        assert store.attempt("a1").kind == "reuse"
        assert store.request("r2").budget == request_budget
        assert store.job("retry").spec.retry_of == "model"
        assert store.scope("main").fold_id == "main"


@pytest.mark.parametrize("target", ["checksum", "index", "event", "missing_event"])
def test_job_integrity_rejects_tampering_before_effects(tmp_path: Path, target: str) -> None:
    path = tmp_path / "results.sqlite3"
    with ResultStore(path) as store:
        declare(store)
        store.declare_job(spec("job"))
    with sqlite3.connect(path) as connection:
        if target == "checksum":
            connection.execute("UPDATE jobs SET payload='{}'")
        elif target == "index":
            connection.execute("UPDATE jobs SET method_id='changed'")
        elif target == "event":
            connection.execute("UPDATE events SET event_type='completed'")
        else:
            connection.execute("DELETE FROM events")
    with ResultStore(path, read_only=True) as store, pytest.raises(StorageIntegrityError):
        store.verify_integrity()


def test_retry_validation_and_sequential_effects(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        first, second = spec("first"), spec("second")
        store.declare_job(first)
        store.declare_job(second)
        store.start_job("first")
        with pytest.raises(ValueError, match="sequential"):
            store.start_job("second")
        store.finish_job("first", measured())
        with pytest.raises(ValueError, match="failed/unknown"):
            store.declare_job(spec("retry", retry_of="first"))
        assert store.job("second").status == "pending"


def test_exception_keeps_independently_available_usage(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        declare(store)
        job = JobSpec.model_validate(spec("late").model_dump() | {"effect": "model"})

        def late() -> JobResult:
            raise TimeoutError("Measured completion arrived after the request deadline")

        with pytest.raises(TimeoutError):
            JobRunner(store).run(
                job,
                late,
                failure_usage=lambda: ResourceUsage(
                    model_calls=1, input_tokens=14, output_tokens=None
                ),
            )
        assert store.job("late").status == "unknown"
        assert store.job("late").usage.input_tokens == 14
        assert store.job("late").usage.output_tokens is None
        assert store.progress()["usage"]["input_tokens"] == 14
        store.verify_integrity()
