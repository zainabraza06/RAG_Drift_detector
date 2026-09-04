"""Persistence for evaluation runs.

The repository owns SQL and nothing else: no scoring, no drift logic, no HTTP
concerns. It accepts and returns domain objects, so services above it are
testable against an in-memory database and never see a SQLAlchemy type.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import DriftDetectorError
from app.db.base import as_utc
from app.db.models import EvaluationRunRow, QueryScoreRow, RunMetricRow
from app.domain.history import MetricPoint, MetricSeries, Page, RunDetail, RunRecord
from app.domain.metrics import METRIC_NAMES, EvaluationResult
from app.repositories.mappers import (
    row_to_query_score,
    row_to_run_record,
)

logger = logging.getLogger(__name__)

#: Metric name -> the column holding it. Keeps callers from passing arbitrary
#: strings into a query, and keeps the API's `metric=` parameter honest.
_METRIC_COLUMNS = {
    "recall_at_k": RunMetricRow.recall_at_k,
    "precision_at_k": RunMetricRow.precision_at_k,
    "mrr": RunMetricRow.mrr,
    "ndcg_at_k": RunMetricRow.ndcg_at_k,
}

MAX_PAGE_SIZE = 200


class UnknownMetricError(DriftDetectorError):
    """A metric was requested by a name the system does not compute."""


class RunRepository:
    """Reads and writes evaluation run history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save(
        self,
        result: EvaluationResult,
        *,
        golden_set_id: int | None = None,
        trigger: str = "api",
    ) -> RunRecord:
        """Persist a completed run and return its stored form."""
        row = EvaluationRunRow(
            run_uuid=str(uuid.uuid4()),
            golden_set_id=golden_set_id,
            golden_set_name=result.golden_set_name,
            golden_set_version=result.golden_set_version,
            golden_set_fingerprint=result.golden_set_fingerprint,
            query_count=result.query_count,
            primary_k=result.primary_k,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_ms=result.duration_ms,
            connector=result.store.connector,
            collection=result.store.collection,
            document_count=result.store.document_count,
            embedding_model=result.store.embedding_model,
            embedding_dimensions=result.store.embedding_dimensions,
            store_extra=dict(result.store.extra),
            trigger=trigger,
            metrics=[
                RunMetricRow(
                    k=metric_set.k,
                    query_count=metric_set.query_count,
                    recall_at_k=metric_set.recall_at_k,
                    precision_at_k=metric_set.precision_at_k,
                    mrr=metric_set.mrr,
                    ndcg_at_k=metric_set.ndcg_at_k,
                )
                for metric_set in result.metrics
            ],
            query_scores=[
                QueryScoreRow(
                    query_id=score.query_id,
                    query_text=score.query,
                    k=score.k,
                    hits=score.hits,
                    recall_at_k=score.recall_at_k,
                    precision_at_k=score.precision_at_k,
                    reciprocal_rank=score.reciprocal_rank,
                    ndcg_at_k=score.ndcg_at_k,
                    first_relevant_rank=score.first_relevant_rank,
                    retrieved_ids=list(score.retrieved_ids),
                    relevant_ids=list(score.relevant_ids),
                    latency_ms=score.latency_ms,
                )
                for score in result.query_scores
            ],
        )
        self._session.add(row)
        self._session.flush()
        logger.info("stored run %s (%d queries)", row.run_uuid, row.query_count)
        return row_to_run_record(row)

    def delete(self, run_id: str) -> bool:
        """Delete a run and its children. Returns whether anything was removed."""
        # ON DELETE CASCADE handles metrics and query scores, which is only
        # true because session.py turns on SQLite's foreign_keys pragma.
        result = self._session.execute(
            delete(EvaluationRunRow).where(EvaluationRunRow.run_uuid == run_id)
        )
        return bool(result.rowcount)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, run_id: str) -> RunRecord | None:
        row = self._row(run_id)
        return row_to_run_record(row) if row is not None else None

    def get_detail(self, run_id: str) -> RunDetail | None:
        """A run with its per-query breakdown eagerly loaded."""
        row = self._session.scalars(
            select(EvaluationRunRow)
            .where(EvaluationRunRow.run_uuid == run_id)
            .options(selectinload(EvaluationRunRow.query_scores))
        ).one_or_none()
        if row is None:
            return None
        return RunDetail(
            run=row_to_run_record(row),
            query_scores=tuple(row_to_query_score(score) for score in row.query_scores),
        )

    def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        golden_set_name: str | None = None,
        fingerprint: str | None = None,
        since: datetime | None = None,
    ) -> Page[RunRecord]:
        """A page of runs, newest first."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        filters = self._filters(golden_set_name, fingerprint, since)
        total = self._session.scalar(
            select(func.count()).select_from(EvaluationRunRow).where(*filters)
        )
        rows = self._session.scalars(
            select(EvaluationRunRow)
            .where(*filters)
            .order_by(EvaluationRunRow.started_at.desc(), EvaluationRunRow.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        return Page[RunRecord](
            items=tuple(row_to_run_record(row) for row in rows),
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    def latest(
        self,
        *,
        golden_set_name: str | None = None,
        fingerprint: str | None = None,
    ) -> RunRecord | None:
        """The most recent run, optionally scoped to one golden set."""
        row = self._session.scalars(
            select(EvaluationRunRow)
            .where(*self._filters(golden_set_name, fingerprint, None))
            .order_by(EvaluationRunRow.started_at.desc(), EvaluationRunRow.id.desc())
            .limit(1)
        ).one_or_none()
        return row_to_run_record(row) if row is not None else None

    def recent(
        self,
        *,
        limit: int = 10,
        fingerprint: str | None = None,
        before: datetime | None = None,
    ) -> tuple[RunRecord, ...]:
        """The ``limit`` most recent runs, newest first.

        Scoping by ``fingerprint`` is how drift detection guarantees it is
        comparing runs scored against identical ground truth.
        """
        query = select(EvaluationRunRow).where(
            *self._filters(None, fingerprint, None)
        )
        if before is not None:
            query = query.where(EvaluationRunRow.started_at < before)
        rows = self._session.scalars(
            query.order_by(
                EvaluationRunRow.started_at.desc(), EvaluationRunRow.id.desc()
            ).limit(max(1, limit))
        ).all()
        return tuple(row_to_run_record(row) for row in rows)

    def series(
        self,
        *,
        metric: str,
        k: int,
        limit: int = 50,
        fingerprint: str | None = None,
        golden_set_name: str | None = None,
    ) -> MetricSeries:
        """One metric's history at one cutoff, oldest point first."""
        column = _METRIC_COLUMNS.get(metric)
        if column is None:
            raise UnknownMetricError(
                f"unknown metric '{metric}'; expected one of {', '.join(METRIC_NAMES)}"
            )

        rows = self._session.execute(
            select(
                EvaluationRunRow.run_uuid,
                EvaluationRunRow.started_at,
                EvaluationRunRow.document_count,
                EvaluationRunRow.golden_set_fingerprint,
                column,
            )
            .join(RunMetricRow, RunMetricRow.run_id == EvaluationRunRow.id)
            .where(RunMetricRow.k == k)
            .where(*self._filters(golden_set_name, fingerprint, None))
            # Take the newest N, then reverse: a chart wants the *latest*
            # window of history, rendered oldest-to-newest.
            .order_by(EvaluationRunRow.started_at.desc(), EvaluationRunRow.id.desc())
            .limit(max(1, min(limit, MAX_PAGE_SIZE)))
        ).all()

        points = tuple(
            MetricPoint(
                run_id=run_uuid,
                # SQLite drops tzinfo on the round trip; every timestamp is
                # written as UTC, so re-attach it rather than emitting a naive
                # datetime the client would read in its own local zone.
                recorded_at=as_utc(started_at),
                value=float(value),
                document_count=document_count,
                golden_set_fingerprint=run_fingerprint,
            )
            for run_uuid, started_at, document_count, run_fingerprint, value in reversed(
                rows
            )
        )
        return MetricSeries(metric=metric, k=k, points=points)

    def count(self, *, fingerprint: str | None = None) -> int:
        total = self._session.scalar(
            select(func.count())
            .select_from(EvaluationRunRow)
            .where(*self._filters(None, fingerprint, None))
        )
        return int(total or 0)

    def evaluated_cutoffs(self) -> tuple[int, ...]:
        """Distinct ``k`` values present in stored history, ascending.

        The dashboard uses this to offer only cutoffs that actually have data.
        """
        rows = self._session.scalars(
            select(RunMetricRow.k).distinct().order_by(RunMetricRow.k)
        ).all()
        return tuple(int(k) for k in rows)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _row(self, run_id: str) -> EvaluationRunRow | None:
        return self._session.scalars(
            select(EvaluationRunRow).where(EvaluationRunRow.run_uuid == run_id)
        ).one_or_none()

    @staticmethod
    def _filters(
        golden_set_name: str | None,
        fingerprint: str | None,
        since: datetime | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if golden_set_name:
            filters.append(EvaluationRunRow.golden_set_name == golden_set_name)
        if fingerprint:
            filters.append(EvaluationRunRow.golden_set_fingerprint == fingerprint)
        if since is not None:
            filters.append(EvaluationRunRow.started_at >= since)
        return filters
