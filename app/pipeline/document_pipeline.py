import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.db.models import ExtractedRecord, ProcessingJob, ValidationError
from app.db.repositories import (
    create_extracted_record,
    create_extraction_error,
    create_processing_job,
    create_validation_errors,
    get_uploaded_file,
    update_processing_job_status,
)
from app.extraction.extractor import ExtractionError, get_extractor
from app.observability.logging import get_logger, log_event
from app.observability.retry import RetryExhaustedError, retry_async
from app.parsers.dispatcher import parse_file
from app.parsers.models import ParserError
from app.validation.rules import validate_extracted_record

logger = get_logger(__name__)


class PipelineError(Exception):
    """Base class for document pipeline failures."""


class PipelineInputError(PipelineError):
    """Raised when the requested pipeline input is not usable."""


@dataclass(frozen=True)
class DocumentPipelineResult:
    job: ProcessingJob
    record: ExtractedRecord
    validation_errors: list[ValidationError]


async def run_document_pipeline(
    *,
    session: AsyncSession,
    settings: Settings,
    file_id: UUID,
    organization_id: UUID | None = None,
    workspace_id: UUID | None = None,
    job: ProcessingJob | None = None,
    manage_job_status: bool = True,
) -> DocumentPipelineResult:
    if job is not None:
        organization_id = organization_id or (
            UUID(job.organization_id) if job.organization_id else None
        )
        workspace_id = workspace_id or (UUID(job.workspace_id) if job.workspace_id else None)

    uploaded_file = await get_uploaded_file(
        session,
        file_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if uploaded_file is None:
        raise PipelineInputError(f"File '{file_id}' was not found.")

    if job is None:
        organization_id = organization_id or (
            UUID(uploaded_file.organization_id) if uploaded_file.organization_id else None
        )
        workspace_id = workspace_id or (
            UUID(uploaded_file.workspace_id) if uploaded_file.workspace_id else None
        )
        job = await create_processing_job(
            session,
            job_id=uuid4(),
            file_id=file_id,
            pipeline="document_extraction",
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
    elif job.pipeline != "document_extraction":
        raise PipelineInputError(f"Unsupported pipeline '{job.pipeline}'.")

    if manage_job_status:
        job = await update_processing_job_status(session, job=job, status="running")
    job_id = UUID(job.id)
    log_event(
        logger,
        logging.INFO,
        "pipeline.started",
        "Document pipeline started",
        job_id=job.id,
        file_id=str(file_id),
        pipeline=job.pipeline,
    )

    try:
        log_event(
            logger,
            logging.INFO,
            "pipeline.stage_started",
            "Parsing source file",
            job_id=job.id,
            file_id=str(file_id),
            stage="parse",
        )
        parsed_document = parse_file(uploaded_file.storage_path)
        log_event(
            logger,
            logging.INFO,
            "pipeline.stage_completed",
            "Source file parsed",
            job_id=job.id,
            file_id=str(file_id),
            stage="parse",
            characters=len(parsed_document.text),
            table_count=len(parsed_document.tables),
        )

        extractor = get_extractor(settings)

        async def record_retry(attempt: int, exc: Exception, delay: float) -> None:
            await create_extraction_error(
                session,
                stage="extract",
                error_type=type(exc).__name__,
                message=str(exc),
                retryable=True,
                attempt=attempt,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_id=job_id,
                file_id=file_id,
                details={
                    "delay_seconds": delay,
                    "provider": extractor.provider,
                    "model": extractor.model,
                },
            )

        extraction_result = await retry_async(
            lambda: extractor.extract(parsed_document),
            attempts=settings.extraction_max_attempts,
            base_delay_seconds=settings.extraction_retry_base_seconds,
            retryable_exceptions=(ExtractionError,),
            operation_name="llm_extraction",
            on_retry=record_retry,
        )
        log_event(
            logger,
            logging.INFO,
            "pipeline.stage_completed",
            "Structured extraction completed",
            job_id=job.id,
            file_id=str(file_id),
            stage="extract",
            provider=extraction_result.provider,
            model=extraction_result.model,
            confidence=extraction_result.record.confidence,
        )

        findings = validate_extracted_record(extraction_result.record)
        needs_review = (
            extraction_result.record.needs_review
            or extraction_result.record.confidence < settings.extraction_review_threshold
            or any(finding.severity.value in {"warning", "error"} for finding in findings)
        )
        extracted_record = extraction_result.record.model_copy(
            update={"needs_review": needs_review}
        )
        record = await create_extracted_record(
            session,
            file_id=file_id,
            job_id=job_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            extracted=extracted_record,
            raw_payload=extraction_result.model_copy(update={"record": extracted_record}).model_dump(
                mode="json"
            ),
        )
        validation_errors = await create_validation_errors(
            session,
            record_id=UUID(record.id),
            job_id=job_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            findings=findings,
        )
        log_event(
            logger,
            logging.INFO,
            "pipeline.stage_completed",
            "Validation completed",
            job_id=job.id,
            file_id=str(file_id),
            stage="validate",
            finding_count=len(findings),
            needs_review=needs_review,
            review_threshold=settings.extraction_review_threshold,
        )
        if manage_job_status:
            job = await update_processing_job_status(session, job=job, status="completed")
        log_event(
            logger,
            logging.INFO,
            "pipeline.completed",
            "Document pipeline completed",
            job_id=job.id,
            file_id=str(file_id),
        )
    except (ParserError, ExtractionError, RetryExhaustedError, ValueError) as exc:
        stage = "parse" if isinstance(exc, ParserError) else "extract"
        cause = exc.cause if isinstance(exc, RetryExhaustedError) else exc
        await create_extraction_error(
            session,
            stage=stage,
            error_type=type(cause).__name__,
            message=str(cause),
            retryable=False,
            attempt=(exc.attempts if isinstance(exc, RetryExhaustedError) else 1),
            organization_id=organization_id,
            workspace_id=workspace_id,
            job_id=job_id,
            file_id=file_id,
            details={"pipeline": job.pipeline},
        )
        if manage_job_status:
            await update_processing_job_status(
                session,
                job=job,
                status="failed",
                error_message=str(exc),
            )
        log_event(
            logger,
            logging.ERROR,
            "pipeline.failed",
            "Document pipeline failed",
            job_id=job.id,
            file_id=str(file_id),
            stage=stage,
            error_type=type(cause).__name__,
        )
        raise PipelineError(str(exc)) from exc

    return DocumentPipelineResult(
        job=job,
        record=record,
        validation_errors=validation_errors,
    )
