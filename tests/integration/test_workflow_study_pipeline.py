"""The starter CLI must inspect configuration without claiming execution readiness."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import project_root, read_yaml_mapping
from workflow_reuse_orchestrator.domain.outcomes import Receipt
from workflow_reuse_orchestrator.experiments import pipeline
from workflow_reuse_orchestrator.runtime.ollama import OllamaProvider
from workflow_reuse_orchestrator.storage import ResultStore


def test_check_reports_pending_runtime_bindings(capsys) -> None:
    assert main(["pipeline", "check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "foundations_ready"
    assert report["runtime_check_available"] is True
    assert "prediction-reuse" in report["methods"]
    assert "prediction-reuse-mlp" not in report["methods"]
    assert report["predictors"] == [
        "logistic_regression",
        "random_forest",
        "gradient_boosted_trees",
        "mlp",
    ]
    assert report["model_selection"]["scope"] == "development_validation"
    assert report["model_selection"]["selected_predictor"] is None
    assert report["selector_training_available"] is False
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


def test_runtime_pilot_records_one_call_and_reads_completed_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    report = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert report["status"] == "passed"
    assert report["usage"]["model_calls"] == 1
    assert report["study_bindings_updated"] is False
    before = len(state["calls"])
    second = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert second["measurement_source"] == "stored_receipt"
    assert len(state["calls"]) == before
    with ResultStore(tmp_path / "results.sqlite3", read_only=True) as store:
        assert len(list(store.receipts("runtime_check"))) == 2
        assert store.receipt("runtime-check:000-started").status == "started"
        assert store.receipt("runtime-check:001-completed").status == "succeeded"


def test_unfinished_pilot_is_not_silently_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    # Model a crash after the started receipt committed and before completion.
    import sqlite3

    with sqlite3.connect(tmp_path / "results.sqlite3") as connection:
        connection.execute(
            "DELETE FROM receipts WHERE receipt_id=?", ("runtime-check:001-completed",)
        )
    before = len(state["calls"])
    with pytest.raises(ValueError, match="unknown outcome"):
        pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert len(state["calls"]) == before


def test_pilot_keeps_usage_on_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    state["generation"].update({"done_reason": "length", "eval_count": 128})
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    report = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert report["status"] == "failed"
    assert report["error"] == "generation_truncated"
    assert report["usage"]["output_tokens"] == 128


@pytest.mark.parametrize(
    "missing,error",
    [
        ("prompt_eval_count", "token_usage_unavailable"),
        ("done_reason", "completion_reason_unavailable"),
    ],
)
def test_cli_pilot_reports_failure_for_unavailable_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    missing: str,
    error: str,
) -> None:
    client, state = ollama_fixture
    state["generation"].pop(missing)
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    exit_code = main(
        ["pipeline", "runtime-check", "--model", "test-model:latest", "--output", str(tmp_path)]
    )
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert exit_code == 1
    if missing == "prompt_eval_count":
        assert report["usage"]["input_tokens"] is None
    else:
        assert report["usage"]["input_tokens"] == 10
    assert report["error"] == error
    assert "Executing one bounded" in output.err


@pytest.mark.parametrize(
    "response_text,finish_reason,error",
    [
        ("Reasoning first.\n</think>\n\nOK", "stop", "unexpected_thinking_output"),
        ("<think>Reasoning.</think>\nOK", "stop", "unexpected_thinking_output"),
        ("OK\n</THINK>", "stop", "unexpected_thinking_output"),
        ("Sure, OK", "stop", "unexpected_pilot_output"),
        ("ok", "stop", "unexpected_pilot_output"),
        ("OK", "unload", "unexpected_completion_reason"),
    ],
)
def test_cli_pilot_rejects_unexpected_output_and_preserves_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    response_text: str,
    finish_reason: str,
    error: str,
) -> None:
    client, state = ollama_fixture
    state["generation"].update(
        {
            "response": response_text,
            "done_reason": finish_reason,
            "prompt_eval_count": 15,
            "eval_count": 122,
        }
    )
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    assert (
        main(
            ["pipeline", "runtime-check", "--model", "test-model:latest", "--output", str(tmp_path)]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["error"] == error
    assert report["generation"]["output_text"] == response_text
    assert report["usage"]["model_calls"] == 1
    assert report["usage"]["input_tokens"] == 15
    assert report["usage"]["output_tokens"] == 122
    with ResultStore(tmp_path / "results.sqlite3", read_only=True) as store:
        completed = store.receipt("runtime-check:001-completed")
        assert completed is not None
        assert completed.status == "failed"
        assert completed.payload["generation"]["output_text"] == response_text
        assert completed.payload["usage"]["output_tokens"] == 122


def test_pilot_accepts_ok_with_surrounding_whitespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    state["generation"]["response"] = " \nOK\r\n"
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    report = pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert report["status"] == "passed"
    assert report["generation"]["output_text"] == " \nOK\r\n"


def test_previous_validator_receipt_is_not_reused_or_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ollama_fixture: tuple[httpx.Client, dict[str, Any]],
) -> None:
    client, state = ollama_fixture
    monkeypatch.setattr(pipeline, "OllamaProvider", lambda **kwargs: OllamaProvider(client=client))
    with ResultStore(tmp_path / "results.sqlite3") as store:
        store.bind("run_parameters", {"purpose": "infrastructure_pilot"})
        store.put_receipt(
            Receipt(
                receipt_id="runtime-check:001-completed",
                kind="runtime_check",
                status="succeeded",
                payload={"status": "passed"},
            )
        )
    with pytest.raises(ValueError, match="new output folder"):
        pipeline.runtime_check(model_name="test-model:latest", output_dir=tmp_path)
    assert state["calls"] == []
    with ResultStore(tmp_path / "results.sqlite3", read_only=True) as store:
        completed = store.receipt("runtime-check:001-completed")
        assert completed is not None
        assert completed.status == "succeeded"
        assert store.binding("run_parameters") == {"purpose": "infrastructure_pilot"}


@pytest.mark.parametrize("invalid", ["duplicate_family", "final_scope"])
def test_cli_rejects_invalid_learning_before_runtime_work(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    invalid: str,
) -> None:
    source = project_root()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "workflow-reuse-orchestrator"\n', encoding="utf-8"
    )
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in ("study", "datasets", "learning", "evaluation"):
        document = read_yaml_mapping(source / "configs" / f"{name}.yaml")
        if name == "learning":
            if invalid == "duplicate_family":
                document["predictors"][1] = document["predictors"][0]
            else:
                document["model_selection"]["scope"] = "final_evaluation"
        (configs / f"{name}.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    assert main(["pipeline", "check", "--config", str(configs / "study.yaml")]) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "Pipeline failed:" in result.err
    assert not (tmp_path / "runs").exists()


def test_new_configuration_does_not_relabel_historical_receipts(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    original = Receipt(
        receipt_id="historical-policy:001",
        kind="policy_outcome",
        status="succeeded",
        payload={"method_id": "prediction-reuse-mlp", "predictor": "mlp"},
    )
    with ResultStore(database) as store:
        store.put_receipt(original)
    assert "prediction-reuse" in pipeline.check_study()["methods"]
    with ResultStore(database, read_only=True) as store:
        retained = store.receipt(original.receipt_id)
        assert retained is not None
        assert retained == original
        assert retained.payload["method_id"] == "prediction-reuse-mlp"
