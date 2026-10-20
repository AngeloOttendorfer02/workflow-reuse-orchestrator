"""Versioned evaluator-only answer metrics and conservative candidate labels."""

from __future__ import annotations

import hashlib
import json
import re
import string
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workflow_reuse_orchestrator.data.drop import DropEvaluationReference
from workflow_reuse_orchestrator.data.finqa import FinqaEvaluationReference
from workflow_reuse_orchestrator.domain.tasks import DatasetId, EvaluationReference, Identifier
from workflow_reuse_orchestrator.storage import canonical_sha256

PARSER_VERSION = "final-answer-v1"
LABEL_VERSION = "known-terminal-correctness-v1"
FINQA_ABSOLUTE_TOLERANCE = Decimal("0.00001")
MAX_ANSWER_CHARACTERS = 65536
MAX_ANSWER_SPANS = 128
MAX_NUMERIC_EXPONENT = 1000
_PUNCTUATION = set(string.punctuation)
_ARTICLES = re.compile(r"\b(a|an|the)\b")
_NUMBER = re.compile(
    r"[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?"
)
_SCORERS: dict[str, dict[str, Any]] = {
    "hotpotqa": {
        "name": "hotpotqa_answer",
        "version": "c10-v1",
        "normalization_version": "hotpotqa-official-v1",
        "numerical_tolerance": None,
        "upstream_revision": "3635853403a8735609ee997664e1528f4480762a",
        "upstream_sha256": "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0",
        "upstream_url": "https://github.com/hotpotqa/hotpot/blob/"
        "3635853403a8735609ee997664e1528f4480762a/hotpot_evaluate_v1.py",
    },
    "drop": {
        "name": "drop_answer",
        "version": "c10-v1",
        "normalization_version": "drop-official-v1",
        "numerical_tolerance": None,
        "upstream_revision": "b1f372248c17ad12684d344955fbcd98e957e77e",
        "upstream_sha256": "589abfbb8a85760cdb3d30381068acb4545c82076311c2da5a112e283193e0a2",
        "upstream_url": "https://github.com/allenai/allennlp-models/blob/"
        "b1f372248c17ad12684d344955fbcd98e957e77e/allennlp_models/rc/tools/drop.py",
    },
    "finqa": {
        "name": "finqa_execution_answer",
        "version": "c10-v1",
        "normalization_version": "finqa-decimal-percent-v1",
        "numerical_tolerance": 0.00001,
        "upstream_revision": "9e2006a6ed65279a01d62e92e61c02638c7c358d",
        "upstream_sha256": "845cd131cab843eceff256cf6d392978cc470a7da4a80107beb56027fdca5c13",
        "upstream_url": "https://github.com/czyssrs/FinQA/blob/"
        "9e2006a6ed65279a01d62e92e61c02638c7c358d/code/evaluate/evaluate.py",
    },
}


def scorer_declaration(dataset: DatasetId) -> dict[str, Any]:
    """The four configuration fields must exactly match the implemented policy."""
    return {
        k: _SCORERS[dataset][k]
        for k in ("name", "version", "normalization_version", "numerical_tolerance")
    }


def validate_scorer_declarations(declarations: dict[str, Any]) -> None:
    for dataset in ("hotpotqa", "drop", "finqa"):
        value = declarations[dataset]
        if value is not None and value != scorer_declaration(dataset):
            raise ValueError(f"Configured {dataset} scorer differs from its implemented identity.")


def scorer_identity(dataset: DatasetId) -> dict[str, Any]:
    identity = dict(_SCORERS[dataset])
    identity.update(
        {
            "parser_version": PARSER_VERSION,
            "label_version": LABEL_VERSION,
            "max_answer_characters": MAX_ANSWER_CHARACTERS,
            "max_answer_spans": MAX_ANSWER_SPANS,
            "implementation_sha256": hashlib.sha256(
                Path(__file__).read_text("utf-8").encode()
            ).hexdigest(),
        }
    )
    if dataset == "finqa":
        identity.update(
            {
                "relative_tolerance": 0,
                "max_numeric_exponent": MAX_NUMERIC_EXPONENT,
                "percentage_policy": "divide_marked_percent_by_100",
                "unit_policy": "native_target_units_no_magnitude_conversion",
            }
        )
    identity["fingerprint"] = canonical_sha256(identity)
    return identity


