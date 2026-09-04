"""Shared test fixtures.

The fake connector below is the payoff of the connector abstraction: the
scoring engine can be tested exhaustively, deterministically and in
milliseconds without a vector store running anywhere.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import create_app
from app.connectors.base import VectorStoreConnector
from app.core.config import Settings, get_settings
from app.core.errors import VectorStoreUnavailableError
from app.db.migrations import upgrade_to_head
from app.db.session import reset_engine, session_scope
from app.domain.golden_set import ExpectedDocument, GoldenQuery, GoldenSet
from app.domain.metrics import EvaluationResult, MetricSet, QueryScore
from app.domain.retrieval import RetrievedDocument, VectorStoreInfo
from app.repositories.golden_sets import GoldenSetRepository
from app.repositories.runs import RunRepository


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


# ----------------------------------------------------------------------
# Database and API fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Isolated settings backed by a throwaway SQLite file and memory Chroma.

    Configured through the environment rather than by constructing Settings
    directly, so the tests exercise the same config path production uses.
    """
    monkeypatch.setenv("DRIFT_ENVIRONMENT", "test")
    monkeypatch.setenv("DRIFT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DRIFT_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    )
    monkeypatch.setenv("DRIFT_CHROMA_MODE", "memory")
    # chromadb.EphemeralClient() is shared per process, so collections
    # outlive the app that made them. A unique name per test is what keeps
    # these isolated and order-independent.
    monkeypatch.setenv("DRIFT_CHROMA_COLLECTION", f"test-{uuid.uuid4().hex[:12]}")
    monkeypatch.setenv("DRIFT_BOOTSTRAP_DEMO", "false")

    get_settings.cache_clear()
    reset_engine()
    resolved = get_settings()
    # The real Alembic migrations run for every test: a schema that only
    # exists via metadata.create_all is a schema nobody has proved deployable.
    upgrade_to_head(resolved)
    try:
        yield resolved
    finally:
        reset_engine()
        get_settings.cache_clear()


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    """A committed-on-exit session against the migrated test database."""
    with session_scope(settings) as db_session:
        yield db_session


@pytest.fixture
def run_repository(session: Session) -> RunRepository:
    return RunRepository(session)


@pytest.fixture
def golden_set_repository(session: Session) -> GoldenSetRepository:
    return GoldenSetRepository(session)


@pytest.fixture
def api_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A live application, bootstrapped with the demo corpus and golden set.

    Bootstrap is left on so the tests also cover startup: migrations, corpus
    indexing and golden set import all have to work for these to pass.
    """
    monkeypatch.setenv("DRIFT_ENVIRONMENT", "test")
    monkeypatch.setenv("DRIFT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DRIFT_DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    )
    monkeypatch.setenv("DRIFT_CHROMA_MODE", "memory")
    monkeypatch.setenv("DRIFT_CHROMA_COLLECTION", f"api-{uuid.uuid4().hex[:12]}")
    monkeypatch.setenv("DRIFT_BOOTSTRAP_DEMO", "true")

    get_settings.cache_clear()
    reset_engine()
    try:
        with TestClient(create_app(get_settings())) as client:
            yield client
    finally:
        reset_engine()
        get_settings.cache_clear()


def make_evaluation_result(
    *,
    recall: float = 0.9,
    ndcg: float = 0.9,
    mrr: float = 0.9,
    precision: float = 0.2,
    document_count: int = 100,
    embedding_model: str = "fake-embedder-v1",
    fingerprint: str = "fingerprint-a",
    name: str = "test-set",
    version: str = "1",
    started_at: datetime | None = None,
    k_values: tuple[int, ...] = (1, 5),
    primary_k: int = 5,
) -> EvaluationResult:
    """A synthetic run result, for testing persistence without scoring."""
    moment = started_at or datetime.now(UTC)
    return EvaluationResult(
        golden_set_name=name,
        golden_set_version=version,
        golden_set_fingerprint=fingerprint,
        query_count=2,
        primary_k=primary_k,
        metrics=tuple(
            MetricSet(
                k=k,
                query_count=2,
                recall_at_k=recall,
                precision_at_k=precision,
                mrr=mrr,
                ndcg_at_k=ndcg,
            )
            for k in k_values
        ),
        query_scores=(
            QueryScore(
                query_id="q1",
                query="alpha",
                k=primary_k,
                retrieved_ids=("doc-a", "doc-x"),
                relevant_ids=("doc-a",),
                hits=1,
                recall_at_k=1.0,
                precision_at_k=0.5,
                reciprocal_rank=1.0,
                ndcg_at_k=1.0,
                first_relevant_rank=1,
                latency_ms=1.5,
            ),
            QueryScore(
                query_id="q2",
                query="beta",
                k=primary_k,
                retrieved_ids=("doc-x", "doc-y"),
                relevant_ids=("doc-b",),
                hits=0,
                recall_at_k=0.0,
                precision_at_k=0.0,
                reciprocal_rank=0.0,
                ndcg_at_k=0.0,
                first_relevant_rank=None,
                latency_ms=1.5,
            ),
        ),
        store=VectorStoreInfo(
            connector="fake",
            collection="test-collection",
            document_count=document_count,
            embedding_model=embedding_model,
            embedding_dimensions=8,
        ),
        started_at=moment,
        finished_at=moment,
    )
