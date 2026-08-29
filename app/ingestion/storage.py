import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.storage.backends import ObjectStorageBackend
from app.storage.keying import artifact_key

ALLOWED_FILE_EXTENSIONS = {".csv", ".eml", ".pdf", ".txt"}
CHUNK_SIZE_BYTES = 1024 * 1024
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
REPEATED_UNDERSCORE_PATTERN = re.compile(r"_+")


@dataclass(frozen=True)
class StoredUpload:
    file_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    storage_path: str
    object_key: str


def validate_upload_filename(filename: str | None) -> str:
    if not filename:
        raise ValueError("Uploaded file must include a filename.")

    safe_name = sanitize_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_FILE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_FILE_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{suffix}'. Allowed types: {allowed}.")

    return safe_name


async def store_upload(
    upload_file: UploadFile,
    storage: ObjectStorageBackend,
    *,
    workspace_id: str,
    max_size_bytes: int,
) -> StoredUpload:
    original_filename = validate_upload_filename(upload_file.filename)
    content = await read_upload_bytes(upload_file, max_size_bytes=max_size_bytes)

    if not content:
        raise ValueError("Uploaded file is empty.")

    file_id = str(uuid4())
    digest = sha256(content).hexdigest()
    object_key = artifact_key(workspace_id, file_id, original_filename)
    stored_object = storage.put_bytes(
        key=object_key,
        content=content,
        content_type=upload_file.content_type or "application/octet-stream",
    )

    return StoredUpload(
        file_id=file_id,
        original_filename=original_filename,
        content_type=upload_file.content_type or "application/octet-stream",
        size_bytes=len(content),
        sha256_hash=digest,
        storage_path=stored_object.uri,
        object_key=object_key,
    )


async def read_upload_bytes(upload_file: UploadFile, *, max_size_bytes: int) -> bytes:
    chunks = []
    total_size = 0
    while True:
        chunk = await upload_file.read(CHUNK_SIZE_BYTES)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size_bytes:
            max_mb = max_size_bytes / (1024 * 1024)
            raise ValueError(f"Uploaded file exceeds the {max_mb:.0f} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace(" ", "_")
    name = SAFE_FILENAME_PATTERN.sub("_", name)
    name = REPEATED_UNDERSCORE_PATTERN.sub("_", name).strip("_")
    if not name or name in {".", ".."}:
        raise ValueError("Uploaded file must include a safe filename.")
    return name
