from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class StorageError(Exception):
    """Raised when a storage backend cannot complete an operation."""


class UnsupportedStorageBackendError(StorageError):
    """Raised when a configured storage backend has not been implemented."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str
    size_bytes: int
    content_type: str
    local_path: Path | None = None


class ObjectStorageBackend(Protocol):
    name: str

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        """Persist bytes under a storage key."""

    def read_bytes(self, uri: str) -> bytes:
        """Read bytes from a storage URI."""

    def exists(self, uri: str) -> bool:
        """Return whether a storage URI exists."""

    def delete(self, uri: str) -> None:
        """Delete a stored object."""


class LocalObjectStorage:
    name = "local"

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(
            key=key,
            uri=str(path),
            size_bytes=len(content),
            content_type=content_type,
            local_path=path,
        )

    def read_bytes(self, uri: str) -> bytes:
        path = self._path_from_uri(uri)
        if not path.exists() or not path.is_file():
            raise StorageError(f"Stored object '{uri}' was not found.")
        return path.read_bytes()

    def exists(self, uri: str) -> bool:
        path = self._path_from_uri(uri)
        return path.exists() and path.is_file()

    def delete(self, uri: str) -> None:
        path = self._path_from_uri(uri)
        if not path.exists():
            return
        if not path.is_file():
            raise StorageError(f"Stored object '{uri}' is not a file.")
        path.unlink()

    def _path_for_key(self, key: str) -> Path:
        candidate = (self.root_dir / key).resolve()
        root = self.root_dir.resolve()
        if not candidate.is_relative_to(root):
            raise StorageError("Storage key resolves outside the configured storage root.")
        return candidate

    def _path_from_uri(self, uri: str) -> Path:
        candidate = Path(uri).resolve()
        root = self.root_dir.resolve()
        if not candidate.is_relative_to(root):
            raise StorageError("Storage URI resolves outside the configured storage root.")
        return candidate
