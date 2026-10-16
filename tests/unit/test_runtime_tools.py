"""Calculator arithmetic remains bounded and independent of ambient precision."""

from decimal import localcontext

import pytest

from workflow_reuse_orchestrator.config import project_root
from workflow_reuse_orchestrator.domain.budgets import RequestBudget
from workflow_reuse_orchestrator.domain.tasks import TaskInput, resolve_evidence
from workflow_reuse_orchestrator.runtime.budgets import BudgetExceeded, BudgetTracker
from workflow_reuse_orchestrator.runtime.tools import (
    CalculatorError,
    RequestTools,
    SafeCalculator,
    SuppliedSourceSearch,
)


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("0.1 + 0.2", "0.3"),
        ("(120 - 100) / 100 * 100", "20"),
        ("-5 // 2", "-3"),
        ("-5 % 2", "1"),
        ("2 ** -3", "0.125"),
    ],
)
def test_arithmetic_uses_decimal_and_python_floor_rules(expression: str, expected: str) -> None:
    with localcontext() as context:
        context.prec = 2
        result = SafeCalculator().calculate(expression)
    assert result.value == expected
    assert result.wall_seconds >= 0


@pytest.mark.parametrize(
    "expression",
    [
        "True + 1",
        "sum([1, 2])",
        "(1).__class__",
        "__import__('os')",
        "1 / 0",
        "2 ** 21",
        "1e300",
        "1" * 257,
    ],
)
def test_rejects_unsupported_or_unbounded_expressions(expression: str) -> None:
    with pytest.raises(CalculatorError):
        SafeCalculator().calculate(expression)


@pytest.fixture
def task() -> TaskInput:
    return TaskInput.model_validate_json(
        (project_root() / "examples/document_question.json").read_text()
    )


def test_search_is_current_source_only_and_preserves_positions(task: TaskInput) -> None:
    result = SuppliedSourceSearch(task).search("Sales 2025")
    assert result.query == "Sales 2025"
    assert result.wall_seconds >= 0
    assert len(result.hits) == 3
    for hit in result.hits:
        assert hit.text == resolve_evidence(task, hit.reference)
    assert result.hits[-1].reference.kind == "cell"
    assert result.hits[-1].text == "2025"
    assert SuppliedSourceSearch(task).search("NoMatchingEvidence").hits == ()


def test_search_ranking_and_ties_follow_source_order() -> None:
    task = TaskInput.model_validate_json("""{
        "task_id":"t","dataset_id":"drop","question":"Which amount?",
        "passages":[{"source_id":"s","passage_id":"p","sentences":[
            "Sales only", "SALES and costs", "Costs and sales", "Salesman"]}],
        "tables":[{"source_id":"s","table_id":"table","rows":[["Sales costs"],["sales"]]}]
    }""")
    result = SuppliedSourceSearch(task).search("sales costs sales", limit=4)
    assert [hit.text for hit in result.hits] == [
        "SALES and costs",
        "Costs and sales",
        "Sales costs",
        "Sales only",
    ]
    assert result.hits[0].matched_terms == ("costs", "sales")
    assert all(hit.text != "Salesman" for hit in result.hits)


@pytest.mark.parametrize(
    "query,limit",
    [
        ("", 5),
        ("!", 5),
        ("a" * 257, 5),
        ("sales", 0),
        ("sales", 21),
        ("sales", True),
        (" ".join(f"word{x}" for x in range(33)), 5),
    ],
)
def test_search_rejects_invalid_query_or_limit(task: TaskInput, query: str, limit: int) -> None:
    with pytest.raises(ValueError):
        SuppliedSourceSearch(task).search(query, limit=limit)


def test_tools_share_allowance_and_count_invalid_attempts(
    task: TaskInput, request_budget: RequestBudget
) -> None:
    tracker = BudgetTracker(request_budget)
    tools = RequestTools(task=task, tracker=tracker)
    with pytest.raises(CalculatorError):
        tools.calculate("1 / 0")
    assert tools.search("sales").hits
    with pytest.raises(BudgetExceeded, match="Tool-call"):
        tools.calculate("1 + 1")
    assert tracker.usage.tool_calls == 2
    assert tracker.usage.model_calls == 0


def test_calculator_caps_syntax_work() -> None:
    with pytest.raises(CalculatorError, match="syntax-node"):
        SafeCalculator().calculate("+".join(["1"] * 64))
