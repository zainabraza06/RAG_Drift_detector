"""Declarative base and shared column conventions.

The explicit naming convention matters more than it looks: SQLite creates
unnamed constraints by default, and Alembic cannot ``DROP CONSTRAINT`` what it
cannot name. Setting it once here keeps future migrations mechanical rather
than hand-written.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Timezone-aware UTC now, used as the default for audit columns."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Re-attach UTC to a datetime read back from SQLite.

    SQLite has no native timestamp type and drops tzinfo on the round trip.
    Every datetime is *written* as UTC, so re-attaching it on read is correct
    and keeps the API from ever emitting a naive timestamp.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class TimestampMixin:
    """Adds a server-independent ``created_at`` audit column."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
