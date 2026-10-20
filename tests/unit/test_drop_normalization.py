"""DROP answer groups, native identity collisions, source sharing and publication."""

import io
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import load_study_bundle
from workflow_reuse_orchestrator.data import drop
from workflow_reuse_orchestrator.data.drop import (
    DropAnswer,
    load_drop_reference,
    load_drop_task,
    normalize_drop,
    normalize_drop_record,
)
from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionSource,
    _json_records,
    acquire_dataset,
)
from workflow_reuse_orchestrator.domain.tasks import SentenceEvidence, resolve_evidence
from workflow_reuse_orchestrator.storage import _WriterLock

PASSAGE = "  Revenue was €1,234.50.\nA second line preserves 20% and 1998\u20131999. "


def answer(number: str = "", spans: list[str] | None = None, **date: str) -> dict[str, Any]:
    return {
        "number": number,
        "spans": spans or [],
        "date": {"day": "", "month": "", "year": "", **date},
    }


def question(query_id: str = "q1", value: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "question": "What was the revenue?",
        "answer": value if value is not None else answer(number="1,234.50"),
    }


def acquired(
    root: Path, train: dict[str, Any], dev: dict[str, Any] | None = None
) -> AcquisitionDataset:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for split, rows in (("train", train), ("dev", dev if dev is not None else train)):
            archive.writestr("drop_dataset/drop_dataset_" + split + ".json", json.dumps(rows))
        archive.writestr("../../never-extract.txt", "outside")
    plan = AcquisitionDataset(
        release="fixture-v1",
        homepage="https://example.org/drop",
        license="fixture",
        license_url="https://example.org/license",
        revision="fixture-v1",
        sources=[
            AcquisitionSource(
                filename="drop.zip",
                url="https://example.org/drop.zip",
                format="drop_zip",
                splits=["train", "dev"],
            )
        ],
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, stream=httpx.ByteStream(buffer.getvalue()))
        )
    ) as client:
        acquire_dataset("drop", plan, root, client=client)
    return plan


def document(*questions: dict[str, Any]) -> dict[str, Any]:
    return {"nfl_1": {"passage": PASSAGE, "qa_pairs": list(questions)}}


@pytest.mark.parametrize(
    "value,kind,values",
    [
        (answer(number="1,234.50"), "number", ("1,234.50",)),
        (answer(spans=["€1,234.50"]), "span", ("€1,234.50",)),
        (answer(spans=["North", "South"]), "spans", ("North", "South")),
        (answer(day="12", month="March", year="1998"), "date", ("12 March 1998",)),
        (answer(year="1998"), "date", ("1998",)),
    ],
)
def test_typed_answers_preserve_values_and_full_native_passage(
    value: dict[str, Any], kind: str, values: tuple[str, ...]
) -> None:
    raw = question(value=value)
    record = normalize_drop_record("nfl_1", PASSAGE, raw)
    group = record.reference.answer_groups[0]
    assert group.kind == kind and group.values == values
    assert record.reference.annotations["answer"] == value
    if kind == "date":
        assert group.date_parts == value["date"]
    if kind == "spans":
        assert record.reference.answers == ('["North","South"]',)
        assert len(record.reference.answer_groups) == 1
    passage = record.task.passages[0]
    assert passage.sentences == (PASSAGE,)
    evidence = SentenceEvidence(
        task_id=record.task.task_id,
        source_id=passage.source_id,
        passage_id=passage.passage_id,
        sentence_index=0,
    )
    assert resolve_evidence(record.task, evidence) == PASSAGE
    assert "answer" not in record.task.model_dump_json()
    assert "validated_answers" not in record.task.model_dump_json()


def test_validated_answers_remain_separate_complete_groups() -> None:
    qa = question(value=answer(spans=["PRIMARY_SECRET", "SECOND_SECRET"]))
    qa["validated_answers"] = [answer(number="42"), answer(year="1999")]
    qa["native_annotation"] = "EVALUATOR_ONLY"
    record = normalize_drop_record("nfl_1", PASSAGE, qa)
    assert [g.kind for g in record.reference.answer_groups] == ["spans", "number", "date"]
    assert [g.origin for g in record.reference.answer_groups] == [
        "answer",
        "validated_answers",
        "validated_answers",
    ]
    assert record.reference.annotations["validated_answers"] == qa["validated_answers"]
    online = record.task.model_dump_json()
    for secret in ("PRIMARY_SECRET", "SECOND_SECRET", "EVALUATOR_ONLY", "answer_groups"):
        assert secret not in online


@pytest.mark.parametrize(
    "annotation",
    [
        {"number": "3", "spans": [], "date": {}},
        {"number": "", "spans": ["A native span"], "date": {}},
        {"number": "", "spans": [], "date": {"year": "1998"}},
    ],
)
def test_native_empty_and_partial_date_mappings_do_not_discard_valid_answers(
    annotation: dict[str, Any],
) -> None:
    record = normalize_drop_record("nfl_1", PASSAGE, question(value=annotation))
    assert len(record.reference.answer_groups) == 1
    assert not record.warnings
    assert record.reference.annotations["answer"] == annotation


