"""Load and validate owned workflow-study configuration declarations."""

import os
import tomllib
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from workflow_reuse_orchestrator.data.prepare import AcquisitionCatalog
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import InferenceProfile, ModelBinding, Sha256
from workflow_reuse_orchestrator.domain.tasks import DatasetId, Identifier
from workflow_reuse_orchestrator.evaluation.scoring import validate_scorer_declarations

MethodId = Literal[
    "single-agent",
    "fixed-workflow",
    "per-question-planning",
    "similarity-reuse",
    "prediction-reuse",
]


PredictorId = Literal["logistic_regression", "random_forest", "gradient_boosted_trees", "mlp"]
SelectionCriterion = Literal["predictive_performance", "calibration", "prediction_overhead"]


class ModelSelectionDeclarations(BaseModel):
    """Development-only selection declarations, not fitted predictor state."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["development_validation"]
    criteria: list[SelectionCriterion] = Field(min_length=3, max_length=3)
    decision_rule: str | None = None
    selected_predictor: PredictorId | None = None

    @field_validator("criteria")
    @classmethod
    def require_distinct_criteria(
        cls, values: list[SelectionCriterion]
    ) -> list[SelectionCriterion]:
        if len(set(values)) != len(values):
            raise ValueError("Model-selection criteria must be unique.")
        return values

    @field_validator("decision_rule")
    @classmethod
    def require_nonempty_rule(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("The model-selection decision rule must not be blank.")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_rule_for_selected_predictor(self) -> Self:
        if self.selected_predictor is not None and self.decision_rule is None:
            raise ValueError(
                "Record a validation decision rule before declaring a selected predictor."
            )
        return self


class PredictorDeclarations(BaseModel):
    """Validate the predictor subset of the still-draft learning configuration.

    Features, estimator parameters, calibration and thresholds receive their full
    scientific schemas in later work packages. This contract does not fit models
    or certify a release for final evaluation.
    """

    model_config = ConfigDict(extra="ignore")

    predictors: list[PredictorId] = Field(min_length=4, max_length=4)
    model_selection: ModelSelectionDeclarations

    @field_validator("predictors")
    @classmethod
    def require_distinct_predictors(cls, values: list[PredictorId]) -> list[PredictorId]:
        if len(set(values)) != len(values):
            raise ValueError("Candidate predictors must be unique.")
        return values


class Declaration(BaseModel):
    """Owned declaration fields; unknown keys and nonfinite values are errors."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EncoderBinding(Declaration):
    model_id: Identifier
    revision: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$", strict=True)
    ]
    tokenizer_revision: Annotated[
        str, StringConstraints(pattern=r"^[0-9a-f]{40}([0-9a-f]{24})?$", strict=True)
    ]
    serialization_version: Identifier
    pooling: Literal["mean", "cls"]


class PromptFileBinding(Declaration):
    path: Path
    sha256: Sha256


class PromptBindings(Declaration):
    coordinator: PromptFileBinding
    retrieval: PromptFileBinding
    reasoning: PromptFileBinding
    checking: PromptFileBinding
    generalization: PromptFileBinding


class SourceRelease(Declaration):
    release: Identifier | None
    source_checksum: Sha256 | None


class HotpotRelease(SourceRelease):
    variant: Literal["distractor"]


class DatasetReleases(Declaration):
    hotpotqa: HotpotRelease
    drop: SourceRelease
    finqa: SourceRelease


class PartitionDeclarations(Declaration):
    grouping: Literal["connected_source_groups"]
    assignment_version: Identifier | None
    final_evaluation_frozen: bool = Field(strict=True)


class DatasetConfig(Declaration):
    schema_version: Literal["workflow-datasets-v1"]
    status: Literal["draft", "configured"]
    datasets: DatasetReleases
    snapshot_id: Identifier | None
    partitions: PartitionDeclarations
    acquisition: AcquisitionCatalog | None = None


class FeatureDimensions(Declaration):
    """The main 140-column interface; ablations are separate fitted variants."""

    task_representation: Literal[64]
    workflow_representation: Literal[64]
    task_metadata: Literal[4]
    graph_metadata: Literal[6]
    compatibility: Literal[2]
    total: Literal[140]


