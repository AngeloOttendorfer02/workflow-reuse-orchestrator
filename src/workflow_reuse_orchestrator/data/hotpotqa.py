"""Lossless HotpotQA distractor adapter and offline, unpartitioned staging artifact."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unicodedata
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import JsonValue, ValidationError

from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionManifest,
    Progress,
    _hash_file,
    _json_records,
    _verify_file,
)
from workflow_reuse_orchestrator.data.staging import (
    STAGING_SQL as _SCHEMA,
)
from workflow_reuse_orchestrator.data.staging import (
    content_hash as _content_hash,
)
from workflow_reuse_orchestrator.data.staging import (
    read_only as _read_only,
)
from workflow_reuse_orchestrator.domain.tasks import (
    EvaluationReference,
    Passage,
    SentenceEvidence,
    TaskInput,
)
from workflow_reuse_orchestrator.storage import _WriterLock, canonical_json, canonical_sha256

ADAPTER_VERSION = "hotpotqa-distractor-v1"
STAGING_SCHEMA = "hotpotqa-staging-v1"


class MalformedHotpotRecord(ValueError):
    """A stable exclusion reason, without embedding raw reference text in logs."""


@dataclass(frozen=True)
class HotpotRecord:
    task: TaskInput
    reference: EvaluationReference
    warnings: tuple[str, ...]


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedHotpotRecord(reason)
    return value


def normalize_hotpotqa_record(raw: dict[str, Any]) -> HotpotRecord:
    """Preserve all context; support labels never choose or reorder paragraphs."""
    native_id = _text(raw.get("_id"), "invalid_native_id")
    if native_id != native_id.strip():
        raise MalformedHotpotRecord("invalid_native_id")
    task_id = "hotpotqa:" + native_id
    question = _text(raw.get("question"), "invalid_question")
    answer = _text(raw.get("answer"), "invalid_answer")
    context = raw.get("context")
    if not isinstance(context, list) or not context:
        raise MalformedHotpotRecord("invalid_context")
    passages: list[Passage] = []
    by_title: dict[str, Passage] = {}
    source_ids: set[str] = set()
    for paragraph in context:
        if not isinstance(paragraph, list) or len(paragraph) != 2:
            raise MalformedHotpotRecord("invalid_paragraph")
        title = _text(paragraph[0], "invalid_title")
        sentences = paragraph[1]
        if (
            not isinstance(sentences, list)
            or not sentences
            or any(not isinstance(s, str) for s in sentences)
            or not any(s.strip() for s in sentences)
        ):
            raise MalformedHotpotRecord("invalid_sentences")
        # Title identity links article variants; exact text hashes expose duplicates.
        article = " ".join(unicodedata.normalize("NFC", title).replace("_", " ").split())
        source_id = "hotpotqa:article:" + canonical_sha256(article)
        if source_id in source_ids:
            raise MalformedHotpotRecord("duplicate_context_title")
        source_ids.add(source_id)
        passage = Passage(
            source_id=source_id,
            passage_id="hotpotqa:paragraph:" + canonical_sha256([title, sentences]),
            title=title,
            sentences=tuple(sentences),
        )
        passages.append(passage)
        by_title[title] = passage
    warnings: list[str] = []
    if any(not s.strip() for p in passages for s in p.sentences):
        warnings.append("blank_sentence_slots_preserved")
    support = raw.get("supporting_facts")
    resolved: list[JsonValue] = []
    unresolved: list[Any] = []
    if not isinstance(support, list) or not support:
        warnings.append("invalid_support_annotations")
    else:
        for fact in support:
            if (
                not isinstance(fact, list)
                or len(fact) != 2
                or not isinstance(fact[0], str)
                or type(fact[1]) is not int
                or fact[0] not in by_title
                or not 0 <= fact[1] < len(by_title[fact[0]].sentences)
            ):
                unresolved.append(fact)
                continue
            passage = by_title[fact[0]]
            resolved.append(
                SentenceEvidence(
                    task_id=task_id,
                    source_id=passage.source_id,
                    passage_id=passage.passage_id,
                    sentence_index=fact[1],
                ).model_dump(mode="json")
            )
        if unresolved:
            warnings.append("unresolved_support_annotations")
    task = TaskInput(
        task_id=task_id, dataset_id="hotpotqa", question=question, passages=tuple(passages)
    )
    reference = EvaluationReference(
        task_id=task_id,
        dataset_id="hotpotqa",
        answers=(answer,),
        annotations={
            "supporting_facts": support,
            "resolved_support": resolved,
            "unresolved_support": unresolved,
            "native_type": raw.get("type"),
            "native_level": raw.get("level"),
        },
    )
    return HotpotRecord(task, reference, tuple(warnings))


def load_hotpotqa_task(path: Path, task_id: str, *, split: str) -> TaskInput:
    """Read input only; no evaluator table is selected by this loader."""
    with closing(_read_only(path)) as connection:
        row = connection.execute(
            "SELECT input_json,content_sha256 FROM inputs WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized HotpotQA input was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized HotpotQA input checksum mismatch.")
    return TaskInput.model_validate_json(row[0])


def load_hotpotqa_reference(path: Path, task_id: str, *, split: str) -> EvaluationReference:
    """Explicit evaluator-only access; callers must enforce scientific roles later."""
    with closing(_read_only(path)) as connection:
        row = connection.execute(
            "SELECT reference_json,content_sha256 FROM evaluation_references "
            "WHERE native_split=? AND task_id=?",
            (split, task_id),
        ).fetchone()
    if row is None:
        raise ValueError("Normalized HotpotQA reference was not found.")
    if canonical_sha256(json.loads(row[0])) != row[1]:
        raise ValueError("Normalized HotpotQA reference checksum mismatch.")
    return EvaluationReference.model_validate_json(row[0])


def _insert_record(
    connection: sqlite3.Connection,
    raw: dict[str, Any],
    split: str,
    index: int,
    counts: Counter[str],
) -> None:
    counts["raw"] += 1
    raw_hash = canonical_sha256(raw)
    native_id = raw.get("_id")
    # A repeated ID is harmless only if the entire native record is identical.
    previous = connection.execute(
        "SELECT raw_sha256 FROM provenance WHERE native_split=? AND task_id=?",
        (split, "hotpotqa:" + native_id if isinstance(native_id, str) else ""),
    ).fetchone()
    reason: str | None = None
    if previous is not None:
        if previous[0] != raw_hash:
            raise ValueError(f"Conflicting HotpotQA task ID in {split} at raw index {index}.")
        reason = "duplicate_task_id"
    else:
        try:
            record = normalize_hotpotqa_record(raw)
        except (MalformedHotpotRecord, ValidationError) as exc:
            reason = str(exc) if isinstance(exc, MalformedHotpotRecord) else "invalid_contract"
    if reason is not None:
        counts["duplicates" if reason == "duplicate_task_id" else "malformed"] += 1
        connection.execute(
            "INSERT INTO exclusions VALUES (?,?,?,?,?)",
            (split, index, native_id if isinstance(native_id, str) else None, raw_hash, reason),
        )
        return
    task = record.task
    connection.execute(
        "INSERT INTO inputs VALUES (?,?,?,?)",
        (
            split,
            task.task_id,
            canonical_json(task.model_dump(mode="json")),
            canonical_sha256(task.model_dump(mode="json")),
        ),
    )
    connection.execute(
        "INSERT INTO evaluation_references VALUES (?,?,?,?)",
        (
            split,
            task.task_id,
            canonical_json(record.reference.model_dump(mode="json")),
            canonical_sha256(record.reference.model_dump(mode="json")),
        ),
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
    counts["retained"] += 1
    counts["with_annotation_warnings"] += int(any("support" in w for w in record.warnings))
    counts["with_blank_sentence_slots"] += int("blank_sentence_slots_preserved" in record.warnings)


def normalize_hotpotqa(
    plan: AcquisitionDataset,
    raw_root: Path,
    output: Path,
    *,
    split: str = "all",
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Verify C06 receipts, stream native records, atomically publish a staging DB.

    This artifact has no scientific assignments and is not a C12 frozen snapshot.
    """
    selected = [s for s in plan.sources if split == "all" or split in s.splits]
    if not selected or any(s.format != "json_array" or len(s.splits) != 1 for s in selected):
        raise ValueError("HotpotQA normalization requires configured native JSON array splits.")
    if any(s.splits[0] not in ("train", "dev") for s in selected):
        raise ValueError("Only labeled HotpotQA train/dev distractor splits are supported.")
    directory = raw_root / "hotpotqa" / plan.release
    manifest = AcquisitionManifest.model_validate_json(
        (directory / "acquisition.json").read_text("utf-8")
    )
    if (
        manifest.dataset != "hotpotqa"
        or manifest.release != plan.release
        or manifest.source_plan != plan
        or manifest.plan_sha256 != canonical_sha256(plan.model_dump(mode="json"))
        or set(manifest.sources) != {s.filename for s in plan.sources}
    ):
        raise ValueError("HotpotQA acquisition provenance does not match the configured release.")
    bindings: dict[str, Any] = {}
    for source in selected:
        receipt = manifest.sources[source.filename]
        if receipt.status != "complete":
            raise ValueError(f"Acquire HotpotQA {source.splits[0]} before normalization.")
        _verify_file(directory / source.filename, receipt)
        if source.expected_sha256 not in (None, receipt.sha256) or source.expected_bytes not in (
            None,
            receipt.size_bytes,
        ):
            raise ValueError("HotpotQA receipt disagrees with pinned source bytes.")
        bindings[source.splits[0]] = {
            "filename": source.filename,
            "sha256": receipt.sha256,
            "size_bytes": receipt.size_bytes,
        }
    output = output.resolve()
    if output == raw_root.resolve() or raw_root.resolve() in output.parents:
        raise ValueError("Normalization output must not be inside the immutable raw release.")
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
        connection.executescript(_SCHEMA)
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
                        "with_annotation_warnings",
                        "with_blank_sentence_slots",
                    )
                }
            )
            path = directory / source.filename
            emit(f"Normalizing HotpotQA {native_split}; preserving every supplied paragraph.")
            with path.open(encoding="utf-8") as stream:
                for index, raw in enumerate(_json_records(stream)):
                    _insert_record(connection, raw, native_split, index, counts)
                    if counts["raw"] % 5000 == 0:
                        emit(f"HotpotQA {native_split}: {counts['raw']} raw records processed.")
            receipt = manifest.sources[source.filename]
            expected = receipt.counts.get(native_split)
            if expected is None or counts["raw"] != expected.records:
                raise ValueError("Normalized raw count differs from the acquisition receipt.")
            if _hash_file(path) != receipt.sha256:
                raise ValueError("HotpotQA raw bytes changed during normalization.")
            if counts["raw"] != counts["retained"] + counts["duplicates"] + counts["malformed"]:
                raise ValueError("HotpotQA normalization counts do not reconcile.")
            counts_by_split[native_split] = dict(counts)
        metadata = {
            "schema_version": STAGING_SCHEMA,
            "adapter_version": ADAPTER_VERSION,
            "dataset": "hotpotqa",
            "release": plan.release,
            "source_plan_sha256": manifest.plan_sha256,
            "sources": bindings,
            "counts": counts_by_split,
            "source_versions": connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "source_identities": connection.execute(
                "SELECT COUNT(DISTINCT source_id) FROM sources"
            ).fetchone()[0],
            "content_sha256": _content_hash(connection),
        }
        metadata["normalization_id"] = "hotpotqa:" + canonical_sha256(metadata)
        connection.execute(
            "INSERT INTO metadata VALUES (?,?)", ("manifest", canonical_json(metadata))
        )
        connection.commit()
        connection.close()
        connection = None
        status = "normalized"
        if output.exists():
            with closing(_read_only(output)) as existing:
                row = existing.execute(
                    "SELECT value_json FROM metadata WHERE key='manifest'"
                ).fetchone()
                if row is None or json.loads(row[0]) != metadata:
                    raise ValueError(
                        "Output already holds different normalization; choose a new output."
                    )
                if _content_hash(existing) != metadata["content_sha256"]:
                    raise ValueError("Existing normalized artifact checksum mismatch.")
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
