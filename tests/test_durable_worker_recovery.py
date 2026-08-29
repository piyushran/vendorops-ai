import asyncio
from datetime import UTC, datetime, timedelta

from app.db.models import ProcessingJob
from app.db.session import get_sessionmaker
from app.workers.durable import FAILED, QUEUED, recover_expired_jobs


def test_expired_job_becomes_terminal_after_max_attempts(test_app) -> None:
    client = test_app.client
    headers = test_app.auth_headers()
    upload = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("recovery.txt", b"Vendor: Recovery Test", "text/plain")},
    )
    assert upload.status_code == 201
    created = client.post(
        "/v1/jobs",
        headers=headers,
        json={"file_id": upload.json()["file_id"]},
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]

    async def verify() -> None:
        async with get_sessionmaker(test_app.settings.database_url)() as session:
            job = await session.get(ProcessingJob, job_id)
            assert job is not None
            job.status = "running"
            job.attempts = job.max_attempts
            job.lease_owner = "dead-worker"
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            job.execution_id = "dead-execution"
            await session.commit()
            recovered = await recover_expired_jobs(session)
            assert recovered == 1
            await session.refresh(job)
            assert job.status == FAILED
            assert job.failed_at is not None
            assert job.lease_owner is None
            assert job.execution_id is None

    asyncio.run(verify())


def test_run_endpoint_requeues_failed_job(test_app) -> None:
    client = test_app.client
    headers = test_app.auth_headers()
    upload = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("rerun.txt", b"Vendor: Rerun Test", "text/plain")},
    )
    assert upload.status_code == 201
    created = client.post(
        "/v1/jobs",
        headers=headers,
        json={"file_id": upload.json()["file_id"]},
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]

    async def fail_job() -> None:
        async with get_sessionmaker(test_app.settings.database_url)() as session:
            job = await session.get(ProcessingJob, job_id)
            assert job is not None
            job.status = FAILED
            job.attempts = job.max_attempts
            job.failed_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(fail_job())

    rerun = client.post(f"/v1/jobs/{job_id}/run", headers=headers)
    assert rerun.status_code == 202
    payload = rerun.json()
    assert payload["status"] == QUEUED
    assert payload["attempts"] == 0
    assert payload["failed_at"] is None
