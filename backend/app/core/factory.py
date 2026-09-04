"""Composition root.

Every object graph the application needs is assembled here from
:class:`~app.core.config.Settings`. Keeping construction in one module means
services depend on abstractions (``VectorStoreConnector``,
``EmbeddingProvider``) and never on configuration -- which is what makes them
trivially testable with fakes.
"""

from __future__ import annotations

from app.connectors import create_connector
from app.connectors.base import VectorStoreConnector
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.embeddings import create_embedding_provider
from app.embeddings.base import EmbeddingProvider
from app.services.scoring.engine import ScoringConfig, ScoringEngine

__all__ = [
    "build_embedding_provider",
    "build_scoring_config",
    "build_scoring_engine",
    "build_vector_store",
]


def build_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Instantiate the configured embedding provider."""
    settings = settings or get_settings()
    options: dict[str, object] = {}
    if settings.embedding_provider == "hashing":
        options["dimensions"] = settings.embedding_dimensions
    return create_embedding_provider(settings.embedding_provider, **options)


def build_vector_store(
    settings: Settings | None = None,
    *,
    embedding_provider: EmbeddingProvider | None = None,
) -> VectorStoreConnector:
    """Instantiate the configured vector store connector."""
    settings = settings or get_settings()
    provider = embedding_provider or build_embedding_provider(settings)

    if settings.connector != "chroma":
        raise ConfigurationError(
            f"connector '{settings.connector}' has no wiring in the composition "
            "root yet; add it to build_vector_store()"
        )

    settings.ensure_directories()
    return create_connector(
        "chroma",
        collection=settings.chroma_collection,
        embedding_provider=provider,
        mode=settings.chroma_mode,
        persist_path=str(settings.resolved_chroma_path),
        host=settings.chroma_host,
        port=settings.chroma_port,
        ssl=settings.chroma_ssl,
    )


def build_scoring_config(settings: Settings | None = None) -> ScoringConfig:
    settings = settings or get_settings()
    return ScoringConfig(
        k_values=tuple(int(k) for k in settings.eval_k_values),
        primary_k=settings.eval_primary_k,
    )


def build_scoring_engine(
    settings: Settings | None = None,
    *,
    connector: VectorStoreConnector | None = None,
) -> ScoringEngine:
    """Assemble a ready-to-run scoring engine."""
    settings = settings or get_settings()
    return ScoringEngine(
        connector=connector or build_vector_store(settings),
        config=build_scoring_config(settings),
    )
