from app.config.settings import Settings
from app.storage.backends import (
    LocalObjectStorage,
    ObjectStorageBackend,
    UnsupportedStorageBackendError,
)
from app.storage.s3 import S3Config, S3ObjectStorage


def get_object_storage(settings: Settings) -> ObjectStorageBackend:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.local_storage_dir)
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET must be configured when STORAGE_BACKEND=s3.")
        return S3ObjectStorage(
            S3Config(
                bucket=settings.s3_bucket,
                region=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
                prefix=settings.s3_prefix,
            )
        )

    raise UnsupportedStorageBackendError(
        f"Storage backend '{settings.storage_backend}' is configured but not implemented. "
        "Use STORAGE_BACKEND=local or STORAGE_BACKEND=s3 for this build."
    )


def get_report_storage(settings: Settings) -> ObjectStorageBackend:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.reports_dir)

    return get_object_storage(settings)
