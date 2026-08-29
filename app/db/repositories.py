from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    ExtractedRecord,
    ExtractionErrorLog,
    GeneratedReport,
    ProcessingJob,
    UploadedFile,
    ValidationError,
)
from app.extraction.schemas import ExtractedBusinessRecord
from app.validation.rules import ValidationFinding


async def create_uploaded_file(
    session: AsyncSession,
    *,
    file_id: UUID,
    organization_id: UUID | str | None = None,
    workspace_id: UUID | str | None = None,
    original_filename: str,
    content_type: str,
    file_type: str,
    size_bytes: int,
    sha256_hash: str,
    storage_path: str,
) -> UploadedFile:
    uploaded_file = UploadedFile(
        id=str(file_id),
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        original_filename=original_filename,
        content_type=content_type,
        file_type=file_type,
        size_bytes=size_bytes,
        sha256_hash=sha256_hash,
        storage_path=storage_path,
    )
    session.add(uploaded_file)
    await create_audit_log(
        session,
        action="file.uploaded",
        entity_type="uploaded_file",
        entity_id=str(file_id),
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={
            "original_filename": original_filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256_hash": sha256_hash,
        },
    )
    await session.commit()
    await session.refresh(uploaded_file)
    return uploaded_file


async def get_uploaded_file(
    session: AsyncSession,
    file_id: UUID,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> UploadedFile | None:
    uploaded_file = await session.get(UploadedFile, str(file_id))
    if uploaded_file is None:
        return None
    if not is_tenant_match(
        uploaded_file,
        organization_id=organization_id,
        workspace_id=workspace_id,
    ):
        return None
    return uploaded_file


async def create_processing_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    file_id: UUID,
    pipeline: str,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    max_attempts: int = 3,
) -> ProcessingJob:
    job = ProcessingJob(
        id=str(job_id),
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        file_id=str(file_id),
        pipeline=pipeline,
        status="queued",
        max_attempts=max_attempts,
    )
    session.add(job)
    await create_audit_log(
        session,
        action="job.created",
        entity_type="processing_job",
        entity_id=str(job_id),
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={"file_id": str(file_id), "pipeline": pipeline},
    )
    await session.commit()
    await session.refresh(job)
    return job


