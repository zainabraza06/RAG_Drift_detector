"""Simulated drift: break the demo index and check the system notices.

These go through the public API end to end. The scenarios only change the
index; the verdicts and diagnoses below are produced by the real scoring
engine, drift detector and rule engine, so they double as a check that each
failure mode is detected and told apart from the other.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.connectors.base import DocumentRecord
from app.services.demo_scenarios import BROKEN_DOCUMENTS, fragment_documents

API = "/api"


@pytest.fixture(autouse=True)
def _demo_controls_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIFT_DEMO_CONTROLS", "true")


def _run(client: TestClient) -> dict[str, Any]:
    run = client.post(f"{API}/runs", json={}).json()
    drift: dict[str, Any] = client.get(f"{API}/runs/{run['run_id']}/drift").json()
    return drift


def _with_baseline(client: TestClient) -> None:
    for _ in range(3):
        _run(client)


def _rules(drift: dict[str, Any]) -> list[str]:
    return [finding["rule_id"] for finding in drift["diagnostics"]["findings"]]


class TestState:
    def test_a_fresh_index_is_healthy(self, api_client: TestClient) -> None:
        state = api_client.get(f"{API}/demo").json()
        assert state == {
            "enabled": True,
            "document_count": 32,
            "corpus_size": 32,
            "missing_documents": 0,
            "fragment_documents": 0,
            "healthy": True,
        }

    def test_unknown_scenarios_are_rejected(self, api_client: TestClient) -> None:
        response = api_client.post(f"{API}/demo/scenarios/drop-table")
        assert response.status_code == 422


class TestDeletedDocuments:
    def test_is_detected_as_missing_content(self, api_client: TestClient) -> None:
        _with_baseline(api_client)

        state = api_client.post(f"{API}/demo/scenarios/delete-documents").json()
        assert state["missing_documents"] == len(BROKEN_DOCUMENTS)

        drift = _run(api_client)
        assert drift["verdict"] == "degraded"
        assert _rules(drift)[0] == "missing_expected_documents"
        assert "expected_documents_demoted" in drift["diagnostics"]["checks_passed"]


class TestRechunk:
    def test_is_detected_as_a_ranking_problem(self, api_client: TestClient) -> None:
        _with_baseline(api_client)

        state = api_client.post(f"{API}/demo/scenarios/rechunk").json()
        assert state["missing_documents"] == 0
        assert state["fragment_documents"] > 0

        drift = _run(api_client)
        assert drift["verdict"] == "degraded"
        # Nothing was deleted, so the diagnosis must be demotion, and missing
        # content must be ruled out rather than guessed at.
        assert _rules(drift)[0] == "expected_documents_demoted"
        assert "missing_expected_documents" in drift["diagnostics"]["checks_passed"]


class TestRestore:
    def test_undoes_both_scenarios_and_reads_as_improvement(
        self, api_client: TestClient
    ) -> None:
        _with_baseline(api_client)
        api_client.post(f"{API}/demo/scenarios/delete-documents")
        api_client.post(f"{API}/demo/scenarios/rechunk")
        _run(api_client)

        state = api_client.post(f"{API}/demo/scenarios/restore").json()
        assert state["healthy"] is True
        assert state["document_count"] == 32

        assert _run(api_client)["verdict"] == "improved"


def test_fragments_never_reuse_an_original_id() -> None:
    document = DocumentRecord(
        document_id="doc-1", content="First sentence. Second one! Third?"
    )
    fragments = fragment_documents([document])
    assert [f.document_id for f in fragments] == [
        "doc-1::chunk-1",
        "doc-1::chunk-2",
        "doc-1::chunk-3",
    ]
    assert fragments[0].metadata["fragment_of"] == "doc-1"
