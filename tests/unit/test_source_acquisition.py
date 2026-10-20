"""Raw acquisition boundaries, with no real network or benchmark download."""

import hashlib
import io
import json
import ssl
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from workflow_reuse_orchestrator.cli import main
from workflow_reuse_orchestrator.config import load_study_bundle
from workflow_reuse_orchestrator.data import prepare
from workflow_reuse_orchestrator.data.prepare import (
    AcquisitionDataset,
    AcquisitionSource,
    acquire_dataset,
    inspect_raw_source,
)
from workflow_reuse_orchestrator.storage import _WriterLock


def payload() -> bytes:
    return json.dumps([{"id": i, "text": "numerical evidence café"} for i in range(3)]).encode()


def response(
    data: bytes, status: int = 200, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status,
        stream=httpx.ByteStream(data),
        headers={"Content-Length": str(len(data)), **(headers or {})},
    )


def plan(data: bytes, *, pinned: bool = True, name: str = "dev.json") -> AcquisitionDataset:
    return AcquisitionDataset(
        release="fixture-v1",
        homepage="https://example.org/dataset",
        license="fixture-only",
        license_url="https://example.org/license",
        revision="fixture-v1",
        sources=[
            AcquisitionSource(
                filename=name,
                url="https://example.org/dev.json",
                format="json_array",
                splits=["dev"],
                expected_sha256=hashlib.sha256(data).hexdigest() if pinned else None,
                expected_bytes=len(data) if pinned else None,
            )
        ],
    )


def manifest(root: Path) -> dict[str, Any]:
    result = json.loads((root / "finqa/fixture-v1/acquisition.json").read_text())
    assert isinstance(result, dict)
    return result


@pytest.mark.parametrize(
    ("cafile", "capath"), [(None, None), ("approved.pem", None), (None, "approved-cas")]
)
def test_owned_client_verifies_tls_and_reuses_receipt_without_tls_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cafile: str | None, capath: str | None
) -> None:
    data = payload()
    context = ssl.create_default_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    for name, value in (("SSL_CERT_FILE", cafile), ("SSL_CERT_DIR", capath)):
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    context_calls: list[tuple[str | None, str | None]] = []

    def create_context(*, cafile: str | None, capath: str | None) -> ssl.SSLContext:
        context_calls.append((cafile, capath))
        return context

    client = httpx.Client(transport=httpx.MockTransport(lambda r: response(data)))
    client_calls: list[float] = []

    def create_client(*, timeout: float, verify: ssl.SSLContext) -> httpx.Client:
        assert verify is context
        client_calls.append(timeout)
        return client

    monkeypatch.setattr(prepare.ssl, "create_default_context", create_context)
    monkeypatch.setattr(prepare.httpx, "Client", create_client)
    report = acquire_dataset("finqa", plan(data), tmp_path, timeout_seconds=19)
    assert report["status"] == "acquired"
    assert context_calls == [(cafile, capath)]
    assert client_calls == [19]
    assert client.is_closed
    repeated = acquire_dataset("finqa", plan(data), tmp_path)
    assert repeated["source_checksum"] == report["source_checksum"]
    assert len(context_calls) == len(client_calls) == 1


def test_acquires_exact_bytes_counts_and_provenance_then_reuses_offline(tmp_path: Path) -> None:
    data = payload()
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response(data, headers={"ETag": '"source-v1"'})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_dataset("finqa", plan(data), tmp_path, client=client)
    assert report["status"] == "acquired"
    assert report["executed_questions"] == 0
    assert report["data_snapshot_available"] is False
    path = tmp_path / "finqa/fixture-v1/dev.json"
    assert path.read_bytes() == data
    state = manifest(tmp_path)
    receipt = state["sources"]["dev.json"]
    assert receipt["counts"] == {"dev": {"records": 3, "questions": 3}}
    assert receipt["sha256"] == hashlib.sha256(data).hexdigest()
    assert receipt["acquired_at"] and state["source_plan"]["license"] == "fixture-only"
    assert receipt["resolved_url"] == "https://example.org/dev.json"
    before = (path.parent / "acquisition.json").read_bytes()
    # No HTTP client is needed or created to verify already-acquired bytes.
    repeated = acquire_dataset("finqa", plan(data), tmp_path)
    assert repeated["source_checksum"] == report["source_checksum"]
    assert (path.parent / "acquisition.json").read_bytes() == before
    assert len(calls) == 1


