"""Fixed-model identity, inference controls, generation contracts, and errors."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from workflow_reuse_orchestrator.domain.tasks import Identifier, Text

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]


class ProviderError(RuntimeError):
    """A provider operation could not complete or returned an invalid response."""


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or its connection has been closed."""


class ProviderResponseError(ProviderError):
    """The provider returned an unsuccessful or malformed response."""


class ModelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_name: Identifier
    model_digest: Sha256
    ollama_version: Identifier
    native_context_tokens: int = Field(ge=1)
    tokenizer_sha256: Sha256
    template_sha256: Sha256
    model_metadata_sha256: Sha256


class InferenceProfile(BaseModel):
    """Explicit generation controls shared by the fixed-model runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    num_ctx: int = Field(ge=1)
    num_predict: int = Field(ge=1)
    seed: int = Field(ge=0)
    temperature: float = Field(default=0.0, ge=0, le=2)
    top_p: float = Field(default=1.0, gt=0, le=1)
    top_k: int = Field(default=40, ge=1)
    min_p: float = Field(default=0.0, ge=0, le=1)
    think: Literal[False] = False
    keep_alive: int = Field(default=300, ge=0)

    @model_validator(mode="after")
    def leave_room_for_input(self) -> Self:
        if self.num_predict >= self.num_ctx:
            raise ValueError("The output limit must leave context space for the input.")
        return self


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    prompt: Text
    max_output_tokens: int = Field(ge=1)
    timeout_seconds: float = Field(gt=0)
    output_schema: dict[str, JsonValue] | None = None


class GenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    output_text: str
    wall_seconds: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = None
    provider_total_seconds: float | None = Field(default=None, ge=0)
    model_load_seconds: float | None = Field(default=None, ge=0)
    prompt_eval_seconds: float | None = Field(default=None, ge=0)
    generation_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_output(self) -> Self:
        if not self.output_text.strip() and self.finish_reason != "length":
            raise ValueError("A completed generation must contain output text.")
        return self


class GenerationProvider(Protocol):
    def generate(
        self,
        *,
        model: ModelBinding,
        inference: InferenceProfile,
        request: GenerationRequest,
    ) -> GenerationResponse: ...
