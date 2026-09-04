"""Application settings.

All configuration arrives through the environment (prefix ``DRIFT_``) or a
``.env`` file, so the same image runs locally and in Docker with nothing but
env vars changed. Defaults are chosen so that a bare ``python -m app.cli``
works against the bundled demo data with zero setup.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Repository root, resolved from this file: app/core/config.py -> backend -> repo
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Typed view of the process environment."""

    model_config = SettingsConfigDict(
        env_prefix="DRIFT_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Application ---------------------------------------------------
    app_name: str = "RAG Drift Detector"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # -- Storage locations ---------------------------------------------
    data_dir: Path = Field(
        default=BACKEND_DIR / "data",
        description="Writable directory for the SQLite file and Chroma index.",
    )

    # -- Vector store ---------------------------------------------------
    connector: str = Field(default="chroma", description="Registered connector name.")
    chroma_mode: Literal["persistent", "http", "memory"] = "persistent"
    chroma_collection: str = "drift_demo"
    chroma_path: Path | None = Field(
        default=None, description="Defaults to <data_dir>/chroma."
    )
    chroma_host: str | None = None
    chroma_port: int = 8000
    chroma_ssl: bool = False

    # -- Embeddings -----------------------------------------------------
    embedding_provider: str = "hashing"
    embedding_dimensions: int = 384

    # -- Evaluation -----------------------------------------------------
    eval_k_values: tuple[int, ...] = (1, 3, 5, 10)
    eval_primary_k: int = 5

    # -- Demo data ------------------------------------------------------
    demo_dir: Path = Field(default=REPO_ROOT / "demo")

    # -- Persistence ----------------------------------------------------
    database_url: str | None = Field(
        default=None, description="Defaults to sqlite:///<data_dir>/driftdetector.db"
    )
    auto_migrate: bool = Field(
        default=True,
        description="Apply Alembic migrations on startup. Disable to gate schema "
        "changes behind a deliberate deploy step.",
    )
    bootstrap_demo: bool = Field(
        default=True,
        description="On a fresh install, index the demo corpus and import the demo "
        "golden set so the dashboard is explorable immediately.",
    )

    # -- API ------------------------------------------------------------
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    )

    @field_validator("eval_k_values", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow ``DRIFT_EVAL_K_VALUES=1,3,5`` style env vars."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def _check_primary_k(self) -> Settings:
        if self.eval_primary_k not in self.eval_k_values:
            raise ValueError(
                f"eval_primary_k={self.eval_primary_k} must appear in "
                f"eval_k_values={self.eval_k_values}"
            )
        return self

    @property
    def resolved_chroma_path(self) -> Path:
        return self.chroma_path or (self.data_dir / "chroma")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'driftdetector.db').as_posix()}"

    @property
    def demo_documents_path(self) -> Path:
        return self.demo_dir / "documents.json"

    @property
    def demo_golden_set_path(self) -> Path:
        return self.demo_dir / "golden_set.json"

    def ensure_directories(self) -> None:
        """Create the writable directories this configuration implies."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.chroma_mode == "persistent":
            self.resolved_chroma_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton (also a FastAPI dependency)."""
    return Settings()
