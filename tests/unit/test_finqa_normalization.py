"""Full financial context, original cells, distinct targets and provenance boundaries."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import load_study_bundle
from workflow_reuse_orchestrator.data import finqa
from workflow_reuse_orchestrator.data.finqa import (
    FinqaEvaluationReference,
    load_finqa_reference,
    load_finqa_task,
    normalize_finqa,
    normalize_finqa_record,
)
from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionSource,
    acquire_dataset,
)
from workflow_reuse_orchestrator.domain.tasks import (
    CellEvidence,
    SentenceEvidence,
    resolve_evidence,
)
from workflow_reuse_orchestrator.storage import _WriterLock


def native(filename: str = "ACME/2020/page_10.pdf", index: int = 1) -> dict[str, Any]:
    return {
        "id": filename + "-" + str(index),
        "filename": filename,
        "pre_text": ["  Figures are in $ millions. ", "", "Sales increased 20%."],
        "post_text": ["  Original context after the table.\nSecond line. "],
        "table_ori": [
            ["", "Fiscal 2020", "Fiscal 2019"],
            ["Cash", "$1,234.50", "$(23,158)", "Original extra cell"],
        ],
        "table": [["", "fiscal 2020", "fiscal 2019"], ["cash", "1234.50", "-23158"]],
        "qa": {
            "question": "What changed?",
            "answer": "380",
            "exe_ans": 3.8,
            "program": "EVALUATOR_PROGRAM",
            "program_re": "EVALUATOR_NESTED_PROGRAM",
            "gold_inds": {"text_0": "GOLD_SELECTED_SECRET"},
            "model_input": [["text_0", "GOLD_SELECTED_SECRET"]],
            "tfidftopn": {"text_0": "RETRIEVAL_SECRET"},
            "ann_table_rows": [1],
            "ann_text_rows": [0],
            "steps": [],
            "explanation": "EVALUATOR_EXPLANATION",
        },
    }


def acquired(root: Path, **splits: list[dict[str, Any]]) -> AcquisitionDataset:
    bodies = {
        split: json.dumps(rows, ensure_ascii=False).encode() for split, rows in splits.items()
    }
    plan = AcquisitionDataset(
        release="fixture-v1",
        homepage="https://example.org/finqa",
        license="fixture",
        license_url="https://example.org/license",
        revision="fixture-v1",
        sources=[
            AcquisitionSource(
                filename=split + ".json",
                url="https://example.org/" + split,
                format="json_array",
                splits=[split],
            )
            for split in bodies
        ],
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=httpx.ByteStream(bodies[request.url.path[1:]])
            )
        )
    ) as client:
        acquire_dataset("finqa", plan, root, client=client)
    return plan


def test_original_table_cells_and_complete_text_round_trip_with_evidence() -> None:
    raw = native()
    record = normalize_finqa_record(raw)
    task = record.task
    assert task.task_id == "finqa:" + raw["id"]
    assert task.tables[0].rows == tuple(tuple(row) for row in raw["table_ori"])
    assert task.passages[0].sentences == tuple(raw["pre_text"])
    assert task.passages[1].sentences == tuple(raw["post_text"])
    assert record.processed_table.rows == tuple(tuple(row) for row in raw["table"])
    cell = CellEvidence(
        task_id=task.task_id,
        source_id=record.report_id,
        table_id=task.tables[0].table_id,
        row_index=1,
        column_index=2,
    )
    assert resolve_evidence(task, cell) == "$(23,158)"
    text = SentenceEvidence(
        task_id=task.task_id,
        source_id=record.report_id,
        passage_id=task.passages[0].passage_id,
        sentence_index=2,
    )
    assert resolve_evidence(task, text) == "Sales increased 20%."
    assert record.warnings == ("ragged_original_table_preserved", "native_table_shapes_differ")
    assert task.model_validate_json(task.model_dump_json()) == task


def test_reference_fields_and_retrieval_annotations_never_select_model_context() -> None:
    raw = native()
    expected = normalize_finqa_record(raw).task
    raw["qa"].update(
        {
            "exe_ans": 999,
            "answer": "REPORTED_SECRET",
            "program": "OTHER_PROGRAM",
            "gold_inds": {},
            "model_input": [],
        }
    )
    actual = normalize_finqa_record(raw).task
    assert actual == expected
    online = actual.model_dump_json()
    for secret in (
        "EVALUATOR_",
        "GOLD_SELECTED_SECRET",
        "RETRIEVAL_SECRET",
        "REPORTED_SECRET",
        "OTHER_PROGRAM",
        "gold_inds",
        "model_input",
        "exe_ans",
        "ann_table_rows",
    ):
        assert secret not in online


def test_execution_target_and_reported_answer_are_not_equivalent_alternatives() -> None:
    record = normalize_finqa_record(native())
    reference = record.reference
    assert reference.answers == ("3.8",)
    assert reference.execution_answer == "3.8"
    assert reference.reported_answer == "380"
    assert reference.answer_kind == "number"
    assert reference.annotations["exe_ans"] == 3.8
    assert reference.program == "EVALUATOR_PROGRAM"
    assert reference.annotation_table_representation == "table"
    with pytest.raises(ValueError, match="must not replace"):
        FinqaEvaluationReference.model_validate_json(
            json.dumps({**reference.model_dump(mode="json"), "answers": ["3.8", "380"]})
        )


@pytest.mark.parametrize(
    "execution,kind,text",
    [
        (0.0, "number", "0.0"),
        (-12.5, "number", "-12.5"),
        (42, "number", "42"),
        ("yes", "yes_no", "yes"),
        ("no", "yes_no", "no"),
        ("1e-5", "number", "1e-5"),
    ],
)
def test_execution_target_types_are_preserved(execution: Any, kind: str, text: str) -> None:
    raw = native()
    raw["qa"]["exe_ans"] = execution
    reference = normalize_finqa_record(raw).reference
    assert reference.answer_kind == kind
    assert reference.execution_answer == text
    assert reference.answers == (text,)


@pytest.mark.parametrize("execution", [None, True, "", "unknown", "NaN", "Infinity", float("nan")])
def test_invalid_execution_reference_is_not_replaced_by_reported_answer(execution: Any) -> None:
    raw = native()
    raw["qa"]["exe_ans"] = execution
    with pytest.raises(ValueError, match="invalid_execution_answer"):
        normalize_finqa_record(raw)


def test_empty_reported_answer_and_missing_program_retain_valid_execution_target() -> None:
    raw = native()
    raw["qa"]["answer"] = ""
    raw["qa"]["program"] = ""
    record = normalize_finqa_record(raw)
    assert record.reference.answers == ("3.8",)
    assert record.reference.reported_answer == ""
    assert record.reference.program is None
    assert "empty_reported_answer" in record.warnings
    assert "missing_program" in record.warnings
    assert record.reference.annotations["program"] == ""


def test_report_identity_links_pages_but_not_other_years_or_companies() -> None:
    first = normalize_finqa_record(native())
    next_page = normalize_finqa_record(native("ACME/2020/page_11.pdf"))
    next_year = normalize_finqa_record(native("ACME/2021/page_10.pdf"))
    other = normalize_finqa_record(native("OTHER/2020/page_10.pdf"))
    assert first.report_id == next_page.report_id
    assert first.page_id != next_page.page_id
    assert first.report_id != next_year.report_id != other.report_id
    assert all(p.source_id == first.report_id for p in first.task.passages)
    assert first.task.tables[0].source_id == first.report_id


def test_page_variant_tracks_processed_table_without_replacing_original_model_table() -> None:
    raw = native()
    first = normalize_finqa_record(raw)
    raw["table"][1][1] = "A changed processed cell"
    second = normalize_finqa_record(raw)
    assert first.task == second.task
    assert first.page_version_id != second.page_version_id
    assert first.processed_table.table_id != second.processed_table.table_id


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("filename", "../2020/page_1.pdf", "invalid_filename"),
        ("filename", "ACME/unknown/page_10.pdf", "invalid_filename"),
        ("id", "ACME/2020/page_99.pdf-1", "id_filename_mismatch"),
        ("qa", None, "invalid_qa"),
        ("pre_text", "flattened text", "invalid_pre_text"),
        ("post_text", [12], "invalid_post_text"),
        ("table_ori", [], "invalid_original_table"),
        ("table_ori", [["Header"], []], "invalid_original_table"),
        ("table_ori", [[1]], "invalid_original_table"),
        ("table", [[None]], "invalid_processed_table"),
    ],
)
def test_malformed_native_records_have_explicit_reasons(
    field: str, value: Any, reason: str
) -> None:
    raw = native()
    raw[field] = value
    with pytest.raises(ValueError, match=reason):
        normalize_finqa_record(raw)


def test_table_only_question_retains_blank_text_in_page_provenance() -> None:
    raw = native()
    raw["pre_text"] = ["", " "]
    raw["post_text"] = []
    record = normalize_finqa_record(raw)
    assert record.task.passages == ()
    assert record.pre_text == ("", " ")
    assert record.post_text == ()
    assert "blank_pre_text_preserved_in_page" in record.warnings
    assert record.task.tables


def test_staging_round_trip_reconciles_counts_tables_and_shared_report_groups(
    tmp_path: Path,
) -> None:
    bad = native(index=9)
    bad["qa"]["exe_ans"] = None
    plan = acquired(
        tmp_path / "raw",
        train=[native(), native(), bad],
        dev=[native("ACME/2020/page_11.pdf")],
        test=[native("OTHER/2021/page_12.pdf")],
    )
    output = tmp_path / "finqa.sqlite3"
    report = normalize_finqa(plan, tmp_path / "raw", output)
    counts = report["counts"]["train"]
    assert (counts["raw"], counts["retained"], counts["duplicates"], counts["malformed"]) == (
        3,
        1,
        1,
        1,
    )
    assert report["source_identities"] == 2
    assert report["table_versions"] == 6
    assert report["page_versions"] == 3
    task_id = "finqa:" + native()["id"]
    assert load_finqa_task(output, task_id, split="train") == normalize_finqa_record(native()).task
    assert (
        load_finqa_reference(output, task_id, split="train")
        == normalize_finqa_record(native()).reference
    )
    with closing(sqlite3.connect(output)) as connection:
        assert connection.execute(
            "SELECT reason FROM exclusions ORDER BY raw_index"
        ).fetchall() == [("duplicate_task_id",), ("invalid_execution_answer",)]
        stored = connection.execute(
            "SELECT rows_json FROM table_versions WHERE representation='original'"
        ).fetchone()
        assert json.loads(stored[0]) == native()["table_ori"]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    for flag in (
        "scientific_roles_assigned",
        "data_snapshot_available",
        "study_bindings_updated",
        "runtime_contacted",
    ):
        assert report[flag] is False
    before = output.read_bytes()
    repeated = normalize_finqa(plan, tmp_path / "raw", output)
    assert repeated["status"] == "verified_existing"
    assert repeated["normalization_id"] == report["normalization_id"]
    assert output.read_bytes() == before
    elsewhere = normalize_finqa(plan, tmp_path / "raw", tmp_path / "elsewhere.sqlite3")
    assert elsewhere["normalization_id"] == report["normalization_id"]


def test_conflicting_native_id_fails_without_publishing(tmp_path: Path) -> None:
    changed = native()
    changed["qa"]["answer"] = "A different reported answer"
    plan = acquired(tmp_path / "raw", train=[native(), changed])
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "finqa.sqlite3")
    assert not (tmp_path / "finqa.sqlite3").exists()
    assert not list(tmp_path.glob("*.tmp*"))


def test_changed_raw_and_wrong_release_plan_are_rejected(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    with pytest.raises(ValueError, match="provenance"):
        normalize_finqa(
            plan.model_copy(update={"revision": "other"}),
            tmp_path / "raw",
            tmp_path / "finqa.sqlite3",
        )
    path = tmp_path / "raw/finqa/fixture-v1/train.json"
    path.write_bytes(path.read_bytes().replace(b"Fiscal", b"FISCAL"))
    with pytest.raises(ValueError, match="checksum"):
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "absent/finqa.sqlite3")
    assert not (tmp_path / "absent").exists()


def test_raw_counts_must_match_acquisition_receipt(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    path = tmp_path / "raw/finqa/fixture-v1/acquisition.json"
    manifest = json.loads(path.read_text())
    manifest["sources"]["train.json"]["counts"]["train"]["records"] += 1
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="raw count differs"):
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "finqa.sqlite3")
    assert not (tmp_path / "finqa.sqlite3").exists()


def test_partial_native_acquisition_can_normalize_only_its_completed_split(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", dev=[native()])
    assert (
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "dev.sqlite3", split="dev")["counts"][
            "dev"
        ]["retained"]
        == 1
    )
    with pytest.raises(ValueError, match="requires configured"):
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "train.sqlite3", split="train")
    assert not (tmp_path / "train.sqlite3").exists()


def test_output_collision_and_native_table_corruption_never_replace_output(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", train=[native()], test=[native(index=2)])
    output = tmp_path / "finqa.sqlite3"
    normalize_finqa(plan, tmp_path / "raw", output, split="train")
    before = output.read_bytes()
    with pytest.raises(ValueError, match="different normalization"):
        normalize_finqa(plan, tmp_path / "raw", output)
    assert output.read_bytes() == before
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("UPDATE table_versions SET rows_json='[]'")
        connection.commit()
    with pytest.raises(ValueError, match="checksum"):
        normalize_finqa(plan, tmp_path / "raw", output, split="train")


@pytest.mark.parametrize(
    "table,loader,column",
    [
        ("inputs", load_finqa_task, "input_json"),
        ("evaluation_references", load_finqa_reference, "reference_json"),
    ],
)
def test_read_only_loaders_reject_corrupt_payloads(
    tmp_path: Path, table: str, loader: Any, column: str
) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    output = tmp_path / "finqa.sqlite3"
    normalize_finqa(plan, tmp_path / "raw", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.execute(f"UPDATE {table} SET {column}='{{}}'")
        connection.commit()
    with pytest.raises(ValueError, match="checksum"):
        loader(output, "finqa:" + native()["id"], split="train")


def test_online_loader_never_reads_evaluation_reference_table(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    output = tmp_path / "finqa.sqlite3"
    normalize_finqa(plan, tmp_path / "raw", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("DROP TABLE evaluation_references")
        connection.commit()
    assert load_finqa_task(output, "finqa:" + native()["id"], split="train").dataset_id == "finqa"


def test_raw_output_and_concurrent_writer_are_rejected(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    with pytest.raises(ValueError, match="immutable raw"):
        normalize_finqa(plan, tmp_path / "raw", tmp_path / "raw/finqa/out.db")
    lock = _WriterLock(tmp_path / "finqa.sqlite3.lock")
    try:
        with pytest.raises(ValueError, match="locked"):
            normalize_finqa(plan, tmp_path / "raw", tmp_path / "finqa.sqlite3")
    finally:
        lock.close()


def test_interruption_preserves_existing_artifact_and_cleans_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = acquired(tmp_path / "raw", train=[native()])
    output = tmp_path / "finqa.sqlite3"
    normalize_finqa(plan, tmp_path / "raw", output)
    before = output.read_bytes()

    def fail(*args: Any) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(finqa, "_insert_record", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        normalize_finqa(plan, tmp_path / "raw", output)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp*"))


def test_cli_accepts_finqa_test_split_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = acquired(tmp_path / "raw", test=[native()])
    bundle = load_study_bundle()
    assert bundle.datasets.acquisition is not None
    catalog = bundle.datasets.acquisition.model_copy(update={"finqa": plan})
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
                "finqa",
                "--split",
                "test",
                "--raw-root",
                str(tmp_path / "raw"),
                "--output",
                str(tmp_path / "finqa.sqlite3"),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["dataset"] == "finqa" and report["counts"]["test"]["retained"] == 1
    assert report["model_table_representation"] == "table_ori"
    assert report["runtime_contacted"] is False
