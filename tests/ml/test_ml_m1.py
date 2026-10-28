"""M1: the claim classifier, a stacked ensemble (char, word, Complement NB, embedding members; LR meta-learner)."""

from __future__ import annotations

import numpy as np
import pytest

from versoml.contracts import Classification
from versoml.data.complaints import generate_corpus
from versoml.data.corpus_llm import load_llm_corpus
from versoml.data.scenarios import SCENARIOS, build_scenario
from versoml.ml import m1_classifier as M
from versoml.ml.m1_classifier import classify_complaint, normalize_text


def test_corpus_mixes_templates_typologies_and_llm_rows():
    rows = M.build_corpus(7, n_templates=4, n_typology=2)
    src = {r["source"] for r in rows}
    assert {"template", "typology", "llm"} <= src
    assert {r["language"] for r in rows} == {"en", "ro"} and {r["group"] for r in rows} == {0, 1, 2}
    # vague and multi-issue complaints have no single label: they never train the model
    assert all(r.get("eval_only") == bool(r.get("expect_ambiguous")) for r in rows if r["source"] == "llm")


def test_ensemble_matches_or_beats_its_best_member_on_held_out_templates(m1_honest):
    ho = m1_honest["eval"]["held_out_templates"]
    for head in ("scenario", "channel", "dispute_type"):
        best = max(ho[head][k]["accuracy"] for k in M.TEXT_MEMBERS)
        assert ho[head]["ensemble_fallback"]["accuracy"] >= best - 0.01, head
    assert ho["scenario"]["ensemble_served"]["accuracy"] >= 0.85
    assert 0.0 <= ho["scenario"]["ensemble_served"]["ece"] <= 0.08


def test_honest_splits_are_reported_and_harder_than_the_leaky_one(m1_honest):
    ev = m1_honest["eval"]
    assert {"held_out_templates", "typo_noise", "cross_lingual_en_to_ro", "templates_to_llm_paraphrases",
            "hard_negatives", "random_split_leaky"} <= set(ev)
    leaky = ev["random_split_leaky"]["scenario"]["ensemble_served"]["accuracy"]
    assert ev["cross_lingual_en_to_ro"]["scenario"]["ensemble_served"]["accuracy"] < leaky
    assert ev["templates_to_llm_paraphrases"]["scenario"]["ensemble_served"]["accuracy"] < leaky
    amb = ev["hard_negatives"]["ambiguity"]
    assert amb["vague_or_multi_issue_flagged"] > amb["clear_hard_negatives_flagged"]


def test_held_out_template_groups_share_no_story_sentence():
    from versoml.data.complaints import T
    from versoml.data.complaints_ro import N_GROUPS, T_RO

    for templates in (T, T_RO):
        for tpl in templates.values():
            for slot in tpl["story"]:
                if len(slot) >= N_GROUPS:
                    assert not set(slot[2::N_GROUPS]) & (set(slot[0::N_GROUPS]) | set(slot[1::N_GROUPS]))


def test_trained_model_metadata(trained):
    m = trained["metrics"]["m1_classifier"]
    assert m["model_version"].startswith("m1-stack-")
    assert m["members"] == ["char", "word", "cnb", "emb"]
    assert m["corpus"]["llm"] >= 1000 and m["languages"]["ro"] >= 2000
    for head in ("channel", "dispute_type", "scenario"):
        assert 0.2 <= m["temperature"][head]["fallback"] <= 5.0


def test_fresh_held_out_accuracy(trained):
    rows = generate_corpus(n_per_scenario=15, seed=4242)
    pred = [classify_complaint(r["text"], {**r["meta"], "attachments": r["attachments"]}, models_dir=trained["dir"],
                               allow_live=False) for r in rows]
    acc = np.mean([p.scenario.value == r["scenario"] for p, r in zip(pred, rows)])
    assert acc >= 0.85


