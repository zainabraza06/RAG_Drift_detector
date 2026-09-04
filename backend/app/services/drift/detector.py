"""Drift detection: is this run's change from baseline real, or noise?

The detector's whole job is to be honest about uncertainty. It refuses to
compare things that are not comparable, it says when it does not have enough
data, and it separates "statistically credible" from "worth acting on".

Comparability rules, enforced rather than assumed
-------------------------------------------------
1. **Same golden set fingerprint.** Runs scored against different judgements
   are measuring with different rulers; the difference between them is not a
   change in the system.
2. **Same primary cutoff.** Recall@5 and Recall@10 are different quantities.
3. **Aligned per-query scores.** The paired bootstrap requires each query's
   two scores; queries present in only one run are dropped and reported.

One pre-specified primary metric
--------------------------------
The verdict is decided on a single metric chosen in advance (NDCG@k by
default). The other three are reported as supporting context.

This is not laziness about multiplicity -- it is the correct response to it.
The four metrics are deterministic functions of the *same* ranked lists, so
they move together almost perfectly: when a document drops out of the index,
Recall, MRR and NDCG all fall for the same queries, and their p-values come
out near-identical. Treating them as a family of four independent hypotheses
and applying a 4x Holm penalty therefore buys almost no error control while
throwing away most of the power. It is quite capable of turning a real
11-point recall drop, whose confidence interval excludes zero outright, into
a "stable" verdict.

So the decision rests on one pre-specified endpoint tested at full alpha (the
approach a clinical trial takes with its primary outcome), and
Holm-Bonferroni is applied to the *supporting* metrics, where it belongs:
they are described, not used to trigger the alert.

Two thresholds, deliberately separate
-------------------------------------
``significant`` asks whether sampling noise can explain the change.
``material`` asks whether the change is big enough to care about. A monitoring
tool needs both: with a large golden set a 0.2-point drop can be statistically
significant and operationally irrelevant, and reporting that as a regression
trains people to ignore alerts.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.drift import (
    DriftAssessment,
    DriftConfig,
    DriftVerdict,
    HitRateComparison,
    MetricComparison,
)
from app.domain.history import GoldenSetRef, RunDetail
from app.domain.metrics import METRIC_NAMES, QueryScore
from app.services.drift.statistics import (
    BootstrapResult,
    mcnemar_paired_test,
    paired_bootstrap_difference,
)

logger = logging.getLogger(__name__)

#: Metric name -> the per-query attribute it is the mean of.
#: MRR is the odd one out: it aggregates ``reciprocal_rank``.
PER_QUERY_ATTRIBUTE: Mapping[str, str] = {
    "recall_at_k": "recall_at_k",
    "precision_at_k": "precision_at_k",
    "mrr": "reciprocal_rank",
    "ndcg_at_k": "ndcg_at_k",
}

#: Simulated coverage of the nominal 95% interval is close to nominal from
#: about 30 queries and noticeably anti-conservative below ~20, so a golden
#: set smaller than this earns an explicit warning on every verdict.
UNDERPOWERED_QUERY_COUNT = 30

_HUMAN_NAMES: Mapping[str, str] = {
    "recall_at_k": "Recall@{k}",
    "precision_at_k": "Precision@{k}",
    "mrr": "MRR",
    "ndcg_at_k": "NDCG@{k}",
}


def holm_bonferroni(p_values: Sequence[float]) -> tuple[float, ...]:
    """Holm-Bonferroni step-down adjustment.

    Four metrics tested at alpha=0.05 give roughly a 1-in-5 chance of at least
    one false alarm per run; on a dashboard that runs hourly, uncorrected
    testing manufactures drift out of nothing. Holm controls the family-wise
    error rate while being uniformly more powerful than plain Bonferroni.
    """
    count = len(p_values)
    if count == 0:
        return ()

    order = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [0.0] * count
    running_max = 0.0
    for rank, index in enumerate(order):
        scaled = min(1.0, (count - rank) * p_values[index])
        # Step-down adjustments must be monotone in ascending p order.
        running_max = max(running_max, scaled)
        adjusted[index] = running_max
    return tuple(adjusted)


@dataclass(frozen=True, slots=True)
class AlignedScores:
    """Per-query scores from the current run and its baseline, lined up by id.

    Query order is fixed and sorted, so a seeded bootstrap over these arrays
    is fully reproducible across processes.
    """

    query_ids: tuple[str, ...]
    current: Mapping[str, QueryScore]
    baseline: Mapping[str, tuple[QueryScore, ...]]

    def __len__(self) -> int:
        return len(self.query_ids)

    def current_values(self, attribute: str) -> list[float]:
        return [
            float(getattr(self.current[query_id], attribute))
            for query_id in self.query_ids
        ]

    def baseline_values(self, attribute: str) -> list[float]:
        """Each query's baseline value, averaged across the baseline runs.

        Averaging *within* a query keeps the comparison paired: the bootstrap
        still resamples queries, and each drawn query contributes both its
        current score and its own baseline score.
        """
        values: list[float] = []
        for query_id in self.query_ids:
            scores = self.baseline[query_id]
            values.append(
                sum(float(getattr(score, attribute)) for score in scores) / len(scores)
            )
        return values

    def current_hits(self) -> list[bool]:
        return [self.current[query_id].hits > 0 for query_id in self.query_ids]

    def baseline_hits(self) -> list[bool]:
        """A baseline hit means the query hit in *every* baseline run.

        A query that was already flickering in and out was not reliably
        working, so calling it a newly broken query would overstate the change.
        """
        return [
            all(score.hits > 0 for score in self.baseline[query_id])
            for query_id in self.query_ids
        ]


class DriftDetector:
    """Compares one run against a baseline of earlier comparable runs."""

    def __init__(self, config: DriftConfig | None = None) -> None:
        self._config = config or DriftConfig()

    @property
    def config(self) -> DriftConfig:
        return self._config

    def assess(
        self, current: RunDetail, baseline: Sequence[RunDetail]
    ) -> DriftAssessment:
        """Assess ``current`` against ``baseline`` (newest first)."""
        config = self._config
        warnings: list[str] = []
        golden_set = GoldenSetRef(
            name=current.run.golden_set.name,
            version=current.run.golden_set.version,
            fingerprint=current.run.golden_set.fingerprint,
        )

        comparable = self._comparable_baseline(current, baseline, warnings)
        if not comparable:
            return self._insufficient(
                current,
                golden_set,
                warnings,
                "No comparable earlier run to compare against.",
            )

        aligned = self._align(current, comparable, warnings)
        if aligned is None:
            return self._insufficient(
                current,
                golden_set,
                warnings,
                "The runs share no queries, so nothing can be compared.",
                baseline_ids=tuple(run.run.run_id for run in comparable),
            )

        baseline_ids = tuple(run.run.run_id for run in comparable)
        if len(aligned) < config.min_queries:
            return self._insufficient(
                current,
                golden_set,
                warnings,
                f"Only {len(aligned)} comparable queries; at least "
                f"{config.min_queries} are needed for a trustworthy interval.",
                baseline_ids=baseline_ids,
                query_count=len(aligned),
            )
        if len(aligned) < UNDERPOWERED_QUERY_COUNT:
            warnings.append(
                f"Golden set has {len(aligned)} queries; below about "
                f"{UNDERPOWERED_QUERY_COUNT} the bootstrap interval is "
                "anti-conservative, so treat borderline results with caution."
            )

        primary_k = current.run.primary_k
        comparisons = self._compare_metrics(primary_k, aligned)
        hit_rate = self._compare_hit_rate(primary_k, aligned)
        verdict = self._verdict(comparisons)

        logger.info(
            "drift assessment for run %s: %s (%d queries, %d baseline runs)",
            current.run.run_id,
            verdict.value,
            len(aligned),
            len(comparable),
        )
        return DriftAssessment(
            run_id=current.run.run_id,
            baseline_run_ids=baseline_ids,
            golden_set=golden_set,
            verdict=verdict,
            summary=self._summarise(verdict, comparisons, primary_k),
            comparisons=comparisons,
            hit_rate=hit_rate,
            query_count=len(aligned),
            warnings=tuple(warnings),
            config=config,
        )

    # ------------------------------------------------------------------
    # Comparability
    # ------------------------------------------------------------------
    def _comparable_baseline(
        self,
        current: RunDetail,
        baseline: Sequence[RunDetail],
        warnings: list[str],
    ) -> list[RunDetail]:
        fingerprint = current.run.golden_set.fingerprint
        primary_k = current.run.primary_k

        comparable: list[RunDetail] = []
        rejected_fingerprint = rejected_cutoff = 0
        for run in baseline:
            if run.run.run_id == current.run.run_id:
                continue
            if run.run.golden_set.fingerprint != fingerprint:
                rejected_fingerprint += 1
                continue
            if run.run.primary_k != primary_k:
                rejected_cutoff += 1
                continue
            if not run.query_scores:
                continue
            comparable.append(run)
            if len(comparable) >= self._config.baseline_window:
                break

        if rejected_fingerprint:
            warnings.append(
                f"Ignored {rejected_fingerprint} earlier run(s) scored against a "
                "different golden set; the judgements changed, so those numbers "
                "are not comparable."
            )
        if rejected_cutoff:
            warnings.append(
                f"Ignored {rejected_cutoff} earlier run(s) evaluated at a "
                f"different primary cutoff than k={primary_k}."
            )
        return comparable

    @staticmethod
    def _align(
        current: RunDetail,
        baseline: Sequence[RunDetail],
        warnings: list[str],
    ) -> AlignedScores | None:
        """Line up per-query scores by query id across current and baseline."""
        current_by_id = {score.query_id: score for score in current.query_scores}

        shared = set(current_by_id)
        for run in baseline:
            shared &= {score.query_id for score in run.query_scores}
        if not shared:
            return None

        dropped = len(current_by_id) - len(shared)
        if dropped:
            warnings.append(
                f"{dropped} quer{'y' if dropped == 1 else 'ies'} present in only "
                "one of the runs were excluded from the comparison."
            )

        baseline_by_id: dict[str, tuple[QueryScore, ...]] = {
            query_id: tuple(
                score
                for run in baseline
                for score in run.query_scores
                if score.query_id == query_id
            )
            for query_id in shared
        }
        return AlignedScores(
            query_ids=tuple(sorted(shared)),
            current=current_by_id,
            baseline=baseline_by_id,
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------
    def _compare_metrics(
        self, primary_k: int, aligned: AlignedScores
    ) -> tuple[MetricComparison, ...]:
        config = self._config

        bootstrapped: list[tuple[str, BootstrapResult, float, float]] = []
        for metric in METRIC_NAMES:
            attribute = PER_QUERY_ATTRIBUTE[metric]
            current_values = aligned.current_values(attribute)
            baseline_values = aligned.baseline_values(attribute)
            result = paired_bootstrap_difference(
                current_values,
                baseline_values,
                confidence_level=config.confidence_level,
                resamples=config.resamples,
                seed=config.seed,
                method=config.interval_method,
            )
            bootstrapped.append(
                (
                    metric,
                    result,
                    sum(current_values) / len(current_values),
                    sum(baseline_values) / len(baseline_values),
                )
            )

        # The primary metric is one pre-specified test and keeps its raw
        # p-value; Holm is applied across the supporting metrics only.
        supporting = [
            entry for entry in bootstrapped if entry[0] != config.primary_metric
        ]
        supporting_adjusted = (
            holm_bonferroni([result.p_value for _, result, _, _ in supporting])
            if config.correct_multiple_comparisons
            else tuple(result.p_value for _, result, _, _ in supporting)
        )
        adjusted_by_metric = {
            metric: adjusted
            for (metric, _, _, _), adjusted in zip(
                supporting, supporting_adjusted, strict=True
            )
        }

        comparisons: list[MetricComparison] = []
        for metric, result, current_mean, baseline_mean in bootstrapped:
            is_primary = metric == config.primary_metric
            adjusted_p = result.p_value if is_primary else adjusted_by_metric[metric]
            difference = result.observed
            direction = (
                "flat" if difference == 0 else ("up" if difference > 0 else "down")
            )
            comparisons.append(
                MetricComparison(
                    metric=metric,
                    k=primary_k,
                    baseline_value=baseline_mean,
                    current_value=current_mean,
                    difference=difference,
                    relative_change=(
                        difference / baseline_mean if baseline_mean else None
                    ),
                    ci_lower=result.ci_lower,
                    ci_upper=result.ci_upper,
                    confidence_level=result.confidence_level,
                    standard_error=result.standard_error,
                    p_value=result.p_value,
                    p_value_degradation=result.p_value_degradation,
                    p_value_adjusted=adjusted_p,
                    sample_size=result.sample_size,
                    resamples=result.resamples,
                    method=result.method,
                    is_primary=is_primary,
                    # Both conditions, so a verdict can never rest on a p-value
                    # that disagrees with its own confidence interval.
                    significant=adjusted_p < config.alpha and result.excludes_zero,
                    material=abs(difference) >= config.min_effect,
                    direction=direction,
                )
            )
        return tuple(comparisons)

    def _compare_hit_rate(
        self, primary_k: int, aligned: AlignedScores
    ) -> HitRateComparison:
        current_hits = aligned.current_hits()
        baseline_hits = aligned.baseline_hits()
        result = mcnemar_paired_test(current_hits, baseline_hits)
        total = len(aligned)

        return HitRateComparison(
            k=primary_k,
            baseline_hit_rate=sum(baseline_hits) / total,
            current_hit_rate=sum(current_hits) / total,
            became_misses=result.baseline_only,
            became_hits=result.current_only,
            unchanged=result.both + result.neither,
            discordant=result.discordant,
            p_value=result.p_value,
            p_value_adjusted=result.p_value,
            significant=result.p_value < self._config.alpha,
        )

    # ------------------------------------------------------------------
    # Verdict and narration
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(comparisons: Sequence[MetricComparison]) -> DriftVerdict:
        """Decided on the pre-specified primary metric alone."""
        primary = next((c for c in comparisons if c.is_primary), None)
        if primary is None:  # pragma: no cover - always set by _compare_metrics
            return DriftVerdict.STABLE
        if primary.is_regression:
            return DriftVerdict.DEGRADED
        if primary.is_improvement:
            return DriftVerdict.IMPROVED
        return DriftVerdict.STABLE

    @staticmethod
    def _label(metric: str, k: int) -> str:
        return _HUMAN_NAMES.get(metric, metric).format(k=k)

    @classmethod
    def _describe(cls, comparison: MetricComparison) -> str:
        label = cls._label(comparison.metric, comparison.k)
        verb = "fell" if comparison.direction == "down" else "rose"
        return (
            f"{label} {verb} {abs(comparison.difference) * 100:.1f} points "
            f"({comparison.baseline_value:.3f} to {comparison.current_value:.3f}), "
            f"{comparison.confidence_level:.0%} CI "
            f"[{comparison.ci_lower:+.3f}, {comparison.ci_upper:+.3f}], "
            f"p={comparison.p_value_adjusted:.4f}"
        )

    @classmethod
    def _summarise(
        cls,
        verdict: DriftVerdict,
        comparisons: Sequence[MetricComparison],
        primary_k: int,
    ) -> str:
        primary = next((c for c in comparisons if c.is_primary), None)

        if verdict is DriftVerdict.DEGRADED and primary is not None:
            corroborating = [
                cls._label(c.metric, c.k)
                for c in comparisons
                if c.is_regression and not c.is_primary
            ]
            headline = f"Retrieval quality regressed: {cls._describe(primary)}."
            if corroborating:
                return f"{headline} Also down: {', '.join(corroborating)}."
            return headline

        if verdict is DriftVerdict.IMPROVED and primary is not None:
            return f"Retrieval quality improved: {cls._describe(primary)}."

        # Stable: say how tightly, so "no drift" reads as a measurement rather
        # than a shrug. The interval bound is what the test could not rule out.
        if primary is None:
            return "No comparable metrics were available."
        bound = max(abs(primary.ci_lower), abs(primary.ci_upper)) * 100
        return (
            f"No significant change in {cls._label(primary.metric, primary.k)} at "
            f"k={primary_k}. The largest movement the data could be hiding is "
            f"about {bound:.1f} points ({primary.confidence_level:.0%} CI)."
        )

    def _insufficient(
        self,
        current: RunDetail,
        golden_set: GoldenSetRef,
        warnings: Sequence[str],
        reason: str,
        *,
        baseline_ids: tuple[str, ...] = (),
        query_count: int = 0,
    ) -> DriftAssessment:
        return DriftAssessment(
            run_id=current.run.run_id,
            baseline_run_ids=baseline_ids,
            golden_set=golden_set,
            verdict=DriftVerdict.INSUFFICIENT_DATA,
            summary=reason,
            comparisons=(),
            hit_rate=None,
            query_count=query_count,
            warnings=tuple(warnings),
            config=self._config,
        )
