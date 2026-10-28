"""BM25, fusion, filters, the rule-ID boost, the zone wall, offline determinism, precedents."""

from __future__ import annotations

import numpy as np
import pytest

from versoml.knowledge.index import BM25, CharNgramTfidf, mmr, ranking, rrf
from versoml.knowledge.text import fold, stem, tokenize

from .conftest import NoNetwork, offline_settings


# ---------------------------------------------------------------- tokens and BM25


def test_tokenize_normalizes_and_drops_stopwords():
    assert fold("Ştiinţa ş ţ") == "stiinta s t"
    tokens = tokenize("Banca rambursează plata neautorizată și PAY-03")
    assert "si" not in tokens and "pay_03" in tokens
    assert tokenize("rambursare") == tokenize("rambursarea")  # light stemming
    assert stem("refunds") == stem("refunded") == "refund"
    assert tokenize("Plata şi") == tokenize("Plata și")  # cedilla and comma below agree


def test_bm25_sanity():
    docs = [tokenize(t) for t in ("the refund deadline is the next business day",
                                  "a chargeback has a scheme deadline",
                                  "the police report is optional")]
    bm = BM25(docs)
    scores = bm.scores(tokenize("refund deadline"))
    assert int(np.argmax(scores)) == 0
    assert scores[2] == 0.0
    assert bm.idf["refund"] > bm.idf["deadlin"]  # rarer term, higher weight
    assert np.all(bm.scores(tokenize("nothing matches here")) == 0)


def test_char_ngrams_survive_typos():
    idx = CharNgramTfidf(["rambursare la sfârșitul zilei lucrătoare", "poprire pe salariu"])
    s = idx.scores("ramburssare zilei lucratoare")
    assert s[0] > s[1] >= 0


def test_ranking_and_rrf_order():
    scores = np.array([0.0, 3.0, 2.0, 3.0])
    assert ranking(scores, np.ones(4, dtype=bool), 10) == [1, 3, 2]  # ties: lower index first; zeros dropped
    assert ranking(scores, np.array([True, False, True, True]), 10) == [3, 2]
    fused = rrf({"bm25": [1, 2, 3], "dense": [2, 3, 1]}, k=60)
    order = sorted(fused, key=lambda i: (-fused[i], i))
    assert order[0] == 2  # second and first beats first and third
    assert fused[2] == pytest.approx(1 / 62 + 1 / 61)
    weighted = rrf({"bm25": [1], "dense": [2]}, k=60, weights={"bm25": 0.5, "dense": 1.0})
    assert weighted[2] > weighted[1]


def test_mmr_prefers_diversity():
    rel = {0: 1.0, 1: 0.99, 2: 0.5}
    sim = lambda a, b: 1.0 if {a, b} == {0, 1} else 0.0  # noqa: E731
    assert mmr([0, 1, 2], rel, sim, k=2, lam=0.5) == [0, 2]
    assert mmr([0, 1, 2], rel, sim, k=2, lam=1.0) == [0, 1]


# ---------------------------------------------------------------- the knowledge base


def test_search_returns_hits_with_why(client_kb):
    hits = client_kb.search("By when must the bank refund an unauthorized payment?", k=5)
    assert hits[0].id == "rule:PAY-03"
    assert hits[0].why["dense"] is True and hits[0].why["signals"] == ["bm25", "dense"]
    assert "rrf" in hits[0].why and hits[0].score > 0
    assert all(h.kind != "precedent" for h in hits)  # past cases are not legal sources by default


def test_offline_without_query_vector_degrades_to_char_ngrams(client_kb):
    hits = client_kb.search("rambursare plată neautorizată termen zi lucrătoare", k=5)
    assert hits and hits[0].why["dense"] is False
    assert hits[0].why["signals"] == ["bm25", "char_ngram"] and hits[0].why["fallback"] == "no_query_vector"
    assert NoNetwork.calls == 0


def test_filters_by_kind_and_rule_ids(client_kb):
    hits = client_kb.search("refund deadline", k=8, kinds=["law"])
    assert hits and all(h.kind == "law" for h in hits)
    hits = client_kb.search("refund", k=8, rule_ids=["PAY-15"])
    assert hits and all("PAY-15" in h.rule_ids or "DSP-04" in h.rule_ids for h in hits)
    with pytest.raises(ValueError):
        client_kb.search("x", kinds=["nonsense"])
    assert client_kb.search("   ") == []


def test_exact_rule_id_mention_boosts_that_rule(client_kb):
    for query, rid in (("What does PAY-12 say about scams?", "PAY-12"), ("ce spune dsp 54", "DSP-54"),
                       ("DSP-05 refund", "PAY-03")):  # an alias resolves to its rule
        hits = client_kb.search(query, k=3)
        assert hits[0].id == f"rule:{rid}"
        assert hits[0].why.get("rule_id_boost")


def test_for_rules_gives_the_rule_then_docs_citing_it(client_kb):
    hits = client_kb.for_rules(["PAY-03", "DSP-54", "DSP-05"], k_per=2)
    ids = [h.id for h in hits]
    assert ids[0] == "rule:PAY-03" and "rule:DSP-54" in ids
    assert len(ids) == len(set(ids))  # DSP-05 is PAY-03: no duplicate
    docs = [h for h in hits if h.why.get("for_rule") == "PAY-03"]
    assert docs and all(h.kind in ("law", "guidance", "typology", "case_study") for h in docs)
    assert any({"PAY-03", "DSP-05"} & set(h.rule_ids) for h in docs)
    assert client_kb.for_rules(["ZZZ-99"]) == []


