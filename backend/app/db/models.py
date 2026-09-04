"""ORM models for run history and stored golden sets.

Two design choices are worth calling out.

**Golden sets are stored relationally, not as a JSON blob.** Queries and their
expected documents are real rows, so the dashboard's golden set editor can add
or edit a single pair without rewriting the whole set, and so a future
diagnostic can join golden judgements against run results in SQL.

**Run rows denormalise the golden set identity they were scored against.** A
run keeps ``golden_set_name``/``version``/``fingerprint`` as plain columns in
addition to the foreign key. History must remain truthful even if the golden
set is later edited or deleted -- a metric is only meaningful next to the
ruler that produced it, and that ruler must not be able to change retroactively.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ----------------------------------------------------------------------
# Golden sets
# ----------------------------------------------------------------------


class GoldenSetRow(TimestampMixin, Base):
    """A stored, versioned golden set."""

    __tablename__ = "golden_sets"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_golden_sets_name_version"),
        Index("ix_golden_sets_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Content hash of the judgements; see GoldenSet.fingerprint.
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Exactly one golden set is the one scheduled runs evaluate.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Where it came from: "file" (imported) or "api" (edited in the UI).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="api")

    queries: Mapped[list[GoldenQueryRow]] = relationship(
        back_populates="golden_set",
        cascade="all, delete-orphan",
        order_by="GoldenQueryRow.position",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GoldenSetRow {self.name} v{self.version} ({self.fingerprint})>"


class GoldenQueryRow(Base):
    """One query within a golden set."""

    __tablename__ = "golden_queries"
    __table_args__ = (
        UniqueConstraint(
            "golden_set_id", "query_id", name="uq_golden_queries_set_query"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    golden_set_id: Mapped[int] = mapped_column(
        ForeignKey("golden_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_id: Mapped[str] = mapped_column(String(200), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Preserves author ordering, which is how the set reads in the editor.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    golden_set: Mapped[GoldenSetRow] = relationship(back_populates="queries")
    expected_documents: Mapped[list[ExpectedDocumentRow]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        order_by="ExpectedDocumentRow.id",
        lazy="selectin",
    )


class ExpectedDocumentRow(Base):
    """A document a golden query is expected to retrieve."""

    __tablename__ = "golden_expected_documents"
    __table_args__ = (
        UniqueConstraint(
            "golden_query_id", "document_id", name="uq_expected_documents_query_doc"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    golden_query_id: Mapped[int] = mapped_column(
        ForeignKey("golden_queries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(String(400), nullable=False)
    relevance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    query: Mapped[GoldenQueryRow] = relationship(back_populates="expected_documents")


# ----------------------------------------------------------------------
# Evaluation runs
# ----------------------------------------------------------------------


class EvaluationRunRow(TimestampMixin, Base):
    """One completed scoring run."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        # The drift detector's hot path: "the last N runs scored against this
        # exact golden set, newest first".
        Index(
            "ix_evaluation_runs_fingerprint_started",
            "golden_set_fingerprint",
            "started_at",
        ),
        Index("ix_evaluation_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Stable public identifier; the integer primary key never leaves the DB.
    run_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )

    golden_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("golden_sets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalised so history stays truthful if the golden set is edited or
    # deleted later. See the module docstring.
    golden_set_name: Mapped[str] = mapped_column(String(200), nullable=False)
    golden_set_version: Mapped[str] = mapped_column(String(50), nullable=False)
    golden_set_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)

    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_k: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # Index snapshot at run time - the raw material for root-cause diagnostics.
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    collection: Mapped[str] = mapped_column(String(200), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    store_extra: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    #: How the run was started: "api", "cli" or "scheduled".
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="api")

    golden_set: Mapped[GoldenSetRow | None] = relationship()
    metrics: Mapped[list[RunMetricRow]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunMetricRow.k",
        lazy="selectin",
    )
    query_scores: Mapped[list[QueryScoreRow]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="QueryScoreRow.id",
        # Lazily loaded: a run's per-query detail is large and only the
        # detail view needs it, so list endpoints never pay for it.
        lazy="select",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EvaluationRunRow {self.run_uuid} {self.golden_set_name}>"


class RunMetricRow(Base):
    """Aggregated metrics for one run at one cutoff ``k``."""

    __tablename__ = "run_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "k", name="uq_run_metrics_run_k"),
        # Serves the trend chart: one metric, one cutoff, ordered by run.
        Index("ix_run_metrics_k_run", "k", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recall_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    precision_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    mrr: Mapped[float] = mapped_column(Float, nullable=False)
    ndcg_at_k: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped[EvaluationRunRow] = relationship(back_populates="metrics")


class QueryScoreRow(Base):
    """Per-query detail for one run at its primary cutoff."""

    __tablename__ = "run_query_scores"
    __table_args__ = (
        UniqueConstraint("run_id", "query_id", name="uq_query_scores_run_query"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_id: Mapped[str] = mapped_column(String(200), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False)
    recall_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    precision_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    reciprocal_rank: Mapped[float] = mapped_column(Float, nullable=False)
    ndcg_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    first_relevant_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    relevant_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    run: Mapped[EvaluationRunRow] = relationship(back_populates="query_scores")


# ----------------------------------------------------------------------
# Drift events
# ----------------------------------------------------------------------


class DriftEventRow(TimestampMixin, Base):
    """A stored drift assessment for one run.

    The per-metric comparisons are held as JSON rather than as child rows.
    They are written once and always read as a whole -- nothing filters or
    aggregates on an individual confidence bound -- so normalising them would
    buy query flexibility nobody needs at the cost of a join on every read.
    The columns that *are* filtered on (verdict, fingerprint, timestamp) are
    real, indexed columns.
    """

    __tablename__ = "drift_events"
    __table_args__ = (
        # One current assessment per run; re-assessing replaces it.
        UniqueConstraint("run_id", name="uq_drift_events_run"),
        Index("ix_drift_events_verdict_detected", "verdict", "detected_at"),
        Index("ix_drift_events_detected_at", "detected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )

    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    golden_set_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False)

    baseline_run_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    comparisons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    hit_rate: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    #: Heuristic root-cause report. Nullable because events written before
    #: diagnostics existed have none, and because a report is optional by
    #: design -- a verdict stands on its own without an explanation.
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    run: Mapped[EvaluationRunRow] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DriftEventRow {self.event_uuid} {self.verdict}>"
