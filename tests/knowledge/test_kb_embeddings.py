"""embed_texts: content-addressed cache (hit and miss), live gating, batching, retries, the PII guard."""

from __future__ import annotations

import numpy as np
import pytest

from versoml.config import Settings
from versoml.knowledge.embeddings import MODELS, Embedder, StaticCache, cache_key, normalize_text

from .conftest import FakeBackend

V3 = "cohere.embed-multilingual-v3"


def _embedder(tmp_path, backend, mode="offline", **kw) -> Embedder:
    settings = Settings(versoml_var_dir=tmp_path / "var", versoml_llm_mode=mode)
    return Embedder(settings, static_dir=tmp_path / "static", backend=backend, backoff_s=0.0, **kw)


def test_cache_key_is_content_addressed():
    a = cache_key(V3, "search_query", "Plata  şi\ttermenul")
    assert a == cache_key(V3, "search_query", "Plata și termenul")  # cedilla and whitespace normalized
    assert a != cache_key(V3, "search_document", "Plata și termenul")
    assert a != cache_key("cohere.embed-v4:0", "search_query", "Plata și termenul")
    assert normalize_text("  a \n b ") == "a b"


def test_offline_miss_returns_none_and_sends_nothing(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="offline")
    assert emb.embed(["never seen"], "search_query", model=V3) is None
    assert emb.embed(["never seen"], "search_query", model=V3, allow_live=False) is None
    assert backend.calls == []
    assert emb.embed([], model=V3).shape == (0, 1024)


def test_live_miss_then_cache_hit(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="live")
    texts = ["refund deadline", "termen rambursare", "refund deadline"]
    first = emb.embed(texts, "search_query", namespace="queries_client", model=V3)
    assert first.shape == (3, 1024) and first.dtype == np.float32
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0, atol=1e-5)
    assert np.allclose(first[0], first[2])
    assert backend.calls == [(V3, 2, "search_query")]  # unique texts only
    # a new process (new embedder) in offline mode finds them in the runtime cache under var/kb
    again = _embedder(tmp_path, FakeBackend(), mode="offline")
    second = again.embed(texts, "search_query", namespace="queries_client", model=V3)
    assert second is not None and np.allclose(first, second, atol=2e-3)  # float16 storage
    assert (tmp_path / "var" / "kb" / "emb_queries_client.sqlite").exists()


def test_allow_live_overrides_offline_mode(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="offline")
    assert emb.embed(["x y z"], model=V3, allow_live=True) is not None
    assert len(backend.calls) == 1


def test_static_cache_roundtrip_and_prune(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="offline")
    out = emb.embed(["doc one", "doc two"], "search_document", namespace="kb", static=True, allow_live=True, model=V3)
    path = tmp_path / "static" / "emb_kb__cohere-embed-multilingual-v3.npz"
    assert path.exists() and not (tmp_path / "var" / "kb" / "emb_kb.sqlite").exists()
    cache = StaticCache(path, 1024)
    assert len(cache) == 2 and cache.get(cache_key(V3, "search_document", "doc one")).dtype == np.float16
    keep = {cache_key(V3, "search_document", "doc two")}
    assert cache.flush(keep=keep) == 1
    fresh = _embedder(tmp_path, FakeBackend(), mode="offline")
    matrix, found = fresh.lookup(["doc one", "doc two"], "search_document", namespace="kb", model=V3)
    assert found.tolist() == [False, True] and np.allclose(matrix[1], out[1], atol=2e-3)


def test_batches_of_96_for_cohere(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="live")
    out = emb.embed([f"text {i}" for i in range(200)], namespace="batch", model=V3)
    assert out.shape == (200, 1024)
    assert [n for _, n, _ in backend.calls] == [96, 96, 8]
    assert MODELS[V3].max_batch == 96


def test_retries_on_throttling_then_succeeds(tmp_path):
    class Throttled(Exception):
        response = {"Error": {"Code": "ThrottlingException"}}

    backend = FakeBackend(fail_times=2, error=Throttled("slow down"))
    emb = _embedder(tmp_path, backend, mode="live")
    assert emb.embed(["a b c"], model=V3) is not None
    assert len(backend.calls) == 3 and emb.stats.errors == 0


def test_fatal_error_returns_none_and_backs_off(tmp_path):
    class Denied(Exception):
        response = {"Error": {"Code": "AccessDeniedException"}}

    backend = FakeBackend(fail_times=10, error=Denied("no"))
    emb = _embedder(tmp_path, backend, mode="live")
    assert emb.embed(["a b c"], model=V3) is None
    assert len(backend.calls) == 1 and emb.stats.errors == 1
    assert not emb.live_allowed(None)  # the 60 s back-off after an access error


def test_wrong_dimension_is_rejected(tmp_path):
    emb = _embedder(tmp_path, FakeBackend(dim=7), mode="live")
    assert emb.embed(["a b c"], model=V3) is None


def test_pii_guard_blocks_runtime_text_before_any_call(tmp_path):
    from versoml.shared.privacy import RawPIIError

    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="live")
    with pytest.raises(RawPIIError):
        emb.embed(["Customer IBAN RO49AAAA1B31007593840000 asked for a refund"], namespace="queries_client", model=V3)
    with pytest.raises(RawPIIError):  # precedents are case data, even when built for the committed cache
        emb.embed(["Past case, CNP 1800101420010"], namespace="precedents", static=True, model=V3)
    assert backend.calls == []
    # pseudonymized text passes
    assert emb.embed(["Customer <IBAN_1> asked for a refund"], namespace="queries_client", model=V3) is not None
    # cached text needs no call, so nothing is checked or sent
    offline = _embedder(tmp_path, FakeBackend(), mode="offline")
    assert offline.embed(["Customer <IBAN_1> asked for a refund"], namespace="queries_client", model=V3) is not None


def test_static_docs_corpus_skips_the_guard(tmp_path):
    backend = FakeBackend()
    emb = _embedder(tmp_path, backend, mode="offline")
    out = emb.embed(["Exemplu IBAN fictiv: RO49AAAA1B31007593840000"], namespace="kb", static=True,
                    allow_live=True, model=V3)
    assert out is not None and len(backend.calls) == 1


def test_invalid_arguments(tmp_path):
    emb = _embedder(tmp_path, FakeBackend())
    with pytest.raises(ValueError):
        emb.embed(["x"], "bogus", model=V3)
    with pytest.raises(ValueError):
        emb.embed(["x"], namespace="../etc", model=V3)
    with pytest.raises(ValueError):
        emb.embed(["x"], model="unknown-model")


def test_public_function_uses_the_process_embedder(tmp_path, monkeypatch):
    from versoml.knowledge import embed_texts, embeddings

    emb = _embedder(tmp_path, FakeBackend(), mode="offline")
    embeddings.set_embedder(emb)
    try:
        assert embed_texts(["unseen query"], "search_query", model=V3) is None
        assert embed_texts(["seen"], "search_query", allow_live=True, model=V3).shape == (1, 1024)
    finally:
        embeddings.set_embedder(None)
