"""The scoring engine: golden set + vector store -> metrics.

Responsibilities are kept narrow on purpose. The engine orchestrates; it does
not know how to talk to a specific vector store (that is a connector), how to
compute a metric (that is :mod:`app.services.scoring.metrics`), or where
results are stored (that is Stage 2).

One retrieval per query
-----------------------
Metrics for *every* configured cutoff are derived from a single retrieval of
``max(k_values)`` documents. Retrieval is the expensive step; computing
Recall@1, @3, @5 and @10 from one ranked list is both cheaper and more
consistent than issuing four queries whose results could differ.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.connectors.base import VectorStoreConnector
from app.core.errors import EvaluationError, VectorStoreError
from app.domain.golden_set import GoldenQuery, GoldenSet
from app.domain.metrics import EvaluationResult, MetricSet, QueryScore
from app.domain.retrieval import RetrievalResult
from app.services.scoring import metrics as m

logger = logging.getLogger(__name__)

DEFAULT_K_VALUES: tuple[int, ...] = (1, 3, 5, 10)
DEFAULT_PRIMARY_K = 5


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Cutoffs a run is evaluated at.

    ``primary_k`` is the headline cutoff: the one the dashboard shows, drift
    detection tests, and per-query detail is retained for.
    """

    k_values: tuple[int, ...] = DEFAULT_K_VALUES
    primary_k: int = DEFAULT_PRIMARY_K
    #: Continue the run when a single query fails against the store, scoring
    #: it as a total miss. Off by default: a partially-failed run would
    #: otherwise look like a genuine quality regression.
    tolerate_query_failures: bool = False
    _normalised: tuple[int, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.k_values:
            raise ValueError("at least one k value is required")
        if any(k < 1 for k in self.k_values):
            raise ValueError(f"k values must all be >= 1, got {self.k_values}")
        cutoffs = tuple(sorted(set(self.k_values)))
        object.__setattr__(self, "_normalised", cutoffs)
        if self.primary_k not in cutoffs:
            raise ValueError(
                f"primary_k={self.primary_k} must be one of k_values={cutoffs}"
            )

    @property
    def cutoffs(self) -> tuple[int, ...]:
        """Deduplicated, ascending cutoffs."""
        return self._normalised

    @property
    def retrieval_depth(self) -> int:
        """How many documents to fetch per query to cover every cutoff."""
        return max(self._normalised)


class ScoringEngine:
    """Runs a golden set against a vector store and scores the results."""

    def __init__(
        self,
        connector: VectorStoreConnector,
        config: ScoringConfig | None = None,
    ) -> None:
        self._connector = connector
        self._config = config or ScoringConfig()

    @property
    def config(self) -> ScoringConfig:
        return self._config

    def evaluate(self, golden_set: GoldenSet) -> EvaluationResult:
        """Score every query in ``golden_set`` against the connected store."""
        started_at = datetime.now(UTC)
        depth = self._config.retrieval_depth

        logger.info(
            "scoring golden set '%s' v%s (%d queries) at depth %d",
            golden_set.name,
            golden_set.version,
            len(golden_set),
            depth,
        )

        retrievals = [self._retrieve(query, depth) for query in golden_set.queries]

        scores_by_k = {
            k: [
                self._score_query(query, retrieval, k)
                for query, retrieval in zip(golden_set.queries, retrievals, strict=True)
            ]
            for k in self._config.cutoffs
        }

        metric_sets: tuple[MetricSet, ...] = tuple(
            m.aggregate_scores(scores_by_k[k], k) for k in self._config.cutoffs
        )

        try:
            store_info = self._connector.describe()
        except VectorStoreError as exc:
            raise EvaluationError(f"could not describe vector store: {exc}") from exc

        result = EvaluationResult(
            golden_set_name=golden_set.name,
            golden_set_version=golden_set.version,
            golden_set_fingerprint=golden_set.fingerprint,
            query_count=len(golden_set),
            primary_k=self._config.primary_k,
            metrics=metric_sets,
            query_scores=tuple(scores_by_k[self._config.primary_k]),
            store=store_info,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

        headline = result.primary_metrics
        logger.info(
            "run complete: recall@%d=%.4f ndcg@%d=%.4f mrr=%.4f",
            headline.k,
            headline.recall_at_k,
            headline.k,
            headline.ndcg_at_k,
            headline.mrr,
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _retrieve(self, query: GoldenQuery, depth: int) -> RetrievalResult:
        try:
            return self._connector.search_with_timing(query.query_id, query.query, depth)
        except VectorStoreError as exc:
            if not self._config.tolerate_query_failures:
                raise EvaluationError(
                    f"retrieval failed for query '{query.query_id}': {exc}"
                ) from exc
            logger.warning(
                "query '%s' failed and was scored as a miss: %s", query.query_id, exc
            )
            return RetrievalResult(query_id=query.query_id, query=query.query)

    @staticmethod
    def _score_query(
        query: GoldenQuery, retrieval: RetrievalResult, k: int
    ) -> QueryScore:
        retrieved: Sequence[str] = retrieval.top_k_ids(k)
        relevant = query.relevant_document_ids
        relevance = {
            doc.document_id: doc.relevance for doc in query.expected_documents
        }
        hits = sum(1 for doc_id in set(retrieved) if doc_id in relevant)

        return QueryScore(
            query_id=query.query_id,
            query=query.query,
            k=k,
            retrieved_ids=tuple(retrieved),
            relevant_ids=tuple(sorted(relevant)),
            hits=hits,
            recall_at_k=m.recall_at_k(retrieved, relevant, k),
            precision_at_k=m.precision_at_k(retrieved, relevant, k),
            reciprocal_rank=m.reciprocal_rank(retrieved, relevant, k),
            ndcg_at_k=m.ndcg_at_k(retrieved, relevance, k),
            first_relevant_rank=m.first_relevant_rank(retrieved, relevant, k),
            latency_ms=retrieval.latency_ms,
        )
