"""Fixtures for the knowledge base tests: offline settings, an embedder that cannot reach the network."""

from __future__ import annotations

from pathlib import Path

import pytest

from versoml.config import Settings
from versoml.knowledge.embeddings import Embedder


class NoNetwork:
    """A backend that fails the test if a live embedding call is attempted."""

    calls = 0

    def available(self) -> bool:
        return True

    def __call__(self, spec, texts, input_type):
        NoNetwork.calls += 1
        raise AssertionError("a test tried to call Bedrock")


class FakeBackend:
    """Deterministic vectors from a hash of the text; records the calls."""

    def __init__(self, dim: int | None = None, fail_times: int = 0, error: Exception | None = None):
        self.calls: list[tuple[str, int, str]] = []
        self.dim = dim
        self.fail_times = fail_times
        self.error = error

    def available(self) -> bool:
        return True

    def __call__(self, spec, texts, input_type):
        import hashlib

        import numpy as np

        self.calls.append((spec.model_id, len(texts), input_type))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error or RuntimeError("boom")
        out = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
            out.append(np.random.default_rng(seed).normal(size=self.dim or spec.dim).tolist())
        return out


def offline_settings(var: Path) -> Settings:
    return Settings(versoml_var_dir=var, versoml_llm_mode="offline", versoml_zone="all")


@pytest.fixture(scope="session")
def kb_var(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("kb_var")


@pytest.fixture(scope="session")
def client_kb(kb_var):
    from versoml.knowledge.kb import KnowledgeBase

    settings = offline_settings(kb_var)
    return KnowledgeBase("client", settings=settings, embedder=Embedder(settings, backend=NoNetwork()))


@pytest.fixture(scope="session")
def aml_kb(kb_var):
    from versoml.knowledge.kb import KnowledgeBase

    settings = offline_settings(kb_var)
    return KnowledgeBase("aml", settings=settings, embedder=Embedder(settings, backend=NoNetwork()))


@pytest.fixture
def offline_llm(tmp_path):
    from versoml.shared.llm import LLMClient

    return LLMClient(offline_settings(tmp_path / "llm"))
