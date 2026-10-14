"""Calculator arithmetic remains bounded and independent of ambient precision."""

from decimal import localcontext

import pytest

from workflow_reuse_orchestrator.runtime.tools import CalculatorError, SafeCalculator


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
