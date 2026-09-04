"""Value objects for drift detection.

A verdict is never returned on its own: every assessment carries the numbers
it was derived from -- the interval, the p-value, the sample size, the method
-- because "drift: true" that cannot be argued with is not evidence, it is an
assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.history import GoldenSetRef

Direction = Literal["up", "down", "flat"]


class DriftVerdict(StrEnum):
    """The outcome of comparing a run against its baseline."""

    #: No metric moved by more than sampling noise can explain.
    STABLE = "stable"
    #: At least one metric fell by a statistically significant, material amount.
    DEGRADED = "degraded"
    #: At least one metric rose significantly, and none fell.
    IMPROVED = "improved"
    #: Not enough comparable history, or too few queries, to say anything.
    INSUFFICIENT_DATA = "insufficient_data"


class DriftConfig(BaseModel):
    """Knobs for a drift assessment, recorded alongside every verdict.

    Stored with the result so an old verdict can always be reproduced and
    understood -- a threshold that changed silently would make history
    incomparable in exactly the way this tool exists to prevent.
    """

    model_config = ConfigDict(frozen=True)

    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    resamples: int = Field(default=10_000, ge=100, le=200_000)
    seed: int = Field(
        default=20240517,
        description="Fixed so the same inputs always produce the same verdict.",
    )
    baseline_window: int = Field(
        default=3,
        ge=1,
        le=50,
        description="How many prior comparable runs form the baseline.",
    )
    min_queries: int = Field(
        default=15,
        ge=2,
        description="Below this the bootstrap is too anti-conservative to trust.",
    )
    min_effect: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Smallest change worth alerting on, in absolute metric points.",
    )
    interval_method: Literal["bca", "percentile"] = "bca"
    primary_metric: Literal["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"] = Field(
        default="ndcg_at_k",
        description=(
            "The pre-specified endpoint the verdict is decided on. NDCG is the "
            "default because it responds to both losing a document and merely "
            "ranking it lower."
        ),
    )
    correct_multiple_comparisons: bool = Field(
        default=True,
        description=(
            "Holm-Bonferroni across the *supporting* metrics. The primary "
            "metric is never penalised: it is one pre-specified test."
        ),
    )

    @property
    def alpha(self) -> float:
        """Significance threshold, derived so it can never disagree with the CI."""
        return 1.0 - self.confidence_level


class MetricComparison(BaseModel):
    """One metric, compared between a run and its baseline."""

    model_config = ConfigDict(frozen=True)

    metric: str
    k: int = Field(ge=1)
    baseline_value: float
    current_value: float
    difference: float = Field(description="current - baseline, in metric points.")
    relative_change: float | None = Field(
        default=None, description="Fraction of the baseline; None when baseline is 0."
    )

    ci_lower: float
    ci_upper: float
    confidence_level: float
    standard_error: float

    p_value: float = Field(ge=0.0, le=1.0, description="Two-sided.")
    p_value_degradation: float = Field(
        ge=0.0, le=1.0, description="One-sided, for H1: the metric fell."
    )
    p_value_adjusted: float = Field(
        ge=0.0, le=1.0, description="Two-sided p after multiple-comparison correction."
    )

    sample_size: int = Field(ge=0, description="Queries in the paired comparison.")
    resamples: int
    method: str

    is_primary: bool = Field(
        default=False,
        description="Whether this is the pre-specified metric the verdict rests on.",
    )
    significant: bool = Field(
        description="p below alpha AND the interval excludes zero."
    )
    material: bool = Field(description="|difference| reaches the min_effect threshold.")
    direction: Direction

    @property
    def is_regression(self) -> bool:
        """A drop that is both statistically credible and worth acting on."""
        return self.significant and self.material and self.direction == "down"

    @property
    def is_improvement(self) -> bool:
        return self.significant and self.material and self.direction == "up"


class HitRateComparison(BaseModel):
    """Paired binary outcome: did each query retrieve anything relevant?

    Tested with exact McNemar rather than a two-proportion z-test, because the
    two runs score the same queries and are therefore not independent samples.
    """

    model_config = ConfigDict(frozen=True)

    k: int = Field(ge=1)
    baseline_hit_rate: float = Field(ge=0.0, le=1.0)
    current_hit_rate: float = Field(ge=0.0, le=1.0)
    became_misses: int = Field(
        ge=0, description="Queries that hit in the baseline and miss now."
    )
    became_hits: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    discordant: int = Field(ge=0, description="Queries whose outcome changed at all.")
    p_value: float = Field(ge=0.0, le=1.0)
    p_value_adjusted: float = Field(ge=0.0, le=1.0)
    significant: bool
    test: str = "mcnemar_exact"


class DriftAssessment(BaseModel):
    """The complete, self-explaining result of one drift check."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    baseline_run_ids: tuple[str, ...] = ()
    golden_set: GoldenSetRef
    verdict: DriftVerdict
    summary: str = Field(description="Plain-English statement of what happened.")
    comparisons: tuple[MetricComparison, ...] = ()
    hit_rate: HitRateComparison | None = None
    query_count: int = Field(default=0, ge=0)
    warnings: tuple[str, ...] = ()
    config: DriftConfig = DriftConfig()
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_drift(self) -> bool:
        return self.verdict is DriftVerdict.DEGRADED

    @property
    def regressions(self) -> tuple[MetricComparison, ...]:
        """Metrics that fell significantly and materially, worst first."""
        return tuple(
            sorted(
                (c for c in self.comparisons if c.is_regression),
                key=lambda c: c.difference,
            )
        )

    @property
    def improvements(self) -> tuple[MetricComparison, ...]:
        return tuple(
            sorted(
                (c for c in self.comparisons if c.is_improvement),
                key=lambda c: -c.difference,
            )
        )

    def comparison_for(self, metric: str) -> MetricComparison | None:
        return next((c for c in self.comparisons if c.metric == metric), None)

    @property
    def primary_comparison(self) -> MetricComparison | None:
        """The comparison the verdict was decided on."""
        return next((c for c in self.comparisons if c.is_primary), None)

    @property
    def supporting_regressions(self) -> tuple[MetricComparison, ...]:
        """Non-primary metrics that also fell -- corroboration, not evidence."""
        return tuple(c for c in self.regressions if not c.is_primary)
