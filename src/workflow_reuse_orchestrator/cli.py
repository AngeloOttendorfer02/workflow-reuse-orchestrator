"""Command-line entry point for the workflow study."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from workflow_reuse_orchestrator import __version__
from workflow_reuse_orchestrator.config import load_study_bundle
from workflow_reuse_orchestrator.data.drop import DropEvaluationReference, normalize_drop
from workflow_reuse_orchestrator.data.finqa import FinqaEvaluationReference, normalize_finqa
from workflow_reuse_orchestrator.data.hotpotqa import normalize_hotpotqa
from workflow_reuse_orchestrator.data.prepare import acquire_dataset
from workflow_reuse_orchestrator.domain.providers import ProviderError
from workflow_reuse_orchestrator.domain.tasks import DatasetId, EvaluationReference
from workflow_reuse_orchestrator.evaluation.scoring import (
    AnswerSubmission,
    score_submission,
    scorer_identity,
)
from workflow_reuse_orchestrator.experiments.pipeline import (
    VALIDATION_LEVELS,
    ValidationLevel,
    check_study,
    inspect_run,
    inspect_runtime_model,
    migrate_run,
    plan_study,
    runtime_check,
    runtime_models,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestrator", description="Task-adaptive document reasoning through workflow reuse."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("data", help="Acquire and normalize versioned benchmark sources.")
    data_operations = data.add_subparsers(dest="operation", required=True)
    for name in ("sources", "acquire"):
        operation = data_operations.add_parser(name)
        operation.add_argument("--config", type=Path)
        if name == "acquire":
            operation.add_argument(
                "--dataset", choices=("all", "hotpotqa", "drop", "finqa"), required=True
            )
            operation.add_argument(
                "--split", choices=("all", "train", "dev", "test"), default="all"
            )
            operation.add_argument("--raw-root", type=Path)
            operation.add_argument("--timeout-seconds", type=float, default=60.0)
    normalize = data_operations.add_parser(
        "normalize", help="Normalize acquired benchmark data offline."
    )
    normalize.add_argument("--config", type=Path)
    normalize.add_argument("--dataset", choices=("hotpotqa", "drop", "finqa"), required=True)
    normalize.add_argument("--split", choices=("all", "train", "dev", "test"), default="all")
    normalize.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    normalize.add_argument("--output", type=Path, required=True)
    evaluation = commands.add_parser("evaluation", help="Inspect or apply offline answer scorers.")
    evaluation_operations = evaluation.add_subparsers(dest="operation", required=True)
    scorers = evaluation_operations.add_parser(
        "scorers", help="Show versioned implemented scorer identities."
    )
    scorers.add_argument("--config", type=Path)
    score = evaluation_operations.add_parser(
        "score", help="Score one explicit submission/reference pair."
    )
    score.add_argument("--submission", type=Path, required=True)
    score.add_argument("--reference", type=Path, required=True)
    pipeline = commands.add_parser(
        "pipeline", help="Inspect study configuration and planned stages."
    )
    operations = pipeline.add_subparsers(dest="operation", required=True)
    for name, help_text in (
        ("check", "Validate typed declarations and an explicit offline readiness gate."),
        ("plan", "Show the study's planned stages without executing them."),
    ):
        operation = operations.add_parser(name, help=help_text)
        operation.add_argument("--config", type=Path, help="Project-relative study configuration.")
        if name == "check":
            operation.add_argument(
                "--level",
                choices=VALIDATION_LEVELS,
                default="scaffold",
                help="Readiness gate to require; all configuration checks are offline.",
            )
    pilot = operations.add_parser(
        "runtime-check", help="Record one infrastructure-pilot generation."
    )
    pilot.add_argument("--config", type=Path)
    pilot.add_argument("--model", required=True, help="Exact installed Ollama model name.")
    pilot.add_argument("--output", required=True, type=Path)
    pilot.add_argument("--base-url")
    pilot.add_argument("--num-ctx", type=int)
    pilot.add_argument("--num-predict", type=int)
    pilot.add_argument("--timeout-seconds", type=float, default=60.0)
    pilot.add_argument(
        "--retry-of", help="Failed/unknown job ID; creates an explicit new pilot trial."
    )
    for name, help_text in (
        ("status", "Read stored progress/events without changing the database."),
        ("migrate", "Explicitly add the v2 job ledger to a schema-v1 database."),
    ):
        operation = operations.add_parser(name, help=help_text)
        operation.add_argument("--output", required=True, type=Path)
        if name == "status":
            operation.add_argument("--job", help="Include one job and its ordered events.")
    runtime = commands.add_parser("runtime", help="List models and inspect model fingerprints.")
    runtime_operations = runtime.add_subparsers(dest="operation", required=True)
    models = runtime_operations.add_parser("models", help="List installed Ollama model names.")
    models.add_argument("--base-url")
    inspect = runtime_operations.add_parser(
        "inspect", help="Read and fingerprint one installed model."
    )
    inspect.add_argument("--model", required=True)
    inspect.add_argument("--base-url")
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluation":
            if args.operation == "scorers":
                bundle = load_study_bundle(args.config)
                if any(
                    getattr(bundle.evaluation.scoring, d) is None for d in bundle.study.datasets
                ):
                    raise ValueError("Every selected dataset requires a configured scorer.")
                report = {
                    "status": "configured",
                    "scorers": {d: scorer_identity(d) for d in bundle.study.datasets},
                    "runtime_contacted": False,
                    "study_bindings_updated": False,
                }
            else:
                submission = AnswerSubmission.model_validate_json(
                    args.submission.read_text("utf-8")
                )
                reference_types: dict[DatasetId, type[EvaluationReference]] = {
                    "hotpotqa": EvaluationReference,
                    "drop": DropEvaluationReference,
                    "finqa": FinqaEvaluationReference,
                }
                reference_type = reference_types[submission.dataset_id]
                reference = reference_type.model_validate_json(args.reference.read_text("utf-8"))
                report = score_submission(submission, reference).model_dump(mode="json")
        elif args.command == "data":
            bundle = load_study_bundle(args.config)
            catalog = bundle.datasets.acquisition
            if catalog is None:
                raise ValueError("No raw acquisition catalog is configured in datasets.yaml.")
            if args.operation == "sources":
                report = {
                    "status": "configured",
                    "acquisition": catalog.model_dump(mode="json"),
                    "runtime_contacted": False,
                    "data_snapshot_available": False,
                }
            elif args.operation == "normalize":
                raw_root = args.raw_root
                output = args.output
                if not raw_root.is_absolute():
                    raw_root = bundle.root / raw_root
                if not output.is_absolute():
                    output = bundle.root / output
                normalizer = {
                    "hotpotqa": normalize_hotpotqa,
                    "drop": normalize_drop,
                    "finqa": normalize_finqa,
                }[args.dataset]
                report = normalizer(
                    getattr(catalog, args.dataset),
                    raw_root,
                    output,
                    split=args.split,
                    progress=lambda message: print(message, file=sys.stderr),
                )
            else:
                datasets: list[DatasetId] = (
                    ["hotpotqa", "drop", "finqa"]
                    if args.dataset == "all"
                    else [cast(DatasetId, args.dataset)]
                )
                raw_root = args.raw_root or Path("data/raw")
                if not raw_root.is_absolute():
                    raw_root = bundle.root / raw_root
                # Reject an unsupported split for any selected dataset before downloading any.
                if any(
                    not any(
                        args.split == "all" or args.split in s.splits
                        for s in getattr(catalog, dataset).sources
                    )
                    for dataset in datasets
                ):
                    raise ValueError(
                        "The requested native split is not available for every dataset."
                    )
                results = [
                    acquire_dataset(
                        dataset,
                        getattr(catalog, dataset),
                        raw_root,
                        split=args.split,
                        timeout_seconds=args.timeout_seconds,
                        progress=lambda message: print(message, file=sys.stderr),
                    )
                    for dataset in datasets
                ]
                report = {
                    "status": "completed",
                    "datasets": results,
                    "workflow_execution_available": False,
                    "study_bindings_updated": False,
                }
        elif args.command == "runtime":
            report = (
                runtime_models(args.base_url)
                if args.operation == "models"
                else inspect_runtime_model(args.model, args.base_url)
            )
        elif args.operation == "check":
            report = check_study(args.config, level=cast(ValidationLevel, args.level))
        elif args.operation == "plan":
            report = plan_study(args.config)
        elif args.operation == "status":
            report = inspect_run(args.output, job_id=args.job)
        elif args.operation == "migrate":
            report = migrate_run(args.output)
        else:
            report = runtime_check(
                model_name=args.model,
                output_dir=args.output,
                config_path=args.config,
                base_url=args.base_url,
                num_ctx=args.num_ctx,
                num_predict=args.num_predict,
                timeout_seconds=args.timeout_seconds,
                progress=lambda message: print(message, file=sys.stderr),
                retry_of=args.retry_of,
            )
    except (OSError, ValueError, ProviderError, sqlite3.Error) as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 1 if report.get("status") in {"failed", "blocked"} else 0
