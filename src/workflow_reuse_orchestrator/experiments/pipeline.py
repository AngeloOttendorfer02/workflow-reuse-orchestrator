"""Offline configuration inspection and the planned workflow study stages."""

from pathlib import Path
from typing import Any

from workflow_reuse_orchestrator.config import configuration_files, load_study, project_root

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


def check_study(config_path: Path | None = None) -> dict[str, Any]:
    """Describe a validated scaffold without making runtime-readiness claims."""
    study = load_study(config_path)
    root = project_root(
        config_path.parent if config_path is not None and config_path.is_absolute() else None
    )
    return {
        "status": "scaffold_ready",
        "profile": study.profile,
        "seed": study.seed,
        "datasets": study.datasets,
        "methods": study.methods,
        "configuration_files": {
            name: path.relative_to(root).as_posix()
            for name, path in configuration_files(study, root).items()
        },
        "pending_runtime_bindings": [
            name for name, value in study.runtime.model_dump().items() if value is None
        ],
        "workflow_execution_available": False,
        "checks": [
            "study declarations",
            "project-relative references",
            "linked YAML syntax and document identities",
        ],
    }


def plan_study(config_path: Path | None = None) -> dict[str, Any]:
    """List planned stages; this command executes no study work."""
    report = check_study(config_path)
    report["stages"] = [{"name": name, "status": "pending"} for name in STAGES]
    return report
