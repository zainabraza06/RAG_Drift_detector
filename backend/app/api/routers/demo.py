"""Simulate drift on the demo index.

Off unless ``DRIFT_DEMO_CONTROLS`` is set. These endpoints change the index
the way an outside pipeline would; scoring, drift detection and diagnostics
are untouched and have to notice the change on their own.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DemoServiceDep
from app.api.schemas import DemoIndexState
from app.services.demo_scenarios import DemoScenarioService, Scenario

router = APIRouter(prefix="/demo", tags=["demo"])


def _state(service: DemoScenarioService) -> DemoIndexState:
    state = service.state()
    return DemoIndexState(
        enabled=service.enabled,
        document_count=state.document_count,
        corpus_size=state.corpus_size,
        missing_documents=state.missing_documents,
        fragment_documents=state.fragment_documents,
        healthy=state.healthy,
    )


@router.get("", response_model=DemoIndexState, summary="Demo index state")
def demo_state(service: DemoServiceDep) -> DemoIndexState:
    return _state(service)


@router.post(
    "/scenarios/{scenario}",
    response_model=DemoIndexState,
    summary="Break or restore the demo index",
    responses={403: {"description": "Demo controls are disabled."}},
)
def apply_scenario(scenario: Scenario, service: DemoServiceDep) -> DemoIndexState:
    """Change the index; the next evaluation shows whether drift is detected.

    * ``delete-documents`` removes six documents the golden set expects.
    * ``rechunk`` adds sentence fragments of every document, leaving the
      originals in place.
    * ``restore`` returns the index to the clean demo corpus.
    """
    service.apply(scenario)
    return _state(service)
