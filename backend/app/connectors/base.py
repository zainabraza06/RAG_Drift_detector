"""The vector store connector contract.

The scoring engine depends on :class:`VectorStoreConnector` and nothing else.
Adding Qdrant or pgvector means writing one new module that implements this
ABC and registering it — no changes to metrics, drift detection or the API.

The contract is split in two on purpose:

* :class:`VectorStoreConnector` — the **read** path, all the scoring engine
  needs (search, count, describe, id existence).
* :class:`SupportsIngestion` — an **optional** capability, implemented only by
  stores this tool can also write to (used to seed the demo corpus).

Keeping ingestion out of the core contract means a connector can be written
for a read-only production index without stubbing methods it cannot honour.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.domain.retrieval import RetrievalResult, RetrievedDocument, VectorStoreInfo


class ConnectorHealth(BaseModel):
    """Result of a connector reachability probe."""

    model_config = ConfigDict(frozen=True)

    connector: str
    collection: str
    reachable: bool
    document_count: int | None = None
    message: str | None = None


class DocumentRecord(BaseModel):
    """A document to be written into a store that supports ingestion."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class VectorStoreConnector(ABC):
    """Read access to one collection in one vector store."""

    #: Registry key, e.g. ``"chroma"``. Set by subclasses.
    name: ClassVar[str] = "unset"

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """The collection this connector is bound to."""

    @abstractmethod
    def count_documents(self) -> int:
        """Number of documents currently indexed in the collection.

        Stage 4 diagnostics compare this across runs to spot corpus growth
        that outpaced the golden set.
        """

    @abstractmethod
    def describe(self) -> VectorStoreInfo:
        """Snapshot the index for the run record."""

    @abstractmethod
    def search(self, query: str, k: int) -> tuple[RetrievedDocument, ...]:
        """Return the top ``k`` hits for ``query``, rank-ordered from 1.

        Implementations must raise a subclass of
        :class:`~app.core.errors.VectorStoreError` rather than leaking
        store-native exceptions.
        """

    @abstractmethod
    def existing_document_ids(self, document_ids: Sequence[str]) -> frozenset[str]:
        """Subset of ``document_ids`` that are present in the collection.

        Powers the "expected documents missing from the index" diagnostic.
        """

    def search_with_timing(self, query_id: str, query: str, k: int) -> RetrievalResult:
        """``search`` wrapped into a :class:`RetrievalResult` with latency.

        Provided by the base class so every connector reports latency the same
        way; override only if the store can report server-side timing.
        """
        started = time.perf_counter()
        documents = self.search(query, k)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return RetrievalResult(
            query_id=query_id,
            query=query,
            documents=documents,
            latency_ms=elapsed_ms,
        )

    def health_check(self) -> ConnectorHealth:
        """Probe the store. Never raises — reports failure in the result."""
        from app.core.errors import VectorStoreError

        try:
            count = self.count_documents()
        except VectorStoreError as exc:
            return ConnectorHealth(
                connector=self.name,
                collection=self.collection_name,
                reachable=False,
                message=str(exc),
            )
        return ConnectorHealth(
            connector=self.name,
            collection=self.collection_name,
            reachable=True,
            document_count=count,
        )

    def close(self) -> None:  # noqa: B027 - optional hook, not every store holds resources
        """Release any held resources. Safe to call more than once."""

    def __enter__(self) -> VectorStoreConnector:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} collection={self.collection_name!r}>"


@runtime_checkable
class SupportsIngestion(Protocol):
    """Optional capability: a store this tool can also write documents into."""

    def upsert_documents(self, documents: Sequence[DocumentRecord]) -> int:
        """Insert or replace ``documents``; returns the number written."""
        ...

    def delete_documents(self, document_ids: Sequence[str]) -> int:
        """Remove documents by id; returns the number requested for deletion."""
        ...
