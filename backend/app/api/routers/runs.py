"""Evaluation run endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query, Response, status

from app.api.deps import DriftServiceDep, RunServiceDep
from app.api.schemas import RunRequest
from app.domain.diagnostics import DiagnosticReport
from app.domain.drift import DriftAssessment
from app.domain.history import Page, RunDetail, RunRecord

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post(
    "",
    response_model=RunRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Run an evaluation now",
    responses={
        409: {"description": "No active golden set to evaluate."},
        503: {"description": "The vector store could not be reached."},
    },
)
def create_run(
    service: RunServiceDep,
    payload: Annotated[RunRequest, Body()] = RunRequest(),
) -> RunRecord:
    """Score a golden set against the vector store and store the result.

    Synchronous by design: a golden set is tens of queries, not thousands, and
    an immediate result is far more useful to a dashboard button than a job id
    the user then has to poll.
    """
    return service.execute(
        golden_set_id=payload.golden_set_id, trigger=payload.trigger
    )


@router.get("", response_model=Page[RunRecord], summary="List runs, newest first")
def list_runs(
    service: RunServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    golden_set_name: Annotated[str | None, Query()] = None,
    fingerprint: Annotated[
        str | None,
        Query(description="Restrict to runs scored against this exact golden set."),
    ] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> Page[RunRecord]:
    return service.list_runs(
        limit=limit,
        offset=offset,
        golden_set_name=golden_set_name,
        fingerprint=fingerprint,
        since=since,
    )


# Declared before /{run_id} so "latest" is never parsed as an identifier.
@router.get(
    "/latest",
    response_model=RunRecord | None,
    summary="The most recent run, if any",
)
def latest_run(
    service: RunServiceDep,
    fingerprint: Annotated[str | None, Query()] = None,
) -> RunRecord | None:
    return service.latest(fingerprint=fingerprint)


@router.get(
    "/{run_id}",
    response_model=RunRecord,
    summary="One run's aggregate metrics",
    responses={404: {"description": "No such run."}},
)
def get_run(run_id: str, service: RunServiceDep) -> RunRecord:
    return service.get(run_id)


@router.get(
    "/{run_id}/queries",
    response_model=RunDetail,
    summary="One run with its per-query breakdown",
    responses={404: {"description": "No such run."}},
)
def get_run_detail(run_id: str, service: RunServiceDep) -> RunDetail:
    """Per-query scores at the run's primary cutoff.

    Separate from the run resource because this payload scales with golden set
    size, and list views never need it.
    """
    return service.get_detail(run_id)


@router.delete(
    "/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a run",
    responses={404: {"description": "No such run."}},
)
def delete_run(run_id: str, service: RunServiceDep) -> Response:
    service.delete(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{run_id}/drift",
    response_model=DriftAssessment,
    summary="Statistical drift assessment for one run",
    responses={404: {"description": "No such run."}},
)
def get_run_drift(
    run_id: str,
    service: DriftServiceDep,
    recompute: Annotated[
        bool, Query(description="Re-run the test instead of returning the stored one.")
    ] = False,
) -> DriftAssessment:
    """Compares this run against its comparable predecessors.

    The stored assessment is returned when one exists; a run that predates
    drift detection is assessed on first request. Pass ``recompute=true`` after
    changing detection settings.
    """
    if recompute:
        return service.assess(run_id)
    return service.get_for_run(run_id)


@router.get(
    "/{run_id}/diagnostics",
    response_model=DiagnosticReport,
    summary="Heuristic root-cause report for one run",
    responses={
        404: {"description": "No such run, or no diagnostics were produced."}
    },
)
def get_run_diagnostics(run_id: str, service: DriftServiceDep) -> DiagnosticReport:
    """Ranked hypotheses for why a run regressed.

    Heuristics, not statistics. The payload carries `basis: "heuristic"` and a
    disclaimer for exactly that reason, and it is only produced for runs whose
    verdict is `degraded` -- diagnostics explain a regression the statistics
    established, they never establish one.
    """
    return service.diagnostics_for_run(run_id)
