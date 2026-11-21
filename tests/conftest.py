"""Shared fixtures: an offline SQLite store with the SYNTHETIC manual and history."""
from __future__ import annotations

import pytest

from app.agent.runner import Agent
from app.config import get_settings
from app.data_gen.faults_gen import seed_store
from app.retrieval.ingest import ingest
from app.store import get_store
from app.tools import ToolContext
from app.llm import get_embedder


def make_settings(tmp_path, **kw):
    s = get_settings(store_backend="sqlite", llm_provider="fake", embed_dim=256, reranker="overlap",
                     max_tool_calls=6, sqlite_path=tmp_path / "test.db", synthetic_dir=tmp_path / "synthetic",
                     trace_dir=tmp_path / "traces")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    return make_settings(tmp_path_factory.mktemp("ff"))


@pytest.fixture(scope="session")
def store(settings):
    st = get_store(settings)
    ingest(settings, st)
    seed_store(settings, st)
    return st


@pytest.fixture(scope="session")
def ctx(settings, store):
    return ToolContext(store, get_embedder(settings), settings)


@pytest.fixture()
def agent(settings, store):
    return Agent(settings, store, trace_dir=None)
