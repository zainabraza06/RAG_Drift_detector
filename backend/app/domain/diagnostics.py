"""Value objects for root-cause diagnostics.

**Read this before adding a rule.** Everything in this module is explicitly
*not* a statistical claim, and the type system is arranged to keep it that way.

Stage 3 (drift detection) answers "did retrieval quality really change?" with
a hypothesis test: a confidence interval, a p-value, a stated alpha, and a
refusal to answer when the data cannot support one. Those numbers mean
something precise and were verified by simulation.

This module answers a different question -- "what plausibly caused it?" -- and
there is no test behind that answer. The checks here are heuristics: they
inspect facts about the index and the run history and point at things that
changed. They are useful, they are often right, and they are *not* evidence in
the sense Stage 3 uses the word.

That boundary is enforced by vocabulary, deliberately:

* No field here is called ``confidence``, ``probability``, ``p_value`` or
  ``significant``, and no finding carries a numeric certainty. A rule cannot
  express "85% likely" because there is nothing to calibrate that against.
* Strength is **ordinal** (:class:`EvidenceStrength`), not numeric, and its
  levels describe *how directly the fact links to the observed failures*, not
  how likely the explanation is to be true.
* The one number a finding may quote is :attr:`DiagnosticFinding.explains`:
  how many of the queries that actually broke reference the thing the rule
  found. That is arithmetic over observed data, not inference.
* A diagnostic never creates, upgrades or contradicts a verdict. It only
  annotates one the statistics already established.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: Shown wherever diagnostics are surfaced, so the framing travels with the
#: data rather than living only in this docstring.
DIAGNOSTIC_DISCLAIMER = (
    "Diagnostics are heuristics, not statistical findings. They report facts "
    "that changed alongside the regression and rank them by how directly each "
    "one links to the queries that broke. They do not establish causation, and "
    "they carry none of the confidence of the drift verdict itself."
)


class EvidenceStrength(StrEnum):
    """How directly a finding links to the queries that actually failed.

    Ordinal on purpose. These are not probabilities and must never be rendered
    as percentages or compared numerically across findings.
    """

    #: A verified fact that mechanically accounts for specific failing
    #: queries. "These 5 queries expect documents that are absent from the
    #: index" is checkable and leaves no inferential gap.
    DIRECT = "direct"

    #: A verified change with a plausible mechanism, but no demonstrated link
    #: to the specific failures. The corpus really did grow by 40%; whether
    #: that caused this regression is not established.
    CIRCUMSTANTIAL = "circumstantial"

    #: Describes the *shape* of the regression rather than proposing a cause.
    #: Useful for narrowing the search, never an answer on its own.
    CONTEXTUAL = "contextual"

    @property
    def rank(self) -> int:
        """Sort key; lower sorts first."""
        return {"direct": 0, "circumstantial": 1, "contextual": 2}[self.value]


class DiagnosticFinding(BaseModel):
    """One thing a rule noticed.

    ``summary`` is written to be read aloud to someone who has not seen the
    dashboard, and is phrased as an observation rather than a conclusion --
    "6 expected documents are missing from the index", not "the index is
    broken".
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(description="Stable identifier of the rule that fired.")
    title: str = Field(description="Short label, e.g. 'Expected documents missing'.")
    summary: str = Field(description="Plain-English statement of what was observed.")
    strength: EvidenceStrength

    #: How many of the queries that regressed this finding accounts for, and
    #: out of how many. Plain arithmetic over observed data -- the only number
    #: a finding is allowed to quote about itself.
    explains: int | None = Field(default=None, ge=0)
    out_of: int | None = Field(default=None, ge=0)

    #: Concrete things a human can go and look at: document ids, query ids,
    #: model names. Kept small enough to render.
    evidence: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict
    )
    #: What to do next. Imperative, specific, and never "investigate further".
    suggested_action: str | None = None

    @property
    def coverage(self) -> float | None:
        """Fraction of the failing queries this finding accounts for."""
        if self.explains is None or not self.out_of:
            return None
        return self.explains / self.out_of


class DiagnosticReport(BaseModel):
    """Ranked findings for one run, plus what was checked and ruled out.

    Negative results are kept deliberately. "The embedding model is unchanged"
    is worth as much to someone debugging as any positive finding, and a report
    that only ever shows hits looks like it is fishing.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    #: Always "heuristic". Present in the serialised payload so a client can
    #: never mistake this object for the statistical assessment.
    basis: str = "heuristic"
    disclaimer: str = DIAGNOSTIC_DISCLAIMER

    findings: tuple[DiagnosticFinding, ...] = ()
    #: Rules that ran and found nothing, by id -- the ruled-out list.
    checks_passed: tuple[str, ...] = ()
    #: Rules that could not run, with the reason (e.g. the index was
    #: unreachable). Never silently omitted.
    checks_skipped: dict[str, str] = Field(default_factory=dict)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)

    @property
    def leading_hypothesis(self) -> DiagnosticFinding | None:
        """The highest-ranked finding, or ``None`` if nothing was found."""
        return self.findings[0] if self.findings else None

    @property
    def direct_findings(self) -> tuple[DiagnosticFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.strength is EvidenceStrength.DIRECT
        )
