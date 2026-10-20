"""Acquire immutable raw sources; normalization and scientific splits follow later."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import ssl
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, TextIO

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from workflow_reuse_orchestrator.domain.providers import Sha256
from workflow_reuse_orchestrator.domain.tasks import DatasetId
from workflow_reuse_orchestrator.storage import _WriterLock, canonical_sha256

SafeName = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")]
Split = Literal["train", "dev", "test"]
Progress = Callable[[str], None]
CHUNK_BYTES = 64 * 1024
CHECKPOINT_BYTES = 8 * 1024 * 1024


class AcquisitionSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: SafeName
    url: str
    download_url: str | None = None
    format: Literal["json_array", "drop_zip"]
    splits: list[Split] = Field(min_length=1)
    expected_sha256: Sha256 | None = None
    expected_bytes: int | None = Field(default=None, gt=0, strict=True)
    checksum_reference: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> AcquisitionSource:
        url = httpx.URL(self.url)
        if url.scheme not in ("http", "https") or not url.host or url.userinfo or url.fragment:
            raise ValueError(
                "Acquisition sources require an absolute HTTP(S) URL without credentials."
            )
        if self.download_url is not None:
            mirror = httpx.URL(self.download_url)
            if mirror.scheme != "https" or not mirror.host or mirror.userinfo or mirror.fragment:
                raise ValueError("An explicit download mirror requires an absolute HTTPS URL.")
            if self.expected_sha256 is None or self.checksum_reference is None:
                raise ValueError("A download mirror requires a pinned checksum and its reference.")
        if self.filename.lower() in {
            "acquisition.json",
            "acquisition.lock",
        } or self.filename.endswith((".part", ".tmp")):
            raise ValueError("Reserved acquisition filename.")
        if len(set(self.splits)) != len(self.splits):
            raise ValueError("Source split names must be unique.")
        if self.format == "json_array" and len(self.splits) != 1:
            raise ValueError("A JSON-array source must identify exactly one native split.")
        if self.format == "drop_zip" and set(self.splits) != {"train", "dev"}:
            raise ValueError("The DROP archive must contain train and dev splits.")
        return self


class AcquisitionDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release: SafeName
    homepage: str
    license: str
    license_url: str
    revision: str
    sources: list[AcquisitionSource] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_sources(self) -> AcquisitionDataset:
        names = [s.filename.casefold() for s in self.sources]
        splits = [split for s in self.sources for split in s.splits]
        if len(names) != len(set(names)) or len(splits) != len(set(splits)):
            raise ValueError("Each raw filename and native split must have one source.")
        return self


class AcquisitionCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["raw-acquisition-v1"]
    hotpotqa: AcquisitionDataset
    drop: AcquisitionDataset
    finqa: AcquisitionDataset


class RawCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: int = Field(ge=0, strict=True)
    questions: int = Field(ge=0, strict=True)


class SourceReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "downloading", "verified", "complete"] = "pending"
    downloaded_bytes: int = Field(default=0, ge=0, strict=True)
    prefix_sha256: Sha256 = hashlib.sha256(b"").hexdigest()
    total_bytes: int | None = Field(default=None, gt=0, strict=True)
    etag: str | None = None
    last_modified: str | None = None
    resolved_url: str | None = None
    sha256: Sha256 | None = None
    size_bytes: int | None = Field(default=None, gt=0, strict=True)
    acquired_at: str | None = None
    counts: dict[str, RawCounts] = Field(default_factory=dict)


class AcquisitionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw-acquisition-v1"] = "raw-acquisition-v1"
    acquisition_version: Literal["c06-v1"] = "c06-v1"
    dataset: DatasetId
    release: str
    plan_sha256: Sha256
    source_plan: AcquisitionDataset
    created_at: str
    sources: dict[str, SourceReceipt]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _write_manifest(path: Path, manifest: AcquisitionManifest) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(manifest.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _hash_file(path: Path, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = limit
    with path.open("rb") as stream:
        while remaining is None or remaining > 0:
            block = stream.read(CHUNK_BYTES if remaining is None else min(CHUNK_BYTES, remaining))
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in (None, 0):
        raise ValueError(f"Partial source is shorter than its checkpoint: {path}")
    return digest.hexdigest()


class _JSONReader:
    """Decode one top-level record at a time rather than loading a 500 MB array."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def more(self) -> None:
        self.buffer = self.buffer[self.position :]
        self.position = 0
        block = self.stream.read(CHUNK_BYTES)
        if not block:
            self.eof = True
        self.buffer += block
        if len(self.buffer) > 32 * 1024 * 1024:
            raise ValueError("A raw JSON record exceeds the 32 MiB acquisition inspection limit.")

    def peek(self) -> str:
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.more()

    def take(self, expected: str) -> None:
        if self.peek() != expected:
            raise ValueError(f"Malformed raw JSON: expected {expected!r}.")
        self.position += 1

    def value(self) -> Any:
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                self.position = end
                return value
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValueError("Incomplete or malformed raw JSON.") from exc
                self.more()


