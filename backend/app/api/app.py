"""FastAPI application factory.

A factory rather than a module-level ``app`` object so tests can build an
isolated instance with its own settings, and so startup side effects
(migrations, demo bootstrap, opening the vector store) happen inside a
lifespan that is guaranteed to be torn down again.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routers import drift, golden_sets, metrics, runs, system
from app.core.config import Settings, get_settings
from app.core.factory import build_vector_store
from app.core.logging import configure_logging
from app.services.bootstrap import bootstrap

logger = logging.getLogger(__name__)

API_PREFIX = "/api"

DESCRIPTION = """
Monitor retrieval quality in a RAG system and detect when it silently degrades.

Score a **golden set** of (query, expected document) judgements against your
vector index, track the resulting Recall@k / Precision@k / MRR / NDCG@k over
time, and compare new runs against a historical baseline.

Errors share one envelope: `{"error": {"code": ..., "message": ...}}`.
Branch on `code`, never on `message`.
""".strip()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The vector store client is opened once and shared: reopening the
        # index per request would dominate the cost of a small evaluation.
        vector_store = build_vector_store(settings)
        app.state.vector_store = vector_store
        app.state.settings = settings
        try:
            report = bootstrap(settings=settings, vector_store=vector_store)
            logger.info(
                "startup complete (migrated=%s, documents_indexed=%d)",
                report.migrated,
                report.documents_indexed,
            )
            yield
        finally:
            vector_store.close()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(system.router)
    api.include_router(runs.router)
    api.include_router(metrics.router)
    api.include_router(drift.router)
    api.include_router(golden_sets.router)
    app.include_router(api)

    return app
