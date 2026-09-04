"""Metric history endpoints — the data behind the trend charts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import RunServiceDep
from app.domain.history import MetricSeries
from app.domain.metrics import METRIC_NAMES

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/cutoffs",
    response_model=list[int],
    summary="Cutoffs that have stored data",
)
def evaluated_cutoffs(service: RunServiceDep) -> list[int]:
    """Distinct ``k`` values present in history.

    Lets the chart's cutoff selector offer only values that would actually
    render a line, instead of every configured cutoff.
    """
    return list(service.evaluated_cutoffs())


@router.get(
    "/series",
    response_model=MetricSeries,
    summary="One metric's history at one cutoff",
    responses={400: {"description": "Unknown metric name."}},
)
def metric_series(
    service: RunServiceDep,
    metric: Annotated[
        str, Query(description=f"One of: {', '.join(METRIC_NAMES)}")
    ] = "recall_at_k",
    k: Annotated[int, Query(ge=1)] = 5,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    fingerprint: Annotated[str | None, Query()] = None,
) -> MetricSeries:
    """Points are ordered oldest first, ready to plot left to right."""
    return service.series(metric=metric, k=k, limit=limit, fingerprint=fingerprint)


@router.get(
    "/trends",
    response_model=list[MetricSeries],
    summary="Every metric's history at one cutoff",
)
def metric_trends(
    service: RunServiceDep,
    k: Annotated[int, Query(ge=1)] = 5,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    fingerprint: Annotated[str | None, Query()] = None,
) -> list[MetricSeries]:
    """All four metrics in one request.

    The trend view plots them together; four round trips to render one screen
    would be four chances for a partial failure.
    """
    return [
        service.series(metric=metric, k=k, limit=limit, fingerprint=fingerprint)
        for metric in METRIC_NAMES
    ]
