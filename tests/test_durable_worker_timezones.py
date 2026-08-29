import asyncio
from datetime import UTC

from app.db.models import ProcessingJob
from app.db.session import get_sessionmaker
from app.workers.durable import claim_next_job


def test_sqlite_job_timestamps_round_trip_as_utc_aware(test_app) -> None:
    """SQLite must not strip tzinfo from worker scheduling timestamps."""
    client = test_app.client
    headers = test_app.auth_headers()
    upload = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("invoice.txt", b"Vendor: UTC Test", "text/plain")},
    )
    assert upload.status_code == 201
    created = client.post("/v1/jobs", headers=headers, json={"file_id": upload.json()["file_id"]})
    assert created.status_code == 201
    job_id = created.json()["job_id"]

    async def verify() -> None:
        async with get_sessionmaker(test_app.settings.database_url)() as session:
            job = await session.get(ProcessingJob, job_id)
            assert job is not None
            assert job.next_run_at.tzinfo is UTC
            claimed = await claim_next_job(session, worker_id="timezone-test", lease_seconds=30)
            assert claimed is not None
            assert claimed.lease_expires_at.tzinfo is UTC

    asyncio.run(verify())
