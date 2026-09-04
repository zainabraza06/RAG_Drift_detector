"""Golden set management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import GoldenSetServiceDep
from app.api.schemas import GoldenSetImportInput, GoldenSetInput, golden_set_from_input
from app.domain.history import Page, StoredGoldenSet

router = APIRouter(prefix="/golden-sets", tags=["golden sets"])


@router.get("", response_model=Page[StoredGoldenSet], summary="List golden sets")
def list_golden_sets(
    service: GoldenSetServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[StoredGoldenSet]:
    return service.list_sets(limit=limit, offset=offset)


@router.post(
    "",
    response_model=StoredGoldenSet,
    status_code=status.HTTP_201_CREATED,
    summary="Create a golden set",
    responses={
        400: {"description": "The judgements are invalid."},
        409: {"description": "That name and version already exists."},
    },
)
def create_golden_set(
    payload: GoldenSetInput, service: GoldenSetServiceDep
) -> StoredGoldenSet:
    """Store a new golden set.

    ``(name, version)`` is unique: revisions are stored as new versions rather
    than overwriting, so a run's recorded ground truth can never change after
    the fact.
    """
    return service.create(
        golden_set_from_input(payload), source="api", activate=payload.activate
    )


@router.post(
    "/import",
    response_model=StoredGoldenSet,
    status_code=status.HTTP_201_CREATED,
    summary="Import a golden set from a JSON or CSV file",
    responses={400: {"description": "The file is missing or unparseable."}},
)
def import_golden_set(
    payload: GoldenSetImportInput, service: GoldenSetServiceDep
) -> StoredGoldenSet:
    return service.import_from_file(
        payload.path,
        name=payload.name,
        version=payload.version,
        activate=payload.activate,
    )


# Declared before /{golden_set_id} so "active" is never parsed as an id.
@router.get(
    "/active",
    response_model=StoredGoldenSet,
    summary="The golden set evaluations use by default",
    responses={409: {"description": "No golden set is active."}},
)
def get_active_golden_set(service: GoldenSetServiceDep) -> StoredGoldenSet:
    return service.get_active()


@router.get(
    "/{golden_set_id}",
    response_model=StoredGoldenSet,
    summary="One golden set",
    responses={404: {"description": "No such golden set."}},
)
def get_golden_set(
    golden_set_id: int, service: GoldenSetServiceDep
) -> StoredGoldenSet:
    return service.get(golden_set_id)


@router.put(
    "/{golden_set_id}",
    response_model=StoredGoldenSet,
    summary="Replace a golden set's judgements",
    responses={
        400: {"description": "The judgements are invalid."},
        404: {"description": "No such golden set."},
    },
)
def update_golden_set(
    golden_set_id: int, payload: GoldenSetInput, service: GoldenSetServiceDep
) -> StoredGoldenSet:
    """Edit judgements in place.

    This recomputes the fingerprint, which deliberately severs comparability
    with runs scored before the edit: changing the ruler must not be able to
    masquerade as a change in the system being measured.
    """
    return service.update_judgements(golden_set_id, golden_set_from_input(payload))


@router.post(
    "/{golden_set_id}/activate",
    response_model=StoredGoldenSet,
    summary="Make this the active golden set",
    responses={404: {"description": "No such golden set."}},
)
def activate_golden_set(
    golden_set_id: int, service: GoldenSetServiceDep
) -> StoredGoldenSet:
    return service.activate(golden_set_id)


@router.delete(
    "/{golden_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a golden set",
    responses={404: {"description": "No such golden set."}},
)
def delete_golden_set(golden_set_id: int, service: GoldenSetServiceDep) -> Response:
    """Runs that used it keep their own snapshot of its identity."""
    service.delete(golden_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
