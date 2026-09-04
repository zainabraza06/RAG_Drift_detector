"""Engine and session management.

SQLite needs two non-default pragmas to behave like a real database under a
web server, and both are set here rather than being assumed:

``foreign_keys=ON``
    SQLite ignores foreign key constraints unless asked. Without this, the
    ``ON DELETE CASCADE`` declared on every child table is silently inert and
    deleting a run would orphan its metrics.

``journal_mode=WAL``
    Write-ahead logging lets readers proceed during a write, which is what
    keeps a dashboard poll from blocking on an in-progress evaluation.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _apply_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        # Wait rather than fail immediately if another connection holds a
        # write lock; evaluations are short but not instantaneous.
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Build an engine for the configured database URL."""
    settings = settings or get_settings()
    url = settings.resolved_database_url
    is_sqlite = url.startswith("sqlite")

    if is_sqlite and ":memory:" not in url:
        # SQLAlchemy will not create the parent directory for us.
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        url,
        # FastAPI serves requests from a thread pool; the default SQLite
        # check would reject connections reused across threads.
        connect_args={"check_same_thread": False} if is_sqlite else {},
        echo=settings.environment == "development" and settings.log_level == "DEBUG",
        future=True,
    )
    if is_sqlite:
        event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    """Process-wide engine singleton."""
    global _engine
    if _engine is None:
        _engine = create_db_engine(settings)
        logger.debug("database engine created for %s", _engine.url)
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any exception."""
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Drop the cached engine and session factory.

    Only used by tests and by the CLI's ``db reset``; production processes
    keep one engine for their lifetime.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
