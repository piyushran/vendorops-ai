import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import BackgroundTasks

from app.config.settings import Settings
from app.db.models import ProcessingJob
from app.db.repositories import create_extraction_error
from app.db.session import get_sessionmaker
from app.observability.logging import get_logger, log_event
from app.pipeline.document_pipeline import PipelineError, PipelineInputError, run_document_pipeline
from app.workers.durable import (
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    recover_expired_jobs,
)

logger = get_logger(__name__)
JobHandler = Callable[[ProcessingJob], Awaitable[None]]


def enqueue_document_job(
    background_tasks: BackgroundTasks,
    *,
    settings: Settings,
    job_id: UUID,
) -> None:
    """Development compatibility path; production uses `python -m app.workers.run`."""
    background_tasks.add_task(execute_document_job, settings=settings, job_id=job_id)


async def execute_document_job(*, settings: Settings, job_id: UUID) -> None:
    del job_id
    await DocumentWorker(settings).run_once()


class DocumentWorker:
    """Polling database worker with an expiring ownership lease per execution."""

    def __init__(
        self, settings: Settings, *, worker_id: str | None = None, handler: JobHandler | None = None
    ):
        self.settings = settings
        self.worker_id = worker_id or f"worker-{uuid4()}"
        self.handler = handler
        self.stopping = asyncio.Event()

    def stop(self) -> None:
        self.stopping.set()

    async def _run_document(self, job: ProcessingJob) -> None:
        async with get_sessionmaker(self.settings.database_url)() as session:
            fresh = await session.get(ProcessingJob, job.id)
            if fresh is not None:
                await run_document_pipeline(
                    session=session,
                    settings=self.settings,
                    file_id=UUID(fresh.file_id),
                    job=fresh,
                    manage_job_status=False,
                )

    async def _heartbeat(self, job: ProcessingJob) -> None:
        while not self.stopping.is_set():
            await asyncio.sleep(self.settings.worker_heartbeat_interval_seconds)
            async with get_sessionmaker(self.settings.database_url)() as session:
                alive = await heartbeat_job(
                    session,
                    job_id=job.id,
                    worker_id=self.worker_id,
                    execution_id=job.execution_id or "",
                    lease_seconds=self.settings.worker_lease_duration_seconds,
                )
            if not alive:
                return

    async def run_once(self) -> bool:
        sessionmaker = get_sessionmaker(self.settings.database_url)
        async with sessionmaker() as session:
            await recover_expired_jobs(session)
            job = await claim_next_job(
                session,
                worker_id=self.worker_id,
                lease_seconds=self.settings.worker_lease_duration_seconds,
            )
        if job is None:
            return False
        started = time.monotonic()
        heartbeat = asyncio.create_task(self._heartbeat(job))
        try:
            if self.handler is not None:
                await self.handler(job)
            else:
                await self._run_document(job)
        except Exception as exc:
            # The document pipeline has already handled its own transient extraction retries.
            # A PipelineError therefore represents a terminal pipeline invocation failure.
            retryable = not isinstance(exc, (PipelineError, PipelineInputError, ValueError))
            async with sessionmaker() as session:
                outcome = await fail_job(
                    session,
                    job=job,
                    worker_id=self.worker_id,
                    error=exc,
                    retryable=retryable,
                    retry_base_seconds=self.settings.worker_retry_base_seconds,
                    retry_max_seconds=self.settings.worker_retry_max_seconds,
                )
                if not isinstance(exc, PipelineError):
                    await create_extraction_error(
                        session,
                        stage="worker",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retryable=outcome != "failed",
                        attempt=job.attempts,
                        job_id=UUID(job.id),
                        file_id=UUID(job.file_id),
                        details={
                            "worker_id": self.worker_id,
                            "execution_id": job.execution_id,
                            "terminal": outcome == "failed",
                        },
                    )
            log_event(
                logger,
                logging.ERROR,
                "worker.job_failed",
                "Durable job failed",
                job_id=job.id,
                attempt=job.attempts,
                outcome=outcome,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error=str(exc),
            )
        else:
            async with sessionmaker() as session:
                completed = await complete_job(session, job=job, worker_id=self.worker_id)
            log_event(
                logger,
                logging.INFO,
                "worker.job_completed",
                "Durable job completed",
                job_id=job.id,
                attempt=job.attempts,
                outcome="completed" if completed else "lease_lost",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        return True

    async def run(self) -> None:
        log_event(
            logger,
            logging.INFO,
            "worker.started",
            "Durable worker started",
            worker_id=self.worker_id,
        )
        while not self.stopping.is_set():
            if not await self.run_once():
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self.stopping.wait(), timeout=self.settings.worker_poll_interval_seconds
                    )
        log_event(
            logger,
            logging.INFO,
            "worker.stopped",
            "Durable worker stopped",
            worker_id=self.worker_id,
        )


def install_signal_handlers(worker: DocumentWorker) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)
