from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission_dependency, tenant_ids
from app.api.schemas import (
    ParsedDocumentResponse,
    ProcessingJobResponse,
    UploadedFileResponse,
)
from app.api.serializers import to_processing_job_response
from app.auth.service import AuthContext
from app.config.settings import Settings, get_settings
from app.db.repositories import (
    create_processing_job,
    create_uploaded_file,
    get_uploaded_file,
)
from app.db.session import get_db_session
from app.ingestion.storage import store_upload
from app.parsers.dispatcher import parse_file
from app.parsers.models import ParserError
from app.storage.factory import get_object_storage

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "",
    response_model=UploadedFileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    file: Annotated[UploadFile, File(...)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> UploadedFileResponse:
    try:
        stored_upload = await store_upload(
            file,
            get_object_storage(settings),
            max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    organization_id, workspace_id = tenant_ids(context)
    uploaded_file = await create_uploaded_file(
        session,
        file_id=UUID(stored_upload.file_id),
        organization_id=organization_id,
        workspace_id=workspace_id,
        original_filename=stored_upload.original_filename,
        content_type=stored_upload.content_type,
        file_type=stored_upload.original_filename.rsplit(".", 1)[-1].lower(),
        size_bytes=stored_upload.size_bytes,
        sha256_hash=stored_upload.sha256_hash,
        storage_path=stored_upload.storage_path,
    )

    return UploadedFileResponse(
        file_id=UUID(uploaded_file.id),
        original_filename=uploaded_file.original_filename,
        content_type=uploaded_file.content_type,
        size_bytes=uploaded_file.size_bytes,
        sha256_hash=uploaded_file.sha256_hash,
        storage_path=uploaded_file.storage_path,
        created_at=uploaded_file.created_at,
    )


@router.get("/{file_id}/parsed", response_model=ParsedDocumentResponse)
async def parse_uploaded_file(
    file_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> ParsedDocumentResponse:
    organization_id, workspace_id = tenant_ids(context)
    uploaded_file = await get_uploaded_file(
        session,
        file_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if uploaded_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' was not found.",
        )

    try:
        parsed_document = parse_file(uploaded_file.storage_path)
    except ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return ParsedDocumentResponse(**parsed_document.model_dump())


@router.post(
    "/{file_id}/extract",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_uploaded_file(
    file_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> ProcessingJobResponse:
    organization_id, workspace_id = tenant_ids(context)
    uploaded_file = await get_uploaded_file(
        session,
        file_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if uploaded_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_id}' was not found.",
        )

    job = await create_processing_job(
        session,
        job_id=uuid4(),
        file_id=file_id,
        pipeline="document_extraction",
        organization_id=organization_id,
        workspace_id=workspace_id,
        max_attempts=get_settings().worker_max_attempts,
    )

    return to_processing_job_response(job)
