from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class UploadedFileResponse(BaseModel):
    file_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    storage_path: str
    created_at: datetime


class CreateJobRequest(BaseModel):
    file_id: UUID
    pipeline: str = Field(default="document_extraction", min_length=1, max_length=100)


class ProcessingJobResponse(BaseModel):
    job_id: UUID
    file_id: UUID
    pipeline: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    next_run_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorResponse(BaseModel):
    detail: str


class DatabaseSummaryResponse(BaseModel):
    tables: list[str]


class ParsedPageResponse(BaseModel):
    page_number: int
    text: str


class ParsedTableResponse(BaseModel):
    name: str
    columns: list[str]
    rows: list[dict]


class ParsedDocumentResponse(BaseModel):
    source_path: str
    file_type: str
    text: str
    metadata: dict
    pages: list[ParsedPageResponse]
    tables: list[ParsedTableResponse]


class ExtractedRecordResponse(BaseModel):
    record_id: UUID
    file_id: UUID
    job_id: UUID | None = None
    record_type: str
    vendor_name: str | None = None
    external_reference: str | None = None
    confidence: float | None = None
    normalized_payload: dict
    raw_payload: dict | None = None
    created_at: datetime


class ValidationErrorResponse(BaseModel):
    validation_error_id: UUID
    record_id: UUID | None = None
    job_id: UUID | None = None
    field_name: str | None = None
    error_type: str
    message: str
    severity: str
    created_at: datetime


class ExtractionRunResponse(BaseModel):
    job: ProcessingJobResponse
    record: ExtractedRecordResponse
    validation_errors: list[ValidationErrorResponse]


class CreateReportRequest(BaseModel):
    report_type: str = Field(default="summary", pattern="^(summary|records)$")
    format: str = Field(default="json", pattern="^(json|csv)$")


class GeneratedReportResponse(BaseModel):
    report_id: UUID
    report_type: str
    status: str
    parameters: dict
    storage_path: str | None = None
    created_at: datetime


class AuditLogResponse(BaseModel):
    audit_log_id: UUID
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    details: dict | None = None
    created_at: datetime


class ExtractionErrorResponse(BaseModel):
    error_id: UUID
    job_id: UUID | None = None
    file_id: UUID | None = None
    stage: str
    error_type: str
    message: str
    retryable: bool
    attempt: int
    details: dict | None = None
    created_at: datetime


class AnalyticsKpiResponse(BaseModel):
    label: str
    value: str
    detail: str
    trend: str
    status: str


class AnalyticsRankedItemResponse(BaseModel):
    label: str
    value: float
    detail: str | None = None


class AnalyticsTrendPointResponse(BaseModel):
    date: str
    value: float
    detail: str | None = None


class AnalyticsBlockedJobResponse(BaseModel):
    job_id: UUID
    file_id: UUID
    status: str
    pipeline: str
    age_hours: float
    error_message: str | None = None


class AnalyticsCostResponse(BaseModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    billable_records: int
    mock_records: int


class AnalyticsDashboardResponse(BaseModel):
    generated_at: datetime
    kpis: list[AnalyticsKpiResponse]
    processed_volume: dict[str, int]
    validation_failures_by_document_type: list[AnalyticsRankedItemResponse]
    error_sources: list[AnalyticsRankedItemResponse]
    extraction_accuracy_over_time: list[AnalyticsTrendPointResponse]
    retry_hotspots: list[AnalyticsRankedItemResponse]
    blocked_jobs: list[AnalyticsBlockedJobResponse]
    llm_cost: AnalyticsCostResponse
    business_reports: list[AnalyticsRankedItemResponse]
    analyst_notes: list[str]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class WorkspaceSummaryResponse(BaseModel):
    workspace_id: UUID
    name: str
    slug: str
    role: str


class OrganizationSummaryResponse(BaseModel):
    organization_id: UUID
    name: str
    slug: str
    plan: str


class AuthUserResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    organization: OrganizationSummaryResponse
    workspace: WorkspaceSummaryResponse
    permissions: list[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthUserResponse
