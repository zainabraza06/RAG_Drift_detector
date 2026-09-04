"""Drift assessment orchestration.

Fetches the run and its comparable history, hands them to the detector, and
stores the verdict. The detector itself stays pure: it takes runs and returns
an assessment, with no idea where either came from.
"""

from __future__ import annotations

import logging

from app.connectors.base import VectorStoreConnector
from app.core.errors import DiagnosticsUnavailableError, RunNotFoundError, VectorStoreError
from app.domain.diagnostics import DiagnosticReport
from app.domain.drift import DriftAssessment, DriftConfig, DriftVerdict
from app.domain.history import Page, RunDetail
from app.repositories.drift import DriftRepository
from app.repositories.runs import RunRepository
from app.services.diagnostics import DiagnosticContext, DiagnosticEngine, IndexProbe
from app.services.drift.detector import DriftDetector

logger = logging.getLogger(__name__)

#: How many earlier runs to pull as *candidates*. The detector then filters
#: for comparability and keeps at most ``config.baseline_window`` of them, so
#: a stretch of runs against a since-edited golden set cannot starve the
#: baseline of usable history.
BASELINE_CANDIDATE_MULTIPLIER = 4
MIN_BASELINE_CANDIDATES = 10


class DriftService:
    """Assesses runs for drift and serves stored assessments."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        drift: DriftRepository,
        config: DriftConfig | None = None,
        vector_store: VectorStoreConnector | None = None,
        diagnostics: DiagnosticEngine | None = None,
    ) -> None:
        self._runs = runs
        self._drift = drift
        self._config = config or DriftConfig()
        self._detector = DriftDetector(self._config)
        self._vector_store = vector_store
        self._diagnostics = diagnostics or DiagnosticEngine()

    @property
    def config(self) -> DriftConfig:
        return self._config

    # ------------------------------------------------------------------
    # Assessment
    # ------------------------------------------------------------------
    def assess(self, run_id: str, *, store: bool = True) -> DriftAssessment:
        """Assess one run against its comparable predecessors."""
        current = self._runs.get_detail(run_id)
        if current is None:
            raise RunNotFoundError(f"run '{run_id}' not found")

        candidates = max(
            MIN_BASELINE_CANDIDATES,
            self._config.baseline_window * BASELINE_CANDIDATE_MULTIPLIER,
        )
        # Only runs that came *before* this one; a baseline built from later
        # runs would be comparing the present against the future.
        earlier = self._runs.recent(
            limit=candidates,
            fingerprint=current.run.golden_set.fingerprint,
            before=current.run.started_at,
        )
        baseline = [
            detail
            for detail in (self._runs.get_detail(record.run_id) for record in earlier)
            if detail is not None
        ]

        assessment = self._detector.assess(current, baseline)

        # Diagnostics only ever explain a verdict the statistics established;
        # they are never run to *produce* one, and never on a healthy run.
        if assessment.verdict is DriftVerdict.DEGRADED:
            report = self._diagnostics.diagnose(
                DiagnosticContext(
                    assessment=assessment,
                    current=current,
                    baseline=baseline,
                    index=self._probe_index(current),
                )
            )
            assessment = assessment.model_copy(update={"diagnostics": report})

        if store:
            return self._drift.save(assessment)
        return assessment

    def _probe_index(self, current: RunDetail) -> IndexProbe:
        """Gather live index facts once, for every rule to share.

        Failure is reported as an unreachable probe rather than raised: rules
        that need the index then record themselves as skipped, and the rest of
        the report still gets produced.
        """
        if self._vector_store is None:
            return IndexProbe(
                reachable=False,
                failure_reason="no vector store was available to this process",
            )

        expected = {
            document_id
            for score in current.query_scores
            for document_id in score.relevant_ids
        }
        try:
            present = self._vector_store.existing_document_ids(sorted(expected))
            count = self._vector_store.count_documents()
        except VectorStoreError as exc:
            logger.warning("index probe failed during diagnostics: %s", exc)
            return IndexProbe(reachable=False, failure_reason=str(exc))

        return IndexProbe(
            document_count=count,
            present_document_ids=present,
            missing_document_ids=frozenset(expected) - present,
            reachable=True,
        )

    def assess_if_possible(self, run_id: str) -> DriftAssessment | None:
        """Assess a run without letting a failure break the caller.

        Used on the evaluation path: a run is valuable on its own, and a drift
        assessment that blows up must not lose the run that was just scored.
        """
        try:
            return self.assess(run_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("drift assessment failed for run %s", run_id)
            return None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def find_for_run(self, run_id: str) -> DriftAssessment | None:
        """The stored assessment for a run, or None. Never raises.

        Used by the dashboard, which must render even when no run has been
        assessed yet - a missing verdict is an empty state, not an error.
        """
        return self._drift.get_for_run(run_id)

    def get_for_run(self, run_id: str, *, compute: bool = True) -> DriftAssessment:
        """The stored assessment for a run, computing it on first request."""
        stored = self._drift.get_for_run(run_id)
        if stored is not None:
            return stored
        if not compute:
            raise RunNotFoundError(f"no drift assessment stored for run '{run_id}'")
        return self.assess(run_id)

    def diagnostics_for_run(self, run_id: str) -> DiagnosticReport:
        """The heuristic report for a run, computing the assessment if needed."""
        assessment = self.get_for_run(run_id)
        if assessment.diagnostics is None:
            raise DiagnosticsUnavailableError(
                f"no diagnostics for run '{run_id}': its verdict is "
                f"'{assessment.verdict.value}', and diagnostics are only produced "
                "for a regression."
            )
        return assessment.diagnostics

    def list_events(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        verdict: DriftVerdict | None = None,
        fingerprint: str | None = None,
    ) -> Page[DriftAssessment]:
        return self._drift.list_events(
            limit=limit, offset=offset, verdict=verdict, fingerprint=fingerprint
        )

    def latest(self) -> DriftAssessment | None:
        return self._drift.latest()

    def count(self, *, verdict: DriftVerdict | None = None) -> int:
        return self._drift.count(verdict=verdict)
