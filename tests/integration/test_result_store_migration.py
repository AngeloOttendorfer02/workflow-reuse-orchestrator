"""Legacy migration, OS writer lifetime locks and truly read-only inspection."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.domain.outcomes import Receipt
from workflow_reuse_orchestrator.experiments.pipeline import inspect_run, migrate_run
from workflow_reuse_orchestrator.storage import (
    ResultStore,
    StorageIntegrityError,
    WriterLockedError,
    canonical_json,
    canonical_sha256,
)


def legacy_database(path: Path) -> Receipt:
    receipt = Receipt(
        receipt_id="historical",
        kind="policy_outcome",
        status="succeeded",
        payload={"method_id": "prediction-reuse-mlp", "usage": {"input_tokens": 12}},
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE receipts (receipt_id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE bindings (name TEXT PRIMARY KEY, payload TEXT NOT NULL, "
            "checksum TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE artifacts (name TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
            "payload BLOB NOT NULL, checksum TEXT NOT NULL)"
        )
        payload = receipt.model_dump(mode="json")
        connection.execute(
            "INSERT INTO receipts VALUES (?,?,?,?)",
            (receipt.receipt_id, receipt.kind, canonical_json(payload), canonical_sha256(payload)),
        )
        connection.execute("PRAGMA user_version=1")
    return receipt


def test_legacy_reads_do_not_migrate_or_invent_history(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    historical = legacy_database(database)
    before = database.read_bytes()
    report = inspect_run(tmp_path)
    assert report["schema_version"] == 1
    assert report["job_ledger_available"] is False
    assert database.read_bytes() == before
    assert not database.with_suffix(".sqlite3.lock").exists()
    with ResultStore(database) as store:
        assert store.schema_version == 1
        assert store.receipt("historical") == historical
        with pytest.raises(ValueError, match="Migrate explicitly"):
            store.jobs()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_explicit_additive_migration_preserves_original_bytes_and_ids(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    historical = legacy_database(database)
    with sqlite3.connect(database) as connection:
        original = connection.execute("SELECT * FROM receipts").fetchall()
    assert migrate_run(tmp_path)["schema_version"] == 2
    assert migrate_run(tmp_path)["historical_jobs_reconstructed"] is False
    with ResultStore(database, read_only=True) as store:
        assert store.receipt("historical") == historical
        assert store.progress()["jobs"]["planned"] == 0
        assert store.progress()["receipt_count"] == 1
        assert store.progress()["usage_basis"] == "incremental_job_costs"
        store.verify_integrity()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM receipts").fetchall() == original


def test_corrupted_legacy_data_blocks_migration_atomically(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    legacy_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE receipts SET payload='{}'")
    with pytest.raises(StorageIntegrityError, match="checksum"):
        migrate_run(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE name='jobs'").fetchall() == []
        )


def test_writer_lock_excludes_second_writer_and_releases_on_close(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    with ResultStore(database):
        with pytest.raises(WriterLockedError):
            ResultStore(database)
        script = """import sys
from pathlib import Path
from workflow_reuse_orchestrator.storage import ResultStore, WriterLockedError
try:
    with ResultStore(Path(sys.argv[1])):
        pass
except WriterLockedError:
    sys.exit(7)
sys.exit(9)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(database)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 7, result.stderr
        with ResultStore(database, read_only=True) as observer:
            observer.verify_integrity()
    # Reusing the persistent lock path is normal; there is no stale PID lock to delete.
    with ResultStore(database) as store:
        store.verify_integrity()


def test_os_releases_writer_after_forced_process_exit(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    script = """import os, sys
from pathlib import Path
from workflow_reuse_orchestrator.storage import ResultStore
store=ResultStore(Path(sys.argv[1]))
store.bind("committed", {"value":1})
os._exit(17)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(database)], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 17, result.stderr
    with ResultStore(database) as store:
        assert store.binding("committed") == {"value": 1}
        store.verify_integrity()


def test_status_cli_is_read_only_and_creates_no_missing_output(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"
    assert main(["pipeline", "status", "--output", str(missing)]) == 2
    assert "Pipeline failed:" in capsys.readouterr().err
    assert not missing.exists()
    assert main(["pipeline", "migrate", "--output", str(missing)]) == 2
    capsys.readouterr()
    assert not missing.exists()
    database = tmp_path / "results.sqlite3"
    with ResultStore(database):
        before = database.read_bytes()
        directory_before = set(tmp_path.iterdir())
        assert main(["pipeline", "status", "--output", str(tmp_path)]) == 0
        output = capsys.readouterr()
        assert output.err == ""
        assert json.loads(output.out)["jobs"]["planned"] == 0
        assert json.loads(output.out)["runtime_contacted"] is False
        assert database.read_bytes() == before
        assert set(tmp_path.iterdir()) == directory_before


def test_read_only_mode_cannot_request_migration(tmp_path: Path) -> None:
    database = tmp_path / "results.sqlite3"
    with pytest.raises(ValueError, match="Read-only"):
        ResultStore(database, read_only=True, migrate=True)
    assert not database.exists()
