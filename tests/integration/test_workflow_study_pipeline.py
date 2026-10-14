"""The starter CLI must inspect configuration without claiming execution readiness."""

import json
from pathlib import Path

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import project_root


def test_check_reports_pending_runtime_bindings(capsys) -> None:
    assert main(["pipeline", "check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "scaffold_ready"
    assert report["workflow_execution_available"] is False
    assert set(report["pending_runtime_bindings"]) == {
        "model",
        "encoder",
        "inference",
        "prompts",
        "request_limits",
    }


def test_plan_reports_pending_stages(capsys) -> None:
    assert main(["pipeline", "plan"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["stages"][0] == {"name": "prepare_data", "status": "pending"}
    assert report["stages"][-1] == {"name": "analyze_results", "status": "pending"}
    assert all(stage["status"] == "pending" for stage in report["stages"])


def test_missing_configuration_returns_actionable_failure(capsys) -> None:
    missing = project_root() / "configs/missing.yaml"
    assert main(["pipeline", "check", "--config", str(missing)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Pipeline failed:" in output.err
    assert Path("missing.yaml").name in output.err
