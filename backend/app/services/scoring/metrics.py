"""Information-retrieval metrics.

Pure functions over ``(retrieved ids, relevance judgements, k)``. No I/O, no
vector store, no framework types -- which is what makes this module the
easiest part of the system to test exhaustively, and the part an interviewer
is most likely to poke at.

Conventions used here, stated explicitly because IR metrics have several
defensible definitions in the wild:

Recall@k
    ``|relevant ∩ top-k| / |relevant|``. Undefined with no relevant
    documents; we return ``0.0`` and the golden set schema forbids that case.

Precision@k
    ``|relevant ∩ top-k| / min(k, |retrieved|)``. The denominator is clamped
    to what was actually returned so that a store holding fewer than ``k``
    documents is not punished for the size of its corpus. With a full result
    list this is identical to the textbook ``hits / k``.

MRR
    Mean over queries of ``1 / rank`` of the *first* relevant hit within the
    top-k, ``0.0`` when the query missed entirely. Strictly this is MRR@k.

NDCG@k
    Exponential gain ``2^rel - 1`` with ``log2(rank + 1)`` discount, divided
    by the ideal DCG obtained by ranking the query's own judgements
    perfectly. Graded relevance is honoured; with binary judgements it
    reduces to the familiar binary form.

All four are reported in ``[0, 1]`` and aggregated by **macro** averaging --
each query counts once, regardless of how many documents it expects.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

from app.domain.metrics import MetricSet, QueryScore

__all__ = [
    "aggregate_scores",
    "dcg",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]


def _validate_k(k: int) -> None:
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")


def _top_k(retrieved_ids: Sequence[str], k: int) -> Sequence[str]:
    _validate_k(k)
    return retrieved_ids[:k]


def recall_at_k(
    retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int
) -> float:
    """Fraction of the relevant documents that appear in the top ``k``."""
    relevant = frozenset(relevant_ids)
    if not relevant:
        return 0.0
    hits = sum(1 for doc_id in set(_top_k(retrieved_ids, k)) if doc_id in relevant)
    return hits / len(relevant)


def precision_at_k(
    retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int
) -> float:
    """Fraction of the top ``k`` results that are relevant.

    See the module docstring for why the denominator is clamped to the number
    of documents actually returned.
    """
    relevant = frozenset(relevant_ids)
    top = _top_k(retrieved_ids, k)
    if not top:
        return 0.0
    hits = sum(1 for doc_id in set(top) if doc_id in relevant)
    return hits / len(top)


def reciprocal_rank(
    retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int
) -> float:
    """``1 / rank`` of the first relevant hit in the top ``k``; ``0`` if none."""
    relevant = frozenset(relevant_ids)
    for position, doc_id in enumerate(_top_k(retrieved_ids, k), start=1):
        if doc_id in relevant:
            return 1.0 / position
    return 0.0


def first_relevant_rank(
    retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int
) -> int | None:
    """1-based rank of the first relevant hit within the top ``k``."""
    relevant = frozenset(relevant_ids)
    for position, doc_id in enumerate(_top_k(retrieved_ids, k), start=1):
        if doc_id in relevant:
            return position
    return None


def dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain of an already-ordered gain sequence."""
    return sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))


def ndcg_at_k(
    retrieved_ids: Sequence[str], relevance: Mapping[str, int], k: int
) -> float:
    """Normalised DCG at ``k`` under graded ``relevance`` judgements.

    ``relevance`` maps document id -> grade; ids absent from the mapping are
    treated as grade 0. Returns ``0.0`` when the query has no positive
    judgements, since the ideal ranking would then have zero gain.
    """
    top = _top_k(retrieved_ids, k)
    actual_gains = [float(2 ** relevance.get(doc_id, 0) - 1) for doc_id in top]

    ideal_grades = sorted(
        (grade for grade in relevance.values() if grade > 0), reverse=True
    )[:k]
    ideal_gains = [float(2**grade - 1) for grade in ideal_grades]

    ideal = dcg(ideal_gains)
    if ideal == 0.0:
        return 0.0
    # Clamped because floating point can push a perfect ranking a hair over 1.
    return min(1.0, dcg(actual_gains) / ideal)


def aggregate_scores(query_scores: Sequence[QueryScore], k: int) -> MetricSet:
    """Macro-average per-query scores into a single :class:`MetricSet`.

    Every score must have been computed at the same cutoff ``k``; mixing
    cutoffs would produce a silently meaningless average, so it is rejected.
    """
    _validate_k(k)
    mismatched = [score.query_id for score in query_scores if score.k != k]
    if mismatched:
        raise ValueError(
            f"cannot aggregate at k={k}: scores computed at another cutoff "
            f"for queries {mismatched[:5]}"
        )

    count = len(query_scores)
    if count == 0:
        return MetricSet(
            k=k,
            query_count=0,
            recall_at_k=0.0,
            precision_at_k=0.0,
            mrr=0.0,
            ndcg_at_k=0.0,
        )

    def mean(attribute: str) -> float:
        total = sum(float(getattr(score, attribute)) for score in query_scores)
        return total / count

    return MetricSet(
        k=k,
        query_count=count,
        recall_at_k=mean("recall_at_k"),
        precision_at_k=mean("precision_at_k"),
        mrr=mean("reciprocal_rank"),
        ndcg_at_k=mean("ndcg_at_k"),
    )
