"""Tests for the drift detector's orchestration and verdict logic."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.domain.drift import DriftConfig, DriftVerdict
from app.domain.history import GoldenSetRef, RunDetail, RunRecord
from app.domain.metrics import MetricSet, QueryScore
from app.domain.retrieval import VectorStoreInfo
from app.services.drift.detector import PER_QUERY_ATTRIBUTE, DriftDetector
from app.services.scoring.engine import ScoringConfig, ScoringEngine
from tests.conftest import FakeConnector, make_golden_set

# Small resample count keeps the suite fast; the statistical properties
# themselves are pinned in test_drift_statistics.py.
FAST = DriftConfig(resamples=800, min_queries=10)


def make_detail(
    run_id: str,
    scores: Sequence[float],
    *,
    fingerprint: str = "fp-a",
    primary_k: int = 5,
    started_at: datetime | None = None,
    hits: Sequence[int] | None = None,
) -> RunDetail:
    """A run whose every per-query metric equals ``scores[i]``.

    Setting all four metrics from one value keeps the tests about the
    detector's logic rather than about metric arithmetic.
    """
    moment = started_at or datetime.now(UTC)
    hit_counts = list(hits) if hits is not None else [1 if s > 0 else 0 for s in scores]
    mean = sum(scores) / len(scores) if scores else 0.0

    query_scores = tuple(
        QueryScore(
            query_id=f"q{index}",
            query=f"query {index}",
            k=primary_k,
            retrieved_ids=("doc-a",),
            relevant_ids=("doc-a",),
            hits=hit_counts[index],
            recall_at_k=value,
            precision_at_k=value,
            reciprocal_rank=value,
            ndcg_at_k=value,
        )
        for index, value in enumerate(scores)
    )
    record = RunRecord(
        run_id=run_id,
        golden_set=GoldenSetRef(name="set", version="1", fingerprint=fingerprint),
        query_count=len(scores),
        primary_k=primary_k,
        metrics=(
            MetricSet(
                k=primary_k,
                query_count=len(scores),
                recall_at_k=mean,
                precision_at_k=mean,
                mrr=mean,
                ndcg_at_k=mean,
            ),
        ),
        store=VectorStoreInfo(connector="fake", collection="c", document_count=100),
        started_at=moment,
        finished_at=moment,
        duration_ms=1.0,
        trigger="api",
    )
    return RunDetail(run=record, query_scores=query_scores)


STEADY = [0.9, 0.8, 1.0, 0.7, 0.95, 0.6, 1.0, 0.85, 0.75, 0.9, 0.65, 1.0, 0.8, 0.7, 0.9]


class TestVerdicts:
    def test_identical_runs_are_stable(self) -> None:
        current = make_detail("current", STEADY)
        baseline = [make_detail("older", STEADY)]

        assessment = DriftDetector(FAST).assess(current, baseline)

        assert assessment.verdict is DriftVerdict.STABLE
        assert not assessment.has_drift
        assert assessment.regressions == ()
        assert all(c.difference == 0.0 for c in assessment.comparisons)

    def test_a_large_drop_is_a_regression(self) -> None:
        degraded = [max(0.0, value - 0.3) for value in STEADY]
        assessment = DriftDetector(FAST).assess(
            make_detail("current", degraded), [make_detail("older", STEADY)]
        )

        assert assessment.verdict is DriftVerdict.DEGRADED
        assert assessment.has_drift
        assert len(assessment.regressions) == 4
        for comparison in assessment.comparisons:
            assert comparison.direction == "down"
            assert comparison.significant
            assert comparison.material
            assert comparison.ci_upper < 0

    def test_a_large_rise_is_an_improvement(self) -> None:
        improved = [min(1.0, value + 0.05) for value in STEADY]
        assessment = DriftDetector(FAST).assess(
            make_detail("current", improved), [make_detail("older", STEADY)]
        )

        assert assessment.verdict is DriftVerdict.IMPROVED
        assert not assessment.has_drift
        assert assessment.improvements

    def test_all_four_metrics_are_reported_even_when_stable(self) -> None:
        assessment = DriftDetector(FAST).assess(
            make_detail("current", STEADY), [make_detail("older", STEADY)]
        )
        assert [c.metric for c in assessment.comparisons] == [
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "ndcg_at_k",
        ]


class TestSignificanceVersusMateriality:
    def test_a_tiny_but_consistent_drop_is_significant_yet_immaterial(self) -> None:
        """The reason a monitoring tool needs two thresholds.

        Every query falls by exactly 0.002, so the change is beyond doubt
        statistically -- and completely irrelevant operationally. Alerting on
        this is how a dashboard teaches people to ignore it.
        """
        current = [value - 0.002 for value in STEADY]
        config = DriftConfig(resamples=800, min_queries=10, min_effect=0.01)

        assessment = DriftDetector(config).assess(
            make_detail("current", current), [make_detail("older", STEADY)]
        )

        recall = assessment.comparison_for("recall_at_k")
        assert recall is not None
        assert recall.significant is True
        assert recall.material is False
        assert recall.is_regression is False
        assert assessment.verdict is DriftVerdict.STABLE

    def test_lowering_min_effect_promotes_it_to_a_regression(self) -> None:
        current = [value - 0.002 for value in STEADY]
        config = DriftConfig(resamples=800, min_queries=10, min_effect=0.001)

        assessment = DriftDetector(config).assess(
            make_detail("current", current), [make_detail("older", STEADY)]
        )
        assert assessment.verdict is DriftVerdict.DEGRADED


class TestComparability:
    def test_a_different_golden_set_is_refused(self) -> None:
        assessment = DriftDetector(FAST).assess(
            make_detail("current", STEADY, fingerprint="fp-a"),
            [make_detail("older", [0.1] * 15, fingerprint="fp-b")],
        )

        # Judgements changed, so the earlier numbers measure something else.
        assert assessment.verdict is DriftVerdict.INSUFFICIENT_DATA
        assert any("different golden set" in w for w in assessment.warnings)

    def test_a_different_primary_cutoff_is_refused(self) -> None:
        assessment = DriftDetector(FAST).assess(
            make_detail("current", STEADY, primary_k=5),
            [make_detail("older", STEADY, primary_k=10)],
        )
        assert assessment.verdict is DriftVerdict.INSUFFICIENT_DATA
        assert any("different primary cutoff" in w for w in assessment.warnings)

    def test_no_baseline_at_all(self) -> None:
        assessment = DriftDetector(FAST).assess(make_detail("current", STEADY), [])
        assert assessment.verdict is DriftVerdict.INSUFFICIENT_DATA
        assert "No comparable earlier run" in assessment.summary
        assert assessment.comparisons == ()

    def test_a_run_is_never_its_own_baseline(self) -> None:
        current = make_detail("same-id", STEADY)
        assessment = DriftDetector(FAST).assess(current, [current])
        assert assessment.verdict is DriftVerdict.INSUFFICIENT_DATA

    def test_too_few_queries_refuses_to_guess(self) -> None:
        config = DriftConfig(resamples=800, min_queries=15)
        assessment = DriftDetector(config).assess(
            make_detail("current", [0.5] * 10), [make_detail("older", [0.9] * 10)]
        )

        assert assessment.verdict is DriftVerdict.INSUFFICIENT_DATA
        assert "at least 15" in assessment.summary
        assert assessment.query_count == 10

    def test_a_small_golden_set_earns_a_warning(self) -> None:
        assessment = DriftDetector(FAST).assess(
            make_detail("current", STEADY), [make_detail("older", STEADY)]
        )
        # 15 queries is above min_queries but below the point where the
        # interval's coverage is trustworthy.
        assert any("anti-conservative" in w for w in assessment.warnings)

    def test_queries_present_in_only_one_run_are_dropped(self) -> None:
        current = make_detail("current", [*STEADY, 0.4, 0.4])
        baseline = [make_detail("older", STEADY)]

        assessment = DriftDetector(FAST).assess(current, baseline)
        assert assessment.query_count == len(STEADY)
        assert any("only" in w and "excluded" in w for w in assessment.warnings)


class TestBaselineWindow:
    def test_window_averages_each_query_across_baseline_runs(self) -> None:
        older = make_detail(
            "older", [0.8] * 15, started_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        newer = make_detail(
            "newer", [1.0] * 15, started_at=datetime(2026, 1, 2, tzinfo=UTC)
        )
        current = make_detail("current", [0.9] * 15)

        config = DriftConfig(resamples=800, min_queries=10, baseline_window=2)
        assessment = DriftDetector(config).assess(current, [newer, older])

        recall = assessment.comparison_for("recall_at_k")
        assert recall is not None
        # Baseline is the per-query mean of 1.0 and 0.8.
        assert recall.baseline_value == pytest.approx(0.9)
        assert recall.difference == pytest.approx(0.0)
        assert len(assessment.baseline_run_ids) == 2

    def test_window_size_caps_the_baseline(self) -> None:
        baseline = [make_detail(f"run-{i}", STEADY) for i in range(5)]
        config = DriftConfig(resamples=800, min_queries=10, baseline_window=2)

        assessment = DriftDetector(config).assess(make_detail("current", STEADY), baseline)
        assert assessment.baseline_run_ids == ("run-0", "run-1")


class TestHitRate:
    def test_counts_queries_that_stopped_working(self) -> None:
        baseline_hits = [1] * 15
        current_hits = [0] * 5 + [1] * 10
        assessment = DriftDetector(FAST).assess(
            make_detail("current", [0.0] * 5 + [0.9] * 10, hits=current_hits),
            [make_detail("older", [0.9] * 15, hits=baseline_hits)],
        )

        assert assessment.hit_rate is not None
        assert assessment.hit_rate.became_misses == 5
        assert assessment.hit_rate.became_hits == 0
        assert assessment.hit_rate.baseline_hit_rate == pytest.approx(1.0)
        assert assessment.hit_rate.current_hit_rate == pytest.approx(10 / 15)
        # Five one-way discordant pairs give an exact p of 0.0625, which does
        # not clear alpha even though every change went the same way.
        assert assessment.hit_rate.p_value == pytest.approx(0.0625)
        assert assessment.hit_rate.significant is False

    def test_a_query_must_hit_in_every_baseline_run_to_count_as_a_baseline_hit(
        self,
    ) -> None:
        # The first query was already flickering, so losing it is not a new
        # break and must not be counted as one.
        flaky_old = make_detail("older", [0.9] * 15, hits=[0] + [1] * 14)
        stable_old = make_detail("newer", [0.9] * 15, hits=[1] * 15)
        current = make_detail("current", [0.9] * 15, hits=[0] + [1] * 14)

        config = DriftConfig(resamples=800, min_queries=10, baseline_window=2)
        assessment = DriftDetector(config).assess(current, [stable_old, flaky_old])

        assert assessment.hit_rate is not None
        assert assessment.hit_rate.became_misses == 0


class TestSummary:
    def test_regression_summary_states_the_numbers(self) -> None:
        degraded = [max(0.0, value - 0.3) for value in STEADY]
        assessment = DriftDetector(FAST).assess(
            make_detail("current", degraded), [make_detail("older", STEADY)]
        )

        summary = assessment.summary
        assert "regressed" in summary
        assert "95% CI" in summary
        assert "p=" in summary
        assert "points" in summary

    def test_stable_summary_bounds_what_it_could_be_hiding(self) -> None:
        assessment = DriftDetector(FAST).assess(
            make_detail("current", STEADY), [make_detail("older", STEADY)]
        )
        # "No drift" should read as a measurement, not a shrug.
        assert "No significant change" in assessment.summary
        assert "could be hiding" in assessment.summary


class TestConfigurationIsRecorded:
    def test_the_config_travels_with_the_verdict(self) -> None:
        config = DriftConfig(resamples=800, min_queries=10, confidence_level=0.9)
        assessment = DriftDetector(config).assess(
            make_detail("current", STEADY), [make_detail("older", STEADY)]
        )

        assert assessment.config.confidence_level == 0.9
        assert assessment.config.alpha == pytest.approx(0.1)
        assert assessment.comparisons[0].confidence_level == 0.9

    def test_multiple_comparison_correction_can_be_disabled(self) -> None:
        current = [value - 0.05 for value in STEADY]
        corrected = DriftDetector(
            DriftConfig(resamples=800, min_queries=10, correct_multiple_comparisons=True)
        ).assess(make_detail("current", current), [make_detail("older", STEADY)])
        raw = DriftDetector(
            DriftConfig(
                resamples=800, min_queries=10, correct_multiple_comparisons=False
            )
        ).assess(make_detail("current", current), [make_detail("older", STEADY)])

        assert corrected.comparisons[0].p_value_adjusted >= (
            raw.comparisons[0].p_value_adjusted
        )
        assert raw.comparisons[0].p_value_adjusted == pytest.approx(
            raw.comparisons[0].p_value
        )


class TestBootstrapTargetsTheReportedMetric:
    def test_per_query_means_equal_the_published_aggregates(self) -> None:
        """The bootstrap must resample the quantity the dashboard shows.

        Every metric the API reports is the macro-mean of the per-query
        scores that drift detection resamples. If that identity ever broke,
        the confidence interval would describe a number nobody is looking at.
        """
        connector = FakeConnector(
            {
                "alpha": ["doc-a", "doc-x"],
                "beta": ["doc-x", "doc-b"],
                "gamma": ["doc-x", "doc-y"],
                "delta": ["doc-d"],
            }
        )
        golden_set = make_golden_set(
            {
                "alpha": ["doc-a"],
                "beta": ["doc-b"],
                "gamma": ["doc-c"],
                "delta": [("doc-d", 3)],
            }
        )
        result = ScoringEngine(connector, ScoringConfig((5,), primary_k=5)).evaluate(
            golden_set
        )

        published = result.primary_metrics.as_dict()
        for metric, attribute in PER_QUERY_ATTRIBUTE.items():
            per_query = [
                getattr(score, attribute) for score in result.query_scores
            ]
            assert sum(per_query) / len(per_query) == pytest.approx(published[metric]), (
                f"{metric} is not the macro-mean of its per-query {attribute}"
            )
