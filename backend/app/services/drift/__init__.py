"""Statistical drift detection.

``statistics`` holds pure resampling functions; ``detector`` applies them to
runs and turns the numbers into a verdict that explains itself.
"""

from app.services.drift.detector import DriftDetector, holm_bonferroni
from app.services.drift.statistics import (
    BootstrapResult,
    McNemarResult,
    bootstrap_mean,
    mcnemar_paired_test,
    paired_bootstrap_difference,
)

__all__ = [
    "BootstrapResult",
    "DriftDetector",
    "McNemarResult",
    "bootstrap_mean",
    "holm_bonferroni",
    "mcnemar_paired_test",
    "paired_bootstrap_difference",
]
