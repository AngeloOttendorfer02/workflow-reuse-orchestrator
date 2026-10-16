"""Bounded arithmetic evaluation without Python eval or ambient Decimal state."""

import ast
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Context, Decimal, DecimalException, Underflow, localcontext
from time import perf_counter


class CalculatorError(ValueError):
    """An arithmetic expression exceeds the supported syntax or numeric bounds."""


@dataclass(frozen=True, slots=True)
class CalculatorResult:
    """A calculator result with observed end-to-end operation latency."""

    expression: str
    value: str
    wall_seconds: float


class SafeCalculator:
    """Evaluate arithmetic with 28-digit precision and bounded finite magnitudes.

    The precision matches Decimal's normal default but is isolated from the caller.
    Source decimal digits are preserved instead of passing through a binary float.
    Floor division and remainder follow Python's convention for negative operands.
    """

    def calculate(self, expression: str) -> CalculatorResult:
        normalized = expression.strip()
        if not normalized or len(normalized) > 256:
            raise CalculatorError("calculator expression must contain 1 to 256 characters")
        started = perf_counter()
        try:
            parsed = ast.parse(normalized, mode="eval")
            with localcontext(Context(prec=28, Emax=256, Emin=-256)) as context:
                # Underflow must not silently turn a nonzero result into zero.
                context.traps[Underflow] = True
                value = self._evaluate_node(parsed.body, normalized)
                if not value.is_finite() or (value and abs(value.adjusted()) > 256):
                    raise CalculatorError("calculator result exceeds the finite magnitude limit")
                formatted = format(value.normalize(), "f")
        except (SyntaxError, DecimalException, ZeroDivisionError, OverflowError) as exc:
            raise CalculatorError("invalid or out-of-range calculator expression") from exc
        return CalculatorResult(normalized, formatted, perf_counter() - started)

    def _evaluate_node(self, node: ast.expr, source: str) -> Decimal:
        """Only whitelisted numeric syntax is traversed; names/calls are rejected."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise CalculatorError("calculator accepts only numeric literals")
            if isinstance(node.value, int):
                value = Decimal(node.value)
            else:
                literal = ast.get_source_segment(source, node)
                assert literal is not None
                value = Decimal(literal.replace("_", ""))
            if not value.is_finite() or (value and abs(value.adjusted()) > 256):
                raise CalculatorError("numeric literal exceeds the finite magnitude limit")
            return value
        if isinstance(node, ast.UnaryOp):
            value = self._evaluate_node(node.operand, source)
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.USub):
                return -value
        if isinstance(node, ast.BinOp):
            left = self._evaluate_node(node.left, source)
            right = self._evaluate_node(node.right, source)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv | ast.Mod):
                quotient = (left / right).to_integral_value(rounding=ROUND_FLOOR)
                return quotient if isinstance(node.op, ast.FloorDiv) else left - right * quotient
            if isinstance(node.op, ast.Pow):
                if right != right.to_integral_value() or abs(right) > 20:
                    raise CalculatorError("calculator requires integer exponents within [-20, 20]")
                return left ** int(right)
        raise CalculatorError("expression contains unsupported syntax")