def test_empty_primary_can_use_validated_answer_without_changing_input() -> None:
    qa = question(value=answer())
    qa["validated_answers"] = [answer(), answer(number="3")]
    record = normalize_drop_record("nfl_1", PASSAGE, qa)
    assert record.reference.answer_groups[0].values == ("3",)
    assert "empty_answer_annotation" in record.warnings
    qa["answer"] = answer(number="7")
    assert normalize_drop_record("nfl_1", PASSAGE, qa).task == record.task


def test_ambiguous_native_fields_follow_upstream_precedence_and_keep_raw() -> None:
    qa = question(value=answer(number="26", year="1980"))
    record = normalize_drop_record("nfl_1", PASSAGE, qa)
    assert record.reference.answer_groups[0].kind == "number"
    assert record.reference.answer_groups[0].values == ("26",)
    assert record.reference.annotations["answer"]["date"]["year"] == "1980"
    assert record.warnings == ("multiple_answer_fields",)


@pytest.mark.parametrize(
    "primary", [None, {}, answer(), {"number": 3}, {"spans": [""]}, {"date": {"year": 1998}}]
)
def test_no_usable_answer_is_an_explicit_exclusion(primary: Any) -> None:
    qa = question()
    qa["answer"] = primary
    with pytest.raises(ValueError, match="no_usable_answers"):
        normalize_drop_record("nfl_1", PASSAGE, qa)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("query_id", "", "invalid_query_id"),
        ("query_id", " q1", "invalid_query_id"),
        ("question", " ", "invalid_question"),
        ("question", 12, "invalid_question"),
    ],
)
def test_malformed_question_has_a_stable_reason(field: str, value: Any, reason: str) -> None:
    qa = question()
    qa[field] = value
    with pytest.raises(ValueError, match=reason):
        normalize_drop_record("nfl_1", PASSAGE, qa)


def test_native_query_id_reuse_is_disambiguated_using_only_input_fields() -> None:
    qa = question()
    first = normalize_drop_record("nfl_1", PASSAGE, qa)
    qa["question"] += "/"
    second = normalize_drop_record("nfl_1", PASSAGE, qa)
    assert first.task.task_id != second.task.task_id
    assert first.task.passages == second.task.passages
    qa["answer"] = answer(number="200")
    assert normalize_drop_record("nfl_1", PASSAGE, qa).task.task_id == second.task.task_id


def test_staging_reconciles_questions_exclusions_and_shared_sources(tmp_path: Path) -> None:
    reused = question()
    reused["question"] += "/"
    plan = acquired(
        tmp_path / "raw",
        document(question(), question(), reused, question("empty", answer())),
        document(question("dev", answer(spans=["A", "B"]))),
    )
    output = tmp_path / "drop.sqlite3"
    report = normalize_drop(plan, tmp_path / "raw", output)
    train = report["counts"]["train"]
    assert (
        train["raw_passages"],
        train["raw"],
        train["retained"],
        train["duplicates"],
        train["malformed"],
        train["reused_native_query_ids"],
    ) == (1, 4, 2, 1, 1, 1)
    assert report["source_identities"] == report["source_versions"] == 1
    assert report["counts"]["dev"]["answer_type_spans"] == 1
    task_id = normalize_drop_record("nfl_1", PASSAGE, question()).task.task_id
    assert load_drop_task(output, task_id, split="train").passages[0].sentences == (PASSAGE,)
    assert load_drop_reference(output, task_id, split="train").answer_groups[0].values == (
        "1,234.50",
    )
    with closing(sqlite3.connect(output)) as connection:
        assert connection.execute(
            "SELECT reason FROM exclusions ORDER BY raw_index"
        ).fetchall() == [("duplicate_task",), ("no_usable_answers",)]
        assert connection.execute("SELECT COUNT(*) FROM native_locations").fetchone()[0] == 3
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not (tmp_path / "never-extract.txt").exists()
    for flag in (
        "scientific_roles_assigned",
        "data_snapshot_available",
        "study_bindings_updated",
        "runtime_contacted",
    ):
        assert report[flag] is False
    before = output.read_bytes()
    repeated = normalize_drop(plan, tmp_path / "raw", output)
    assert repeated["status"] == "verified_existing"
    assert repeated["normalization_id"] == report["normalization_id"]
    assert output.read_bytes() == before
    elsewhere = normalize_drop(plan, tmp_path / "raw", tmp_path / "elsewhere.sqlite3")
    assert elsewhere["normalization_id"] == report["normalization_id"]


def test_conflicting_annotation_for_same_input_is_not_silently_overwritten(tmp_path: Path) -> None:
    changed = question(value=answer(number="400"))
    plan = acquired(tmp_path / "raw", document(question(), changed))
    output = tmp_path / "drop.sqlite3"
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_drop(plan, tmp_path / "raw", output)
    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp*"))


