"""Role output parsing is pure, reference-free, and tied to current evidence."""

import json

import pytest
from pydantic import ValidationError

from workflow_reuse_orchestrator.config import project_root
from workflow_reuse_orchestrator.domain.budgets import ResourceUsage
from workflow_reuse_orchestrator.domain.outcomes import AttemptOutcome, validate_role_output_json
from workflow_reuse_orchestrator.domain.tasks import (
    CellEvidence,
    SentenceEvidence,
    TaskInput,
    resolve_evidence,
)
from workflow_reuse_orchestrator.domain.workflows import BoundWorkflow


@pytest.fixture
def task() -> TaskInput:
    return TaskInput.model_validate_json(
        (project_root() / "examples/document_question.json").read_text()
    )


@pytest.fixture
def graph() -> BoundWorkflow:
    return BoundWorkflow.model_validate_json(
        (project_root() / "examples/bound_workflow.json").read_text()
    )


def test_sentence_and_cell_locations_resolve_exact_text(task: TaskInput) -> None:
    passage, table = task.passages[0], task.tables[0]
    sentence = SentenceEvidence(
        task_id=task.task_id,
        source_id=passage.source_id,
        passage_id=passage.passage_id,
        sentence_index=0,
    )
    cell = CellEvidence(
        task_id=task.task_id,
        source_id=table.source_id,
        table_id=table.table_id,
        row_index=2,
        column_index=1,
    )
    assert resolve_evidence(task, sentence) == passage.sentences[0]
    assert resolve_evidence(task, cell) == table.rows[2][1]
    for update in (
        {"task_id": "other"},
        {"source_id": "other"},
        {"row_index": 99},
        {"column_index": 99},
    ):
        with pytest.raises(ValueError, match=r"current task|does not exist"):
            resolve_evidence(task, CellEvidence(**(cell.model_dump() | update)))


def test_role_mismatch_annotations_and_stale_evidence_rejected(
    task: TaskInput, graph: BoundWorkflow
) -> None:
    node = graph.nodes[1]
    with pytest.raises(ValueError, match="role"):
        validate_role_output_json('{"role":"retrieval","evidence":[]}', node=node, task=task)
    payload = {
        "role": "reasoning",
        "answer": "Example",
        "evidence": [],
        "reference_answer": "secret",
    }
    with pytest.raises(ValidationError, match="reference_answer"):
        validate_role_output_json(json.dumps(payload), node=node, task=task)
    del payload["reference_answer"]
    payload["evidence"] = [
        {
            "kind": "cell",
            "task_id": "previous-task",
            "source_id": "report",
            "table_id": "sales-table",
            "row_index": 1,
            "column_index": 1,
        }
    ]
    with pytest.raises(ValueError, match="current task"):
        validate_role_output_json(json.dumps(payload), node=node, task=task)


def test_role_outputs_are_structural_not_gold_correctness(
    task: TaskInput, graph: BoundWorkflow
) -> None:
    output = validate_role_output_json(
        '{"role":"reasoning","answer":"An unevaluated candidate","evidence":[]}',
        node=graph.nodes[1],
        task=task,
    )
    assert output.role == "reasoning"
    checked = validate_role_output_json(
        '{"role":"checking","check":{"verdict":"uncertain",'
        '"rationale":"No supporting evidence"},"evidence":[]}',
        node=graph.nodes[2],
        task=task,
    )
    assert checked.role == "checking"


def test_duplicate_evidence_is_not_multiple_support(task: TaskInput, graph: BoundWorkflow) -> None:
    passage = task.passages[0]
    ref = SentenceEvidence(
        task_id=task.task_id,
        source_id=passage.source_id,
        passage_id=passage.passage_id,
        sentence_index=0,
    ).model_dump(mode="json")
    with pytest.raises(ValueError, match="unique"):
        validate_role_output_json(
            json.dumps({"role": "retrieval", "evidence": [ref, ref]}),
            node=graph.nodes[0],
            task=task,
        )


def test_observable_metadata_contains_only_input_counts(task: TaskInput) -> None:
    counts = task.observable_metadata().model_dump()
    assert counts == {
        "question_characters": len(task.question),
        "passage_count": 1,
        "sentence_count": 1,
        "table_count": 1,
        "cell_count": 6,
    }
    assert not {"dataset_id", "answers", "annotations", "correct", "cost"} & counts.keys()


@pytest.mark.parametrize(
    "status,answer,code",
    [
        ("succeeded", None, None),
        ("succeeded", "answer", "tool_error"),
        ("started", None, "provider_error"),
        ("started", "answer", None),
        ("failed", None, None),
        ("failed", "answer", "tool_error"),
        ("unknown", None, "provider_error"),
        ("failed", None, "unknown_effect"),
    ],
)
def test_inconsistent_attempt_states_rejected(
    status: str, answer: str | None, code: str | None
) -> None:
    with pytest.raises(ValidationError):
        AttemptOutcome.model_validate(
            {
                "request_id": "r",
                "attempt_id": "a",
                "kind": "reuse",
                "status": status,
                "answer": answer,
                "failure_code": code,
                "cumulative_usage": ResourceUsage(),
            }
        )


def test_unknown_attempt_preserves_missing_usage() -> None:
    outcome = AttemptOutcome(
        request_id="r",
        attempt_id="a",
        kind="reuse",
        status="unknown",
        failure_code="unknown_effect",
        cumulative_usage=ResourceUsage(model_calls=1, input_tokens=None, output_tokens=None),
    )
    assert AttemptOutcome.model_validate_json(outcome.model_dump_json()) == outcome
    assert outcome.cumulative_usage.input_tokens is None
