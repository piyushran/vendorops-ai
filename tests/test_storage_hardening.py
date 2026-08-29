from pathlib import Path

import pytest

from app.storage.backends import LocalObjectStorage, StorageError
from app.storage.integrity import sha256_bytes
from app.storage.keying import artifact_key


def test_artifact_key_is_workspace_scoped_and_sanitized() -> None:
    key = artifact_key(
        "workspace/../finance",
        "artifact-123",
        "../../vendor invoice.pdf",
    )

    assert key == "workspaces/workspace_.._finance/artifacts/artifact-123/vendor_invoice.pdf"
    assert ".." not in key.split("/")[-1]


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)

    with pytest.raises(StorageError):
        storage.put_bytes(
            key="../../outside.txt",
            content=b"secret",
            content_type="text/plain",
        )


def test_local_storage_round_trip_is_binary_safe(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    stored = storage.put_bytes(
        key="workspaces/ws-1/artifacts/file-1/invoice.pdf",
        content=b"%PDF-test\x00\xff",
        content_type="application/pdf",
    )

    assert stored.size_bytes == 11
    assert storage.exists(stored.uri)
    assert storage.read_bytes(stored.uri) == b"%PDF-test\x00\xff"


def test_local_storage_delete(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    stored = storage.put_bytes(
        key="workspaces/ws-1/artifacts/file-1/invoice.pdf",
        content=b"invoice",
        content_type="application/pdf",
    )

    assert storage.exists(stored.uri)
    storage.delete(stored.uri)
    assert not storage.exists(stored.uri)


def test_sha256_bytes_is_deterministic() -> None:
    content = b"vendorops-artifact"

    digest = sha256_bytes(content)

    assert digest == sha256_bytes(content)
    assert len(digest) == 64


def test_sha256_bytes_changes_when_content_changes() -> None:
    assert sha256_bytes(b"invoice-a") != sha256_bytes(b"invoice-b")
