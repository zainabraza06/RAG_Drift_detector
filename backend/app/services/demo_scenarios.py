"""Break and repair the demo index on demand.

A drift detector pointed at an index nobody touches has nothing to detect:
every run scores the same and the verdict is always "stable". In production
the index is changed by some other pipeline; in the demo there is none, so
this module plays that pipeline's part, reproducing two failures that
genuinely happen to RAG systems:

* **documents deleted** - an ingestion job drops content the golden set
  expects. A *content* regression: the right answers are no longer there.
* **botched re-chunk** - a re-index splits every document into sentence
  fragments and leaves the originals in place. Nothing is lost, but the
  fragments crowd the originals out of the top-k. A *ranking* regression.

Nothing here touches scoring, drift detection or diagnostics. The scenarios
only change the index, exactly as an outside pipeline would, and the rest of
the system has to notice on its own.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.connectors.base import DocumentRecord, SupportsIngestion, VectorStoreConnector
from app.core.errors import ConfigurationError, DriftDetectorError
from app.services.corpus import seed_documents

logger = logging.getLogger(__name__)

#: Removed by the "documents deleted" scenario. Spread across categories so
#: several unrelated queries break at once, which is what a botched ingestion
#: actually looks like.
BROKEN_DOCUMENTS: tuple[str, ...] = (
    "doc-api-001",
    "doc-api-002",
    "doc-auth-003",
    "doc-security-003",
    "doc-data-002",
    "doc-support-003",
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class DemoDisabledError(DriftDetectorError):
    """Demo controls are switched off for this deployment."""


class Scenario(StrEnum):
    DELETE_DOCUMENTS = "delete-documents"
    RECHUNK = "rechunk"
    RESTORE = "restore"


@dataclass(frozen=True, slots=True)
class IndexState:
    """What the demo index currently looks like, relative to the clean corpus."""

    document_count: int
    corpus_size: int
    missing_documents: int
    fragment_documents: int

    @property
    def healthy(self) -> bool:
        return self.missing_documents == 0 and self.fragment_documents == 0


def fragment_documents(documents: Sequence[DocumentRecord]) -> tuple[DocumentRecord, ...]:
    """Split each document into one record per sentence, as a bad re-chunk would."""
    fragments: list[DocumentRecord] = []
    for document in documents:
        sentences = [s for s in _SENTENCE_END.split(document.content) if s.strip()]
        for index, sentence in enumerate(sentences, start=1):
            fragments.append(
                DocumentRecord(
                    document_id=f"{document.document_id}::chunk-{index}",
                    content=sentence,
                    metadata={**document.metadata, "fragment_of": document.document_id},
                )
            )
    return tuple(fragments)


class DemoScenarioService:
    """Applies scenarios to the demo index and reports its state."""

    def __init__(
        self,
        store: VectorStoreConnector,
        corpus: Sequence[DocumentRecord],
        *,
        enabled: bool,
    ) -> None:
        self._store = store
        self._corpus = tuple(corpus)
        self._fragments = fragment_documents(self._corpus)
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def state(self) -> IndexState:
        corpus_ids = [document.document_id for document in self._corpus]
        fragment_ids = [document.document_id for document in self._fragments]
        present = self._store.existing_document_ids(corpus_ids)
        fragments = self._store.existing_document_ids(fragment_ids)
        return IndexState(
            document_count=self._store.count_documents(),
            corpus_size=len(corpus_ids),
            missing_documents=len(corpus_ids) - len(present),
            fragment_documents=len(fragments),
        )

    def apply(self, scenario: Scenario) -> IndexState:
        if not self._enabled:
            raise DemoDisabledError(
                "demo controls are disabled; set DRIFT_DEMO_CONTROLS=true to enable them"
            )
        store = self._writable()

        if scenario is Scenario.DELETE_DOCUMENTS:
            store.delete_documents(BROKEN_DOCUMENTS)
        elif scenario is Scenario.RECHUNK:
            seed_documents(self._store, self._fragments)
        else:
            store.delete_documents([d.document_id for d in self._fragments])
            seed_documents(self._store, self._corpus)

        state = self.state()
        logger.info("demo scenario %s applied: %s", scenario.value, state)
        return state

    def _writable(self) -> SupportsIngestion:
        if not isinstance(self._store, SupportsIngestion):
            raise ConfigurationError(
                f"connector '{self._store.name}' is read-only; demo scenarios need "
                "one that supports ingestion"
            )
        return self._store
