from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class NegotiationSettings(BaseModel):
    public_base_url: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_PUBLIC_BASE_URL", "http://127.0.0.1:8031"))
    duckdb_path: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_DUCKDB_PATH", "/data/db/duckdb/gramlead-read.duckdb"))
    jsonl_dir: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_JSONL_DIR", "/data/out"))
    artifacts_dir: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_ARTIFACTS_DIR", "/data/out/negotiation_assistant"))
    postgres_dsn: str = Field(
        default_factory=lambda: os.getenv(
            "NEGOTIATION_POSTGRES_DSN",
            "postgresql://negotiation:negotiation@x-files-negotiation-postgres:5432/negotiation",
        )
    )
    store: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_STORE", "postgres"))
    openrouter_api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = Field(default_factory=lambda: os.getenv("NEGOTIATION_OPENROUTER_MODEL", "openai/gpt-oss-120b:free"))
    max_messages_per_brief: int = Field(default_factory=lambda: int(os.getenv("NEGOTIATION_MAX_MESSAGES", "80")))
    llm_timeout_sec: int = Field(default_factory=lambda: int(os.getenv("NEGOTIATION_LLM_TIMEOUT_SEC", "90")))

    @property
    def artifacts_path(self) -> Path:
        return Path(self.artifacts_dir)

    @property
    def jsonl_path(self) -> Path:
        return Path(self.jsonl_dir)

    @property
    def duckdb_file(self) -> Path:
        return Path(self.duckdb_path)


settings = NegotiationSettings()

