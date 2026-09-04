"""Populate a realistic evaluation history for the demo.

A freshly started instance has nothing to show: one run is not a trend, and
drift detection needs a baseline. This script produces a history worth looking
at, by running *real* evaluations against the *real* index and deliberately
breaking retrieval part way through.

Every metric, interval, p-value and diagnostic it produces is genuine — the
scoring engine and the drift detector do the same work they always do. The
only thing simulated is **when** the runs happened: they are stamped across
the past few days so the trend charts have a readable x-axis instead of a
dozen points inside the same minute.

    python -m scripts.seed_demo_history --days 12

Use ``--reset`` to clear existing history first. Intended for demos and
screenshots; it is not imported by the application.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.core.factory import build_scoring_engine, build_vector_store
from app.core.logging import configure_logging
from app.db.models import DriftEventRow, EvaluationRunRow
from app.db.session import session_scope
from app.domain.metrics import EvaluationResult
from app.repositories.drift import DriftRepository
from app.repositories.golden_sets import GoldenSetRepository
from app.repositories.runs import RunRepository
from app.services.bootstrap import bootstrap
from app.services.drift_service import DriftService
from app.services.golden_set_service import GoldenSetService

logger = logging.getLogger("seed_demo_history")

#: Documents removed part way through to create a genuine regression. They are
#: spread across categories so several unrelated queries break at once, which
#: is what a botched re-index actually looks like.
BROKEN_DOCUMENTS = [
    "doc-api-001",
    "doc-api-002",
    "doc-auth-003",
    "doc-security-003",
    "doc-data-002",
    "doc-support-003",
]


@dataclass(frozen=True, slots=True)
class Timeline:
    """How many runs to produce, and when the breakage happens."""

    total_runs: int
    break_after: int
    days: int

    def started_at(self, index: int) -> datetime:
        """Evenly space runs across the window, ending roughly now."""
        step = timedelta(days=self.days) / max(self.total_runs - 1, 1)
        return datetime.now(UTC) - step * (self.total_runs - 1 - index)


def _clear_history(settings: Settings) -> None:
    with session_scope(settings) as session:
        session.query(DriftEventRow).delete()
        session.query(EvaluationRunRow).delete()
    logger.info("cleared existing run history")


def _restamp(result: EvaluationResult, moment: datetime) -> EvaluationResult:
    """Return the result with simulated start/finish timestamps.

    Only the clock is adjusted; every metric in the result was computed by the
    scoring engine from a real retrieval against the real index.
    """
    return result.model_copy(
        update={
            "started_at": moment,
            "finished_at": moment + timedelta(milliseconds=result.duration_ms or 0),
        }
    )


def seed(settings: Settings, timeline: Timeline, *, reset: bool) -> int:
    bootstrap(settings=settings)
    if reset:
        _clear_history(settings)

    with build_vector_store(settings) as store:
        engine = build_scoring_engine(settings, connector=store)

        with session_scope(settings) as session:
            golden_sets = GoldenSetService(GoldenSetRepository(session))
            stored = golden_sets.get_active()
            golden_set = stored.golden_set
            golden_set_id = stored.golden_set_id

        run_ids: list[str] = []
        for index in range(timeline.total_runs):
            if index == timeline.break_after:
                removed = store.delete_documents(BROKEN_DOCUMENTS)  # type: ignore[attr-defined]
                logger.info(
                    "removed %d expected documents to create a regression", removed
                )

            result = _restamp(engine.evaluate(golden_set), timeline.started_at(index))

            # Each run is saved and assessed in its own transaction, because
            # the drift detector reads the runs that came before it.
            with session_scope(settings) as session:
                record = RunRepository(session).save(
                    result, golden_set_id=golden_set_id, trigger="scheduled"
                )
                run_ids.append(record.run_id)

            with session_scope(settings) as session:
                DriftService(
                    runs=RunRepository(session),
                    drift=DriftRepository(session),
                    vector_store=store,
                ).assess(record.run_id)

            metrics = result.primary_metrics
            logger.info(
                "run %d/%d  ndcg@%d=%.4f recall@%d=%.4f",
                index + 1,
                timeline.total_runs,
                metrics.k,
                metrics.ndcg_at_k,
                metrics.k,
                metrics.recall_at_k,
            )

    with session_scope(settings) as session:
        verdicts = DriftRepository(session).list_events(limit=timeline.total_runs)
        summary = {
            verdict: sum(1 for item in verdicts.items if item.verdict.value == verdict)
            for verdict in ("degraded", "stable", "improved", "insufficient_data")
        }

    print(f"\nSeeded {len(run_ids)} runs across {timeline.days} days.")
    print(f"  verdicts: {summary}")
    print(f"  removed:  {len(BROKEN_DOCUMENTS)} documents before run "
          f"{timeline.break_after + 1}")
    print("\nRestore the index with:  python -m app.cli seed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", type=int, default=10, help="Total runs to produce.")
    parser.add_argument(
        "--break-after",
        type=int,
        default=7,
        help="Break retrieval before this run index (0-based).",
    )
    parser.add_argument("--days", type=int, default=12, help="Window to spread across.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing history first."
    )
    args = parser.parse_args(argv)

    if not 0 < args.break_after < args.runs:
        parser.error("--break-after must be between 1 and --runs - 1")

    settings = get_settings()
    configure_logging(settings.log_level)
    return seed(
        settings,
        Timeline(total_runs=args.runs, break_after=args.break_after, days=args.days),
        reset=args.reset,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
