"""Vector-store facing value objects.

These types are deliberately store-agnostic: every connector translates its
native response shape into them, so the scoring engine never learns whether it
is talking to Chroma, Qdrant or pgvector.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievedDocument(BaseModel):
    """A single hit returned by a vector store, already rank-ordered."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    rank: int = Field(ge=1, description="1-based position in the result list.")
    score: float | None = Field(
        default=None,
        description="Store-native similarity score; higher is more similar.",
    )
    distance: float | None = Field(
        default=None,
        description="Store-native distance; lower is more similar.",
    )
    content: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """The ordered hits a store returned for one query."""

    model_config = ConfigDict(frozen=True)

    query_id: str
    query: str
    documents: tuple[RetrievedDocument, ...] = ()
    latency_ms: float | None = Field(default=None, ge=0)

    @property
    def document_ids(self) -> tuple[str, ...]:
        """Retrieved ids in rank order."""
        return tuple(doc.document_id for doc in self.documents)

    def top_k_ids(self, k: int) -> tuple[str, ...]:
        """The first ``k`` retrieved ids in rank order."""
        if k < 1:
            raise ValueError("k must be >= 1")
        return self.document_ids[:k]


class VectorStoreInfo(BaseModel):
    """A snapshot of the index a run was scored against.

    Captured with every evaluation run because Stage 4 root-cause diagnostics
    reason over *changes* in this snapshot (corpus growth, embedding model
    swaps) to explain a drop in retrieval quality.
    """

    model_config = ConfigDict(frozen=True)

    connector: str = Field(description="Registered connector name, e.g. 'chroma'.")
    collection: str
    document_count: int = Field(ge=0)
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
