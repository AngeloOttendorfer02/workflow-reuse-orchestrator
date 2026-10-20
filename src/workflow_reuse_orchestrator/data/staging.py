"""Shared SQLite layout and logical hashing for unpartitioned adapter artifacts."""

import hashlib
import sqlite3
from pathlib import Path

from workflow_reuse_orchestrator.storage import canonical_json

STAGING_SQL = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE inputs (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, input_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL, PRIMARY KEY(native_split, task_id));
CREATE TABLE evaluation_references (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, reference_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(native_split, task_id),
    FOREIGN KEY(native_split, task_id) REFERENCES inputs(native_split, task_id));
CREATE TABLE sources (
    passage_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL,
    sentences_json TEXT NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE task_sources (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, position INTEGER NOT NULL,
    passage_id TEXT NOT NULL REFERENCES sources(passage_id),
    PRIMARY KEY(native_split, task_id, position),
    FOREIGN KEY(native_split, task_id) REFERENCES inputs(native_split, task_id));
CREATE TABLE provenance (
    native_split TEXT NOT NULL, task_id TEXT NOT NULL, raw_index INTEGER NOT NULL,
    raw_sha256 TEXT NOT NULL, warnings_json TEXT NOT NULL,
    PRIMARY KEY(native_split, task_id),
    FOREIGN KEY(native_split, task_id) REFERENCES inputs(native_split, task_id));
CREATE TABLE exclusions (
    native_split TEXT NOT NULL, raw_index INTEGER NOT NULL, native_id TEXT,
    raw_sha256 TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(native_split, raw_index));
CREATE INDEX source_identity ON sources(source_id);
CREATE INDEX source_content ON sources(content_sha256);
"""


def content_hash(
    connection: sqlite3.Connection, *, extra_tables: tuple[tuple[str, str], ...] = ()
) -> str:
    digest = hashlib.sha256()
    for table, order in (
        ("inputs", "native_split,task_id"),
        ("evaluation_references", "native_split,task_id"),
        ("sources", "passage_id"),
        ("task_sources", "native_split,task_id,position"),
        ("provenance", "native_split,task_id"),
        ("exclusions", "native_split,raw_index"),
        *extra_tables,
    ):
        digest.update((table + "\n").encode())
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            digest.update((canonical_json(list(row)) + "\n").encode("utf-8"))
    return digest.hexdigest()


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
