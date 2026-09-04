"""The embedding provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

Vector = list[float]


class EmbeddingProvider(ABC):
    """Turns text into vectors, and identifies itself while doing so.

    Implementations must be deterministic for a given ``model_id``: two runs
    that report the same ``model_id`` and ``dimensions`` are assumed by the
    drift detector to have embedded text the same way.
    """

    #: Registry key, e.g. ``"hashing"``. Set by subclasses.
    name: str = "unset"

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier of the model *and* its version.

        Recorded with every run; a change here is grounds for a
        "embedding model changed" drift diagnosis.
        """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Length of the vectors this provider emits."""

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed a batch of documents for indexing."""

    def embed_query(self, text: str) -> Vector:
        """Embed a single search query.

        Defaults to document embedding; providers with asymmetric
        query/document encoders override this.
        """
        return self.embed_documents([text])[0]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} model_id={self.model_id!r} dim={self.dimensions}>"
