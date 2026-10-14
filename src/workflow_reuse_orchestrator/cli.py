"""Command-line entry point for the workflow study."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from workflow_reuse_orchestrator import __version__
from workflow_reuse_orchestrator.experiments.pipeline import check_study, plan_study


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
    args = parser.parse_args(argv)
    try:
        report = check_study(args.config) if args.operation == "check" else plan_study(args.config)
    except (OSError, ValueError) as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0
