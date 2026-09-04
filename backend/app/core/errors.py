"""Application-level exception hierarchy.

Every error raised by a service inherits from :class:`DriftDetectorError`, so
the API layer can map the whole domain onto HTTP responses in one place
instead of scattering ``try/except`` blocks through route handlers.
"""

from __future__ import annotations


class DriftDetectorError(Exception):
    """Base class for every error this application raises deliberately."""


class ConfigurationError(DriftDetectorError):
    """The application or a component was configured in an unusable way."""


class GoldenSetError(DriftDetectorError):
    """A golden set could not be loaded, parsed or validated."""


class VectorStoreError(DriftDetectorError):
    """Base class for vector store connector failures."""


class VectorStoreUnavailableError(VectorStoreError):
    """The vector store could not be reached at all."""


class CollectionNotFoundError(VectorStoreError):
    """The configured collection does not exist in the vector store."""


class UnknownConnectorError(ConfigurationError):
    """A connector was requested by a name that is not registered."""


class UnknownEmbeddingProviderError(ConfigurationError):
    """An embedding provider was requested by a name that is not registered."""


class EvaluationError(DriftDetectorError):
    """A scoring run could not be completed."""