def _json_records(stream: TextIO, *, mapping: bool = False) -> Iterator[dict[str, Any]]:
    reader = _JSONReader(stream)
    reader.take("{" if mapping else "[")
    end = "}" if mapping else "]"
    seen_keys: set[str] = set()
    if reader.peek() != end:
        while True:
            if mapping:
                key = reader.value()
                if not isinstance(key, str) or key in seen_keys:
                    raise ValueError("Raw passage keys must be unique strings.")
                seen_keys.add(key)
                reader.take(":")
            value = reader.value()
            if not isinstance(value, dict):
                raise ValueError("Raw dataset records must be JSON objects.")
            yield value
            if reader.peek() == end:
                break
            reader.take(",")
    reader.take(end)
    if reader.peek():
        raise ValueError("Unexpected content after the raw JSON document.")


def inspect_raw_source(path: Path, source: AcquisitionSource) -> dict[str, RawCounts]:
    """Count original records/questions without creating normalized inputs or labels."""
    if source.format == "json_array":
        with path.open(encoding="utf-8") as stream:
            count = sum(1 for _ in _json_records(stream))
        if not count:
            raise ValueError("Raw source contains no records.")
        return {source.splits[0]: RawCounts(records=count, questions=count)}
    result: dict[str, RawCounts] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            for split in source.splits:
                member = f"drop_dataset/drop_dataset_{split}.json"
                matches = [i for i in archive.infolist() if i.filename == member]
                if len(matches) != 1 or matches[0].file_size > 1024**3:
                    raise ValueError(f"DROP archive requires one bounded {member} member.")
                records = questions = 0
                with (
                    archive.open(matches[0]) as raw,
                    io.TextIOWrapper(raw, encoding="utf-8") as text,
                ):
                    for record in _json_records(text, mapping=True):
                        pairs = record.get("qa_pairs")
                        if not isinstance(pairs, list) or any(
                            not isinstance(p, dict) for p in pairs
                        ):
                            raise ValueError("DROP source requires a qa_pairs list per passage.")
                        records += 1
                        questions += len(pairs)
                if not records or not questions:
                    raise ValueError("DROP source contains an empty split.")
                result[split] = RawCounts(records=records, questions=questions)
    except (zipfile.BadZipFile, KeyError, UnicodeError) as exc:
        raise ValueError(f"Invalid raw DROP archive: {exc}") from exc
    return result


def _restore_partial(path: Path, receipt: SourceReceipt) -> int:
    offset = receipt.downloaded_bytes
    if not path.exists():
        if offset:
            raise ValueError(
                "Partial source is missing; preserve or restore its acquisition record."
            )
        return 0
    if path.stat().st_size < offset or _hash_file(path, offset) != receipt.prefix_sha256:
        raise ValueError("Partial source checksum does not match its checkpoint.")
    # A process crash can leave bytes beyond the last fsynced manifest checkpoint.
    with path.open("r+b") as stream:
        stream.truncate(offset)
    return offset


def _strong_etag(value: str | None) -> bool:
    return value is not None and value.startswith('"') and value.endswith('"')