@pytest.mark.parametrize("damage", ["corrupt", "missing", "different-size"])
def test_completed_source_changes_fail_without_redownload(tmp_path: Path, damage: str) -> None:
    data = payload()
    with httpx.Client(transport=httpx.MockTransport(lambda r: response(data))) as c:
        acquire_dataset("finqa", plan(data), tmp_path, client=c)
    path = tmp_path / "finqa/fixture-v1/dev.json"
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"X" * (len(data) if damage == "corrupt" else 1))
    with pytest.raises(ValueError, match=r"checksum|missing|changed size"):
        acquire_dataset("finqa", plan(data), tmp_path)


def test_changed_plan_requires_new_release(tmp_path: Path) -> None:
    data = payload()
    original = plan(data)
    with httpx.Client(transport=httpx.MockTransport(lambda r: response(data))) as c:
        acquire_dataset("finqa", original, tmp_path, client=c)
    altered = original.model_copy(update={"revision": "different-revision"})
    with pytest.raises(ValueError, match="plan changed"):
        acquire_dataset("finqa", altered, tmp_path)


class InterruptedBody(httpx.SyncByteStream):
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self) -> Iterator[bytes]:
        yield self.data
        raise httpx.ReadError("fixture interruption")


@pytest.mark.parametrize(
    "mode", ["range", "ignored", "changed-etag", "wrong-range", "wrong-total", "no-validator"]
)
def test_interrupted_transfers_resume_or_restart_without_mixed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setattr(prepare, "CHUNK_BYTES", 16)
    data = payload()
    source_plan = plan(data, pinned=mode != "no-validator")
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        headers = {"Content-Length": str(len(data))}
        if mode != "no-validator":
            headers["ETag"] = '"v1"'
        if len(calls) == 1:
            return httpx.Response(200, headers=headers, stream=InterruptedBody(data[:64]))
        if mode in {"ignored", "no-validator"}:
            return response(data, headers=headers)
        offset = int(request.headers["Range"].split("=")[1].rstrip("-"))
        assert offset == 64
        assert request.headers["If-Range"] == '"v1"'
        total = len(data) + (1 if mode == "wrong-total" else 0)
        start = offset + (1 if mode == "wrong-range" else 0)
        return response(
            data[offset:],
            206,
            headers={
                "Content-Range": f"bytes {start}-{total - 1}/{total}",
                "ETag": '"v2"' if mode == "changed-etag" else '"v1"',
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        with pytest.raises(ValueError, match="retained checkpoints"):
            acquire_dataset("finqa", source_plan, tmp_path, client=c)
        receipt = manifest(tmp_path)["sources"]["dev.json"]
        assert receipt["downloaded_bytes"] == 64
        partial = tmp_path / "finqa/fixture-v1/dev.json.part"
        # Simulate uncheckpointed trailing bytes from an abruptly terminated writer.
        with partial.open("ab") as stream:
            stream.write(b"uncheckpointed")
        if mode in {"changed-etag", "wrong-range", "wrong-total"}:
            with pytest.raises(ValueError, match=r"changed|invalid"):
                acquire_dataset("finqa", source_plan, tmp_path, client=c)
            assert not partial.with_suffix("").exists()
        else:
            acquire_dataset("finqa", source_plan, tmp_path, client=c)
            assert partial.with_suffix("").read_bytes() == data
            if mode == "no-validator":
                assert "Range" not in calls[1].headers


def test_corrupt_partial_is_not_resumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prepare, "CHUNK_BYTES", 16)
    data = payload()
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    headers={"Content-Length": str(len(data)), "ETag": '"v1"'},
                    stream=InterruptedBody(data[:64]),
                )
            )
        ) as c,
        pytest.raises(ValueError, match="retained checkpoints"),
    ):
        acquire_dataset("finqa", plan(data), tmp_path, client=c)
    partial = tmp_path / "finqa/fixture-v1/dev.json.part"
    partial.write_bytes(b"X" * 64)
    with pytest.raises(ValueError, match="checkpoint"):
        acquire_dataset("finqa", plan(data), tmp_path)