def test_romanian_template_accuracy(trained):
    rows = generate_corpus(n_per_scenario=10, seed=4243, language="ro")
    pred = [classify_complaint(r["text"], {**r["meta"], "attachments": r["attachments"]}, models_dir=trained["dir"],
                               allow_live=False) for r in rows]
    assert np.mean([p.scenario.value == r["scenario"] for p, r in zip(pred, rows)]) >= 0.8


def test_scenarios_classified(trained):
    for sid in SCENARIOS:
        b = build_scenario(sid)
        c = classify_complaint(b.complaint.text, {"attachments": [a.model_dump() for a in b.complaint.attachments],
                                                  "channel_hint": b.complaint.channel_hint, "source": b.complaint.source},
                               models_dir=trained["dir"], allow_live=False)
        assert isinstance(c, Classification) and c.method == "ml" and c.model_version.startswith("m1-")
        assert c.scenario.value == b.rule_context_hints["scenario"], sid
        assert c.channel.value == b.rule_context_hints["channel"], sid


def test_fallback_meta_learner_without_embeddings(trained, monkeypatch):
    # no embedding module at all: the text-only meta-learner answers
    monkeypatch.setattr(M, "_query_embedding", lambda text, allow_live: None)
    c = classify_complaint("Am primit un SMS de la curier cu un link si mi-au plecat 2.300 lei din cont, nu am facut eu "
                           "transferul", models_dir=trained["dir"])
    assert c.model_version.endswith("+text")
    assert c.scenario.value == "phishing_link" and abs(sum(v for k, v in c.proba.items() if k.startswith("scenario:")) - 1) < 0.02


def test_embedding_member_used_when_the_vector_is_cached(trained):
    model = M._load(trained["dir"])
    if "full" not in model["metas"]["scenario"]:
        pytest.skip("no committed embedding cache")
    row = next(r for r in load_llm_corpus() if not r.get("expect_ambiguous"))
    c = classify_complaint(row["text"], models_dir=trained["dir"], allow_live=False)   # cache only, no network
    assert c.model_version.endswith("+emb")
    assert isinstance(c, Classification)


def test_cedilla_and_case_normalization(trained):
    a = "Got a text from the courier, paid the fee and then RON 3,200 left my account. Kind regards, Ştefan Popescu"
    b = a.replace("Ş", "Ș").upper()
    assert normalize_text(a) == normalize_text(b)
    ca = classify_complaint(a, models_dir=trained["dir"], allow_live=False)
    cb = classify_complaint(b, models_dir=trained["dir"], allow_live=False)
    assert ca.scenario == cb.scenario and abs(ca.probability - cb.probability) < 1e-9


def test_probabilities_and_ambiguity(trained):
    c = classify_complaint("Hello, I have a question.", models_dir=trained["dir"], allow_live=False)
    scen = {k: v for k, v in c.proba.items() if k.startswith("scenario:")}
    assert len(scen) == 12 and abs(sum(scen.values()) - 1.0) < 0.02
    assert {k.split(":")[0] for k in c.proba} == {"channel", "dispute_type", "scenario"}
    assert c.ambiguous is True
    clear = classify_complaint(build_scenario("vishing_securitate").complaint.text, models_dir=trained["dir"], allow_live=False)
    assert clear.ambiguous is False and clear.probability > 0.8


def test_mask_pii_hides_contacts_before_embedding():
    masked = M.mask_pii("Call me at +40700123456 or ana.pop@mail.example, card 4111 1111 1111 1111")
    assert "+40700123456" not in masked and "ana.pop@mail.example" not in masked


def test_inference_is_fast(trained):
    import time

    text = "Someone called from the bank and I moved RON 5,000 to a safe account"
    classify_complaint(text, models_dir=trained["dir"], allow_live=False)
    t = time.perf_counter()
    for _ in range(10):
        classify_complaint(text, models_dir=trained["dir"], allow_live=False)
    assert (time.perf_counter() - t) / 10 < 0.05
