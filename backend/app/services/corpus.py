"""Loading a document corpus and seeding it into a vector store.

This is a *demo and fixture* concern rather than a monitoring concern -- in
production the corpus is indexed by whatever pipeline owns the RAG system, and
this tool only reads it. It lives in the codebase so the repository is
explorable end to end with no external setup.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.connectors.base import DocumentRecord, SupportsIngestion, VectorStoreConnector
from app.core.errors import ConfigurationError, DriftDetectorError

logger = logging.getLogger(__name__)

#: Documents are written in batches so a large corpus does not build one
#: enormous request; Chroma handles a few hundred at a time comfortably.
DEFAULT_BATCH_SIZE = 128


class CorpusError(DriftDetectorError):
    """A document corpus could not be loaded."""


def load_documents(path: str | Path) -> tuple[DocumentRecord, ...]:
    """Read a corpus JSON file into :class:`DocumentRecord` objects.

    Accepts either ``{"documents": [...]}`` or a bare list. Each document
    needs an ``id`` and ``content``; ``title`` and ``category`` are folded
    into metadata, and the title is prepended to the indexed text because a
    document's heading is usually its most discriminative sentence.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise CorpusError(f"corpus file not found: {file_path}")

    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"invalid JSON in corpus {file_path}: {exc}") from exc

    raw_documents = payload if isinstance(payload, list) else payload.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise CorpusError(f"corpus {file_path} contains no 'documents'")

    records: list[DocumentRecord] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_documents):
        if not isinstance(raw, dict):
            raise CorpusError(f"documents[{index}] must be an object")

        document_id = str(raw.get("id") or raw.get("document_id") or "").strip()
        content = str(raw.get("content") or raw.get("text") or "").strip()
        if not document_id:
            raise CorpusError(f"documents[{index}] is missing 'id'")
        if not content:
            raise CorpusError(f"document '{document_id}' has empty content")
        if document_id in seen:
            raise CorpusError(f"duplicate document id '{document_id}' in corpus")
        seen.add(document_id)

        title = str(raw.get("title") or "").strip()
        metadata: dict[str, str | int | float | bool] = {}
        if title:
            metadata["title"] = title
        category = raw.get("category")
        if category:
            metadata["category"] = str(category)

        records.append(
            DocumentRecord(
                document_id=document_id,
                content=f"{title}. {content}" if title else content,
                metadata=metadata,
            )
        )

    logger.debug("loaded %d documents from %s", len(records), file_path)
    return tuple(records)


def seed_documents(
    connector: VectorStoreConnector,
    documents: Sequence[DocumentRecord],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Upsert ``documents`` into ``connector``; returns the number written.

    Raises :class:`ConfigurationError` if the connector is read-only, which
    the :class:`~app.connectors.base.SupportsIngestion` protocol makes a
    runtime-checkable question rather than a guess.
    """
    if not isinstance(connector, SupportsIngestion):
        raise ConfigurationError(
            f"connector '{connector.name}' does not support ingestion; "
            "index the corpus with your own pipeline instead"
        )
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    written = 0
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        written += connector.upsert_documents(batch)
        logger.debug("upserted %d/%d documents", written, len(documents))

    logger.info(
        "seeded %d documents into %s collection '%s'",
        written,
        connector.name,
        connector.collection_name,
    )
    return written
