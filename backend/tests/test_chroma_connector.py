"""Integration tests for the Chroma connector and hashing embedder.

These run against a real (ephemeral, in-process) Chroma instance, so they
verify the actual response-shape translation rather than a mock's idea of it.
No network access and no model download is involved.
"""

from __future__ import annotations

import pytest

from app.connectors.base import DocumentRecord, SupportsIngestion, VectorStoreConnector
from app.connectors.chroma import ChromaConnector
from app.connectors.registry import available_connectors, create_connector
from app.core.errors import ConfigurationError, UnknownConnectorError
from app.embeddings.hashing import HashingEmbeddingProvider
from app.services.scoring.engine import ScoringConfig, ScoringEngine
from tests.conftest import make_golden_set

DOCUMENTS = [
    DocumentRecord(
        document_id="doc-billing",
        content=(
            "Understanding your invoice. Invoices are generated monthly and list "
            "every subscription line item and metered usage charge."
        ),
        metadata={"category": "billing"},
    ),
    DocumentRecord(
        document_id="doc-auth",
        content=(
            "Resetting a forgotten password. Select forgot password and a single "
            "use reset link is emailed to you."
        ),
        metadata={"category": "authentication"},
    ),
    DocumentRecord(
        document_id="doc-ratelimit",
        content=(
            "Rate limits and throttling. Exceeding the limit returns HTTP 429 with "
            "a Retry-After header expressed in seconds."
        ),
        metadata={"category": "api"},
    ),
]


@pytest.fixture
def connector() -> ChromaConnector:
    store = ChromaConnector(
        collection="test-collection",
        embedding_provider=HashingEmbeddingProvider(dimensions=256),
        mode="memory",
    )
    store.upsert_documents(DOCUMENTS)
    return store


class TestRegistry:
    def test_chroma_is_registered(self) -> None:
        assert "chroma" in available_connectors()

    def test_factory_builds_a_working_connector(self) -> None:
        store = create_connector(
            "chroma",
            collection="factory-test",
            embedding_provider=HashingEmbeddingProvider(dimensions=64),
            mode="memory",
        )
        assert isinstance(store, VectorStoreConnector)
        assert store.count_documents() == 0

    def test_unknown_connector_lists_what_is_available(self) -> None:
        with pytest.raises(UnknownConnectorError, match="available: chroma"):
            create_connector("qdrant", collection="x")

    def test_persistent_mode_requires_a_path(self) -> None:
        with pytest.raises(ConfigurationError, match="requires `persist_path`"):
            ChromaConnector(
                collection="x",
                embedding_provider=HashingEmbeddingProvider(),
                mode="persistent",
            )


class TestReadPath:
    def test_counts_indexed_documents(self, connector: ChromaConnector) -> None:
        assert connector.count_documents() == len(DOCUMENTS)

    def test_search_returns_rank_ordered_hits(self, connector: ChromaConnector) -> None:
        hits = connector.search("http 429 retry after header", k=3)
        assert [hit.rank for hit in hits] == [1, 2, 3]
        assert hits[0].document_id == "doc-ratelimit"
        # Cosine space: score and distance are complementary.
        assert hits[0].distance is not None and hits[0].score is not None
        assert hits[0].score == pytest.approx(1.0 - hits[0].distance)

    def test_search_respects_k(self, connector: ChromaConnector) -> None:
        assert len(connector.search("invoice", k=1)) == 1
        assert len(connector.search("invoice", k=2)) == 2

    def test_search_never_returns_more_than_the_corpus(
        self, connector: ChromaConnector
    ) -> None:
        assert len(connector.search("invoice", k=50)) == len(DOCUMENTS)

    def test_search_hydrates_content_and_metadata(
        self, connector: ChromaConnector
    ) -> None:
        top = connector.search("forgot password reset link", k=1)[0]
        assert top.document_id == "doc-auth"
        assert top.content is not None and "reset link" in top.content
        assert top.metadata["category"] == "authentication"

    def test_rejects_a_non_positive_k(self, connector: ChromaConnector) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            connector.search("anything", k=0)

    def test_existing_document_ids_reports_only_what_is_indexed(
        self, connector: ChromaConnector
    ) -> None:
        found = connector.existing_document_ids(["doc-auth", "doc-gone", "doc-billing"])
        assert found == frozenset({"doc-auth", "doc-billing"})
        assert connector.existing_document_ids([]) == frozenset()

    def test_describe_snapshots_the_index(self, connector: ChromaConnector) -> None:
        info = connector.describe()
        assert info.connector == "chroma"
        assert info.collection == "test-collection"
        assert info.document_count == len(DOCUMENTS)
        # The model recorded on the index, not just the one querying it.
        assert info.embedding_model == "hashing-v1-d256"
        assert info.embedding_dimensions == 256
        assert info.extra["distance"] == "cosine"

    def test_health_check_reports_reachability(self, connector: ChromaConnector) -> None:
        health = connector.health_check()
        assert health.reachable is True
        assert health.document_count == len(DOCUMENTS)

    def test_search_with_timing_wraps_results(self, connector: ChromaConnector) -> None:
        result = connector.search_with_timing("q1", "invoice", k=2)
        assert result.query_id == "q1"
        assert result.latency_ms is not None and result.latency_ms >= 0
        assert len(result.document_ids) == 2
        assert result.top_k_ids(1) == result.document_ids[:1]


