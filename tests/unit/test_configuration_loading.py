"""Configuration failures must be visible before any runtime work starts."""

from pathlib import Path
from typing import Any

import pytest

from workflow_reuse_orchestrator.config import (
    PredictorDeclarations,
    RuntimeBindings,
    StudyConfig,
    load_study,
    project_root,
    read_yaml_mapping,
    resolve_project_path,
)
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ModelBinding


def test_loads_study_from_a_project_subdirectory(monkeypatch: pytest.MonkeyPatch) -> None:
    root = project_root()
    monkeypatch.chdir(root / "notebooks")
    study = load_study(Path("configs/study.yaml"))
    assert study.datasets == ["hotpotqa", "drop", "finqa"]
    assert study.runtime.model is None


@pytest.mark.parametrize("field", ["datasets", "methods"])
def test_rejects_duplicate_study_members(field: str) -> None:
    document = read_yaml_mapping(project_root() / "configs/study.yaml")
    document[field][1] = document[field][0]
    with pytest.raises(ValueError, match="must be unique"):
        StudyConfig.model_validate(document)


@pytest.mark.parametrize("relative_path", [Path("../outside.yaml"), Path("/outside.yaml")])
def test_rejects_configuration_paths_outside_project(tmp_path: Path, relative_path: Path) -> None:
    with pytest.raises(ValueError, match="project"):
        resolve_project_path(tmp_path, relative_path)


def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("datasets: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid YAML"):
        read_yaml_mapping(path)


def test_rejects_a_yaml_list_instead_of_a_configuration(tmp_path: Path) -> None:
    path = tmp_path / "wrong.yaml"
    path.write_text("- hotpotqa\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a YAML mapping"):
        read_yaml_mapping(path)


def test_typed_bindings_reject_context_above_native_capacity(model_binding: ModelBinding) -> None:
    with pytest.raises(ValueError, match="native context"):
        RuntimeBindings(
            model=model_binding,
            inference=InferenceProfile(num_ctx=16384, num_predict=128, seed=2609),
        )


def test_typed_bindings_require_one_safe_generation(
    inference_profile: InferenceProfile, request_budget: RequestBudget
) -> None:
    with pytest.raises(ValueError, match="one bounded generation"):
        RuntimeBindings(
            inference=inference_profile,
            request_limits=request_budget.model_copy(update={"max_input_tokens": 10}),
        )


@pytest.fixture
def learning_document() -> dict[str, Any]:
    return read_yaml_mapping(project_root() / "configs/learning.yaml")


def test_active_study_uses_generic_prediction_reuse(learning_document: dict[str, Any]) -> None:
    study = load_study()
    declarations = PredictorDeclarations.model_validate(learning_document)
    assert "prediction-reuse" in study.methods
    assert declarations.predictors == [
        "logistic_regression",
        "random_forest",
        "gradient_boosted_trees",
        "mlp",
    ]
    assert declarations.model_selection.scope == "development_validation"
    assert declarations.model_selection.decision_rule is None
    assert declarations.model_selection.selected_predictor is None


def test_active_configuration_rejects_old_method_without_relabeling_it() -> None:
    document = read_yaml_mapping(project_root() / "configs/study.yaml")
    document["methods"][-1] = "prediction-reuse-mlp"
    with pytest.raises(ValueError, match="Historical receipts must retain"):
        StudyConfig.model_validate(document)
    assert document["methods"][-1] == "prediction-reuse-mlp"


@pytest.mark.parametrize("invalid", ["duplicate", "unknown", "missing"])
def test_rejects_invalid_candidate_families(
    learning_document: dict[str, Any], invalid: str
) -> None:
    if invalid == "duplicate":
        learning_document["predictors"][1] = "logistic_regression"
    elif invalid == "unknown":
        learning_document["predictors"][1] = "unknown_estimator"
    else:
        learning_document["predictors"].pop()
    with pytest.raises(ValueError):
        PredictorDeclarations.model_validate(learning_document)


@pytest.mark.parametrize("invalid", ["final_scope", "duplicate_criterion", "unknown_criterion"])
def test_rejects_invalid_model_selection_declarations(
    learning_document: dict[str, Any], invalid: str
) -> None:
    selection = learning_document["model_selection"]
    if invalid == "final_scope":
        selection["scope"] = "final_evaluation"
    elif invalid == "duplicate_criterion":
        selection["criteria"][1] = selection["criteria"][0]
    else:
        selection["criteria"][1] = "final_answer_accuracy"
    with pytest.raises(ValueError):
        PredictorDeclarations.model_validate(learning_document)


@pytest.mark.parametrize(
    "family", ["logistic_regression", "random_forest", "gradient_boosted_trees", "mlp"]
)
def test_each_declared_family_can_be_selected_with_an_explicit_rule(
    learning_document: dict[str, Any], family: str
) -> None:
    selection = learning_document["model_selection"]
    selection["decision_rule"] = "Registered development-validation selection rule."
    selection["selected_predictor"] = family
    declarations = PredictorDeclarations.model_validate(learning_document)
    assert declarations.model_selection.selected_predictor == family


def test_selected_predictor_requires_a_recorded_rule(learning_document: dict[str, Any]) -> None:
    learning_document["model_selection"]["selected_predictor"] = "mlp"
    with pytest.raises(ValueError, match="before declaring a selected predictor"):
        PredictorDeclarations.model_validate(learning_document)


def test_rejects_blank_selection_rule(learning_document: dict[str, Any]) -> None:
    learning_document["model_selection"]["decision_rule"] = "  "
    with pytest.raises(ValueError, match="must not be blank"):
        PredictorDeclarations.model_validate(learning_document)


def test_rejects_an_unknown_selected_predictor(learning_document: dict[str, Any]) -> None:
    learning_document["model_selection"].update(
        decision_rule="Registered rule.", selected_predictor="unknown_estimator"
    )
    with pytest.raises(ValueError):
        PredictorDeclarations.model_validate(learning_document)
