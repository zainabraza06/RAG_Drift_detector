"""Tests for the IR metric primitives.

These are the numbers every other stage is built on, so the suite pins down
exact hand-computed values rather than only checking bounds and monotonicity.
"""

from __future__ import annotations

import math

import pytest

from app.domain.metrics import MetricSet, QueryScore
from app.services.scoring.metrics import (
    aggregate_scores,
    dcg,
    first_relevant_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RANKED = ["d1", "d2", "d3", "d4", "d5"]


# ----------------------------------------------------------------------
# Recall@k
# ----------------------------------------------------------------------
class TestRecallAtK:
    def test_all_relevant_documents_found(self) -> None:
        assert recall_at_k(RANKED, {"d1", "d3"}, k=5) == 1.0

    def test_partial_recall_is_fraction_of_relevant_set(self) -> None:
        # 2 of 4 relevant documents fall inside the top 5.
        assert recall_at_k(RANKED, {"d1", "d3", "d9", "d10"}, k=5) == 0.5

    def test_cutoff_excludes_documents_below_k(self) -> None:
        assert recall_at_k(RANKED, {"d5"}, k=3) == 0.0
        assert recall_at_k(RANKED, {"d5"}, k=5) == 1.0

    def test_no_relevant_documents_is_zero_not_an_error(self) -> None:
        assert recall_at_k(RANKED, set(), k=5) == 0.0

    def test_empty_result_list(self) -> None:
        assert recall_at_k([], {"d1"}, k=5) == 0.0

    def test_recall_is_monotonic_in_k(self) -> None:
        relevant = {"d1", "d4"}
        values = [recall_at_k(RANKED, relevant, k) for k in range(1, 6)]
        assert values == sorted(values)


# ----------------------------------------------------------------------
# Precision@k
# ----------------------------------------------------------------------
class TestPrecisionAtK:
    def test_full_precision(self) -> None:
        assert precision_at_k(RANKED, set(RANKED), k=5) == 1.0

    def test_textbook_case_with_a_full_result_list(self) -> None:
        # 2 hits out of 5 returned.
        assert precision_at_k(RANKED, {"d1", "d2"}, k=5) == pytest.approx(0.4)

    def test_denominator_clamps_to_documents_actually_returned(self) -> None:
        # Only two documents exist; one is relevant. Dividing by k=5 would
        # report 0.2 and punish a small corpus, so we report 1/2.
        assert precision_at_k(["d1", "d2"], {"d1"}, k=5) == pytest.approx(0.5)

    def test_empty_result_list(self) -> None:
        assert precision_at_k([], {"d1"}, k=5) == 0.0

    def test_k_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            precision_at_k(RANKED, {"d1"}, k=0)


# ----------------------------------------------------------------------
# Reciprocal rank
# ----------------------------------------------------------------------
class TestReciprocalRank:
    @pytest.mark.parametrize(
        ("relevant", "expected"),
        [
            ({"d1"}, 1.0),
            ({"d2"}, 0.5),
            ({"d3"}, 1 / 3),
            ({"d4"}, 0.25),
            ({"d5"}, 0.2),
        ],
    )
    def test_reciprocal_of_first_hit_rank(
        self, relevant: set[str], expected: float
    ) -> None:
        assert reciprocal_rank(RANKED, relevant, k=5) == pytest.approx(expected)

    def test_only_the_first_hit_counts(self) -> None:
        assert reciprocal_rank(RANKED, {"d2", "d3", "d4"}, k=5) == pytest.approx(0.5)

    def test_miss_scores_zero(self) -> None:
        assert reciprocal_rank(RANKED, {"d9"}, k=5) == 0.0

    def test_hit_below_the_cutoff_does_not_count(self) -> None:
        assert reciprocal_rank(RANKED, {"d4"}, k=3) == 0.0

    def test_first_relevant_rank_reports_none_on_a_miss(self) -> None:
        assert first_relevant_rank(RANKED, {"d3"}, k=5) == 3
        assert first_relevant_rank(RANKED, {"d9"}, k=5) is None


# ----------------------------------------------------------------------
# NDCG@k
# ----------------------------------------------------------------------
class TestNdcgAtK:
    def test_dcg_uses_log2_rank_plus_one_discount(self) -> None:
        assert dcg([3.0]) == pytest.approx(3.0)  # log2(2) == 1
        assert dcg([1.0, 1.0]) == pytest.approx(1.0 + 1 / math.log2(3))

    def test_perfect_binary_ranking_is_one(self) -> None:
        assert ndcg_at_k(RANKED, {"d1": 1, "d2": 1}, k=5) == pytest.approx(1.0)

    def test_hand_computed_graded_value(self) -> None:
        # Retrieved d1 (grade 1) then d2 (grade 3).
        #   DCG  = (2^1-1)/log2(2) + (2^3-1)/log2(3) = 1 + 7/1.58496 = 5.41627
        #   IDCG = (2^3-1)/log2(2) + (2^1-1)/log2(3) = 7 + 0.63093   = 7.63093
        expected = (1 + 7 / math.log2(3)) / (7 + 1 / math.log2(3))
        assert ndcg_at_k(["d1", "d2"], {"d1": 1, "d2": 3}, k=5) == pytest.approx(
            expected
        )
        assert expected == pytest.approx(0.70981, abs=1e-5)

    def test_ordering_matters(self) -> None:
        relevance = {"d1": 3, "d2": 1}
        good = ndcg_at_k(["d1", "d2"], relevance, k=5)
        bad = ndcg_at_k(["d2", "d1"], relevance, k=5)
        assert good == pytest.approx(1.0)
        assert bad < good

    def test_unjudged_documents_contribute_zero_gain(self) -> None:
        with_noise = ndcg_at_k(["d9", "d1"], {"d1": 1}, k=5)
        assert with_noise == pytest.approx(1 / math.log2(3))

    def test_no_positive_judgements_is_zero(self) -> None:
        assert ndcg_at_k(RANKED, {"d1": 0}, k=5) == 0.0
        assert ndcg_at_k(RANKED, {}, k=5) == 0.0

    def test_ideal_ranking_is_truncated_at_k(self) -> None:
        # Three relevant documents but only room for two: retrieving the best
        # two in order must still score a perfect 1.0.
        relevance = {"d1": 3, "d2": 3, "d3": 3}
        assert ndcg_at_k(["d1", "d2"], relevance, k=2) == pytest.approx(1.0)

    def test_result_never_exceeds_one(self) -> None:
        assert ndcg_at_k(RANKED, {doc: 3 for doc in RANKED}, k=5) <= 1.0


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------
def _score(query_id: str, k: int = 5, **values: float) -> QueryScore:
    defaults: dict[str, float] = {
        "recall_at_k": 0.0,
        "precision_at_k": 0.0,
        "reciprocal_rank": 0.0,
        "ndcg_at_k": 0.0,
    }
    defaults.update(values)
    return QueryScore(
        query_id=query_id,
        query=query_id,
        k=k,
        retrieved_ids=(),
        relevant_ids=(),
        hits=0,
        **defaults,  # type: ignore[arg-type]
    )


class TestAggregateScores:
    def test_macro_average_weights_every_query_equally(self) -> None:
        scores = [
            _score("a", recall_at_k=1.0, ndcg_at_k=1.0),
            _score("b", recall_at_k=0.0, ndcg_at_k=0.0),
            _score("c", recall_at_k=0.5, ndcg_at_k=0.5),
        ]
        aggregated = aggregate_scores(scores, k=5)
        assert aggregated.recall_at_k == pytest.approx(0.5)
        assert aggregated.ndcg_at_k == pytest.approx(0.5)
        assert aggregated.query_count == 3
        assert aggregated.k == 5

    def test_reciprocal_rank_aggregates_into_mrr(self) -> None:
        scores = [_score("a", reciprocal_rank=1.0), _score("b", reciprocal_rank=0.5)]
        assert aggregate_scores(scores, k=5).mrr == pytest.approx(0.75)

    def test_empty_input_yields_zeroed_metrics(self) -> None:
        aggregated = aggregate_scores([], k=3)
        assert aggregated == MetricSet(
            k=3,
            query_count=0,
            recall_at_k=0.0,
            precision_at_k=0.0,
            mrr=0.0,
            ndcg_at_k=0.0,
        )

    def test_mixing_cutoffs_is_rejected(self) -> None:
        scores = [_score("a", k=5), _score("b", k=10)]
        with pytest.raises(ValueError, match="another cutoff"):
            aggregate_scores(scores, k=5)
