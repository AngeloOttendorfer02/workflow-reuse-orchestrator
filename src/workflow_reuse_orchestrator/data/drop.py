"""DROP passages and typed evaluator answers, without gold-selected context."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import zipfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionManifest,
    Progress,
    _hash_file,
    _json_records,
    _verify_file,
)
from workflow_reuse_orchestrator.data.staging import STAGING_SQL, content_hash, read_only
from workflow_reuse_orchestrator.domain.tasks import EvaluationReference, Passage, TaskInput, Text
from workflow_reuse_orchestrator.storage import _WriterLock, canonical_json, canonical_sha256

ADAPTER_VERSION = "drop-original-v1"
STAGING_SCHEMA = "drop-staging-v1"
_EXTRA_TABLES = (("native_locations", "native_split,task_id"),)
_DROP_SQL = """
CREATE TABLE native_locations (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, passage_id TEXT NOT NULL,
    query_id TEXT NOT NULL, passage_index INTEGER NOT NULL, question_index INTEGER NOT NULL,
    PRIMARY KEY(native_split,task_id),
    FOREIGN KEY(native_split,task_id) REFERENCES inputs(native_split,task_id));
CREATE INDEX native_query_identity ON native_locations(native_split,query_id);
"""


class MalformedDropRecord(ValueError):
    """Stable record exclusion reason."""


class DropAnswer(BaseModel):
    """One complete answer; multi-span values are jointly required, not alternatives."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal["number", "span", "spans", "date"]
    values: tuple[Text, ...] = Field(min_length=1)
    date_parts: dict[str, str] | None = None
    origin: Literal["answer", "validated_answers"]
    annotation_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_group(self) -> Self:
        if (self.kind == "spans" and len(self.values) < 2) or (
            self.kind != "spans" and len(self.values) != 1
        ):
            raise ValueError("DROP answer groups must retain their complete typed value shape.")
        if self.kind == "date":
            if self.date_parts is None or set(self.date_parts) != {"day", "month", "year"}:
                raise ValueError("A DROP date must preserve its three native components.")
            rendered = "{day} {month} {year}".format(**self.date_parts).strip()
            if self.values != (rendered,):
                raise ValueError("DROP date text must agree with its native components.")
        elif self.date_parts is not None:
            raise ValueError("Only a DROP date group may contain date components.")
        return self

    def display(self) -> str:
        return canonical_json(self.values) if self.kind == "spans" else self.values[0]


class DropEvaluationReference(EvaluationReference):
    """Typed groups are authoritative for C10 DROP scoring; answers are displays."""

    answer_groups: tuple[DropAnswer, ...] = Field(min_length=1)


@dataclass(frozen=True)
class DropRecord:
    task: TaskInput
    reference: DropEvaluationReference
    warnings: tuple[str, ...]


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedDropRecord(reason)
    return value


def _identifier(value: Any, reason: str) -> str:
    result = _text(value, reason)
    if result != result.strip():
        raise MalformedDropRecord(reason)
    return result


def _answer(
    raw: Any, origin: Literal["answer", "validated_answers"], index: int
) -> tuple[DropAnswer | None, str | None]:
    if not isinstance(raw, dict):
        return None, "invalid_answer_annotation"
    number = raw.get("number", "")
    spans = raw.get("spans", [])
    date = raw.get("date", {"day": "", "month": "", "year": ""})
    if (
        not isinstance(number, str)
        or not isinstance(spans, list)
        or any(not isinstance(s, str) or not s.strip() for s in spans)
        or not isinstance(date, dict)
        or not set(date) <= {"day", "month", "year"}
        or any(not isinstance(v, str) for v in date.values())
    ):
        return None, "invalid_answer_annotation"
    # Native number/span answers can have date={}; missing date components stay empty.
    date = {"day": "", "month": "", "year": "", **date}
    active = (bool(number.strip()), bool(spans), any(v.strip() for v in date.values()))
    warning = "multiple_answer_fields" if sum(active) > 1 else None
    # Match the upstream evaluator's number > spans > date precedence.
    if active[0]:
        kind: Literal["number", "span", "spans", "date"] = "number"
        values = (number,)
    elif active[1]:
        kind = "span" if len(spans) == 1 else "spans"
        values = tuple(spans)
    elif active[2]:
        kind = "date"
        values = (f"{date['day']} {date['month']} {date['year']}".strip(),)
    else:
        return None, "empty_answer_annotation"
    return DropAnswer(
        kind=kind,
        values=values,
        date_parts=date if kind == "date" else None,
        origin=origin,
        annotation_index=index,
    ), warning


