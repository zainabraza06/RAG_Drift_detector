"""FastAPI dependency providers.

The wiring layer. Routes declare the *service* they need and nothing about how
it is built, which keeps handlers thin and makes them trivial to exercise with
a dependency override in tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.connectors.base import VectorStoreConnector
from app.core.config import Settings, get_settings
from app.core.factory import build_scoring_config
from app.db.session import get_session_factory
from app.repositories.golden_sets import GoldenSetRepository
from app.repositories.runs import RunRepository
from app.services.golden_set_service import GoldenSetService
from app.services.run_service import RunService
from app.services.scoring.engine import ScoringEngine


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_db_session() -> Iterator[Session]:
    """One transactional session per request.

    Committing here rather than inside repositories means a handler that
    performs several writes gets all-or-nothing semantics for free.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_db_session)]


def get_vector_store(request: Request) -> VectorStoreConnector:
    """The connector opened once at application startup.

    Held on ``app.state`` so every request reuses one client rather than
    reopening the index per call.
    """
    connector: VectorStoreConnector = request.app.state.vector_store
    return connector


VectorStoreDep = Annotated[VectorStoreConnector, Depends(get_vector_store)]


def get_scoring_engine(
    settings: SettingsDep, vector_store: VectorStoreDep
) -> ScoringEngine:
    return ScoringEngine(vector_store, build_scoring_config(settings))


ScoringEngineDep = Annotated[ScoringEngine, Depends(get_scoring_engine)]


def get_golden_set_service(session: SessionDep) -> GoldenSetService:
    return GoldenSetService(GoldenSetRepository(session))


GoldenSetServiceDep = Annotated[GoldenSetService, Depends(get_golden_set_service)]


def get_run_service(
    session: SessionDep,
    engine: ScoringEngineDep,
    golden_sets: GoldenSetServiceDep,
) -> RunService:
    return RunService(
        engine=engine, runs=RunRepository(session), golden_sets=golden_sets
    )


RunServiceDep = Annotated[RunService, Depends(get_run_service)]
