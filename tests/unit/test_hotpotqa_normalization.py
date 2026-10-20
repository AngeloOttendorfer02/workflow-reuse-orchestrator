"""Native context, evaluator isolation, provenance and atomic staging boundaries."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import load_study_bundle
from workflow_reuse_orchestrator.data import hotpotqa
from workflow_reuse_orchestrator.data.hotpotqa import (
    load_hotpotqa_reference,
    load_hotpotqa_task,
    normalize_hotpotqa,
    normalize_hotpotqa_record,
)
from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionSource,
    acquire_dataset,
)
from workflow_reuse_orchestrator.domain.tasks import Passage, SentenceEvidence, resolve_evidence
from workflow_reuse_orchestrator.storage import _WriterLock


def native(native_id: str = "q1") -> dict[str, Any]:
    return {
        "_id": native_id,
        "question": "Which country do both people come from?",
        "context": [
            ["Distractor", ["Nothing selected by the gold facts."]],
            ["First Person", ["A first sentence.", "", "  A native €1,234.50 sentence. "]],
            ["Second Person", ["Another sentence."]],
        ],
        "answer": "REFERENCE_ONLY_ANSWER",
        "supporting_facts": [["First Person", 2], ["Second Person", 0]],
        "type": "comparison",
        "level": "hard",
    }


def acquired(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    dev: list[dict[str, Any]] | None = None,
) -> AcquisitionDataset:
    bodies = {"train": json.dumps(rows, ensure_ascii=False).encode()}
    if dev is not None:
        bodies["dev"] = json.dumps(dev, ensure_ascii=False).encode()
    plan = AcquisitionDataset(
        release="fixture-v1",
        homepage="https://example.org/hotpotqa",
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
                200, stream=httpx.ByteStream(bodies[request.url.path.strip("/")])
            )
        )
    ) as client:
        acquire_dataset("hotpotqa", plan, root, client=client)
    return plan


def test_preserves_distractors_formatting_blank_slots_and_evidence() -> None:
    raw = native()
    record = normalize_hotpotqa_record(raw)
    assert record.task.task_id == "hotpotqa:q1"
    assert record.task.question == raw["question"]
    assert [[p.title, list(p.sentences)] for p in record.task.passages] == raw["context"]
    assert len(record.task.passages) == 3
    assert record.warnings == ("blank_sentence_slots_preserved",)
    reference = record.reference
    assert reference.answers == (raw["answer"],)
    assert reference.annotations["supporting_facts"] == raw["supporting_facts"]
    facts = reference.annotations["resolved_support"]
    assert isinstance(facts, list)
    first = SentenceEvidence.model_validate(facts[0])
    assert first.sentence_index == 2
    assert resolve_evidence(record.task, first) == raw["context"][1][1][2]
    online = record.task.model_dump_json()
    for forbidden in ("REFERENCE_ONLY_ANSWER", "supporting_facts", "native_type", "native_level"):
        assert forbidden not in online


@pytest.mark.parametrize(
    "support",
    [
        None,
        [],
        [["Missing title", 0]],
        [["First Person", 902]],
        [["First Person", True]],
        [["First Person", -1]],
    ],
)
def test_bad_support_is_audited_without_changing_input(support: Any) -> None:
    raw = native()
    expected = normalize_hotpotqa_record(raw).task
    raw["supporting_facts"] = support
    record = normalize_hotpotqa_record(raw)
    assert record.task == expected
    assert any("support" in w for w in record.warnings)
    assert record.reference.annotations["supporting_facts"] == support


def test_article_identity_links_text_variants_without_flattening_text() -> None:
    first = normalize_hotpotqa_record(native()).task.passages[1]
    raw = native("q2")
    raw["context"][1][0] = "First_Person"
    raw["context"][1][1][0] = "An updated version."
    second = normalize_hotpotqa_record(raw).task.passages[1]
    assert first.source_id == second.source_id
    assert first.passage_id != second.passage_id
    assert second.title == "First_Person"
    assert normalize_hotpotqa_record(native()).task.passages[1] == first


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("_id", " ", "invalid_native_id"),
        ("_id", " q1", "invalid_native_id"),
        ("question", "", "invalid_question"),
        ("answer", None, "invalid_answer"),
        ("context", [], "invalid_context"),
        ("context", [["Title", [" ", ""]]], "invalid_sentences"),
        ("context", [["Title", [123]]], "invalid_sentences"),
        ("context", [["Title"]], "invalid_paragraph"),
        ("context", [["Title", ["A"]], ["Title", ["B"]]], "duplicate_context_title"),
    ],
)
def test_malformed_record_has_stable_reason(field: str, value: Any, reason: str) -> None:
    raw = native()
    raw[field] = value
    with pytest.raises(ValueError, match=reason):
        normalize_hotpotqa_record(raw)


def test_round_trip_reconciles_duplicates_malformed_and_native_splits(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    bad = native("bad")
    bad["question"] = ""
    plan = acquired(raw_root, [native(), native(), bad], dev=[native()])
    output = tmp_path / "normalized.sqlite3"
    report = normalize_hotpotqa(plan, raw_root, output)
    assert report["counts"]["train"] == {
        "raw": 3,
        "retained": 1,
        "duplicates": 1,
        "malformed": 1,
        "with_annotation_warnings": 0,
        "with_blank_sentence_slots": 1,
    }
    assert report["counts"]["dev"]["retained"] == 1
    # A cross-split repeated identity remains available for the later group audit.
    for split in ("train", "dev"):
        assert load_hotpotqa_task(output, "hotpotqa:q1", split=split) == (
            normalize_hotpotqa_record(native()).task
        )
        assert load_hotpotqa_reference(output, "hotpotqa:q1", split=split).answers == (
            "REFERENCE_ONLY_ANSWER",
        )
    assert report["source_versions"] == 3
    assert report["source_identities"] == 3
    for flag in (
        "scientific_roles_assigned",
        "data_snapshot_available",
        "study_bindings_updated",
        "runtime_contacted",
    ):
        assert report[flag] is False
    before = output.read_bytes()
    repeated = normalize_hotpotqa(plan, raw_root, output)
    assert repeated["status"] == "verified_existing"
    assert repeated["normalization_id"] == report["normalization_id"]
    assert output.read_bytes() == before
    other = normalize_hotpotqa(plan, raw_root, tmp_path / "other.sqlite3")
    assert other["normalization_id"] == report["normalization_id"]
    with closing(sqlite3.connect(output)) as connection:
        assert connection.execute(
            "SELECT reason FROM exclusions ORDER BY raw_index"
        ).fetchall() == [("duplicate_task_id",), ("invalid_question",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_conflicting_id_fails_atomically(tmp_path: Path) -> None:
    conflicting = native()
    conflicting["answer"] = "A different reference"
    plan = acquired(tmp_path / "raw", [native(), conflicting])
    output = tmp_path / "out.sqlite3"
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_hotpotqa(plan, tmp_path / "raw", output)
    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_changed_raw_bytes_fail_before_output_creation(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    path = tmp_path / "raw/hotpotqa/fixture-v1/train.json"
    path.write_bytes(path.read_bytes().replace(b"country", b"COUNTRY"))
    with pytest.raises(ValueError, match="checksum"):
        normalize_hotpotqa(plan, tmp_path / "raw", tmp_path / "absent/out.sqlite3")
    assert not (tmp_path / "absent").exists()


def test_wrong_plan_or_pending_source_is_rejected(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    changed = plan.model_copy(update={"revision": "different"})
    with pytest.raises(ValueError, match="provenance"):
        normalize_hotpotqa(changed, tmp_path / "raw", tmp_path / "out.sqlite3")
    manifest = tmp_path / "raw/hotpotqa/fixture-v1/acquisition.json"
    state = json.loads(manifest.read_text())
    state["sources"]["train.json"]["status"] = "downloading"
    manifest.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="before normalization"):
        normalize_hotpotqa(plan, tmp_path / "raw", tmp_path / "out.sqlite3")


def test_output_collision_and_corruption_never_overwrite_existing_artifact(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", [native()], dev=[native("q2")])
    output = tmp_path / "out.sqlite3"
    normalize_hotpotqa(plan, tmp_path / "raw", output, split="train")
    before = output.read_bytes()
    with pytest.raises(ValueError, match="different normalization"):
        normalize_hotpotqa(plan, tmp_path / "raw", output)
    assert output.read_bytes() == before
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("UPDATE inputs SET input_json='{}'")
        connection.commit()
    with pytest.raises(ValueError, match="checksum"):
        load_hotpotqa_task(output, "hotpotqa:q1", split="train")
    with pytest.raises(ValueError, match="checksum"):
        normalize_hotpotqa(plan, tmp_path / "raw", output, split="train")


def test_raw_location_and_concurrent_writer_are_protected(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    with pytest.raises(ValueError, match="immutable raw"):
        normalize_hotpotqa(plan, tmp_path / "raw", tmp_path / "raw/hotpotqa/fixture-v1/out.db")
    output = tmp_path / "out.sqlite3"
    lock = _WriterLock(tmp_path / "out.sqlite3.lock")
    try:
        with pytest.raises(ValueError, match="locked"):
            normalize_hotpotqa(plan, tmp_path / "raw", output)
    finally:
        lock.close()
    assert not output.exists()


def test_raw_changed_during_read_is_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    real_insert = hotpotqa._insert_record

    def insert_and_change(*args: Any) -> None:
        real_insert(*args)
        path = tmp_path / "raw/hotpotqa/fixture-v1/train.json"
        path.write_bytes(path.read_bytes().replace(b"country", b"COUNTRY"))

    monkeypatch.setattr(hotpotqa, "_insert_record", insert_and_change)
    with pytest.raises(ValueError, match="changed during normalization"):
        normalize_hotpotqa(plan, tmp_path / "raw", tmp_path / "out.sqlite3")
    assert not (tmp_path / "out.sqlite3").exists()


def test_online_loader_does_not_read_reference_table(tmp_path: Path) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    output = tmp_path / "out.sqlite3"
    normalize_hotpotqa(plan, tmp_path / "raw", output)
    with closing(sqlite3.connect(output)) as connection:
        connection.execute("DROP TABLE evaluation_references")
        connection.commit()
    assert load_hotpotqa_task(output, "hotpotqa:q1", split="train").task_id == "hotpotqa:q1"


def test_passage_preserves_blank_slots_but_rejects_empty_content() -> None:
    assert Passage(source_id="s", passage_id="p", sentences=("", "Text", " ")).sentences == (
        "",
        "Text",
        " ",
    )
    with pytest.raises(ValueError, match="non-blank"):
        Passage(source_id="s", passage_id="p", sentences=("", " "))
    with pytest.raises(ValueError):
        Passage(source_id="s", passage_id="p", sentences=(123,))


def test_cli_normalizes_offline_from_explicit_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = acquired(tmp_path / "raw", [native()])
    original_loader = hotpotqa.normalize_hotpotqa_record
    task_calls: list[str] = []

    def adapter(raw: dict[str, Any]) -> hotpotqa.HotpotRecord:
        task_calls.append(raw["_id"])
        return original_loader(raw)

    study = load_study_bundle()
    assert study.datasets.acquisition is not None
    catalog = study.datasets.acquisition.model_copy(update={"hotpotqa": plan})
    study = study.model_copy(
        update={"datasets": study.datasets.model_copy(update={"acquisition": catalog})}
    )
    monkeypatch.setattr("workflow_reuse_orchestrator.cli.load_study_bundle", lambda config: study)
    monkeypatch.setattr(hotpotqa, "normalize_hotpotqa_record", adapter)
    assert (
        main(
            [
                "data",
                "normalize",
                "--dataset",
                "hotpotqa",
                "--split",
                "train",
                "--raw-root",
                str(tmp_path / "raw"),
                "--output",
                str(tmp_path / "out.sqlite3"),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "normalized"
    assert report["runtime_contacted"] is False
    assert task_calls == ["q1"]
    assert "preserving every supplied paragraph" in captured.err
