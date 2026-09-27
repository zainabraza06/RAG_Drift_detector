"""Request and response schemas unique to the HTTP layer.

Domain value objects from :mod:`app.domain.history` are used directly as
response models wherever they fit; this module only adds the shapes that are
genuinely HTTP-specific -- request bodies, and composite payloads assembled
for a particular screen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import GoldenSetError
from app.domain.drift import DriftAssessment, DriftVerdict
from app.domain.golden_set import (
    DEFAULT_RELEVANCE,
    ExpectedDocument,
    GoldenQuery,
    GoldenSet,
)
from app.domain.history import GoldenSetRef, RunRecord, StoredGoldenSet
from app.domain.metrics import MetricSet

HealthStatus = Literal["healthy", "warning", "critical", "unknown"]

# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------


class ExpectedDocumentInput(BaseModel):
    """One expected document in a golden query."""

    document_id: str = Field(min_length=1, max_length=400)
    relevance: int = Field(default=DEFAULT_RELEVANCE, ge=0, le=10)


class GoldenQueryInput(BaseModel):
    """One (query, expected documents) judgement."""

    query_id: str | None = Field(
        default=None,
        max_length=200,
        description="Generated from position when omitted.",
    )
    query: str = Field(min_length=1, max_length=2000)
    expected_documents: list[ExpectedDocumentInput] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=1000)


class GoldenSetInput(BaseModel):
    """Create or replace the judgements of a golden set."""

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1", min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    queries: list[GoldenQueryInput] = Field(min_length=1)
    activate: bool = Field(
        default=False, description="Make this the set evaluations use by default."
    )


class GoldenSetImportInput(BaseModel):
    """Import a golden set from a file already on the server."""

    path: str = Field(min_length=1, description="Path readable by the API process.")
    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=50)
    activate: bool = True


class RunRequest(BaseModel):
    """Trigger an evaluation."""

    golden_set_id: int | None = Field(
        default=None, description="Defaults to the active golden set."
    )
    trigger: Literal["api", "cli", "scheduled"] = "api"


# ----------------------------------------------------------------------
# Responses
# ----------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness plus the two dependencies that can actually be down."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    version: str
    database: bool = Field(description="Schema reachable and migrated to head.")
    vector_store: bool
    message: str | None = None


class VectorStoreStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    connector: str
    collection: str
    reachable: bool
    document_count: int | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    message: str | None = None


class SystemInfoResponse(BaseModel):
    """Everything the dashboard's settings panel needs in one call."""

    model_config = ConfigDict(frozen=True)

    app_name: str
    version: str
    environment: str
    schema_revision: str | None
    vector_store: VectorStoreStatus
    available_connectors: tuple[str, ...]
    available_embedding_providers: tuple[str, ...]
    eval_k_values: tuple[int, ...]
    eval_primary_k: int
    run_count: int
    golden_set_count: int
    active_golden_set: GoldenSetRef | None = None


class DemoIndexState(BaseModel):
    """The demo index relative to the clean corpus, for the simulate-drift panel."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(description="Whether scenarios can be applied here.")
    document_count: int
    corpus_size: int
    missing_documents: int = Field(description="Corpus documents absent from the index.")
    fragment_documents: int = Field(description="Sentence fragments from a bad re-chunk.")
    healthy: bool


class DashboardSummary(BaseModel):
    """The at-a-glance payload behind the dashboard home screen.

    Assembled server-side so the first paint needs one request rather than
    four, and so "has this system ever been evaluated?" is answerable without
    the client inferring it from an empty list.
    """

    model_config = ConfigDict(frozen=True)

    has_runs: bool
    total_runs: int
    latest_run: RunRecord | None = None
    previous_run: RunRecord | None = None
    primary_metrics: MetricSet | None = None
    #: Change in each primary metric versus the previous comparable run.
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    active_golden_set: StoredGoldenSet | None = None
    last_run_at: datetime | None = None
    document_count: int | None = None

    #: Traffic light for the dashboard header.
    health: HealthStatus = "unknown"
    latest_drift: DriftAssessment | None = None
    open_regressions: int = Field(
        default=0, ge=0, description="Metrics currently flagged as regressed."
    )


def health_status(assessment: DriftAssessment | None, *, has_runs: bool) -> HealthStatus:
    """Map a drift verdict onto the dashboard traffic light.

    "Insufficient data" is amber rather than green on purpose: a system that
    has never been compared against anything is not known to be healthy, and
    showing green would be a claim the data does not support.
    """
    if not has_runs:
        return "unknown"
    if assessment is None:
        return "unknown"
    if assessment.verdict is DriftVerdict.DEGRADED:
        return "critical"
    if assessment.verdict is DriftVerdict.INSUFFICIENT_DATA:
        return "unknown"
    return "warning" if assessment.warnings else "healthy"


# ----------------------------------------------------------------------
# Input -> domain conversion
# ----------------------------------------------------------------------
def golden_set_from_input(payload: GoldenSetInput) -> GoldenSet:
    """Convert an API payload into the validated domain object.

    Pydantic has already enforced field-level constraints; constructing the
    domain object additionally enforces the invariants that span fields
    (unique query ids, unique documents per query), and any violation surfaces
    as a GoldenSetError the API maps to 400.
    """
    try:
        return GoldenSet(
            name=payload.name,
            version=payload.version,
            description=payload.description,
            queries=tuple(
                GoldenQuery(
                    query_id=query.query_id or f"q{position}",
                    query=query.query,
                    note=query.note,
                    expected_documents=tuple(
                        ExpectedDocument(
                            document_id=document.document_id,
                            relevance=document.relevance,
                        )
                        for document in query.expected_documents
                    ),
                )
                for position, query in enumerate(payload.queries, start=1)
            ),
        )
    except ValidationError as exc:
        errors = exc.errors()
        if not errors:  # pragma: no cover - pydantic always reports at least one
            raise GoldenSetError(str(exc)) from exc
        first = errors[0]
        location = ".".join(str(part) for part in first["loc"])
        message = first["msg"]
        raise GoldenSetError(
            f"{location}: {message}" if location else message
        ) from exc
