"""The router's plan (which collectors run, and why), the graph's Send fan-out, the pipeline the console draws,
and the plain-language reason for each decision."""

from __future__ import annotations

from langgraph.types import Send

from versoml.zone_client import agents as A
from versoml.zone_client.graph import route_collectors
from versoml.zone_client.reasons import decision_reasons, scenario_phrase, sentence
from versoml.zone_client.routing import COLLECTORS, plan

TRANSFER = {"tx_id": "TX-1", "channel": "transfer", "kind": "transfer", "session_id": "SES-1"}
POS = {"tx_id": "TX-2", "channel": "card", "kind": "card_pos", "session_id": None}
NOTHING = {"ibans": [], "domains": [], "phones": []}


def runs(steps):
    return {s["node"]: s["run"] for s in steps}


def test_a_transfer_after_a_link_runs_everything():
    steps = plan(tx=TRANSFER, customer_ref="C", attack_domains=["livrare-bancademo.example"], merchant_domain=None,
                 indicators={"ibans": ["RO61BDEM1777286093723598"], "domains": ["livrare-bancademo.example"], "phones": []},
                 narrative_chars=300)
    assert [s["node"] for s in steps] == COLLECTORS and all(runs(steps).values())
    domain = next(s for s in steps if s["node"] == "colector_domeniu")
    assert domain["reason"] == "Domain check runs: the complaint mentions a link (livrare-bancademo.example)"
    campaign = next(s for s in steps if s["node"] == "colector_campanie")
    assert campaign["reason"] == "Campaign check runs: the payee account and the link can be compared with other cases"


def test_a_card_payment_at_a_shop_skips_the_device_and_domain_checks():
    steps = runs(plan(tx=POS, customer_ref="C", attack_domains=[], merchant_domain=None, indicators=NOTHING,
                      narrative_chars=10))
    assert steps == {"colector_tranzactie": True, "colector_sca": True, "colector_dispozitiv": False,
                     "colector_domeniu": False, "colector_campanie": False}


def test_an_online_shop_gets_a_domain_check_without_a_link():
    steps = plan(tx={**POS, "kind": "card_ecom"}, customer_ref="C", attack_domains=[], merchant_domain="modademo.example",
                 indicators=NOTHING, narrative_chars=100)
    assert runs(steps)["colector_domeniu"] and "online shop (modademo.example)" in steps[3]["reason"]
    assert runs(steps)["colector_dispozitiv"] is True


def test_declared_facts_only_reads_the_history_and_the_story():
    known = runs(plan(tx=None, customer_ref="C", attack_domains=[], merchant_domain=None, indicators=NOTHING,
                      narrative_chars=120))
    assert known == {"colector_tranzactie": True, "colector_sca": False, "colector_dispozitiv": False,
                     "colector_domeniu": False, "colector_campanie": True}
    unknown = plan(tx=None, customer_ref=None, attack_domains=[], merchant_domain=None, indicators=NOTHING,
                   narrative_chars=0)
    assert not any(runs(unknown).values())
    assert all(s["reason"] and "—" not in s["reason"] for s in unknown)


def test_route_collectors_sends_only_the_chosen_ones():
    state = {"case_id": "CT-1", "routing": [{"node": "colector_sca", "run": True}, {"node": "colector_domeniu", "run": False},
                                            {"node": "colector_campanie", "run": True}]}
    sends = route_collectors(state)
    assert [s.node for s in sends] == ["colector_sca", "colector_campanie"] and all(isinstance(s, Send) for s in sends)
    assert route_collectors({"routing": [{"node": "colector_sca", "run": False}]}) == "motor_reguli"


def test_pipeline_drawing_matches_the_graph():
    ids = {n["id"] for n in A.PIPELINE_NODES}
    assert {"identificare", "router", "colector_campanie"} <= ids
    for source, target in A.PIPELINE_EDGES:
        assert source in ids and target in ids, (source, target)
    edges = set(A.PIPELINE_EDGES)
    assert ("receptor", "identificare") in edges and ("ceasornicar", "router") in edges
    assert all(("router", c) in edges and (c, "motor_reguli") in edges for c in COLLECTORS)
    assert ("receptor", "clasificator") not in edges and ("ceasornicar", "colector_sca") not in edges
    from versoml.zone_client.graph import build_graph

    nodes = set(build_graph().get_graph().nodes)
    assert ids - {"procuror", "avocat", "cantaritor", "filtru_zid"} <= nodes


