"""Golden set business logic.

Sits between the API/CLI and the repository. Everything here is a policy
decision rather than storage mechanics: which set a run should use, what
happens when judgements are edited, and how a file import becomes a stored,
versioned artifact.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.errors import GoldenSetError
from app.domain.golden_set import GoldenSet
from app.domain.history import Page, StoredGoldenSet
from app.repositories.golden_sets import DuplicateGoldenSetError, GoldenSetRepository
from app.services.goldenset.loader import load_golden_set

logger = logging.getLogger(__name__)


class GoldenSetNotFoundError(GoldenSetError):
    """The requested golden set does not exist."""


class NoActiveGoldenSetError(GoldenSetError):
    """No golden set is marked active, so there is nothing to evaluate."""


class GoldenSetService:
    """Create, version, activate and retrieve golden sets."""

    def __init__(self, repository: GoldenSetRepository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, golden_set_id: int) -> StoredGoldenSet:
        stored = self._repository.get(golden_set_id)
        if stored is None:
            raise GoldenSetNotFoundError(f"golden set {golden_set_id} not found")
        return stored

    def list_sets(self, *, limit: int = 50, offset: int = 0) -> Page[StoredGoldenSet]:
        return self._repository.list_sets(limit=limit, offset=offset)

    def get_active(self) -> StoredGoldenSet:
        """The golden set runs evaluate by default."""
        active = self._repository.get_active()
        if active is None:
            raise NoActiveGoldenSetError(
                "no active golden set; create one or activate an existing set "
                "before running an evaluation"
            )
        return active

    def resolve(self, golden_set_id: int | None) -> StoredGoldenSet:
        """The set to evaluate: the one asked for, else the active one."""
        return self.get(golden_set_id) if golden_set_id else self.get_active()

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
        """Store a new golden set, optionally making it the active one."""
        return self._repository.create(golden_set, source=source, activate=activate)

    def update_judgements(
        self, golden_set_id: int, golden_set: GoldenSet
    ) -> StoredGoldenSet:
        """Replace a set's queries in place.

        The fingerprint is recomputed from the new judgements, so runs scored
        before and after an edit are automatically excluded from each other's
        drift comparison. That is the intended behaviour: changing the ruler
        must not look like a change in the system being measured.
        """
        existing = self.get(golden_set_id)
        updated = self._repository.replace_queries(golden_set_id, golden_set)
        if updated.fingerprint != existing.fingerprint:
            logger.info(
                "golden set %d judgements changed: %s -> %s; prior runs are no "
                "longer comparable",
                golden_set_id,
                existing.fingerprint,
                updated.fingerprint,
            )
        return updated

    def activate(self, golden_set_id: int) -> StoredGoldenSet:
        self.get(golden_set_id)  # 404 before mutating anything
        return self._repository.activate(golden_set_id)

    def delete(self, golden_set_id: int) -> None:
        """Delete a golden set, keeping the system runnable.

        Deleting the *active* set would otherwise leave the installation
        unable to evaluate anything until someone noticed and activated
        another by hand, so the newest survivor is promoted automatically.
        Runs that used the deleted set keep their own identity snapshot.
        """
        if not self._repository.delete(golden_set_id):
            raise GoldenSetNotFoundError(f"golden set {golden_set_id} not found")

        if self._repository.get_active() is not None:
            return
        survivors = self._repository.list_sets(limit=1)
        if survivors.items:
            promoted = survivors.items[0]
            self._repository.activate(promoted.golden_set_id)
            logger.info(
                "activated golden set %d ('%s' v%s) after the active set was deleted",
                promoted.golden_set_id,
                promoted.golden_set.name,
                promoted.golden_set.version,
            )

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def import_from_file(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        version: str | None = None,
        activate: bool = True,
    ) -> StoredGoldenSet:
        """Load a JSON/CSV golden set from disk and store it."""
        golden_set = load_golden_set(path, name=name, version=version)
        return self.create(golden_set, source="file", activate=activate)

    def import_if_absent(
        self, path: str | Path, *, activate: bool = True
    ) -> StoredGoldenSet | None:
        """Import ``path`` unless that name/version is already stored.

        Used to bootstrap the demo on a fresh database without turning a
        restart into a duplicate-key error.
        """
        try:
            return self.import_from_file(path, activate=activate)
        except DuplicateGoldenSetError:
            logger.debug("golden set from %s already imported; skipping", path)
            return None
