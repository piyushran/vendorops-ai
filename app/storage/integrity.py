"""Artifact integrity and idempotency helpers."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for artifact bytes."""
    return hashlib.sha256(data).hexdigest()
