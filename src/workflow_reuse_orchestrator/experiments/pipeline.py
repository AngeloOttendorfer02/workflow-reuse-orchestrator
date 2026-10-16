"""Configuration inspection and a recorded, single-call infrastructure pilot."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue

from workflow_reuse_orchestrator import __version__
from workflow_reuse_orchestrator.config import (
    StudyBundle,
    configuration_files,
    load_study,
    load_study_bundle,
    ollama_base_url,
    resolve_project_path,
)
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.outcomes import (
    AttemptSpec,
    JobResult,
    JobSpec,
    Receipt,
    RequestSpec,
    RunSpec,
    ScopeSpec,
)
from workflow_reuse_orchestrator.domain.providers import InferenceProfile
from workflow_reuse_orchestrator.experiments.stages import JobRunner
from workflow_reuse_orchestrator.runtime.budgets import (
    BudgetedGenerator,
    BudgetExceeded,
    BudgetTracker,
)
from workflow_reuse_orchestrator.runtime.ollama import OllamaProvider
from workflow_reuse_orchestrator.storage import ResultStore, canonical_sha256

STAGES = (
    "prepare_data",
    "baseline_pilot",
    "discover_library",
    "collect_candidates",
    "prepare_features",
    "train_selectors",
    "development_pilot",
    "final_evaluation",
    "analyze_results",
)


ValidationLevel = Literal["scaffold", "runtime", "data", "protected"]
VALIDATION_LEVELS = ("scaffold", "runtime", "data", "protected")
GATE_NAMES = {
    "scaffold": "scaffold_valid",
    "runtime": "runtime_bound",
    "data": "data_ready",
    "protected": "protected_release_ready",
}


def readiness_blockers(bundle: StudyBundle) -> dict[str, list[str]]:
    """Check declarations offline; unfinished scientific verifiers fail closed."""
    runtime = bundle.study.runtime
    runtime_blockers = [
        f"runtime.{name} is unbound"
        for name in type(runtime).model_fields
        if getattr(runtime, name) is None
    ]
    if runtime.prompts is not None:
        for role in type(runtime.prompts).model_fields:
            binding = getattr(runtime.prompts, role)
            try:
                path = resolve_project_path(bundle.root, binding.path)
                content = path.read_bytes()
                if not content.strip():
                    runtime_blockers.append(f"runtime.prompts.{role} is empty")
                elif hashlib.sha256(content).hexdigest() != binding.sha256:
                    runtime_blockers.append(f"runtime.prompts.{role} checksum does not match")
            except (OSError, ValueError) as exc:
                runtime_blockers.append(f"runtime.prompts.{role}: {exc}")

    data = bundle.datasets
    data_blockers = []
    for dataset in ("hotpotqa", "drop", "finqa"):
        release = getattr(data.datasets, dataset)
        for name in ("release", "source_checksum"):
            if getattr(release, name) is None:
                data_blockers.append(f"datasets.{dataset}.{name} is unresolved")
    if data.snapshot_id is None:
        data_blockers.append("datasets.snapshot_id is unresolved")
    if data.partitions.assignment_version is None:
        data_blockers.append("datasets.partitions.assignment_version is unresolved")
    # A path/flag or nonempty SQLite file cannot substitute for snapshot evidence.
    data_blockers.append(
        "Prepared dataset integrity and partition verification is not implemented."
    )

    protected_blockers = []
    if runtime_blockers:
        protected_blockers.append("Runtime bindings have not passed the offline runtime gate.")
    protected_blockers.append("Dataset snapshot verification has not passed the data gate.")
    learning = bundle.learning
    for name in ("decision_rule", "selected_predictor"):
        if getattr(learning.model_selection, name) is None:
            protected_blockers.append(f"learning.model_selection.{name} is unresolved")
    for name in ("calibration", "selection_thresholds", "development_cost_estimates"):
        if getattr(learning, name) is None:
            protected_blockers.append(f"learning.{name} is unresolved")
    if not bundle.evaluation.protocol_frozen:
        protected_blockers.append("evaluation.protocol_frozen is false")
    protected_blockers.extend(
        f"evaluation.{name} is unresolved" for name in bundle.evaluation.unresolved_fields()
    )
    # A frozen flag is a declaration, not an immutable release/inference verifier.
    protected_blockers.append(
        "Protected release and fitted-artifact verification is not implemented."
    )
    return {
        "scaffold": [],
        "runtime": runtime_blockers,
        "data": data_blockers,
        "protected": protected_blockers,
    }


def check_study(
    config_path: Path | None = None, *, level: ValidationLevel = "scaffold"
) -> dict[str, Any]:
    """Validate owned schemas and report an explicitly requested offline gate."""
    if level not in VALIDATION_LEVELS:
        raise ValueError(f"Unknown validation level: {level}")
    bundle = load_study_bundle(config_path)
    study, root, learning = bundle.study, bundle.root, bundle.learning
    blockers = readiness_blockers(bundle)
    ready = not blockers[level]
    return {
        "status": "foundations_ready"
        if ready and level == "scaffold"
        else ("runtime_bound" if ready else "blocked"),
        "requested_level": level,
        "ready": ready,
        "readiness": {GATE_NAMES[name]: not problems for name, problems in blockers.items()},
        "blockers": {GATE_NAMES[name]: problems for name, problems in blockers.items()},
        "runtime_contacted": False,
        "profile": study.profile,
        "seed": study.seed,
        "datasets": study.datasets,
        "methods": study.methods,
        "predictors": learning.predictors,
        "model_selection": learning.model_selection.model_dump(mode="json"),
        "selector_training_available": False,
        "configuration_files": {
            name: path.relative_to(root).as_posix()
            for name, path in configuration_files(study, root).items()
        },
        "pending_runtime_bindings": [
            name
            for name in type(study.runtime).model_fields
            if getattr(study.runtime, name) is None
        ],
        "workflow_execution_available": False,
        "runtime_check_available": True,
        "checks": [
            "study and typed runtime declarations",
            "project-relative configuration references",
            "dataset, learning and evaluation declaration schemas and ownership",
            "cross-document snapshot and source-group identities",
            "requested offline readiness gate",
        ],
    }


def plan_study(config_path: Path | None = None) -> dict[str, Any]:
    """List planned stages; this command executes no study work."""
    report = check_study(config_path)
    report["stages"] = [{"name": name, "status": "pending"} for name in STAGES]
    return report


def runtime_models(base_url: str | None = None) -> dict[str, Any]:
    with OllamaProvider(base_url=ollama_base_url(base_url)) as provider:
        return {"ollama_version": provider.version(), "models": provider.models()}


def inspect_runtime_model(model_name: str, base_url: str | None = None) -> dict[str, Any]:
    with OllamaProvider(base_url=ollama_base_url(base_url)) as provider:
        return provider.inspect_model(model_name).model_dump(mode="json")


def inspect_run(output_dir: Path, *, job_id: str | None = None) -> dict[str, Any]:
    """Inspect the ledger without migration, recovery, locks or provider contact."""
    with ResultStore(output_dir / "results.sqlite3", read_only=True) as store:
        store.verify_integrity()
        report = store.progress()
        if job_id is not None:
            job = store.job(job_id)
            if job is None:
                raise ValueError(f"Unknown job: {job_id}")
            report["job"] = job.model_dump(mode="json")
            report["events"] = store.events(job_id)
        return {**report, "runtime_contacted": False}


def migrate_run(output_dir: Path) -> dict[str, Any]:
    database = output_dir / "results.sqlite3"
    if not database.is_file():
        raise ValueError("Migration requires an existing result database.")
    with ResultStore(database, migrate=True) as store:
        store.verify_integrity()
        return {
            "schema_version": store.schema_version,
            "status": "migrated",
            "runtime_contacted": False,
            "historical_jobs_reconstructed": False,
        }


def runtime_check(
    *,
    model_name: str,
    output_dir: Path,
    config_path: Path | None = None,
    base_url: str | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    timeout_seconds: float = 60.0,
    progress: Callable[[str], None] | None = None,
    retry_of: str | None = None,
) -> dict[str, Any]:
    """Inspect a model and record at most one generation, independently of study execution.

    The short default limits are infrastructure-pilot controls. They never fill
    or replace the active study bindings. Existing completed receipts are read
    as historical measurements; an unfinished attempt is not silently retried.
    """
    study = load_study(config_path)
    inference = study.runtime.inference or InferenceProfile(
        num_ctx=num_ctx if num_ctx is not None else 4096,
        num_predict=num_predict if num_predict is not None else 128,
        seed=study.seed,
    )
    if (num_ctx is not None and num_ctx != inference.num_ctx) or (
        num_predict is not None and num_predict != inference.num_predict
    ):
        raise ValueError("Pilot options differ from the configured inference binding.")
    if study.runtime.model is not None and study.runtime.model.model_name != model_name:
        raise ValueError("The selected model differs from the configured model binding.")
    budget = RequestBudget(
        max_model_calls=1,
        max_input_tokens=inference.num_ctx,
        max_output_tokens=inference.num_predict,
        max_tool_calls=0,
        max_wall_seconds=timeout_seconds,
        max_plan_repairs=0,
        max_fallback_plans=0,
    )
    endpoint = ollama_base_url(base_url)
    study_document = study.model_dump(mode="json")
    for field in ("datasets_config", "learning_config", "evaluation_config"):
        study_document[field] = getattr(study, field).as_posix()
    parameters: dict[str, JsonValue] = {
        "purpose": "infrastructure_pilot",
        "model_name": model_name,
        "base_url": endpoint,
        "study_sha256": canonical_sha256(study_document),
        "prompt": "Reply with exactly OK.",
        "expected_output": "OK",
        "inference": inference.model_dump(mode="json"),
        "request_budget": budget.model_dump(mode="json"),
    }
    database = output_dir / "results.sqlite3"
    first_job_id = "runtime-check:trial-001"
    job_id = first_job_id if retry_of is None else f"{retry_of}:retry"
    with ResultStore(database) as store:
        store.verify_integrity()
        previous_parameters = store.binding("run_parameters")
        if previous_parameters is not None and "expected_output" not in previous_parameters:
            raise ValueError(
                "This pilot used the previous output validation. "
                "Use a new output folder for the corrected check."
            )
        store.bind("run_parameters", parameters)
        if retry_of is None:
            completed = store.receipt("runtime-check:001-completed")
            if completed is not None:
                if progress is not None:
                    progress("Reading the completed infrastructure-pilot receipt.")
                return {**completed.payload, "measurement_source": "stored_receipt"}
            if store.receipt("runtime-check:000-started") is not None:
                if store.schema_version == 2:
                    store.recover_running(run_id="runtime-pilot")
                raise ValueError(
                    "An unfinished generation has an unknown outcome. "
                    "Inspect its job and supply --retry-of JOB_ID for an explicit new trial, "
                    "or use a new output folder."
                )
        if store.schema_version != 2:
            raise ValueError(
                "Migrate this schema-v1 database explicitly or use a new output folder."
            )
        package_root = Path(__file__).resolve().parents[1]
        code_hash = canonical_sha256(
            {
                path.relative_to(package_root).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted(package_root.rglob("*.py"))
            }
        )
        store.declare_run(
            RunSpec(
                run_id="runtime-pilot",
                purpose="infrastructure_pilot",
                configuration_sha256=canonical_sha256(parameters),
                code_version=f"{__version__}:{code_hash}",
            )
        )
        store.declare_scope(
            ScopeSpec(
                scope_id="runtime-pilot:scope",
                run_id="runtime-pilot",
                family="infrastructure",
                fold_id="infrastructure",
            )
        )
        store.recover_running(run_id="runtime-pilot")
        request_id, attempt_id = f"{job_id}:request", f"{job_id}:attempt"
        store.declare_request(
            RequestSpec(
                request_id=request_id,
                scope_id="runtime-pilot:scope",
                task_id="infrastructure-prompt",
                method_id="infrastructure-pilot",
                budget=budget,
            )
        )
        store.declare_attempt(
            AttemptSpec(attempt_id=attempt_id, request_id=request_id, kind="primary")
        )
        spec = JobSpec(
            job_id=job_id,
            scope_id="runtime-pilot:scope",
            stage="runtime_check",
            phase="startup",
            method_id="infrastructure-pilot",
            effect="model",
            request_id=request_id,
            attempt_id=attempt_id,
            retry_of=retry_of,
            parameters=parameters,
        )
        job = store.declare_job(spec)
        if job.status in ("succeeded", "failed"):
            return {**(job.result or {}), "measurement_source": "stored_receipt"}
        if job.status != "pending":
            raise ValueError(f"Job {job_id} has an unknown outcome; declare an explicit retry.")
        if progress is not None:
            progress("Inspecting the installed model and runtime fingerprints.")
        with OllamaProvider(base_url=endpoint, timeout_seconds=timeout_seconds) as provider:
            model = provider.inspect_model(model_name)
            if study.runtime.model is not None and model != study.runtime.model:
                raise ValueError("The installed model differs from the configured fingerprint.")
            store.bind("model_binding", model.model_dump(mode="json"))
            tracker = BudgetTracker(budget)
            generator = BudgetedGenerator(
                provider=provider, model=model, inference=inference, tracker=tracker
            )

            def operation() -> JobResult:
                response = None
                error = None
                try:
                    if progress is not None:
                        progress("Executing one bounded infrastructure-pilot generation.")
                    response = generator.generate(str(parameters["prompt"]))
                    if response.finish_reason == "length":
                        error = "generation_truncated"
                    elif response.finish_reason is None:
                        error = "completion_reason_unavailable"
                    elif response.finish_reason != "stop":
                        error = "unexpected_completion_reason"
                    elif not tracker.usage.token_counts_available:
                        error = "token_usage_unavailable"
                    elif any(
                        tag in response.output_text.casefold() for tag in ("<think>", "</think>")
                    ):
                        error = "unexpected_thinking_output"
                    elif response.output_text.strip() != parameters["expected_output"]:
                        error = "unexpected_pilot_output"
                except BudgetExceeded as exc:
                    if response is None:
                        raise  # Unknown/late provider effects must not become a free retry.
                    error = str(exc)
                report: dict[str, Any] = {
                    "status": "passed" if error is None else "failed",
                    "purpose": "infrastructure_pilot",
                    "job_id": job_id,
                    "request_id": request_id,
                    "attempt_id": attempt_id,
                    "method_id": "infrastructure-pilot",
                    "fold_id": "infrastructure",
                    "retry_of": retry_of,
                    "model": model.model_dump(mode="json"),
                    "inference": inference.model_dump(mode="json"),
                    "request_budget": budget.model_dump(mode="json"),
                    "usage": tracker.usage.model_dump(mode="json"),
                    "generation": response.model_dump(mode="json")
                    if response is not None
                    else None,
                    "error": error,
                    "workflow_execution_available": False,
                    "study_bindings_updated": False,
                }
                if progress is not None:
                    progress("Saving generation, usage, and completion status to SQLite.")
                return JobResult(
                    status="succeeded" if error is None else "failed",
                    result=report,
                    usage=tracker.usage,
                    error=error,
                )

            def completed_receipts(result: JobResult) -> tuple[Receipt, ...]:
                if retry_of is not None:
                    return ()
                return (
                    Receipt(
                        receipt_id="runtime-check:001-completed",
                        kind="runtime_check",
                        status=result.status,
                        payload=result.result,
                    ),
                )

            def job_progress(event: dict[str, Any]) -> None:
                if progress is not None:
                    counts = event["progress"]["jobs"]
                    progress(
                        f"[{event['phase']}/{event['stage']}] method={event['method_id']} "
                        f"fold={event['fold_id']} completed={counts['succeeded']} "
                        f"failed={counts['failed']} unknown={counts['unknown']} "
                        f"planned={counts['planned']}"
                    )

            receipts = (
                ()
                if retry_of is not None
                else (
                    Receipt(
                        receipt_id="runtime-check:000-started",
                        kind="runtime_check",
                        status="started",
                        payload={
                            "purpose": "infrastructure_pilot",
                            "model_name": model_name,
                            "job_id": job_id,
                            "method_id": "infrastructure-pilot",
                            "fold_id": "infrastructure",
                        },
                    ),
                )
            )
            job = JobRunner(store, progress=job_progress).run(
                spec,
                operation,
                started_receipts=receipts,
                completed_receipts=completed_receipts,
                failure_usage=lambda: tracker.usage,
            )
            return {**(job.result or {}), "measurement_source": "live"}
