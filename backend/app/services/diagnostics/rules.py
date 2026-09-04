"""The built-in diagnostic rules.

Ordered here roughly from most to least direct, though the engine ranks by
:class:`~app.domain.diagnostics.EvidenceStrength` and coverage rather than by
declaration order.

Every rule states an observation. None of them claims causation, and none
reports a numeric confidence -- see :mod:`app.domain.diagnostics` for why that
boundary exists and how it is enforced.
"""

from __future__ import annotations

from typing import ClassVar

from app.domain.diagnostics import DiagnosticFinding, EvidenceStrength
from app.services.diagnostics.base import (
    DiagnosticContext,
    DiagnosticRule,
    RuleNotApplicable,
    register_rule,
)

#: Ids are truncated in evidence payloads so a report stays renderable when a
#: whole collection has gone missing.
MAX_LISTED_IDS = 12


def _sample(ids: set[str] | frozenset[str]) -> list[str]:
    return sorted(ids)[:MAX_LISTED_IDS]


@register_rule
class MissingExpectedDocumentsRule(DiagnosticRule):
    """Expected documents that are no longer in the index at all.

    The most direct finding available: if a query expects document X and X is
    absent from the store, that query mechanically cannot retrieve it. No
    inference is involved, which is why this is the one rule allowed to say it
    accounts for specific failures.
    """

    rule_id: ClassVar[str] = "missing_expected_documents"
    title: ClassVar[str] = "Expected documents missing from the index"

    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        probe = context.index
        if not probe.reachable:
            raise RuleNotApplicable(
                probe.failure_reason or "the vector store could not be reached"
            )

        missing = probe.missing_document_ids
        if not missing:
            return None

        # Which of the queries that actually broke expect a missing document?
        broken, population = context.failing_queries
        accounted = [
            score
            for score in broken
            if any(doc_id in missing for doc_id in score.relevant_ids)
        ]

        summary = (
            f"{len(missing)} document(s) the golden set expects are absent from "
            f"the index."
        )
        if broken:
            summary += (
                f" {len(accounted)} of the {len(broken)} {population} "
                f"expect at least one of them."
            )

        return DiagnosticFinding(
            rule_id=self.rule_id,
            title=self.title,
            summary=summary,
            strength=EvidenceStrength.DIRECT,
            explains=len(accounted) if broken else None,
            out_of=len(broken) if broken else None,
            evidence={
                "missing_document_count": len(missing),
                "missing_document_ids": _sample(missing),
                "affected_query_ids": [score.query_id for score in accounted][
                    :MAX_LISTED_IDS
                ],
                "measured_against": population,
            },
            suggested_action=(
                "Check whether the last indexing job dropped these documents, or "
                "whether they were deleted upstream. If the removal was intended, "
                "update the golden set so it stops expecting them."
            ),
        )


@register_rule
class EmbeddingModelChangedRule(DiagnosticRule):
    """The embedding model or dimensionality differs between runs.

    Mechanically unambiguous: vectors built by a different model are not
    comparable, so every similarity score changes at once. Recorded on each
    run precisely so this is checkable rather than guessable.
    """

    rule_id: ClassVar[str] = "embedding_model_changed"
    title: ClassVar[str] = "Embedding model changed between runs"

    def applies(self, context: DiagnosticContext) -> bool:
        return context.previous is not None

    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        previous = context.previous
        if previous is None:  # pragma: no cover - guarded by applies()
            raise RuleNotApplicable("no earlier run to compare against")

        current_store = context.current.run.store
        previous_store = previous.run.store

        model_changed = current_store.embedding_model != previous_store.embedding_model
        dimensions_changed = (
            current_store.embedding_dimensions != previous_store.embedding_dimensions
        )
        if not (model_changed or dimensions_changed):
            return None

        if model_changed:
            summary = (
                f"The index reports a different embedding model than it did in the "
                f"previous run: '{previous_store.embedding_model}' became "
                f"'{current_store.embedding_model}'."
            )
        else:
            summary = (
                f"Embedding dimensionality changed from "
                f"{previous_store.embedding_dimensions} to "
                f"{current_store.embedding_dimensions}."
            )

        return DiagnosticFinding(
            rule_id=self.rule_id,
            title=self.title,
            summary=summary,
            strength=EvidenceStrength.DIRECT,
            # A model swap affects every query at once, so quoting a per-query
            # coverage number would imply a specificity this does not have.
            evidence={
                "previous_model": previous_store.embedding_model or "unknown",
                "current_model": current_store.embedding_model or "unknown",
                "previous_dimensions": previous_store.embedding_dimensions or 0,
                "current_dimensions": current_store.embedding_dimensions or 0,
            },
            suggested_action=(
                "Re-index the whole corpus with a single embedding model. A "
                "collection holding vectors from two models returns meaningless "
                "distances, and the golden set should be re-baselined afterwards."
            ),
        )


@register_rule
class ExpectedDocumentsDemotedRule(DiagnosticRule):
    """Expected documents are still indexed but no longer retrieved.

    The discriminator between a *content* problem and a *ranking* problem. If
    the documents are present and simply stopped appearing in the top-k, the
    corpus is intact and something about scoring, chunking or neighbouring
    content changed instead.
    """

    rule_id: ClassVar[str] = "expected_documents_demoted"
    title: ClassVar[str] = "Expected documents still indexed but no longer retrieved"

    def applies(self, context: DiagnosticContext) -> bool:
        return context.index.reachable and bool(context.baseline)

    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        probe = context.index
        if not probe.reachable:
            raise RuleNotApplicable(
                probe.failure_reason or "the vector store could not be reached"
            )

        broken, population = context.failing_queries
        if not broken:
            return None

        demoted = [
            score
            for score in broken
            # Every document this query expects is still in the index, yet the
            # query no longer surfaces any of them.
            if score.relevant_ids
            and all(doc_id in probe.present_document_ids for doc_id in score.relevant_ids)
            and not set(score.retrieved_ids) & set(score.relevant_ids)
        ]
        if not demoted:
            return None

        return DiagnosticFinding(
            rule_id=self.rule_id,
            title=self.title,
            summary=(
                f"{len(demoted)} of the {len(broken)} {population} expect documents "
                f"that are still present in the index but fell out of the top-k. "
                f"The content is intact; what changed is the ranking."
            ),
            strength=EvidenceStrength.DIRECT,
            explains=len(demoted),
            out_of=len(broken),
            evidence={
                "query_ids": [score.query_id for score in demoted][:MAX_LISTED_IDS],
                "still_indexed_document_ids": _sample(
                    {doc_id for score in demoted for doc_id in score.relevant_ids}
                ),
                "measured_against": population,
            },
            suggested_action=(
                "Look at what was added or re-chunked near these documents, and at "
                "any change to the distance metric or retrieval depth. Raising k "
                "would mask this rather than fix it."
            ),
        )


@register_rule
class CorpusSizeChangedRule(DiagnosticRule):
    """The indexed document count moved materially since the baseline.

    Circumstantial by nature. A corpus that grew 40% really did grow, and
    growth genuinely can dilute retrieval -- but nothing here demonstrates
    that *these* queries broke *because* of it, and saying otherwise would be
    the exact overreach this module is arranged to prevent.
    """

    rule_id: ClassVar[str] = "corpus_size_changed"
    title: ClassVar[str] = "Indexed document count changed"

    #: Below this the change is noise from ordinary ingestion.
    MATERIAL_FRACTION: ClassVar[float] = 0.10

    def applies(self, context: DiagnosticContext) -> bool:
        return context.previous is not None

    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        previous = context.previous
        if previous is None:  # pragma: no cover - guarded by applies()
            raise RuleNotApplicable("no earlier run to compare against")

        before = previous.run.store.document_count
        after = context.current.run.store.document_count
        if before == 0:
            raise RuleNotApplicable("the baseline run recorded an empty index")

        change = after - before
        fraction = change / before
        if abs(fraction) < self.MATERIAL_FRACTION:
            return None

        direction = "grew" if change > 0 else "shrank"
        summary = (
            f"The index {direction} from {before:,} to {after:,} documents "
            f"({fraction:+.0%}) since the baseline run."
        )
        if change > 0:
            summary += (
                " A larger corpus gives every query more competing neighbours, "
                "which can push expected documents out of the top-k."
            )
        else:
            summary += " Documents were removed from the index."

        return DiagnosticFinding(
            rule_id=self.rule_id,
            title=self.title,
            summary=summary,
            strength=EvidenceStrength.CIRCUMSTANTIAL,
            evidence={
                "baseline_document_count": before,
                "current_document_count": after,
                "change": change,
                "fraction": round(fraction, 4),
            },
            suggested_action=(
                "Check whether the golden set still represents the corpus. A set "
                "written for 500 documents may simply be stale for 5,000."
                if change > 0
                else "Confirm the removal was intentional and not a partial "
                "indexing failure."
            ),
        )


@register_rule
class RegressionShapeRule(DiagnosticRule):
    """Whether the regression is concentrated in a few queries or spread across all.

    Not a cause -- a description of the failure's shape, which is what narrows
    the search. A handful of broken queries points at specific documents; a
    uniform drop across the whole set points at something systemic.
    """

    rule_id: ClassVar[str] = "regression_shape"
    title: ClassVar[str] = "Shape of the regression"

    #: At or below this fraction of the golden set, the damage is localised.
    CONCENTRATED_FRACTION: ClassVar[float] = 0.25
    #: At or above this, essentially everything moved.
    BROAD_FRACTION: ClassVar[float] = 0.60

    def applies(self, context: DiagnosticContext) -> bool:
        return bool(context.baseline) and bool(context.current.query_scores)

    def evaluate(self, context: DiagnosticContext) -> DiagnosticFinding | None:
        regressed = context.regressed_queries
        total = len(context.current.query_scores)
        if not regressed or not total:
            return None

        fraction = len(regressed) / total
        if fraction <= self.CONCENTRATED_FRACTION:
            shape = "concentrated"
            reading = (
                "A small, specific set of queries moved, which points at particular "
                "documents rather than at the index as a whole."
            )
        elif fraction >= self.BROAD_FRACTION:
            shape = "broad"
            reading = (
                "Most of the golden set moved together, which points at something "
                "systemic: a re-index, an embedding change, or a retrieval "
                "configuration change."
            )
        else:
            shape = "mixed"
            reading = (
                "The regression is neither localised nor uniform, so both a "
                "content change and a configuration change are still in play."
            )

        return DiagnosticFinding(
            rule_id=self.rule_id,
            title=self.title,
            summary=(
                f"{len(regressed)} of {total} queries scored worse than baseline "
                f"({fraction:.0%}). {reading}"
            ),
            strength=EvidenceStrength.CONTEXTUAL,
            explains=len(regressed),
            out_of=total,
            evidence={
                "shape": shape,
                "measured_against": "all queries in the golden set",
                "regressed_query_ids": [
                    score.query_id for score in regressed[:MAX_LISTED_IDS]
                ],
                "worst_query_id": min(
                    regressed, key=lambda score: score.ndcg_at_k
                ).query_id,
            },
            suggested_action=(
                "Start from the worst-scoring queries listed here and compare "
                "their retrieved documents against the previous run."
            ),
        )
