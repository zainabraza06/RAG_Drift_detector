"""Evaluation run orchestration.

Combines the three collaborators a run needs -- the golden set service, the
scoring engine and the run repository -- and owns the ordering between them.
Route handlers call one method here and format the result; they never touch a
repository or the engine directly.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.core.errors import RunNotFoundError
from app.domain.history import MetricSeries, Page, RunDetail, RunRecord
from app.repositories.runs import RunRepository
from app.services.drift_service import DriftService
from app.services.golden_set_service import GoldenSetService
from app.services.scoring.engine import ScoringEngine

logger = logging.getLogger(__name__)

# Re-exported: this was the error's original home, and callers import it here.
__all__ = ["RunNotFoundError", "RunService", "metric_deltas"]


class RunService:
    """Executes evaluations and serves their history."""

    def __init__(
        self,
        *,
        engine: ScoringEngine,
        runs: RunRepository,
        golden_sets: GoldenSetService,
        drift: DriftService | None = None,
    ) -> None:
        self._engine = engine
        self._runs = runs
        self._golden_sets = golden_sets
        self._drift = drift

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(
        self, *, golden_set_id: int | None = None, trigger: str = "api"
    ) -> RunRecord:
        """Score a golden set against the vector store and persist the result."""
        stored = self._golden_sets.resolve(golden_set_id)
        logger.info(
            "starting evaluation of golden set '%s' v%s (trigger=%s)",
            stored.golden_set.name,
            stored.golden_set.version,
            trigger,
        )
        result = self._engine.evaluate(stored.golden_set)
        record = self._runs.save(
            result, golden_set_id=stored.golden_set_id, trigger=trigger
        )
        if self._drift is not None:
            # Assessing here means a run is never sitting in history without a
            # verdict. It cannot fail the evaluation: the run is already saved,
            # and assess_if_possible swallows and logs anything that goes wrong.
            self._drift.assess_if_possible(record.run_id)
        return record

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def get(self, run_id: str) -> RunRecord:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(f"run '{run_id}' not found")
        return record

    def get_detail(self, run_id: str) -> RunDetail:
        detail = self._runs.get_detail(run_id)
        if detail is None:
            raise RunNotFoundError(f"run '{run_id}' not found")
        return detail

    def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        golden_set_name: str | None = None,
        fingerprint: str | None = None,
        since: datetime | None = None,
    ) -> Page[RunRecord]:
        return self._runs.list_runs(
            limit=limit,
            offset=offset,
            golden_set_name=golden_set_name,
            fingerprint=fingerprint,
            since=since,
        )

    def latest(self, *, fingerprint: str | None = None) -> RunRecord | None:
        return self._runs.latest(fingerprint=fingerprint)

    def series(
        self,
        *,
        metric: str,
        k: int,
        limit: int = 50,
        fingerprint: str | None = None,
    ) -> MetricSeries:
        return self._runs.series(
            metric=metric, k=k, limit=limit, fingerprint=fingerprint
        )

    def delete(self, run_id: str) -> None:
        if not self._runs.delete(run_id):
            raise RunNotFoundError(f"run '{run_id}' not found")

    def count(self) -> int:
        return self._runs.count()

    def evaluated_cutoffs(self) -> tuple[int, ...]:
        """Cutoffs that actually have stored data, for the chart's k selector."""
        return self._runs.evaluated_cutoffs()

    def latest_pair(self) -> tuple[RunRecord | None, RunRecord | None]:
        """The newest run, and the run before it scored against the same set.

        The pair is scoped to one fingerprint so a dashboard delta never
        compares numbers produced by two different golden sets.
        """
        latest = self._runs.latest()
        if latest is None:
            return None, None
        recent = self._runs.recent(
            limit=2, fingerprint=latest.golden_set.fingerprint
        )
        previous = recent[1] if len(recent) > 1 else None
        return latest, previous


def metric_deltas(
    current: RunRecord, previous: RunRecord | None
) -> dict[str, float]:
    """Change in each headline metric versus ``previous``.

    Empty when there is nothing to compare against, or when the previous run
    did not evaluate the current run's primary cutoff -- an absent delta is
    more honest than a zero the UI would render as "no change".
    """
    if previous is None:
        return {}
    previous_metrics = previous.metrics_at(current.primary_k)
    if previous_metrics is None:
        return {}
    current_values = current.primary_metrics.as_dict()
    baseline_values = previous_metrics.as_dict()
    return {
        name: current_values[name] - baseline_values[name] for name in current_values
    }
