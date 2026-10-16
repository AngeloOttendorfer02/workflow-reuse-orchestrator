"""Real SQLite transactions verify immutable identity, checksums, and read-only access."""

import sqlite3
from pathlib import Path

import pytest

from workflow_reuse_orchestrator.domain.outcomes import Receipt
from workflow_reuse_orchestrator.storage import ResultStore, StorageIntegrityError, canonical_sha256


def receipt(answer: str = "OK") -> Receipt:
    return Receipt(
        receipt_id="request:completed",
        kind="generation",
        status="succeeded",
        payload={"answer": answer},
    )


def test_round_trip_and_read_only_inspection(tmp_path: Path) -> None:
    database = tmp_path / "path with spaces" / "results.sqlite3"
    with ResultStore(database) as store:
        store.bind("model", {"digest": "a" * 64})
        store.put_receipt(receipt())
        store.put_artifact("selector", b"model-bytes", media_type="application/octet-stream")
    modified = database.stat().st_mtime_ns
    with ResultStore(database, read_only=True) as store:
        assert store.binding("model") == {"digest": "a" * 64}
        assert store.receipt("request:completed") == receipt()
        assert list(store.receipts("generation")) == [receipt()]
        assert store.artifact("selector") == b"model-bytes"
        with pytest.raises(ValueError, match="read-only"):
            store.bind("new", {})
    assert database.stat().st_mtime_ns == modified


def test_idempotent_receipts_cannot_be_changed(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        store.put_receipt(receipt())
        store.put_receipt(receipt())
        with pytest.raises(StorageIntegrityError, match="Receipt changed"):
            store.put_receipt(receipt("changed"))
        assert store.receipt("request:completed") == receipt()


def test_conflicting_bindings_and_artifacts_preserve_originals(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        store.bind("settings", {"seed": 2609})
        store.put_artifact("library", b"original", media_type="application/json")
        with pytest.raises(StorageIntegrityError, match="Binding changed"):
            store.bind("settings", {"seed": 1})
        with pytest.raises(StorageIntegrityError, match="Artifact changed"):
            store.put_artifact("library", b"replacement", media_type="application/json")
        assert store.binding("settings") == {"seed": 2609}
        assert store.artifact("library") == b"original"


@pytest.mark.parametrize("table", ["receipts", "bindings", "artifacts"])
def test_checksum_mismatch_is_detected(tmp_path: Path, table: str) -> None:
    database = tmp_path / "results.sqlite3"
    with ResultStore(database) as store:
        store.put_receipt(receipt())
        store.bind("settings", {"seed": 2609})
        store.put_artifact("library", b"original", media_type="application/json")
    with sqlite3.connect(database) as connection:
        if table == "artifacts":
            connection.execute("UPDATE artifacts SET payload=?", (b"tampered",))
        elif table == "bindings":
            connection.execute("UPDATE bindings SET payload=?", ('{"seed":1}',))
        else:
            connection.execute("UPDATE receipts SET payload=?", ('{"answer":"changed"}',))
    with (
        ResultStore(database, read_only=True) as store,
        pytest.raises(StorageIntegrityError, match="checksum"),
    ):
        if table == "artifacts":
            store.artifact("library")
        elif table == "bindings":
            store.binding("settings")
        else:
            store.receipt("request:completed")


def test_unversioned_predecessor_database_is_not_reinterpreted(tmp_path: Path) -> None:
    database = tmp_path / "old.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE results (payload TEXT)")
    with pytest.raises(StorageIntegrityError, match="unversioned"):
        ResultStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("results",)]


def test_missing_read_only_database_is_not_created(tmp_path: Path) -> None:
    database = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        ResultStore(database, read_only=True)
    assert not database.exists()


def test_nonfinite_values_cannot_enter_bindings(tmp_path: Path) -> None:
    with ResultStore(tmp_path / "results.sqlite3") as store:
        with pytest.raises(ValueError):
            store.bind("bad", {"value": float("nan")})
        assert store.binding("bad") is None


def test_checksums_ignore_json_mapping_order() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
