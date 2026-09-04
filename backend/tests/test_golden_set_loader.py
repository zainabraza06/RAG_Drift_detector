"""Tests for golden set parsing.

A silently mis-parsed golden set produces a plausible-looking but wrong
quality number, so the error paths get as much attention as the happy ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import GoldenSetError
from app.domain.golden_set import ExpectedDocument, GoldenQuery, GoldenSet
from app.services.goldenset.loader import (
    load_golden_set,
    parse_csv_golden_set,
    parse_json_golden_set,
    to_json_payload,
)


class TestParseJson:
    def test_full_object_with_graded_relevance(self) -> None:
        raw = json.dumps(
            {
                "name": "support",
                "version": "3",
                "description": "docs",
                "queries": [
                    {
                        "query_id": "q-a",
                        "query": "how do I reset my password",
                        "expected_documents": [
                            {"document_id": "doc-1", "relevance": 3},
                            {"document_id": "doc-2", "relevance": 1},
                        ],
                        "note": "graded",
                    }
                ],
            }
        )
        golden_set = parse_json_golden_set(raw)

        assert golden_set.name == "support"
        assert golden_set.version == "3"
        assert len(golden_set) == 1
        query = golden_set.queries[0]
        assert query.query_id == "q-a"
        assert query.relevance_of("doc-1") == 3
        assert query.relevance_of("missing") == 0
        assert query.note == "graded"

    def test_singular_and_plural_id_shorthands(self) -> None:
        raw = json.dumps(
            [
                {"query": "one", "expected_document_id": "doc-1"},
                {"query": "two", "expected_document_ids": ["doc-2", "doc-3"]},
                {"query": "three", "expected_documents": ["doc-4"]},
            ]
        )
        golden_set = parse_json_golden_set(raw)
        assert [len(q.expected_documents) for q in golden_set.queries] == [1, 2, 1]
        # Ids default to binary relevance.
        assert golden_set.queries[0].expected_documents[0].relevance == 1

    def test_query_ids_are_generated_when_absent(self) -> None:
        golden_set = parse_json_golden_set(
            json.dumps([{"query": "one", "expected_document_id": "doc-1"}])
        )
        assert golden_set.queries[0].query_id == "q1"

    def test_invalid_json_names_the_problem(self) -> None:
        with pytest.raises(GoldenSetError, match="invalid JSON"):
            parse_json_golden_set("{not json")

    def test_missing_queries_list(self) -> None:
        with pytest.raises(GoldenSetError, match="non-empty 'queries' list"):
            parse_json_golden_set(json.dumps({"name": "x"}))

    def test_missing_query_text_points_at_the_index(self) -> None:
        raw = json.dumps([{"expected_document_id": "doc-1"}])
        with pytest.raises(GoldenSetError, match=r"queries\[0\] is missing"):
            parse_json_golden_set(raw)

    def test_query_with_no_expected_documents_is_rejected(self) -> None:
        raw = json.dumps([{"query": "orphan"}])
        with pytest.raises(GoldenSetError, match="at least one expected document"):
            parse_json_golden_set(raw)

    def test_duplicate_document_ids_within_a_query_are_rejected(self) -> None:
        raw = json.dumps(
            [{"query": "dupe", "expected_document_ids": ["doc-1", "doc-1"]}]
        )
        with pytest.raises(GoldenSetError, match="duplicate document ids"):
            parse_json_golden_set(raw)

    def test_out_of_range_relevance_is_rejected(self) -> None:
        raw = json.dumps(
            [
                {
                    "query": "graded",
                    "expected_documents": [{"document_id": "d1", "relevance": 99}],
                }
            ]
        )
        with pytest.raises(GoldenSetError, match="invalid relevance"):
            parse_json_golden_set(raw)


class TestParseCsv:
    def test_rows_are_grouped_into_multi_document_queries(self) -> None:
        raw = (
            "query_id,query,expected_document_id,relevance\n"
            "q-a,reset password,doc-1,3\n"
            "q-a,reset password,doc-2,1\n"
            "q-b,change plan,doc-3,\n"
        )
        golden_set = parse_csv_golden_set(raw)

        assert len(golden_set) == 2
        first = golden_set.queries[0]
        assert first.query_id == "q-a"
        assert [d.document_id for d in first.expected_documents] == ["doc-1", "doc-2"]
        assert first.relevance_of("doc-1") == 3
        # Blank relevance falls back to binary.
        assert golden_set.queries[1].relevance_of("doc-3") == 1

    def test_header_aliases_are_accepted(self) -> None:
        raw = "question,doc_id\nreset password,doc-1\n"
        golden_set = parse_csv_golden_set(raw)
        assert golden_set.queries[0].query == "reset password"
        assert golden_set.queries[0].expected_documents[0].document_id == "doc-1"

    def test_blank_rows_are_skipped(self) -> None:
        raw = "query,expected_document_id\nalpha,doc-1\n,\nbeta,doc-2\n"
        assert len(parse_csv_golden_set(raw)) == 2

    def test_missing_required_column_is_reported(self) -> None:
        with pytest.raises(GoldenSetError, match="missing required column"):
            parse_csv_golden_set("query,note\nalpha,hi\n")

    def test_row_number_is_included_in_errors(self) -> None:
        raw = "query,expected_document_id\nalpha,doc-1\nbeta,\n"
        with pytest.raises(GoldenSetError, match="row 3: missing expected document"):
            parse_csv_golden_set(raw)

    def test_reused_query_id_with_different_text_is_rejected(self) -> None:
        raw = (
            "query_id,query,expected_document_id\n"
            "q-a,alpha,doc-1\n"
            "q-a,beta,doc-2\n"
        )
        with pytest.raises(GoldenSetError, match="reused with different"):
            parse_csv_golden_set(raw)

    def test_non_numeric_relevance_is_reported(self) -> None:
        raw = "query,expected_document_id,relevance\nalpha,doc-1,high\n"
        with pytest.raises(GoldenSetError, match="is not a number"):
            parse_csv_golden_set(raw)


class TestLoadFromDisk:
    def test_dispatches_on_extension(self, tmp_path: Path) -> None:
        json_path = tmp_path / "set.json"
        json_path.write_text(
            json.dumps([{"query": "alpha", "expected_document_id": "doc-1"}]),
            encoding="utf-8",
        )
        csv_path = tmp_path / "set.csv"
        csv_path.write_text("query,expected_document_id\nalpha,doc-1\n", encoding="utf-8")

        assert len(load_golden_set(json_path)) == 1
        assert len(load_golden_set(csv_path)) == 1

    def test_name_defaults_to_the_filename(self, tmp_path: Path) -> None:
        path = tmp_path / "my-eval-set.csv"
        path.write_text("query,expected_document_id\nalpha,doc-1\n", encoding="utf-8")
        assert load_golden_set(path).name == "my-eval-set"

    def test_name_and_version_can_be_overridden(self, tmp_path: Path) -> None:
        path = tmp_path / "set.csv"
        path.write_text("query,expected_document_id\nalpha,doc-1\n", encoding="utf-8")
        golden_set = load_golden_set(path, name="renamed", version="7")
        assert (golden_set.name, golden_set.version) == ("renamed", "7")

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(GoldenSetError, match="not found"):
            load_golden_set(tmp_path / "nope.json")

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "set.yaml"
        path.write_text("queries: []", encoding="utf-8")
        with pytest.raises(GoldenSetError, match="unsupported golden set format"):
            load_golden_set(path)

    def test_bundled_demo_golden_set_loads(self) -> None:
        from app.core.config import get_settings

        golden_set = load_golden_set(get_settings().demo_golden_set_path)
        assert len(golden_set) >= 20
        assert golden_set.all_expected_document_ids


class TestFingerprint:
    def _set(self, relevance: int = 1, query_text: str = "alpha") -> GoldenSet:
        return GoldenSet(
            name="n",
            version="1",
            queries=(
                GoldenQuery(
                    query_id="q1",
                    query=query_text,
                    expected_documents=(
                        ExpectedDocument(document_id="doc-1", relevance=relevance),
                    ),
                ),
            ),
        )

    def test_is_stable_across_identical_content(self) -> None:
        assert self._set().fingerprint == self._set().fingerprint

    def test_ignores_metadata_but_tracks_judgements(self) -> None:
        renamed = self._set().model_copy(update={"name": "other", "version": "9"})
        assert renamed.fingerprint == self._set().fingerprint
        assert self._set(relevance=3).fingerprint != self._set().fingerprint
        assert self._set(query_text="beta").fingerprint != self._set().fingerprint


class TestRoundTrip:
    def test_json_payload_reparses_to_an_equivalent_set(self) -> None:
        original = parse_json_golden_set(
            json.dumps(
                {
                    "name": "support",
                    "version": "2",
                    "queries": [
                        {
                            "query_id": "q-a",
                            "query": "alpha",
                            "expected_documents": [
                                {"document_id": "doc-1", "relevance": 3}
                            ],
                            "note": "keep me",
                        }
                    ],
                }
            )
        )
        reparsed = parse_json_golden_set(json.dumps(to_json_payload(original)))
        assert reparsed.fingerprint == original.fingerprint
        assert reparsed.queries[0].note == "keep me"
