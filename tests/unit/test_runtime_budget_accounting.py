"""Planning, execution, repair, and fallback share one ledger."""

from dataclasses import dataclass

import pytest

from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.providers import (
    GenerationRequest,
    GenerationResponse,
    InferenceProfile,
    ModelBinding,
    ProviderUnavailableError,
)
from workflow_reuse_orchestrator.runtime.budgets import (
    BudgetedGenerator,
    BudgetExceeded,
    BudgetTracker,
)


@dataclass
class FakeClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def response(input_tokens: int | None = 10, output_tokens: int | None = 2) -> GenerationResponse:
    return GenerationResponse(
        output_text="OK", wall_seconds=0.1, input_tokens=input_tokens, output_tokens=output_tokens
    )


def test_planning_and_fallback_cannot_reset_call_allowance(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget)
    for _ in range(3):
        tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
        tracker.finish_generation(response())
    tracker.consume_plan_repair()
    tracker.consume_fallback_plan()
    with pytest.raises(BudgetExceeded, match="Model-call"):
        tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    assert tracker.usage.model_calls == 3
    assert tracker.usage.input_tokens == 30
    assert tracker.usage.output_tokens == 6
    assert tracker.usage.plan_repairs == tracker.usage.fallback_plans == 1


def test_failed_generation_is_counted_and_its_tokens_are_unknown(
    request_budget: RequestBudget,
) -> None:
    tracker = BudgetTracker(request_budget)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    tracker.abandon_generation()
    assert tracker.usage.model_calls == 1
    assert tracker.usage.input_tokens is None
    with pytest.raises(BudgetExceeded, match="unavailable"):
        tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)


def test_missing_telemetry_is_not_zero(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    tracker.finish_generation(response(input_tokens=None))
    assert tracker.usage.input_tokens is None
    assert tracker.usage.output_tokens == 2
    assert tracker.usage.token_counts_available is False


def test_reserves_before_effect_and_reconciles_actual_tokens(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget.model_copy(update={"max_output_tokens": 8}))
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    assert tracker.usage.model_calls == 1
    assert tracker.usage.output_tokens is None
    tracker.finish_generation(response(output_tokens=2))
    with pytest.raises(BudgetExceeded, match="output-token"):
        tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    assert tracker.usage.model_calls == 1


def test_overrun_is_recorded_and_blocks_subsequent_effects(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    with pytest.raises(BudgetExceeded, match="reserved"):
        tracker.finish_generation(response(output_tokens=9))
    assert tracker.usage.output_tokens == 9
    with pytest.raises(BudgetExceeded, match="reserved"):
        tracker.run_tool(lambda: "must not run")


def test_failed_tool_still_consumes_its_allowance(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget.model_copy(update={"max_tool_calls": 1}))

    def failure() -> None:
        raise ValueError("tool failed")

    with pytest.raises(ValueError, match="tool failed"):
        tracker.run_tool(failure)
    with pytest.raises(BudgetExceeded, match="Tool-call"):
        tracker.run_tool(lambda: None)
    assert tracker.usage.tool_calls == 1


def test_only_one_fallback_and_one_repair_are_permitted(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget)
    tracker.consume_fallback_plan()
    tracker.consume_plan_repair()
    with pytest.raises(BudgetExceeded, match="Fallback"):
        tracker.consume_fallback_plan()
    with pytest.raises(BudgetExceeded, match="repair"):
        tracker.consume_plan_repair()


def test_expired_deadline_blocks_generation_before_provider(
    request_budget: RequestBudget, model_binding: ModelBinding, inference_profile: InferenceProfile
) -> None:
    clock = FakeClock()
    tracker = BudgetTracker(request_budget, clock=clock)

    class NeverCalled:
        def generate(
            self, *, model: ModelBinding, inference: InferenceProfile, request: GenerationRequest
        ) -> GenerationResponse:
            raise AssertionError("No provider call should occur.")

    generator = BudgetedGenerator(
        provider=NeverCalled(), model=model_binding, inference=inference_profile, tracker=tracker
    )
    clock.now = 11.0
    with pytest.raises(BudgetExceeded, match="wall-time"):
        generator.generate("Question")
    assert tracker.usage.model_calls == 0


def test_transport_failure_is_accounted_by_bound_generator(
    request_budget: RequestBudget, model_binding: ModelBinding, inference_profile: InferenceProfile
) -> None:
    tracker = BudgetTracker(request_budget)

    class FailingProvider:
        def generate(
            self, *, model: ModelBinding, inference: InferenceProfile, request: GenerationRequest
        ) -> GenerationResponse:
            raise ProviderUnavailableError("offline")

    generator = BudgetedGenerator(
        provider=FailingProvider(),
        model=model_binding,
        inference=inference_profile,
        tracker=tracker,
    )
    with pytest.raises(ProviderUnavailableError, match="offline"):
        generator.generate("Question")
    assert tracker.usage.model_calls == 1
    assert tracker.usage.input_tokens is None
