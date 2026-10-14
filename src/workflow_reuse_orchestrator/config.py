"""Load the starter study declarations and project-relative configuration files."""

import os
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ModelBinding
from workflow_reuse_orchestrator.domain.tasks import DatasetId

MethodId = Literal[
    "single-agent",
    "fixed-workflow",
    "per-question-planning",
    "similarity-reuse",
    "prediction-reuse-mlp",
]


class RuntimeBindings(BaseModel):
    """Typed model/inference/request limits; encoder and prompts remain reserved."""

    model_config = ConfigDict(extra="forbid")

    model: ModelBinding | None = None
    encoder: dict[str, Any] | None = None
    inference: InferenceProfile | None = None
    prompts: dict[str, Any] | None = None
    request_limits: RequestBudget | None = None

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if (
            self.model is not None
            and self.inference is not None
            and self.inference.num_ctx > self.model.native_context_tokens
        ):
            raise ValueError("Inference context exceeds the bound model's native context.")
        if (
            self.inference is not None
            and self.request_limits is not None
            and (
                self.request_limits.max_input_tokens < self.inference.num_ctx
                or self.request_limits.max_output_tokens < self.inference.num_predict
            )
        ):
            raise ValueError("Request limits must permit at least one bounded generation.")
        return self


class StudyConfig(BaseModel):
    """The fixed study identity and locations of its configuration documents."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["workflow-study-v1"]
    profile: Literal["workflow_reuse"]
    seed: int = Field(ge=0)
    datasets: list[DatasetId] = Field(min_length=3, max_length=3)
    methods: list[MethodId] = Field(min_length=5, max_length=5)
    datasets_config: Path
    learning_config: Path
    evaluation_config: Path
    runtime: RuntimeBindings

    @field_validator("datasets", "methods")
    @classmethod
    def require_unique_values(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Every configured dataset and method must be unique.")
        return values


def project_root(start: Path | None = None) -> Path:
    """Find this project's root from the working directory or a supplied location."""
    location = (start or Path.cwd()).resolve()
    if location.is_file():
        location = location.parent
    for directory in (location, *location.parents):
        metadata = directory / "pyproject.toml"
        if not metadata.is_file():
            continue
        with metadata.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
        if project.get("name") == "workflow-reuse-orchestrator":
            return directory
    raise ValueError("Run this command inside the workflow-reuse-orchestrator project.")


def resolve_project_path(root: Path, relative_path: Path) -> Path:
    """Resolve a configuration reference within the project."""
    if relative_path.is_absolute():
        raise ValueError(f"Configuration references must be project-relative: {relative_path}")
    location = (root / relative_path).resolve()
    if not location.is_relative_to(root.resolve()):
        raise ValueError(f"Configuration reference leaves the project: {relative_path}")
    return location


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read a YAML mapping and report syntax errors with its filename."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict) or not all(isinstance(key, str) for key in document):
        raise ValueError(f"Expected a YAML mapping with string keys in {path}.")
    return document


def configuration_files(study: StudyConfig, root: Path) -> dict[str, Path]:
    """Return the three linked configuration paths."""
    return {
        "datasets": resolve_project_path(root, study.datasets_config),
        "learning": resolve_project_path(root, study.learning_config),
        "evaluation": resolve_project_path(root, study.evaluation_config),
    }


def load_study(path: Path | None = None) -> StudyConfig:
    """Validate the study declarations and the linked YAML document identities.

    The starter does not verify model metadata, dataset partitions, feature
    implementations, or evaluation readiness. Their work packages add those checks.
    """
    root = project_root(path.parent if path is not None and path.is_absolute() else None)
    location = root / "configs/study.yaml" if path is None else path
    if not location.is_absolute():
        location = resolve_project_path(root, location)
    elif not location.resolve().is_relative_to(root):
        raise ValueError("The study configuration must be inside the project.")
    study = StudyConfig.model_validate(read_yaml_mapping(location))
    for name, linked_path in configuration_files(study, root).items():
        document = read_yaml_mapping(linked_path)
        expected_version = f"workflow-{name}-v1"
        if document.get("schema_version") != expected_version:
            raise ValueError(f"Expected schema_version {expected_version!r} in {linked_path}.")
    return study


def ollama_base_url(override: str | None = None) -> str:
    """Use an explicit endpoint, its environment setting, or the local default."""
    return override or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