def normalize_drop_record(passage_id: str, passage_text: Any, qa: dict[str, Any]) -> DropRecord:
    """Keep native text intact and construct evaluator-only typed answer groups."""
    passage_id = _identifier(passage_id, "invalid_passage_id")
    passage_text = _text(passage_text, "invalid_passage")
    query_id = _identifier(qa.get("query_id"), "invalid_query_id")
    question = _text(qa.get("question"), "invalid_question")
    # Native query IDs are not unique in the released dev file. Use input-only
    # disambiguation, so changing reference annotations never changes a task ID.
    task_id = "drop:" + query_id + ":" + canonical_sha256([passage_id, question])
    passage = Passage(
        source_id="drop:passage:" + passage_id,
        passage_id="drop:paragraph:" + canonical_sha256([passage_id, passage_text]),
        title=passage_id,
        sentences=(passage_text,),
    )
    warnings: list[str] = []
    groups: list[DropAnswer] = []
    primary, warning = _answer(qa.get("answer"), "answer", 0)
    if primary is not None:
        groups.append(primary)
    if warning:
        warnings.append(warning)
    validated = qa.get("validated_answers", [])
    if not isinstance(validated, list):
        warnings.append("invalid_validated_answers")
    else:
        for index, annotation in enumerate(validated):
            group, warning = _answer(annotation, "validated_answers", index)
            if group is not None:
                groups.append(group)
            if warning:
                warnings.append(warning)
    if not groups:
        raise MalformedDropRecord("no_usable_answers")
    reference = DropEvaluationReference(
        task_id=task_id,
        dataset_id="drop",
        answers=tuple(dict.fromkeys(g.display() for g in groups)),
        answer_groups=tuple(groups),
        annotations={k: v for k, v in qa.items() if k not in ("query_id", "question")},
    )
    return DropRecord(
        TaskInput(task_id=task_id, dataset_id="drop", question=question, passages=(passage,)),
        reference,
        tuple(dict.fromkeys(warnings)),
    )


def load_drop_task(path: Path, task_id: str, *, split: str) -> TaskInput:
    """Read only the checksummed input table."""
    with closing(read_only(path)) as connection:
        row = connection.execute(
            "SELECT input_json,content_sha256 FROM inputs WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized DROP input was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized DROP input checksum mismatch.")
    task = TaskInput.model_validate_json(row[0])
    if task.dataset_id != "drop":
        raise ValueError("Normalized input does not belong to DROP.")
    return task


def load_drop_reference(path: Path, task_id: str, *, split: str) -> DropEvaluationReference:
    """Read typed answers explicitly, separately from online inputs."""
    with closing(read_only(path)) as connection:
        row = connection.execute(
            "SELECT reference_json,content_sha256 FROM evaluation_references "
            "WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized DROP reference was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized DROP reference checksum mismatch.")
    reference = DropEvaluationReference.model_validate_json(row[0])
    if reference.dataset_id != "drop":
        raise ValueError("Normalized reference does not belong to DROP.")
    return reference


