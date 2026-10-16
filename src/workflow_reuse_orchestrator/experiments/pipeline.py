"""Configuration inspection and a recorded, single-call infrastructure pilot."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from workflow_reuse_orchestrator.config import (
    StudyBundle,
    configuration_files,
    load_study,
    load_study_bundle,
    ollama_base_url,
    resolve_project_path,
)
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.outcomes import Receipt
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ProviderError
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
    parameters = {
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
    with ResultStore(database) as store:
        previous_parameters = store.binding("run_parameters")
        if previous_parameters is not None and "expected_output" not in previous_parameters:
            raise ValueError(
                "This pilot used the previous output validation. "
                "Use a new output folder for the corrected check."
            )
        store.bind("run_parameters", parameters)
        completed = store.receipt("runtime-check:001-completed")
        if completed is not None:
            if progress is not None:
                progress("Reading the completed infrastructure-pilot receipt.")
            return {**completed.payload, "measurement_source": "stored_receipt"}
        if store.receipt("runtime-check:000-started") is not None:
            raise ValueError(
                "An unfinished generation has an unknown outcome. "
                "Use a new output folder for an explicitly counted retry."
            )
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
            store.put_receipt(
                Receipt(
                    receipt_id="runtime-check:000-started",
                    kind="runtime_check",
                    status="started",
                    payload={"purpose": "infrastructure_pilot", "model_name": model_name},
                )
            )
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
                elif any(tag in response.output_text.casefold() for tag in ("<think>", "</think>")):
                    error = "unexpected_thinking_output"
                elif response.output_text.strip() != parameters["expected_output"]:
                    error = "unexpected_pilot_output"
            except (ProviderError, BudgetExceeded) as exc:
                error = str(exc)
            report: dict[str, Any] = {
                "status": "passed" if error is None else "failed",
                "purpose": "infrastructure_pilot",
                "model": model.model_dump(mode="json"),
                "inference": inference.model_dump(mode="json"),
                "request_budget": budget.model_dump(mode="json"),
                "usage": tracker.usage.model_dump(mode="json"),
                "generation": response.model_dump(mode="json") if response is not None else None,
                "error": error,
                "workflow_execution_available": False,
                "study_bindings_updated": False,
            }
            if progress is not None:
                progress("Saving generation, usage, and completion status to SQLite.")
            store.put_receipt(
                Receipt(
                    receipt_id="runtime-check:001-completed",
                    kind="runtime_check",
                    status="succeeded" if error is None else "failed",
                    payload=report,
                )
            )
            return {**report, "measurement_source": "live"}
