from dataclasses import dataclass

from app.storage.backends import StoredObject, StorageError


@dataclass(frozen=True)
class S3Config:
    bucket: str
    region: str | None = None
    endpoint_url: str | None = None
    prefix: str = "vendorops"


class S3ObjectStorage:
    """S3-compatible private object storage using the AWS SDK default credential chain."""

    name = "s3"

    def __init__(self, config: S3Config) -> None:
        if not config.bucket:
            raise ValueError("S3 bucket must be configured for the S3 storage backend.")
        import boto3

        self.config = config
        self.client = boto3.client(
            "s3",
            region_name=config.region,
            endpoint_url=config.endpoint_url,
        )

    def _key(self, key: str) -> str:
        clean = key.lstrip("/")
        return f"{self.config.prefix.rstrip('/')}/{clean}" if self.config.prefix else clean

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        object_key = self._key(key)
        try:
            self.client.put_object(
                Bucket=self.config.bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
            )
        except Exception as exc:
            raise StorageError(f"Failed to store S3 object '{object_key}'.") from exc
        return StoredObject(
            key=object_key,
            uri=f"s3://{self.config.bucket}/{object_key}",
            size_bytes=len(content),
            content_type=content_type,
        )

    def read_bytes(self, uri: str) -> bytes:
        bucket, key = self._parse_uri(uri)
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise StorageError(f"Failed to read S3 object '{uri}'.") from exc

    def exists(self, uri: str) -> bool:
        bucket, key = self._parse_uri(uri)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self.client.exceptions.ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise StorageError(f"Failed to inspect S3 object '{uri}'.") from exc

    def presign_get(self, uri: str, *, expires_in: int = 900) -> str:
        bucket, key = self._parse_uri(uri)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            raise StorageError(f"Failed to create signed URL for '{uri}'.") from exc

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, str]:
        prefix = "s3://"
        if not uri.startswith(prefix) or "/" not in uri[len(prefix) :]:
            raise StorageError(f"Invalid S3 URI '{uri}'.")
        bucket, key = uri[len(prefix) :].split("/", 1)
        if not bucket or not key:
            raise StorageError(f"Invalid S3 URI '{uri}'.")
        return bucket, key
