"""Persistence for drift assessments."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.db.models import DriftEventRow, EvaluationRunRow
from app.domain.diagnostics import DiagnosticReport
from app.domain.drift import (
    DriftAssessment,
    DriftConfig,
    DriftVerdict,
    HitRateComparison,
    MetricComparison,
)
from app.domain.history import GoldenSetRef, Page

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 200


class DriftRepository:
    """Reads and writes stored drift assessments."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save(self, assessment: DriftAssessment) -> DriftAssessment:
        """Store an assessment, replacing any previous one for the same run.

        Re-assessing a run with more baseline history is a legitimate thing to
        do, and a run should have exactly one current verdict rather than a
        pile of superseded ones.
        """
        run_row = self._run_row(assessment.run_id)
        if run_row is None:
            raise ValueError(f"cannot store drift for unknown run '{assessment.run_id}'")

        row = self._session.scalars(
            select(DriftEventRow).where(DriftEventRow.run_id == run_row.id)
        ).one_or_none()
        if row is None:
            row = DriftEventRow(event_uuid=str(uuid.uuid4()), run_id=run_row.id)
            self._session.add(row)

        row.verdict = assessment.verdict.value
        row.summary = assessment.summary
        row.query_count = assessment.query_count
        row.golden_set_fingerprint = assessment.golden_set.fingerprint
        row.baseline_run_ids = list(assessment.baseline_run_ids)
        row.comparisons = [
            comparison.model_dump(mode="json") for comparison in assessment.comparisons
        ]
        row.hit_rate = (
            assessment.hit_rate.model_dump(mode="json") if assessment.hit_rate else None
        )
        row.warnings = list(assessment.warnings)
        row.config = assessment.config.model_dump(mode="json")
        row.diagnostics = (
            assessment.diagnostics.model_dump(mode="json")
            if assessment.diagnostics
            else None
        )
        row.detected_at = assessment.detected_at

        self._session.flush()
        logger.info(
            "stored drift event %s for run %s (%s)",
            row.event_uuid,
            assessment.run_id,
            assessment.verdict.value,
        )
        return self._to_assessment(row, assessment.golden_set)

    def delete_for_run(self, run_id: str) -> bool:
        run_row = self._run_row(run_id)
        if run_row is None:
            return False
        row = self._session.scalars(
            select(DriftEventRow).where(DriftEventRow.run_id == run_row.id)
        ).one_or_none()
        if row is None:
            return False
        self._session.delete(row)
        return True

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_for_run(self, run_id: str) -> DriftAssessment | None:
        row = self._session.scalars(
            select(DriftEventRow)
            .join(EvaluationRunRow, DriftEventRow.run_id == EvaluationRunRow.id)
            .where(EvaluationRunRow.run_uuid == run_id)
        ).one_or_none()
        return self._to_assessment(row) if row is not None else None

    def list_events(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        verdict: DriftVerdict | None = None,
        fingerprint: str | None = None,
    ) -> Page[DriftAssessment]:
        """A page of assessments, newest first."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        filters = []
        if verdict is not None:
            filters.append(DriftEventRow.verdict == verdict.value)
        if fingerprint:
            filters.append(DriftEventRow.golden_set_fingerprint == fingerprint)

        total = self._session.scalar(
            select(func.count()).select_from(DriftEventRow).where(*filters)
        )
        rows = self._session.scalars(
            select(DriftEventRow)
            .where(*filters)
            .order_by(DriftEventRow.detected_at.desc(), DriftEventRow.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        return Page[DriftAssessment](
            items=tuple(self._to_assessment(row) for row in rows),
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    def latest(self) -> DriftAssessment | None:
        row = self._session.scalars(
            select(DriftEventRow)
            .order_by(DriftEventRow.detected_at.desc(), DriftEventRow.id.desc())
            .limit(1)
        ).one_or_none()
        return self._to_assessment(row) if row is not None else None

    def count(self, *, verdict: DriftVerdict | None = None) -> int:
        filters = [] if verdict is None else [DriftEventRow.verdict == verdict.value]
        total = self._session.scalar(
            select(func.count()).select_from(DriftEventRow).where(*filters)
        )
        return int(total or 0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _run_row(self, run_id: str) -> EvaluationRunRow | None:
        return self._session.scalars(
            select(EvaluationRunRow).where(EvaluationRunRow.run_uuid == run_id)
        ).one_or_none()

    @staticmethod
    def _to_assessment(
        row: DriftEventRow, golden_set: GoldenSetRef | None = None
    ) -> DriftAssessment:
        reference = golden_set or GoldenSetRef(
            name=row.run.golden_set_name,
            version=row.run.golden_set_version,
            fingerprint=row.golden_set_fingerprint,
        )
        return DriftAssessment(
            run_id=row.run.run_uuid,
            baseline_run_ids=tuple(row.baseline_run_ids or ()),
            golden_set=reference,
            verdict=DriftVerdict(row.verdict),
            summary=row.summary,
            comparisons=tuple(
                MetricComparison.model_validate(entry)
                for entry in (row.comparisons or [])
            ),
            hit_rate=(
                HitRateComparison.model_validate(row.hit_rate) if row.hit_rate else None
            ),
            query_count=row.query_count,
            warnings=tuple(row.warnings or ()),
            config=DriftConfig.model_validate(row.config or {}),
            diagnostics=(
                DiagnosticReport.model_validate(row.diagnostics)
                if row.diagnostics
                else None
            ),
            detected_at=as_utc(row.detected_at),
        )