class AnswerSubmission(BaseModel):
    """A final answer plus known execution state, never reference-bearing input."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: Identifier
    dataset_id: DatasetId
    status: Literal["started", "succeeded", "failed", "unknown"]
    answer: str | tuple[str, ...] | None = None
    finish_reason: str | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def preserve_unknown_effects(self) -> Self:
        if self.failure_code == "unknown_effect" and self.status != "unknown":
            raise ValueError("Unknown effects must retain the unknown execution state.")
        return self


class AnswerScore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    schema_version: Literal["answer-score-v1"] = "answer-score-v1"
    task_id: Identifier
    dataset_id: DatasetId
    status: Literal[
        "scored", "execution_failed", "invalid_output", "truncated", "unknown", "incomplete"
    ]
    reason: str
    binary_label: Literal[0, 1] | None
    answer_em: float | None = Field(default=None, ge=0, le=1)
    answer_f1: float | None = Field(default=None, ge=0, le=1)
    numeric_correct: bool | None = None
    normalized_prediction: tuple[str, ...] | None = None
    numerical_difference: str | None = None
    scorer: dict[str, Any]

    @field_validator("binary_label", mode="before")
    @classmethod
    def require_integer_label(cls, value: Any) -> Any:
        if value is not None and type(value) is not int:
            raise ValueError("A binary label must be an integer 0/1 or unavailable null.")
        return value

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        unavailable = self.status in ("unknown", "incomplete")
        if unavailable != (self.binary_label is None):
            raise ValueError("Only known terminal results may have binary labels.")
        if unavailable and any(
            v is not None for v in (self.answer_em, self.answer_f1, self.numeric_correct)
        ):
            raise ValueError("Unknown/incomplete executions cannot have measured correctness.")
        if self.status != "scored" and self.binary_label == 1:
            raise ValueError("Only a scored answer can be correct.")
        if self.status == "scored":
            if self.dataset_id == "finqa":
                if (
                    self.numeric_correct is None
                    or self.answer_em is not None
                    or self.answer_f1 is not None
                ):
                    raise ValueError("FinQA requires numeric/yes-no correctness, not answer EM/F1.")
                expected_label = 1 if self.numeric_correct else 0
            else:
                if (
                    self.answer_em is None
                    or self.answer_f1 is None
                    or self.numeric_correct is not None
                ):
                    raise ValueError("HotpotQA/DROP require answer EM and F1.")
                expected_label = 1 if self.answer_em == 1.0 else 0
            if self.binary_label != expected_label:
                raise ValueError("Binary success must agree with the dataset correctness metric.")
        return self


def normalize_hotpot_answer(text: str) -> str:
    without_punctuation = "".join(c for c in text.lower() if c not in _PUNCTUATION)
    return " ".join(_ARTICLES.sub(" ", without_punctuation).split())


def hotpot_answer_metrics(prediction: str, gold: str) -> tuple[float, float]:
    predicted, expected = normalize_hotpot_answer(prediction), normalize_hotpot_answer(gold)
    em = float(predicted == expected)
    if predicted != expected and ({predicted, expected} & {"yes", "no", "noanswer"}):
        return em, 0.0
    p, g = predicted.split(), expected.split()
    common = sum((Counter(p) & Counter(g)).values())
    if not common:
        return em, 0.0
    precision, recall = common / len(p), common / len(g)
    return em, 2 * precision * recall / (precision + recall)


def _drop_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def normalize_drop_answer(text: str) -> str:
    parts = []
    for token in re.split(" |-", text.lower()):
        cleaned = (
            token if _drop_number(token) else "".join(c for c in token if c not in _PUNCTUATION)
        )
        cleaned = str(float(cleaned)) if _drop_number(cleaned) else cleaned
        normalized = " ".join(_ARTICLES.sub(" ", cleaned).split())
        if normalized:
            parts.append(normalized)
    return " ".join(parts)


def _alignment_total(scores: list[list[float]]) -> float:
    """Exact maximum-weight one-to-one matching using a padded Hungarian algorithm."""
    n = max(len(scores), len(scores[0]) if scores else 0)
    if not n:
        return 0.0
    costs = [
        [-(scores[i][j] if i < len(scores) and j < len(scores[i]) else 0.0) for j in range(n)]
        for i in range(n)
    ]
    u, v = [0.0] * (n + 1), [0.0] * (n + 1)
    matched, previous = [0] * (n + 1), [0] * (n + 1)
    for row in range(1, n + 1):
        matched[0] = row
        column = 0
        distance, used = [float("inf")] * (n + 1), [False] * (n + 1)
        while True:
            used[column] = True
            active_row, next_column, delta = matched[column], 0, float("inf")
            for j in range(1, n + 1):
                if used[j]:
                    continue
                reduced = costs[active_row - 1][j - 1] - u[active_row] - v[j]
                if reduced < distance[j]:
                    distance[j], previous[j] = reduced, column
                if distance[j] < delta:
                    delta, next_column = distance[j], j
            for j in range(n + 1):
                if used[j]:
                    u[matched[j]] += delta
                    v[j] -= delta
                else:
                    distance[j] -= delta
            column = next_column
            if not matched[column]:
                break
        while column:
            matched[column] = matched[previous[column]]
            column = previous[column]
    return sum(-costs[matched[j] - 1][j - 1] for j in range(1, n + 1))


def drop_answer_metrics(prediction: tuple[str, ...], gold: tuple[str, ...]) -> tuple[float, float]:
    p = [normalize_drop_answer(s) for s in prediction]
    g = [normalize_drop_answer(s) for s in gold]
    em = float(set(p) == set(g) and len(p) == len(g))
    scores: list[list[float]] = []
    for expected in g:
        gb = set(expected.split())
        gn = {s for s in gb if _drop_number(s)}
        row = []
        for predicted in p:
            pb = set(predicted.split())
            pn = {s for s in pb if _drop_number(s)}
            if gn and not gn.intersection(pn):
                row.append(0.0)
                continue
            common = len(gb & pb)
            precision = common / len(pb) if pb else 1.0
            recall = common / len(gb) if gb else 1.0
            row.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
        scores.append(row)
    size = max(len(p), len(g))
    # Match NumPy's scaled round-to-even, including binary halfway cases.
    return em, round((_alignment_total(scores) / size) * 100) / 100 if size else 0.0


def parse_finqa_number(text: str) -> Decimal:
    value = text.strip().replace("\u2212", "-")
    accounting = value.startswith("(") and value.endswith(")")
    if accounting:
        value = value[1:-1].strip()
    currency = value[:1] in ("$", "€", "£")
    if currency:
        value = value[1:].strip()
    percent = value.endswith("%")
    if percent:
        value = value[:-1].strip()
    if (currency and percent) or (accounting and value[:1] in ("+", "-")):
        raise ValueError("invalid_numeric_answer")
    if not _NUMBER.fullmatch(value):
        raise ValueError("invalid_numeric_answer")
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("invalid_numeric_answer") from exc
    if not number.is_finite():
        raise ValueError("invalid_numeric_answer")
    exponent = number.as_tuple().exponent
    if not isinstance(exponent, int) or abs(exponent) > MAX_NUMERIC_EXPONENT:
        raise ValueError("numeric_exponent_out_of_range")
    with localcontext() as context:
        context.prec = max(50, len(number.as_tuple().digits) + 10)
        if accounting:
            number = -number
        if percent:
            number /= 100
    return number


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate_json_key")
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("invalid_json_constant")


def parse_final_answer(answer: str | tuple[str, ...] | None, dataset: DatasetId) -> tuple[str, ...]:
    value: Any = answer
    if isinstance(value, str):
        if len(value) > MAX_ANSWER_CHARACTERS:
            raise ValueError("answer_too_long")
        value = value.strip()
        if value.startswith(("{", "[", '"')):
            value = json.loads(value, object_pairs_hook=_object, parse_constant=_reject_constant)
            if isinstance(value, dict):
                if set(value) != {"answer"}:
                    raise ValueError("invalid_answer_envelope")
                value = value["answer"]
    if isinstance(value, str):
        spans = (value,)
    elif isinstance(value, (list, tuple)):
        spans = tuple(value)
    else:
        raise ValueError("invalid_answer_shape")
    if (
        not spans
        or len(spans) > MAX_ANSWER_SPANS
        or any(not isinstance(s, str) or not s.strip() for s in spans)
    ):
        raise ValueError("invalid_answer_spans")
    if sum(len(s) for s in spans) > MAX_ANSWER_CHARACTERS:
        raise ValueError("answer_too_long")
    if dataset != "drop" and len(spans) != 1:
        raise ValueError("multiple_answers_not_permitted")
    return spans


def _validate_reference(reference: EvaluationReference) -> None:
    if isinstance(reference, DropEvaluationReference) and reference.dataset_id != "drop":
        raise ValueError("DROP reference type must retain its DROP dataset identity.")
    if isinstance(reference, FinqaEvaluationReference) and reference.dataset_id != "finqa":
        raise ValueError("FinQA reference type must retain its FinQA dataset identity.")
    if reference.dataset_id == "drop" and not isinstance(reference, DropEvaluationReference):
        raise ValueError("DROP scoring requires C08 typed answer groups, not display strings.")
    if reference.dataset_id == "finqa" and not isinstance(reference, FinqaEvaluationReference):
        raise ValueError("FinQA scoring requires the distinct C09 execution target.")
    if isinstance(reference, FinqaEvaluationReference) and reference.answer_kind == "number":
        exponent = Decimal(reference.execution_answer).as_tuple().exponent
        if not isinstance(exponent, int) or abs(exponent) > MAX_NUMERIC_EXPONENT:
            raise ValueError("FinQA reference exponent is outside the registered numerical policy.")


def score_submission(submission: AnswerSubmission, reference: EvaluationReference) -> AnswerScore:
    """Evaluator-only API: unknown work is unavailable; known failures are incorrect."""
    if (submission.task_id, submission.dataset_id) != (reference.task_id, reference.dataset_id):
        raise ValueError("Submission and reference must identify the same task and dataset.")
    _validate_reference(reference)
    common: dict[str, Any] = {
        "task_id": submission.task_id,
        "dataset_id": submission.dataset_id,
        "scorer": scorer_identity(submission.dataset_id),
    }
    if submission.status in ("unknown", "started"):
        return AnswerScore(
            **common,
            status="unknown" if submission.status == "unknown" else "incomplete",
            reason="execution_not_known_terminal",
            binary_label=None,
        )

    def failure(
        status: Literal["execution_failed", "invalid_output", "truncated"], reason: str
    ) -> AnswerScore:
        return AnswerScore(
            **common,
            status=status,
            reason=reason,
            binary_label=0,
            answer_em=0.0 if submission.dataset_id != "finqa" else None,
            answer_f1=0.0 if submission.dataset_id != "finqa" else None,
            numeric_correct=False if submission.dataset_id == "finqa" else None,
        )

    if submission.status == "failed" or submission.failure_code is not None:
        return failure("execution_failed", "confirmed_execution_failure")
    if submission.finish_reason in ("length", "max_tokens", "max_output_tokens", "token_limit"):
        return failure("truncated", "generation_truncated")
    if submission.finish_reason not in (None, "stop", "eos", "eos_token", "end_turn"):
        return failure("invalid_output", "unaccepted_completion_reason")
    try:
        spans = parse_final_answer(submission.answer, submission.dataset_id)
    except (ValueError, RecursionError):
        return failure("invalid_output", "invalid_final_answer")
    difference: str | None = None
    normalized: tuple[str, ...]
    if isinstance(reference, FinqaEvaluationReference):
        if reference.answer_kind == "yes_no":
            normalized = (spans[0].strip().lower(),)
            if normalized[0] not in ("yes", "no"):
                return failure("invalid_output", "invalid_yes_no_answer")
            correct = normalized[0] == reference.execution_answer
        else:
            try:
                predicted = parse_finqa_number(spans[0])
            except ValueError:
                return failure("invalid_output", "invalid_numeric_answer")
            expected = Decimal(reference.execution_answer)
            with localcontext() as context:
                context.prec = (
                    max(50, len(predicted.as_tuple().digits), len(expected.as_tuple().digits)) + 10
                )
                delta = abs(predicted - expected)
            normalized, difference = (str(predicted),), str(delta)
            correct = delta <= FINQA_ABSOLUTE_TOLERANCE
        return AnswerScore(
            **common,
            status="scored",
            reason="correct_answer" if correct else "incorrect_answer",
            binary_label=1 if correct else 0,
            numeric_correct=correct,
            normalized_prediction=normalized,
            numerical_difference=difference,
        )
    if isinstance(reference, DropEvaluationReference):
        metrics = [drop_answer_metrics(spans, group.values) for group in reference.answer_groups]
        normalized = tuple(normalize_drop_answer(s) for s in spans)
    else:
        metrics = [hotpot_answer_metrics(spans[0], gold) for gold in reference.answers]
        normalized = (normalize_hotpot_answer(spans[0]),)
    em, f1 = max(m[0] for m in metrics), max(m[1] for m in metrics)
    return AnswerScore(
        **common,
        status="scored",
        reason="correct_answer" if em == 1.0 else "incorrect_answer",
        binary_label=1 if em == 1.0 else 0,
        answer_em=em,
        answer_f1=f1,
        normalized_prediction=normalized,
    )
