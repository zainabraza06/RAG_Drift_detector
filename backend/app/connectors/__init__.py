"""Pluggable vector store connectors.

Importing this package registers every built-in connector, so
:func:`create_connector` can resolve them by name.
"""

from app.connectors.base import (
    ConnectorHealth,
    DocumentRecord,
    SupportsIngestion,
    VectorStoreConnector,
)
from app.connectors.chroma import ChromaConnector
from app.connectors.registry import (
    available_connectors,
    create_connector,
    register_connector,
)

__all__ = [
    "ChromaConnector",
    "ConnectorHealth",
    "DocumentRecord",
    "SupportsIngestion",
    "VectorStoreConnector",
    "available_connectors",
    "create_connector",
    "register_connector",
]
