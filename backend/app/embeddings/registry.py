"""Name -> embedding provider registry.

Providers register themselves with a decorator at import time, so adding a new
one is a single new module plus an import — no edits to the scoring engine, the
API or the config loader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from app.core.errors import UnknownEmbeddingProviderError

if TYPE_CHECKING:  # pragma: no cover
    from app.embeddings.base import EmbeddingProvider

_REGISTRY: dict[str, type[EmbeddingProvider]] = {}

P = TypeVar("P", bound="type[EmbeddingProvider]")


def register_embedding_provider(provider_cls: P) -> P:
    """Class decorator registering ``provider_cls`` under its ``name``."""
    name = getattr(provider_cls, "name", "unset")
    if name in ("unset", ""):
        raise ValueError(f"{provider_cls.__name__} must define a non-empty `name`")
    if name in _REGISTRY and _REGISTRY[name] is not provider_cls:
        raise ValueError(f"embedding provider '{name}' is already registered")
    _REGISTRY[name] = provider_cls
    return provider_cls


def available_embedding_providers() -> tuple[str, ...]:
    """Registered provider names, sorted."""
    return tuple(sorted(_REGISTRY))


def create_embedding_provider(name: str, **options: Any) -> EmbeddingProvider:
    """Instantiate the provider registered under ``name``."""
    try:
        provider_cls = _REGISTRY[name]
    except KeyError:
        raise UnknownEmbeddingProviderError(
            f"unknown embedding provider '{name}'; "
            f"available: {', '.join(available_embedding_providers()) or 'none'}"
        ) from None
    return provider_cls(**options)
