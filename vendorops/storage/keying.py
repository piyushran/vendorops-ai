"""Deterministic tenant/workspace scoped object-key helpers."""

from __future__ import annotations


def artifact_key(workspace_id: str, artifact_id: str, filename: str | None = None) -> str:
    """Return a private, collision-resistant object key scoped to a workspace."""
    suffix = ""
    if filename:
        safe_name = filename.replace("/", "_").replace("\\", "_").strip()
        suffix = f"/{safe_name}" if safe_name else ""
    return f"workspaces/{workspace_id}/artifacts/{artifact_id}{suffix}"
