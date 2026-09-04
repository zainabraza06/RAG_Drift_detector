"""ORM row <-> domain object translation.

Isolated in one module so the mapping is reviewable in a single place and
neither side leaks: repositories never return ORM rows, and the domain layer
never imports SQLAlchemy.
"""

from __future__ import annotations

from app.db.base import as_utc
from app.db.models import (
    EvaluationRunRow,
    ExpectedDocumentRow,
    GoldenQueryRow,
    GoldenSetRow,
    QueryScoreRow,
    RunMetricRow,
)
from app.domain.golden_set import ExpectedDocument, GoldenQuery, GoldenSet
from app.domain.history import GoldenSetRef, RunRecord, StoredGoldenSet
from app.domain.metrics import MetricSet, QueryScore
from app.domain.retrieval import VectorStoreInfo

__all__ = [
    "golden_set_to_rows",
    "row_to_golden_set",
    "row_to_metric_set",
    "row_to_query_score",
    "row_to_run_record",
    "row_to_stored_golden_set",
]


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------
def row_to_metric_set(row: RunMetricRow) -> MetricSet:
    return MetricSet(
        k=row.k,
        query_count=row.query_count,
        recall_at_k=row.recall_at_k,
        precision_at_k=row.precision_at_k,
        mrr=row.mrr,
        ndcg_at_k=row.ndcg_at_k,
    )


def row_to_query_score(row: QueryScoreRow) -> QueryScore:
    return QueryScore(
        query_id=row.query_id,
        query=row.query_text,
        k=row.k,
        retrieved_ids=tuple(row.retrieved_ids or ()),
        relevant_ids=tuple(row.relevant_ids or ()),
        hits=row.hits,
        recall_at_k=row.recall_at_k,
        precision_at_k=row.precision_at_k,
        reciprocal_rank=row.reciprocal_rank,
        ndcg_at_k=row.ndcg_at_k,
        first_relevant_rank=row.first_relevant_rank,
        latency_ms=row.latency_ms,
    )


def row_to_run_record(row: EvaluationRunRow) -> RunRecord:
    return RunRecord(
        run_id=row.run_uuid,
        golden_set=GoldenSetRef(
            name=row.golden_set_name,
            version=row.golden_set_version,
            fingerprint=row.golden_set_fingerprint,
        ),
        query_count=row.query_count,
        primary_k=row.primary_k,
        metrics=tuple(row_to_metric_set(metric) for metric in row.metrics),
        store=VectorStoreInfo(
            connector=row.connector,
            collection=row.collection,
            document_count=row.document_count,
            embedding_model=row.embedding_model,
            embedding_dimensions=row.embedding_dimensions,
            extra=dict(row.store_extra or {}),
        ),
        started_at=as_utc(row.started_at),
        finished_at=as_utc(row.finished_at),
        duration_ms=row.duration_ms,
        trigger=row.trigger,
    )


# ----------------------------------------------------------------------
# Golden sets
# ----------------------------------------------------------------------
def row_to_golden_set(row: GoldenSetRow) -> GoldenSet:
    return GoldenSet(
        name=row.name,
        version=row.version,
        description=row.description,
        created_at=as_utc(row.created_at),
        queries=tuple(
            GoldenQuery(
                query_id=query.query_id,
                query=query.query_text,
                note=query.note,
                expected_documents=tuple(
                    ExpectedDocument(
                        document_id=document.document_id, relevance=document.relevance
                    )
                    for document in query.expected_documents
                ),
            )
            for query in row.queries
        ),
    )


def row_to_stored_golden_set(row: GoldenSetRow) -> StoredGoldenSet:
    return StoredGoldenSet(
        golden_set_id=row.id,
        golden_set=row_to_golden_set(row),
        is_active=row.is_active,
        source=row.source,
        created_at=as_utc(row.created_at),
    )


def golden_set_to_rows(golden_set: GoldenSet) -> list[GoldenQueryRow]:
    """Build the child rows for a golden set, preserving author ordering."""
    return [
        GoldenQueryRow(
            query_id=query.query_id,
            query_text=query.query,
            note=query.note,
            position=position,
            expected_documents=[
                ExpectedDocumentRow(
                    document_id=document.document_id, relevance=document.relevance
                )
                for document in query.expected_documents
            ],
        )
        for position, query in enumerate(golden_set.queries)
    ]
