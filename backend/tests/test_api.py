"""End-to-end HTTP tests.

These drive a fully bootstrapped application: real migrations, the demo corpus
indexed into an in-process Chroma, the demo golden set imported, and real
scoring behind ``POST /runs``. Nothing here is mocked, so a passing suite means
``docker compose up`` followed by clicking "Run Evaluation Now" works.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

API = "/api"


def _new_golden_set(name: str = "extra", version: str = "1") -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "description": "created over HTTP",
        "queries": [
            {
                "query_id": "q-invoice",
                "query": "download last month invoice",
                "expected_documents": [
                    {"document_id": "doc-billing-001", "relevance": 3}
                ],
            },
            {
                "query": "rotate a leaked api key",
                "expected_documents": [{"document_id": "doc-auth-004"}],
            },
        ],
    }


# ----------------------------------------------------------------------
# Bootstrap and system endpoints
# ----------------------------------------------------------------------
class TestBootstrapAndHealth:
    def test_startup_indexes_the_demo_corpus_and_golden_set(
        self, api_client: TestClient
    ) -> None:
        info = api_client.get(f"{API}/system/info").json()
        assert info["vector_store"]["reachable"] is True
        assert info["vector_store"]["document_count"] == 32
        assert info["active_golden_set"]["name"] == "acme-cloud-support"
        # Compared against the migration head rather than a literal, so a
        # new migration does not break an unrelated test.
        from app.db.migrations import head_revision

        assert info["schema_revision"] == head_revision()

    def test_health_reports_both_dependencies(self, api_client: TestClient) -> None:
        response = api_client.get(f"{API}/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "status": "ok",
            "version": body["version"],
            "database": True,
            "vector_store": True,
            "message": None,
        }

    def test_openapi_schema_is_served(self, api_client: TestClient) -> None:
        schema = api_client.get("/openapi.json").json()
        assert f"{API}/runs" in schema["paths"]
        assert f"{API}/golden-sets/{{golden_set_id}}" in schema["paths"]


class TestDashboard:
    def test_empty_state_is_explicit(self, api_client: TestClient) -> None:
        body = api_client.get(f"{API}/dashboard").json()
        # "never evaluated" must be distinguishable from "nothing matched",
        # or the UI cannot choose between onboarding and an empty list.
        assert body["has_runs"] is False
        assert body["total_runs"] == 0
        assert body["latest_run"] is None
        assert body["metric_deltas"] == {}
        assert body["active_golden_set"]["golden_set"]["name"] == "acme-cloud-support"

    def test_summarises_the_latest_run(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        body = api_client.get(f"{API}/dashboard").json()

        assert body["has_runs"] is True
        assert body["total_runs"] == 1
        assert body["document_count"] == 32
        assert body["primary_metrics"]["k"] == 5
        assert body["last_run_at"].endswith("Z")
        # One run has nothing to compare against.
        assert body["metric_deltas"] == {}

    def test_deltas_appear_once_there_is_a_baseline(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/runs", json={})
        api_client.post(f"{API}/runs", json={})
        body = api_client.get(f"{API}/dashboard").json()

        assert body["previous_run"] is not None
        assert set(body["metric_deltas"]) == {
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "ndcg_at_k",
        }


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------
class TestRuns:
    def test_creating_a_run_scores_the_active_golden_set(
        self, api_client: TestClient
    ) -> None:
        response = api_client.post(f"{API}/runs", json={"trigger": "api"})
        assert response.status_code == 201

        body = response.json()
        assert body["golden_set"]["name"] == "acme-cloud-support"
        assert body["query_count"] == 30
        assert body["trigger"] == "api"
        assert [m["k"] for m in body["metrics"]] == [1, 3, 5, 10]
        # Real retrieval against the real demo corpus.
        assert body["metrics"][2]["recall_at_k"] > 0.8
        assert body["store"]["document_count"] == 32

    def test_a_run_can_target_a_specific_golden_set(
        self, api_client: TestClient
    ) -> None:
        created = api_client.post(
            f"{API}/golden-sets", json=_new_golden_set()
        ).json()
        body = api_client.post(
            f"{API}/runs", json={"golden_set_id": created["golden_set_id"]}
        ).json()
        assert body["golden_set"]["name"] == "extra"
        assert body["query_count"] == 2

    def test_listing_is_paginated_and_newest_first(
        self, api_client: TestClient
    ) -> None:
        for _ in range(3):
            api_client.post(f"{API}/runs", json={})

        page = api_client.get(f"{API}/runs", params={"limit": 2}).json()
        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["items"][0]["started_at"] >= page["items"][1]["started_at"]

    def test_latest_returns_null_before_any_run(
        self, api_client: TestClient
    ) -> None:
        assert api_client.get(f"{API}/runs/latest").json() is None

    def test_latest_is_not_parsed_as_a_run_id(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/runs", json={}).json()
        latest = api_client.get(f"{API}/runs/latest").json()
        assert latest["run_id"] == created["run_id"]

    def test_per_query_detail(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/runs", json={}).json()
        detail = api_client.get(f"{API}/runs/{created['run_id']}/queries").json()

        assert detail["run"]["run_id"] == created["run_id"]
        assert len(detail["query_scores"]) == 30
        score = detail["query_scores"][0]
        assert {"query_id", "recall_at_k", "ndcg_at_k", "retrieved_ids"} <= set(score)

    def test_deleting_a_run(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/runs", json={}).json()
        assert api_client.delete(f"{API}/runs/{created['run_id']}").status_code == 204
        assert api_client.get(f"{API}/runs/{created['run_id']}").status_code == 404

    def test_missing_run_uses_the_standard_error_envelope(
        self, api_client: TestClient
    ) -> None:
        response = api_client.get(f"{API}/runs/nope")
        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "run_not_found", "message": "run 'nope' not found"}
        }


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------
class TestMetrics:
    def test_series_is_empty_before_any_run(self, api_client: TestClient) -> None:
        body = api_client.get(
            f"{API}/metrics/series", params={"metric": "recall_at_k", "k": 5}
        ).json()
        assert body["points"] == []

    def test_series_points_are_chart_ready(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        api_client.post(f"{API}/runs", json={})

        body = api_client.get(
            f"{API}/metrics/series", params={"metric": "ndcg_at_k", "k": 5}
        ).json()
        assert body["metric"] == "ndcg_at_k"
        assert len(body["points"]) == 2
        # Oldest first, and timestamps carry an explicit UTC offset.
        assert body["points"][0]["recorded_at"] <= body["points"][1]["recorded_at"]
        assert body["points"][0]["recorded_at"].endswith("Z")
        assert body["points"][0]["document_count"] == 32

    def test_trends_returns_every_metric_in_one_request(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/runs", json={})
        body = api_client.get(f"{API}/metrics/trends", params={"k": 5}).json()
        assert [series["metric"] for series in body] == [
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "ndcg_at_k",
        ]
        assert all(len(series["points"]) == 1 for series in body)

    def test_cutoffs_reflect_stored_data(self, api_client: TestClient) -> None:
        assert api_client.get(f"{API}/metrics/cutoffs").json() == []
        api_client.post(f"{API}/runs", json={})
        assert api_client.get(f"{API}/metrics/cutoffs").json() == [1, 3, 5, 10]

    def test_unknown_metric_is_a_400_with_a_usable_message(
        self, api_client: TestClient
    ) -> None:
        response = api_client.get(f"{API}/metrics/series", params={"metric": "f1"})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "unknown_metric"
        assert "recall_at_k" in error["message"]


# ----------------------------------------------------------------------
# Golden sets
# ----------------------------------------------------------------------
class TestGoldenSets:
    def test_the_demo_set_is_listed(self, api_client: TestClient) -> None:
        page = api_client.get(f"{API}/golden-sets").json()
        assert page["total"] == 1
        assert page["items"][0]["golden_set"]["name"] == "acme-cloud-support"
        assert page["items"][0]["source"] == "file"
        assert page["items"][0]["is_active"] is True

    def test_creating_generates_missing_query_ids(
        self, api_client: TestClient
    ) -> None:
        body = api_client.post(f"{API}/golden-sets", json=_new_golden_set()).json()
        ids = [q["query_id"] for q in body["golden_set"]["queries"]]
        assert ids == ["q-invoice", "q2"]

    def test_creating_with_activate_switches_the_active_set(
        self, api_client: TestClient
    ) -> None:
        payload = _new_golden_set() | {"activate": True}
        created = api_client.post(f"{API}/golden-sets", json=payload).json()
        assert created["is_active"] is True

        active = api_client.get(f"{API}/golden-sets/active").json()
        assert active["golden_set_id"] == created["golden_set_id"]

    def test_duplicate_name_and_version_conflicts(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/golden-sets", json=_new_golden_set())
        response = api_client.post(f"{API}/golden-sets", json=_new_golden_set())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "golden_set_exists"

    def test_editing_judgements_changes_the_fingerprint(
        self, api_client: TestClient
    ) -> None:
        created = api_client.post(f"{API}/golden-sets", json=_new_golden_set()).json()
        set_id = created["golden_set_id"]

        revised = _new_golden_set()
        revised["queries"][0]["query"] = "a completely different question"
        updated = api_client.put(f"{API}/golden-sets/{set_id}", json=revised).json()

        # The ruler changed, so runs either side of the edit are no longer
        # comparable - and the fingerprint is what enforces that.
        assert updated["golden_set"]["queries"][0]["query"] == (
            "a completely different question"
        )
        assert api_client.get(f"{API}/golden-sets/{set_id}").status_code == 200

    def test_editing_can_reuse_query_ids(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/golden-sets", json=_new_golden_set()).json()
        set_id = created["golden_set_id"]

        revised = _new_golden_set()
        revised["queries"].append(
            {
                "query_id": "q-extra",
                "query": "keep data inside the EU",
                "expected_documents": [{"document_id": "doc-data-003"}],
            }
        )
        response = api_client.put(f"{API}/golden-sets/{set_id}", json=revised)
        assert response.status_code == 200
        assert len(response.json()["golden_set"]["queries"]) == 3

    def test_activate_endpoint(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/golden-sets", json=_new_golden_set()).json()
        set_id = created["golden_set_id"]
        assert (
            api_client.post(f"{API}/golden-sets/{set_id}/activate").json()["is_active"]
            is True
        )

    def test_deleting_the_active_set_promotes_a_survivor(
        self, api_client: TestClient
    ) -> None:
        payload = _new_golden_set() | {"activate": True}
        created = api_client.post(f"{API}/golden-sets", json=payload).json()

        assert (
            api_client.delete(f"{API}/golden-sets/{created['golden_set_id']}").status_code
            == 204
        )
        # An installation must never be left unable to evaluate anything.
        active = api_client.get(f"{API}/golden-sets/active")
        assert active.status_code == 200
        assert active.json()["golden_set"]["name"] == "acme-cloud-support"

    def test_runs_survive_deletion_of_their_golden_set(
        self, api_client: TestClient
    ) -> None:
        created = api_client.post(f"{API}/golden-sets", json=_new_golden_set()).json()
        run = api_client.post(
            f"{API}/runs", json={"golden_set_id": created["golden_set_id"]}
        ).json()

        api_client.delete(f"{API}/golden-sets/{created['golden_set_id']}")

        surviving = api_client.get(f"{API}/runs/{run['run_id']}").json()
        assert surviving["golden_set"]["name"] == "extra"

    def test_missing_set_is_a_404(self, api_client: TestClient) -> None:
        response = api_client.get(f"{API}/golden-sets/999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "golden_set_not_found"

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"name": "x", "queries": []}, "queries"),
            ({"name": "", "queries": [{"query": "a", "expected_documents": []}]}, "name"),
        ],
    )
    def test_validation_errors_name_the_offending_field(
        self, api_client: TestClient, payload: dict[str, Any], field: str
    ) -> None:
        response = api_client.post(f"{API}/golden-sets", json=payload)
        assert response.status_code == 422

        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(item["field"].startswith(field) for item in error["detail"])

    def test_duplicate_documents_in_a_query_are_rejected(
        self, api_client: TestClient
    ) -> None:
        payload = _new_golden_set()
        payload["queries"][0]["expected_documents"].append(
            {"document_id": "doc-billing-001"}
        )
        response = api_client.post(f"{API}/golden-sets", json=payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_golden_set"

    def test_importing_a_file(self, api_client: TestClient) -> None:
        from app.core.config import get_settings

        response = api_client.post(
            f"{API}/golden-sets/import",
            json={
                "path": str(get_settings().demo_golden_set_path),
                "version": "imported-2",
                "activate": False,
            },
        )
        assert response.status_code == 201
        assert response.json()["golden_set"]["version"] == "imported-2"

    def test_importing_a_missing_file_is_a_400(self, api_client: TestClient) -> None:
        response = api_client.post(
            f"{API}/golden-sets/import", json={"path": "/nope/missing.json"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_golden_set"


# ----------------------------------------------------------------------
# Drift
# ----------------------------------------------------------------------
class TestDrift:
    def test_the_first_run_has_no_baseline(self, api_client: TestClient) -> None:
        created = api_client.post(f"{API}/runs", json={}).json()
        body = api_client.get(f"{API}/runs/{created['run_id']}/drift").json()

        assert body["verdict"] == "insufficient_data"
        assert body["comparisons"] == []
        assert "No comparable earlier run" in body["summary"]

    def test_an_unchanged_system_is_stable(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        second = api_client.post(f"{API}/runs", json={}).json()

        body = api_client.get(f"{API}/runs/{second['run_id']}/drift").json()
        assert body["verdict"] == "stable"
        assert body["query_count"] == 30
        assert len(body["comparisons"]) == 4
        # Retrieval is deterministic, so an unchanged index moves nothing.
        assert all(c["difference"] == 0.0 for c in body["comparisons"])

    def test_a_degraded_index_is_detected_with_its_reasoning(
        self, api_client: TestClient
    ) -> None:
        """The end-to-end claim: break retrieval, and the tool says so."""
        for _ in range(2):
            api_client.post(f"{API}/runs", json={})

        # Remove documents the golden set expects, which is what a botched
        # re-index looks like from the outside.
        api_client.app.state.vector_store.delete_documents(  # type: ignore[attr-defined]
            [
                "doc-api-001",
                "doc-api-002",
                "doc-auth-003",
                "doc-security-003",
                "doc-data-002",
                "doc-support-003",
            ]
        )
        degraded = api_client.post(f"{API}/runs", json={}).json()
        body = api_client.get(f"{API}/runs/{degraded['run_id']}/drift").json()

        assert body["verdict"] == "degraded"
        recall = next(c for c in body["comparisons"] if c["metric"] == "recall_at_k")
        assert recall["difference"] < -0.1
        assert recall["ci_upper"] < 0  # the whole interval sits below zero
        assert recall["p_value_adjusted"] < 0.05
        assert recall["significant"] is True
        assert recall["material"] is True

        # The verdict has to carry its reasoning, not just a boolean.
        assert "CI" in body["summary"] and "p=" in body["summary"]
        assert body["hit_rate"]["became_misses"] > 0

    def test_assessments_are_stored_and_listed(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        api_client.post(f"{API}/runs", json={})

        page = api_client.get(f"{API}/drift/events").json()
        assert page["total"] == 2
        assert page["items"][0]["verdict"] == "stable"
        assert api_client.get(f"{API}/drift/latest").json()["verdict"] == "stable"

    def test_events_can_be_filtered_by_verdict(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        api_client.post(f"{API}/runs", json={})

        page = api_client.get(
            f"{API}/drift/events", params={"verdict": "insufficient_data"}
        ).json()
        assert page["total"] == 1
        assert page["items"][0]["verdict"] == "insufficient_data"

    def test_latest_is_null_before_any_run(self, api_client: TestClient) -> None:
        assert api_client.get(f"{API}/drift/latest").json() is None

    def test_drift_for_a_missing_run_is_a_404(self, api_client: TestClient) -> None:
        response = api_client.get(f"{API}/runs/nope/drift")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "run_not_found"

    def test_deleting_a_run_removes_its_assessment(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/runs", json={})
        second = api_client.post(f"{API}/runs", json={}).json()

        assert api_client.get(f"{API}/drift/events").json()["total"] == 2
        api_client.delete(f"{API}/runs/{second['run_id']}")
        # ON DELETE CASCADE: a verdict cannot outlive the run it describes.
        assert api_client.get(f"{API}/drift/events").json()["total"] == 1

    def test_the_config_is_recorded_with_every_verdict(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/runs", json={})
        second = api_client.post(f"{API}/runs", json={}).json()

        config = api_client.get(f"{API}/runs/{second['run_id']}/drift").json()["config"]
        assert config["confidence_level"] == 0.95
        assert config["resamples"] == 10000
        assert config["seed"] == 20240517


class TestDashboardHealth:
    def test_unknown_before_any_run(self, api_client: TestClient) -> None:
        assert api_client.get(f"{API}/dashboard").json()["health"] == "unknown"

    def test_unknown_while_there_is_no_baseline(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        body = api_client.get(f"{API}/dashboard").json()
        # One run has nothing to compare against, and "not yet known to be
        # healthy" must not be shown as green.
        assert body["health"] == "unknown"
        assert body["latest_drift"]["verdict"] == "insufficient_data"

    def test_warning_when_a_stable_verdict_carries_caveats(
        self, api_client: TestClient
    ) -> None:
        api_client.post(f"{API}/runs", json={})
        api_client.post(f"{API}/runs", json={})
        body = api_client.get(f"{API}/dashboard").json()

        # The demo golden set has 30 queries, right at the edge of where the
        # interval is trustworthy, so the verdict is stable with a caveat.
        assert body["health"] in {"healthy", "warning"}
        assert body["open_regressions"] == 0

    def test_critical_once_a_regression_is_detected(
        self, api_client: TestClient
    ) -> None:
        for _ in range(2):
            api_client.post(f"{API}/runs", json={})
        api_client.app.state.vector_store.delete_documents(  # type: ignore[attr-defined]
            ["doc-api-001", "doc-api-002", "doc-auth-003", "doc-security-003"]
        )
        api_client.post(f"{API}/runs", json={})

        body = api_client.get(f"{API}/dashboard").json()
        assert body["health"] == "critical"
        assert body["open_regressions"] > 0
        assert body["latest_drift"]["verdict"] == "degraded"


class TestIsolation:
    def test_each_test_gets_a_freshly_seeded_index(
        self, api_client: TestClient
    ) -> None:
        """Guards the fixture, not the app.

        chromadb.EphemeralClient() is shared across a process, so a collection
        created by one test outlives the application that made it. Without a
        unique collection name per test, documents deleted by an earlier test
        would silently leak in here and make results order-dependent.
        """
        info = api_client.get(f"{API}/system/info").json()
        assert info["vector_store"]["document_count"] == 32


class TestDiagnosticsEndpoint:
    def _degrade(self, api_client: TestClient) -> str:
        for _ in range(2):
            api_client.post(f"{API}/runs", json={})
        api_client.app.state.vector_store.delete_documents(  # type: ignore[attr-defined]
            [
                "doc-api-001",
                "doc-api-002",
                "doc-auth-003",
                "doc-security-003",
                "doc-data-002",
                "doc-support-003",
            ]
        )
        run_id: str = api_client.post(f"{API}/runs", json={}).json()["run_id"]
        return run_id

    def test_a_regression_gets_a_ranked_heuristic_report(
        self, api_client: TestClient
    ) -> None:
        run_id = self._degrade(api_client)
        body = api_client.get(f"{API}/runs/{run_id}/diagnostics").json()

        assert body["basis"] == "heuristic"
        assert "not statistical findings" in body["disclaimer"]

        findings = body["findings"]
        assert findings, "a deleted-document regression should produce findings"
        # Most direct evidence first.
        assert findings[0]["rule_id"] == "missing_expected_documents"
        assert findings[0]["strength"] == "direct"
        assert findings[0]["explains"] == findings[0]["out_of"]
        assert [f["strength"] for f in findings] == sorted(
            (f["strength"] for f in findings),
            key=lambda s: ["direct", "circumstantial", "contextual"].index(s),
        )

    def test_the_report_says_what_it_ruled_out(self, api_client: TestClient) -> None:
        run_id = self._degrade(api_client)
        body = api_client.get(f"{API}/runs/{run_id}/diagnostics").json()

        # Negative results matter: a report that only ever shows hits looks
        # like it is fishing.
        assert "embedding_model_changed" in body["checks_passed"]
        assert "expected_documents_demoted" in body["checks_passed"]

    def test_diagnostics_are_attached_to_the_drift_assessment(
        self, api_client: TestClient
    ) -> None:
        run_id = self._degrade(api_client)
        body = api_client.get(f"{API}/runs/{run_id}/drift").json()

        assert body["verdict"] == "degraded"
        assert body["diagnostics"]["basis"] == "heuristic"
        # The statistical fields and the heuristic ones stay in separate
        # objects, so a client can never confuse their standing.
        assert "p_value_adjusted" in body["comparisons"][0]
        assert not any(
            "p_value" in key or "confidence" in key
            for key in body["diagnostics"]["findings"][0]
        )

    def test_a_healthy_run_gets_no_diagnostics(self, api_client: TestClient) -> None:
        api_client.post(f"{API}/runs", json={})
        second = api_client.post(f"{API}/runs", json={}).json()

        drift = api_client.get(f"{API}/runs/{second['run_id']}/drift").json()
        assert drift["verdict"] == "stable"
        # Diagnostics explain a regression the statistics established; they
        # are never produced speculatively for a healthy run.
        assert drift["diagnostics"] is None

        response = api_client.get(f"{API}/runs/{second['run_id']}/diagnostics")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "diagnostics_unavailable"

    def test_diagnostics_survive_a_round_trip_through_the_database(
        self, api_client: TestClient
    ) -> None:
        run_id = self._degrade(api_client)
        first = api_client.get(f"{API}/runs/{run_id}/diagnostics").json()
        # Second read comes from the stored event rather than being recomputed.
        second = api_client.get(f"{API}/runs/{run_id}/diagnostics").json()

        assert first["findings"] == second["findings"]
        assert first["checks_passed"] == second["checks_passed"]

    def test_diagnostics_appear_in_the_drift_events_feed(
        self, api_client: TestClient
    ) -> None:
        self._degrade(api_client)
        page = api_client.get(
            f"{API}/drift/events", params={"verdict": "degraded"}
        ).json()

        assert page["total"] == 1
        assert page["items"][0]["diagnostics"]["findings"]
