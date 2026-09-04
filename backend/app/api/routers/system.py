"""Health, system information and the dashboard summary."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import __version__
from app.api.deps import (
    GoldenSetServiceDep,
    RunServiceDep,
    SessionDep,
    SettingsDep,
    VectorStoreDep,
)
from app.api.schemas import (
    DashboardSummary,
    HealthResponse,
    SystemInfoResponse,
    VectorStoreStatus,
)
from app.connectors import available_connectors
from app.db.migrations import current_revision
from app.domain.history import GoldenSetRef
from app.embeddings import available_embedding_providers
from app.services.golden_set_service import NoActiveGoldenSetError
from app.services.run_service import metric_deltas

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


def _describe_store(vector_store: VectorStoreDep) -> VectorStoreStatus:
    """Probe the vector store without ever raising.

    Health endpoints that can themselves fail are worse than useless, so a
    failed probe is reported as data rather than as a 500.
    """
    health = vector_store.health_check()
    if not health.reachable:
        return VectorStoreStatus(
            connector=vector_store.name,
            collection=vector_store.collection_name,
            reachable=False,
            message=health.message,
        )
    info = vector_store.describe()
    return VectorStoreStatus(
        connector=info.connector,
        collection=info.collection,
        reachable=True,
        document_count=info.document_count,
        embedding_model=info.embedding_model,
        embedding_dimensions=info.embedding_dimensions,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness and readiness")
def health(
    session: SessionDep, vector_store: VectorStoreDep, response: Response
) -> HealthResponse:
    """Report on the two dependencies that can actually be down.

    Returns 503 when either is unreachable so an orchestrator's readiness
    probe can route traffic away, while still returning a body that says
    *which* dependency failed.
    """
    database_ok = True
    message: str | None = None
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - only on a broken database
        database_ok = False
        message = f"database unavailable: {exc}"
        logger.exception("health check: database probe failed")

    store = _describe_store(vector_store)
    if not store.reachable and message is None:
        message = store.message

    healthy = database_ok and store.reachable
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        database=database_ok,
        vector_store=store.reachable,
        message=message,
    )


@router.get(
    "/system/info",
    response_model=SystemInfoResponse,
    summary="Resolved configuration and component status",
)
def system_info(
    settings: SettingsDep,
    vector_store: VectorStoreDep,
    runs: RunServiceDep,
    golden_sets: GoldenSetServiceDep,
) -> SystemInfoResponse:
    try:
        active = golden_sets.get_active()
        active_ref = GoldenSetRef(
            name=active.golden_set.name,
            version=active.golden_set.version,
            fingerprint=active.fingerprint,
        )
    except NoActiveGoldenSetError:
        active_ref = None

    return SystemInfoResponse(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        schema_revision=current_revision(settings),
        vector_store=_describe_store(vector_store),
        available_connectors=available_connectors(),
        available_embedding_providers=available_embedding_providers(),
        eval_k_values=tuple(settings.eval_k_values),
        eval_primary_k=settings.eval_primary_k,
        run_count=runs.count(),
        golden_set_count=golden_sets.list_sets(limit=1).total,
        active_golden_set=active_ref,
    )


@router.get(
    "/dashboard",
    response_model=DashboardSummary,
    summary="Everything the dashboard home screen needs",
)
def dashboard(
    runs: RunServiceDep, golden_sets: GoldenSetServiceDep
) -> DashboardSummary:
    """One request per first paint.

    ``has_runs`` is explicit rather than inferred from an empty list, so the
    UI can distinguish "never evaluated" (show onboarding) from "evaluated,
    nothing matched this filter" (show an empty state).
    """
    latest, previous = runs.latest_pair()
    try:
        active = golden_sets.get_active()
    except NoActiveGoldenSetError:
        active = None

    return DashboardSummary(
        has_runs=latest is not None,
        total_runs=runs.count(),
        latest_run=latest,
        previous_run=previous,
        primary_metrics=latest.primary_metrics if latest else None,
        metric_deltas=metric_deltas(latest, previous) if latest else {},
        active_golden_set=active,
        last_run_at=latest.finished_at if latest else None,
        document_count=latest.store.document_count if latest else None,
    )
