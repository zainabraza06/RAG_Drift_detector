"""Pluggable embedding providers.

The provider used to build an index is a first-class, *recorded* property of
an evaluation run: silently swapping embedding models is one of the most
common causes of real-world retrieval drift, and Stage 4 diagnostics detect it
by comparing :attr:`EmbeddingProvider.model_id` across runs.
"""

from app.embeddings.base import EmbeddingProvider
from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.registry import (
    available_embedding_providers,
    create_embedding_provider,
    register_embedding_provider,
)

__all__ = [
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "available_embedding_providers",
    "create_embedding_provider",
    "register_embedding_provider",
]
