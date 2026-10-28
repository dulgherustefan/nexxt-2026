"""Chunking, ID and mark extraction, and the corpus sources (rules, typologies, precedents)."""

from __future__ import annotations

import re
from pathlib import Path

from versoml.knowledge import corpus
from versoml.knowledge.chunker import MAX_CHARS, chunk_markdown, pack_blocks, parse_sections, split_blocks
from versoml.knowledge.text import marks_in, query_rule_ids, rule_ids_in, weakest_mark

DOC = """# 99 · Test document: rules

Intro paragraph with PAY-03.

## 1. Payments (PAY-xx)

| ID | Rule | Tag |
|---|---|---|
{rows}

```python
# not a heading
x = 1
```

## 2. Surse

- https://example.test/a
"""


def _doc(tmp_path: Path, rows: int = 40) -> Path:
    body = "\n".join(f"| PAY-{i:02d} | Plata {i} se rambursează la sfârșitul zilei lucrătoare următoare, "
                     f"conform regulii {i}. | [P] |" for i in range(1, rows + 1))
    path = tmp_path / "99_test.md"
    path.write_text(DOC.format(rows=body), encoding="utf-8")
    return path


def test_headings_inside_code_fences_are_not_sections():
    sections = parse_sections("# T\n\n## A\ntext\n```\n# comment\n```\n## B\nmore\n")
    assert [s.path for s in sections] == [["T", "A"], ["T", "B"]]


def test_long_tables_split_with_the_header_repeated(tmp_path):
    chunks = chunk_markdown(_doc(tmp_path), root=tmp_path)
    table_parts = [c for c in chunks if "#1-payments-pay-xx" in c.id]
    assert len(table_parts) >= 2
    for c in table_parts:
        assert c.text.startswith("| ID | Rule | Tag |\n|---|---|---|")
        assert len(c.text) <= MAX_CHARS + 200
    assert table_parts[0].id == "ctx:99_test#1-payments-pay-xx"
    assert table_parts[1].id == "ctx:99_test#1-payments-pay-xx-2"
    # every row is in exactly one part, and the rule IDs follow their rows
    all_ids = [rid for c in table_parts for rid in c.rule_ids]
    assert sorted(all_ids) == [f"PAY-{i:02d}" for i in range(1, 41)]
    assert table_parts[0].title == "99 · Test document > 1. Payments (PAY-xx)"
    assert table_parts[0].confidence == "P"


def test_bibliography_and_code_only_parts_are_skipped(tmp_path):
    chunks = chunk_markdown(_doc(tmp_path), root=tmp_path)
    assert not any("surse" in c.id for c in chunks)
    assert not any(c.text.lstrip().startswith("```python") for c in chunks)
    assert chunks[0].id == "ctx:99_test#intro" and chunks[0].rule_ids == ["PAY-03"]


def test_prose_parts_overlap():
    para = " ".join(f"Sentence number {i} explains the refund rule in plain words." for i in range(80))
    parts = pack_blocks(split_blocks(para.split("\n")), max_chars=600)
    assert len(parts) > 2
    assert parts[1].startswith("… ")
    tail = parts[1][2:].split(" Sentence")[0]
    assert tail in parts[0]


def test_rule_ids_shorthand_and_ranges():
    assert rule_ids_in("PAY-01, 03, 04 | AML-07–09 | DSP-01–19 lege") == [
        "PAY-01", "PAY-03", "PAY-04", "AML-07", "AML-08", "AML-09", "DSP-01", "DSP-19"]
    assert rule_ids_in("termen 15.10.2026 PAY-03, 15.10.2026") == ["PAY-03"]
    assert query_rule_ids("what does pay 3 say, and DSP-54?") == ["PAY-03", "DSP-54"]


def test_marks_weakest_and_combined():
    counts = marks_in("[P] text [S/U] more [P — comunicat CURIA 147/26] [Inf] [P-proiect] [Poprire]")
    assert counts["P"] == 2 and counts["U"] == 2 and counts["S"] == 0 and counts["Inf"] == 1
    assert weakest_mark(counts) == "U"
    assert weakest_mark(marks_in("only [P] and [S]")) == "S"
    assert weakest_mark(marks_in("no marks")) is None


def test_cedilla_is_normalized_in_chunks(tmp_path):
    path = tmp_path / "98_ced.md"
    path.write_text("# T\n\n## A\nPlata şi termenul ţinut.\n", encoding="utf-8")
    text = chunk_markdown(path, root=tmp_path)[0].text
    assert "și" in text and "ținut" in text and "ş" not in text and "ţ" not in text


