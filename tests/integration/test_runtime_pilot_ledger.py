"""The real pilot API uses the ledger; all provider responses remain offline mocks."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.domain.providers import ProviderUnavailableError
from workflow_reuse_orchestrator.experiments import pipeline
from workflow_reuse_orchestrator.runtime.ollama import OllamaProvider
from workflow_reuse_orchestrator.storage import ResultStore


def test_pilot_records_lineage_and_status_without_contact_on_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    capsys,
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    report = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert report["status"] == "passed"
    assert report["method_id"] == "infrastructure-pilot"
    assert report["fold_id"] == "infrastructure"
    calls = len(state["calls"])
    before = (tmp_path / "results.sqlite3").read_bytes()
    assert main(["pipeline", "status", "--output", str(tmp_path), "--job", report["job_id"]]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["job"]["status"] == "succeeded"
    assert status["usage"]["input_tokens"] == 10
    assert status["usage"]["model_calls"] == 1
    assert len(status["events"]) == 3
    assert len(state["calls"]) == calls
    assert (tmp_path / "results.sqlite3").read_bytes() == before
    second = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert second["measurement_source"] == "stored_receipt"
    assert len(state["calls"]) == calls


def test_uncertain_pilot_retry_is_a_new_linked_trial_and_keeps_possible_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    real_generate = OllamaProvider.generate

    def interrupted(self, **kwargs):
        raise ProviderUnavailableError("Connection interrupted")

    monkeypatch.setattr(OllamaProvider, "generate", interrupted)
    with pytest.raises(ProviderUnavailableError):
        pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    original = "runtime-check:trial-001"
    status = pipeline.inspect_run(tmp_path, job_id=original)
    assert status["job"]["status"] == "unknown"
    assert status["usage"]["model_calls"] == 1
    assert status["usage"]["input_tokens"] is None
    calls = len(state["calls"])
    with pytest.raises(ValueError, match="unknown outcome"):
        pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert len(state["calls"]) == calls
    monkeypatch.setattr(OllamaProvider, "generate", real_generate)
    retry = pipeline.runtime_check(
        model_name="test-model:latest", output_dir=tmp_path, retry_of=original
    )
    assert retry["status"] == "passed"
    assert retry["retry_of"] == original
    status = pipeline.inspect_run(tmp_path)
    assert status["jobs"]["unknown"] == status["jobs"]["succeeded"] == 1
    assert status["usage"]["model_calls"] == 2
    assert status["usage"]["input_tokens"] is None
    calls = len(state["calls"])
    cached = pipeline.runtime_check(
        model_name="test-model:latest", output_dir=tmp_path, retry_of=original
    )
    assert cached["measurement_source"] == "stored_receipt"
    assert len(state["calls"]) == calls
    with ResultStore(tmp_path / "results.sqlite3", read_only=True) as store:
        first = store.job(original)
        second = store.job(retry["job_id"])
        assert first.spec.request_id != second.spec.request_id
        assert first.spec.attempt_id != second.spec.attempt_id
        assert store.receipt("runtime-check:000-started") is not None
        assert store.receipt("runtime-check:001-completed") is None
        store.verify_integrity()


def test_failed_pilot_can_be_retried_without_overwriting_original_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    state["generation"]["response"] = "Unexpected answer"
    failed = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert failed["status"] == "failed"
    state["generation"]["response"] = "OK"
    retry = pipeline.runtime_check(
        model_name="test-model:latest", output_dir=tmp_path, retry_of=failed["job_id"]
    )
    assert retry["status"] == "passed"
    with ResultStore(tmp_path / "results.sqlite3", read_only=True) as store:
        original = store.receipt("runtime-check:001-completed")
        assert original.status == "failed"
        assert original.payload["generation"]["output_text"] == "Unexpected answer"
        assert store.progress()["usage"]["model_calls"] == 2