class MLPCandidate(Declaration):
    hidden_layers: int = Field(ge=1, strict=True)
    hidden_sizes: list[Annotated[int, Field(ge=1, strict=True)]] | None

    @model_validator(mode="after")
    def match_layer_widths(self) -> Self:
        if self.hidden_sizes is not None and len(self.hidden_sizes) != self.hidden_layers:
            raise ValueError("MLP hidden_sizes must contain one width per hidden layer.")
        return self


class CalibrationDeclarations(Declaration):
    method: Literal["sigmoid", "isotonic"]
    fitting_role: Literal["selector_calibration"]


class SelectionThresholds(Declaration):
    success_probability: float = Field(ge=0, le=1)
    cosine_similarity: float = Field(ge=-1, le=1)
    tie_break: Literal["workflow_id"]


class DevelopmentCostDeclarations(Declaration):
    basis: Literal["development_executions"]
    fallback: Literal["workflow_structure"]
    estimator_version: Identifier


class LearningConfig(PredictorDeclarations):
    """Owned learning declarations; fitted-state verification is still separate."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["workflow-learning-v1"]
    status: Literal["draft", "configured"]
    features: FeatureDimensions
    mlp: MLPCandidate
    fitting_scope: Literal["development_only"]
    calibration: CalibrationDeclarations | None
    selection_thresholds: SelectionThresholds | None
    development_cost_estimates: DevelopmentCostDeclarations | None


class ScorerDeclaration(Declaration):
    name: Identifier
    version: Identifier
    normalization_version: Identifier
    numerical_tolerance: float | None = Field(default=None, ge=0)


class ScoringDeclarations(Declaration):
    hotpotqa: ScorerDeclaration | None
    drop: ScorerDeclaration | None
    finqa: ScorerDeclaration | None

    @model_validator(mode="after")
    def match_implemented_scorers(self) -> Self:
        validate_scorer_declarations(self.model_dump(mode="json"))
        return self


class CorrectnessMargins(Declaration):
    hotpotqa: float = Field(ge=0, lt=1)
    drop: float = Field(ge=0, lt=1)
    finqa: float = Field(ge=0, lt=1)


class DatasetCounts(Declaration):
    hotpotqa: int = Field(ge=1, strict=True)
    drop: int = Field(ge=1, strict=True)
    finqa: int = Field(ge=1, strict=True)


class FinalPopulation(Declaration):
    snapshot_id: Identifier
    counts: DatasetCounts


class SamplingDeclarations(Declaration):
    mode: Literal["full", "source_grouped"]
    sample_id: Identifier
    assignment_version: Identifier
    seed: int = Field(ge=0, strict=True)


class StatisticsDeclarations(Declaration):
    confidence_level: float = Field(gt=0, lt=1)
    bootstrap_resamples: int = Field(ge=1, strict=True)
    resampling_unit: Literal["source_group"]
    paired_test: Identifier
    multiplicity: Literal["holm"]
    seed: int = Field(ge=0, strict=True)


class RepetitionDeclarations(Declaration):
    executions: Literal[3]
    subset_id: Identifier
    seed: int = Field(ge=0, strict=True)


class HumanAssessmentDeclarations(Declaration):
    assessors: Literal[2]
    sample_id: Identifier
    rubric_version: Identifier
    blind_methods: Literal[True]
    agreement_before_reconciliation: Literal[True]


class CacheOrderDeclarations(Declaration):
    cache_policy: Literal["miss", "separate_conditions"]
    warmup_policy: Literal["excluded_and_reported", "included"]
    method_order: Literal["seeded_random", "balanced"]
    concurrency: Literal[1]
    seed: int = Field(ge=0, strict=True)


class EvaluationConfig(Declaration):
    schema_version: Literal["workflow-evaluation-v1"]
    status: Literal["draft", "configured"]
    protocol_frozen: bool = Field(strict=True)
    scoring: ScoringDeclarations
    correctness_loss_margins: CorrectnessMargins | None
    final_population: FinalPopulation | None
    sampling: SamplingDeclarations | None
    statistics: StatisticsDeclarations | None
    repetitions: RepetitionDeclarations | None
    human_assessment: HumanAssessmentDeclarations | None
    cache_and_method_order: CacheOrderDeclarations | None

    def unresolved_fields(self) -> list[str]:
        fields = [
            "correctness_loss_margins",
            "final_population",
            "sampling",
            "statistics",
            "repetitions",
            "human_assessment",
            "cache_and_method_order",
        ]
        missing = [name for name in fields if getattr(self, name) is None]
        missing.extend(
            f"scoring.{dataset}"
            for dataset in ("hotpotqa", "drop", "finqa")
            if getattr(self.scoring, dataset) is None
        )
        return missing

    @model_validator(mode="after")
    def require_complete_frozen_declarations(self) -> Self:
        if self.protocol_frozen and self.unresolved_fields():
            raise ValueError("A frozen protocol cannot contain unresolved evaluation declarations.")
        return self


class RuntimeBindings(BaseModel):
    """Typed bindings; their presence does not verify live provider availability."""

    model_config = ConfigDict(extra="forbid")

    model: ModelBinding | None = None
    encoder: EncoderBinding | None = None
    inference: InferenceProfile | None = None
    prompts: PromptBindings | None = None
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

    @field_validator("methods", mode="before")
    @classmethod
    def reject_historical_method_in_active_study(cls, value: object) -> object:
        if isinstance(value, list) and "prediction-reuse-mlp" in value:
            raise ValueError(
                "Use 'prediction-reuse' in the active study instead of 'prediction-reuse-mlp'. "
                "Historical receipts must retain their original method identifiers."
            )
        return value

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


class StudyBundle(BaseModel):
    """One typed read of the four configuration documents."""

    root: Path
    study: StudyConfig
    datasets: DatasetConfig
    learning: LearningConfig
    evaluation: EvaluationConfig

    @model_validator(mode="after")
    def consistent_scientific_identities(self) -> Self:
        population = self.evaluation.final_population
        if population is not None and population.snapshot_id != self.datasets.snapshot_id:
            raise ValueError("Final population snapshot_id differs from the dataset configuration.")
        sampling = self.evaluation.sampling
        if sampling is not None and (
            sampling.assignment_version != self.datasets.partitions.assignment_version
        ):
            raise ValueError("Evaluation sampling uses a different source-group assignment.")
        if self.evaluation.protocol_frozen and not self.datasets.partitions.final_evaluation_frozen:
            raise ValueError("A frozen protocol requires frozen final source-group assignments.")
        return self


def _read_model[ConfigModel: BaseModel](path: Path, model: type[ConfigModel]) -> ConfigModel:
    try:
        return model.model_validate(read_yaml_mapping(path))
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration in {path}: {exc}") from exc


def load_study_bundle(path: Path | None = None) -> StudyBundle:
    """Validate owned declaration schemas; do not load data, fit or contact providers."""
    root = project_root(path.parent if path is not None and path.is_absolute() else None)
    location = root / "configs/study.yaml" if path is None else path
    if not location.is_absolute():
        location = resolve_project_path(root, location)
    elif not location.resolve().is_relative_to(root):
        raise ValueError("The study configuration must be inside the project.")
    study = _read_model(location, StudyConfig)
    linked = configuration_files(study, root)
    return StudyBundle(
        root=root,
        study=study,
        datasets=_read_model(linked["datasets"], DatasetConfig),
        learning=_read_model(linked["learning"], LearningConfig),
        evaluation=_read_model(linked["evaluation"], EvaluationConfig),
    )


def load_study(path: Path | None = None) -> StudyConfig:
    """Return the study after validating all linked declaration documents."""
    return load_study_bundle(path).study


def ollama_base_url(override: str | None = None) -> str:
    """Use an explicit endpoint, its environment setting, or the local default."""
    return override or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def load_predictor_declarations(study: StudyConfig, root: Path) -> PredictorDeclarations:
    """Read only declarations; historical result records are never migrated here."""
    path = resolve_project_path(root, study.learning_config)
    return _read_model(path, LearningConfig)
