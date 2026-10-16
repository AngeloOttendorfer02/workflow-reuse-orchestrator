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


@pytest.mark.parametrize("effect", ["tool", "model", "repair", "fallback"])
def test_pending_generation_blocks_other_effects(
    request_budget: RequestBudget, effect: str
) -> None:
    tracker = BudgetTracker(request_budget)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    operations = {
        "tool": lambda: tracker.run_tool(lambda: pytest.fail("Tool must not run")),
        "model": lambda: tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8),
        "repair": tracker.consume_plan_repair,
        "fallback": tracker.consume_fallback_plan,
    }
    with pytest.raises(ValueError, match="pending"):
        operations[effect]()
    assert tracker.usage.model_calls == 1
    assert (
        tracker.usage.tool_calls == tracker.usage.plan_repairs == tracker.usage.fallback_plans == 0
    )
    tracker.abandon_generation()


def test_tool_cannot_nest_or_start_model_recovery(request_budget: RequestBudget) -> None:
    tracker = BudgetTracker(request_budget)

    def reentrant() -> None:
        for operation in (
            lambda: tracker.run_tool(lambda: None),
            lambda: tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8),
            tracker.consume_plan_repair,
            tracker.consume_fallback_plan,
        ):
            with pytest.raises(ValueError, match="pending"):
                operation()

    tracker.run_tool(reentrant)
    assert tracker.usage.tool_calls == 1
    assert (
        tracker.usage.model_calls == tracker.usage.plan_repairs == tracker.usage.fallback_plans == 0
    )


def test_cancellation_has_unknown_tokens_and_clears_pending_state(
    request_budget: RequestBudget, model_binding: ModelBinding, inference_profile: InferenceProfile
) -> None:
    class CancelledProvider:
        def generate(
            self, *, model: ModelBinding, inference: InferenceProfile, request: GenerationRequest
        ) -> GenerationResponse:
            raise KeyboardInterrupt("cancelled")

    tracker = BudgetTracker(request_budget)
    generator = BudgetedGenerator(
        provider=CancelledProvider(),
        model=model_binding,
        inference=inference_profile,
        tracker=tracker,
    )
    with pytest.raises(KeyboardInterrupt, match="cancelled"):
        generator.generate("Question")
    assert tracker.usage.model_calls == 1
    assert tracker.usage.input_tokens is tracker.usage.output_tokens is None
    # No model token reservation is possible; an otherwise permitted local tool still is.
    assert tracker.run_tool(lambda: "available") == "available"
    with pytest.raises(BudgetExceeded, match="unavailable"):
        generator.generate("retry")


def test_generation_timeout_uses_remaining_request_time_and_retains_late_usage(
    request_budget: RequestBudget, model_binding: ModelBinding, inference_profile: InferenceProfile
) -> None:
    clock = FakeClock()
    tracker = BudgetTracker(request_budget, clock=clock)

    class LateProvider:
        def generate(
            self, *, model: ModelBinding, inference: InferenceProfile, request: GenerationRequest
        ) -> GenerationResponse:
            assert request.timeout_seconds == 6.0
            clock.now = 11.0
            return response()

    clock.now = 4.0
    generator = BudgetedGenerator(
        provider=LateProvider(), model=model_binding, inference=inference_profile, tracker=tracker
    )
    with pytest.raises(BudgetExceeded, match="wall-time"):
        generator.generate("Question")
    assert tracker.usage.input_tokens == 10
    assert tracker.usage.output_tokens == 2
    assert tracker.usage.wall_seconds == 11.0
    with pytest.raises(BudgetExceeded, match="wall-time"):
        tracker.consume_fallback_plan()


def test_failed_late_tool_retains_failure_and_exhausts_deadline(
    request_budget: RequestBudget,
) -> None:
    clock = FakeClock()
    tracker = BudgetTracker(request_budget, clock=clock)

    def late_failure() -> None:
        clock.now = 11.0
        raise ValueError("original tool failure")

    with pytest.raises(ValueError, match="original tool failure"):
        tracker.run_tool(late_failure)
    assert tracker.usage.tool_calls == 1
    with pytest.raises(BudgetExceeded, match="wall-time"):
        tracker.run_tool(lambda: pytest.fail("Expired tool must not run"))


def test_primary_repair_and_fallback_snapshots_share_usage_and_deadline(
    request_budget: RequestBudget,
) -> None:
    from workflow_reuse_orchestrator.domain.outcomes import AttemptOutcome

    clock = FakeClock()
    tracker = BudgetTracker(request_budget, clock=clock)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    tracker.finish_generation(response())
    clock.now = 3.0
    failed = AttemptOutcome(
        request_id="r",
        attempt_id="reuse",
        kind="reuse",
        status="failed",
        failure_code="invalid_role_output",
        cumulative_usage=tracker.usage,
    )
    tracker.consume_plan_repair()
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    tracker.finish_generation(response())
    tracker.consume_fallback_plan()
    tracker.run_tool(lambda: None)
    tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)
    tracker.finish_generation(response())
    clock.now = 7.0
    success = AttemptOutcome(
        request_id="r",
        attempt_id="fallback",
        kind="fallback",
        status="succeeded",
        answer="Unevaluated answer",
        cumulative_usage=tracker.usage,
    )
    assert failed.cumulative_usage.model_calls == 1  # Earlier immutable snapshot.
    assert success.cumulative_usage.model_calls == 3  # Cumulative, not an incremental bill.
    assert success.cumulative_usage.input_tokens == 30
    assert success.cumulative_usage.plan_repairs == success.cumulative_usage.fallback_plans == 1
    assert tracker.remaining_seconds == 3.0
    with pytest.raises(BudgetExceeded, match="Model-call"):
        tracker.reserve_generation(input_tokens_upper_bound=64, output_tokens=8)


def test_zero_tool_repair_and_fallback_limits_reject_before_effect(
    request_budget: RequestBudget,
) -> None:
    budget = RequestBudget.model_validate(
        request_budget.model_dump()
        | {"max_tool_calls": 0, "max_plan_repairs": 0, "max_fallback_plans": 0}
    )
    tracker = BudgetTracker(budget)
    for operation in (
        lambda: tracker.run_tool(lambda: pytest.fail("Not permitted")),
        tracker.consume_plan_repair,
        tracker.consume_fallback_plan,
    ):
        with pytest.raises(BudgetExceeded):
            operation()
    assert (
        tracker.usage.tool_calls == tracker.usage.plan_repairs == tracker.usage.fallback_plans == 0
    )
