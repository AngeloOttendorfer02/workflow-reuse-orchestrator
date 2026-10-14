"""Configuration failures must be visible before any runtime work starts."""

from pathlib import Path

import pytest

from workflow_reuse_orchestrator.config import (
    StudyConfig,
    load_study,
    project_root,
    read_yaml_mapping,
    resolve_project_path,
)


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