def test_crash_after_verification_recovers_without_another_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = payload()
    replace = prepare.os.replace

    def fail_publication(source: Path, target: Path) -> None:
        if str(source).endswith(".part"):
            raise OSError("fixture publication crash")
        replace(source, target)

    with monkeypatch.context() as m:
        m.setattr(prepare.os, "replace", fail_publication)
        with (
            httpx.Client(transport=httpx.MockTransport(lambda r: response(data))) as c,
            pytest.raises(OSError, match="publication crash"),
        ):
            acquire_dataset("finqa", plan(data), tmp_path, client=c)
    assert manifest(tmp_path)["sources"]["dev.json"]["status"] == "verified"
    acquire_dataset("finqa", plan(data), tmp_path)
    assert (tmp_path / "finqa/fixture-v1/dev.json").read_bytes() == data


def test_crash_after_publication_recovers_record_without_another_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = payload()
    original = prepare._write_manifest

    def fail_completion(path: Path, value: prepare.AcquisitionManifest) -> None:
        if value.sources["dev.json"].status == "complete":
            raise OSError("fixture completion crash")
        original(path, value)

    with monkeypatch.context() as m:
        m.setattr(prepare, "_write_manifest", fail_completion)
        with (
            httpx.Client(transport=httpx.MockTransport(lambda r: response(data))) as c,
            pytest.raises(OSError, match="completion crash"),
        ):
            acquire_dataset("finqa", plan(data), tmp_path, client=c)
    assert manifest(tmp_path)["sources"]["dev.json"]["status"] == "verified"
    assert (tmp_path / "finqa/fixture-v1/dev.json").exists()
    acquire_dataset("finqa", plan(data), tmp_path)
    assert manifest(tmp_path)["sources"]["dev.json"]["status"] == "complete"


def test_existing_unowned_source_and_concurrent_writer_are_refused(tmp_path: Path) -> None:
    directory = tmp_path / "finqa/fixture-v1"
    directory.mkdir(parents=True)
    (directory / "dev.json").write_bytes(payload())
    with pytest.raises(ValueError, match="without provenance"):
        acquire_dataset("finqa", plan(payload()), tmp_path)
    (directory / "dev.json").unlink()
    lock = _WriterLock(directory / "acquisition.lock")
    try:
        with pytest.raises(ValueError, match="locked"):
            acquire_dataset("finqa", plan(payload()), tmp_path)
    finally:
        lock.close()


@pytest.mark.parametrize(
    "case", ["wrong-checksum", "wrong-size", "html", "truncated-json", "empty-json"]
)
def test_invalid_downloads_are_never_published(tmp_path: Path, case: str) -> None:
    data = payload()
    source_plan = plan(data, pinned=case in {"wrong-checksum", "wrong-size"})
    received = {
        "wrong-checksum": b"X" * len(data),
        "wrong-size": b"short",
        "html": b"<html>error</html>",
        "truncated-json": b'[{"x":',
        "empty-json": b"[]",
    }[case]
    with (
        httpx.Client(transport=httpx.MockTransport(lambda r: response(received))) as c,
        pytest.raises(ValueError),
    ):
        acquire_dataset("finqa", source_plan, tmp_path, client=c)
    assert not (tmp_path / "finqa/fixture-v1/dev.json").exists()


@pytest.mark.parametrize("text", ['[{"x":1},]', '[{"x":1}] trailing', '{"x":1}', "[1]", '[{"x":1}'])
def test_malformed_array_structure_is_rejected(tmp_path: Path, text: str) -> None:
    path = tmp_path / "raw.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        inspect_raw_source(path, plan(payload()).sources[0])


