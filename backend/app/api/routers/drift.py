"""Drift detection endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DriftServiceDep
from app.domain.drift import DriftAssessment, DriftVerdict
from app.domain.history import Page

router = APIRouter(prefix="/drift", tags=["drift"])


@router.get(
    "/events",
    response_model=Page[DriftAssessment],
    summary="Past drift assessments, newest first",
)
def list_drift_events(
    service: DriftServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    verdict: Annotated[
        DriftVerdict | None,
        Query(description="Filter to one verdict, e.g. 'degraded'."),
    ] = None,
    fingerprint: Annotated[str | None, Query()] = None,
) -> Page[DriftAssessment]:
    """Each entry carries its full statistical reasoning, not just a verdict."""
    return service.list_events(
        limit=limit, offset=offset, verdict=verdict, fingerprint=fingerprint
    )


@router.get(
    "/latest",
    response_model=DriftAssessment | None,
    summary="The most recent drift assessment, if any",
)
def latest_drift(service: DriftServiceDep) -> DriftAssessment | None:
    return service.latest()
