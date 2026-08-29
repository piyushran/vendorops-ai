"""S3-compatible object storage adapter for production deployments."""

from __future__ import annotations

import io
from dataclasses import dataclass

try:
    import boto3
except ImportError:  # pragma: no cover - exercised when the optional extra is absent
    boto3 = None


@dataclass(frozen=True)
class S3Storage:
    """Minimal S3-compatible storage boundary.

    The adapter intentionally contains no application/business logic. Callers provide
    a fully scoped object key such as ``workspaces/<workspace_id>/artifacts/<id>``.
    """

    bucket: str
    endpoint_url: str | None = None
    region_name: str | None = None

    def _client(self):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 storage")
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client().put_object(
            Bucket=self.bucket,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=content_type,
        )

    def get(self, key: str) -> bytes:
        response = self._client().get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client().head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return False
            raise

    def presigned_get_url(self, key: str, expires_in: int = 900) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
