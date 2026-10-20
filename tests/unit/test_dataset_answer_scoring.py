"""Pinned upstream vectors, complete answer groups and evaluator failure boundaries."""

import itertools
import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import (
    EvaluationConfig,
    load_study_bundle,
    read_yaml_mapping,
)
from workflow_reuse_orchestrator.data.drop import normalize_drop_record
from workflow_reuse_orchestrator.data.finqa import normalize_finqa_record
from workflow_reuse_orchestrator.domain.tasks import DatasetId, EvaluationReference
from workflow_reuse_orchestrator.evaluation.scoring import (
    MAX_ANSWER_CHARACTERS,
    MAX_ANSWER_SPANS,
    AnswerScore,
    AnswerSubmission,
    _alignment_total,
    drop_answer_metrics,
    hotpot_answer_metrics,
    normalize_drop_answer,
    parse_final_answer,
    parse_finqa_number,
    score_submission,
    scorer_declaration,
    scorer_identity,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/scoring_reference_cases.json"


def hotpot(*answers: str) -> EvaluationReference:
    return EvaluationReference(
        task_id="task-1", dataset_id="hotpotqa", answers=answers or ("New York",)
    )


def drop(*spans: str, alternatives: list[dict[str, Any]] | None = None) -> EvaluationReference:
    qa = {
        "query_id": "q1",
        "question": "Which names?",
        "answer": {
            "number": "",
            "date": {},
            "spans": list(spans or ("North", "South")),
        },
        "validated_answers": alternatives or [],
    }
    return normalize_drop_record("p1", "Supplied text", qa).reference


def finqa(execution: Any = 3.8, reported: str = "380") -> EvaluationReference:
    return normalize_finqa_record(
        {
            "id": "ACME/2020/page_1.pdf-1",
            "filename": "ACME/2020/page_1.pdf",
            "pre_text": ["Native text"],
            "post_text": [],
            "table_ori": [["Year", "Value"], ["2020", "3.8"]],
            "table": [["year", "value"], ["2020", "3.8"]],
            "qa": {
                "question": "What is the value?",
                "answer": reported,
                "exe_ans": execution,
                "program": "divide(3.8, const_1)",
            },
        }
    ).reference


def submission(
    reference: EvaluationReference, answer: Any = None, **changes: Any
) -> AnswerSubmission:
    return AnswerSubmission.model_validate(
        {
            "task_id": reference.task_id,
            "dataset_id": reference.dataset_id,
            "status": "succeeded",
            "answer": answer,
            **changes,
        }
    )


@pytest.mark.parametrize("dataset", ["hotpotqa", "drop"])
def test_metrics_agree_with_independently_generated_upstream_vectors(dataset: DatasetId) -> None:
    fixture = json.loads(FIXTURE.read_text())
    for index, case in enumerate(fixture[dataset]):
        actual = (
            hotpot_answer_metrics(case["prediction"], case["gold"])
            if dataset == "hotpotqa"
            else drop_answer_metrics(tuple(case["prediction"]), tuple(case["gold"]))
        )
        assert actual == pytest.approx(case["expected"], abs=1e-12), (dataset, index, case)


@pytest.mark.parametrize("dataset", ["hotpotqa", "drop", "finqa"])
def test_receipt_identities_bind_pinned_sources_parser_and_implementation(
    dataset: DatasetId,
) -> None:
    pinned = json.loads(FIXTURE.read_text())["sources"][dataset]
    identity = scorer_identity(dataset)
    assert identity["upstream_revision"] == pinned["revision"]
    assert identity["upstream_sha256"] == pinned["sha256"]
    assert len(identity["implementation_sha256"]) == len(identity["fingerprint"]) == 64
    assert identity == scorer_identity(dataset)
    assert identity["parser_version"] == "final-answer-v1"
    assert identity["label_version"] == "known-terminal-correctness-v1"


def test_alignment_is_global_optimum_for_rectangular_and_tied_matrices() -> None:
    rng = random.Random(2609)
    for rows, columns in itertools.product(range(1, 5), repeat=2):
        scores = [
            [rng.choice((0.0, 0.25, 0.5, 0.75, 1.0)) for _ in range(columns)] for _ in range(rows)
        ]
        n = max(rows, columns)
        expected = max(
            sum(
                scores[i][j] if i < rows and j < columns else 0.0 for i, j in enumerate(permutation)
            )
            for permutation in itertools.permutations(range(n))
        )
        assert _alignment_total(scores) == pytest.approx(expected)
    assert _alignment_total([[0.9, 0.8], [0.8, 0.0]]) == pytest.approx(1.6)


def test_hotpot_exact_match_controls_label_even_when_f1_is_partial() -> None:
    reference = hotpot("New York City", "NYC")
    partial = score_submission(submission(reference, "New York"), reference)
    assert partial.answer_em == 0.0 and partial.answer_f1 == pytest.approx(0.8)
    assert partial.binary_label == 0
    complete = score_submission(submission(reference, "The NYC!"), reference)
    assert complete.answer_em == complete.answer_f1 == 1.0
    assert complete.binary_label == 1


@pytest.mark.parametrize(
    "prediction,gold,em,f1",
    [
        ("red red blue", "red blue", 0.0, 0.8),
        ("yes indeed", "yes", 0.0, 0.0),
        ("no", "noanswer", 0.0, 0.0),
        ("the", "the", 1.0, 0.0),
    ],
)
def test_hotpot_counter_polarity_and_empty_normalization_rules(
    prediction: str, gold: str, em: float, f1: float
) -> None:
    assert hotpot_answer_metrics(prediction, gold) == pytest.approx((em, f1))


def test_drop_requires_all_spans_with_order_independent_matching() -> None:
    reference = drop("North", "South")
    complete = score_submission(submission(reference, '["South","North"]'), reference)
    assert complete.binary_label == 1 and complete.answer_em == complete.answer_f1 == 1.0
    incomplete = score_submission(submission(reference, "North"), reference)
    assert incomplete.binary_label == 0 and incomplete.answer_f1 == 0.5
    combined = score_submission(submission(reference, "North and South"), reference)
    assert combined.binary_label == 0
    duplicate = score_submission(submission(reference, ("North", "South", "South")), reference)
    assert duplicate.binary_label == 0


def test_drop_number_gating_and_upstream_sign_tokenization_are_preserved() -> None:
    assert drop_answer_metrics(("4 points",), ("3 points",)) == (0.0, 0.0)
    assert drop_answer_metrics(("3.0",), ("3",)) == (1.0, 1.0)
    assert normalize_drop_answer("-3") == "3.0"  # Pinned upstream hyphen tokenization.


def test_drop_alternatives_and_partial_dates_are_complete_evaluator_groups() -> None:
    reference = drop(
        "North",
        alternatives=[
            {"number": "", "spans": [], "date": {"day": "", "month": "", "year": "1998"}}
        ],
    )
    assert score_submission(submission(reference, "1998"), reference).binary_label == 1
    assert score_submission(submission(reference, "1999"), reference).binary_label == 0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,234.50", "1234.50"),
        ("$1,234.50", "1234.50"),
        ("€12", "12"),
        ("£12", "12"),
        ("($1,234.50)", "-1234.50"),
        ("(3.8)", "-3.8"),
        ("26%", "0.26"),
        (" 2.6e1 % ", "0.26"),
        ("\u22123.8", "-3.8"),
        (".25", "0.25"),
        ("-0", "0"),
    ],
)
def test_finqa_decimal_parser_policy(text: str, expected: str) -> None:
    assert parse_finqa_number(text) == Decimal(expected)