async def get_processing_job(
    session: AsyncSession,
    job_id: UUID,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> ProcessingJob | None:
    job = await session.get(ProcessingJob, str(job_id))
    if job is None:
        return None
    if not is_tenant_match(job, organization_id=organization_id, workspace_id=workspace_id):
        return None
    return job


async def update_processing_job_status(
    session: AsyncSession,
    *,
    job: ProcessingJob,
    status: str,
    error_message: str | None = None,
) -> ProcessingJob:
    job.status = status
    job.error_message = error_message
    await create_audit_log(
        session,
        action="job.status_updated",
        entity_type="processing_job",
        entity_id=job.id,
        organization_id=UUID(job.organization_id) if job.organization_id else None,
        workspace_id=UUID(job.workspace_id) if job.workspace_id else None,
        details={"status": status, "error_message": error_message},
    )
    await session.commit()
    await session.refresh(job)
    return job


async def create_extracted_record(
    session: AsyncSession,
    *,
    file_id: UUID,
    job_id: UUID | None,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    extracted: ExtractedBusinessRecord,
    raw_payload: dict,
) -> ExtractedRecord:
    if job_id is not None:
        existing = (
            await session.execute(
                select(ExtractedRecord).where(ExtractedRecord.job_id == str(job_id))
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    record = ExtractedRecord(
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        file_id=str(file_id),
        job_id=str(job_id) if job_id else None,
        record_type=extracted.record_type.value,
        vendor_name=extracted.vendor_name,
        external_reference=extracted.document_id,
        normalized_payload=extracted.model_dump(mode="json"),
        raw_payload=raw_payload,
        confidence=extracted.confidence,
    )
    session.add(record)
    await session.flush()
    await create_audit_log(
        session,
        action="record.extracted",
        entity_type="extracted_record",
        entity_id=record.id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={
            "file_id": str(file_id),
            "job_id": str(job_id) if job_id else None,
            "record_type": extracted.record_type.value,
            "confidence": extracted.confidence,
            "provider": raw_payload.get("provider"),
        },
    )
    await session.commit()
    await session.refresh(record)
    return record


async def list_extracted_records(
    session: AsyncSession,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> list[ExtractedRecord]:
    query = apply_tenant_filter(
        select(ExtractedRecord),
        ExtractedRecord,
        organization_id=organization_id,
        workspace_id=workspace_id,
    ).order_by(ExtractedRecord.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_extracted_record(
    session: AsyncSession,
    record_id: UUID,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> ExtractedRecord | None:
    record = await session.get(ExtractedRecord, str(record_id))
    if record is None:
        return None
    if not is_tenant_match(record, organization_id=organization_id, workspace_id=workspace_id):
        return None
    return record


async def create_validation_errors(
    session: AsyncSession,
    *,
    record_id: UUID,
    job_id: UUID | None,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    findings: list[ValidationFinding],
) -> list[ValidationError]:
    validation_errors = [
        ValidationError(
            organization_id=str(organization_id) if organization_id else None,
            workspace_id=str(workspace_id) if workspace_id else None,
            record_id=str(record_id),
            job_id=str(job_id) if job_id else None,
            field_name=finding.field_name,
            error_type=finding.error_type,
            message=finding.message,
            severity=finding.severity.value,
        )
        for finding in findings
    ]
    session.add_all(validation_errors)
    await create_audit_log(
        session,
        action="record.validated",
        entity_type="extracted_record",
        entity_id=str(record_id),
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={
            "job_id": str(job_id) if job_id else None,
            "finding_count": len(findings),
            "error_count": sum(1 for finding in findings if finding.severity.value == "error"),
        },
    )
    await session.commit()
    for validation_error in validation_errors:
        await session.refresh(validation_error)
    return validation_errors


async def list_validation_errors(
    session: AsyncSession,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> list[ValidationError]:
    query = apply_tenant_filter(
        select(ValidationError),
        ValidationError,
        organization_id=organization_id,
        workspace_id=workspace_id,
    ).order_by(ValidationError.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_validation_errors_for_record(
    session: AsyncSession,
    record_id: UUID,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> list[ValidationError]:
    query = apply_tenant_filter(
        select(ValidationError).where(ValidationError.record_id == str(record_id)),
        ValidationError,
        organization_id=organization_id,
        workspace_id=workspace_id,
    ).order_by(ValidationError.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_generated_report(
    session: AsyncSession,
    *,
    report_type: str,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    parameters: dict,
    storage_path: str,
    status: str = "created",
) -> GeneratedReport:
    report = GeneratedReport(
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        report_type=report_type,
        status=status,
        parameters=parameters,
        storage_path=storage_path,
    )
    session.add(report)
    await session.flush()
    await create_audit_log(
        session,
        action="report.generated",
        entity_type="generated_report",
        entity_id=report.id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={
            "report_type": report_type,
            "storage_path": storage_path,
            "parameters": parameters,
        },
    )
    await session.commit()
    await session.refresh(report)
    return report


async def list_generated_reports(
    session: AsyncSession,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> list[GeneratedReport]:
    query = apply_tenant_filter(
        select(GeneratedReport),
        GeneratedReport,
        organization_id=organization_id,
        workspace_id=workspace_id,
    ).order_by(GeneratedReport.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_generated_report(
    session: AsyncSession,
    report_id: UUID,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> GeneratedReport | None:
    report = await session.get(GeneratedReport, str(report_id))
    if report is None:
        return None
    if not is_tenant_match(report, organization_id=organization_id, workspace_id=workspace_id):
        return None
    return report


async def create_audit_log(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    organization_id: UUID | str | None = None,
    workspace_id: UUID | str | None = None,
    details: dict | None = None,
    actor: str = "system",
) -> AuditLog:
    audit_log = AuditLog(
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    session.add(audit_log)
    return audit_log


async def list_audit_logs(
    session: AsyncSession,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    limit: int = 50,
) -> list[AuditLog]:
    query = (
        apply_tenant_filter(
            select(AuditLog),
            AuditLog,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_audit_logs(session: AsyncSession) -> int:
    result = await session.execute(select(AuditLog))
    return len(result.scalars().all())


async def create_extraction_error(
    session: AsyncSession,
    *,
    stage: str,
    error_type: str,
    message: str,
    retryable: bool,
    attempt: int,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    job_id: UUID | None = None,
    file_id: UUID | None = None,
    details: dict | None = None,
) -> ExtractionErrorLog:
    error_log = ExtractionErrorLog(
        organization_id=str(organization_id) if organization_id else None,
        workspace_id=str(workspace_id) if workspace_id else None,
        job_id=str(job_id) if job_id else None,
        file_id=str(file_id) if file_id else None,
        stage=stage,
        error_type=error_type,
        message=message,
        retryable=retryable,
        attempt=attempt,
        details=details,
    )
    session.add(error_log)
    await session.flush()
    await create_audit_log(
        session,
        action="pipeline.error_recorded",
        entity_type="extraction_error",
        entity_id=error_log.id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        details={
            "job_id": str(job_id) if job_id else None,
            "file_id": str(file_id) if file_id else None,
            "stage": stage,
            "error_type": error_type,
            "retryable": retryable,
            "attempt": attempt,
        },
    )
    await session.commit()
    await session.refresh(error_log)
    return error_log


async def list_extraction_errors(
    session: AsyncSession,
    *,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    limit: int = 50,
) -> list[ExtractionErrorLog]:
    query = (
        apply_tenant_filter(
            select(ExtractionErrorLog),
            ExtractionErrorLog,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        .order_by(ExtractionErrorLog.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


def apply_tenant_filter(query, model, *, organization_id: UUID | None, workspace_id: UUID | None):
    if organization_id is not None:
        query = query.where(
            or_(model.organization_id == str(organization_id), model.organization_id.is_(None))
        )
    if workspace_id is not None:
        query = query.where(
            or_(model.workspace_id == str(workspace_id), model.workspace_id.is_(None))
        )
    return query


def is_tenant_match(
    entity,
    *,
    organization_id: UUID | None,
    workspace_id: UUID | None,
) -> bool:
    if organization_id is not None and entity.organization_id not in (None, str(organization_id)):
        return False
    if workspace_id is not None and entity.workspace_id not in (None, str(workspace_id)):
        return False
    return True