def test_aml_kb_has_no_precedents(aml_kb):
    assert aml_kb.stats()["by_kind"].get("precedent", 0) == 0
    assert all(c.kind != "precedent" for c in aml_kb.chunks())
    assert aml_kb.precedents("phishing courier link transfer") == []
    assert aml_kb.search("courier text message refund", k=10, kinds=["precedent"]) == []
    with pytest.raises(PermissionError):
        aml_kb.add_precedent("CT-2026-000001", "text", {"verdict": "RAMBURSEAZA"})


def test_aml_process_cannot_load_the_client_kb(tmp_path):
    from versoml.config import Settings
    from versoml.knowledge.kb import KnowledgeBase

    with pytest.raises(PermissionError):
        KnowledgeBase("client", settings=Settings(versoml_var_dir=tmp_path, versoml_zone="aml",
                                                  versoml_llm_mode="offline"))


def test_offline_results_are_deterministic(kb_var, client_kb):
    from versoml.knowledge.embeddings import Embedder
    from versoml.knowledge.kb import KnowledgeBase

    settings = offline_settings(kb_var)
    other = KnowledgeBase("client", settings=settings, embedder=Embedder(settings, backend=NoNetwork()))
    for q in ("Ce face banca dacă plătitorul a fost grav neglijent?", "poprire salariu executor", "PAY-01"):
        a = [(h.id, h.score, h.why) for h in client_kb.search(q, k=6)]
        b = [(h.id, h.score, h.why) for h in other.search(q, k=6)]
        assert a == b


def test_precedents_search_and_exclusion(client_kb):
    text = ("I got a text from the courier, tapped the link and entered a code. Then a transfer I did not make "
            "left my account.")
    hits = client_kb.precedents(text, k=3)
    assert len(hits) == 3 and all(h.kind == "precedent" for h in hits)
    assert all("outcome" in h.meta and h.meta["case_id"] for h in hits)
    top = hits[0].meta["case_id"]
    again = client_kb.precedents(text, k=3, exclude_case_id=top)
    assert top not in [h.meta["case_id"] for h in again]


def test_add_precedent_is_pseudonymized_persisted_and_searchable(tmp_path):
    from versoml.knowledge.embeddings import Embedder
    from versoml.knowledge.kb import KnowledgeBase

    settings = offline_settings(tmp_path)
    kb = KnowledgeBase("client", settings=settings, embedder=Embedder(settings, backend=NoNetwork()))
    text = ("Zorblax quantum parcel scam: the payment went to RO49AAAA1B31007593840000 and the customer "
            "wrote from client.test@example.com.")
    kb.add_precedent("CT-2026-777001", text, {"verdict": "RAMBURSEAZA", "rule_ids": ["PAY-03"]},
                     {"scenario": "phishing_link", "channel": "transfer"})
    hits = kb.precedents("zorblax quantum parcel", k=1)
    assert hits[0].id == "prec:CT-2026-777001"
    assert "RO49AAAA" not in hits[0].text and "example.com" not in hits[0].text
    assert hits[0].meta["outcome"]["verdict"] == "RAMBURSEAZA" and hits[0].meta["origin"] == "runtime"
    saved = (tmp_path / "kb" / "precedents.jsonl").read_text(encoding="utf-8")
    assert "CT-2026-777001" in saved and "RO49AAAA" not in saved
    reloaded = KnowledgeBase("client", settings=settings, embedder=Embedder(settings, backend=NoNetwork()))
    assert reloaded.chunk("prec:CT-2026-777001") is not None
    assert reloaded.stats()["precedents"]["runtime"] == 1


def test_stats_and_load_speed(client_kb):
    stats = client_kb.stats()
    assert stats["dense_available"] and stats["dense_coverage"] >= 0.9  # precedents may lag a golden-set edit
    assert stats["embedding_model"] == client_kb.model and not stats["stale"]
    assert stats["by_kind"]["rule"] >= 60 and stats["by_kind"]["precedent"] >= 300
    assert stats["load_ms"] < 3000  # under 1 s on a laptop; generous for CI


def test_search_is_fast(client_kb):
    import time

    client_kb.search("warm up", k=6)
    started = time.perf_counter()
    for q in ("termen rambursare", "What is a safe-account scam?", "PAY-03", "poprire salariu") * 5:
        client_kb.search(q, k=6)
    assert (time.perf_counter() - started) / 20 < 0.2  # about 5-10 ms here; generous for CI


def test_rerank_reorders_and_failures_keep_the_order(client_kb):
    from versoml.knowledge import rerank

    base = [h.id for h in client_kb.search("refund deadline", k=5)]
    rerank.set_backend(lambda model, q, docs, n: [(i, 1.0 - i / 100) for i in reversed(range(len(docs)))])
    try:
        flipped = client_kb.search("refund deadline", k=5, rerank=True)
        assert flipped[0].why["rerank_rank"] == 1 and [h.id for h in flipped] != base

        def broken(*_a):
            raise RuntimeError("down")

        rerank.set_backend(broken)
        assert [h.id for h in client_kb.search("refund deadline", k=5, rerank=True)] == base
    finally:
        rerank.set_backend(None)
