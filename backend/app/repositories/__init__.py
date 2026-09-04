"""Data access. Repositories own SQL; they accept and return domain objects."""

from app.repositories.golden_sets import GoldenSetRepository
from app.repositories.runs import RunRepository

__all__ = ["GoldenSetRepository", "RunRepository"]
