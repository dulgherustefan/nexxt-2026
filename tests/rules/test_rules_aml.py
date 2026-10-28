"""Zona AML: TC-13…TC-16 din docs/context/11 §6, EX-10…EX-12 și extensiile URM-01, URM-02, URM-04."""

from __future__ import annotations

from datetime import datetime

from rules_testkit import TZ, eod, ts
from versoml.contracts import Money, Question, Verdict
from versoml.shared.rules import AmlRuleContext, evaluate_aml
from versoml.shared.rules.packs.aml import onpcsb_window_end, str_correction_deadline, str_hold_until, threshold_report_deadline
from versoml.shared.rules.packs.urm import prohibited_features


def aml(**kw) -> AmlRuleContext:
    base = {"lead_id": "LEAD-SYN-001", "now": ts(2026, 11, 23, 9)}
    base.update(kw)
    return AmlRuleContext(**base)


def outcomes(out) -> dict[str, str]:
    return {h.rule_id: h.outcome for h in out.hits}


def test_TC13_rapoarte_de_prag_rtn_si_rte():
    out = evaluate_aml(aml(now=ts(2026, 11, 26, 18), cash_linked=Money(value=60000.0), threshold_tx_at=ts(2026, 11, 26, 11)))
    assert outcomes(out)["AML-07"] == "AML_RTN_DUE"
    assert next(d for d in out.deadlines if d.rule_id == "AML-09").due_at == eod(2026, 12, 3)
    assert threshold_report_deadline(ts(2026, 11, 26, 11)) == eod(2026, 12, 3)
    rte = evaluate_aml(aml(external_transfers_linked=Money(value=10000.0, currency="EUR")))
    assert outcomes(rte)["AML-08"] == "AML_RTE_DUE"
    below = evaluate_aml(aml(external_transfers_linked=Money(value=9999.99, currency="EUR")))
    assert "AML-08" not in outcomes(below)


def test_TC14_EX10_str_vineri_16_00_tranzactia_asteapta_pana_miercuri():
    out = evaluate_aml(aml(now=ts(2026, 11, 27, 16, 5), suspicion_confirmed=True, transaction_executed=False,
                           str_registered_at=ts(2026, 11, 27, 16)))
    assert outcomes(out)["AML-01"] == "AML_STR_REQUIRED"
    assert outcomes(out)["AML-02"] == "AML_TX_HOLD" and outcomes(out)["AML-03"] == "AML_TX_HOLD"
    assert out.tx_hold_until == ts(2026, 12, 2, 16)
    assert str_hold_until(ts(2026, 11, 27, 16)) == ts(2026, 12, 2, 16)
    rts = out.decisions[0]
    assert rts.question == Question.RTS and rts.decision == Verdict.RTS_PROPUS and rts.requires_human
    assert rts.deadline == ts(2026, 12, 2, 16)


def test_TC15_suspendare_48h_prelungire_72h_si_96h_invalid():
    assert onpcsb_window_end(ts(2026, 11, 23, 10), 48, 48) == ts(2026, 11, 25, 10)
    assert onpcsb_window_end(ts(2026, 11, 25, 10), 72, 72) == ts(2026, 12, 2, 10)
    out = evaluate_aml(aml(suspicion_confirmed=True, transaction_executed=False, str_registered_at=ts(2026, 11, 20, 10),
                           suspension_start=ts(2026, 11, 23, 10), suspension_hours=48,
                           extension_start=ts(2026, 11, 25, 10), extension_hours=72, extensions_requested=1))
    assert outcomes(out)["AML-04"] == "AML_SUSPENSION_ACTIVE"
    assert out.tx_hold_until == ts(2026, 12, 2, 10)
    bad = evaluate_aml(aml(suspension_start=ts(2026, 11, 25, 10), suspension_hours=96))
    assert outcomes(bad)["AML-04"] == "AML_INVALID_DURATION"
    assert not [d for d in bad.deadlines if d.rule_id == "AML-04"]           # motorul nu inventează un termen


