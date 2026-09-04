"""Programmatic access to Alembic.

``alembic upgrade head`` is the source of truth for schema changes, but the
API container and the test suite should not have to shell out to run it. These
helpers drive the same migration scripts in-process, so there is exactly one
definition of the schema and no ``create_all`` shortcut that could drift from
the migration history.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import BACKEND_DIR, Settings, get_settings
from app.db.session import get_engine

logger = logging.getLogger(__name__)

ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def build_alembic_config(settings: Settings | None = None) -> Config:
    """An Alembic ``Config`` pointed at this package's migration scripts.

    Paths are absolute so migrations run correctly regardless of the process
    working directory -- which differs between the CLI, uvicorn and pytest.
    """
    settings = settings or get_settings()
    if not ALEMBIC_INI.exists():  # pragma: no cover - packaging guard
        raise FileNotFoundError(f"alembic.ini not found at {ALEMBIC_INI}")

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", settings.resolved_database_url)
    return config


def upgrade_to_head(settings: Settings | None = None) -> None:
    """Bring the database up to the latest revision. Idempotent."""
    settings = settings or get_settings()
    settings.ensure_directories()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    logger.info("applying database migrations to head")
    command.upgrade(build_alembic_config(settings), "head")


def downgrade_to(revision: str, settings: Settings | None = None) -> None:
    """Roll the database back to ``revision`` (``base`` empties it)."""
    command.downgrade(build_alembic_config(settings), revision)


def current_revision(settings: Settings | None = None) -> str | None:
    """The revision the database is currently stamped with, if any."""
    engine = get_engine(settings)
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def head_revision(settings: Settings | None = None) -> str | None:
    """The latest revision available in the migration scripts."""
    return ScriptDirectory.from_config(build_alembic_config(settings)).get_current_head()


def is_up_to_date(settings: Settings | None = None) -> bool:
    """Whether the database schema matches the newest migration."""
    return current_revision(settings) == head_revision(settings)
