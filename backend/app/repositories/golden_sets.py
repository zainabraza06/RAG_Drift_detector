"""Persistence for golden sets."""

from __future__ import annotations

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import GoldenSetError
from app.db.models import GoldenSetRow
from app.domain.golden_set import GoldenSet
from app.domain.history import Page, StoredGoldenSet
from app.repositories.mappers import golden_set_to_rows, row_to_stored_golden_set

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 200


class DuplicateGoldenSetError(GoldenSetError):
    """A golden set with this name and version already exists."""


class GoldenSetRepository:
    """Reads and writes stored golden sets."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def create(
        self,
        golden_set: GoldenSet,
        *,
        source: str = "api",
        activate: bool = False,
    ) -> StoredGoldenSet:
        """Store a new golden set. ``(name, version)`` must be unique."""
        row = GoldenSetRow(
            name=golden_set.name,
            version=golden_set.version,
            description=golden_set.description,
            fingerprint=golden_set.fingerprint,
            source=source,
            is_active=False,
            queries=golden_set_to_rows(golden_set),
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateGoldenSetError(
                f"golden set '{golden_set.name}' version '{golden_set.version}' "
                "already exists; bump the version to store a revision"
            ) from exc

        if activate:
            self._activate(row)

        logger.info(
            "stored golden set '%s' v%s (%d queries, fingerprint %s)",
            row.name,
            row.version,
            len(golden_set),
            row.fingerprint,
        )
        return row_to_stored_golden_set(row)

    def replace_queries(
        self, golden_set_id: int, golden_set: GoldenSet
    ) -> StoredGoldenSet:
        """Replace a stored set's judgements in place.

        Queries are deleted and rebuilt rather than diffed: a golden set is
        small, and rebuilding guarantees the stored fingerprint always matches
        the stored rows. Editing judgements changes the fingerprint, which is
        exactly what stops drift detection from comparing across the change.
        """
        row = self._row(golden_set_id)
        if row is None:
            raise GoldenSetError(f"golden set {golden_set_id} not found")

        row.description = golden_set.description
        row.fingerprint = golden_set.fingerprint

        # Delete the old children in their own flush before inserting the new
        # ones. In a single flush SQLAlchemy orders INSERTs ahead of the
        # delete-orphan DELETEs, which trips uq_golden_queries_set_query the
        # moment an edit reuses a query_id -- i.e. on almost every real edit.
        row.queries.clear()
        self._session.flush()

        row.queries = golden_set_to_rows(golden_set)
        self._session.flush()
        return row_to_stored_golden_set(row)

    def activate(self, golden_set_id: int) -> StoredGoldenSet:
        """Make this the golden set that runs evaluate by default."""
        row = self._row(golden_set_id)
        if row is None:
            raise GoldenSetError(f"golden set {golden_set_id} not found")
        self._activate(row)
        return row_to_stored_golden_set(row)

    def delete(self, golden_set_id: int) -> bool:
        """Delete a golden set. Runs that used it keep their snapshot."""
        result = self._session.execute(
            delete(GoldenSetRow).where(GoldenSetRow.id == golden_set_id)
        )
        return bool(result.rowcount)

    def _activate(self, row: GoldenSetRow) -> None:
        # Deactivate every other set first: "active" is a singleton, and
        # enforcing it here means no caller can create two.
        self._session.execute(
            update(GoldenSetRow)
            .where(GoldenSetRow.id != row.id)
            .values(is_active=False)
        )
        row.is_active = True
        self._session.flush()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, golden_set_id: int) -> StoredGoldenSet | None:
        row = self._row(golden_set_id)
        return row_to_stored_golden_set(row) if row is not None else None

    def get_by_name(self, name: str, version: str) -> StoredGoldenSet | None:
        row = self._session.scalars(
            select(GoldenSetRow)
            .where(GoldenSetRow.name == name)
            .where(GoldenSetRow.version == version)
        ).one_or_none()
        return row_to_stored_golden_set(row) if row is not None else None

    def get_active(self) -> StoredGoldenSet | None:
        """The golden set runs evaluate by default, if one is set."""
        row = self._session.scalars(
            select(GoldenSetRow).where(GoldenSetRow.is_active.is_(True)).limit(1)
        ).one_or_none()
        return row_to_stored_golden_set(row) if row is not None else None

    def list_sets(self, *, limit: int = 50, offset: int = 0) -> Page[StoredGoldenSet]:
        """A page of golden sets, newest first."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        total = self._session.scalar(select(func.count()).select_from(GoldenSetRow))
        rows = self._session.scalars(
            select(GoldenSetRow)
            .order_by(GoldenSetRow.created_at.desc(), GoldenSetRow.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return Page[StoredGoldenSet](
            items=tuple(row_to_stored_golden_set(row) for row in rows),
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    def count(self) -> int:
        total = self._session.scalar(select(func.count()).select_from(GoldenSetRow))
        return int(total or 0)

    def _row(self, golden_set_id: int) -> GoldenSetRow | None:
        return self._session.get(GoldenSetRow, golden_set_id)
