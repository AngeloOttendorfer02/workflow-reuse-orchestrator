"""Owned schemas reject invalid values and conflicting scientific declarations."""

from typing import Any

import pytest

from workflow_reuse_orchestrator.config import (
    DatasetConfig,
    EvaluationConfig,
    LearningConfig,
    project_root,
    read_yaml_mapping,
)


@pytest.mark.parametrize(
    "name,model,foreign_key",
    [
        ("datasets", DatasetConfig, "predictors"),
        ("learning", LearningConfig, "protocol_frozen"),
        ("evaluation", EvaluationConfig, "runtime"),
    ],
)
def test_scientific_documents_reject_cross_owned_fields(
    name: str, model: Any, foreign_key: str
) -> None:
    document = read_yaml_mapping(project_root() / "configs" / f"{name}.yaml")
    document[foreign_key] = None
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        model.model_validate(document)


@pytest.mark.parametrize("field", ["variant", "source_checksum", "grouping"])
def test_dataset_declarations_reject_invalid_source_metadata(field: str) -> None:
    document = read_yaml_mapping(project_root() / "configs/datasets.yaml")
    if field == "variant":
        document["datasets"]["hotpotqa"]["variant"] = "fullwiki"
    elif field == "source_checksum":
        document["datasets"]["drop"]["source_checksum"] = "not-a-checksum"
    else:
        document["partitions"]["grouping"] = "random_question_rows"
    with pytest.raises(ValueError):
        DatasetConfig.model_validate(document)


@pytest.mark.parametrize("invalid", ["features", "layers", "scope", "threshold", "nan"])
def test_learning_declarations_reject_unsafe_or_inconsistent_values(invalid: str) -> None:
    document = read_yaml_mapping(project_root() / "configs/learning.yaml")
    if invalid == "features":
        document["features"]["task_representation"] = 63
    elif invalid == "layers":
        document["mlp"]["hidden_sizes"] = [32]
    elif invalid == "scope":
        document["fitting_scope"] = "final_evaluation"
    else:
        document["selection_thresholds"] = {
            "success_probability": float("nan") if invalid == "nan" else 1.1,
            "cosine_similarity": 0.5,
            "tie_break": "workflow_id",
        }
    with pytest.raises(ValueError):
        LearningConfig.model_validate(document)


def test_frozen_protocol_cannot_be_a_flag_on_an_unresolved_draft() -> None:
    document = read_yaml_mapping(project_root() / "configs/evaluation.yaml")
    document["protocol_frozen"] = True
    with pytest.raises(ValueError, match="unresolved evaluation declarations"):
        EvaluationConfig.model_validate(document)


def test_draft_nulls_are_valid_declarations_not_scientific_evidence() -> None:
    root = project_root() / "configs"
    datasets = DatasetConfig.model_validate(read_yaml_mapping(root / "datasets.yaml"))
    learning = LearningConfig.model_validate(read_yaml_mapping(root / "learning.yaml"))
    evaluation = EvaluationConfig.model_validate(read_yaml_mapping(root / "evaluation.yaml"))
    assert datasets.snapshot_id is None
    assert learning.model_selection.selected_predictor is None
    assert evaluation.unresolved_fields()


@pytest.mark.parametrize("owner", ["datasets", "evaluation"])
def test_freeze_flags_must_be_booleans_not_strings(owner: str) -> None:
    document = read_yaml_mapping(project_root() / "configs" / f"{owner}.yaml")
    if owner == "datasets":
        document["partitions"]["final_evaluation_frozen"] = "false"
        model = DatasetConfig
    else:
        document["protocol_frozen"] = "false"
        model = EvaluationConfig
    with pytest.raises(ValueError):
        model.model_validate(document)
