"""Tests for the scoring engine's orchestration behaviour."""

from __future__ import annotations

import pytest

from app.core.errors import EvaluationError
from app.domain.golden_set import GoldenSet
from app.services.scoring.engine import ScoringConfig, ScoringEngine
from tests.conftest import FakeConnector, make_golden_set


class TestScoringConfig:
    def test_cutoffs_are_deduplicated_and_sorted(self) -> None:
        config = ScoringConfig(k_values=(10, 3, 3, 1), primary_k=3)
        assert config.cutoffs == (1, 3, 10)
        assert config.retrieval_depth == 10

    def test_primary_k_must_be_an_evaluated_cutoff(self) -> None:
        with pytest.raises(ValueError, match="must be one of k_values"):
            ScoringConfig(k_values=(1, 5), primary_k=3)

    def test_k_values_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            ScoringConfig(k_values=(0, 5), primary_k=5)

    def test_at_least_one_cutoff_is_required(self) -> None:
        with pytest.raises(ValueError, match="at least one k value"):
            ScoringConfig(k_values=(), primary_k=5)


class TestEvaluate:
    def test_perfect_retrieval_scores_one_across_the_board(
        self, perfect_connector: FakeConnector, perfect_golden_set: GoldenSet
    ) -> None:
        engine = ScoringEngine(perfect_connector, ScoringConfig((1, 3), primary_k=1))
        result = engine.evaluate(perfect_golden_set)

        headline = result.primary_metrics
        assert headline.recall_at_k == pytest.approx(1.0)
        assert headline.precision_at_k == pytest.approx(1.0)
        assert headline.mrr == pytest.approx(1.0)
        assert headline.ndcg_at_k == pytest.approx(1.0)
        assert result.query_count == 3
        assert not result.missed_queries

    def test_one_retrieval_per_query_serves_every_cutoff(
        self, perfect_connector: FakeConnector, perfect_golden_set: GoldenSet
    ) -> None:
        engine = ScoringEngine(
            perfect_connector, ScoringConfig((1, 3, 5, 10), primary_k=5)
        )
        engine.evaluate(perfect_golden_set)

        # Three queries, one search each, all issued at the deepest cutoff.
        assert len(perfect_connector.search_calls) == 3
        assert {depth for _, depth in perfect_connector.search_calls} == {10}

    def test_metrics_are_produced_for_every_configured_cutoff(
        self, perfect_connector: FakeConnector, perfect_golden_set: GoldenSet
    ) -> None:
        engine = ScoringEngine(
            perfect_connector, ScoringConfig((1, 3, 10), primary_k=3)
        )
        result = engine.evaluate(perfect_golden_set)
        assert result.evaluated_k_values == (1, 3, 10)
        assert result.metrics_at(10).k == 10
        with pytest.raises(KeyError, match="no metrics at k=5"):
            result.metrics_at(5)

    def test_degraded_retrieval_lowers_the_headline_metrics(self) -> None:
        connector = FakeConnector(
            {
                "alpha": ["noise-1", "doc-a"],  # demoted to rank 2
                "beta": ["noise-1", "noise-2"],  # complete miss
                "gamma": ["doc-c"],  # still perfect
            }
        )
        golden_set = make_golden_set(
            {"alpha": ["doc-a"], "beta": ["doc-b"], "gamma": ["doc-c"]}
        )
        result = ScoringEngine(connector, ScoringConfig((5,), primary_k=5)).evaluate(
            golden_set
        )

        headline = result.primary_metrics
        assert headline.recall_at_k == pytest.approx(2 / 3)
        # MRR: 1/2 for alpha, 0 for beta, 1 for gamma.
        assert headline.mrr == pytest.approx((0.5 + 0.0 + 1.0) / 3)
        assert [score.query_id for score in result.missed_queries] == ["q2"]

    def test_per_query_detail_is_retained_at_the_primary_cutoff_only(
        self, perfect_connector: FakeConnector, perfect_golden_set: GoldenSet
    ) -> None:
        engine = ScoringEngine(
            perfect_connector, ScoringConfig((1, 3, 5), primary_k=3)
        )
        result = engine.evaluate(perfect_golden_set)
        assert len(result.query_scores) == 3
        assert {score.k for score in result.query_scores} == {3}

    def test_run_records_the_golden_set_fingerprint_and_store_snapshot(
        self, perfect_connector: FakeConnector, perfect_golden_set: GoldenSet
    ) -> None:
        result = ScoringEngine(perfect_connector).evaluate(perfect_golden_set)
        assert result.golden_set_fingerprint == perfect_golden_set.fingerprint
        assert result.store.document_count == 100
        assert result.store.embedding_model == "fake-embedder-v1"
        assert result.duration_ms >= 0


class TestFailureHandling:
    def test_a_failing_query_aborts_the_run_by_default(self) -> None:
        connector = FakeConnector(
            {"alpha": ["doc-a"], "beta": ["doc-b"]},
            failing_queries=frozenset({"beta"}),
        )
        golden_set = make_golden_set({"alpha": ["doc-a"], "beta": ["doc-b"]})
        with pytest.raises(EvaluationError, match="retrieval failed for query 'q2'"):
            ScoringEngine(connector).evaluate(golden_set)

    def test_failures_can_be_tolerated_and_scored_as_misses(self) -> None:
        connector = FakeConnector(
            {"alpha": ["doc-a"], "beta": ["doc-b"]},
            failing_queries=frozenset({"beta"}),
        )
        golden_set = make_golden_set({"alpha": ["doc-a"], "beta": ["doc-b"]})
        engine = ScoringEngine(
            connector,
            ScoringConfig((5,), primary_k=5, tolerate_query_failures=True),
        )
        result = engine.evaluate(golden_set)

        assert result.primary_metrics.recall_at_k == pytest.approx(0.5)
        assert [score.query_id for score in result.missed_queries] == ["q2"]


class TestGradedRelevance:
    def test_ndcg_reflects_ranking_of_graded_judgements(self) -> None:
        golden_set = make_golden_set(
            {"alpha": [("doc-best", 3), ("doc-ok", 1)]}
        )
        good = FakeConnector({"alpha": ["doc-best", "doc-ok"]})
        bad = FakeConnector({"alpha": ["doc-ok", "doc-best"]})

        config = ScoringConfig((5,), primary_k=5)
        good_result = ScoringEngine(good, config).evaluate(golden_set)
        bad_result = ScoringEngine(bad, config).evaluate(golden_set)

        # Recall is blind to ordering; NDCG is not. That difference is exactly
        # the kind of silent degradation this tool exists to catch.
        assert good_result.primary_metrics.recall_at_k == pytest.approx(1.0)
        assert bad_result.primary_metrics.recall_at_k == pytest.approx(1.0)
        assert good_result.primary_metrics.ndcg_at_k == pytest.approx(1.0)
        assert bad_result.primary_metrics.ndcg_at_k < 0.85