def _insert_question(
    connection: sqlite3.Connection,
    raw: dict[str, Any],
    split: str,
    ordinal: int,
    passage_index: int,
    question_index: int,
    counts: Counter[str],
) -> None:
    counts["raw"] += 1
    raw_hash = canonical_sha256(raw)
    qa = raw["qa"]
    reason: str | None = None
    try:
        record = normalize_drop_record(raw["passage_id"], raw["passage"], qa)
    except (MalformedDropRecord, ValidationError) as exc:
        reason = str(exc) if isinstance(exc, MalformedDropRecord) else "invalid_contract"
    if reason is None:
        previous = connection.execute(
            "SELECT raw_sha256 FROM provenance WHERE native_split=? AND task_id=?",
            (split, record.task.task_id),
        ).fetchone()
        if previous is not None:
            if previous[0] != raw_hash:
                raise ValueError(f"Conflicting DROP task in {split} at question index {ordinal}.")
            reason = "duplicate_task"
    if reason is not None:
        counts["duplicates" if reason == "duplicate_task" else "malformed"] += 1
        connection.execute(
            "INSERT INTO exclusions VALUES (?,?,?,?,?)",
            (
                split,
                ordinal,
                qa.get("query_id") if isinstance(qa.get("query_id"), str) else None,
                raw_hash,
                reason,
            ),
        )
        return
    task = record.task
    warnings = list(record.warnings)
    if connection.execute(
        "SELECT 1 FROM native_locations WHERE native_split=? AND query_id=? LIMIT 1",
        (split, qa["query_id"]),
    ).fetchone():
        counts["reused_native_query_ids"] += 1
        warnings.append("reused_native_query_id")
    for table, payload in (("inputs", task), ("evaluation_references", record.reference)):
        document = payload.model_dump(mode="json")
        connection.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?)",
            (split, task.task_id, canonical_json(document), canonical_sha256(document)),
        )
    connection.execute(
        "INSERT INTO provenance VALUES (?,?,?,?,?)",
        (split, task.task_id, ordinal, raw_hash, canonical_json(warnings)),
    )
    passage = task.passages[0]
    connection.execute(
        "INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)",
        (
            passage.passage_id,
            passage.source_id,
            passage.title,
            canonical_json(passage.sentences),
            canonical_sha256(passage.sentences),
        ),
    )
    connection.execute(
        "INSERT INTO task_sources VALUES (?,?,?,?)", (split, task.task_id, 0, passage.passage_id)
    )
    connection.execute(
        "INSERT INTO native_locations VALUES (?,?,?,?,?,?)",
        (split, task.task_id, raw["passage_id"], qa["query_id"], passage_index, question_index),
    )
    counts["retained"] += 1
    counts["with_annotation_warnings"] += int(bool(record.warnings))
    counts["answer_type_" + record.reference.answer_groups[0].kind] += 1