# ---------------------------------------------------------------- plain-language reasons

CTX = {"amount": {"value": 3200.0, "currency": "RON"}, "dispute_type": "neautorizata",
       "screen_showed_amount_and_payee": False}


def test_refund_now_names_the_rule():
    s = sentence({"question": "rambursare_t1", "decision": "RAMBURSEAZA", "rule_ids": ["PAY-03", "PAY-15", "PAY-02"]},
                 CTX, {"claims_unauthorized": True})
    assert s == {"rule_id": "PAY-03", "question": "rambursare_t1", "decision": "RAMBURSEAZA",
                 "sentence": "Refund now: the customer says it wasn't them and the bank can't show they approved this "
                             "payment (PAY-03)."}


def test_approval_names_the_escalating_rule_only():
    hits = [{"rule_id": "DSP-59", "outcome": "sub_plafon"}, {"rule_id": "URM-03", "outcome": "semnale_de_risc"}]
    s = sentence({"question": "rambursare_t1", "decision": "RAMBURSEAZA_CU_APROBARE",
                  "rule_ids": ["PAY-03", "DSP-59", "URM-03"], "deadline": "2026-10-29T21:59:59+00:00"}, CTX, {}, hits)
    assert s["rule_id"] == "URM-03" and "because the customer has risk signals" in s["sentence"]
    assert "29 Oct 2026, 23:59" in s["sentence"] and "limit" not in s["sentence"]


def test_a_reading_without_a_live_model_gets_its_own_reason():
    hits = [{"rule_id": "DSP-59", "outcome": "sub_plafon"}, {"rule_id": "DSP-57", "outcome": "extragere_de_confirmat"}]
    s = sentence({"question": "rambursare_t1", "decision": "RAMBURSEAZA_CU_APROBARE",
                  "rule_ids": ["PAY-03", "DSP-59", "DSP-57"], "deadline": "2026-10-29T21:59:59+00:00"}, CTX, {}, hits)
    assert s["rule_id"] == "DSP-57" and "because the complaint was read without a live model:" in s["sentence"]
    assert "second look" not in s["sentence"]
    injected = [{"rule_id": "DSP-57", "outcome": "DSP_SECURITY_SIGNAL"}]
    s = sentence({"question": "rambursare_t1", "decision": "RAMBURSEAZA_CU_APROBARE", "rule_ids": ["PAY-03", "DSP-57"]},
                 CTX, {}, injected)
    assert "the complaint text needs a check against the bank's records" in s["sentence"]


def test_every_verdict_gets_one_sentence_without_dashes():
    decisions = [
        {"question": "rambursare_t1", "decision": v, "rule_ids": r} for v, r in (
            ("RESPINGE_TARDIV", ["PAY-01"]), ("NU_SE_APLICA_T1", ["PAY-12"]), ("EXCEPTIE_FRAUDA_CLIENT", ["PAY-03"]),
            ("INFORMATII_SUPLIMENTARE", ["DSP-53", "PAY-03"]))] + [
        {"question": "recuperare_escroc", "decision": "RECHEMARE", "rule_ids": ["REC-04"]},
        {"question": "recuperare_escroc", "decision": "CHARGEBACK", "rule_ids": ["DSP-52"]},
        {"question": "recuperare_client", "decision": "NU_RECOMANDAM_RECUPERARE", "rule_ids": ["PAY-06"]},
        {"question": "raspuns_reclamatie", "decision": "INFORMATII_SUPLIMENTARE", "rule_ids": ["DSP-53", "CMP-01"],
         "missing_evidence": ["the payment details (date, amount and payee)"], "deadline": "2026-11-18T21:59:59+00:00"}]
    out = decision_reasons(decisions, CTX, {})
    assert [r["rule_id"] for r in out] == ["PAY-01", "PAY-12", "PAY-03", "DSP-53", "REC-04", "DSP-52", "PAY-06", "DSP-53"]
    assert out[3]["sentence"].startswith("Ask for more information: the payment could not be found")
    assert "the payment details (date, amount and payee)" in out[-1]["sentence"]
    for r in out:
        assert r["sentence"].endswith(f"({r['rule_id']}).") and "—" not in r["sentence"]


def test_scenario_phrase():
    assert scenario_phrase("phishing_link") == "Paid after a fake link"
    assert scenario_phrase(None, "neautorizata", {"tx_id": None}) == "Payment not identified yet"
    assert scenario_phrase(None, "app") == "Approved under a scam"