def _download(
    client: httpx.Client,
    source: AcquisitionSource,
    partial: Path,
    receipt: SourceReceipt,
    checkpoint: Callable[[], None],
    progress: Progress,
) -> None:
    offset = receipt.downloaded_bytes
    if offset and receipt.total_bytes == offset:
        return
    can_resume = offset > 0 and (_strong_etag(receipt.etag) or source.expected_sha256 is not None)
    headers = {"Accept-Encoding": "identity"}
    if can_resume:
        headers["Range"] = f"bytes={offset}-"
        if _strong_etag(receipt.etag):
            headers["If-Range"] = str(receipt.etag)
    with client.stream(
        "GET", source.download_url or source.url, headers=headers, follow_redirects=True
    ) as response:
        response.raise_for_status()
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise ValueError(
                "Raw downloads must use identity content encoding for byte verification."
            )
        etag = response.headers.get("etag")
        total: int | None
        if response.status_code == 206:
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", "")
            )
            if not can_resume or match is None or int(match[1]) != offset:
                raise ValueError("The server returned an invalid byte-range response.")
            if int(match[2]) != int(match[3]) - 1 or int(match[3]) <= offset:
                raise ValueError("The server did not return the complete remaining byte range.")
            if _strong_etag(receipt.etag) and etag != receipt.etag:
                raise ValueError("The remote source changed during a resumed download.")
            total = int(match[3])
            if receipt.total_bytes is not None and receipt.total_bytes != total:
                raise ValueError("The remote source size changed during a resumed download.")
        elif response.status_code == 200:
            # Range ignored or If-Range no longer matched: restart, never append mixed bytes.
            offset = 0
            total = (
                int(response.headers["content-length"])
                if "content-length" in response.headers
                else None
            )
        else:
            raise ValueError(f"Unexpected acquisition HTTP status: {response.status_code}")
        if source.expected_bytes is not None and total not in (None, source.expected_bytes):
            raise ValueError("Remote source size does not match its pinned size.")
        receipt.status = "downloading"
        receipt.total_bytes = total
        receipt.etag = etag
        receipt.last_modified = response.headers.get("last-modified")
        receipt.resolved_url = str(response.url.copy_with(query=None))
        digest = hashlib.sha256()
        if offset:
            with partial.open("rb") as existing:
                while block := existing.read(CHUNK_BYTES):
                    digest.update(block)
        with partial.open("ab" if offset else "wb") as stream:

            def save_progress() -> None:
                stream.flush()
                os.fsync(stream.fileno())
                receipt.downloaded_bytes = stream.tell()
                receipt.prefix_sha256 = digest.hexdigest()
                checkpoint()

            save_progress()
            progress(f"Downloading {source.filename}: starting at {offset} bytes.")
            last_checkpoint = offset
            try:
                for block in response.iter_raw(CHUNK_BYTES):
                    stream.write(block)
                    digest.update(block)
                    if stream.tell() - last_checkpoint >= CHECKPOINT_BYTES:
                        save_progress()
                        last_checkpoint = stream.tell()
                        progress(
                            f"Downloading {source.filename}: {last_checkpoint} bytes recorded."
                        )
            finally:
                save_progress()
        if total is not None and receipt.downloaded_bytes != total:
            raise ValueError("Incomplete source download; rerun acquisition to resume it.")


def _verify_file(path: Path, receipt: SourceReceipt) -> None:
    if receipt.sha256 is None or receipt.size_bytes is None or not receipt.counts:
        raise ValueError("Completed source is missing its verification receipt.")
    if not path.is_file() or path.stat().st_size != receipt.size_bytes:
        raise ValueError(f"Acquired source is missing or has changed size: {path}")
    if _hash_file(path) != receipt.sha256:
        raise ValueError(f"Acquired source checksum mismatch: {path}")


