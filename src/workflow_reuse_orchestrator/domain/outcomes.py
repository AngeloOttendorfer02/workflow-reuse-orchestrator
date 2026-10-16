"""Role outputs, request identities, and durable work-unit contracts."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from workflow_reuse_orchestrator.domain.budgets import RequestBudget, ResourceUsage
from workflow_reuse_orchestrator.domain.providers import Sha256
from workflow_reuse_orchestrator.domain.tasks import (
    EvidenceReference,
    Identifier,
    TaskInput,
    Text,
    resolve_evidence,
)
from workflow_reuse_orchestrator.domain.workflows import BoundWorkflowNode


class Receipt(BaseModel):
    """Gold scores belong in separate evaluator receipts, outside runtime payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    receipt_id: Identifier
    kind: Identifier
    status: Literal["started", "succeeded", "failed", "unknown"]
    payload: dict[str, JsonValue]


class CoordinatorOutput(BaseModel):
    """In-graph procedural guidance; whole-graph planning remains a later step."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    role: Literal["coordinator"] = "coordinator"
    plan: tuple[Text, ...] = Field(min_length=1, max_length=12)


class RetrievalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    role: Literal["retrieval"] = "retrieval"
    evidence: tuple[EvidenceReference, ...] = Field(max_length=64)


class ReasoningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    role: Literal["reasoning"] = "reasoning"
    answer: Text
    evidence: tuple[EvidenceReference, ...] = Field(max_length=64)


class CheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    verdict: Literal["pass", "fail", "uncertain"]
    rationale: Text


class CheckingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    role: Literal["checking"] = "checking"
    check: CheckVerdict
    evidence: tuple[EvidenceReference, ...] = Field(max_length=64)


RoleOutput = Annotated[
    CoordinatorOutput | RetrievalOutput | ReasoningOutput | CheckingOutput,
    Field(discriminator="role"),
]
ROLE_OUTPUT_ADAPTER: TypeAdapter[RoleOutput] = TypeAdapter(RoleOutput)


def validate_role_output_json(
    payload: str, *, node: BoundWorkflowNode, task: TaskInput
) -> RoleOutput:
    """Parse strictly, match the declared role, and resolve all current evidence.

    Empty retrieval/evidence is observable, not fabricated support. A valid output
    is structurally usable; this function makes no gold-correctness judgment.
    """
    output = ROLE_OUTPUT_ADAPTER.validate_json(payload)
    if output.role != node.role:
        raise ValueError("Output role must match the declared node role.")
    if not isinstance(output, CoordinatorOutput):
        if len(set(output.evidence)) != len(output.evidence):
            raise ValueError("Evidence references must be unique within an output.")
        for reference in output.evidence:
            resolve_evidence(task, reference)
    return output


FailureCode = Literal[
    "invalid_workflow",
    "invalid_role_output",
    "provider_error",
    "tool_error",
    "budget_exceeded",
    "cancelled",
    "unknown_effect",
]


class AttemptOutcome(BaseModel):
    """A request-scoped snapshot, not an incremental bill or a resumable job.

    cumulative_usage includes all earlier attempts, planning, repairs and tools.
    An unknown effect cannot be reported as success or safely retried as free work.
    C05 persists identities; later policies own complete attempt lifecycles.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["attempt-v1"] = "attempt-v1"
    request_id: Identifier
    attempt_id: Identifier
    kind: Literal["primary", "reuse", "fallback"]
    status: Literal["started", "succeeded", "failed", "unknown"]
    cumulative_usage: ResourceUsage
    answer: Text | None = None
    failure_code: FailureCode | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status == "succeeded":
            if self.answer is None or self.failure_code is not None:
                raise ValueError("Succeeded attempts require an answer and no failure code.")
        elif self.answer is not None:
            raise ValueError("Only succeeded attempts may deliver an answer.")
        if self.status == "started" and self.failure_code is not None:
            raise ValueError("Started attempts cannot have a terminal failure code.")
        if self.status in ("failed", "unknown") and self.failure_code is None:
            raise ValueError("Failed/unknown attempts require a failure code.")
        if (self.status == "unknown") != (self.failure_code == "unknown_effect"):
            raise ValueError("Unknown effects require the unknown terminal state.")
        return self


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    run_id: Identifier
    purpose: Literal["infrastructure_pilot", "development", "protected"]
    configuration_sha256: Sha256
    code_version: Identifier


class ScopeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    scope_id: Identifier
    run_id: Identifier
    family: Identifier
    fold_id: Identifier


class RequestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    request_id: Identifier
    scope_id: Identifier
    task_id: Identifier
    method_id: Identifier
    budget: RequestBudget


class AttemptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    attempt_id: Identifier
    request_id: Identifier
    kind: Literal["primary", "reuse", "fallback"]


class JobSpec(BaseModel):
    """One resumable work unit; external effects require intent before contact."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    job_id: Identifier
    scope_id: Identifier
    stage: Identifier
    phase: Literal["startup", "request", "analysis"]
    method_id: Identifier
    effect: Literal["local", "model", "tool"]
    request_id: Identifier | None = None
    attempt_id: Identifier | None = None
    retry_of: Identifier | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request_identity(self) -> Self:
        if (self.request_id is None) != (self.attempt_id is None):
            raise ValueError("Request and attempt identities must be supplied together.")
        if self.phase == "request" and self.request_id is None:
            raise ValueError("Request-phase jobs require request and attempt identities.")
        return self


class JobResult(BaseModel):
    """Incremental cost of this unit, unlike AttemptOutcome's cumulative usage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    status: Literal["succeeded", "failed"] = "succeeded"
    result: dict[str, JsonValue] = Field(default_factory=dict)
    usage: ResourceUsage = Field(default_factory=ResourceUsage)
    error: Text | None = None

    @model_validator(mode="after")
    def validate_error(self) -> Self:
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("Only failed results require an error.")
        return self


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["job-v1"] = "job-v1"
    spec: JobSpec
    status: Literal["pending", "running", "succeeded", "failed", "unknown"] = "pending"
    usage: ResourceUsage = Field(default_factory=ResourceUsage)
    wall_time_available: bool = True
    result: dict[str, JsonValue] | None = None
    error: Text | None = None
    started_at: str | None = None
    finished_at: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.status == "pending":
            if self.started_at is not None or self.finished_at is not None:
                raise ValueError("Pending jobs cannot have execution timestamps.")
        elif self.started_at is None:
            raise ValueError("Admitted jobs require a start timestamp.")
        terminal = self.status in ("succeeded", "failed", "unknown")
        if terminal != (self.finished_at is not None):
            raise ValueError("Only terminal jobs require a finish timestamp.")
        if (self.status in ("failed", "unknown")) != (self.error is not None):
            raise ValueError("Failed/unknown jobs require an error.")
        if (self.status in ("succeeded", "failed")) != (self.result is not None):
            raise ValueError("Known completed jobs require a result, even if empty.")
        return self
