"""The diagnostic rule contract and registry.

A rule is a small, independent, side-effect-free function of a
:class:`DiagnosticContext`. Adding one is a new class plus a decorator -- no
edits to the engine, the API, or any existing rule. That is the whole reason
this is a registry rather than a chain of ``if`` statements: diagnostic
heuristics are exactly the kind of code that accretes, and the accretion has
to be additive.

Rules must not:

* reach for the database, the network or the clock (everything they may
  inspect is on the context, so they stay trivially testable);
* claim statistical confidence -- see :mod:`app.domain.diagnostics`;
* depend on another rule having run, or on the order rules run in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypeVar

from app.domain.diagnostics import DiagnosticFinding
from app.domain.drift import DriftAssessment, MetricComparison
from app.domain.history import RunDetail
from app.domain.metrics import QueryScore


@dataclass(frozen=True, slots=True)
class IndexProbe:
    """Live facts about the vector store, gathered once for all rules.

    Probing is done by the service and passed in, so rules never perform I/O
    and a store that is down degrades to "this check was skipped" rather than
    to an exception mid-report.
    """

    document_count: int | None = None
    present_document_ids: frozenset[str] = frozenset()
    missing_document_ids: frozenset[str] = frozenset()
    reachable: bool = True
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    """Everything a rule is allowed to look at.

    ``baseline`` is ordered newest first and contains exactly the runs the
    drift assessment used, so a diagnostic can never reason about runs the
    verdict did not consider.
    """

    assessment: DriftAssessment
    current: RunDetail
    baseline: Sequence[RunDetail]
    index: IndexProbe

    @property
    def previous(self) -> RunDetail | None:
        """The most recent baseline run, if there is one."""
        return self.baseline[0] if self.baseline else None

    @property
    def regressed_queries(self) -> tuple[QueryScore, ...]:
        """Queries that scored strictly worse than their baseline average.

        This is the population diagnostics are trying to explain. It is
        computed from stored per-query scores, so it is an observation about
        what happened, not an inference about why.
        """
        if not self.baseline:
            return ()

        baseline_by_id: dict[str, list[float]] = {}
        for run in self.baseline:
            for score in run.query_scores:
                baseline_by_id.setdefault(score.query_id, []).append(score.ndcg_at_k)

        regressed: list[QueryScore] = []
        for score in self.current.query_scores:
            history = baseline_by_id.get(score.query_id)
            if not history:
                continue
            if score.ndcg_at_k < sum(history) / len(history):
                regressed.append(score)
        return tuple(regressed)

    @property
    def newly_missing_queries(self) -> tuple[QueryScore, ...]:
        """Queries that retrieved something relevant before and now retrieve nothing.

        The sharpest signal available: a total miss is unambiguous in a way a
        small score change is not.
        """
        if not self.baseline:
            return ()
        previously_hit = {
            score.query_id
            for score in self.baseline[0].query_scores
            if score.hits > 0
        }
        return tuple(
            score
            for score in self.current.query_scores
            if score.is_miss and score.query_id in previously_hit
        )

    @property
    def failing_queries(self) -> tuple[tuple[QueryScore, ...], str]:
        """The population a finding's coverage is measured against, and its name.

        Total misses are preferred when there are any, because they are the
        unambiguous failures. Falling back to "scored worse" keeps the rules
        useful when quality degraded without any query breaking outright.

        The phrase is returned alongside the population so a finding can name
        its own denominator. Two findings quoting "3 of 5" and "23 of 30"
        against silently different populations would invite exactly the
        false comparison this avoids.
        """
        newly_missing = self.newly_missing_queries
        if newly_missing:
            return newly_missing, "queries that stopped retrieving anything relevant"
        return self.regressed_queries, "queries that scored worse than baseline"

    @property
    def primary_comparison(self) -> MetricComparison | None:
        return self.assessment.primary_comparison


class RuleNotApplicable(Exception):
    """Raised by a rule that cannot run, carrying the reason for the report."""


class DiagnosticRule(ABC):
    """One heuristic check."""

    #: Registry key, stable across versions because it is stored with reports.
    rule_id: ClassVar[str] = "unset"
    #: Human label shown in the UI.
    title: ClassVar[str] = "Untitled check"

    def applies(self, context: DiagnosticContext) -> bool:
        """Cheap gate. Rules that need a baseline should override this."""
        return True

    @abstractmethod
    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        """Inspect the context and return a finding, or ``None`` for nothing.

        Returning ``None`` is a *passed check*, and is reported as such.
        Raise :class:`RuleNotApplicable` when the check could not be performed
        at all, so the report can distinguish "ruled out" from "unknown".
        """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.rule_id!r}>"


_REGISTRY: dict[str, type[DiagnosticRule]] = {}

R = TypeVar("R", bound="type[DiagnosticRule]")


def register_rule(rule_cls: R) -> R:
    """Class decorator registering ``rule_cls`` under its ``rule_id``."""
    rule_id = getattr(rule_cls, "rule_id", "unset")
    if rule_id in ("unset", ""):
        raise ValueError(f"{rule_cls.__name__} must define a non-empty `rule_id`")
    if rule_id in _REGISTRY and _REGISTRY[rule_id] is not rule_cls:
        raise ValueError(f"diagnostic rule '{rule_id}' is already registered")
    _REGISTRY[rule_id] = rule_cls
    return rule_cls


def available_rules() -> tuple[str, ...]:
    """Registered rule ids, sorted."""
    return tuple(sorted(_REGISTRY))


def build_rules() -> tuple[DiagnosticRule, ...]:
    """Instantiate every registered rule, in a stable order."""
    return tuple(_REGISTRY[rule_id]() for rule_id in available_rules())
