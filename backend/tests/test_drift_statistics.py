"""Tests for the resampling statistics.

This is the module whose correctness the whole "statistically significant
drift detection" claim rests on, so it is tested three ways: against
closed-form answers, against invariants the procedure must satisfy, and
against simulated coverage.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.drift.detector import holm_bonferroni
from app.services.drift.statistics import (
    bootstrap_mean,
    mcnemar_paired_test,
    paired_bootstrap_difference,
)

RESAMPLES = 2000


class TestPointEstimate:
    def test_observed_is_exactly_the_mean_paired_difference(self) -> None:
        current = [0.9, 0.4, 1.0, 0.2]
        baseline = [0.8, 0.6, 1.0, 0.1]
        result = paired_bootstrap_difference(current, baseline, resamples=RESAMPLES)

        expected = sum(c - b for c, b in zip(current, baseline, strict=True)) / 4
        assert result.observed == pytest.approx(expected)
        # Equivalently the difference of the two macro-means, which is the
        # quantity the dashboard reports.
        assert result.observed == pytest.approx(
            sum(current) / 4 - sum(baseline) / 4
        )

    def test_sample_size_is_the_query_count(self) -> None:
        result = paired_bootstrap_difference([1.0] * 7, [0.5] * 7, resamples=RESAMPLES)
        assert result.sample_size == 7
        assert result.resamples == RESAMPLES


class TestPairing:
    def test_identical_runs_give_a_zero_width_interval(self) -> None:
        # Retrieval is deterministic, so an unchanged system must produce a
        # difference of exactly zero with no uncertainty -- the pairing is
        # what makes that true regardless of how varied the queries are.
        scores = [0.1, 0.95, 0.4, 0.0, 1.0, 0.62, 0.33, 0.87, 0.5, 0.2]
        result = paired_bootstrap_difference(scores, scores, resamples=RESAMPLES)

        assert result.observed == 0.0
        assert result.interval == (0.0, 0.0)
        assert result.p_value == pytest.approx(1.0)

    def test_a_uniform_shift_is_recovered_with_no_uncertainty(self) -> None:
        baseline = [0.1, 0.95, 0.4, 0.0, 1.0, 0.62, 0.33, 0.87, 0.5, 0.2]
        current = [value - 0.05 for value in baseline]
        result = paired_bootstrap_difference(current, baseline, resamples=RESAMPLES)

        assert result.observed == pytest.approx(-0.05)
        assert result.ci_lower == pytest.approx(-0.05)
        assert result.ci_upper == pytest.approx(-0.05)
        assert result.excludes_zero

    def test_pairing_cancels_between_query_difficulty(self) -> None:
        """The core claim: pairing removes variance that is not the signal.

        Query difficulty here spans the whole [0, 1] range, dwarfing the
        0.05 shift. Resampling the runs independently would drown the effect;
        the paired interval isolates it.
        """
        rng = np.random.default_rng(11)
        baseline = rng.uniform(0.0, 1.0, 40)
        current = baseline - 0.05

        paired = paired_bootstrap_difference(current, baseline, resamples=8000)
        paired_width = paired.ci_upper - paired.ci_lower

        generator = np.random.default_rng(11)
        unpaired = (
            current[generator.integers(0, 40, (8000, 40))].mean(axis=1)
            - baseline[generator.integers(0, 40, (8000, 40))].mean(axis=1)
        )
        unpaired_width = float(np.percentile(unpaired, 97.5) - np.percentile(unpaired, 2.5))

        assert paired_width < unpaired_width / 10
        assert paired.excludes_zero


class TestIntervalAndPValueAgree:
    def test_a_clear_regression_is_significant_both_ways(self) -> None:
        rng = np.random.default_rng(3)
        baseline = rng.uniform(0.4, 1.0, 40)
        current = baseline - rng.uniform(0.05, 0.25, 40)
        result = paired_bootstrap_difference(current, baseline, resamples=8000)

        assert result.observed < 0
        assert result.excludes_zero
        assert result.ci_upper < 0
        assert result.p_value < 0.05
        # The one-sided degradation p-value is never larger than the two-sided
        # one. Here the effect is strong enough that both bottom out at the
        # Monte Carlo floor of 1/(R+1), so the bound is not strict.
        assert result.p_value_degradation <= result.p_value
        assert result.p_value == pytest.approx(1 / 8001)

    def test_one_sided_is_sharper_for_a_borderline_effect(self) -> None:
        rng = np.random.default_rng(17)
        baseline = rng.uniform(0.4, 1.0, 40)
        current = baseline + rng.normal(-0.03, 0.09, 40)
        result = paired_bootstrap_difference(current, baseline, resamples=8000)

        assert result.observed < 0
        assert result.p_value_degradation < result.p_value

    def test_pure_noise_is_not_significant(self) -> None:
        rng = np.random.default_rng(5)
        baseline = rng.uniform(0.3, 0.9, 40)
        current = baseline + rng.normal(0, 0.02, 40)
        result = paired_bootstrap_difference(current, baseline, resamples=8000)

        assert not result.excludes_zero
        assert result.p_value > 0.05

    def test_p_value_is_never_zero(self) -> None:
        # The (1 + #extreme)/(R + 1) form: R resamples cannot rule out a rarer
        # event, so reporting p = 0 would overstate the evidence.
        baseline = [0.9] * 30
        current = [0.1] * 30
        result = paired_bootstrap_difference(current, baseline, resamples=1000)

        assert result.p_value > 0
        assert result.p_value == pytest.approx(1 / 1001)

    def test_direction_of_the_one_sided_p_value(self) -> None:
        baseline = [0.5] * 30
        improved = [0.8] * 30
        result = paired_bootstrap_difference(improved, baseline, resamples=1000)

        # An improvement gives essentially no evidence of degradation.
        assert result.observed > 0
        assert result.p_value_degradation > 0.9


class TestReproducibility:
    def test_the_same_seed_gives_the_same_verdict(self) -> None:
        rng = np.random.default_rng(1)
        baseline = rng.uniform(0, 1, 30)
        current = baseline - 0.04

        first = paired_bootstrap_difference(
            current, baseline, resamples=RESAMPLES, seed=99
        )
        second = paired_bootstrap_difference(
            current, baseline, resamples=RESAMPLES, seed=99
        )
        assert first == second

    def test_a_different_seed_moves_the_interval_only_slightly(self) -> None:
        rng = np.random.default_rng(2)
        baseline = rng.uniform(0, 1, 60)
        current = baseline - rng.normal(0.05, 0.05, 60)

        first = paired_bootstrap_difference(current, baseline, resamples=8000, seed=1)
        second = paired_bootstrap_difference(current, baseline, resamples=8000, seed=2)
        assert first.observed == pytest.approx(second.observed)
        assert first.ci_lower == pytest.approx(second.ci_lower, abs=0.01)


class TestIntervalMethods:
    def test_bca_and_percentile_agree_on_symmetric_data(self) -> None:
        rng = np.random.default_rng(8)
        baseline = rng.uniform(0.3, 0.7, 80)
        current = baseline + rng.normal(-0.05, 0.05, 80)

        bca = paired_bootstrap_difference(current, baseline, resamples=8000, method="bca")
        percentile = paired_bootstrap_difference(
            current, baseline, resamples=8000, method="percentile"
        )
        assert bca.method == "bca"
        assert percentile.method == "percentile"
        assert bca.ci_lower == pytest.approx(percentile.ci_lower, abs=0.02)

    def test_bca_falls_back_when_the_correction_is_undefined(self) -> None:
        # Every query moved by exactly the same amount, so the bootstrap
        # distribution is a point mass and BCa has nothing to correct.
        result = paired_bootstrap_difference(
            [0.5] * 20, [0.6] * 20, resamples=RESAMPLES, method="bca"
        )
        assert result.method == "percentile"
        assert result.interval == pytest.approx((-0.1, -0.1))

    def test_confidence_level_widens_the_interval(self) -> None:
        rng = np.random.default_rng(4)
        baseline = rng.uniform(0, 1, 50)
        current = baseline + rng.normal(0, 0.1, 50)

        narrow = paired_bootstrap_difference(
            current, baseline, resamples=8000, confidence_level=0.80
        )
        wide = paired_bootstrap_difference(
            current, baseline, resamples=8000, confidence_level=0.99
        )
        assert (wide.ci_upper - wide.ci_lower) > (narrow.ci_upper - narrow.ci_lower)


class TestCoverage:
    def test_the_interval_covers_at_roughly_its_stated_rate(self) -> None:
        """The claim "95% confidence interval" has to be earned by simulation.

        Under the null, a nominal 95% interval should contain the true effect
        (zero) about 95% of the time. The bootstrap is asymptotically correct
        and mildly anti-conservative in small samples, so the assertion is a
        band rather than a point -- see docs for the measured n-sweep.
        """
        rng = np.random.default_rng(21)
        trials, covered = 200, 0
        for trial in range(trials):
            difficulty = rng.beta(5, 2, 40)
            noise = rng.normal(0, 0.08, 40)
            result = paired_bootstrap_difference(
                difficulty + noise, difficulty, resamples=800, seed=trial
            )
            covered += result.ci_lower <= 0.0 <= result.ci_upper

        coverage = covered / trials
        assert 0.88 <= coverage <= 0.99, f"coverage was {coverage:.3f}"


class TestValidation:
    def test_unequal_lengths_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="equal-length"):
            paired_bootstrap_difference([0.1, 0.2], [0.1])

    def test_a_single_observation_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 2 paired"):
            paired_bootstrap_difference([0.1], [0.2])

    def test_non_finite_scores_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            paired_bootstrap_difference([0.1, math.nan], [0.1, 0.2])

    def test_invalid_confidence_level(self) -> None:
        with pytest.raises(ValueError, match="confidence_level"):
            paired_bootstrap_difference([0.1, 0.2], [0.3, 0.4], confidence_level=1.5)

    def test_too_few_resamples(self) -> None:
        with pytest.raises(ValueError, match="resamples must be >= 100"):
            paired_bootstrap_difference([0.1, 0.2], [0.3, 0.4], resamples=10)


class TestBootstrapMean:
    def test_interval_brackets_the_sample_mean(self) -> None:
        rng = np.random.default_rng(6)
        values = rng.uniform(0.2, 0.9, 50)
        result = bootstrap_mean(values, resamples=8000)

        assert result.observed == pytest.approx(float(values.mean()))
        assert result.ci_lower < result.observed < result.ci_upper


class TestMcNemar:
    def test_no_discordant_pairs_is_no_evidence(self) -> None:
        result = mcnemar_paired_test([True, False, True], [True, False, True])
        assert result.discordant == 0
        assert result.p_value == 1.0
        assert result.both == 2
        assert result.neither == 1

    def test_counts_the_2x2_table_correctly(self) -> None:
        #                     current:  T      F      T      F
        current = [True, False, True, False]
        baseline = [True, True, False, False]
        result = mcnemar_paired_test(current, baseline)

        assert result.both == 1  # index 0
        assert result.baseline_only == 1  # index 1: was a hit, now a miss
        assert result.current_only == 1  # index 2: was a miss, now a hit
        assert result.neither == 1  # index 3
        assert result.discordant == 2

    def test_five_one_way_discordant_pairs_cannot_reach_significance(self) -> None:
        # 2 * 0.5^5 = 0.0625: the smallest two-sided exact p available with
        # five discordant pairs. Worth pinning, because it is exactly the case
        # where a chi-squared approximation would wrongly claim significance.
        baseline = [True] * 5 + [True] * 10
        current = [False] * 5 + [True] * 10
        result = mcnemar_paired_test(current, baseline)

        assert result.discordant == 5
        assert result.baseline_only == 5
        assert result.p_value == pytest.approx(0.0625)
        assert result.p_value > 0.05

    def test_ten_one_way_discordant_pairs_are_significant(self) -> None:
        baseline = [True] * 10 + [True] * 20
        current = [False] * 10 + [True] * 20
        result = mcnemar_paired_test(current, baseline)

        assert result.p_value == pytest.approx(2 * 0.5**10)
        assert result.p_value < 0.05

    def test_balanced_discordance_is_not_evidence_of_change(self) -> None:
        baseline = [True] * 5 + [False] * 5
        current = [False] * 5 + [True] * 5
        result = mcnemar_paired_test(current, baseline)

        assert result.baseline_only == 5
        assert result.current_only == 5
        assert result.p_value == pytest.approx(1.0)

    def test_length_mismatch_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="equal-length"):
            mcnemar_paired_test([True], [True, False])


class TestHolmBonferroni:
    def test_smallest_p_is_multiplied_by_the_family_size(self) -> None:
        adjusted = holm_bonferroni([0.01, 0.04, 0.03, 0.20])
        assert adjusted[0] == pytest.approx(0.04)  # 0.01 * 4

    def test_adjustment_is_monotone_in_ascending_p_order(self) -> None:
        p_values = [0.001, 0.008, 0.039, 0.041, 0.9]
        adjusted = holm_bonferroni(p_values)
        by_rank = [adjusted[i] for i in sorted(range(5), key=lambda i: p_values[i])]
        assert by_rank == sorted(by_rank)

    def test_adjusted_values_never_exceed_one(self) -> None:
        assert all(value <= 1.0 for value in holm_bonferroni([0.5, 0.6, 0.9]))

    def test_is_less_conservative_than_bonferroni(self) -> None:
        p_values = [0.01, 0.02, 0.03, 0.04]
        holm = holm_bonferroni(p_values)
        bonferroni = [min(1.0, p * len(p_values)) for p in p_values]
        assert all(h <= b for h, b in zip(holm, bonferroni, strict=True))
        assert holm[-1] < bonferroni[-1]

    def test_empty_input(self) -> None:
        assert holm_bonferroni([]) == ()

    def test_single_test_is_unadjusted(self) -> None:
        assert holm_bonferroni([0.03]) == pytest.approx((0.03,))
