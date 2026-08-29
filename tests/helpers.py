import asyncio

from fastapi.testclient import TestClient

from app.auth.service import seed_default_identity
from app.config.settings import Settings, get_settings
from app.db.session import get_sessionmaker
from app.workers.document_jobs import DocumentWorker


def seed_demo_identity(database_url: str, settings: Settings) -> None:
    async def seed() -> None:
        sessionmaker = get_sessionmaker(database_url)
        async with sessionmaker() as session:
            await seed_default_identity(session, settings)

    asyncio.run(seed())


def auth_headers(client: TestClient, settings: Settings) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login",
        json={
            "email": settings.demo_admin_email,
            "password": settings.demo_admin_password,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def wait_for_job(
    client: TestClient,
    job_id: str,
    headers: dict[str, str],
    *,
    expected_status: str = "completed",
) -> dict:
    """Drive one standalone worker iteration, then poll the durable job state."""
    settings = get_settings()
    asyncio.run(DocumentWorker(settings, worker_id="test-worker").run_once())

    response = client.get(f"/v1/jobs/{job_id}", headers=headers)
    assert response.status_code == 200
    latest_payload = response.json()
    assert latest_payload["status"] == expected_status
    return latest_payload


def extract_file_and_wait(client: TestClient, file_id: str, headers: dict[str, str]) -> dict:
    response = client.post(f"/v1/files/{file_id}/extract", headers=headers)
    assert response.status_code == 202
    job = response.json()
    return wait_for_job(client, job["job_id"], headers)
