"""One adapter for chat models and embedders.

- FakeLLM / HashEmbedder: offline and deterministic, used by tests and `make eval`.
- OpenAIAdapter: Azure OpenAI (default real provider) or any OpenAI-compatible endpoint.

The agent only ever calls `complete_json(task, payload)` and `embed(texts)`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass

from app.config import Settings

STOPWORDS = set(
    "a an and are as at be been but by can for from has have i in is it its me my of on or our so that the "
    "their there this to was we were what when which while will with you your it's not no some any".split()
)
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[0-9]+)?")


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens with light stemming; keeps codes like 'pf-101' intact."""
    out = []
    for tok in TOKEN_RE.findall(text.lower()):
        if tok in STOPWORDS or len(tok) < 2:
            continue
        out.append(stem(tok))
    return out


def stem(tok: str) -> str:
    if any(ch.isdigit() for ch in tok):
        return tok
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 4:
        tok = tok[:-1]
    for suffix in ("ation", "ating", "ate", "ing", "age", "ion", "ed"):
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 3:
            return tok[: -len(suffix)]
    return tok


@dataclass
class LLMResult:
    data: dict
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str


# --------------------------------------------------------------------------- embedders
class HashEmbedder:
    """Deterministic bag-of-words embedder (feature hashing). Not semantic, but
    word overlap gives useful similarity, which is enough for offline tests."""

    model = "fake-hash-embedder"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        toks = tokenize(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


# --------------------------------------------------------------------------- chat models
class FakeLLM:
    """Deterministic stand-in for a chat model. It implements each agent task
    with plain heuristics (see app/agent/fake_policy.py), so the whole pipeline
    runs without an API key. Its scores are NOT a quality measure."""

    model = "fake-llm"

    def complete_json(self, task: str, payload: dict) -> LLMResult:
        from app.agent import fake_policy

        start = time.perf_counter()
        data = fake_policy.run(task, payload)
        prompt_chars = len(json.dumps(payload, default=str))
        return LLMResult(
            data=data,
            input_tokens=prompt_chars // 4,
            output_tokens=len(json.dumps(data)) // 4,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=self.model,
        )


class OpenAIAdapter:
    """Azure OpenAI or an OpenAI-compatible endpoint, configured by env vars."""

    def __init__(self, provider: str):
        import openai

        self.provider = provider
        if provider == "azure":
            self.client = openai.AzureOpenAI(
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            )
            self.model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
            self.embed_model = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")
        else:
            self.client = openai.OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY", ""), base_url=os.getenv("OPENAI_BASE_URL") or None
            )
            self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
            self.embed_model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    def complete_json(self, task: str, payload: dict) -> LLMResult:
        from app.agent.prompts import build_messages

        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=build_messages(task, payload),
            response_format={"type": "json_object"},
            temperature=0,
        )
        text = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"error": "invalid_json", "raw": text[:500]}
        usage = resp.usage
        return LLMResult(
            data=data,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=self.model,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.embed_model, input=texts)
        return [d.embedding for d in resp.data]


def get_llm(settings: Settings):
    if settings.llm_provider == "fake":
        return FakeLLM()
    return OpenAIAdapter(settings.llm_provider)


def get_embedder(settings: Settings):
    if settings.llm_provider == "fake":
        return HashEmbedder(settings.embed_dim)
    return OpenAIAdapter(settings.llm_provider)
