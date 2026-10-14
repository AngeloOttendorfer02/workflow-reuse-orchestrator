"""Supplied sources preserve structure; evaluator annotations cannot enter inputs."""

import json

import pytest

from workflow_reuse_orchestrator.config import project_root
from workflow_reuse_orchestrator.domain.tasks import EvaluationReference, Passage, Table, TaskInput


def test_document_input_preserves_sentence_and_cell_positions() -> None:
    task = TaskInput(
        task_id="task-1",
        dataset_id="finqa",
        question="What changed?",
        passages=(Passage(source_id="report", passage_id="note", sentences=("A note.",)),),
        tables=(
            Table(source_id="report", table_id="table", rows=(("Year", "Value"), ("2025", "120"))),
        ),
    )
    restored = TaskInput.model_validate_json(task.model_dump_json())
    assert restored == task
    assert restored.tables[0].rows[1][1] == "120"
    assert restored.passages[0].sentences[0] == "A note."


@pytest.mark.parametrize("field", ["reference_answer", "gold_program", "annotations", "metadata"])
def test_model_input_rejects_reference_and_free_form_fields(field: str) -> None:
    document = json.loads((project_root() / "examples/document_question.json").read_text())
    document[field] = "hidden answer"
    with pytest.raises(ValueError, match="Extra inputs"):
        TaskInput.model_validate_json(json.dumps(document))


def test_reference_remains_separate_from_input() -> None:
    task = TaskInput.model_validate_json(
        (project_root() / "examples/document_question.json").read_text()
    )
    reference = EvaluationReference(
        task_id=task.task_id,
        dataset_id=task.dataset_id,
        answers=("20",),
        annotations={"gold_program": "subtract then divide"},
    )
    assert reference.task_id == task.task_id
    assert "gold_program" not in task.model_dump_json()
    assert "answers" not in task.model_dump()


def test_rejects_duplicate_document_identifiers() -> None:
    passage = Passage(source_id="s", passage_id="p", sentences=("Text.",))
    with pytest.raises(ValueError, match="unique"):
        TaskInput(task_id="t", dataset_id="drop", question="Question?", passages=(passage, passage))