@pytest.mark.parametrize(
    "text",
    [
        "NaN",
        "Infinity",
        "1,2,3",
        "12,34",
        "3 million",
        "about 3",
        "(-3)",
        "$3%",
        "3/4",
        "3 or 4",
        "",
        "1e10000",
    ],
)
def test_finqa_rejects_nonfinite_ambiguous_or_unregistered_unit_answers(text: str) -> None:
    reference = finqa(3.0)
    score = score_submission(submission(reference, text), reference)
    assert score.binary_label == 0 and score.status == "invalid_output"


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("3.8", 1),
        ("3.80001", 1),
        ("3.8000100001", 0),
        ("3.79999", 1),
        ("3.7999899999", 0),
        ("380", 0),
    ],
)
def test_finqa_absolute_tolerance_boundary_and_distinct_reported_answer(
    answer: str, expected: int
) -> None:
    reference = finqa(3.8, reported="380")
    score = score_submission(submission(reference, answer), reference)
    assert score.binary_label == expected
    assert score.numeric_correct is bool(expected)
    assert score.answer_em is score.answer_f1 is None


def test_finqa_percentage_scaling_is_explicit_and_never_guessed_from_gold() -> None:
    fraction, percentage_points = finqa(0.26), finqa(26.0)
    assert score_submission(submission(fraction, "26%"), fraction).binary_label == 1
    assert score_submission(submission(fraction, "26"), fraction).binary_label == 0
    assert (
        score_submission(submission(percentage_points, "26%"), percentage_points).binary_label == 0
    )
    large = finqa(1e12)
    assert score_submission(submission(large, "1000000000000.01"), large).binary_label == 0


