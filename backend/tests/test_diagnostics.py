"""Tests for the root-cause diagnostic rules and engine.

Two things are being protected here. The first is that each rule fires on the
situation it describes and stays quiet otherwise. The second, and the reason
:class:`TestFramingBoundary` exists at all, is that diagnostics never start
speaking the language of the statistical layer -- that boundary is a design
decision, and a design decision with no test is a comment.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.domain.diagnostics import (
    DIAGNOSTIC_DISCLAIMER,
    DiagnosticFinding,
    DiagnosticReport,
    EvidenceStrength,
)
from app.domain.drift import DriftAssessment, DriftVerdict
from app.domain.history import GoldenSetRef, RunDetail, RunRecord
from app.domain.metrics import MetricSet, QueryScore
from app.domain.retrieval import VectorStoreInfo
from app.services.diagnostics import (
    DiagnosticContext,
    DiagnosticEngine,
    IndexProbe,
    available_rules,
    build_rules,
    rank_findings,
)
from app.services.diagnostics.base import DiagnosticRule, RuleNotApplicable
from app.services.diagnostics.rules import (
    CorpusSizeChangedRule,
    EmbeddingModelChangedRule,
    ExpectedDocumentsDemotedRule,
    MissingExpectedDocumentsRule,
    RegressionShapeRule,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def score(
    query_id: str,
    *,
    ndcg: float,
    hits: int,
    expects: Sequence[str] = ("doc-a",),
    retrieved: Sequence[str] = ("doc-a",),
) -> QueryScore:
    return QueryScore(
        query_id=query_id,
        query=f"query {query_id}",
        k=5,
        retrieved_ids=tuple(retrieved),
        relevant_ids=tuple(expects),
        hits=hits,
        recall_at_k=ndcg,
        precision_at_k=ndcg,
        reciprocal_rank=ndcg,
        ndcg_at_k=ndcg,
    )


def run(
    run_id: str,
    scores: Sequence[QueryScore],
    *,
    document_count: int = 100,
    embedding_model: str = "hashing-v1-d384",
    embedding_dimensions: int = 384,
) -> RunDetail:
    mean = sum(s.ndcg_at_k for s in scores) / len(scores) if scores else 0.0
    record = RunRecord(
        run_id=run_id,
        golden_set=GoldenSetRef(name="set", version="1", fingerprint="fp-a"),
        query_count=len(scores),
        primary_k=5,
        metrics=(
            MetricSet(
                k=5,
                query_count=len(scores),
                recall_at_k=mean,
                precision_at_k=mean,
                mrr=mean,
                ndcg_at_k=mean,
            ),
        ),
        store=VectorStoreInfo(
            connector="fake",
            collection="c",
            document_count=document_count,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        ),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=1.0,
        trigger="api",
    )
    return RunDetail(run=record, query_scores=tuple(scores))


def assessment(verdict: DriftVerdict = DriftVerdict.DEGRADED) -> DriftAssessment:
    return DriftAssessment(
        run_id="current",
        baseline_run_ids=("older",),
        golden_set=GoldenSetRef(name="set", version="1", fingerprint="fp-a"),
        verdict=verdict,
        summary="a regression",
    )


def context(
    current: RunDetail,
    baseline: Sequence[RunDetail],
    *,
    probe: IndexProbe | None = None,
) -> DiagnosticContext:
    return DiagnosticContext(
        assessment=assessment(),
        current=current,
        baseline=baseline,
        index=probe or IndexProbe(reachable=True),
    )


HEALTHY = [score(f"q{i}", ndcg=1.0, hits=1, expects=(f"doc-{i}",)) for i in range(10)]


# ----------------------------------------------------------------------
# The framing boundary
# ----------------------------------------------------------------------
class TestFramingBoundary:
    """Diagnostics must never look like they carry statistical authority."""

    FORBIDDEN = ("confidence", "probability", "p_value", "significant", "ci_")

    def test_findings_expose_no_statistical_fields(self) -> None:
        fields = set(DiagnosticFinding.model_fields)
        for banned in self.FORBIDDEN:
            assert not any(banned in name for name in fields), (
                f"DiagnosticFinding exposes a field containing '{banned}'; "
                "diagnostics are heuristics and must not borrow the vocabulary "
                "of the statistical layer"
            )

    def test_reports_expose_no_statistical_fields(self) -> None:
        fields = set(DiagnosticReport.model_fields)
        for banned in self.FORBIDDEN:
            assert not any(banned in name for name in fields)

    def test_strength_is_ordinal_not_numeric(self) -> None:
        # A float would invite "78% confident", which nothing here could
        # calibrate. Ordinal levels cannot be misread that way.
        for strength in EvidenceStrength:
            assert isinstance(strength.value, str)
        assert [s.rank for s in EvidenceStrength] == [0, 1, 2]

    def test_every_report_carries_its_basis_and_disclaimer(self) -> None:
        report = DiagnosticReport(run_id="r1")
        assert report.basis == "heuristic"
        assert report.disclaimer == DIAGNOSTIC_DISCLAIMER
        # The framing has to survive serialisation, or an API client sees a
        # bare list of confident-sounding claims.
        payload = report.model_dump(mode="json")
        assert payload["basis"] == "heuristic"
        assert "not statistical findings" in payload["disclaimer"]

    def test_coverage_is_arithmetic_over_observed_queries(self) -> None:
        # The only number a finding may quote about itself, and it is a count
        # of what happened rather than an estimate of anything.
        finding = DiagnosticFinding(
            rule_id="r",
            title="t",
            summary="s",
            strength=EvidenceStrength.DIRECT,
            explains=3,
            out_of=4,
        )
        assert finding.coverage == pytest.approx(0.75)

    def test_coverage_is_none_when_a_rule_cannot_count(self) -> None:
        finding = DiagnosticFinding(
            rule_id="r", title="t", summary="s", strength=EvidenceStrength.DIRECT
        )
        assert finding.coverage is None


# ----------------------------------------------------------------------
# Individual rules
# ----------------------------------------------------------------------
class TestMissingExpectedDocuments:
    def test_fires_and_attributes_the_broken_queries(self) -> None:
        current = run(
            "current",
            [
                score("q0", ndcg=0.0, hits=0, expects=("doc-0",), retrieved=("x",)),
                score("q1", ndcg=0.0, hits=0, expects=("doc-1",), retrieved=("x",)),
                *HEALTHY[2:],
            ],
        )
        probe = IndexProbe(
            missing_document_ids=frozenset({"doc-0", "doc-1"}),
            present_document_ids=frozenset(f"doc-{i}" for i in range(2, 10)),
        )
        finding = MissingExpectedDocumentsRule().evaluate(
            context(current, [run("older", HEALTHY)], probe=probe)
        )

        assert finding is not None
        assert finding.strength is EvidenceStrength.DIRECT
        assert finding.explains == 2
        assert finding.out_of == 2
        assert finding.coverage == pytest.approx(1.0)
        assert "2 document(s)" in finding.summary
        assert finding.evidence["missing_document_ids"] == ["doc-0", "doc-1"]

    def test_stays_quiet_when_nothing_is_missing(self) -> None:
        finding = MissingExpectedDocumentsRule().evaluate(
            context(run("current", HEALTHY), [run("older", HEALTHY)])
        )
        assert finding is None

    def test_reports_itself_unrunnable_when_the_index_is_down(self) -> None:
        probe = IndexProbe(reachable=False, failure_reason="connection refused")
        with pytest.raises(RuleNotApplicable, match="connection refused"):
            MissingExpectedDocumentsRule().evaluate(
                context(run("current", HEALTHY), [run("older", HEALTHY)], probe=probe)
            )

    def test_names_the_population_its_coverage_is_measured_against(self) -> None:
        current = run(
            "current",
            [
                score("q0", ndcg=0.0, hits=0, expects=("doc-0",), retrieved=("x",)),
                *HEALTHY[1:],
            ],
        )
        probe = IndexProbe(missing_document_ids=frozenset({"doc-0"}))
        finding = MissingExpectedDocumentsRule().evaluate(
            context(current, [run("older", HEALTHY)], probe=probe)
        )
        assert finding is not None
        # Two findings quoting different denominators must not read as
        # comparable, so each says what it counted.
        assert "measured_against" in finding.evidence
        assert finding.evidence["measured_against"] in finding.summary


class TestEmbeddingModelChanged:
    def test_fires_on_a_model_swap(self) -> None:
        finding = EmbeddingModelChangedRule().evaluate(
            context(
                run("current", HEALTHY, embedding_model="minilm-v2"),
                [run("older", HEALTHY, embedding_model="hashing-v1-d384")],
            )
        )
        assert finding is not None
        assert finding.strength is EvidenceStrength.DIRECT
        assert "hashing-v1-d384" in finding.summary
        assert "minilm-v2" in finding.summary

    def test_fires_on_a_dimensionality_change_alone(self) -> None:
        finding = EmbeddingModelChangedRule().evaluate(
            context(
                run("current", HEALTHY, embedding_dimensions=768),
                [run("older", HEALTHY, embedding_dimensions=384)],
            )
        )
        assert finding is not None
        assert "384" in finding.summary and "768" in finding.summary

    def test_quotes_no_coverage_because_a_swap_affects_everything(self) -> None:
        finding = EmbeddingModelChangedRule().evaluate(
            context(
                run("current", HEALTHY, embedding_model="other"),
                [run("older", HEALTHY)],
            )
        )
        assert finding is not None
        # Claiming "explains 4 of 7 queries" would imply a specificity a
        # global model change does not have.
        assert finding.explains is None
        assert finding.coverage is None

    def test_stays_quiet_when_the_model_is_unchanged(self) -> None:
        finding = EmbeddingModelChangedRule().evaluate(
            context(run("current", HEALTHY), [run("older", HEALTHY)])
        )
        assert finding is None

    def test_does_not_apply_without_a_baseline(self) -> None:
        assert not EmbeddingModelChangedRule().applies(context(run("c", HEALTHY), []))


class TestExpectedDocumentsDemoted:
    def test_fires_when_documents_are_present_but_not_retrieved(self) -> None:
        current = run(
            "current",
            [
                score("q0", ndcg=0.0, hits=0, expects=("doc-0",), retrieved=("noise",)),
                *HEALTHY[1:],
            ],
        )
        probe = IndexProbe(
            present_document_ids=frozenset(f"doc-{i}" for i in range(10)),
            missing_document_ids=frozenset(),
        )
        finding = ExpectedDocumentsDemotedRule().evaluate(
            context(current, [run("older", HEALTHY)], probe=probe)
        )

        assert finding is not None
        assert finding.strength is EvidenceStrength.DIRECT
        assert "still present" in finding.summary
        assert "ranking" in finding.summary
        assert finding.evidence["still_indexed_document_ids"] == ["doc-0"]

    def test_stays_quiet_when_the_document_is_actually_gone(self) -> None:
        """The discriminator: deletion is not demotion.

        Without this the two rules would both fire on every regression and the
        report would stop distinguishing a content problem from a ranking one.
        """
        current = run(
            "current",
            [
                score("q0", ndcg=0.0, hits=0, expects=("doc-0",), retrieved=("noise",)),
                *HEALTHY[1:],
            ],
        )
        probe = IndexProbe(
            present_document_ids=frozenset(f"doc-{i}" for i in range(1, 10)),
            missing_document_ids=frozenset({"doc-0"}),
        )
        assert (
            ExpectedDocumentsDemotedRule().evaluate(
                context(current, [run("older", HEALTHY)], probe=probe)
            )
            is None
        )


class TestCorpusSizeChanged:
    def test_fires_on_material_growth(self) -> None:
        finding = CorpusSizeChangedRule().evaluate(
            context(
                run("current", HEALTHY, document_count=500),
                [run("older", HEALTHY, document_count=100)],
            )
        )
        assert finding is not None
        # Growth is never more than circumstantial: nothing here shows these
        # queries broke *because* of it.
        assert finding.strength is EvidenceStrength.CIRCUMSTANTIAL
        assert finding.evidence["fraction"] == pytest.approx(4.0)
        assert "grew" in finding.summary

    def test_fires_on_shrinkage(self) -> None:
        finding = CorpusSizeChangedRule().evaluate(
            context(
                run("current", HEALTHY, document_count=60),
                [run("older", HEALTHY, document_count=100)],
            )
        )
        assert finding is not None
        assert "shrank" in finding.summary

    def test_ignores_ordinary_ingestion_noise(self) -> None:
        finding = CorpusSizeChangedRule().evaluate(
            context(
                run("current", HEALTHY, document_count=105),
                [run("older", HEALTHY, document_count=100)],
            )
        )
        assert finding is None

    def test_is_unrunnable_against_an_empty_baseline_index(self) -> None:
        with pytest.raises(RuleNotApplicable, match="empty index"):
            CorpusSizeChangedRule().evaluate(
                context(
                    run("current", HEALTHY, document_count=10),
                    [run("older", HEALTHY, document_count=0)],
                )
            )


class TestRegressionShape:
    def _shape(self, regressed: int) -> str:
        scores = [
            score(
                f"q{i}",
                ndcg=0.2 if i < regressed else 1.0,
                hits=1,
                expects=(f"doc-{i}",),
            )
            for i in range(20)
        ]
        baseline = [
            score(f"q{i}", ndcg=1.0, hits=1, expects=(f"doc-{i}",)) for i in range(20)
        ]
        finding = RegressionShapeRule().evaluate(
            context(run("current", scores), [run("older", baseline)])
        )
        assert finding is not None
        return str(finding.evidence["shape"])

    def test_a_few_broken_queries_read_as_concentrated(self) -> None:
        assert self._shape(3) == "concentrated"

    def test_most_of_the_set_moving_reads_as_broad(self) -> None:
        assert self._shape(16) == "broad"

    def test_in_between_reads_as_mixed(self) -> None:
        assert self._shape(8) == "mixed"

    def test_is_only_ever_contextual(self) -> None:
        scores = [
            score(f"q{i}", ndcg=0.2, hits=1, expects=(f"doc-{i}",)) for i in range(20)
        ]
        baseline = [
            score(f"q{i}", ndcg=1.0, hits=1, expects=(f"doc-{i}",)) for i in range(20)
        ]
        finding = RegressionShapeRule().evaluate(
            context(run("current", scores), [run("older", baseline)])
        )
        assert finding is not None
        # Describing the shape of a failure is not proposing a cause.
        assert finding.strength is EvidenceStrength.CONTEXTUAL


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------
class TestRanking:
    def _finding(
        self, rule_id: str, strength: EvidenceStrength, coverage: float | None
    ) -> DiagnosticFinding:
        explains, out_of = (
            (None, None) if coverage is None else (int(coverage * 10), 10)
        )
        return DiagnosticFinding(
            rule_id=rule_id,
            title=rule_id,
            summary="s",
            strength=strength,
            explains=explains,
            out_of=out_of,
        )

    def test_direct_findings_outrank_circumstantial_ones(self) -> None:
        ranked = rank_findings(
            [
                self._finding("shape", EvidenceStrength.CONTEXTUAL, 1.0),
                self._finding("growth", EvidenceStrength.CIRCUMSTANTIAL, 1.0),
                self._finding("missing", EvidenceStrength.DIRECT, 0.2),
            ]
        )
        assert [f.rule_id for f in ranked] == ["missing", "growth", "shape"]

    def test_coverage_breaks_ties_within_a_strength(self) -> None:
        ranked = rank_findings(
            [
                self._finding("a", EvidenceStrength.DIRECT, 0.3),
                self._finding("b", EvidenceStrength.DIRECT, 0.9),
            ]
        )
        assert [f.rule_id for f in ranked] == ["b", "a"]

    def test_ranking_is_deterministic_for_identical_findings(self) -> None:
        findings = [
            self._finding("z", EvidenceStrength.DIRECT, 0.5),
            self._finding("a", EvidenceStrength.DIRECT, 0.5),
        ]
        assert [f.rule_id for f in rank_findings(findings)] == ["a", "z"]


class TestEngine:
    def test_registry_holds_every_built_in_rule(self) -> None:
        assert available_rules() == (
            "corpus_size_changed",
            "embedding_model_changed",
            "expected_documents_demoted",
            "missing_expected_documents",
            "regression_shape",
        )
        assert len(build_rules()) == 5

    def test_rules_that_find_nothing_are_reported_as_passed(self) -> None:
        report = DiagnosticEngine().diagnose(
            context(run("current", HEALTHY), [run("older", HEALTHY)])
        )
        assert not report.has_findings
        assert "embedding_model_changed" in report.checks_passed
        assert "missing_expected_documents" in report.checks_passed

    def test_unrunnable_rules_are_reported_as_skipped_not_passed(self) -> None:
        # "We checked and it is fine" and "we could not check" are different
        # claims, and collapsing them would overstate what the report knows.
        probe = IndexProbe(reachable=False, failure_reason="store unreachable")
        report = DiagnosticEngine().diagnose(
            context(run("current", HEALTHY), [run("older", HEALTHY)], probe=probe)
        )
        assert "missing_expected_documents" in report.checks_skipped
        assert "missing_expected_documents" not in report.checks_passed
        assert report.checks_skipped["missing_expected_documents"] == "store unreachable"

    def test_a_rule_that_raises_cannot_destroy_the_report(self) -> None:
        class ExplodingRule(DiagnosticRule):
            rule_id = "exploding"
            title = "Explodes"

            def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
                raise RuntimeError("boom")

        engine = DiagnosticEngine(
            rules=[ExplodingRule(), EmbeddingModelChangedRule()]
        )
        report = engine.diagnose(
            context(
                run("current", HEALTHY, embedding_model="other"),
                [run("older", HEALTHY)],
            )
        )
        assert report.checks_skipped["exploding"] == "the check failed to run"
        assert [f.rule_id for f in report.findings] == ["embedding_model_changed"]

    def test_leading_hypothesis_is_the_top_ranked_finding(self) -> None:
        current = run(
            "current",
            [
                score("q0", ndcg=0.0, hits=0, expects=("doc-0",), retrieved=("x",)),
                *HEALTHY[1:],
            ],
            document_count=500,
            embedding_model="other",
        )
        probe = IndexProbe(missing_document_ids=frozenset({"doc-0"}))
        report = DiagnosticEngine().diagnose(
            context(current, [run("older", HEALTHY)], probe=probe)
        )

        assert report.leading_hypothesis is not None
        assert report.leading_hypothesis.strength is EvidenceStrength.DIRECT
        assert len(report.direct_findings) >= 1
