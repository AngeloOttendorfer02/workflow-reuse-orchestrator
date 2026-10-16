"""Immutable receipt identities for started and completed effects."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from workflow_reuse_orchestrator.domain.tasks import Identifier


class Receipt(BaseModel):
    """Gold scores belong in separate evaluator receipts, outside runtime payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    receipt_id: Identifier
    kind: Identifier
    status: Literal["started", "succeeded", "failed", "unknown"]
    payload: dict[str, JsonValue]
