"""Testul de neinterferență pe funcții de decizie de jucărie: curată, cu scurgere, dependentă de AML."""

from __future__ import annotations

import json

from versoml.wall import adversarial_aml_states, empty_aml_state, find_terms, run_noninterference

CASES = [
    {"case_id": "CT-2026-000001", "amount": 3200, "scenario": "phishing_link"},
    {"case_id": "CT-2026-000002", "amount": 18000, "scenario": "cont_sigur"},
    {"case_id": "CT-2026-000003", "amount": 450, "scenario": "card_ecom_fara_3ds"},
]


def pure_decide(case, aml_state):
    verdict = "RAMBURSEAZA" if case["amount"] <= 5000 else "RAMBURSEAZA_CU_APROBARE"
    return {
        "case_id": case["case_id"],
        "decision": verdict,
        "rule_ids": ["PAY-03", "PAY-15"],
        "letter": {"subject": "Răspuns la contestație", "body": f"Am rambursat {case['amount']} lei."},
        "ts": "variază la fiecare rulare",
    }


def leaky_decide(case, aml_state):
    out = pure_decide(case, aml_state)
    notes = [n for lead in aml_state.get("leads", []) for n in lead.get("notes", [])]
    if notes:
        out["letter"]["body"] += " " + notes[0]
    return out


def interfering_decide(case, aml_state):
    out = pure_decide(case, aml_state)
    if aml_state.get("leads"):
        out["decision"] = "EXCEPTIE_FRAUDA_CLIENT"
    return out


def fragile_decide(case, aml_state):
    if len(aml_state.get("leads", [])) > 10:
        raise RuntimeError("prea multe piste")
    return pure_decide(case, aml_state)


def test_adversarial_states_are_hostile_and_registered(registry):
    states = adversarial_aml_states(4, registry=registry)
    assert len(states) == 4 and len({s["label"] for s in states}) == 4
    for state in states:
        dumped = json.dumps(state, ensure_ascii=False)
        assert registry.scan(dumped) >= 1
        assert find_terms(" ".join(state["notes"]))
        assert "hold_signal" not in dumped and "approved_by" not in dumped
    assert len(states[-1]["leads"]) > 10
    assert empty_aml_state()["leads"] == []


def test_pure_decide_passes(registry):
    states = adversarial_aml_states(4, registry=registry)
    report = run_noninterference(pure_decide, CASES, states, registry=registry)
    assert report["passed"] and report["runs"] == len(CASES) * 4
    assert report["leaks"] == 0 and report["mismatches"] == 0 and report["details"] == []


def test_leaky_decide_is_caught_without_copying_aml_content(registry):
    states = adversarial_aml_states(3, registry=registry)
    report = run_noninterference(leaky_decide, CASES, states, registry=registry)
    assert not report["passed"] and report["leaks"] == 9 and report["canary_total"] >= 9
    assert report["mismatches"] == 9
    leak = next(d for d in report["details"] if d["kind"] == "leak")
    assert leak["terms"] and leak["canaries"] >= 1
    dumped = json.dumps(report, ensure_ascii=False)
    assert registry.scan(dumped) == 0


def test_interfering_decide_is_caught(registry):
    report = run_noninterference(interfering_decide, CASES[:1], adversarial_aml_states(2, registry=registry),
                                 registry=registry)
    assert not report["passed"] and report["mismatches"] == 2 and report["leaks"] == 0
    assert report["details"][0]["paths"] == ["$.decision"]


def test_errors_only_under_aml_state_count_as_interference(registry):
    report = run_noninterference(fragile_decide, CASES[:1], adversarial_aml_states(3, registry=registry),
                                 registry=registry)
    assert not report["passed"] and report["mismatches"] == 1
    assert report["details"][0]["kind"] == "error" and report["details"][0]["error"] == "RuntimeError"


def test_default_states_are_generated(registry):
    report = run_noninterference(pure_decide, CASES[:1], registry=registry)
    assert report["passed"] and report["states"] == 5 and report["runs"] == 5