def acquire_dataset(
    dataset: DatasetId,
    plan: AcquisitionDataset,
    raw_root: Path,
    *,
    split: str = "all",
    client: httpx.Client | None = None,
    timeout_seconds: float = 60.0,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Acquire one explicit raw release with crash-safe publication and local verification."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Acquisition timeout must be finite and positive.")
    selected = [s for s in plan.sources if split == "all" or split in s.splits]
    if not selected:
        raise ValueError(f"No {split!r} raw split is configured for {dataset}.")
    emit = progress or (lambda message: None)
    directory = raw_root / dataset / plan.release
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "acquisition.json"
    lock = _WriterLock(directory / "acquisition.lock")
    owned_client = client is None
    try:
        plan_hash = canonical_sha256(plan.model_dump(mode="json"))
        if manifest_path.exists():
            manifest = AcquisitionManifest.model_validate_json(manifest_path.read_text("utf-8"))
            if (
                manifest.dataset != dataset
                or manifest.release != plan.release
                or manifest.plan_sha256 != plan_hash
                or manifest.source_plan != plan
                or set(manifest.sources) != {s.filename for s in plan.sources}
            ):
                raise ValueError(
                    "Raw release/source plan changed; use a new explicit release identity."
                )
        else:
            if any(
                (directory / s.filename).exists() or (directory / (s.filename + ".part")).exists()
                for s in plan.sources
            ):
                raise ValueError(
                    "Raw source files exist without provenance; refusing to overwrite."
                )
            manifest = AcquisitionManifest(
                dataset=dataset,
                release=plan.release,
                plan_sha256=plan_hash,
                source_plan=plan,
                created_at=_utc_now(),
                sources={s.filename: SourceReceipt() for s in plan.sources},
            )
            _write_manifest(manifest_path, manifest)

        def checkpoint() -> None:
            _write_manifest(manifest_path, manifest)

        for configured_source in plan.sources:
            existing_receipt = manifest.sources[configured_source.filename]
            if existing_receipt.status == "complete":
                _verify_file(directory / configured_source.filename, existing_receipt)

        for source in selected:
            receipt = manifest.sources[source.filename]
            target = directory / source.filename
            partial = directory / (source.filename + ".part")
            if receipt.status == "complete":
                emit(f"Verified existing {dataset}/{source.filename}; no download.")
                continue
            if receipt.status != "verified":
                if target.exists():
                    raise ValueError("A raw target exists without a verified publication record.")
                _restore_partial(partial, receipt)
                if client is None:
                    # Include Windows CA/ROOT stores; preserve explicit CA overrides.
                    context = ssl.create_default_context(
                        cafile=os.environ.get("SSL_CERT_FILE") or None,
                        capath=os.environ.get("SSL_CERT_DIR") or None,
                    )
                    client = httpx.Client(timeout=timeout_seconds, verify=context)
                download_url = source.download_url or source.url
                emit(f"Acquiring {dataset}/{source.filename} from {download_url}")
                _download(client, source, partial, receipt, checkpoint, emit)
                size = partial.stat().st_size
                checksum = _hash_file(partial)
                if source.expected_bytes is not None and size != source.expected_bytes:
                    raise ValueError("Downloaded source does not match its pinned byte count.")
                if source.expected_sha256 is not None and checksum != source.expected_sha256:
                    raise ValueError("Downloaded source SHA-256 differs from the pinned checksum.")
                receipt.counts = inspect_raw_source(partial, source)
                receipt.sha256 = checksum
                receipt.size_bytes = size
                receipt.acquired_at = _utc_now()
                receipt.status = "verified"
                checkpoint()
            if target.exists():
                _verify_file(target, receipt)
            else:
                _verify_file(partial, receipt)
                os.replace(partial, target)
            receipt.status = "complete"
            checkpoint()
            emit(f"Acquired {dataset}/{source.filename}; SHA-256 {receipt.sha256}")
        complete = all(r.status == "complete" for r in manifest.sources.values())
        source_checksum = (
            canonical_sha256({name: r.sha256 for name, r in sorted(manifest.sources.items())})
            if complete
            else None
        )
        return {
            "status": "acquired" if complete else "partial",
            "dataset": dataset,
            "release": plan.release,
            "manifest": str(manifest_path),
            "source_checksum": source_checksum,
            "sources": {
                s.filename: manifest.sources[s.filename].model_dump(mode="json") for s in selected
            },
            "executed_questions": 0,
            "data_snapshot_available": False,
        }
    except httpx.HTTPError as exc:
        raise ValueError(
            f"Raw acquisition failed; retained checkpoints can be resumed: {exc}"
        ) from exc
    finally:
        if owned_client and client is not None:
            client.close()
        lock.close()
