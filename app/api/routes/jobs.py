from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission_dependency, tenant_ids
from app.api.schemas import CreateJobRequest, ProcessingJobResponse
from app.api.serializers import to_processing_job_response
from app.auth.service import AuthContext
from app.config.settings import Settings, get_settings
from app.db.repositories import create_processing_job, get_processing_job, get_uploaded_file
from app.db.session import get_db_session
from app.workers.document_jobs import enqueue_document_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post(
    "",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: CreateJobRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> ProcessingJobResponse:
    organization_id, workspace_id = tenant_ids(context)
    file_record = await get_uploaded_file(
        session,
        request.file_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{request.file_id}' was not found.",
        )

    job = await create_processing_job(
        session,
        job_id=uuid4(),
        file_id=request.file_id,
        pipeline=request.pipeline,
        organization_id=organization_id,
        workspace_id=workspace_id,
        max_attempts=get_settings().worker_max_attempts,
    )

    return to_processing_job_response(job)


@router.get("/{job_id}", response_model=ProcessingJobResponse)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> ProcessingJobResponse:
    organization_id, workspace_id = tenant_ids(context)
    job = await get_processing_job(
        session,
        job_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' was not found.",
        )

    return to_processing_job_response(job)


@router.post(
    "/{job_id}/run",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    context: Annotated[AuthContext, Depends(require_permission_dependency("pipeline:write"))],
) -> ProcessingJobResponse:
    organization_id, workspace_id = tenant_ids(context)
    job = await get_processing_job(
        session,
        job_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' was not found.",
        )

    if job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is already running.",
        )
    if job.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' has already completed.",
        )

    enqueue_document_job(background_tasks, settings=settings, job_id=job_id)

    return to_processing_job_response(job)
