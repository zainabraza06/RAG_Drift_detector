"""Metric value objects produced by the scoring engine."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.retrieval import VectorStoreInfo

#: Canonical metric names, used as the vocabulary shared by the scoring
#: engine, the persistence layer, the drift detector and the API.
METRIC_NAMES: tuple[str, ...] = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k")


class QueryScore(BaseModel):
    """Per-query breakdown at a single cutoff ``k``.

    Kept alongside the aggregates because drift is far easier to explain when
    you can point at *which* queries regressed.
    """

    model_config = ConfigDict(frozen=True)

    query_id: str
    query: str
    k: int = Field(ge=1)
    retrieved_ids: tuple[str, ...]
    relevant_ids: tuple[str, ...]
    hits: int = Field(ge=0, description="Relevant documents found within top-k.")
    recall_at_k: float = Field(ge=0.0, le=1.0)
    precision_at_k: float = Field(ge=0.0, le=1.0)
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)
    first_relevant_rank: int | None = Field(
        default=None, ge=1, description="1-based rank of the first hit, if any."
    )
    latency_ms: float | None = Field(default=None, ge=0)

    @property
    def is_miss(self) -> bool:
        """True when the query retrieved none of its expected documents."""
        return self.hits == 0


class MetricSet(BaseModel):
    """Macro-averaged metrics over every query in the golden set at one ``k``.

    Macro (per-query) averaging is used deliberately: it weights every query
    equally so a handful of queries with many expected documents cannot mask a
    broad regression across the rest of the set.
    """

    model_config = ConfigDict(frozen=True)

    k: int = Field(ge=1)
    query_count: int = Field(ge=0)
    recall_at_k: float = Field(ge=0.0, le=1.0)
    precision_at_k: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)

    def as_dict(self) -> dict[str, float]:
        """Metric name -> value, restricted to :data:`METRIC_NAMES`."""
        return {name: float(getattr(self, name)) for name in METRIC_NAMES}


class EvaluationResult(BaseModel):
    """The complete output of one scoring run.

    Per-query detail is retained only for ``primary_k`` — the cutoff drift
    detection and the dashboard headline numbers are based on — to keep stored
    runs small while still supporting query-level explanation.
    """

    model_config = ConfigDict(frozen=True)

    golden_set_name: str
    golden_set_version: str
    golden_set_fingerprint: str
    query_count: int = Field(ge=0)
    primary_k: int = Field(ge=1)
    metrics: tuple[MetricSet, ...] = Field(min_length=1)
    query_scores: tuple[QueryScore, ...] = ()
    store: VectorStoreInfo
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000.0

    @property
    def evaluated_k_values(self) -> tuple[int, ...]:
        return tuple(m.k for m in self.metrics)

    def metrics_at(self, k: int) -> MetricSet:
        """The :class:`MetricSet` computed at cutoff ``k``."""
        for metric_set in self.metrics:
            if metric_set.k == k:
                return metric_set
        raise KeyError(
            f"run has no metrics at k={k}; evaluated k values: {self.evaluated_k_values}"
        )

    @property
    def primary_metrics(self) -> MetricSet:
        """Headline metrics — those computed at :attr:`primary_k`."""
        return self.metrics_at(self.primary_k)

    @property
    def missed_queries(self) -> tuple[QueryScore, ...]:
        """Queries that retrieved none of their expected documents."""
        return tuple(score for score in self.query_scores if score.is_miss)
