"""Tests for settings parsing.

These exist because of a bug that only appeared in Docker: every field here is
fine with its default, and the failure needed an environment variable set the
way the shipped compose file and .env.example set it.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


class TestCommaSeparatedEnvVars:
    """The documented `DRIFT_EVAL_K_VALUES=1,3,5,10` form must actually work.

    For a complex-typed field, pydantic-settings JSON-decodes the environment
    value *before* any ``mode="before"`` validator runs. Without the NoDecode
    annotation these raise a SettingsError at import time, which took the whole
    API container down on startup while every local test still passed.
    """

    def test_eval_k_values_accepts_the_documented_csv_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRIFT_EVAL_K_VALUES", "1,3,5,10")
        monkeypatch.setenv("DRIFT_EVAL_PRIMARY_K", "5")
        assert Settings().eval_k_values == (1, 3, 5, 10)

    def test_eval_k_values_tolerates_whitespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRIFT_EVAL_K_VALUES", " 1 , 5 ,10 ")
        monkeypatch.setenv("DRIFT_EVAL_PRIMARY_K", "5")
        assert Settings().eval_k_values == (1, 5, 10)

    def test_cors_origins_accepts_the_csv_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "DRIFT_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        )
        assert Settings().cors_origins == (
            "http://localhost:3000",
            "http://localhost:5173",
        )

    def test_defaults_still_apply_with_no_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DRIFT_EVAL_K_VALUES", raising=False)
        monkeypatch.delenv("DRIFT_CORS_ORIGINS", raising=False)
        settings = Settings()
        assert settings.eval_k_values == (1, 3, 5, 10)
        assert settings.cors_origins


class TestValidation:
    def test_primary_k_must_be_one_of_the_evaluated_cutoffs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRIFT_EVAL_K_VALUES", "1,3")
        monkeypatch.setenv("DRIFT_EVAL_PRIMARY_K", "5")
        with pytest.raises(ValueError, match="must appear in"):
            Settings()

    def test_booleans_parse_from_the_env_var_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # docker-compose.yml passes these as strings.
        monkeypatch.setenv("DRIFT_BOOTSTRAP_DEMO", "false")
        monkeypatch.setenv("DRIFT_AUTO_MIGRATE", "true")
        settings = Settings()
        assert settings.bootstrap_demo is False
        assert settings.auto_migrate is True

    def test_database_url_defaults_under_the_data_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("DRIFT_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("DRIFT_DATABASE_URL", raising=False)
        assert Settings().resolved_database_url.endswith("driftdetector.db")
