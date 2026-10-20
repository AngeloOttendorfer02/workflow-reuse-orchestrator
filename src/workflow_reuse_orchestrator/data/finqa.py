"""Full FinQA report context, original tables and evaluator-only numerical targets."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import ValidationError, model_validator

from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionManifest,
    Progress,
    _hash_file,
    _json_records,
    _verify_file,
)
from workflow_reuse_orchestrator.data.staging import STAGING_SQL, content_hash, read_only
from workflow_reuse_orchestrator.domain.tasks import EvaluationReference, Passage, Table, TaskInput
from workflow_reuse_orchestrator.storage import _WriterLock, canonical_json, canonical_sha256

ADAPTER_VERSION = "finqa-original-table-v1"
STAGING_SCHEMA = "finqa-staging-v1"
_EXTRA_TABLES = (
    ("table_versions", "table_id"),
    ("task_tables", "native_split,task_id,position"),
    ("page_versions", "page_version_id"),
    ("native_locations", "native_split,task_id"),
)
_FINQA_SQL = """
CREATE TABLE table_versions (
    table_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, page_id TEXT NOT NULL,
    representation TEXT NOT NULL, rows_json TEXT NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE task_tables (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, position INTEGER NOT NULL,
    table_id TEXT NOT NULL REFERENCES table_versions(table_id),
    PRIMARY KEY(native_split,task_id,position),
    FOREIGN KEY(native_split,task_id) REFERENCES inputs(native_split,task_id));
CREATE TABLE page_versions (
    page_version_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, report_id TEXT NOT NULL,
    filename TEXT NOT NULL, pre_text_json TEXT NOT NULL, post_text_json TEXT NOT NULL,
    original_table_id TEXT NOT NULL REFERENCES table_versions(table_id),
    processed_table_id TEXT NOT NULL REFERENCES table_versions(table_id));
CREATE TABLE native_locations (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, native_id TEXT NOT NULL,
    report_id TEXT NOT NULL, page_id TEXT NOT NULL,
    page_version_id TEXT NOT NULL REFERENCES page_versions(page_version_id),
    PRIMARY KEY(native_split,task_id),
    FOREIGN KEY(native_split,task_id) REFERENCES inputs(native_split,task_id));
CREATE INDEX financial_report_identity ON native_locations(report_id);
CREATE INDEX financial_page_identity ON native_locations(page_id);
"""


class MalformedFinqaRecord(ValueError):
    """Stable record exclusion reason, without logging gold values."""


class FinqaEvaluationReference(EvaluationReference):
    """Execution target and reported answer remain distinct; C10 defines scoring."""

    answer_kind: Literal["number", "yes_no"]
    execution_answer: str
    reported_answer: str | None
    program: str | None
    annotation_table_representation: Literal["table"] = "table"

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        kind, value = _execution_answer(self.execution_answer)
        if kind != self.answer_kind or value != self.execution_answer:
            raise ValueError("FinQA execution target does not match its declared answer kind.")
        if self.answers != (self.execution_answer,):
            raise ValueError(
                "FinQA reported answers must not replace or extend the execution target."
            )
        return self


@dataclass(frozen=True)
class FinqaRecord:
    task: TaskInput
    reference: FinqaEvaluationReference
    report_id: str
    page_id: str
    page_version_id: str
    filename: str
    pre_text: tuple[str, ...]
    post_text: tuple[str, ...]
    processed_table: Table
    warnings: tuple[str, ...]


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedFinqaRecord(reason)
    return value


def _text_rows(value: Any, reason: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(s, str) for s in value):
        raise MalformedFinqaRecord(reason)
    return tuple(value)


def _table_rows(value: Any, reason: str) -> tuple[tuple[str, ...], ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(row, list) or not row or any(not isinstance(c, str) for c in row)
            for row in value
        )
    ):
        raise MalformedFinqaRecord(reason)
    return tuple(tuple(row) for row in value)


def _execution_answer(value: Any) -> tuple[Literal["number", "yes_no"], str]:
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in ("yes", "no"):
            return "yes_no", text.lower()
    elif type(value) is int or (type(value) is float and math.isfinite(value)):
        text = canonical_json(value)
    else:
        raise MalformedFinqaRecord("invalid_execution_answer")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise MalformedFinqaRecord("invalid_execution_answer") from exc
    if not number.is_finite():
        raise MalformedFinqaRecord("invalid_execution_answer")
    return "number", text


def normalize_finqa_record(raw: dict[str, Any]) -> FinqaRecord:
    """Preserve original table cells and every text row; never use gold retrieval."""
    filename = _text(raw.get("filename"), "invalid_filename")
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([0-9]{4})/page_([0-9]+)\.pdf", filename)
    if match is None or match[1] in (".", ".."):
        raise MalformedFinqaRecord("invalid_filename")
    native_id = _text(raw.get("id"), "invalid_native_id")
    if not re.fullmatch(re.escape(filename) + r"-[0-9]+", native_id):
        raise MalformedFinqaRecord("id_filename_mismatch")
    qa = raw.get("qa")
    if not isinstance(qa, dict):
        raise MalformedFinqaRecord("invalid_qa")
    question = _text(qa.get("question"), "invalid_question")
    pre = _text_rows(raw.get("pre_text"), "invalid_pre_text")
    post = _text_rows(raw.get("post_text"), "invalid_post_text")
    original_rows = _table_rows(raw.get("table_ori"), "invalid_original_table")
    processed_rows = _table_rows(raw.get("table"), "invalid_processed_table")
    report_id = "finqa:report:" + match[1] + "/" + match[2]
    page_id = "finqa:page:" + filename
    task_id = "finqa:" + native_id
    page_version_id = "finqa:page-version:" + canonical_sha256(
        [filename, pre, post, original_rows, processed_rows]
    )
    original = Table(
        source_id=report_id,
        table_id="finqa:table:original:" + canonical_sha256([filename, original_rows]),
        rows=original_rows,
    )
    processed = Table(
        source_id=report_id,
        table_id="finqa:table:processed:" + canonical_sha256([filename, processed_rows]),
        rows=processed_rows,
    )
    passages: list[Passage] = []
    warnings: list[str] = []
    for segment, rows in (("pre_text", pre), ("post_text", post)):
        if not rows:
            continue
        if not any(s.strip() for s in rows):
            warnings.append("blank_" + segment + "_preserved_in_page")
            continue
        passages.append(
            Passage(
                source_id=report_id,
                passage_id="finqa:text:" + canonical_sha256([filename, segment, rows]),
                title=filename + ":" + segment,
                sentences=rows,
            )
        )
    if len({len(row) for row in original_rows}) > 1:
        warnings.append("ragged_original_table_preserved")
    if tuple(map(len, original_rows)) != tuple(map(len, processed_rows)):
        warnings.append("native_table_shapes_differ")
    answer_kind, execution_answer = _execution_answer(qa.get("exe_ans"))
    reported = qa.get("answer")
    if not isinstance(reported, str):
        reported = None
        warnings.append("missing_reported_answer")
    elif not reported.strip():
        warnings.append("empty_reported_answer")
    program = qa.get("program")
    if not isinstance(program, str) or not program.strip():
        program = None
        warnings.append("missing_program")
    reference = FinqaEvaluationReference(
        task_id=task_id,
        dataset_id="finqa",
        answers=(execution_answer,),
        answer_kind=answer_kind,
        execution_answer=execution_answer,
        reported_answer=reported,
        program=program,
        annotations={k: v for k, v in qa.items() if k != "question"},
    )
    return FinqaRecord(
        TaskInput(
            task_id=task_id,
            dataset_id="finqa",
            question=question,
            passages=tuple(passages),
            tables=(original,),
        ),
        reference,
        report_id,
        page_id,
        page_version_id,
        filename,
        pre,
        post,
        processed,
        tuple(warnings),
    )


def load_finqa_task(path: Path, task_id: str, *, split: str) -> TaskInput:
    """Read only checksummed model inputs; no evaluator table is selected."""
    with closing(read_only(path)) as connection:
        row = connection.execute(
            "SELECT input_json,content_sha256 FROM inputs WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized FinQA input was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized FinQA input checksum mismatch.")
    task = TaskInput.model_validate_json(row[0])
    if task.dataset_id != "finqa":
        raise ValueError("Normalized input does not belong to FinQA.")
    return task


def load_finqa_reference(path: Path, task_id: str, *, split: str) -> FinqaEvaluationReference:
    """Explicit evaluator-only load of gold execution/answer/program annotations."""
    with closing(read_only(path)) as connection:
        row = connection.execute(
            "SELECT reference_json,content_sha256 FROM evaluation_references "
            "WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized FinQA reference was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized FinQA reference checksum mismatch.")
    reference = FinqaEvaluationReference.model_validate_json(row[0])
    if reference.dataset_id != "finqa":
        raise ValueError("Normalized reference does not belong to FinQA.")
    return reference


def _insert_record(
    connection: sqlite3.Connection,
    raw: dict[str, Any],
    split: str,
    index: int,
    counts: Counter[str],
) -> None:
    counts["raw"] += 1
    raw_hash = canonical_sha256(raw)
    native_id = raw.get("id")
    previous = connection.execute(
        "SELECT raw_sha256 FROM provenance WHERE native_split=? AND task_id=?",
        (split, "finqa:" + native_id if isinstance(native_id, str) else ""),
    ).fetchone()
    reason: str | None = None
    if previous is not None:
        if previous[0] != raw_hash:
            raise ValueError(f"Conflicting FinQA task ID in {split} at raw index {index}.")
        reason = "duplicate_task_id"
    else:
        try:
            record = normalize_finqa_record(raw)
        except (MalformedFinqaRecord, ValidationError) as exc:
            reason = str(exc) if isinstance(exc, MalformedFinqaRecord) else "invalid_contract"
    if reason is not None:
        counts["duplicates" if reason == "duplicate_task_id" else "malformed"] += 1
        connection.execute(
            "INSERT INTO exclusions VALUES (?,?,?,?,?)",
            (split, index, native_id if isinstance(native_id, str) else None, raw_hash, reason),
        )
        return
    task = record.task
    for table, payload in (("inputs", task), ("evaluation_references", record.reference)):
        document = payload.model_dump(mode="json")
        connection.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?)",
            (split, task.task_id, canonical_json(document), canonical_sha256(document)),
        )
    connection.execute(
        "INSERT INTO provenance VALUES (?,?,?,?,?)",
        (split, task.task_id, index, raw_hash, canonical_json(record.warnings)),
    )
    for position, passage in enumerate(task.passages):
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
            "INSERT INTO task_sources VALUES (?,?,?,?)",
            (split, task.task_id, position, passage.passage_id),
        )
    for representation, table_model in (
        ("original", task.tables[0]),
        ("processed", record.processed_table),
    ):
        connection.execute(
            "INSERT OR IGNORE INTO table_versions VALUES (?,?,?,?,?,?)",
            (
                table_model.table_id,
                table_model.source_id,
                record.page_id,
                representation,
                canonical_json(table_model.rows),
                canonical_sha256(table_model.rows),
            ),
        )
    connection.execute(
        "INSERT INTO task_tables VALUES (?,?,?,?)",
        (split, task.task_id, 0, task.tables[0].table_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO page_versions VALUES (?,?,?,?,?,?,?,?)",
        (
            record.page_version_id,
            record.page_id,
            record.report_id,
            record.filename,
            canonical_json(record.pre_text),
            canonical_json(record.post_text),
            task.tables[0].table_id,
            record.processed_table.table_id,
        ),
    )
    connection.execute(
        "INSERT INTO native_locations VALUES (?,?,?,?,?,?)",
        (split, task.task_id, raw["id"], record.report_id, record.page_id, record.page_version_id),
    )
    counts["retained"] += 1
    counts["answer_type_" + record.reference.answer_kind] += 1
    for warning in record.warnings:
        counts[warning] += 1


def normalize_finqa(
    plan: AcquisitionDataset,
    raw_root: Path,
    output: Path,
    *,
    split: str = "all",
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Stream acquired JSON splits into an atomic, unpartitioned FinQA artifact."""
    selected = [s for s in plan.sources if split == "all" or split in s.splits]
    if (
        split not in ("all", "train", "dev", "test")
        or not selected
        or any(s.format != "json_array" or len(s.splits) != 1 for s in selected)
    ):
        raise ValueError(
            "FinQA normalization requires configured native train/dev/test JSON arrays."
        )
    directory = raw_root / "finqa" / plan.release
    manifest = AcquisitionManifest.model_validate_json(
        (directory / "acquisition.json").read_text("utf-8")
    )
    if (
        manifest.dataset != "finqa"
        or manifest.release != plan.release
        or manifest.source_plan != plan
        or manifest.plan_sha256 != canonical_sha256(plan.model_dump(mode="json"))
        or set(manifest.sources) != {s.filename for s in plan.sources}
    ):
        raise ValueError("FinQA acquisition provenance does not match the configured release.")
    bindings: dict[str, Any] = {}
    for source in selected:
        receipt = manifest.sources[source.filename]
        if receipt.status != "complete":
            raise ValueError(f"Acquire FinQA {source.splits[0]} before normalization.")
        _verify_file(directory / source.filename, receipt)
        if source.expected_sha256 not in (None, receipt.sha256) or source.expected_bytes not in (
            None,
            receipt.size_bytes,
        ):
            raise ValueError("FinQA receipt disagrees with pinned source bytes.")
        bindings[source.splits[0]] = {
            "filename": source.filename,
            "sha256": receipt.sha256,
            "size_bytes": receipt.size_bytes,
        }
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
        connection.executescript(STAGING_SQL + _FINQA_SQL)
        counts_by_split: dict[str, dict[str, int]] = {}
        for source in selected:
            native_split = source.splits[0]
            counts: Counter[str] = Counter(
                {
                    k: 0
                    for k in (
                        "raw",
                        "retained",
                        "duplicates",
                        "malformed",
                        "answer_type_number",
                        "answer_type_yes_no",
                        "empty_reported_answer",
                        "missing_reported_answer",
                        "missing_program",
                        "ragged_original_table_preserved",
                        "native_table_shapes_differ",
                        "blank_pre_text_preserved_in_page",
                        "blank_post_text_preserved_in_page",
                    )
                }
            )
            path = directory / source.filename
            emit(
                f"Normalizing FinQA {native_split}; preserving full text and original table cells."
            )
            with path.open(encoding="utf-8") as stream:
                for index, raw in enumerate(_json_records(stream)):
                    _insert_record(connection, raw, native_split, index, counts)
                    if counts["raw"] % 1000 == 0:
                        emit(f"FinQA {native_split}: {counts['raw']} raw records processed.")
            expected = manifest.sources[source.filename].counts.get(native_split)
            if expected is None or counts["raw"] != expected.records:
                raise ValueError("FinQA raw count differs from the acquisition receipt.")
            if _hash_file(path) != manifest.sources[source.filename].sha256:
                raise ValueError("FinQA raw source changed during normalization.")
            if counts["raw"] != counts["retained"] + counts["duplicates"] + counts["malformed"]:
                raise ValueError("FinQA normalization counts do not reconcile.")
            counts["report_identities"] = connection.execute(
                "SELECT COUNT(DISTINCT report_id) FROM native_locations WHERE native_split=?",
                (native_split,),
            ).fetchone()[0]
            counts["page_identities"] = connection.execute(
                "SELECT COUNT(DISTINCT page_id) FROM native_locations WHERE native_split=?",
                (native_split,),
            ).fetchone()[0]
            counts_by_split[native_split] = dict(counts)
        text_versions = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        model_tables = connection.execute(
            "SELECT COUNT(DISTINCT table_id) FROM task_tables"
        ).fetchone()[0]
        reports = connection.execute(
            "SELECT COUNT(DISTINCT report_id) FROM native_locations"
        ).fetchone()[0]
        metadata = {
            "schema_version": STAGING_SCHEMA,
            "adapter_version": ADAPTER_VERSION,
            "dataset": "finqa",
            "release": plan.release,
            "source_plan_sha256": manifest.plan_sha256,
            "model_table_representation": "table_ori",
            "sources": bindings,
            "counts": counts_by_split,
            "source_versions": text_versions + model_tables,
            "source_identities": reports,
            "text_versions": text_versions,
            "model_table_versions": model_tables,
            "table_versions": connection.execute("SELECT COUNT(*) FROM table_versions").fetchone()[
                0
            ],
            "page_versions": connection.execute("SELECT COUNT(*) FROM page_versions").fetchone()[0],
            "content_sha256": content_hash(connection, extra_tables=_EXTRA_TABLES),
        }
        metadata["normalization_id"] = "finqa:" + canonical_sha256(metadata)
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
                    raise ValueError("Existing normalized FinQA artifact checksum mismatch.")
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
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.close()
