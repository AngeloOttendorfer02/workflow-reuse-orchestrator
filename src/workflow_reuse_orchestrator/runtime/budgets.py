"""Sequential cumulative accounting shared by all roles and recovery attempts."""

from collections.abc import Callable
from time import perf_counter
from typing import TypeVar

from pydantic import JsonValue

from workflow_reuse_orchestrator.domain.budgets import RequestBudget, ResourceUsage
from workflow_reuse_orchestrator.domain.providers import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    InferenceProfile,
    ModelBinding,
)

T = TypeVar("T")


class BudgetExceeded(RuntimeError):
    """An effect cannot be permitted or completed within the declared allowance."""


class BudgetTracker:
    """Count attempts before effects, then reconcile available measured tokens.

    A failed/incomplete call has unknown token cost. Subsequent generation is
    blocked when token usage is unknown. The tracker intentionally permits only
    one pending generation because this prototype executes sequentially.
    """

    def __init__(self, budget: RequestBudget, *, clock: Callable[[], float] = perf_counter) -> None:
        self.budget = budget
        self._clock = clock
        self._started = clock()
        self._model_calls = 0
        self._tool_calls = 0
        self._input_tokens: int | None = 0
        self._output_tokens: int | None = 0
        self._repairs = 0
        self._fallbacks = 0
        self._pending: tuple[int, int] | None = None
        self._blocked_reason: str | None = None

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.budget.max_wall_seconds - (self._clock() - self._started))

    @property
    def usage(self) -> ResourceUsage:
        return ResourceUsage(
            model_calls=self._model_calls,
            input_tokens=self._input_tokens if self._pending is None else None,
            output_tokens=self._output_tokens if self._pending is None else None,
            tool_calls=self._tool_calls,
            wall_seconds=max(0.0, self._clock() - self._started),
            plan_repairs=self._repairs,
            fallback_plans=self._fallbacks,
        )

    def reserve_generation(self, *, input_tokens_upper_bound: int, output_tokens: int) -> None:
        self._check_time()
        if self._pending is not None:
            raise ValueError("A generation is already pending.")
        for value in (input_tokens_upper_bound, output_tokens):
            if type(value) is not int or value < 1:
                raise ValueError("Generation reservations must be positive integer token bounds.")
        if self._input_tokens is None or self._output_tokens is None:
            raise BudgetExceeded("Token usage is unavailable; further generation is blocked.")
        if self._model_calls >= self.budget.max_model_calls:
            raise BudgetExceeded("Model-call allowance exhausted.")
        if self._input_tokens + input_tokens_upper_bound > self.budget.max_input_tokens:
            raise BudgetExceeded("Insufficient input-token allowance for a safe reservation.")
        if self._output_tokens + output_tokens > self.budget.max_output_tokens:
            raise BudgetExceeded("Insufficient output-token allowance for a safe reservation.")
        self._model_calls += 1
        self._pending = (input_tokens_upper_bound, output_tokens)

    def finish_generation(self, response: GenerationResponse) -> None:
        if self._pending is None:
            raise ValueError("No generation is pending.")
        input_limit, output_limit = self._pending
        self._pending = None
        self._input_tokens = self._add(self._input_tokens, response.input_tokens)
        self._output_tokens = self._add(self._output_tokens, response.output_tokens)
        if (response.input_tokens is not None and response.input_tokens > input_limit) or (
            response.output_tokens is not None and response.output_tokens > output_limit
        ):
            self._blocked_reason = "Provider usage exceeded its reserved token limits."
            raise BudgetExceeded(self._blocked_reason)
        self._check_time()

    def abandon_generation(self) -> None:
        if self._pending is None:
            raise ValueError("No generation is pending.")
        self._pending = None
        self._input_tokens = None
        self._output_tokens = None

    def run_tool(self, operation: Callable[[], T]) -> T:
        self._check_time()
        if self._pending is not None:
            raise ValueError("Cannot execute a tool during a pending generation.")
        if self._tool_calls >= self.budget.max_tool_calls:
            raise BudgetExceeded("Tool-call allowance exhausted.")
        self._tool_calls += 1
        result = operation()
        self._check_time()
        return result

    def consume_plan_repair(self) -> None:
        self._check_time()
        if self._repairs >= self.budget.max_plan_repairs:
            raise BudgetExceeded("Plan-repair allowance exhausted.")
        self._repairs += 1

    def consume_fallback_plan(self) -> None:
        self._check_time()
        if self._fallbacks >= self.budget.max_fallback_plans:
            raise BudgetExceeded("Fallback-plan allowance exhausted.")
        self._fallbacks += 1

    def _check_time(self) -> None:
        if self._blocked_reason is not None:
            raise BudgetExceeded(self._blocked_reason)
        if self.remaining_seconds <= 0:
            raise BudgetExceeded("Whole-request wall-time allowance exhausted.")

    @staticmethod
    def _add(total: int | None, value: int | None) -> int | None:
        return None if total is None or value is None else total + value


class BudgetedGenerator:
    """Bind one model/profile and reuse the same tracker for every generation."""

    def __init__(
        self,
        *,
        provider: GenerationProvider,
        model: ModelBinding,
        inference: InferenceProfile,
        tracker: BudgetTracker,
    ) -> None:
        if inference.num_ctx > model.native_context_tokens:
            raise ValueError("Inference context exceeds the model's native context.")
        self._provider = provider
        self._model = model
        self._inference = inference
        self.tracker = tracker

    def generate(
        self, prompt: str, *, output_schema: dict[str, JsonValue] | None = None
    ) -> GenerationResponse:
        if self.tracker.remaining_seconds <= 0:
            raise BudgetExceeded("Whole-request wall-time allowance exhausted.")
        request = GenerationRequest(
            prompt=prompt,
            max_output_tokens=self._inference.num_predict,
            timeout_seconds=self.tracker.remaining_seconds,
            output_schema=output_schema,
        )
        self.tracker.reserve_generation(
            input_tokens_upper_bound=self._inference.num_ctx,
            output_tokens=self._inference.num_predict,
        )
        try:
            response = self._provider.generate(
                model=self._model, inference=self._inference, request=request
            )
        except Exception:
            self.tracker.abandon_generation()
            raise
        self.tracker.finish_generation(response)
        return response
