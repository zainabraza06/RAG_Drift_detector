"""Resampling statistics for drift detection.

Pure functions over arrays of per-query scores. No database, no domain types,
no configuration -- so every claim this module makes can be checked against a
textbook and against simulation.

Why a *paired* bootstrap
------------------------
Two runs being compared are scored against the **same golden set** (the drift
detector refuses to compare across fingerprints). Query *i* therefore appears
in both runs, and the runs are not independent samples: a query that is
intrinsically hard drags both runs down together.

Resampling the two runs independently would ignore that pairing and inflate
the variance of the difference, because it would carry the between-query
variance -- which is usually far larger than the run-to-run change we are
trying to detect -- into the estimate twice. The correct procedure resamples
**query indices**, and for each drawn index takes *both* runs' scores for that
query. Between-query difficulty then cancels inside each difference, and what
remains is the quantity of interest.

Concretely, for per-query scores ``b`` (baseline) and ``c`` (current):

    d_i  = c_i - b_i                        per-query paired difference
    θ̂    = mean(d)                           the observed change
    θ*_r = mean(d[I_r]),  I_r ~ Uniform{1..n} with replacement, |I_r| = n

The distribution of ``θ*`` is what the confidence interval is read off.

Confidence interval vs p-value
------------------------------
These come from two *different* resample sets, and conflating them is the most
common way to get bootstrap inference subtly wrong:

* The **interval** is read off the uncentred resamples ``θ*``, whose
  distribution is centred near ``θ̂``. It answers "how precisely do we know the
  change?"
* The **p-value** requires a distribution generated under the null hypothesis
  ``H₀: E[d] = 0``. The uncentred distribution is not that, so the differences
  are re-centred (``d_i - θ̂``) before resampling, and the observed ``θ̂`` is
  compared against the resulting null distribution. The Monte Carlo estimate
  uses the ``(1 + #extreme) / (R + 1)`` form, which is the standard unbiased
  form and cannot report the impossible ``p = 0``.

What the interval does and does not cover
-----------------------------------------
The bootstrap resamples **queries**, so the interval quantifies uncertainty
arising from *which queries happen to be in the golden set*. It treats the
retrieval system as fixed. It does **not** capture uncertainty from a
non-deterministic index, from embedding non-determinism, or from the golden
set being an unrepresentative sample of real user queries -- the inference is
about the population of queries the golden set can be regarded as a sample
from, and no wider.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.stats import binomtest, norm

#: Every internal array is 1-D float64; naming it once keeps the signatures
#: readable under mypy --strict.
FloatArray = NDArray[np.float64]

__all__ = [
    "BootstrapResult",
    "McNemarResult",
    "bootstrap_mean",
    "mcnemar_paired_test",
    "paired_bootstrap_difference",
]

IntervalMethod = Literal["bca", "percentile"]

DEFAULT_RESAMPLES = 10_000
DEFAULT_CONFIDENCE = 0.95
#: Fixed by default so a monitoring tool gives the same verdict for the same
#: inputs. Reproducibility matters more here than a fresh random stream.
DEFAULT_SEED = 20240517


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """The outcome of a bootstrap over per-query scores.

    ``p_value`` is two-sided (``H₁: Δ ≠ 0``). ``p_value_degradation`` is the
    one-sided p-value for ``H₁: Δ < 0`` -- the only direction a monitoring
    tool actually alerts on.
    """

    observed: float
    ci_lower: float
    ci_upper: float
    confidence_level: float
    p_value: float
    p_value_degradation: float
    standard_error: float
    sample_size: int
    resamples: int
    method: IntervalMethod

    @property
    def excludes_zero(self) -> bool:
        """Whether the whole interval sits on one side of zero."""
        return self.ci_upper < 0.0 or self.ci_lower > 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return (self.ci_lower, self.ci_upper)


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """Exact McNemar test on paired binary outcomes."""

    baseline_only: int
    current_only: int
    both: int
    neither: int
    p_value: float
    sample_size: int

    @property
    def discordant(self) -> int:
        """Queries whose outcome changed -- the only ones the test uses."""
        return self.baseline_only + self.current_only


def _validate_pair(
    current: Sequence[float] | FloatArray, baseline: Sequence[float] | FloatArray
) -> tuple[FloatArray, FloatArray]:
    current_array = np.asarray(current, dtype=np.float64)
    baseline_array = np.asarray(baseline, dtype=np.float64)

    if current_array.ndim != 1 or baseline_array.ndim != 1:
        raise ValueError("per-query scores must be one-dimensional")
    if current_array.size != baseline_array.size:
        raise ValueError(
            "paired comparison needs equal-length inputs, got "
            f"{current_array.size} current and {baseline_array.size} baseline"
        )
    if current_array.size < 2:
        raise ValueError("a bootstrap needs at least 2 paired observations")
    if not np.all(np.isfinite(current_array)) or not np.all(np.isfinite(baseline_array)):
        raise ValueError("per-query scores must all be finite")
    return current_array, baseline_array


def _percentile_interval(
    resample_means: FloatArray, confidence_level: float
) -> tuple[float, float]:
    alpha = 1.0 - confidence_level
    lower, upper = np.percentile(
        resample_means, [100 * (alpha / 2), 100 * (1 - alpha / 2)]
    )
    return float(lower), float(upper)


def _bca_interval(
    values: FloatArray,
    resample_means: FloatArray,
    observed: float,
    confidence_level: float,
) -> tuple[float, float] | None:
    """Bias-corrected and accelerated interval, or ``None`` if undefined.

    The plain percentile interval is only correct when the bootstrap
    distribution is unbiased and symmetric. BCa corrects for both median bias
    (``z0``) and for the estimator's variance changing with its value
    (``a``, from a jackknife), which matters here because metrics are bounded
    in [0, 1] and pile up against those bounds.
    """
    proportion_below = float(np.mean(resample_means < observed))
    # Φ⁻¹ is infinite at 0 and 1; that happens when the bootstrap distribution
    # is degenerate, and BCa has nothing to correct.
    if proportion_below <= 0.0 or proportion_below >= 1.0:
        return None
    bias_correction = float(norm.ppf(proportion_below))

    # Leave-one-out jackknife means, computed in closed form.
    n = values.size
    total = values.sum()
    jackknife_means = (total - values) / (n - 1)
    centred = jackknife_means.mean() - jackknife_means

    numerator = float(np.sum(centred**3))
    denominator = 6.0 * float(np.sum(centred**2)) ** 1.5
    if denominator == 0.0:
        return None
    acceleration = numerator / denominator

    alpha = 1.0 - confidence_level
    z_alpha = norm.ppf([alpha / 2, 1 - alpha / 2])
    adjusted = bias_correction + (bias_correction + z_alpha) / (
        1 - acceleration * (bias_correction + z_alpha)
    )
    percentiles = norm.cdf(adjusted) * 100.0
    if not np.all(np.isfinite(percentiles)):
        return None

    lower, upper = np.percentile(resample_means, percentiles)
    return float(lower), float(upper)


def _monte_carlo_p_values(
    differences: FloatArray,
    observed: float,
    generator: np.random.Generator,
    resamples: int,
) -> tuple[float, float]:
    """Two-sided and degradation-direction p-values under ``H₀: E[d] = 0``.

    The differences are re-centred before resampling so the resulting
    distribution actually satisfies the null hypothesis; testing against the
    uncentred distribution would be testing the wrong thing.
    """
    n = differences.size
    centred = differences - observed
    indices = generator.integers(0, n, size=(resamples, n))
    null_means = centred[indices].mean(axis=1)

    # The (1 + #extreme) / (R + 1) form: an unbiased Monte Carlo p-value that
    # never reports 0, since R resamples cannot rule out a rarer event.
    two_sided = (1 + int(np.sum(np.abs(null_means) >= abs(observed)))) / (resamples + 1)
    degradation = (1 + int(np.sum(null_means <= observed))) / (resamples + 1)
    return min(1.0, two_sided), min(1.0, degradation)


def paired_bootstrap_difference(
    current: Sequence[float] | FloatArray,
    baseline: Sequence[float] | FloatArray,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    method: IntervalMethod = "bca",
) -> BootstrapResult:
    """Bootstrap the mean paired difference ``mean(current - baseline)``.

    ``current[i]`` and ``baseline[i]`` must be the *same query's* score in the
    two runs; the caller is responsible for aligning them by query id.

    Returns the observed change, a two-sided confidence interval for it, and
    p-values computed from a separately generated null distribution. See the
    module docstring for why those are two different resample sets.
    """
    current_array, baseline_array = _validate_pair(current, baseline)
    if not 0.0 < confidence_level < 1.0:
        raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level}")
    if resamples < 100:
        raise ValueError(f"resamples must be >= 100, got {resamples}")

    differences: FloatArray = np.asarray(
        current_array - baseline_array, dtype=np.float64
    )
    observed = float(differences.mean())
    n = differences.size
    generator = np.random.default_rng(seed)

    # Every query is equally likely to be drawn, and a query may be drawn more
    # than once -- that *is* the sampling-with-replacement step.
    indices = generator.integers(0, n, size=(resamples, n))
    resample_means: FloatArray = np.asarray(
        differences[indices].mean(axis=1), dtype=np.float64
    )

    interval: tuple[float, float] | None = None
    resolved: IntervalMethod = method
    if method == "bca":
        interval = _bca_interval(differences, resample_means, observed, confidence_level)
        if interval is None:
            # Degenerate bootstrap distribution (e.g. every query moved by the
            # same amount): report the honest percentile interval instead of
            # an undefined correction.
            resolved = "percentile"
    if interval is None:
        interval = _percentile_interval(resample_means, confidence_level)

    two_sided, degradation = _monte_carlo_p_values(
        differences, observed, np.random.default_rng(seed + 1), resamples
    )

    return BootstrapResult(
        observed=observed,
        ci_lower=interval[0],
        ci_upper=interval[1],
        confidence_level=confidence_level,
        p_value=two_sided,
        p_value_degradation=degradation,
        standard_error=float(resample_means.std(ddof=1)),
        sample_size=n,
        resamples=resamples,
        method=resolved,
    )


def bootstrap_mean(
    values: Sequence[float] | FloatArray,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    method: IntervalMethod = "bca",
) -> BootstrapResult:
    """Bootstrap a single run's macro-averaged metric.

    Used for the error bars on the trend chart: it says how precisely this
    golden set pins down the metric, independent of any comparison. The
    p-value fields test the uninteresting ``H₀: mean = 0`` and should be
    ignored for this use.
    """
    array = np.asarray(values, dtype=np.float64)
    return paired_bootstrap_difference(
        array,
        np.zeros_like(array),
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
        method=method,
    )


def mcnemar_paired_test(
    current_hits: Sequence[bool] | NDArray[np.bool_],
    baseline_hits: Sequence[bool] | NDArray[np.bool_],
) -> McNemarResult:
    """Exact McNemar test for a paired binary outcome, e.g. hit rate.

    A two-proportion z-test is the wrong tool here even though the outcome is
    a proportion: it assumes two *independent* samples, and these are the same
    queries measured twice. McNemar conditions on the discordant pairs -- the
    queries whose outcome actually changed -- which is both valid under
    pairing and far more powerful, since concordant queries carry no
    information about change.

    The exact binomial form is used rather than the chi-squared approximation
    because golden sets are small and discordant counts are often < 10, where
    the approximation is unreliable.
    """
    current_array = np.asarray(current_hits, dtype=bool)
    baseline_array = np.asarray(baseline_hits, dtype=bool)
    if current_array.size != baseline_array.size:
        raise ValueError("paired test needs equal-length inputs")
    if current_array.size == 0:
        raise ValueError("paired test needs at least one observation")

    baseline_only = int(np.sum(baseline_array & ~current_array))
    current_only = int(np.sum(~baseline_array & current_array))
    both = int(np.sum(baseline_array & current_array))
    neither = int(np.sum(~baseline_array & ~current_array))

    discordant = baseline_only + current_only
    if discordant == 0:
        # No query changed outcome; there is no evidence of change at all.
        p_value = 1.0
    else:
        p_value = float(
            binomtest(baseline_only, discordant, 0.5, alternative="two-sided").pvalue
        )

    return McNemarResult(
        baseline_only=baseline_only,
        current_only=current_only,
        both=both,
        neither=neither,
        p_value=p_value,
        sample_size=current_array.size,
    )
