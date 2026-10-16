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


class EvaluationReference(BaseModel):
    """Evaluator-only answer forms and support/program annotations."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: Identifier
    dataset_id: DatasetId
    answers: tuple[Text, ...] = Field(min_length=1)
    annotations: dict[str, JsonValue] = Field(default_factory=dict)
