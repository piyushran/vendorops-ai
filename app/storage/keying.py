"""Deterministic workspace-scoped object-key helpers."""

from __future__ import annotations

import re


_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def artifact_key(workspace_id: str, artifact_id: str, filename: str | None = None) -> str:
    """Return a private object key that cannot cross workspace boundaries."""
    workspace = _safe_segment(workspace_id, "workspace_id")
    artifact = _safe_segment(artifact_id, "artifact_id")
    suffix = ""
    if filename:
        safe_name = _safe_segment(filename, "filename")
        suffix = f"/{safe_name}"
    return f"workspaces/{workspace}/artifacts/{artifact}{suffix}"


def _safe_segment(value: str, field_name: str) -> str:
    cleaned = _SAFE_SEGMENT.sub("_", str(value).strip())
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"{field_name} must contain a safe value.")
    return cleaned