class TestIngestion:
    def test_connector_satisfies_the_ingestion_protocol(
        self, connector: ChromaConnector
    ) -> None:
        assert isinstance(connector, SupportsIngestion)

    def test_upsert_replaces_rather_than_duplicates(
        self, connector: ChromaConnector
    ) -> None:
        connector.upsert_documents(
            [DocumentRecord(document_id="doc-auth", content="Replaced content.")]
        )
        assert connector.count_documents() == len(DOCUMENTS)

    def test_delete_removes_documents(self, connector: ChromaConnector) -> None:
        connector.delete_documents(["doc-auth"])
        assert connector.count_documents() == len(DOCUMENTS) - 1
        assert connector.existing_document_ids(["doc-auth"]) == frozenset()

    def test_empty_batches_are_no_ops(self, connector: ChromaConnector) -> None:
        assert connector.upsert_documents([]) == 0
        assert connector.delete_documents([]) == 0


class TestEndToEndScoring:
    def test_engine_scores_a_real_index(self, connector: ChromaConnector) -> None:
        golden_set = make_golden_set(
            {
                "http 429 retry after header": ["doc-ratelimit"],
                "forgot password reset link": ["doc-auth"],
                "monthly invoice line items": ["doc-billing"],
            }
        )
        engine = ScoringEngine(connector, ScoringConfig((1, 3), primary_k=1))
        result = engine.evaluate(golden_set)

        # Lexically unambiguous queries; the hashing embedder should nail all
        # three at rank 1. If this ever fails, retrieval genuinely broke.
        assert result.primary_metrics.recall_at_k == pytest.approx(1.0)
        assert result.primary_metrics.mrr == pytest.approx(1.0)
        assert result.store.document_count == len(DOCUMENTS)


class TestHashingEmbeddings:
    def test_vectors_are_deterministic_across_instances(self) -> None:
        first = HashingEmbeddingProvider(dimensions=128).embed_query("hello world")
        second = HashingEmbeddingProvider(dimensions=128).embed_query("hello world")
        assert first == second

    def test_vectors_are_unit_length(self) -> None:
        vector = HashingEmbeddingProvider(dimensions=128).embed_query("hello world")
        assert sum(value * value for value in vector) == pytest.approx(1.0)

    def test_dimension_is_honoured(self) -> None:
        assert len(HashingEmbeddingProvider(dimensions=64).embed_query("x")) == 64

    def test_empty_text_yields_a_valid_unit_vector(self) -> None:
        vector = HashingEmbeddingProvider(dimensions=32).embed_query("!!! ???")
        assert sum(value * value for value in vector) == pytest.approx(1.0)

    def test_model_id_encodes_algorithm_version_and_dimensions(self) -> None:
        assert HashingEmbeddingProvider(dimensions=256).model_id == "hashing-v1-d256"

    def test_related_text_is_closer_than_unrelated_text(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=512)

        def cosine(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=False))

        anchor = provider.embed_query("reset a forgotten password")
        related = provider.embed_query("password reset link expired")
        unrelated = provider.embed_query("invoice line items and tax")
        assert cosine(anchor, related) > cosine(anchor, unrelated)

    def test_tiny_dimensions_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="dimensions must be >= 16"):
            HashingEmbeddingProvider(dimensions=8)
