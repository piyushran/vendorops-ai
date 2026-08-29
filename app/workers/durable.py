"""Database-backed durable job state machine and lease operations."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessingJob, utc_now
from app.db.repositories import create_audit_log

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
TERMINAL_STATES = frozenset({COMPLETED, FAILED})
ALLOWED_TRANSITIONS = {
    QUEUED: frozenset({RUNNING}),
    RUNNING: frozenset({QUEUED, COMPLETED, FAILED}),
    COMPLETED: frozenset(),
    FAILED: frozenset(),
}


class InvalidJobTransition(ValueError):
    pass


def retry_delay(attempt: int, base_seconds: float, maximum_seconds: float) -> float:
    return min(maximum_seconds, base_seconds * (2 ** max(0, attempt - 1)))


def transition(job: ProcessingJob, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(job.status, frozenset()):
        raise InvalidJobTransition(f"Cannot transition job {job.id} from {job.status} to {target}.")
    job.status = target


async def claim_next_job(
    session: AsyncSession, *, worker_id: str, lease_seconds: float
) -> ProcessingJob | None:
    """Atomically lease one eligible job. PostgreSQL uses SKIP LOCKED; SQLite is safe via CAS."""
    now = utc_now()
    eligible = and_(
        ProcessingJob.status == QUEUED,
        ProcessingJob.next_run_at <= now,
        or_(ProcessingJob.lease_expires_at.is_(None), ProcessingJob.lease_expires_at < now),
    )
    query = (
        select(ProcessingJob)
        .where(eligible)
        .order_by(ProcessingJob.next_run_at, ProcessingJob.created_at)
    )
    if session.bind and session.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    candidate = (await session.execute(query.limit(1))).scalar_one_or_none()
    if candidate is None:
        await session.rollback()
        return None
    execution_id = str(uuid4())
    values = {
        "status": RUNNING,
        "attempts": candidate.attempts + 1,
        "started_at": now,
        "lease_owner": worker_id,
        "lease_expires_at": now + timedelta(seconds=lease_seconds),
        "execution_id": execution_id,
        "error_message": None,
        "updated_at": now,
    }
    # The predicate makes SQLite concurrent claimers harmless even without row locks.
    result = await session.execute(
        update(ProcessingJob).where(ProcessingJob.id == candidate.id, eligible).values(**values)
    )
    if result.rowcount != 1:
        await session.rollback()
        return None
    await session.commit()
    claimed = await session.get(ProcessingJob, candidate.id)
    return claimed


async def heartbeat_job(
    session: AsyncSession, *, job_id: str, worker_id: str, execution_id: str, lease_seconds: float
) -> bool:
    now = utc_now()
    result = await session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == RUNNING,
            ProcessingJob.lease_owner == worker_id,
            ProcessingJob.execution_id == execution_id,
            ProcessingJob.lease_expires_at >= now,
        )
        .values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now)
    )
    await session.commit()
    return result.rowcount == 1


async def recover_expired_jobs(session: AsyncSession) -> int:
    now = utc_now()
    result = await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.status == RUNNING, ProcessingJob.lease_expires_at < now)
        .values(
            status=QUEUED,
            next_run_at=now,
            lease_owner=None,
            lease_expires_at=None,
            execution_id=None,
            error_message="Worker lease expired; job recovered.",
            updated_at=now,
        )
    )
    await session.commit()
    return result.rowcount or 0


async def complete_job(session: AsyncSession, *, job: ProcessingJob, worker_id: str) -> bool:
    now = utc_now()
    result = await session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job.id,
            ProcessingJob.status == RUNNING,
            ProcessingJob.lease_owner == worker_id,
            ProcessingJob.execution_id == job.execution_id,
        )
        .values(
            status=COMPLETED,
            completed_at=now,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
    )
    if result.rowcount:
        await create_audit_log(
            session,
            action="job.status_updated",
            entity_type="processing_job",
            entity_id=job.id,
            details={"status": COMPLETED, "execution_id": job.execution_id},
        )
    await session.commit()
    return result.rowcount == 1


async def fail_job(
    session: AsyncSession,
    *,
    job: ProcessingJob,
    worker_id: str,
    error: Exception,
    retryable: bool,
    retry_base_seconds: float,
    retry_max_seconds: float,
) -> str:
    now = utc_now()
    terminal = not retryable or job.attempts >= job.max_attempts
    values: dict = {
        "error_message": str(error),
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": now,
    }
    if terminal:
        values.update(status=FAILED, failed_at=now)
    else:
        values.update(
            status=QUEUED,
            next_run_at=now
            + timedelta(seconds=retry_delay(job.attempts, retry_base_seconds, retry_max_seconds)),
        )
    result = await session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job.id,
            ProcessingJob.status == RUNNING,
            ProcessingJob.lease_owner == worker_id,
            ProcessingJob.execution_id == job.execution_id,
        )
        .values(**values)
    )
    if result.rowcount:
        await create_audit_log(
            session,
            action="job.status_updated",
            entity_type="processing_job",
            entity_id=job.id,
            details={"status": FAILED if terminal else QUEUED, "execution_id": job.execution_id},
        )
    await session.commit()
    return FAILED if terminal and result.rowcount else QUEUED
