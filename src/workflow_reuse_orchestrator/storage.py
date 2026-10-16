"""Versioned SQLite receipts, immutable bindings, and checksum artifacts."""

import hashlib
import importlib
import json
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeVar

from pydantic import BaseModel

from workflow_reuse_orchestrator.domain.budgets import ResourceUsage
from workflow_reuse_orchestrator.domain.outcomes import (
    AttemptSpec,
    JobRecord,
    JobResult,
    JobSpec,
    Receipt,
    RequestSpec,
    RunSpec,
    ScopeSpec,
)

SCHEMA_VERSION = 2
M = TypeVar("M", bound=BaseModel)
_IDENTITY_FIELDS = {
    "runs": ("run_id",),
    "scopes": ("scope_id", "run_id"),
    "requests": ("request_id", "scope_id"),
    "attempts": ("attempt_id", "request_id"),
}


class StorageIntegrityError(ValueError):
    """Stored content differs from its checksum or an immutable identity."""


class WriterLockedError(ValueError):
    """Another cooperative writer owns this result database."""


class _WriterLock:
    """Kernel-owned lifetime lock; never unlink a lock path while another process waits."""

    def __init__(self, path: Path) -> None:
        self._handle = path.open("a+b")
        try:
            if os.fstat(self._handle.fileno()).st_size == 0:
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            self._windows = os.name == "nt"
            self._api = importlib.import_module("msvcrt" if self._windows else "fcntl")
            if self._windows:
                self._api.locking(self._handle.fileno(), self._api.LK_NBLCK, 1)
            else:
                self._api.flock(self._handle.fileno(), self._api.LOCK_EX | self._api.LOCK_NB)
        except BaseException as exc:
            self._handle.close()
            if isinstance(exc, OSError):
                raise WriterLockedError(f"Result writer is locked: {path}") from exc
            raise

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            self._handle.seek(0)
            if self._windows:
                self._api.locking(self._handle.fileno(), self._api.LK_UNLCK, 1)
            else:
                self._api.flock(self._handle.fileno(), self._api.LOCK_UN)
        finally:
            self._handle.close()


