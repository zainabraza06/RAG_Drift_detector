"""Logging setup.

One helper, called once at process start (CLI ``main`` or FastAPI lifespan),
so log formatting is consistent everywhere and no module configures logging as
an import side effect.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

#: Third-party loggers that are noisy at INFO and say nothing we need.
_QUIET_LOGGERS = ("chromadb", "httpx", "urllib3", "posthog", "onnxruntime")


def configure_logging(level: str = "INFO") -> None:
    """Install a single stderr handler on the root logger."""
    resolved = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(resolved, logging.WARNING))
