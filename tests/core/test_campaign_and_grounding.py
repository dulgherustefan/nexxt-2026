"""The campaign linker (shared indicators, M6, story similarity) and the knowledge-base wrapper (citations,
plain legal references, graceful degradation when the knowledge base is missing)."""

from __future__ import annotations

import asyncio
import sys
import types

import numpy as np
import pytest

from versoml.zone_client import campaign as CP
from versoml.zone_client import grounding as G

STORY = ("I got a text from <TELEFON_1> saying my parcel could not be delivered. I opened the link and paid the fee. "
         "Two minutes later RON 3,200 had gone to someone I do not know. Please give me my money back.")


def case(cid, ibans=(), domains=(), phones=(), narrative=""):
    return {"case_id": cid, "indicators": {"ibans": list(ibans), "domains": list(domains), "phones": list(phones)},
            "narrative": narrative}


def test_same_payee_and_domain_link_cases_with_masked_indicators():
    out = CP.link("CT-2026-000003", {"ibans": ["RO61BDEM1777286093723598"],
                                     "domains": ["https://livrare-bancademo.example/colet/RO1"], "phones": []}, "",
                  [case("CT-2026-000001", ibans=["RO61 BDEM 1777 2860 9372 3598"]),
                   case("CT-2026-000002", domains=["plata.livrare-bancademo.example"]),
                   case("CT-2026-000009", ibans=["RO27YBNK0000000000004471"])])
    assert out["case_ids"] == ["CT-2026-000001", "CT-2026-000002", "CT-2026-000003"]
    assert {"kind": "iban", "value_masked": "RO61 BDEM •••• 3598"} in out["shared_indicators"]
    assert {"kind": "domain", "value_masked": "livrare-bancademo.example"} in out["shared_indicators"]
    assert out["campaign_id"].startswith("CMP-") and out["similarity"] == 0.0
    assert not any("1777286093" in i["value_masked"] for i in out["shared_indicators"])


def test_similar_stories_link_without_shared_indicators():
    out = CP.link("CT-B", {}, STORY, [case("CT-A", narrative=STORY.replace("3,200", "1,850")),
                                       case("CT-C", narrative="The shop never delivered my order, I want a refund.")])
    assert out["case_ids"] == ["CT-A", "CT-B"] and out["method"] == "lexical" and out["similarity"] > 0.6


def test_embeddings_are_used_when_available():
    def embed(texts):
        return np.array([[1.0, 0.0], [0.99, 0.141], [0.0, 1.0]][:len(texts)])

    out = CP.link("CT-B", {}, "story", [case("CT-A", narrative="x"), case("CT-C", narrative="y")], embed=embed)
    assert out["method"] == "embedding" and out["case_ids"] == ["CT-A", "CT-B"]


def test_nothing_shared_means_no_campaign():
    assert CP.link("CT-B", {"ibans": ["RO27YBNK0000000000004471"]}, "short", [case("CT-A", narrative="other")]) is None
    assert CP.link("CT-B", {}, STORY, []) is None


# ---------------------------------------------------------------- the knowledge base


