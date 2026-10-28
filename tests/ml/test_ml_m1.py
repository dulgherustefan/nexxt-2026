"""M1: clasificatorul de contestații."""

from __future__ import annotations

import numpy as np

from versoml.contracts import Classification
from versoml.data.complaints import generate_corpus
from versoml.data.scenarios import SCENARIOS, build_scenario
from versoml.ml.m1_classifier import classify_complaint, normalize_text


def test_held_out_metrics(trained):
    m = trained["metrics"]["m1_classifier"]
    for head in ("channel", "dispute_type", "scenario"):
        assert m[head]["accuracy"] >= 0.85, head
        assert m[head]["macro_f1"] >= 0.80, head
        assert 0.0 <= m[head]["ece"] <= 0.15, head
    assert m["accuracy_text_only"]["scenario"] >= 0.75


def test_fresh_held_out_accuracy(trained):
    rows = generate_corpus(n_per_scenario=15, seed=4242)
    pred = [classify_complaint(r["text"], {**r["meta"], "attachments": r["attachments"]}, models_dir=trained["dir"])
            for r in rows]
    acc = np.mean([p.scenario.value == r["scenario"] for p, r in zip(pred, rows)])
    assert acc >= 0.85


def test_scenarios_classified(trained):
    for sid in SCENARIOS:
        b = build_scenario(sid)
        c = classify_complaint(b.complaint.text, {"attachments": [a.model_dump() for a in b.complaint.attachments],
                                                  "channel_hint": b.complaint.channel_hint, "source": b.complaint.source},
                               models_dir=trained["dir"])
        assert isinstance(c, Classification) and c.method == "ml" and c.model_version.startswith("m1-")
        assert c.scenario.value == b.rule_context_hints["scenario"], sid
        assert c.channel.value == b.rule_context_hints["channel"], sid


def test_cedilla_and_case_normalization(trained):
    a = "Am primit un SMS de la curier şi am plătit taxa, apoi mi-au luat 3.200 lei din cont"
    b = a.replace("ş", "ș").upper()
    assert normalize_text(a) == normalize_text(b)
    ca, cb = classify_complaint(a, models_dir=trained["dir"]), classify_complaint(b, models_dir=trained["dir"])
    assert ca.scenario == cb.scenario and abs(ca.probability - cb.probability) < 1e-9


def test_probabilities_and_ambiguity(trained):
    c = classify_complaint("Bună ziua, am o întrebare.", models_dir=trained["dir"])
    scen = {k: v for k, v in c.proba.items() if k.startswith("scenario:")}
    assert len(scen) == 12 and abs(sum(scen.values()) - 1.0) < 0.02
    assert {k.split(":")[0] for k in c.proba} == {"channel", "dispute_type", "scenario"}
    assert c.ambiguous is True
    clear = classify_complaint(build_scenario("vishing_securitate").complaint.text, models_dir=trained["dir"])
    assert clear.ambiguous is False and clear.probability > 0.8