@pytest.mark.parametrize("answer,expected", [(" YES ", 1), ("no", 0), ("true", 0), ("1", 0)])
def test_finqa_yes_no_is_categorical_not_numeric(answer: str, expected: int) -> None:
    reference = finqa("yes", reported="")
    assert score_submission(submission(reference, answer), reference).binary_label == expected


@pytest.mark.parametrize("answer", [" New York ", '"New York"', '{"answer":"New York"}'])
def test_explicit_scalar_formats_have_one_frozen_meaning(answer: str) -> None:
    reference = hotpot()
    assert score_submission(submission(reference, answer), reference).binary_label == 1


@pytest.mark.parametrize(
    "answer",
    [
        None,
        "",
        " ",
        "[]",
        "[1]",
        '["North",null]',
        '{"answer":"North","answer":"South"}',
        '{"answer":NaN}',
        '{"answer":"New York","reason":"guess"}',
        "[broken",
        ("New York", "NYC"),
        '```json\n{"answer":"New York"}\n```',
    ],
)
def test_invalid_or_ambiguous_final_output_is_not_repaired(answer: Any) -> None:
    reference = hotpot()
    score = score_submission(submission(reference, answer), reference)
    assert score.binary_label == 0
    # Code fences are treated as literal answer prose, not silently stripped.
    assert score.status in ("invalid_output", "scored")


def test_output_size_and_span_bounds_are_registered() -> None:
    with pytest.raises(ValueError, match="too_long"):
        parse_final_answer("x" * (MAX_ANSWER_CHARACTERS + 1), "hotpotqa")
    with pytest.raises(ValueError, match="invalid_answer_spans"):
        parse_final_answer(("x",) * (MAX_ANSWER_SPANS + 1), "drop")


@pytest.mark.parametrize("reference", [hotpot(), drop(), finqa()])
@pytest.mark.parametrize("reason", ["length", "max_tokens", "max_output_tokens", "token_limit"])
def test_truncated_correct_looking_answers_are_incorrect(
    reference: EvaluationReference, reason: str
) -> None:
    answer = reference.answers[0]
    result = score_submission(submission(reference, answer, finish_reason=reason), reference)
    assert result.status == "truncated" and result.binary_label == 0


@pytest.mark.parametrize("reference", [hotpot(), drop(), finqa()])
def test_confirmed_execution_failure_overrides_correct_looking_text(
    reference: EvaluationReference,
) -> None:
    result = score_submission(
        submission(reference, reference.answers[0], status="failed", failure_code="provider_error"),
        reference,
    )
    assert result.status == "execution_failed" and result.binary_label == 0


