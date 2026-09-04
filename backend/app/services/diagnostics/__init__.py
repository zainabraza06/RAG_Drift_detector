"""Root-cause diagnostics.

Heuristics, explicitly not statistics. See :mod:`app.domain.diagnostics` for
the framing boundary and why it is enforced by vocabulary.
"""

from app.services.diagnostics.base import (
    DiagnosticContext,
    DiagnosticRule,
    IndexProbe,
    RuleNotApplicable,
    available_rules,
    build_rules,
    register_rule,
)
from app.services.diagnostics.engine import DiagnosticEngine, rank_findings
from app.services.diagnostics.rules import (
    CorpusSizeChangedRule,
    EmbeddingModelChangedRule,
    ExpectedDocumentsDemotedRule,
    MissingExpectedDocumentsRule,
    RegressionShapeRule,
)

__all__ = [
    "CorpusSizeChangedRule",
    "DiagnosticContext",
    "DiagnosticEngine",
    "DiagnosticRule",
    "EmbeddingModelChangedRule",
    "ExpectedDocumentsDemotedRule",
    "IndexProbe",
    "MissingExpectedDocumentsRule",
    "RegressionShapeRule",
    "RuleNotApplicable",
    "available_rules",
    "build_rules",
    "rank_findings",
    "register_rule",
]
