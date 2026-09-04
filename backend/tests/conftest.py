"""Shared test fixtures.

The fake connector below is the payoff of the connector abstraction: the
scoring engine can be tested exhaustively, deterministically and in
milliseconds without a vector store running anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

import pytest

from app.connectors.base import VectorStoreConnector
from app.core.errors import VectorStoreUnavailableError
from app.domain.golden_set import ExpectedDocument, GoldenQuery, GoldenSet
from app.domain.retrieval import RetrievedDocument, VectorStoreInfo


class FakeConnector(VectorStoreConnector):
    """A connector whose results are dictated by the test.

    ``results`` maps query text -> the ranked document ids to return. Queries
    listed in ``failing_queries`` raise, which is how the engine's
    failure-tolerance behaviour is exercised.
    """

    name: ClassVar[str] = "fake"

    def __init__(
        self,
        results: Mapping[str, Sequence[str]],
        *,
        collection: str = "test-collection",
        document_count: int = 100,
        embedding_model: str = "fake-embedder-v1",
        failing_queries: frozenset[str] = frozenset(),
    ) -> None:
        self._results = {query: tuple(ids) for query, ids in results.items()}
        self._collection = collection
        self._document_count = document_count
        self._embedding_model = embedding_model
        self._failing_queries = failing_queries
        self.search_calls: list[tuple[str, int]] = []

    @property
    def collection_name(self) -> str:
        return self._collection

    def count_documents(self) -> int:
        return self._document_count

    def describe(self) -> VectorStoreInfo:
        return VectorStoreInfo(
            connector=self.name,
            collection=self._collection,
            document_count=self._document_count,
            embedding_model=self._embedding_model,
            embedding_dimensions=8,
        )

    def search(self, query: str, k: int) -> tuple[RetrievedDocument, ...]:
        self.search_calls.append((query, k))
        if query in self._failing_queries:
            raise VectorStoreUnavailableError(f"simulated failure for '{query}'")
        ids = self._results.get(query, ())[:k]
        return tuple(
            RetrievedDocument(
                document_id=document_id,
                rank=rank,
                score=1.0 - (rank - 1) * 0.1,
                distance=(rank - 1) * 0.1,
            )
            for rank, document_id in enumerate(ids, start=1)
        )

    def existing_document_ids(self, document_ids: Sequence[str]) -> frozenset[str]:
        indexed = {doc_id for ids in self._results.values() for doc_id in ids}
        return frozenset(indexed.intersection(document_ids))


def make_golden_set(
    pairs: Mapping[str, Sequence[str | tuple[str, int]]],
    *,
    name: str = "test-set",
    version: str = "1",
) -> GoldenSet:
    """Build a golden set from ``{query text: [doc id | (doc id, relevance)]}``."""
    queries = []
    for index, (query_text, expected) in enumerate(pairs.items(), start=1):
        documents = tuple(
            ExpectedDocument(document_id=item)
            if isinstance(item, str)
            else ExpectedDocument(document_id=item[0], relevance=item[1])
            for item in expected
        )
        queries.append(
            GoldenQuery(
                query_id=f"q{index}", query=query_text, expected_documents=documents
            )
        )
    return GoldenSet(name=name, version=version, queries=tuple(queries))


@pytest.fixture
def perfect_connector() -> FakeConnector:
    """Returns each query's expected document at rank 1."""
    return FakeConnector(
        {
            "alpha": ["doc-a", "doc-x", "doc-y"],
            "beta": ["doc-b", "doc-x", "doc-y"],
            "gamma": ["doc-c", "doc-x", "doc-y"],
        }
    )


@pytest.fixture
def perfect_golden_set() -> GoldenSet:
    return make_golden_set(
        {"alpha": ["doc-a"], "beta": ["doc-b"], "gamma": ["doc-c"]}
    )
