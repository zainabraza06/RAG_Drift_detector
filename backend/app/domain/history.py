"""Value objects for persisted history.

These sit between the ORM and the API: repositories return them, services
compose them, and FastAPI serialises them directly as response models. One
definition, three consumers -- rather than an ORM row, a service DTO and an
API schema that must be kept in sync by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.domain.golden_set import GoldenSet
from app.domain.metrics import MetricSet, QueryScore
from app.domain.retrieval import VectorStoreInfo

T = TypeVar("T")


class GoldenSetRef(BaseModel):
    """Identity of the golden set a run was scored against.

    Carried on every run as a snapshot rather than a live join: if the golden
    set is later edited or deleted, historical runs must still say truthfully
    which ruler produced their numbers.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    fingerprint: str


class RunRecord(BaseModel):
    """A persisted evaluation run, without its per-query detail."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(description="Stable public identifier (UUID).")
    golden_set: GoldenSetRef
    query_count: int = Field(ge=0)
    primary_k: int = Field(ge=1)
    metrics: tuple[MetricSet, ...] = Field(min_length=1)
    store: VectorStoreInfo
    started_at: datetime
    finished_at: datetime
    duration_ms: float = Field(ge=0)
    trigger: str = Field(description="How the run was started: api, cli, scheduled.")

    @property
    def primary_metrics(self) -> MetricSet:
        """Headline metrics, at :attr:`primary_k`."""
        for metric_set in self.metrics:
            if metric_set.k == self.primary_k:
                return metric_set
        raise KeyError(f"run {self.run_id} has no metrics at k={self.primary_k}")

    def metrics_at(self, k: int) -> MetricSet | None:
        """Metrics at cutoff ``k``, or ``None`` if the run did not evaluate it."""
        return next((m for m in self.metrics if m.k == k), None)


class RunDetail(BaseModel):
    """A run together with its per-query breakdown."""

    model_config = ConfigDict(frozen=True)

    run: RunRecord
    query_scores: tuple[QueryScore, ...] = ()

    @property
    def missed_queries(self) -> tuple[QueryScore, ...]:
        return tuple(score for score in self.query_scores if score.is_miss)


class MetricPoint(BaseModel):
    """One metric value at one point in time.

    ``document_count`` rides along because the trend chart's most useful
    overlay is corpus size: a recall decline that tracks corpus growth tells a
    very different story from one that does not.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    recorded_at: datetime
    value: float
    document_count: int = Field(ge=0)
    golden_set_fingerprint: str


class MetricSeries(BaseModel):
    """A named metric's values over time, oldest first."""

    model_config = ConfigDict(frozen=True)

    metric: str
    k: int = Field(ge=1)
    points: tuple[MetricPoint, ...] = ()

    @property
    def latest(self) -> MetricPoint | None:
        return self.points[-1] if self.points else None


class StoredGoldenSet(BaseModel):
    """A golden set as persisted, with its storage metadata."""

    model_config = ConfigDict(frozen=True)

    golden_set_id: int
    golden_set: GoldenSet
    is_active: bool
    source: str
    created_at: datetime

    @property
    def fingerprint(self) -> str:
        return self.golden_set.fingerprint

    @property
    def query_count(self) -> int:
        return len(self.golden_set)


class Page(BaseModel, Generic[T]):
    """A slice of a larger result set.

    ``total`` is the unfiltered-by-page count, which is what lets the UI render
    "showing 1-20 of 137" without a second request.
    """

    model_config = ConfigDict(frozen=True)

    items: tuple[T, ...] = ()
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