def canonical_json(value: object) -> str:
    """Serialize finite JSON values consistently across machines."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ResultStore:
    """One compact database; completed receipts and bindings cannot be overwritten."""

    def __init__(self, path: Path, *, read_only: bool = False, migrate: bool = False) -> None:
        if read_only and migrate:
            raise ValueError("Read-only inspection cannot migrate a database.")
        self.path = path.resolve()
        self.read_only = read_only
        self._closed = False
        self._writer_lock: _WriterLock | None = None
        try:
            if read_only:
                self._connection = sqlite3.connect(
                    self.path.as_uri() + "?mode=ro", uri=True, timeout=10
                )
                self._connection.execute("PRAGMA query_only=ON")
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._writer_lock = _WriterLock(self.path.with_suffix(self.path.suffix + ".lock"))
                self._connection = sqlite3.connect(self.path, timeout=10)
            self._connection.execute("PRAGMA foreign_keys=ON")
            with self._connection:
                if not read_only:
                    self._connection.execute("BEGIN IMMEDIATE")
                self.schema_version = int(
                    self._connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if self.schema_version not in (0, 1, SCHEMA_VERSION) or (
                    read_only and self.schema_version == 0
                ):
                    raise StorageIntegrityError(
                        f"Unsupported result database version: {self.schema_version}"
                    )
                if self.schema_version == 0:
                    existing = self._connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    if existing:
                        raise StorageIntegrityError(
                            "Refusing to reinterpret an unversioned database."
                        )
                    for statement in (
                        "CREATE TABLE receipts (receipt_id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                        "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
                        "CREATE TABLE bindings (name TEXT PRIMARY KEY, "
                        "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
                        "CREATE TABLE artifacts (name TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
                        "payload BLOB NOT NULL, checksum TEXT NOT NULL)",
                    ):
                        self._connection.execute(statement)
                if not read_only and (
                    self.schema_version == 0 or (self.schema_version == 1 and migrate)
                ):
                    if self.schema_version == 1:
                        self.verify_integrity()
                    self._create_job_schema()
                    self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    self.schema_version = SCHEMA_VERSION
        except BaseException:
            if hasattr(self, "_connection"):
                self._connection.close()
            if self._writer_lock is not None:
                self._writer_lock.close()
            raise

    def _create_job_schema(self) -> None:
        for statement in (
            "CREATE TABLE runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
            "checksum TEXT NOT NULL)",
            "CREATE TABLE scopes (scope_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
            "CREATE TABLE requests (request_id TEXT PRIMARY KEY, "
            "scope_id TEXT NOT NULL REFERENCES scopes, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
            "CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, "
            "request_id TEXT NOT NULL REFERENCES requests, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
            "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES scopes, "
            "request_id TEXT REFERENCES requests, attempt_id TEXT REFERENCES attempts, "
            "retry_of TEXT REFERENCES jobs, status TEXT NOT NULL, stage TEXT NOT NULL, "
            "phase TEXT NOT NULL, method_id TEXT NOT NULL, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
            "CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "job_id TEXT NOT NULL REFERENCES jobs, event_type TEXT NOT NULL, "
            "payload TEXT NOT NULL, checksum TEXT NOT NULL)",
            "CREATE INDEX jobs_scope_status ON jobs(scope_id,status)",
            "CREATE INDEX jobs_request_attempt ON jobs(request_id,attempt_id)",
            "CREATE INDEX events_job_sequence ON events(job_id,sequence)",
        ):
            self._connection.execute(statement)

    def bind(self, name: str, value: object) -> None:
        self._require_writable()
        encoded = canonical_json(value)
        checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO bindings VALUES (?,?,?)", (name, encoded, checksum)
            )
            row = self._connection.execute(
                "SELECT payload, checksum FROM bindings WHERE name=?", (name,)
            ).fetchone()
            if row != (encoded, checksum):
                raise StorageIntegrityError(f"Binding changed: {name}")

    def binding(self, name: str) -> Any:
        self._require_open()
        row = self._connection.execute(
            "SELECT payload, checksum FROM bindings WHERE name=?", (name,)
        ).fetchone()
        return None if row is None else self._verified_json(row[0], row[1], name)

    def put_receipt(self, receipt: Receipt) -> None:
        self._require_writable()
        with self._connection:
            self._insert_receipt(receipt)

    def _insert_receipt(self, receipt: Receipt) -> None:
        encoded = canonical_json(receipt.model_dump(mode="json"))
        checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        self._connection.execute(
            "INSERT OR IGNORE INTO receipts VALUES (?,?,?,?)",
            (receipt.receipt_id, receipt.kind, encoded, checksum),
        )
        row = self._connection.execute(
            "SELECT payload, checksum FROM receipts WHERE receipt_id=?", (receipt.receipt_id,)
        ).fetchone()
        if row != (encoded, checksum):
            raise StorageIntegrityError(f"Receipt changed: {receipt.receipt_id}")

    def receipt(self, receipt_id: str) -> Receipt | None:
        self._require_open()
        row = self._connection.execute(
            "SELECT kind, payload, checksum FROM receipts WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        if row is None:
            return None
        self._verified_json(row[1], row[2], receipt_id)
        receipt = Receipt.model_validate_json(row[1])
        if receipt.receipt_id != receipt_id or receipt.kind != row[0]:
            raise StorageIntegrityError(f"Indexed receipt differs from payload: {receipt_id}")
        return receipt

    def receipts(self, kind: str) -> Iterator[Receipt]:
        self._require_open()
        rows = self._connection.execute(
            "SELECT receipt_id FROM receipts WHERE kind=? ORDER BY receipt_id", (kind,)
        )
        for (identity,) in rows:
            receipt = self.receipt(identity)
            if receipt is not None:
                yield receipt

    def put_artifact(self, name: str, content: bytes, *, media_type: str) -> None:
        self._require_writable()
        checksum = hashlib.sha256(content).hexdigest()
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?)",
                (name, media_type, content, checksum),
            )
            row = self._connection.execute(
                "SELECT media_type, payload, checksum FROM artifacts WHERE name=?", (name,)
            ).fetchone()
            if row != (media_type, content, checksum):
                raise StorageIntegrityError(f"Artifact changed: {name}")

    def artifact(self, name: str) -> bytes | None:
        self._require_open()
        row = self._connection.execute(
            "SELECT payload, checksum FROM artifacts WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return None
        content = bytes(row[0])
        if hashlib.sha256(content).hexdigest() != row[1]:
            raise StorageIntegrityError(f"Artifact checksum mismatch: {name}")
        return content

    def _require_jobs(self, *, writable: bool = False) -> None:
        if writable:
            self._require_writable()
        else:
            self._require_open()
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                "Schema-v1 has no job ledger. Migrate explicitly or use a new output folder."
            )

    def _identity(self, table: str, identity: str, contract: type[M]) -> M | None:
        self._require_jobs()
        fields = _IDENTITY_FIELDS[table]
        row = self._connection.execute(
            f"SELECT {','.join(fields)},payload,checksum FROM {table} WHERE {fields[0]}=?",
            (identity,),
        ).fetchone()
        if row is None:
            return None
        self._verified_json(row[-2], row[-1], identity)
        model = contract.model_validate_json(row[-2])
        if tuple(getattr(model, field) for field in fields) != row[:-2]:
            raise StorageIntegrityError(f"Indexed identity differs from payload: {identity}")
        return model

    def _declare_identity(
        self, table: str, spec: RunSpec | ScopeSpec | RequestSpec | AttemptSpec
    ) -> None:
        self._require_jobs(writable=True)
        fields = _IDENTITY_FIELDS[table]
        encoded = canonical_json(spec.model_dump(mode="json"))
        values = tuple(getattr(spec, field) for field in fields)
        placeholders = ",".join("?" for _ in range(len(fields) + 2))
        with self._connection:
            self._connection.execute(
                f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})",
                (*values, encoded, canonical_sha256(spec.model_dump(mode="json"))),
            )
            row = self._connection.execute(
                f"SELECT {','.join(fields)},payload,checksum FROM {table} WHERE {fields[0]}=?",
                (values[0],),
            ).fetchone()
            if row != (*values, encoded, canonical_sha256(spec.model_dump(mode="json"))):
                raise StorageIntegrityError(f"Immutable {table} identity changed: {values[0]}")

    def declare_run(self, spec: RunSpec) -> None:
        self._declare_identity("runs", spec)

    def declare_scope(self, spec: ScopeSpec) -> None:
        if self.run(spec.run_id) is None:
            raise ValueError("Scope requires a declared run.")
        self._declare_identity("scopes", spec)

    def declare_request(self, spec: RequestSpec) -> None:
        if self.scope(spec.scope_id) is None:
            raise ValueError("Request requires a declared scope.")
        self._declare_identity("requests", spec)

    def declare_attempt(self, spec: AttemptSpec) -> None:
        if self.request(spec.request_id) is None:
            raise ValueError("Attempt requires a declared request.")
        self._declare_identity("attempts", spec)

    def run(self, run_id: str) -> RunSpec | None:
        return self._identity("runs", run_id, RunSpec)

    def scope(self, scope_id: str) -> ScopeSpec | None:
        return self._identity("scopes", scope_id, ScopeSpec)

    def request(self, request_id: str) -> RequestSpec | None:
        return self._identity("requests", request_id, RequestSpec)

    def attempt(self, attempt_id: str) -> AttemptSpec | None:
        return self._identity("attempts", attempt_id, AttemptSpec)

    def declare_job(self, spec: JobSpec) -> JobRecord:
        self._require_jobs(writable=True)
        existing = self.job(spec.job_id)
        if existing is not None:
            if existing.spec != spec:
                raise StorageIntegrityError(f"Job identity changed: {spec.job_id}")
            return existing
        if self.scope(spec.scope_id) is None:
            raise ValueError("Job requires a declared scope.")
        if spec.request_id is not None:
            request = self.request(spec.request_id)
            attempt = self.attempt(str(spec.attempt_id))
            if (
                request is None
                or request.scope_id != spec.scope_id
                or request.method_id != spec.method_id
            ):
                raise ValueError("Job/request scope and method must agree.")
            if attempt is None or attempt.request_id != request.request_id:
                raise ValueError("Job attempt must belong to its request.")
            if self._connection.execute(
                "SELECT 1 FROM jobs WHERE request_id=? AND status='unknown'", (spec.request_id,)
            ).fetchone():
                raise ValueError(
                    "An unknown request cannot admit new jobs; use an explicit new trial."
                )
        if spec.retry_of is not None:
            previous = self.job(spec.retry_of)
            if previous is None or previous.status not in ("failed", "unknown"):
                raise ValueError("Retry requires a failed/unknown predecessor.")
            comparable = ("scope_id", "stage", "phase", "method_id", "effect", "parameters")
            if any(getattr(spec, field) != getattr(previous.spec, field) for field in comparable):
                raise ValueError("Retry must retain scope, method, stage, effect and parameters.")
            if previous.spec.request_id is not None and (
                spec.request_id is None or spec.request_id == previous.spec.request_id
            ):
                raise ValueError("Retry requires an explicit new request/trial identity.")
            if previous.spec.request_id is not None and spec.request_id is not None:
                original_request = self.request(previous.spec.request_id)
                new_request = self.request(spec.request_id)
                if (
                    original_request is None
                    or new_request is None
                    or (
                        original_request.model_dump(exclude={"request_id"})
                        != new_request.model_dump(exclude={"request_id"})
                    )
                ):
                    raise ValueError("Retry must retain task, scope, method and declared limits.")
            if self._connection.execute(
                "SELECT 1 FROM jobs WHERE retry_of=?", (spec.retry_of,)
            ).fetchone():
                raise ValueError("This job already has a retry; follow its existing retry chain.")
        record = JobRecord(spec=spec)
        with self._connection:
            self._write_job(record, "declared", insert=True)
        return record

    def job(self, job_id: str) -> JobRecord | None:
        self._require_jobs()
        row = self._connection.execute(
            "SELECT job_id,scope_id,request_id,attempt_id,retry_of,status,stage,phase,method_id,"
            "payload,checksum FROM jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        self._verified_json(row[-2], row[-1], job_id)
        record = JobRecord.model_validate_json(row[-2])
        if row[:-2] != self._job_columns(record):
            raise StorageIntegrityError(f"Indexed job differs from payload: {job_id}")
        return record

    def jobs(
        self,
        *,
        run_id: str | None = None,
        request_id: str | None = None,
        attempt_id: str | None = None,
    ) -> tuple[JobRecord, ...]:
        self._require_jobs()
        ids = self._connection.execute(
            "SELECT j.job_id FROM jobs j JOIN scopes s ON j.scope_id=s.scope_id "
            "WHERE (? IS NULL OR s.run_id=?) AND (? IS NULL OR j.request_id=?) "
            "AND (? IS NULL OR j.attempt_id=?) ORDER BY j.rowid",
            (run_id, run_id, request_id, request_id, attempt_id, attempt_id),
        ).fetchall()
        return tuple(record for (identity,) in ids if (record := self.job(identity)) is not None)

    @staticmethod
    def _job_columns(record: JobRecord) -> tuple[object, ...]:
        spec = record.spec
        return (
            spec.job_id,
            spec.scope_id,
            spec.request_id,
            spec.attempt_id,
            spec.retry_of,
            record.status,
            spec.stage,
            spec.phase,
            spec.method_id,
        )

    def _write_job(self, record: JobRecord, event_type: str, *, insert: bool = False) -> None:
        encoded = canonical_json(record.model_dump(mode="json"))
        checksum = canonical_sha256(record.model_dump(mode="json"))
        columns = self._job_columns(record)
        if insert:
            self._connection.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (*columns, encoded, checksum)
            )
        else:
            self._connection.execute(
                "UPDATE jobs SET status=?,payload=?,checksum=? WHERE job_id=?",
                (record.status, encoded, checksum, record.spec.job_id),
            )
        self._connection.execute(
            "INSERT INTO events(job_id,event_type,payload,checksum) VALUES (?,?,?,?)",
            (record.spec.job_id, event_type, encoded, checksum),
        )

    def start_job(self, job_id: str, *, receipts: tuple[Receipt, ...] = ()) -> JobRecord:
        self._require_jobs(writable=True)
        record = self.job(job_id)
        if record is None or record.status != "pending":
            raise ValueError("Only a pending job can start.")
        if self._connection.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
            raise ValueError("Another job is in flight; execution must remain sequential.")
        if record.spec.request_id is not None:
            states = self._connection.execute(
                "SELECT status FROM jobs WHERE request_id=? AND job_id<>?",
                (record.spec.request_id, job_id),
            ).fetchall()
            if any(state in ("running", "unknown") for (state,) in states):
                raise ValueError("An in-flight/unknown request cannot admit another effect.")
        usage = ResourceUsage(
            model_calls=int(record.spec.effect == "model"),
            tool_calls=int(record.spec.effect == "tool"),
            input_tokens=None if record.spec.effect == "model" else 0,
            output_tokens=None if record.spec.effect == "model" else 0,
        )
        started = JobRecord(
            spec=record.spec,
            status="running",
            usage=usage,
            wall_time_available=False,
            started_at=datetime.now(UTC).isoformat(),
        )
        with self._connection:
            self._write_job(started, "started")
            for receipt in receipts:
                self._insert_receipt(receipt)
        return started

    def finish_job(
        self, job_id: str, result: JobResult, *, receipts: tuple[Receipt, ...] = ()
    ) -> JobRecord:
        self._require_jobs(writable=True)
        record = self.job(job_id)
        if record is None or record.status != "running":
            raise ValueError("Only a running job can finish; terminal jobs are immutable.")
        if (record.spec.effect == "model" and result.usage.model_calls < 1) or (
            record.spec.effect == "tool" and result.usage.tool_calls < 1
        ):
            raise ValueError("Measured usage cannot erase an admitted effect.")
        finished = JobRecord(
            spec=record.spec,
            status=result.status,
            usage=result.usage,
            result=result.result,
            error=result.error,
            started_at=record.started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
        with self._connection:
            self._write_job(finished, "completed")
            for receipt in receipts:
                self._insert_receipt(receipt)
        return finished

    def interrupt_job(
        self,
        job_id: str,
        *,
        error: str,
        elapsed_seconds: float | None = None,
        usage: ResourceUsage | None = None,
    ) -> JobRecord:
        self._require_jobs(writable=True)
        record = self.job(job_id)
        if record is None or record.status != "running":
            raise ValueError("Only a running job can be interrupted.")
        known_local = record.spec.effect == "local" and elapsed_seconds is not None
        values = (record.usage if usage is None else usage).model_dump()
        values["model_calls"] = max(int(values["model_calls"]), record.usage.model_calls)
        values["tool_calls"] = max(int(values["tool_calls"]), record.usage.tool_calls)
        values["wall_seconds"] = max(float(values["wall_seconds"]), elapsed_seconds or 0.0)
        measured_usage = ResourceUsage.model_validate(values)
        interrupted = JobRecord(
            spec=record.spec,
            status="failed" if known_local else "unknown",
            usage=measured_usage,
            wall_time_available=elapsed_seconds is not None,
            result={} if known_local else None,
            error=error,
            started_at=record.started_at,
            finished_at=datetime.now(UTC).isoformat(),
        )
        with self._connection:
            self._write_job(interrupted, "interrupted")
        return interrupted

    def recover_running(self, *, run_id: str) -> int:
        """Explicit writer recovery. Even local in-flight units are conservatively unknown."""
        self._require_jobs(writable=True)
        running = [job for job in self.jobs(run_id=run_id) if job.status == "running"]
        for job in running:
            self.interrupt_job(
                job.spec.job_id,
                error="Process ended without a durable result; possible cost retained.",
            )
        return len(running)

    def events(self, job_id: str) -> tuple[dict[str, Any], ...]:
        self._require_jobs()
        rows = self._connection.execute(
            "SELECT sequence,event_type,payload,checksum FROM events "
            "WHERE job_id=? ORDER BY sequence",
            (job_id,),
        ).fetchall()
        result = []
        for sequence, event_type, payload, checksum in rows:
            self._verified_json(payload, checksum, f"event:{sequence}")
            record = JobRecord.model_validate_json(payload)
            if record.spec.job_id != job_id:
                raise StorageIntegrityError("Event job identity differs from its payload.")
            result.append(
                {
                    "sequence": sequence,
                    "event_type": event_type,
                    "record": record.model_dump(mode="json"),
                }
            )
        return tuple(result)

    def progress(self, *, run_id: str | None = None) -> dict[str, Any]:
        self._require_open()
        if self.schema_version == 1:
            return {
                "schema_version": 1,
                "job_ledger_available": False,
                "jobs": {},
                "message": "Legacy receipts are readable; job history was not recorded.",
            }
        records = self.jobs(run_id=run_id)
        states = ("pending", "running", "succeeded", "failed", "unknown")
        counts = {state: sum(job.status == state for job in records) for state in states}
        measured = [job for job in records if job.status != "pending"]
        usage: dict[str, Any] = {}
        for field in ResourceUsage.model_fields:
            values = [getattr(job.usage, field) for job in measured]
            usage[field] = None if any(value is None for value in values) else sum(values)
        if any(not job.wall_time_available for job in measured):
            usage["wall_seconds"] = None
        phases = {
            phase: sum(job.spec.phase == phase for job in records)
            for phase in ("startup", "request", "analysis")
        }
        scopes = []
        for (identity,) in self._connection.execute(
            "SELECT scope_id FROM scopes WHERE (? IS NULL OR run_id=?) ORDER BY scope_id",
            (run_id, run_id),
        ):
            scope = self.scope(identity)
            if scope is not None:
                scopes.append(scope.model_dump(mode="json"))
        return {
            "schema_version": self.schema_version,
            "job_ledger_available": True,
            "run_id": run_id,
            "jobs": {"planned": len(records), **counts},
            "phase_counts": phases,
            "scopes": scopes,
            "usage": usage,
            "usage_basis": "incremental_job_costs",
            "receipt_count": self._connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[
                0
            ],
            "current": [
                job.spec.model_dump(mode="json") for job in records if job.status == "running"
            ],
            "unknown_job_ids": [job.spec.job_id for job in records if job.status == "unknown"],
        }

    def verify_integrity(self) -> None:
        """Read-only-safe SQLite, checksum, identity and event-history checks."""
        self._require_open()
        if self._connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise StorageIntegrityError("SQLite integrity check failed.")
        if self._connection.execute("PRAGMA foreign_key_check").fetchall():
            raise StorageIntegrityError("SQLite foreign-key integrity check failed.")
        for (identity,) in self._connection.execute("SELECT receipt_id FROM receipts"):
            self.receipt(identity)
        for (identity,) in self._connection.execute("SELECT name FROM bindings"):
            self.binding(identity)
        for (identity,) in self._connection.execute("SELECT name FROM artifacts"):
            self.artifact(identity)
        if self.schema_version == 1:
            return
        for table, contract in (
            ("runs", RunSpec),
            ("scopes", ScopeSpec),
            ("requests", RequestSpec),
            ("attempts", AttemptSpec),
        ):
            for (identity,) in self._connection.execute(
                f"SELECT {_IDENTITY_FIELDS[table][0]} FROM {table}"
            ):
                self._identity(table, identity, contract)
        for job in self.jobs():
            events = self.events(job.spec.job_id)
            if not events:
                raise StorageIntegrityError(f"Missing event history: {job.spec.job_id}")
            expected = ["declared"]
            if job.status != "pending":
                expected.append("started")
            if job.status in ("succeeded", "failed", "unknown"):
                expected.append(
                    "interrupted"
                    if job.status == "unknown" or events[-1]["event_type"] == "interrupted"
                    else "completed"
                )
            if (
                [event["event_type"] for event in events] != expected
                or not events
                or events[-1]["record"] != job.model_dump(mode="json")
            ):
                raise StorageIntegrityError(
                    f"Event history differs from job state: {job.spec.job_id}"
                )

    @staticmethod
    def _verified_json(payload: str, checksum: str, name: str) -> Any:
        if hashlib.sha256(payload.encode("utf-8")).hexdigest() != checksum:
            raise StorageIntegrityError(f"Receipt/binding checksum mismatch: {name}")
        return json.loads(payload)

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("Result store is closed.")

    def _require_writable(self) -> None:
        self._require_open()
        if self.read_only:
            raise ValueError("Cannot modify a read-only result store.")

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._connection.close()
            finally:
                if self._writer_lock is not None:
                    self._writer_lock.close()

    def __enter__(self) -> Self:
        self._require_open()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
