"""Immutable receipt identities for started and completed effects."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from workflow_reuse_orchestrator.domain.budgets import ResourceUsage
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
    Persistence and recovery transitions are implemented in C05 and later.
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