def normalize_drop(
    plan: AcquisitionDataset,
    raw_root: Path,
    output: Path,
    *,
    split: str = "all",
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Normalize fixed ZIP members offline into a checksummed, unpartitioned artifact."""
    if (
        split not in ("all", "train", "dev")
        or len(plan.sources) != 1
        or plan.sources[0].format != "drop_zip"
        or set(plan.sources[0].splits) != {"train", "dev"}
    ):
        raise ValueError("DROP normalization requires one original train/dev ZIP release.")
    source = plan.sources[0]
    selected = [s for s in ("train", "dev") if split in ("all", s)]
    directory = raw_root / "drop" / plan.release
    manifest = AcquisitionManifest.model_validate_json(
        (directory / "acquisition.json").read_text("utf-8")
    )
    if (
        manifest.dataset != "drop"
        or manifest.release != plan.release
        or manifest.source_plan != plan
        or manifest.plan_sha256 != canonical_sha256(plan.model_dump(mode="json"))
        or set(manifest.sources) != {source.filename}
    ):
        raise ValueError("DROP acquisition provenance does not match the configured release.")
    receipt = manifest.sources[source.filename]
    if receipt.status != "complete":
        raise ValueError("Acquire the DROP archive before normalization.")
    path = directory / source.filename
    _verify_file(path, receipt)
    if source.expected_sha256 not in (None, receipt.sha256) or source.expected_bytes not in (
        None,
        receipt.size_bytes,
    ):
        raise ValueError("DROP receipt disagrees with pinned source bytes.")
    output = output.resolve()
    if output == raw_root.resolve() or raw_root.resolve() in output.parents:
        raise ValueError("Normalization output must not be inside immutable raw sources.")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = _WriterLock(output.with_name(output.name + ".lock"))
    temporary: Path | None = None
    connection: sqlite3.Connection | None = None
    emit = progress or (lambda message: None)
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=output.name + ".", suffix=".tmp", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(STAGING_SQL + _DROP_SQL)
        counts_by_split: dict[str, dict[str, int]] = {}
        with zipfile.ZipFile(path) as archive:
            for native_split in selected:
                member = f"drop_dataset/drop_dataset_{native_split}.json"
                matches = [i for i in archive.infolist() if i.filename == member]
                if len(matches) != 1 or matches[0].file_size > 1024**3:
                    raise ValueError(f"DROP archive requires one bounded {member} member.")
                counts: Counter[str] = Counter(
                    {
                        k: 0
                        for k in (
                            "raw_passages",
                            "raw",
                            "retained",
                            "duplicates",
                            "malformed",
                            "with_annotation_warnings",
                            "reused_native_query_ids",
                            "answer_type_number",
                            "answer_type_span",
                            "answer_type_spans",
                            "answer_type_date",
                        )
                    }
                )
                emit(f"Normalizing DROP {native_split}; preserving original passage text.")
                with (
                    archive.open(matches[0]) as raw,
                    io.TextIOWrapper(raw, encoding="utf-8") as text,
                ):
                    for passage_index, document in enumerate(
                        _json_records(text, mapping=True, key_field="__drop_passage_id")
                    ):
                        counts["raw_passages"] += 1
                        pairs = document.get("qa_pairs")
                        if not isinstance(pairs, list) or any(
                            not isinstance(q, dict) for q in pairs
                        ):
                            raise ValueError("DROP passage requires a qa_pairs list of objects.")
                        for question_index, qa in enumerate(pairs):
                            _insert_question(
                                connection,
                                {
                                    "passage_id": document["__drop_passage_id"],
                                    "passage": document.get("passage"),
                                    "qa": qa,
                                },
                                native_split,
                                counts["raw"],
                                passage_index,
                                question_index,
                                counts,
                            )
                            if counts["raw"] % 10000 == 0:
                                emit(f"DROP {native_split}: {counts['raw']} questions processed.")
                expected = receipt.counts.get(native_split)
                if expected is None or (counts["raw_passages"], counts["raw"]) != (
                    expected.records,
                    expected.questions,
                ):
                    raise ValueError("DROP raw counts differ from the acquisition receipt.")
                if counts["raw"] != counts["retained"] + counts["duplicates"] + counts["malformed"]:
                    raise ValueError("DROP normalization counts do not reconcile.")
                counts["retained_passages"] = connection.execute(
                    "SELECT COUNT(DISTINCT passage_id) FROM native_locations WHERE native_split=?",
                    (native_split,),
                ).fetchone()[0]
                counts["passages_without_retained_questions"] = (
                    counts["raw_passages"] - counts["retained_passages"]
                )
                counts_by_split[native_split] = dict(counts)
        if _hash_file(path) != receipt.sha256:
            raise ValueError("DROP raw archive changed during normalization.")
        metadata = {
            "schema_version": STAGING_SCHEMA,
            "adapter_version": ADAPTER_VERSION,
            "dataset": "drop",
            "release": plan.release,
            "source_plan_sha256": manifest.plan_sha256,
            "sources": {
                s: {
                    "filename": source.filename,
                    "archive_member": f"drop_dataset/drop_dataset_{s}.json",
                    "sha256": receipt.sha256,
                    "size_bytes": receipt.size_bytes,
                }
                for s in selected
            },
            "counts": counts_by_split,
            "source_versions": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "source_identities": connection.execute(
                "SELECT COUNT(DISTINCT source_id) FROM sources"
            ).fetchone()[0],
            "content_sha256": content_hash(connection, extra_tables=_EXTRA_TABLES),
        }
        metadata["normalization_id"] = "drop:" + canonical_sha256(metadata)
        connection.execute(
            "INSERT INTO metadata VALUES (?,?)", ("manifest", canonical_json(metadata))
        )
        connection.commit()
        connection.close()
        connection = None
        status = "normalized"
        if output.exists():
            with closing(read_only(output)) as existing:
                row = existing.execute(
                    "SELECT value_json FROM metadata WHERE key='manifest'"
                ).fetchone()
                if row is None or json.loads(row[0]) != metadata:
                    raise ValueError(
                        "Output already holds different normalization; choose a new output."
                    )
                if content_hash(existing, extra_tables=_EXTRA_TABLES) != metadata["content_sha256"]:
                    raise ValueError("Existing normalized DROP artifact checksum mismatch.")
            status = "verified_existing"
        else:
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, output)
        return {
            "status": status,
            "output": str(output),
            **metadata,
            "scientific_roles_assigned": False,
            "data_snapshot_available": False,
            "study_bindings_updated": False,
            "runtime_contacted": False,
        }
    except (zipfile.BadZipFile, KeyError, UnicodeError) as exc:
        raise ValueError(f"Invalid raw DROP archive: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.close()