def test_rule_chunks_one_per_rule_with_mark_and_source():
    from versoml.shared.rules.registry import all_rules

    chunks = corpus.rule_chunks()
    assert [c.id for c in chunks] == [f"rule:{s.rule_id}" for s in all_rules()]
    pay03 = next(c for c in chunks if c.id == "rule:PAY-03")
    assert pay03.kind == "rule" and pay03.confidence == "P"
    assert "Confidence: [P]" in pay03.text and "Legal basis:" in pay03.text
    assert pay03.source.startswith("docs/context/11_reguli_kyc_aml_credit_plati_reclamatii.md")
    assert "PSP rambursează imediat" in pay03.text  # the Romanian catalog row is quoted
    assert "DSP-05" in pay03.rule_ids  # alias
    # parameter values are run-time settings, so they are not in the text
    assert not re.search(r"auto_refund_cap_ron = ", " ".join(c.text for c in chunks))


def test_static_corpus_ids_are_unique_and_well_formed():
    chunks = corpus.build_static_corpus()
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    pattern = re.compile(r"^(rule:[A-Z]{2,4}-\d{2}|ctx:[0-9a-z_]+#[0-9a-z-]+|typ:[a-z0-9_]+(#cues)?|case:[0-9a-z-]+#[0-9a-z-]+)$")
    assert all(pattern.match(i) for i in ids), [i for i in ids if not pattern.match(i)][:5]
    kinds = {c.kind for c in chunks}
    assert {"rule", "law", "guidance", "case_study"} <= kinds
    assert all(c.confidence in (None, "P", "S", "U") for c in chunks)


def test_case_studies_one_chunk_per_numbered_case():
    chunks = corpus.chunk_case_studies(corpus.CASE_STUDIES, root=corpus.ROOT)
    numbered = [c for c in chunks if re.search(r"#\d+$", c.id)]
    assert [int(c.id.rsplit("#", 1)[1]) for c in numbered] == list(range(1, 15))
    assert all(c.kind == "case_study" for c in chunks)
    assert "Revolut" in next(c for c in chunks if c.id.endswith("#10")).text


def test_typologies_missing_or_invalid_file_is_skipped(tmp_path):
    assert corpus.typology_chunks(tmp_path / "missing.yaml") == []
    bad = tmp_path / "bad.yaml"
    bad.write_text("typologies: [unclosed", encoding="utf-8")
    assert corpus.typology_chunks(bad) == []
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text("something: else\n", encoding="utf-8")
    assert corpus.typology_chunks(wrong) == []


def test_typology_chunks_from_the_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "ROOT", tmp_path)
    path = tmp_path / "t.yaml"
    path.write_text("""
typologies:
  - id: safe_account_test
    name: Safe account transfer
    name_ro: Transfer într-un cont sigur
    family: app_scam
    psd2_class: authorized_push_payment
    channels: [transfer]
    maps_to_scenario: cont_sigur
    story: A caller says the savings are at risk (PAY-12).
    steps: [Call, Transfer]
    complaint_cues_en: [They told me to move my money to a safe account.]
    complaint_cues_ro: [Mi-au zis să mut banii într-un cont sigur.]
    bank_signals: [New beneficiary]
    sources: [{title: Report, publisher: Example, url: "https://example.test/r", date: "2026", confidence: S}]
    confidence: S
  - {name: no id, skipped: true}
""", encoding="utf-8")
    chunks = corpus.typology_chunks(path)
    assert [c.id for c in chunks] == ["typ:safe_account_test", "typ:safe_account_test#cues"]
    main, cues = chunks
    assert main.kind == "typology" and main.confidence == "S" and main.rule_ids == ["PAY-12"]
    assert main.meta["scenario"] == "cont_sigur" and main.meta["sources"][0]["url"] == "https://example.test/r"
    assert "safe account" in cues.text and "cont sigur" in cues.text


def test_precedents_are_pseudonymized_and_carry_outcomes():
    from versoml.shared.privacy import PrivacyProxy

    precedents = corpus.golden_precedents()
    assert len(precedents) >= 300
    proxy = PrivacyProxy()
    assert all(not proxy.find_raw_pii(c.text) for c in precedents)
    first = next(c for c in precedents if c.id == "prec:CT-2026-900001")
    assert first.meta["outcome"]["verdict"] == "RAMBURSEAZA" and first.meta["scenario"] == "phishing_link"
    assert "PAY-03" in first.rule_ids
    assert "<PERSOANA_1>" in first.text  # the signature name is gone
    # hidden instructions of the injection cases never enter the knowledge base
    injected = [c for c in precedents if c.meta["scenario"] == "injectie_document"]
    assert injected
    assert all("previous instructions" not in c.text.lower() and "supervisor" not in c.text.lower() for c in injected)


def test_inline_names_are_pseudonymized_but_merchants_stay():
    safe = corpus.safe_case_text("I sent 300 RON to Ana Pop at Demo Bank. Then Ana Pop called again.\nIon Ionescu", "T1")
    assert "Ana Pop" not in safe and "Ion Ionescu" not in safe and "Demo Bank" in safe
    assert safe.count("<PERSOANA_2>") == 2  # stable within the text
