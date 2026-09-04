"""Runs the diagnostic rules and ranks what they found.

The engine is deliberately dumb: it runs every applicable rule, collects the
findings, sorts them, and records what was skipped. It contains no diagnostic
logic of its own, so a new heuristic never means editing this file.

A rule that raises is isolated. One badly-behaved heuristic must not be able
to destroy a report -- the drift verdict is already established by this point
and losing the explanation is much worse than losing one line of it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.domain.diagnostics import DiagnosticFinding, DiagnosticReport
from app.services.diagnostics.base import (
    DiagnosticContext,
    DiagnosticRule,
    RuleNotApplicable,
    build_rules,
)

logger = logging.getLogger(__name__)


def rank_findings(
    findings: Sequence[DiagnosticFinding],
) -> tuple[DiagnosticFinding, ...]:
    """Order findings: most direct first, then best-covering.

    Ranking is by evidence *strength* and by how much of the observed damage a
    finding accounts for -- never by a likelihood score, because there is no
    model here that could produce one honestly.
    """
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.strength.rank,
                -(finding.coverage or 0.0),
                finding.rule_id,
            ),
        )
    )


class DiagnosticEngine:
    """Applies a set of rules to a drift assessment."""

    def __init__(self, rules: Sequence[DiagnosticRule] | None = None) -> None:
        self._rules = tuple(rules) if rules is not None else build_rules()

    @property
    def rules(self) -> tuple[DiagnosticRule, ...]:
        return self._rules

    def diagnose(self, context: DiagnosticContext) -> DiagnosticReport:
        """Run every applicable rule and rank the results."""
        findings: list[DiagnosticFinding] = []
        passed: list[str] = []
        skipped: dict[str, str] = {}

        for rule in self._rules:
            try:
                if not rule.applies(context):
                    skipped[rule.rule_id] = "not applicable to this run"
                    continue
                finding = rule.evaluate(context)
            except RuleNotApplicable as exc:
                skipped[rule.rule_id] = str(exc)
                continue
            except Exception:
                # Never let one heuristic take down the report.
                logger.exception("diagnostic rule '%s' failed", rule.rule_id)
                skipped[rule.rule_id] = "the check failed to run"
                continue

            if finding is None:
                passed.append(rule.rule_id)
            else:
                findings.append(finding)

        report = DiagnosticReport(
            run_id=context.current.run.run_id,
            findings=rank_findings(findings),
            checks_passed=tuple(passed),
            checks_skipped=skipped,
        )
        logger.info(
            "diagnostics for run %s: %d finding(s), %d passed, %d skipped",
            context.current.run.run_id,
            len(report.findings),
            len(passed),
            len(skipped),
        )
        return report
