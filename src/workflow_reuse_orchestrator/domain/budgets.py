"""Whole-request limits and measured usage; missing tokens remain unavailable."""

from pydantic import BaseModel, ConfigDict, Field


class RequestBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    max_model_calls: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_tool_calls: int = Field(ge=0)
    max_wall_seconds: float = Field(gt=0)
    max_plan_repairs: int = Field(ge=0)
    max_fallback_plans: int = Field(ge=0, le=1)


class ResourceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    model_calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=0, ge=0)
    output_tokens: int | None = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0)
    plan_repairs: int = Field(default=0, ge=0)
    fallback_plans: int = Field(default=0, ge=0)

    @property
    def token_counts_available(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None
