"""Chroma implementation of :class:`~app.connectors.base.VectorStoreConnector`.

Three client modes are supported behind one class:

``persistent``  on-disk index (the default, and what docker-compose mounts)
``http``        a remote ``chroma run`` server
``memory``      ephemeral, used by the test suite

The connector deliberately embeds queries itself through an
:class:`~app.embeddings.base.EmbeddingProvider` rather than relying on Chroma's
built-in embedding function. That keeps the embedding model an explicit,
recorded property of every run -- which is what makes the Stage 4
"embedding model changed" diagnostic possible -- and keeps the demo runnable
with no model download.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from app.connectors.base import DocumentRecord, VectorStoreConnector
from app.connectors.registry import register_connector
from app.core.errors import (
    CollectionNotFoundError,
    ConfigurationError,
    VectorStoreError,
    VectorStoreUnavailableError,
)
from app.domain.retrieval import RetrievedDocument, VectorStoreInfo
from app.embeddings.base import EmbeddingProvider

if TYPE_CHECKING:  # pragma: no cover
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection

ClientMode = Literal["persistent", "http", "memory"]

#: Chroma stores the vectors' distance function in collection metadata. Our
#: providers emit L2-normalised vectors, for which cosine is the right space.
_HNSW_SPACE = "cosine"

#: Metadata keys we stamp on the collection at creation time so that an index
#: can always say which embedding model built it.
_META_MODEL = "drift_detector.embedding_model"
_META_DIMENSIONS = "drift_detector.embedding_dimensions"


@register_connector
class ChromaConnector(VectorStoreConnector):
    """Read/write access to a single Chroma collection."""

    name: ClassVar[str] = "chroma"

    def __init__(
        self,
        collection: str,
        embedding_provider: EmbeddingProvider,
        *,
        mode: ClientMode = "persistent",
        persist_path: str | None = None,
        host: str | None = None,
        port: int = 8000,
        ssl: bool = False,
        create_if_missing: bool = True,
    ) -> None:
        if mode == "persistent" and not persist_path:
            raise ConfigurationError("chroma persistent mode requires `persist_path`")
        if mode == "http" and not host:
            raise ConfigurationError("chroma http mode requires `host`")

        self._collection_name = collection
        self._provider = embedding_provider
        self._mode: ClientMode = mode
        self._persist_path = persist_path
        self._host = host
        self._port = port
        self._ssl = ssl
        self._create_if_missing = create_if_missing
        self._client: ClientAPI | None = None
        self._collection: Collection | None = None

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------
    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        return self._provider

    def _get_client(self) -> ClientAPI:
        if self._client is not None:
            return self._client
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ConfigurationError(
                "chromadb is not installed; add it to your environment"
            ) from exc

        try:
            if self._mode == "persistent":
                assert self._persist_path is not None  # guarded in __init__
                self._client = chromadb.PersistentClient(path=self._persist_path)
            elif self._mode == "http":
                assert self._host is not None  # guarded in __init__
                self._client = chromadb.HttpClient(
                    host=self._host, port=self._port, ssl=self._ssl
                )
            else:
                self._client = chromadb.EphemeralClient()
        except Exception as exc:
            raise VectorStoreUnavailableError(
                f"could not connect to Chroma ({self._mode}): {exc}"
            ) from exc
        return self._client

    def _get_collection(self) -> Collection:
        if self._collection is not None:
            return self._collection
        client = self._get_client()
        try:
            if self._create_if_missing:
                self._collection = client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={
                        "hnsw:space": _HNSW_SPACE,
                        _META_MODEL: self._provider.model_id,
                        _META_DIMENSIONS: self._provider.dimensions,
                    },
                )
            else:
                self._collection = client.get_collection(name=self._collection_name)
        except VectorStoreError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "does not exist" in message or "not found" in message:
                raise CollectionNotFoundError(
                    f"Chroma collection '{self._collection_name}' does not exist"
                ) from exc
            raise VectorStoreUnavailableError(
                f"could not open Chroma collection '{self._collection_name}': {exc}"
            ) from exc
        return self._collection

    def close(self) -> None:
        self._collection = None
        self._client = None

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------
    def count_documents(self) -> int:
        collection = self._get_collection()
        try:
            return int(collection.count())
        except Exception as exc:
            raise VectorStoreUnavailableError(f"Chroma count failed: {exc}") from exc

    def describe(self) -> VectorStoreInfo:
        collection = self._get_collection()
        metadata: dict[str, Any] = dict(collection.metadata or {})
        indexed_model = metadata.get(_META_MODEL)
        indexed_dimensions = metadata.get(_META_DIMENSIONS)
        return VectorStoreInfo(
            connector=self.name,
            collection=self._collection_name,
            document_count=self.count_documents(),
            # The model recorded *on the index* is the honest answer to "what
            # built these vectors"; the query-time provider is reported
            # separately so a mismatch between the two is detectable.
            embedding_model=(
                str(indexed_model) if indexed_model else self._provider.model_id
            ),
            embedding_dimensions=(
                int(indexed_dimensions)
                if isinstance(indexed_dimensions, int | float)
                else self._provider.dimensions
            ),
            extra={
                "mode": self._mode,
                "distance": str(metadata.get("hnsw:space", _HNSW_SPACE)),
                "query_embedding_model": self._provider.model_id,
            },
        )

    def search(self, query: str, k: int) -> tuple[RetrievedDocument, ...]:
        if k < 1:
            raise ValueError("k must be >= 1")
        collection = self._get_collection()
        embedding = self._provider.embed_query(query)
        try:
            response = collection.query(
                # Chroma's stubs invariantly type this as list[Sequence[float]];
                # our list[float] is structurally identical.
                query_embeddings=cast(Any, [embedding]),
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreUnavailableError(f"Chroma query failed: {exc}") from exc
        return self._to_documents(response)

    @staticmethod
    def _to_documents(response: Any) -> tuple[RetrievedDocument, ...]:
        """Flatten Chroma's ``{key: [[...per query...]]}`` response shape."""

        def first_row(key: str) -> list[Any]:
            rows = response.get(key) or []
            if len(rows) == 0 or rows[0] is None:
                return []
            return list(rows[0])

        ids = first_row("ids")
        distances = first_row("distances")
        documents = first_row("documents")
        metadatas = first_row("metadatas")

        hits: list[RetrievedDocument] = []
        for position, document_id in enumerate(ids):
            distance = float(distances[position]) if position < len(distances) else None
            hits.append(
                RetrievedDocument(
                    document_id=str(document_id),
                    rank=position + 1,
                    # Cosine space: distance = 1 - similarity.
                    score=(1.0 - distance) if distance is not None else None,
                    distance=distance,
                    content=(documents[position] if position < len(documents) else None),
                    metadata=(
                        dict(metadatas[position] or {})
                        if position < len(metadatas)
                        else {}
                    ),
                )
            )
        return tuple(hits)

    def existing_document_ids(self, document_ids: Sequence[str]) -> frozenset[str]:
        unique_ids = list(dict.fromkeys(document_ids))
        if not unique_ids:
            return frozenset()
        collection = self._get_collection()
        try:
            response = collection.get(ids=unique_ids, include=[])
        except Exception as exc:
            raise VectorStoreUnavailableError(f"Chroma get failed: {exc}") from exc
        return frozenset(str(found) for found in (response.get("ids") or []))

    # ------------------------------------------------------------------
    # Ingestion capability (see SupportsIngestion)
    # ------------------------------------------------------------------
    def upsert_documents(self, documents: Sequence[DocumentRecord]) -> int:
        if not documents:
            return 0
        collection = self._get_collection()
        contents = [record.content for record in documents]
        try:
            collection.upsert(
                ids=[record.document_id for record in documents],
                documents=contents,
                embeddings=self._provider.embed_documents(contents),  # type: ignore[arg-type]
                metadatas=[
                    dict(record.metadata) or {"seeded": True} for record in documents
                ],
            )
        except Exception as exc:
            raise VectorStoreUnavailableError(f"Chroma upsert failed: {exc}") from exc
        return len(documents)

    def delete_documents(self, document_ids: Sequence[str]) -> int:
        unique_ids = list(dict.fromkeys(document_ids))
        if not unique_ids:
            return 0
        collection = self._get_collection()
        try:
            collection.delete(ids=unique_ids)
        except Exception as exc:
            raise VectorStoreUnavailableError(f"Chroma delete failed: {exc}") from exc
        return len(unique_ids)
