"""Golden evaluation set: the ground truth definition of "good retrieval".

A golden set is a versioned collection of queries, each annotated with the
document ids that *should* be retrieved for it. It is the yardstick every
scoring run is measured against, so it is treated as an immutable, content
addressed artifact: the ``fingerprint`` changes whenever the queries change,
which lets historical runs be compared only when they were scored against
comparable ground truth.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Default graded relevance assigned to an expected document when the golden
#: set does not specify one. Binary relevance (0/1) is the common case.
DEFAULT_RELEVANCE: int = 1


class ExpectedDocument(BaseModel):
    """A single document that a query is expected to retrieve.

    ``relevance`` supports *graded* judgements (0 = irrelevant, higher = more
    relevant). Graded values only affect NDCG; the set based metrics
    (Recall/Precision/MRR) treat any ``relevance > 0`` as relevant.
    """

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1, description="Vector store document id.")
    relevance: int = Field(
        default=DEFAULT_RELEVANCE,
        ge=0,
        le=10,
        description="Graded relevance; 0 means explicitly non-relevant.",
    )


class GoldenQuery(BaseModel):
    """One (query, expected documents) judgement."""

    model_config = ConfigDict(frozen=True)

    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_documents: tuple[ExpectedDocument, ...] = Field(min_length=1)
    note: str | None = Field(
        default=None, description="Optional human context for why this pair matters."
    )

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped

    @model_validator(mode="after")
    def _reject_duplicate_documents(self) -> GoldenQuery:
        ids = [doc.document_id for doc in self.expected_documents]
        if len(ids) != len(set(ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(
                f"query '{self.query_id}' lists duplicate document ids: {duplicates}"
            )
        return self

    @property
    def relevant_document_ids(self) -> frozenset[str]:
        """Ids with non-zero relevance — the denominator for Recall@k."""
        return frozenset(
            doc.document_id for doc in self.expected_documents if doc.relevance > 0
        )

    def relevance_of(self, document_id: str) -> int:
        """Graded relevance of ``document_id``; 0 when it is not expected."""
        for doc in self.expected_documents:
            if doc.document_id == document_id:
                return doc.relevance
        return 0


class GoldenSet(BaseModel):
    """A named, versioned collection of :class:`GoldenQuery` judgements."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, default="default")
    version: str = Field(min_length=1, default="1")
    description: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    queries: tuple[GoldenQuery, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _reject_duplicate_query_ids(self) -> GoldenSet:
        ids = [q.query_id for q in self.queries]
        if len(ids) != len(set(ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate query_ids in golden set: {duplicates}")
        return self

    def __len__(self) -> int:
        return len(self.queries)

    @property
    def all_expected_document_ids(self) -> frozenset[str]:
        """Every document id referenced anywhere in the set.

        Stage 4 diagnostics use this to detect expected documents that have
        disappeared from the index.
        """
        return frozenset(
            doc.document_id for query in self.queries for doc in query.expected_documents
        )

    @property
    def fingerprint(self) -> str:
        """Stable content hash of the judgements (not the metadata).

        Two golden sets with the same fingerprint are interchangeable for
        drift comparison purposes even if their names or timestamps differ.
        """
        payload = [
            {
                "query_id": q.query_id,
                "query": q.query,
                "expected": sorted(
                    (d.document_id, d.relevance) for d in q.expected_documents
                ),
            }
            for q in sorted(self.queries, key=lambda q: q.query_id)
        ]
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
