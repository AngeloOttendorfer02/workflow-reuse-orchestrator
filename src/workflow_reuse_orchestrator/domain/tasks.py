"""Supplied-document inputs and separately loaded evaluator references."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

DatasetId = Literal["hotpotqa", "drop", "finqa"]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, strict=True)]
Text = Annotated[str, StringConstraints(pattern=r"(?s).*\S.*", strict=True)]


class Passage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: Identifier
    passage_id: Identifier
    title: str = ""
    sentences: tuple[Text, ...] = Field(min_length=1)


class Table(BaseModel):
    """Keep cell text and row/column positions; normalization belongs to preparation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: Identifier
    table_id: Identifier
    rows: tuple[tuple[str, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_cells(self) -> Self:
        if any(not row for row in self.rows):
            raise ValueError("Every table row must contain at least one cell.")
        return self


class TaskInput(BaseModel):
    """The complete online input; reference answers and annotations are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: Identifier
    dataset_id: DatasetId
    question: Text
    passages: tuple[Passage, ...] = ()
    tables: tuple[Table, ...] = ()

    @model_validator(mode="after")
    def validate_documents(self) -> Self:
        documents = [item.passage_id for item in self.passages]
        documents.extend(item.table_id for item in self.tables)
        if not documents:
            raise ValueError("A document question must contain supplied passages or tables.")
        if len(documents) != len(set(documents)):
            raise ValueError("Document identifiers must be unique within a task.")
        return self

    def observable_metadata(self) -> "ObservableTaskMetadata":
        """Input-only counts; C25 will define the four selector feature units."""
        return ObservableTaskMetadata(
            question_characters=len(self.question),
            passage_count=len(self.passages),
            sentence_count=sum(len(passage.sentences) for passage in self.passages),
            table_count=len(self.tables),
            cell_count=sum(len(row) for table in self.tables for row in table.rows),
        )


class ObservableTaskMetadata(BaseModel):
    """Descriptive counts, without dataset identity, answers, or execution outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    question_characters: int = Field(ge=1)
    passage_count: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    cell_count: int = Field(ge=0)


class SentenceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["sentence"] = "sentence"
    task_id: Identifier
    source_id: Identifier
    passage_id: Identifier
    sentence_index: int = Field(ge=0)


class CellEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["cell"] = "cell"
    task_id: Identifier
    source_id: Identifier
    table_id: Identifier
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)


EvidenceReference = Annotated[SentenceEvidence | CellEvidence, Field(discriminator="kind")]


def resolve_evidence(task: TaskInput, reference: EvidenceReference) -> str:
    """Resolve a zero-based location against this task, including source identity."""
    if reference.task_id != task.task_id:
        raise ValueError("Evidence must belong to the current task.")
    if isinstance(reference, SentenceEvidence):
        for passage in task.passages:
            if (passage.source_id, passage.passage_id) == (
                reference.source_id,
                reference.passage_id,
            ) and reference.sentence_index < len(passage.sentences):
                return passage.sentences[reference.sentence_index]
    else:
        for table in task.tables:
            if (table.source_id, table.table_id) == (
                reference.source_id,
                reference.table_id,
            ) and reference.row_index < len(table.rows):
                row = table.rows[reference.row_index]
                if reference.column_index < len(row):
                    return row[reference.column_index]
    raise ValueError("Evidence location does not exist in the supplied documents.")


class EvaluationReference(BaseModel):
    """Evaluator-only answer forms and support/program annotations."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: Identifier
    dataset_id: DatasetId
    answers: tuple[Text, ...] = Field(min_length=1)
    annotations: dict[str, JsonValue] = Field(default_factory=dict)