@pytest.mark.parametrize("status", ["unknown", "started"])
def test_unknown_and_unfinished_effects_never_become_binary_training_rows(status: str) -> None:
    reference = hotpot()
    result = score_submission(submission(reference, "New York", status=status), reference)
    assert (
        result.binary_label
        is result.answer_em
        is result.answer_f1
        is result.numeric_correct
        is None
    )
    assert result.status == ("unknown" if status == "unknown" else "incomplete")
    with pytest.raises(ValueError, match="unknown execution state"):
        submission(reference, "New York", status="failed", failure_code="unknown_effect")


def test_unaccepted_completion_reason_is_a_known_invalid_output() -> None:
    reference = hotpot()
    result = score_submission(
        submission(reference, "New York", finish_reason="content_filter"), reference
    )
    assert result.status == "invalid_output" and result.binary_label == 0


def test_task_identity_and_typed_reference_boundaries_are_enforced() -> None:
    reference = hotpot()
    with pytest.raises(ValueError, match="same task"):
        score_submission(submission(reference, "New York", task_id="different-task"), reference)
    for dataset in ("drop", "finqa"):
        flat = EvaluationReference(task_id="t", dataset_id=dataset, answers=("display only",))
        with pytest.raises(ValueError, match="requires"):
            score_submission(submission(flat, "display only"), flat)


@pytest.mark.parametrize("reference", [drop(), finqa()])
def test_typed_reference_cannot_be_relabelled_to_another_dataset(
    reference: EvaluationReference,
) -> None:
    invalid = reference.model_copy(update={"dataset_id": "hotpotqa"})
    with pytest.raises(ValueError, match="reference type"):
        score_submission(submission(invalid, "a prediction"), invalid)


def test_receipts_cannot_claim_success_from_partial_f1() -> None:
    reference = hotpot("New York City")
    partial = score_submission(submission(reference, "New York"), reference)
    assert AnswerScore.model_validate_json(partial.model_dump_json()) == partial
    document = partial.model_dump(mode="json")
    document["binary_label"] = 1
    with pytest.raises(ValueError, match="Binary success"):
        AnswerScore.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("label", [True, False, 1.0, 0.0])
def test_receipt_labels_do_not_coerce_boolean_or_float_values(label: Any) -> None:
    reference = hotpot()
    result = score_submission(submission(reference, "New York"), reference)
    document = result.model_dump(mode="json")
    document["binary_label"] = label
    with pytest.raises(ValueError, match="integer"):
        AnswerScore.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("dataset", ["hotpotqa", "drop", "finqa"])
def test_configured_versions_and_tolerances_must_match_implemented_policy(
    dataset: DatasetId,
) -> None:
    bundle = load_study_bundle()
    declared = getattr(bundle.evaluation.scoring, dataset)
    assert declared.model_dump(mode="json") == scorer_declaration(dataset)
    for field, value in (("version", "different"), ("numerical_tolerance", 0.5)):
        document = read_yaml_mapping(bundle.root / "configs/evaluation.yaml")
        document["scoring"][dataset][field] = value
        with pytest.raises(ValueError, match="implemented identity"):
            EvaluationConfig.model_validate(document)


def test_cli_catalog_and_explicit_pair_scoring_are_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["evaluation", "scorers"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert set(catalog["scorers"]) == {"hotpotqa", "drop", "finqa"}
    assert catalog["runtime_contacted"] is False
    reference = finqa()
    submission_path, reference_path = tmp_path / "submission.json", tmp_path / "reference.json"
    submission_path.write_text(submission(reference, "3.8").model_dump_json())
    reference_path.write_text(reference.model_dump_json())
    assert (
        main(
            [
                "evaluation",
                "score",
                "--submission",
                str(submission_path),
                "--reference",
                str(reference_path),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["binary_label"] == 1 and result["numeric_correct"] is True
    submission_path.write_text(submission(reference, "380").model_dump_json())
    assert (
        main(
            [
                "evaluation",
                "score",
                "--submission",
                str(submission_path),
                "--reference",
                str(reference_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["binary_label"] == 0
