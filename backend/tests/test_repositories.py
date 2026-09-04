"""Tests for the persistence layer.

Every test here runs against a real SQLite database created by the actual
Alembic migrations, so the schema, its constraints and its cascades are
exercised rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import EvaluationRunRow, GoldenQueryRow, QueryScoreRow, RunMetricRow
from app.domain.golden_set import ExpectedDocument, GoldenQuery, GoldenSet
from app.repositories.golden_sets import DuplicateGoldenSetError, GoldenSetRepository
from app.repositories.runs import RunRepository, UnknownMetricError
from tests.conftest import make_evaluation_result


def _golden_set(name: str = "test-set", version: str = "1") -> GoldenSet:
    return GoldenSet(
        name=name,
        version=version,
        description="a set",
        queries=(
            GoldenQuery(
                query_id="q-a",
                query="alpha query",
                note="first",
                expected_documents=(
                    ExpectedDocument(document_id="doc-1", relevance=3),
                    ExpectedDocument(document_id="doc-2", relevance=1),
                ),
            ),
            GoldenQuery(
                query_id="q-b",
                query="beta query",
                expected_documents=(ExpectedDocument(document_id="doc-3"),),
            ),
        ),
    )


# ----------------------------------------------------------------------
# Run repository
# ----------------------------------------------------------------------
class TestSaveRun:
    def test_round_trips_every_field(self, run_repository: RunRepository) -> None:
        result = make_evaluation_result(recall=0.75, ndcg=0.8, document_count=1234)
        saved = run_repository.save(result, trigger="cli")

        fetched = run_repository.get(saved.run_id)
        assert fetched is not None
        assert fetched.run_id == saved.run_id
        assert fetched.golden_set.fingerprint == "fingerprint-a"
        assert fetched.primary_metrics.recall_at_k == pytest.approx(0.75)
        assert fetched.primary_metrics.ndcg_at_k == pytest.approx(0.8)
        assert fetched.store.document_count == 1234
        assert fetched.store.embedding_model == "fake-embedder-v1"
        assert fetched.trigger == "cli"
        assert fetched.query_count == 2

    def test_stores_metrics_for_every_cutoff(
        self, run_repository: RunRepository, session: Session
    ) -> None:
        run_repository.save(make_evaluation_result(k_values=(1, 3, 5), primary_k=5))
        assert session.scalar(select(func.count()).select_from(RunMetricRow)) == 3

    def test_stores_per_query_detail(self, run_repository: RunRepository) -> None:
        saved = run_repository.save(make_evaluation_result())
        detail = run_repository.get_detail(saved.run_id)

        assert detail is not None
        assert len(detail.query_scores) == 2
        assert [score.query_id for score in detail.query_scores] == ["q1", "q2"]
        assert detail.query_scores[0].retrieved_ids == ("doc-a", "doc-x")
        assert [score.query_id for score in detail.missed_queries] == ["q2"]

    def test_run_ids_are_unique_across_saves(
        self, run_repository: RunRepository
    ) -> None:
        first = run_repository.save(make_evaluation_result())
        second = run_repository.save(make_evaluation_result())
        assert first.run_id != second.run_id

    def test_timestamps_come_back_timezone_aware(
        self, run_repository: RunRepository
    ) -> None:
        # SQLite drops tzinfo; a naive datetime would be read by clients in
        # their own local zone and silently misplace every point on the chart.
        saved = run_repository.save(make_evaluation_result())
        fetched = run_repository.get(saved.run_id)
        assert fetched is not None
        assert fetched.started_at.tzinfo is not None
        assert fetched.finished_at.tzinfo is not None

    def test_missing_run_reads_as_none(self, run_repository: RunRepository) -> None:
        assert run_repository.get("nope") is None
        assert run_repository.get_detail("nope") is None


class TestDeleteRun:
    def test_removes_the_run_and_cascades_to_children(
        self, run_repository: RunRepository, session: Session
    ) -> None:
        saved = run_repository.save(make_evaluation_result())
        assert run_repository.delete(saved.run_id) is True
        session.flush()

        # The cascade only works because session.py enables SQLite's
        # foreign_keys pragma; without it these rows would be orphaned.
        assert session.scalar(select(func.count()).select_from(RunMetricRow)) == 0
        assert session.scalar(select(func.count()).select_from(QueryScoreRow)) == 0
        assert run_repository.get(saved.run_id) is None

    def test_deleting_a_missing_run_reports_false(
        self, run_repository: RunRepository
    ) -> None:
        assert run_repository.delete("nope") is False


class TestListAndFilter:
    @staticmethod
    def _seed(repository: RunRepository) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(5):
            repository.save(
                make_evaluation_result(
                    recall=0.5 + index / 10,
                    started_at=base + timedelta(hours=index),
                    fingerprint="fp-a" if index < 3 else "fp-b",
                )
            )

    def test_returns_newest_first(self, run_repository: RunRepository) -> None:
        self._seed(run_repository)
        page = run_repository.list_runs(limit=10)
        timestamps = [record.started_at for record in page.items]
        assert timestamps == sorted(timestamps, reverse=True)
        assert page.total == 5

    def test_pagination_reports_the_unpaged_total(
        self, run_repository: RunRepository
    ) -> None:
        self._seed(run_repository)
        page = run_repository.list_runs(limit=2, offset=0)
        assert len(page.items) == 2
        assert page.total == 5
        assert page.has_more is True

        last = run_repository.list_runs(limit=2, offset=4)
        assert len(last.items) == 1
        assert last.has_more is False

    def test_limit_is_clamped_rather_than_rejected(
        self, run_repository: RunRepository
    ) -> None:
        self._seed(run_repository)
        assert run_repository.list_runs(limit=10_000).limit == 200
        assert run_repository.list_runs(limit=0).limit == 1

    def test_filters_by_fingerprint(self, run_repository: RunRepository) -> None:
        self._seed(run_repository)
        page = run_repository.list_runs(fingerprint="fp-b")
        assert page.total == 2
        assert {r.golden_set.fingerprint for r in page.items} == {"fp-b"}

    def test_filters_by_since(self, run_repository: RunRepository) -> None:
        self._seed(run_repository)
        cutoff = datetime(2026, 1, 1, 3, tzinfo=UTC)
        assert run_repository.list_runs(since=cutoff).total == 2

    def test_latest_respects_the_fingerprint_scope(
        self, run_repository: RunRepository
    ) -> None:
        self._seed(run_repository)
        assert run_repository.latest() is not None
        scoped = run_repository.latest(fingerprint="fp-a")
        assert scoped is not None
        assert scoped.golden_set.fingerprint == "fp-a"

    def test_latest_on_an_empty_database(
        self, run_repository: RunRepository
    ) -> None:
        assert run_repository.latest() is None

    def test_recent_returns_newest_first_within_a_fingerprint(
        self, run_repository: RunRepository
    ) -> None:
        self._seed(run_repository)
        recent = run_repository.recent(limit=3, fingerprint="fp-a")
        assert len(recent) == 3
        assert recent[0].started_at > recent[-1].started_at

    def test_recent_honours_the_before_cursor(
        self, run_repository: RunRepository
    ) -> None:
        self._seed(run_repository)
        before = datetime(2026, 1, 1, 2, tzinfo=UTC)
        recent = run_repository.recent(limit=10, fingerprint="fp-a", before=before)
        assert all(record.started_at < before for record in recent)


class TestMetricSeries:
    def test_points_are_ordered_oldest_first(
        self, run_repository: RunRepository
    ) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(3):
            run_repository.save(
                make_evaluation_result(
                    recall=0.6 + index / 10, started_at=base + timedelta(hours=index)
                )
            )

        series = run_repository.series(metric="recall_at_k", k=5)
        assert series.metric == "recall_at_k"
        assert [round(point.value, 2) for point in series.points] == [0.6, 0.7, 0.8]
        assert series.latest is not None
        assert series.latest.value == pytest.approx(0.8)

    def test_series_timestamps_are_timezone_aware(
        self, run_repository: RunRepository
    ) -> None:
        run_repository.save(make_evaluation_result())
        series = run_repository.series(metric="ndcg_at_k", k=5)
        assert series.points[0].recorded_at.tzinfo is not None

    def test_series_carries_the_corpus_size_alongside_the_metric(
        self, run_repository: RunRepository
    ) -> None:
        run_repository.save(make_evaluation_result(document_count=4242))
        series = run_repository.series(metric="mrr", k=5)
        assert series.points[0].document_count == 4242

    def test_series_is_scoped_to_the_requested_cutoff(
        self, run_repository: RunRepository
    ) -> None:
        run_repository.save(make_evaluation_result(k_values=(1, 5), primary_k=5))
        assert len(run_repository.series(metric="recall_at_k", k=1).points) == 1
        assert len(run_repository.series(metric="recall_at_k", k=3).points) == 0

    def test_unknown_metric_is_rejected_by_name(
        self, run_repository: RunRepository
    ) -> None:
        with pytest.raises(UnknownMetricError, match="unknown metric 'f1'"):
            run_repository.series(metric="f1", k=5)

    def test_evaluated_cutoffs_are_distinct_and_sorted(
        self, run_repository: RunRepository
    ) -> None:
        run_repository.save(make_evaluation_result(k_values=(1, 5), primary_k=5))
        run_repository.save(make_evaluation_result(k_values=(5, 10), primary_k=5))
        assert run_repository.evaluated_cutoffs() == (1, 5, 10)


# ----------------------------------------------------------------------
# Golden set repository
# ----------------------------------------------------------------------
class TestGoldenSetRepository:
    def test_round_trips_queries_and_graded_relevance(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        stored = golden_set_repository.create(_golden_set())
        fetched = golden_set_repository.get(stored.golden_set_id)

        assert fetched is not None
        assert fetched.query_count == 2
        assert fetched.golden_set.queries[0].query_id == "q-a"
        assert fetched.golden_set.queries[0].relevance_of("doc-1") == 3
        assert fetched.golden_set.queries[0].note == "first"
        # The reconstructed set must hash identically, or history comparisons
        # would silently break on a round trip through the database.
        assert fetched.fingerprint == _golden_set().fingerprint

    def test_author_ordering_is_preserved(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        stored = golden_set_repository.create(_golden_set())
        fetched = golden_set_repository.get(stored.golden_set_id)
        assert fetched is not None
        assert [q.query_id for q in fetched.golden_set.queries] == ["q-a", "q-b"]

    def test_name_and_version_are_unique(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        golden_set_repository.create(_golden_set())
        with pytest.raises(DuplicateGoldenSetError, match="already exists"):
            golden_set_repository.create(_golden_set())

    def test_a_new_version_of_the_same_name_is_allowed(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        golden_set_repository.create(_golden_set(version="1"))
        second = golden_set_repository.create(_golden_set(version="2"))
        assert second.golden_set.version == "2"
        assert golden_set_repository.count() == 2

    def test_activation_is_a_singleton(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        first = golden_set_repository.create(_golden_set(version="1"), activate=True)
        second = golden_set_repository.create(_golden_set(version="2"), activate=True)

        active = golden_set_repository.get_active()
        assert active is not None
        assert active.golden_set_id == second.golden_set_id

        refetched_first = golden_set_repository.get(first.golden_set_id)
        assert refetched_first is not None
        assert refetched_first.is_active is False

    def test_no_active_set_reads_as_none(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        golden_set_repository.create(_golden_set())
        assert golden_set_repository.get_active() is None

    def test_replacing_queries_reuses_ids_without_conflict(
        self, golden_set_repository: GoldenSetRepository, session: Session
    ) -> None:
        stored = golden_set_repository.create(_golden_set())

        # Reuses query_id "q-a" - the case that trips the unique constraint if
        # inserts are ordered ahead of the delete-orphan deletes.
        revised = GoldenSet(
            name="test-set",
            version="1",
            queries=(
                GoldenQuery(
                    query_id="q-a",
                    query="alpha query rewritten",
                    expected_documents=(ExpectedDocument(document_id="doc-9"),),
                ),
            ),
        )
        updated = golden_set_repository.replace_queries(stored.golden_set_id, revised)

        assert updated.query_count == 1
        assert updated.golden_set.queries[0].query == "alpha query rewritten"
        assert session.scalar(select(func.count()).select_from(GoldenQueryRow)) == 1

    def test_editing_judgements_changes_the_fingerprint(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        stored = golden_set_repository.create(_golden_set())
        revised = GoldenSet(
            name="test-set",
            version="1",
            queries=(
                GoldenQuery(
                    query_id="q-a",
                    query="something else entirely",
                    expected_documents=(ExpectedDocument(document_id="doc-1"),),
                ),
            ),
        )
        updated = golden_set_repository.replace_queries(stored.golden_set_id, revised)
        assert updated.fingerprint != stored.fingerprint

    def test_deleting_a_set_leaves_its_runs_intact(
        self,
        golden_set_repository: GoldenSetRepository,
        run_repository: RunRepository,
        session: Session,
    ) -> None:
        stored = golden_set_repository.create(_golden_set())
        saved = run_repository.save(
            make_evaluation_result(), golden_set_id=stored.golden_set_id
        )
        session.flush()

        assert golden_set_repository.delete(stored.golden_set_id) is True
        session.flush()
        session.expire_all()

        # ON DELETE SET NULL: history keeps its own snapshot of the golden set
        # identity, so a deleted ruler cannot erase what it measured.
        surviving = run_repository.get(saved.run_id)
        assert surviving is not None
        assert surviving.golden_set.name == "test-set"
        row = session.scalars(
            select(EvaluationRunRow).where(EvaluationRunRow.run_uuid == saved.run_id)
        ).one()
        assert row.golden_set_id is None

    def test_deleting_a_missing_set_reports_false(
        self, golden_set_repository: GoldenSetRepository
    ) -> None:
        assert golden_set_repository.delete(999) is False
