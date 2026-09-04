"""Name -> vector store connector registry.

Mirrors :mod:`app.embeddings.registry`. The API and CLI resolve connectors by
name from configuration, so a new backend becomes available to the whole
application the moment its module is imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from app.core.errors import UnknownConnectorError

if TYPE_CHECKING:  # pragma: no cover
    from app.connectors.base import VectorStoreConnector

_REGISTRY: dict[str, type[VectorStoreConnector]] = {}

C = TypeVar("C", bound="type[VectorStoreConnector]")


def register_connector(connector_cls: C) -> C:
    """Class decorator registering ``connector_cls`` under its ``name``."""
    name = getattr(connector_cls, "name", "unset")
    if name in ("unset", ""):
        raise ValueError(f"{connector_cls.__name__} must define a non-empty `name`")
    if name in _REGISTRY and _REGISTRY[name] is not connector_cls:
        raise ValueError(f"connector '{name}' is already registered")
    _REGISTRY[name] = connector_cls
    return connector_cls


def available_connectors() -> tuple[str, ...]:
    """Registered connector names, sorted."""
    return tuple(sorted(_REGISTRY))


def create_connector(name: str, **options: Any) -> VectorStoreConnector:
    """Instantiate the connector registered under ``name``."""
    try:
        connector_cls = _REGISTRY[name]
    except KeyError:
        raise UnknownConnectorError(
            f"unknown vector store connector '{name}'; "
            f"available: {', '.join(available_connectors()) or 'none'}"
        ) from None
    return connector_cls(**options)
