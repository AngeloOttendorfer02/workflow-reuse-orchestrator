"""Command-line entry point for the workflow study."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from workflow_reuse_orchestrator import __version__
from workflow_reuse_orchestrator.domain.providers import ProviderError
from workflow_reuse_orchestrator.experiments.pipeline import (
    check_study,
    inspect_runtime_model,
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
    pipeline = commands.add_parser(
        "pipeline", help="Inspect study configuration and planned stages."
    )
    operations = pipeline.add_subparsers(dest="operation", required=True)
    for name, help_text in (
        ("check", "Validate starter declarations and linked YAML documents offline."),
        ("plan", "Show the study's planned stages without executing them."),
    ):
        operation = operations.add_parser(name, help=help_text)
        operation.add_argument("--config", type=Path, help="Project-relative study configuration.")
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
        if args.command == "runtime":
            report = (
                runtime_models(args.base_url)
                if args.operation == "models"
                else inspect_runtime_model(args.model, args.base_url)
            )
        elif args.operation == "check":
            report = check_study(args.config)
        elif args.operation == "plan":
            report = plan_study(args.config)
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
            )
    except (OSError, ValueError, ProviderError) as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 1 if report.get("status") == "failed" else 0
