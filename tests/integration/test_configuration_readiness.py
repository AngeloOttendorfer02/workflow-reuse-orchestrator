"""Offline gates distinguish declarations, bound bytes, and missing verifiers."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import load_study_bundle, project_root, read_yaml_mapping
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ModelBinding
from workflow_reuse_orchestrator.evaluation.scoring import scorer_declaration
from workflow_reuse_orchestrator.experiments.pipeline import check_study


@pytest.fixture
def configured_root(
    tmp_path: Path,
    model_binding: ModelBinding,
    inference_profile: InferenceProfile,
    request_budget: RequestBudget,
) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "workflow-reuse-orchestrator"\n', encoding="utf-8"
    )
    shutil.copytree(project_root() / "configs", tmp_path / "configs")
    path = tmp_path / "configs/study.yaml"
    document = read_yaml_mapping(path)
    prompts = {}
    for role in ("coordinator", "retrieval", "reasoning", "checking", "generalization"):
        relative = Path("configs/prompts") / f"{role}.md"
        prompts[role] = {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest(),
        }
    document["runtime"] = {
        "model": model_binding.model_dump(mode="json"),
        "inference": inference_profile.model_dump(mode="json"),
        "request_limits": request_budget.model_dump(mode="json"),
        "encoder": {
            "model_id": "fixture-encoder",
            "revision": "a" * 40,
            "tokenizer_revision": "b" * 40,
            "serialization_version": "serialization-v1",
            "pooling": "mean",
        },
        "prompts": prompts,
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return tmp_path


def test_current_draft_only_passes_the_scaffold_gate() -> None:
    report = check_study()
    assert report["status"] == "foundations_ready"
    assert report["ready"] is True
    assert report["readiness"] == {
        "scaffold_valid": True,
        "runtime_bound": False,
        "data_ready": False,
        "protected_release_ready": False,
    }
    assert report["runtime_contacted"] is False


@pytest.mark.parametrize("level", ["runtime", "data", "protected"])
def test_cli_returns_nonzero_for_unmet_requested_readiness(
    level: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["pipeline", "check", "--level", level]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "blocked"
    assert report["requested_level"] == level
    assert report["ready"] is False
    assert output.err == ""


def test_runtime_bound_checks_declarations_and_prompt_bytes_without_contact(
    configured_root: Path,
) -> None:
    report = check_study(configured_root / "configs/study.yaml", level="runtime")
    assert report["status"] == "runtime_bound"
    assert report["ready"] is True
    assert report["runtime_contacted"] is False
    assert report["workflow_execution_available"] is False
    assert report["selector_training_available"] is False


def test_changed_prompt_bytes_block_runtime_gate(configured_root: Path) -> None:
    (configured_root / "configs/prompts/reasoning.md").write_text("changed", encoding="utf-8")
    report = check_study(configured_root / "configs/study.yaml", level="runtime")
    assert report["ready"] is False
    assert any("reasoning checksum" in reason for reason in report["blockers"]["runtime_bound"])


def test_runtime_prompt_cannot_escape_project(configured_root: Path) -> None:
    path = configured_root / "configs/study.yaml"
    document = read_yaml_mapping(path)
    document["runtime"]["prompts"]["reasoning"]["path"] = "../outside.md"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    report = check_study(path, level="runtime")
    assert report["ready"] is False
    assert any("leaves the project" in reason for reason in report["blockers"]["runtime_bound"])


def complete_declarations(root: Path) -> None:
    datasets_path = root / "configs/datasets.yaml"
    datasets = read_yaml_mapping(datasets_path)
    for dataset in ("hotpotqa", "drop", "finqa"):
        datasets["datasets"][dataset].update(release="fixture-release", source_checksum="a" * 64)
    datasets["snapshot_id"] = "fixture-snapshot"
    datasets["partitions"].update(assignment_version="groups-v1", final_evaluation_frozen=True)
    datasets_path.write_text(yaml.safe_dump(datasets), encoding="utf-8")
    learning_path = root / "configs/learning.yaml"
    learning = read_yaml_mapping(learning_path)
    learning["model_selection"].update(
        decision_rule="Registered fixture rule.", selected_predictor="logistic_regression"
    )
    learning["calibration"] = {"method": "sigmoid", "fitting_role": "selector_calibration"}
    learning["selection_thresholds"] = {
        "success_probability": 0.8,
        "cosine_similarity": 0.5,
        "tie_break": "workflow_id",
    }
    learning["development_cost_estimates"] = {
        "basis": "development_executions",
        "fallback": "workflow_structure",
        "estimator_version": "costs-v1",
    }
    learning_path.write_text(yaml.safe_dump(learning), encoding="utf-8")
    evaluation_path = root / "configs/evaluation.yaml"
    evaluation = read_yaml_mapping(evaluation_path)
    evaluation.update(
        protocol_frozen=True,
        scoring={dataset: scorer_declaration(dataset) for dataset in ("hotpotqa", "drop", "finqa")},
        correctness_loss_margins={"hotpotqa": 0.02, "drop": 0.02, "finqa": 0.02},
        final_population={
            "snapshot_id": "fixture-snapshot",
            "counts": {"hotpotqa": 2, "drop": 2, "finqa": 2},
        },
        sampling={
            "mode": "full",
            "sample_id": "sample-v1",
            "assignment_version": "groups-v1",
            "seed": 2609,
        },
        statistics={
            "confidence_level": 0.95,
            "bootstrap_resamples": 100,
            "resampling_unit": "source_group",
            "paired_test": "fixture-test",
            "multiplicity": "holm",
            "seed": 2609,
        },
        repetitions={"executions": 3, "subset_id": "subset-v1", "seed": 2609},
        human_assessment={
            "assessors": 2,
            "sample_id": "human-v1",
            "rubric_version": "v1",
            "blind_methods": True,
            "agreement_before_reconciliation": True,
        },
        cache_and_method_order={
            "cache_policy": "miss",
            "warmup_policy": "excluded_and_reported",
            "method_order": "balanced",
            "concurrency": 1,
            "seed": 2609,
        },
    )
    evaluation_path.write_text(yaml.safe_dump(evaluation), encoding="utf-8")


def test_complete_declarations_and_frozen_flags_cannot_fake_scientific_readiness(
    configured_root: Path,
) -> None:
    complete_declarations(configured_root)
    # Merely creating a file with the planned name is not a snapshot verifier.
    snapshot = configured_root / "data/processed/fixture-snapshot/datasets.sqlite3"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"not an audited dataset snapshot")
    report = check_study(configured_root / "configs/study.yaml", level="protected")
    assert report["readiness"]["runtime_bound"] is True
    assert report["readiness"]["data_ready"] is False
    assert report["readiness"]["protected_release_ready"] is False
    assert any("not implemented" in reason for reason in report["blockers"]["data_ready"])
    assert any(
        "not implemented" in reason for reason in report["blockers"]["protected_release_ready"]
    )


@pytest.mark.parametrize("conflict", ["snapshot", "assignment", "frozen_groups"])
def test_inconsistent_cross_document_identities_fail_before_gate_checks(
    configured_root: Path, conflict: str
) -> None:
    complete_declarations(configured_root)
    path = configured_root / "configs/evaluation.yaml"
    evaluation = read_yaml_mapping(path)
    if conflict == "snapshot":
        evaluation["final_population"]["snapshot_id"] = "another-snapshot"
    elif conflict == "assignment":
        evaluation["sampling"]["assignment_version"] = "another-assignment"
    else:
        path = configured_root / "configs/datasets.yaml"
        datasets = read_yaml_mapping(path)
        datasets["partitions"]["final_evaluation_frozen"] = False
        path.write_text(yaml.safe_dump(datasets), encoding="utf-8")
    if conflict != "frozen_groups":
        path.write_text(yaml.safe_dump(evaluation), encoding="utf-8")
    with pytest.raises(ValueError):
        load_study_bundle(configured_root / "configs/study.yaml")


def test_invalid_level_is_a_cli_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["pipeline", "check", "--level", "everything"])
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