class FakeKB:
    def __init__(self):
        self.added = []

    def search(self, q, k=6, kinds=None, rule_ids=None):
        return [{"id": "rule:PAY-03", "kind": "rule", "title": "Refund by the end of the next business day",
                 "text": "...", "source": "Law 209/2019, art. 173–174", "confidence": "P", "rule_ids": ["PAY-03"],
                 "score": 0.9}][:k]

    def for_rules(self, ids, k_per=1):
        return [{"id": "rule:PAY-03", "kind": "rule", "title": "t", "text": "x", "source": "L209 art. 173",
                 "confidence": "P", "rule_ids": ["PAY-03"]},
                {"id": "rule:DSP-59", "kind": "rule", "title": "cap", "text": "x", "source": "note", "confidence": "U"},
                {"id": "ctx:aml", "kind": "law", "title": "AML", "text": "x", "source": "Legea 129/2019 art. 6",
                 "confidence": "P"}]

    def precedents(self, text, k=3, exclude_case_id=None):
        assert "<CLIENT_" in text or "Ana" not in text
        return [{"id": "prec:CT-2026-000777", "kind": "precedent", "title": "p", "text": "t", "source": "case",
                 "meta": {"outcome": {"verdict": "RAMBURSEAZA"}, "case_id": "CT-2026-000777"}}]

    def add_precedent(self, case_id, text, outcome, meta=None):
        self.added.append((case_id, text, outcome, meta))

    async def ask(self, question, k=6):
        return {"question": question, "answer": "By the end of the next business day [1].", "citations":
                self.search(question), "grounded": True, "mode": "offline"}

    def stats(self):
        return {"chunks": {"rule": 40}, "embedding_model": "cohere.embed-multilingual-v3", "dense": False,
                "built_at": None}


@pytest.fixture
def fake_kb(monkeypatch):
    kb = FakeKB()
    module = types.ModuleType("versoml.knowledge")
    module.get_kb = lambda zone="client": kb
    module.embed_texts = lambda texts, input_type="clustering", namespace="campaign": None
    monkeypatch.setitem(sys.modules, "versoml.knowledge", module)
    monkeypatch.setattr(G, "pseudonymize", lambda text, scope="kb-query": (text, {}))
    return kb


def test_plain_references_are_english_citable_and_wall_safe(fake_kb):
    refs = G.plain_references(G.for_rules(["PAY-03", "DSP-59"]))
    assert refs == ["Law 209/2019, art. 173"]               # [U] and AML law are never cited to the customer
    assert G.plain_reference({"source": "Law 209/2019, Article 173–174", "confidence": "P"}) == "Law 209/2019, art. 173-174"


def test_wrapper_shapes(fake_kb):
    assert G.search("refund")[0]["id"] == "rule:PAY-03" and G.search("")[0:] == []
    answer = asyncio.run(G.ask("When is the refund due?"))
    assert answer["grounded"] and answer["citations"][0]["rule_ids"] == ["PAY-03"]
    assert G.stats()["available"] is True and G.stats()["chunks"] == {"rule": 40}
    prec = G.precedents("<CLIENT_1> lost RON 3,200", exclude_case_id="CT-2026-000001")
    assert prec == [{"hit": prec[0]["hit"], "outcome": {"verdict": "RAMBURSEAZA", "decision": "RAMBURSEAZA"}, "case_id_masked": "CT-2026-••77"}]
    assert G.add_precedent("CT-1", "text", {"verdict": "X"}) and fake_kb.added[0][0] == "CT-1"
    assert G.embed(["a"]) is None


def test_missing_knowledge_base_degrades(monkeypatch):
    monkeypatch.setattr(G, "_kb", lambda zone="client": None)
    assert G.search("x") == [] and G.for_rules(["PAY-03"]) == [] and G.precedents("x") == []
    assert G.stats() == {"chunks": {}, "embedding_model": None, "dense": False, "built_at": None, "available": False}
    assert asyncio.run(G.ask("x"))["grounded"] is False and G.add_precedent("CT-1", "t", {}) is False


def test_outcome_view_maps_golden_outcomes():
    from versoml.zone_client.grounding import outcome_view

    view = outcome_view({"verdict": "RAMBURSEAZA", "recovery": "RECHEMARE", "requires_human": False})
    assert view["decision"] == "RAMBURSEAZA" and view["recovered"] is True and view["status"] == "decided by the rules"
    view = outcome_view({"verdict": "ESCALADEAZA", "recovery": "NU_RECOMANDAM_RECUPERARE", "requires_human": True})
    assert view["recovered"] is False and view["status"] == "signed by a person"
    assert outcome_view({"decision": "X", "status": "closed"}) == {"decision": "X", "status": "closed"}
