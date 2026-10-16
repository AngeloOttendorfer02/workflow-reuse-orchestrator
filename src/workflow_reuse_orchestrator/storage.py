"""Versioned SQLite receipts, immutable bindings, and checksum artifacts."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from workflow_reuse_orchestrator.domain.outcomes import Receipt

SCHEMA_VERSION = 1


class StorageIntegrityError(ValueError):
    """Stored content differs from its checksum or an immutable identity."""


def canonical_json(value: object) -> str:
    """Serialize finite JSON values consistently across machines."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ResultStore:
    """One compact database; completed receipts and bindings cannot be overwritten."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path.resolve()
        self.read_only = read_only
        self._closed = False
        if read_only:
            self._connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, timeout=10
            )
            self._connection.execute("PRAGMA query_only=ON")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=10)
        try:
            with self._connection:
                if not read_only:
                    self._connection.execute("BEGIN IMMEDIATE")
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA_VERSION) or (read_only and version != SCHEMA_VERSION):
                    raise StorageIntegrityError(f"Unsupported result database version: {version}")
                if version == 0:
                    existing = self._connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    if existing:
                        raise StorageIntegrityError(
                            "Refusing to reinterpret an unversioned database."
                        )
                    self._connection.execute(
                        "CREATE TABLE receipts (receipt_id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                        "payload TEXT NOT NULL, checksum TEXT NOT NULL)"
                    )
                    self._connection.execute(
                        "CREATE TABLE bindings (name TEXT PRIMARY KEY, "
                        "payload TEXT NOT NULL, checksum TEXT NOT NULL)"
                    )
                    self._connection.execute(
                        "CREATE TABLE artifacts (name TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
                        "payload BLOB NOT NULL, checksum TEXT NOT NULL)"
                    )
                    self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        except Exception:
            self._connection.close()
            raise

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
        encoded = canonical_json(receipt.model_dump(mode="json"))
        checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._connection:
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
            "SELECT payload, checksum FROM receipts WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        if row is None:
            return None
        self._verified_json(row[0], row[1], receipt_id)
        return Receipt.model_validate_json(row[0])

    def receipts(self, kind: str) -> Iterator[Receipt]:
        self._require_open()
        rows = self._connection.execute(
            "SELECT payload, checksum FROM receipts WHERE kind=? ORDER BY receipt_id", (kind,)
        )
        for payload, checksum in rows:
            self._verified_json(payload, checksum, kind)
            yield Receipt.model_validate_json(payload)

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
            self._connection.close()

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