def test_raw_json_is_read_incrementally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prepare, "CHUNK_BYTES", 3)

    class BoundedReader(io.StringIO):
        def read(self, size: int = -1) -> str:
            assert 0 <= size <= 3
            return super().read(size)

    assert list(prepare._json_records(BoundedReader('[{"unicode":"é"},{"x":[1,2]}]'))) == [
        {"unicode": "é"},
        {"x": [1, 2]},
    ]


def test_drop_archive_counts_questions_without_extracting_files(tmp_path: Path) -> None:
    path = tmp_path / "drop.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for split in ["train", "dev"]:
            archive.writestr(
                f"drop_dataset/drop_dataset_{split}.json",
                json.dumps(
                    {
                        "passage-a": {
                            "passage": "text",
                            "qa_pairs": [{"query_id": "a"}, {"query_id": "b"}],
                        },
                        "passage-b": {"passage": "text", "qa_pairs": [{"query_id": "c"}]},
                    }
                ),
            )
        archive.writestr("../outside.txt", "not extracted")
    source = AcquisitionSource(
        filename="drop.zip",
        url="https://example.org/drop.zip",
        format="drop_zip",
        splits=["train", "dev"],
    )
    counts = inspect_raw_source(path, source)
    assert counts["train"].records == 2 and counts["train"].questions == 3
    assert counts["dev"] == counts["train"]
    assert not (tmp_path / "outside.txt").exists()


def test_drop_archive_missing_or_duplicate_members_fail(tmp_path: Path) -> None:
    source = AcquisitionSource(
        filename="drop.zip",
        url="https://example.org/drop.zip",
        format="drop_zip",
        splits=["train", "dev"],
    )
    path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("unexpected.json", "{}")
    with pytest.raises(ValueError, match="requires one"):
        inspect_raw_source(path, source)


@pytest.mark.parametrize(
    "filename", ["../escape", "bad/name", r"bad\name", ".", "acquisition.json", "data.part"]
)
def test_catalog_rejects_unsafe_or_reserved_names(filename: str) -> None:
    with pytest.raises(ValidationError):
        AcquisitionSource(
            filename=filename, url="https://example.org/raw", format="json_array", splits=["dev"]
        )


def test_offline_source_catalog_and_scientific_readiness(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = load_study_bundle()
    assert bundle.datasets.acquisition is not None
    assert bundle.datasets.snapshot_id is None
    assert bundle.datasets.datasets.finqa.release is None
    assert main(["data", "sources"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["data_snapshot_available"] is False
    assert report["runtime_contacted"] is False
    assert set(report["acquisition"]) == {"schema_version", "hotpotqa", "drop", "finqa"}


def test_explicit_mirror_preserves_origin_and_checks_pinned_bytes(tmp_path: Path) -> None:
    data = payload()
    original = plan(data)
    entry = original.sources[0].model_dump() | {
        "download_url": "https://mirror.example.org/dev.json",
        "checksum_reference": "https://example.org/published-checksums",
    }
    source = AcquisitionSource.model_validate(entry)
    source_plan = AcquisitionDataset.model_validate(original.model_dump() | {"sources": [source]})

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "mirror.example.org"
        return response(data)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        acquire_dataset("finqa", source_plan, tmp_path, client=client)
    state = manifest(tmp_path)
    assert state["source_plan"]["sources"][0]["url"] == "https://example.org/dev.json"
    assert state["sources"]["dev.json"]["resolved_url"] == "https://mirror.example.org/dev.json"


@pytest.mark.parametrize("field", ["expected_sha256", "checksum_reference"])
def test_unpinned_download_mirrors_are_rejected(field: str) -> None:
    entry = plan(payload()).sources[0].model_dump() | {
        "download_url": "https://mirror.example.org/dev.json",
        "checksum_reference": "https://example.org/checksums",
        field: None,
    }
    with pytest.raises(ValidationError, match="pinned checksum"):
        AcquisitionSource.model_validate(entry)


def test_bad_split_is_rejected_before_network_or_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No 'test'"):
        acquire_dataset("finqa", plan(payload()), tmp_path, split="test")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_timeout_is_rejected_before_writes(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        acquire_dataset("finqa", plan(payload()), tmp_path, timeout_seconds=timeout)
    assert list(tmp_path.iterdir()) == []
