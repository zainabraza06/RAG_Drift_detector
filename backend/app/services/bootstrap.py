"""First-run bootstrap.

Makes a fresh install explorable immediately: migrate the schema, index the
demo corpus if the vector store is empty, and import the demo golden set if
none is stored. Every step is idempotent and individually skippable, so this
is safe to run on every start and easy to disable in production
(``DRIFT_BOOTSTRAP_DEMO=false``).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from app.connectors.base import SupportsIngestion, VectorStoreConnector
from app.core.config import Settings, get_settings
from app.core.errors import DriftDetectorError
from app.db.migrations import upgrade_to_head
from app.db.session import session_scope
from app.repositories.golden_sets import GoldenSetRepository
from app.services.corpus import load_documents, seed_documents
from app.services.golden_set_service import GoldenSetService

logger = logging.getLogger(__name__)


class BootstrapReport(BaseModel):
    """What the bootstrap actually did, for logging and for tests."""

    model_config = ConfigDict(frozen=True)

    migrated: bool = False
    documents_indexed: int = 0
    golden_set_imported: str | None = None
    skipped: tuple[str, ...] = ()


def bootstrap(
    *,
    settings: Settings | None = None,
    vector_store: VectorStoreConnector | None = None,
) -> BootstrapReport:
    """Prepare a fresh installation. Safe to call on every startup."""
    settings = settings or get_settings()
    settings.ensure_directories()
    skipped: list[str] = []

    migrated = False
    if settings.auto_migrate:
        upgrade_to_head(settings)
        migrated = True
    else:
        skipped.append("migrations (auto_migrate disabled)")

    if not settings.bootstrap_demo:
        return BootstrapReport(
            migrated=migrated, skipped=(*skipped, "demo data (bootstrap_demo disabled)")
        )

    indexed = _seed_corpus_if_empty(settings, vector_store, skipped)
    imported = _import_golden_set_if_empty(settings, skipped)

    report = BootstrapReport(
        migrated=migrated,
        documents_indexed=indexed,
        golden_set_imported=imported,
        skipped=tuple(skipped),
    )
    logger.info("bootstrap complete: %s", report.model_dump())
    return report


def _seed_corpus_if_empty(
    settings: Settings,
    vector_store: VectorStoreConnector | None,
    skipped: list[str],
) -> int:
    if vector_store is None:
        skipped.append("demo corpus (no vector store provided)")
        return 0
    if not settings.demo_documents_path.exists():
        skipped.append(f"demo corpus (not found at {settings.demo_documents_path})")
        return 0

    try:
        if vector_store.count_documents() > 0:
            skipped.append("demo corpus (collection already populated)")
            return 0
        if not isinstance(vector_store, SupportsIngestion):
            skipped.append("demo corpus (connector is read-only)")
            return 0
        documents = load_documents(settings.demo_documents_path)
        return seed_documents(vector_store, documents)
    except DriftDetectorError as exc:
        # A failed demo seed must never stop the API from starting; the
        # dashboard's empty state is a better outcome than a crash loop.
        logger.warning("skipping demo corpus seed: %s", exc)
        skipped.append(f"demo corpus ({exc})")
        return 0


def _import_golden_set_if_empty(settings: Settings, skipped: list[str]) -> str | None:
    if not settings.demo_golden_set_path.exists():
        skipped.append(f"demo golden set (not found at {settings.demo_golden_set_path})")
        return None

    try:
        with session_scope(settings) as session:
            service = GoldenSetService(GoldenSetRepository(session))
            if service.list_sets(limit=1).total > 0:
                skipped.append("demo golden set (a golden set already exists)")
                return None
            stored = service.import_if_absent(
                settings.demo_golden_set_path, activate=True
            )
            return stored.golden_set.name if stored else None
    except DriftDetectorError as exc:
        logger.warning("skipping demo golden set import: %s", exc)
        skipped.append(f"demo golden set ({exc})")
        return None
