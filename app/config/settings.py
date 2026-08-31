from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VendorOps AI"
    app_env: str = "local"
    app_debug: bool = True
    api_prefix: str = "/v1"

    database_url: str = "sqlite+aiosqlite:///./vendorops.db"
    storage_backend: str = Field(default="local", pattern="^(local|s3|azure|gcs)$")
    max_upload_size_mb: int = Field(default=25, ge=1, le=250)
    local_storage_dir: Path = Field(default=Path("./storage"))
    reports_dir: Path = Field(default=Path("./reports_out"))
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_prefix: str = "vendorops"
    s3_presign_ttl_seconds: int = Field(default=900, ge=60, le=86400)

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    log_level: str = "INFO"
    log_format: str = "json"
    extraction_max_attempts: int = Field(default=3, ge=1, le=5)
    extraction_retry_base_seconds: float = Field(default=0.4, ge=0.0, le=10.0)
    extraction_review_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    worker_poll_interval_seconds: float = Field(default=1.0, ge=0.05, le=60.0)
    worker_lease_duration_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)
    worker_heartbeat_interval_seconds: float = Field(default=15.0, ge=0.2, le=1800.0)
    worker_max_attempts: int = Field(default=3, ge=1, le=100)
    worker_retry_base_seconds: float = Field(default=5.0, ge=0.0, le=3600.0)
    worker_retry_max_seconds: float = Field(default=300.0, ge=0.0, le=86400.0)
    llm_input_cost_per_1k_tokens: float = Field(default=0.0004, ge=0.0)
    llm_output_cost_per_1k_tokens: float = Field(default=0.0016, ge=0.0)
    auth_token_ttl_hours: int = Field(default=12, ge=1, le=720)
    demo_admin_email: str = "admin@vendorops.ai"
    demo_admin_password: str = "VendorOpsDemo123!"
    default_organization_name: str = "VendorOps Demo Co"
    default_workspace_name: str = "Finance Operations"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
