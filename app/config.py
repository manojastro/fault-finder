"""Settings read from environment variables (and .env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


@dataclass
class Settings:
    store_backend: str = field(default_factory=lambda: os.getenv("STORE_BACKEND", "sqlite"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql://faultfinder:faultfinder@localhost:5433/faultfinder"
        )
    )
    sqlite_path: Path = field(default_factory=lambda: _path(os.getenv("SQLITE_PATH", "data/local/faultfinder.db")))
    manual_path: Path = field(default_factory=lambda: _path(os.getenv("MANUAL_PATH", "data/manual")))
    synthetic_dir: Path = field(default_factory=lambda: _path(os.getenv("SYNTHETIC_DIR", "data/synthetic")))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "fake"))
    embed_dim: int = field(default_factory=lambda: int(os.getenv("EMBED_DIM", "256")))
    reranker: str = field(default_factory=lambda: os.getenv("RERANKER", "overlap"))
    max_tool_calls: int = field(default_factory=lambda: int(os.getenv("MAX_TOOL_CALLS", "6")))
    trace_dir: Path = field(default_factory=lambda: _path(os.getenv("TRACE_DIR", "traces")))
    safety_rules_path: Path = field(
        default_factory=lambda: _path(os.getenv("SAFETY_RULES_PATH", "config/safety_rules.yaml"))
    )
    prices_path: Path = field(default_factory=lambda: _path(os.getenv("PRICES_PATH", "config/prices.yaml")))


def get_settings(**overrides) -> Settings:
    s = Settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s
