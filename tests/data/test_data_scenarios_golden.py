"""Scenariile și setul de aur."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

import pytest

from versoml.contracts import Complaint, RuleContext, Scenario, Verdict
from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.aml_world import demo_mule
from versoml.data.golden import GENERATED_300, GOLDEN_40, generated_300, golden_40, read_jsonl
from versoml.data.oracle import expected_outcome
from versoml.data.scenarios import SCENARIOS, _scenario_params, build_case, build_scenario, list_scenarios
from versoml.data.text import has_cedilla

RECOVERY = {"RECHEMARE", "CHARGEBACK", "RECUPERARE_PROPUSA", "NU_RECOMANDAM_RECUPERARE", None}


def test_scenarios_cover_contract_and_demo():
    assert {s.value for s in Scenario} | {"demo_t1", "demo_t1_victima2"} == set(SCENARIOS)
    assert all({"id", "title", "description", "channel", "expected_verdict"} == set(s) for s in list_scenarios())


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_bundle_is_complete_and_consistent(sid):
    b = build_scenario(sid)
    assert isinstance(b.complaint, Complaint) and b.complaint.synthetic
    ctx = RuleContext.model_validate(b.rule_context_hints)
    assert ctx.case_id == b.complaint.case_id
    assert b.expected["rambursare_t1"] == SCENARIOS[sid].expected_verdict.value
    assert b.expected == {**expected_outcome(b.rule_context_hints), "injection_suspected": b.expected["injection_suspected"],
                          "aml_lead": b.expected["aml_lead"]}
    assert not has_cedilla(b.complaint.text)
    assert b.records["customer"]["customer_ref"] == SCENARIOS[sid].customer_ref
    assert build_scenario(sid).model_dump(mode="json") == b.model_dump(mode="json")   # determinist


def test_demo_t1():
    b = build_scenario("demo_t1")
    h, r = b.rule_context_hints, b.records
    assert b.complaint.customer_ref == "CUST-DEMO-01" and r["customer"]["alias"] == "Demo Customer 01"
    assert r["accounts"][0]["balance"] == pytest.approx(12450.00)
    assert any(a.kind == "sms" and a.content == art.DEMO_SMS_TEXT for a in b.complaint.attachments)
    assert h["seconds_after_click"] == 118 and h["amount"]["value"] == 3200.0 and h["channel"] == "transfer"
    assert h["device_known"] is False and h["sca_method"] == "sms_otp" and h["screen_showed_amount_and_payee"] is False
    enroll = [a for a in r["auth_events"] if a["purpose"] == "device_enrollment"]
    assert enroll[0]["method"] == "sms_otp" and enroll[0]["screen_showed_amount_and_payee"] is False
    ben = r["beneficiary"]
    assert ben["iban"] == demo_mule(7)["iban"] and ids.iban_bank_code(ben["iban"]) == "BDEM" and ben["name"]
    assert h["beneficiary_new"] is True
    assert b.expected["rambursare_t1"] == "RAMBURSEAZA" and b.expected["recovery"] == "RECHEMARE"
    assert b.expected["t1_deadline"] == "2026-10-29T23:59:59+02:00" and b.expected["aml_lead"] is True
    assert b.live and r["post_transfer"]["to_iban"] == ben["iban"] and r["post_transfer"]["amount"] == 3200.0


def test_demo_t1_victima2_same_mule():
    b1, b2 = build_scenario("demo_t1"), build_scenario("demo_t1_victima2")
    h = b2.rule_context_hints
    assert b2.complaint.customer_ref == "CUST-DEMO-02"
    assert b2.records["beneficiary"]["iban"] == b1.records["beneficiary"]["iban"]
    assert h["channel"] == "transfer_instant" and h["dispute_type"] == "app" and h["amount"]["value"] == 4750.0
    assert h["screen_showed_amount_and_payee"] is True and h["device_known"] is True
    assert art.SCAM_PHONE_CONT_SIGUR in b2.complaint.text
    assert b2.expected["rambursare_t1"] == "NU_SE_APLICA_T1" and b2.expected["requires_human"] is True
    assert b2.expected["recovery"] == "RECHEMARE"


def test_injection_does_not_change_outcome():
    p = _scenario_params(7)["injectie_document"]
    with_inj = build_case(p)
    without = build_case(replace(p, injection=None, scenario="phishing_link"))
    keys = ("rambursare_t1", "requires_human", "recovery", "chargeback_reason", "t1_deadline")
    assert {k: with_inj.expected[k] for k in keys} == {k: without.expected[k] for k in keys}
    assert with_inj.expected["injection_suspected"] is True
    assert any("Ignore all previous instructions" in a.content for a in with_inj.complaint.attachments)


@pytest.fixture(scope="module")
def golden():
    return read_jsonl(GOLDEN_40), read_jsonl(GENERATED_300)


def test_golden_files_schema(golden):
    g40, g300 = golden
    assert len(g40) == 40 and len(g300) == 300
    for line in g40 + g300:
        assert {"id", "scenario", "complaint", "rule_context", "expected"} <= set(line)
        Complaint.model_validate(line["complaint"])
        ctx = RuleContext.model_validate(line["rule_context"])
        e = line["expected"]
        assert set(e) == {"rambursare_t1", "requires_human", "recovery", "chargeback_reason", "t1_deadline",
                          "injection_suspected"}
        Verdict(e["rambursare_t1"])
        assert e["recovery"] in RECOVERY and isinstance(e["requires_human"], bool)
        assert {k: e[k] for k in e if k != "injection_suspected"} == expected_outcome(ctx)
        assert line["complaint"]["case_id"] == ctx.case_id
        assert not has_cedilla(line["complaint"]["text"])
    assert len({l["id"] for l in g40}) == 40 and len({l["complaint"]["case_id"] for l in g40 + g300}) == 340


def test_golden_coverage(golden):
    g40, _ = golden
    per = Counter(l["scenario"] for l in g40)
    for s in Scenario:
        assert per[s.value] >= 3, s
    assert per["demo_t1"] == 1 and per["demo_t1_victima2"] == 1
    tags = {t for l in g40 for t in l["tags"]}
    assert {"weekend", "paste_ortodox", "rusalii", "1_decembrie", "craciun", "anul_nou", "boboteaza", "1_mai",
            "schimbare_ora", "fus_orar", "cap_edge", "13_luni", "hold_signal"} <= tags
    verdicts = Counter(l["expected"]["rambursare_t1"] for l in g40)
    assert set(verdicts) == {"RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE", "EXCEPTIE_FRAUDA_CLIENT", "RESPINGE_TARDIV",
                             "NU_SE_APLICA_T1"}
    inj = [l for l in g40 if l["scenario"] == "injectie_document"]
    assert inj and all(l["expected"]["injection_suspected"] for l in inj)


def test_golden_deadline_spot_checks(golden):
    g40, _ = golden
    by_tag = {t: l for l in g40 for t in l["tags"]}
    assert by_tag["paste_ortodox"]["expected"]["t1_deadline"] == "2026-04-14T23:59:59+03:00"
    assert by_tag["1_decembrie"]["expected"]["t1_deadline"] == "2025-12-02T23:59:59+02:00"
    assert by_tag["schimbare_ora"]["expected"]["t1_deadline"] == "2026-10-26T23:59:59+02:00"
    assert by_tag["fus_orar"]["rule_context"]["notified_at"].endswith("+00:00")
    assert by_tag["fus_orar"]["expected"]["t1_deadline"] == "2026-10-29T23:59:59+02:00"
    assert by_tag["limita_inclusiva"]["expected"]["rambursare_t1"] == "RAMBURSEAZA"
    assert by_tag["cap_edge"]["expected"]["rambursare_t1"] in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")
    caps = {l["rule_context"]["amount"]["value"]: l["expected"]["rambursare_t1"] for l in g40 if "cap_edge" in l["tags"]}
    assert caps == {5000.0: "RAMBURSEAZA", 5000.01: "RAMBURSEAZA_CU_APROBARE"}


def test_golden_files_are_reproducible(golden):
    g40, g300 = golden
    assert json.dumps(golden_40(7), ensure_ascii=False) == json.dumps(g40, ensure_ascii=False)
    assert json.dumps(generated_300(7), ensure_ascii=False) == json.dumps(g300, ensure_ascii=False)