def test_wrong_source_plan_and_changed_raw_archive_fail_before_publication(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    with pytest.raises(ValueError, match="provenance"):
        normalize_drop(
            plan.model_copy(update={"revision": "other"}),
            tmp_path / "raw",
            tmp_path / "drop.sqlite3",
        )
    path = tmp_path / "raw/drop/fixture-v1/drop.zip"
    data = path.read_bytes()
    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError, match="checksum"):
        normalize_drop(plan, tmp_path / "raw", tmp_path / "absent/drop.sqlite3")
    assert not (tmp_path / "absent").exists()


def test_raw_counts_in_receipt_must_reconcile(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    path = tmp_path / "raw/drop/fixture-v1/acquisition.json"
    state = json.loads(path.read_text())
    state["sources"]["drop.zip"]["counts"]["train"]["questions"] += 1
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="raw counts differ"):
        normalize_drop(plan, tmp_path / "raw", tmp_path / "drop.sqlite3")
    assert not (tmp_path / "drop.sqlite3").exists()


def test_output_collisions_and_corruption_preserve_existing_file(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    output = tmp_path / "drop.sqlite3"
    normalize_drop(plan, tmp_path / "raw", output, split="dev")
    before = output.read_bytes()
    with pytest.raises(ValueError, match="different normalization"):
        normalize_drop(plan, tmp_path / "raw", output)
    assert output.read_bytes() == before
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("UPDATE native_locations SET question_index=999")
        connection.commit()
    with pytest.raises(ValueError, match="checksum"):
        normalize_drop(plan, tmp_path / "raw", output, split="dev")


@pytest.mark.parametrize(
    "table,loader", [("inputs", load_drop_task), ("evaluation_references", load_drop_reference)]
)
def test_loaders_detect_corrupted_payloads(tmp_path: Path, table: str, loader: Any) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    output = tmp_path / "drop.sqlite3"
    normalize_drop(plan, tmp_path / "raw", output)
    task_id = normalize_drop_record("nfl_1", PASSAGE, question()).task.task_id
    with closing(sqlite3.connect(output)) as connection:
        column = "input_json" if table == "inputs" else "reference_json"
        connection.execute(f"UPDATE {table} SET {column}='{{}}'")
        connection.commit()
    with pytest.raises(ValueError, match="checksum"):
        loader(output, task_id, split="train")


def test_online_loader_does_not_access_reference_table(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    output = tmp_path / "drop.sqlite3"
    normalize_drop(plan, tmp_path / "raw", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("DROP TABLE evaluation_references")
        connection.commit()
    task_id = normalize_drop_record("nfl_1", PASSAGE, question()).task.task_id
    assert load_drop_task(output, task_id, split="train").dataset_id == "drop"


def test_raw_output_and_concurrent_writer_are_rejected(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    with pytest.raises(ValueError, match="immutable raw"):
        normalize_drop(plan, tmp_path / "raw", tmp_path / "raw/drop/fixture-v1/out.db")
    lock = _WriterLock(tmp_path / "drop.sqlite3.lock")
    try:
        with pytest.raises(ValueError, match="locked"):
            normalize_drop(plan, tmp_path / "raw", tmp_path / "drop.sqlite3")
    finally:
        lock.close()


def test_mapping_parser_preserves_keys_and_never_overwrites_native_fields() -> None:
    assert list(
        _json_records(io.StringIO('{"p1":{"passage":"Text"}}'), mapping=True, key_field="_key")
    ) == [{"passage": "Text", "_key": "p1"}]
    with pytest.raises(ValueError, match="cannot replace"):
        list(_json_records(io.StringIO('{"p1":{"_key":"native"}}'), mapping=True, key_field="_key"))


def test_answer_model_rejects_flattened_or_inconsistent_groups() -> None:
    with pytest.raises(ValueError, match="typed value shape"):
        DropAnswer(kind="number", values=("1", "2"), origin="answer", annotation_index=0)
    with pytest.raises(ValueError, match="native components"):
        DropAnswer(
            kind="date",
            values=("1998",),
            date_parts={"day": "", "month": "", "year": "1999"},
            origin="answer",
            annotation_index=0,
        )


def test_cli_selects_drop_normalization_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    bundle = load_study_bundle()
    assert bundle.datasets.acquisition is not None
    catalog = bundle.datasets.acquisition.model_copy(update={"drop": plan})
    bundle = bundle.model_copy(
        update={"datasets": bundle.datasets.model_copy(update={"acquisition": catalog})}
    )
    monkeypatch.setattr("workflow_reuse_orchestrator.cli.load_study_bundle", lambda config: bundle)
    assert (
        main(
            [
                "data",
                "normalize",
                "--dataset",
                "drop",
                "--split",
                "dev",
                "--raw-root",
                str(tmp_path / "raw"),
                "--output",
                str(tmp_path / "drop.sqlite3"),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["dataset"] == "drop" and report["counts"]["dev"]["retained"] == 1
    assert report["runtime_contacted"] is False


def test_exception_during_normalization_never_replaces_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = acquired(tmp_path / "raw", document(question()))
    output = tmp_path / "drop.sqlite3"
    normalize_drop(plan, tmp_path / "raw", output)
    before = output.read_bytes()

    def fail(*args: Any) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(drop, "_insert_question", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        normalize_drop(plan, tmp_path / "raw", output)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp*"))
