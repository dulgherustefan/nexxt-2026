"""M6 (legarea cazurilor) și M7 (contrafactual)."""

from __future__ import annotations

import pytest

from versoml.contracts import RuleContext
from versoml.data import artifacts as art
from versoml.data.oracle import expected_outcome
from versoml.data.scenarios import SCENARIOS, build_scenario, to_dispute_facts
from versoml.ml.m6_entity_resolution import link_cases, normalize_company
from versoml.ml.m7_counterfactual import counterfactual


def test_demo_cases_linked_by_iban():
    refs = [to_dispute_facts(build_scenario(s)).model_dump(mode="json") for s in ("demo_t1", "demo_t1_victima2", "sim_swap")]
    clusters = link_cases(refs)
    demo = {SCENARIOS["demo_t1"].case_id, SCENARIOS["demo_t1_victima2"].case_id}
    cl = next(c for c in clusters if demo <= set(c["case_ids"]))
    assert any(l["reason"] == "iban" for l in cl["links"])
    assert SCENARIOS["sim_swap"].case_id not in cl["case_ids"]
    assert cl["shared"]["ibans"] and cl["amount_total"] == pytest.approx(3200 + 4750)


def test_domain_phone_company_and_device_links():
    refs = [
        {"case_id": "A", "url": f"https://plata.{art.SCAM_DOMAIN_DEMO}/x", "beneficiary_name": "Ion Popescu"},
        {"case_id": "B", "domain": art.SCAM_DOMAIN_DEMO, "beneficiary_name": "Ion Popescu"},
        {"case_id": "C", "phone": "0700 000 111"},
        {"case_id": "D", "attack": {"phone": "+40700000111"}},
        {"case_id": "E", "beneficiary": {"name": "EXPRES LIVRARE DEMO SRL"}},
        {"case_id": "F", "beneficiary_name": "Expres Livrare Demo S.R.L."},
        {"case_id": "G", "device_fingerprint": "fp-1"},
        {"case_id": "H", "device": "fp-1"},
        {"case_id": "I", "beneficiary_name": "Ion Popescu"},        # numele de persoană nu leagă singur
    ]
    clusters = {tuple(c["case_ids"]): {l["reason"] for l in c["links"]} for c in link_cases(refs)}
    assert clusters[("A", "B")] == {"domeniu"}
    assert clusters[("C", "D")] == {"telefon"}
    assert clusters[("E", "F")] == {"denumire_firma"}
    assert clusters[("G", "H")] == {"dispozitiv"}
    assert not any("I" in k for k in clusters)
    assert normalize_company("EXPRES LIVRARE DEMO S.R.L.") == normalize_company("Expres Livrare Demo SRL") == "expres livrare demo"


def test_inel_ring_linked(trained):
    assert trained["metrics"]["m6_entity_resolution"]["inel_3_victims_linked"] is True
    assert trained["metrics"]["m6_entity_resolution"]["demo_t1_linked_to_victima2"] is True


def _decide(ctx: dict) -> dict:
    RuleContext.model_validate(ctx)
    return {"decision": expected_outcome(ctx)["rambursare_t1"]}


def test_counterfactual_on_demo_case():
    ctx = build_scenario("demo_t1").rule_context_hints
    res = counterfactual(_decide, ctx, ["screen_showed_amount_and_payee", "device_known", "hold_signal", "amount", "case_id"],
                         variants={"amount": [{"value": 6400.0, "currency": "RON"}]})
    assert res["base"]["decision"] == "RAMBURSEAZA"
    assert "screen_showed_amount_and_payee" not in res["fragile_fields"]      # C-70/25: rambursarea rămâne
    assert {"hold_signal", "amount"} <= set(res["fragile_fields"])
    assert 0 < res["change_rate"] < 1
    removed_case = [r for r in res["results"] if r["field"] == "case_id"]
    assert removed_case and removed_case[0]["error"] is not None            # câmp obligatoriu eliminat


def test_counterfactual_generic():
    res = counterfactual(lambda c: "DA" if c.get("x", 0) > 1 else "NU", {"x": 2, "y": True}, ["x", "y"])
    assert res["fragile_fields"] == ["x"] and res["n_variants"] == 5
