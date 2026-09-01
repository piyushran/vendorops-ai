from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import models as agent_models  # noqa: F401
from app.api.routes import (
    analytics,
    auth,
    files,
    health,
    jobs,
    observability,
    records,
    reports,
    validation,
)
from app.auth.service import seed_default_identity
from app.config.settings import get_settings
from app.db.session import get_sessionmaker, init_db
from app.observability.logging import configure_logging
from app.observability.middleware import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await init_db(settings.database_url)
    sessionmaker = get_sessionmaker(settings.database_url)
    async with sessionmaker() as session:
        await seed_default_identity(session, settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        description="AI-powered data pipeline for document ingestion and extraction.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(files.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)
    app.include_router(records.router, prefix=settings.api_prefix)
    app.include_router(validation.router, prefix=settings.api_prefix)
    app.include_router(reports.router, prefix=settings.api_prefix)
    app.include_router(observability.router, prefix=settings.api_prefix)
    app.include_router(analytics.router, prefix=settings.api_prefix)

    return app


app = create_app()
