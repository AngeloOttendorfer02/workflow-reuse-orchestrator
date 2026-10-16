"""Supplied-source lexical search, restricted arithmetic, and shared tool budgets."""

import ast
import re
from decimal import ROUND_FLOOR, Context, Decimal, DecimalException, Underflow, localcontext
from time import perf_counter

from workflow_reuse_orchestrator.domain.providers import CalculatorResult as CalculatorResult
from workflow_reuse_orchestrator.domain.providers import SourceSearchHit, SourceSearchResult
from workflow_reuse_orchestrator.domain.tasks import (
    CellEvidence,
    SentenceEvidence,
    TaskInput,
)
from workflow_reuse_orchestrator.runtime.budgets import BudgetTracker


class CalculatorError(ValueError):
    """An arithmetic expression exceeds the supported syntax or numeric bounds."""


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
            if sum(1 for _ in ast.walk(parsed)) > 128:
                raise CalculatorError("calculator expression exceeds the syntax-node limit")
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


class SuppliedSourceSearch:
    """Case-folded whole-word matches over this task's sentences and table cells.

    Rank by distinct matched query terms, then original passage/table order and
    zero-based position. This deterministic local tool is separate from workflow
    library retrieval. It never opens URLs/files or loads evaluator references.
    """

    def __init__(self, task: TaskInput) -> None:
        self._task = task

    def search(self, query: str, *, limit: int = 5) -> SourceSearchResult:
        started = perf_counter()
        if type(query) is not str or not query.strip() or len(query) > 256:
            raise ValueError("Search query must contain 1 to 256 characters.")
        terms = tuple(sorted(set(re.findall(r"\w+", query.casefold()))))
        if not terms or len(terms) > 32:
            raise ValueError("Search query must contain 1 to 32 distinct word terms.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Search limit must be an integer within [1, 20].")
        hits: list[SourceSearchHit] = []
        task = self._task
        for passage in task.passages:
            for index, text in enumerate(passage.sentences):
                matched = self._matches(terms, text)
                if matched:
                    hits.append(
                        SourceSearchHit(
                            reference=SentenceEvidence(
                                task_id=task.task_id,
                                source_id=passage.source_id,
                                passage_id=passage.passage_id,
                                sentence_index=index,
                            ),
                            text=text,
                            matched_terms=matched,
                        )
                    )
        for table in task.tables:
            for row_index, row in enumerate(table.rows):
                for column_index, text in enumerate(row):
                    matched = self._matches(terms, text)
                    if matched:
                        hits.append(
                            SourceSearchHit(
                                reference=CellEvidence(
                                    task_id=task.task_id,
                                    source_id=table.source_id,
                                    table_id=table.table_id,
                                    row_index=row_index,
                                    column_index=column_index,
                                ),
                                text=text,
                                matched_terms=matched,
                            )
                        )
        hits.sort(key=lambda hit: -len(hit.matched_terms))  # Stable ties retain source order.
        return SourceSearchResult(
            query=query.strip(), hits=tuple(hits[:limit]), wall_seconds=perf_counter() - started
        )

    @staticmethod
    def _matches(terms: tuple[str, ...], text: str) -> tuple[str, ...]:
        words = set(re.findall(r"\w+", text.casefold()))
        return tuple(term for term in terms if term in words)


class RequestTools:
    """Host-owned tool entry points, sharing the caller's whole-request tracker.

    Low-level tools remain usable for unit tests. Future role runners use these
    counted entry points. Failures consume tool allowance; calls are synchronous,
    so a deadline overrun is detected after return rather than forcibly interrupted.
    """

    def __init__(self, *, task: TaskInput, tracker: BudgetTracker) -> None:
        self._search = SuppliedSourceSearch(task)
        self._calculator = SafeCalculator()
        self.tracker = tracker

    def search(self, query: str, *, limit: int = 5) -> SourceSearchResult:
        return self.tracker.run_tool(lambda: self._search.search(query, limit=limit))

    def calculate(self, expression: str) -> CalculatorResult:
        return self.tracker.run_tool(lambda: self._calculator.calculate(expression))
