"""Alembic environment.

The database URL comes from application settings rather than ``alembic.ini``,
so ``alembic upgrade head`` always targets the same database the application
does -- including inside Docker, where the URL is an environment variable.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import Connection

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_db_engine

# Importing the models registers every table on Base.metadata, which is what
# `--autogenerate` diffs against.
from app.db import models  # noqa: F401  isort:skip

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # SQLite cannot ALTER most things in place; batch mode rewrites the
        # table instead, so future migrations are not blocked by the backend.
        render_as_batch=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade --sql``)."""
    _configure(url=get_settings().resolved_database_url)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    engine = create_db_engine(get_settings())
    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