def test_EX12_a_doua_prelungire_e_invalida():
    out = evaluate_aml(aml(extension_start=ts(2026, 11, 25, 10), extension_hours=72, extensions_requested=2))
    assert outcomes(out)["AML-04"] == "AML_INVALID_DURATION"


def test_TC16_EX11_str_returnat_corectare_in_2_zile_si_24h_de_la_noua_confirmare():
    out = evaluate_aml(aml(str_returned_at=ts(2026, 11, 23, 11), str_corrected_registered_at=ts(2026, 11, 25, 15)))
    assert outcomes(out)["AML-06"] == "AML_STR_RETURNED"
    assert str_correction_deadline(ts(2026, 11, 23, 11)) == eod(2026, 11, 25)
    assert next(d for d in out.deadlines if "Corectarea" in d.name).due_at == eod(2026, 11, 25)
    assert out.tx_hold_until == ts(2026, 11, 26, 15)


def test_URM04_payload_agentului_aml_produce_propunere_de_rts():
    payload = {"lead_id": "LEAD-SYN-002", "now": datetime(2026, 10, 28, 15, tzinfo=TZ), "victims": 2, "cases": 2,
               "top_mule_score": 0.82, "typologies": ["fan-in", None], "osint_red_flags": 1, "amount_total": 6400.0,
               "transaction_executed": True}
    fields = AmlRuleContext.model_fields
    out = evaluate_aml(AmlRuleContext(**{k: v for k, v in payload.items() if k in fields}))
    rts = out.model_dump(mode="json")["decisions"][0]
    assert rts["question"] == "rts" and rts["decision"] == "RTS_PROPUS" and rts["requires_human"]
    assert "URM-04" in rts["rule_ids"] and "URM-02" in rts["rule_ids"]
    low = evaluate_aml(AmlRuleContext(lead_id="LEAD-SYN-003", now=payload["now"], victims=1, top_mule_score=0.3))
    assert low.decisions[0].decision == Verdict.MONITORIZARE and not low.decisions[0].requires_human


def test_URM04_tranzactie_neexecutata_ceasuri_estimate():
    out = evaluate_aml(aml(now=ts(2026, 11, 27, 16), top_mule_score=0.9, transaction_executed=False))
    assert outcomes(out)["AML-02"] == "AML_TX_HOLD"
    names = [d.name for d in out.deadlines]
    assert any("estimat" in n for n in names) and any("48h" in n for n in names) and any("72h" in n for n in names)
    assert out.tx_hold_until == ts(2026, 12, 2, 16)


def test_URM01_scor_cu_trasaturi_personale_e_scos_din_decizie():
    out = evaluate_aml(aml(top_mule_score=0.95, features_used=["fan_in_24h", "vârsta_titular", "tranzit_rapid"]))
    assert outcomes(out)["URM-01"] == "URM_PROFILING_FEATURE"
    assert out.decisions[0].decision == Verdict.MONITORIZARE                    # scorul nu mai susține RTS-ul
    lead = out.decisions[1]
    assert lead.question == Question.PISTA_AML and lead.decision == Verdict.INFORMATII_SUPLIMENTARE
    assert lead.requires_human
    clean = evaluate_aml(aml(top_mule_score=0.95, features_used=["fan_in_24h", "page_views", "tranzit_rapid"]))
    assert outcomes(clean)["URM-01"] == "fapte_obiective" and clean.decisions[0].decision == Verdict.RTS_PROPUS


def test_URM01_potrivire_pe_cuvinte_intregi_fara_diacritice():
    terms = ["varsta", "age", "stare_civila"]
    assert prohibited_features(["Vârsta", "client_age", "stare civila", "page_views", "average_amount"], terms) == \
        ["Vârsta", "client_age", "stare civila"]


def test_URM02_interdictia_de_tipping_off_e_mereu_prezenta():
    out = evaluate_aml(aml())
    assert outcomes(out)["URM-02"] == "AML_TIPPING_OFF_BAN"
    assert any(c.startswith("tipping_off_ban") for c in out.constraints)
    assert all("URM-02" in d.rule_ids for d in out.decisions)
    assert "art. 47" in next(h for h in out.hits if h.rule_id == "URM-02").explanation
