"""Corpusul de reclamații: șabloane EN/RO, tipologii, corpusul LLM din git (igienă, ordine, etichete)."""

from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from versoml.data import ids
from versoml.data.complaints import SCENARIO_LABELS, generate_corpus
from versoml.data.complaints_ro import T_RO, complaint_text_ro
from versoml.data.corpus_llm import BRANDS_EN, LLM_CORPUS, load_llm_corpus, scrub
from versoml.data.text import has_cedilla
from versoml.data.typologies import load_typologies, typology_corpus


@pytest.fixture(scope="module")
def llm_rows():
    return [json.loads(x) for x in LLM_CORPUS.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_romanian_templates_cover_every_story():
    assert set(T_RO) == set(SCENARIO_LABELS) - {"injectie_document"}
    text = " ".join(s for tpl in T_RO.values() for slot in tpl["story"] for s in slot)
    assert not has_cedilla(text) and "ș" in text and "ț" in text


def test_romanian_corpus_is_messy_but_never_uses_cedillas():
    rows = generate_corpus(20, 7, language="ro")
    assert len(rows) == 20 * len(SCENARIO_LABELS) and all(r["language"] == "ro" for r in rows)
    texts = [r["text"] for r in rows]
    assert not any(has_cedilla(t) for t in texts)
    assert sum(not re.search("[ăâîșț]", t) for t in texts) > 0.2 * len(texts)   # many write without diacritics
    assert generate_corpus(20, 7, language="ro") == rows                          # deterministic


def test_groups_select_disjoint_phrase_variants():
    import random

    facts = {"amount": 1200.0, "executed_at": "2026-10-20T10:00:00+03:00", "notified_at": "2026-10-21T10:00:00+03:00"}
    texts = {g: {complaint_text_ro("plata_dubla", random.Random(i), facts=facts, style={"variants": g, "length": "scurt"})[0]
                 for i in range(30)} for g in (0, 2)}
    first0 = {t.split(".")[0] for t in texts[0]}
    first2 = {t.split(".")[0] for t in texts[2]}
    assert first0 and first2 and not first0 & first2


def test_english_default_path_is_unchanged_for_the_golden_set():
    from versoml.data.golden import GOLDEN_40, golden_40, read_jsonl

    assert [l["complaint"]["text"] for l in golden_40(7)] == [l["complaint"]["text"] for l in read_jsonl(GOLDEN_40)]


def test_typology_corpus_maps_to_existing_scenarios():
    typ = load_typologies()
    assert len(typ) >= 20 and all(t["maps_to_scenario"] in SCENARIO_LABELS for t in typ)
    rows = typology_corpus(3, 7, language="ro", group=1)
    assert {r["typology"] for r in rows} == {t["id"] for t in typ}
    assert all(r["scenario"] == next(t["maps_to_scenario"] for t in typ if t["id"] == r["typology"]) for r in rows)


def test_llm_corpus_size_order_and_labels(llm_rows):
    assert len(llm_rows) >= 1200
    kinds = Counter(r["kind"] for r in llm_rows)
    assert kinds["paraphrase"] >= 700 and kinds["hard_negative"] >= 200 and kinds["typology"] >= 300
    assert Counter(r["language"] for r in llm_rows)["ro"] >= 0.4 * len(llm_rows)
    per = Counter((r["scenario"], r["language"]) for r in llm_rows if r["kind"] == "paraphrase")
    assert set(s for s, _ in per) == set(SCENARIO_LABELS) and min(per.values()) >= 25
    assert [r["id"] for r in llm_rows] == [f"LLM{i:05d}" for i in range(1, len(llm_rows) + 1)]
    order = ["paraphrase", "hard_negative", "typology"]
    keys = [(order.index(r["kind"]), r["scenario"], r.get("subtype") or "", r.get("typology") or "", r["language"],
             r["batch"], r["index"]) for r in llm_rows]
    assert keys == sorted(keys)
    assert all(r["synthetic"] is True and (r["channel"], r["dispute_type"]) for r in llm_rows)
    assert len(load_llm_corpus()) == len(llm_rows)


def test_llm_corpus_has_nothing_real_looking(llm_rows):
    brands = re.compile("|".join(rf"\b(?:{pat})\b" for _, pat in BRANDS_EN.values()), re.I)
    for r in llm_rows:
        t = r["text"]
        assert scrub(t, r["language"], "check")[0] == t, r["id"]                  # the scrubber has nothing left to do
        assert not has_cedilla(t), r["id"]
        assert not brands.search(t), (r["id"], brands.search(t).group(0))
        for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", t):
            assert email.endswith("@mail.example"), r["id"]
        for m in re.finditer(r"(?<!\d)(?:\+?40|0040|0)\s?7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?!\d)", t):
            assert re.sub(r"\D", "", m.group(0))[-9:].startswith("700"), r["id"]
        for iban in re.findall(r"\bRO\d{2}[A-Z]{4}[A-Z0-9]{16}\b", t.replace(" ", "")):
            assert ids.iban_bank_code(iban) in ids.FICTIVE_BANKS, r["id"]
        assert not re.search(r"\b[1-8]\d{12}\b", t), r["id"]                       # no CNP-shaped numbers
        for url in re.findall(r"https?://\S+", t):
            assert re.search(r"\.(example|test)\b", url), r["id"]


def test_scrub_replaces_real_brands_and_identifiers():
    raw = "Fan Courier SMS, then ING took 300 lei; call 0722 123 456, mail ion@gmail.com, www.shop.ro, an OTP code"
    out, n = scrub(raw, "en", "k")
    assert "Demo Courier" in out and "Demo Bank" in out and "0722" not in out and "gmail" not in out
    assert "shop.ro" not in out and "OTP code" in out and n >= 5
    assert scrub(out, "en", "k") == (out, 0)
