"""Drift assessment orchestration.

Fetches the run and its comparable history, hands them to the detector, and
stores the verdict. The detector itself stays pure: it takes runs and returns
an assessment, with no idea where either came from.
"""

from __future__ import annotations

import logging

from app.core.errors import RunNotFoundError
from app.domain.drift import DriftAssessment, DriftConfig, DriftVerdict
from app.domain.history import Page
from app.repositories.drift import DriftRepository
from app.repositories.runs import RunRepository
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
    ) -> None:
        self._runs = runs
        self._drift = drift
        self._config = config or DriftConfig()
        self._detector = DriftDetector(self._config)

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
        if store:
            return self._drift.save(assessment)
        return assessment

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
