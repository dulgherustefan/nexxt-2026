"""Tabelul rezultatelor așteptate pe scenarii (același ca setul de aur), pe `RuleContext` simplu, din contract.

`recovery_of` reproduce logica din versoml/eval/run.py: întâi recuperare_escroc, apoi recuperare_client.
"""

from __future__ import annotations

from typing import Any

import pytest

from rules_testkit import FACT_IDS, decision, eod, hit, ts
from versoml.contracts import Channel, DisputeType, Money, Question, RuleContext, Scenario, Verdict
from versoml.shared.rules import end_of_next_business_day, evaluate

REFUNDS = (Verdict.RAMBURSEAZA, Verdict.RAMBURSEAZA_CU_APROBARE)
RECOVERY_ACTIONS = ("RECHEMARE", "CHARGEBACK", "RECUPERARE_PROPUSA")


def recovery_of(out) -> str | None:
    for q in ("recuperare_escroc", "recuperare_client"):
        d = next((x for x in out.decisions if x.question.value == q), None)
        if d and d.decision.value in RECOVERY_ACTIONS:
            return d.decision.value
    d = next((x for x in out.decisions if x.question.value == "recuperare_client"), None)
    return d.decision.value if d else None


def scenario_ctx(scenario: Scenario, **kw: Any) -> RuleContext:
    executed = kw.pop("executed_at", ts(2026, 10, 28, 14, 2))
    notified = kw.pop("notified_at", ts(2026, 10, 28, 14, 40))
    base: dict[str, Any] = {"case_id": f"CT-SYN-{scenario.value}", "now": notified, "scenario": scenario,
                            "executed_at": executed, "notified_at": notified, "fact_ids": dict(FACT_IDS)}
    base.update(kw)
    return RuleContext(**base)


SCENARIOS: dict[str, dict[str, Any]] = {
    "phishing_link": dict(scenario=Scenario.PHISHING_LINK, channel=Channel.TRANSFER, dispute_type=DisputeType.NEAUTORIZATA,
                          amount=Money(value=3200.0), device_known=False, seconds_after_click=118, sca_performed=True,
                          sca_method="device_enrollment", screen_showed_amount_and_payee=False, beneficiary_new=True,
                          client_admits_sharing_credentials=True, client_fraud_score=0.12),
    "card_ecom_fara_3ds": dict(scenario=Scenario.CARD_ECOM_FARA_3DS, channel=Channel.CARD,
                               dispute_type=DisputeType.NEAUTORIZATA, amount=Money(value=1450.0), eci="07",
                               cavv_present=False, sca_performed=False, merchant_mcc="5732"),
    "card_visa_secure": dict(scenario=Scenario.CARD_VISA_SECURE, channel=Channel.CARD, dispute_type=DisputeType.NEAUTORIZATA,
                             amount=Money(value=2100.0), eci="05", cavv_present=True, sca_performed=True,
                             sca_method="app_push", screen_showed_amount_and_payee=True, client_admits_approving_in_app=True,
                             device_known=True),
    "vishing_securitate": dict(scenario=Scenario.VISHING_SECURITATE, channel=Channel.TRANSFER, dispute_type=DisputeType.APP,
                               amount=Money(value=4800.0), sca_performed=True, sca_method="app_push",
                               screen_showed_amount_and_payee=True, client_admits_approving_in_app=True, device_known=True,
                               beneficiary_new=True),
    "cont_sigur": dict(scenario=Scenario.CONT_SIGUR, channel=Channel.TRANSFER_INSTANT, dispute_type=DisputeType.APP,
                       amount=Money(value=18500.0), sca_performed=True, screen_showed_amount_and_payee=True,
                       client_admits_approving_in_app=True, device_known=True, beneficiary_new=True),
    "sim_swap": dict(scenario=Scenario.SIM_SWAP, channel=Channel.TRANSFER, dispute_type=DisputeType.NEAUTORIZATA,
                     amount=Money(value=2900.0), sim_swap_hours_before=1.5, device_known=False, sca_performed=True,
                     sca_method="sms_otp", screen_showed_amount_and_payee=True),
    "frauda_client": dict(scenario=Scenario.FRAUDA_CLIENT, channel=Channel.CARD, dispute_type=DisputeType.NEAUTORIZATA,
                          amount=Money(value=1900.0), eci="07", device_known=True, prior_disputes_12m=4,
                          client_fraud_score=0.91, sca_performed=False),
    "reclamatie_tardiva": dict(scenario=Scenario.RECLAMATIE_TARDIVA, channel=Channel.TRANSFER,
                               dispute_type=DisputeType.NEAUTORIZATA, amount=Money(value=1200.0),
                               executed_at=ts(2025, 8, 20, 12), notified_at=ts(2026, 10, 28, 9)),
    "plata_dubla": dict(scenario=Scenario.PLATA_DUBLA, channel=Channel.CARD, dispute_type=DisputeType.EROARE_PROCESARE,
                        amount=Money(value=349.9), duplicate_of="TX-SYN-000777", eci="07"),
    "marfa_nelivrata": dict(scenario=Scenario.MARFA_NELIVRATA, channel=Channel.CARD,
                            dispute_type=DisputeType.DISPUTA_COMERCIANT, amount=Money(value=780.0), eci="07"),
}

# scenariu → (rambursare_t1, requires_human pentru rambursare, ruta de recuperare sau None)
EXPECTED: dict[str, tuple[Verdict, bool, str | None]] = {
    "phishing_link": (Verdict.RAMBURSEAZA, False, "RECHEMARE"),
    "card_ecom_fara_3ds": (Verdict.RAMBURSEAZA, False, "CHARGEBACK"),
    "card_visa_secure": (Verdict.RAMBURSEAZA, False, "RECUPERARE_PROPUSA"),
    "vishing_securitate": (Verdict.NU_SE_APLICA_T1, True, "RECHEMARE"),
    "cont_sigur": (Verdict.NU_SE_APLICA_T1, True, "RECHEMARE"),
    "sim_swap": (Verdict.RAMBURSEAZA, False, "RECHEMARE"),
    "frauda_client": (Verdict.RAMBURSEAZA_CU_APROBARE, True, None),
    "reclamatie_tardiva": (Verdict.RESPINGE_TARDIV, True, None),
    "plata_dubla": (Verdict.NU_SE_APLICA_T1, False, "CHARGEBACK"),
    "marfa_nelivrata": (Verdict.NU_SE_APLICA_T1, False, "CHARGEBACK"),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_tabelul_rezultatelor_asteptate(name):
    ctx = scenario_ctx(**SCENARIOS[name])
    out = evaluate(ctx)
    verdict, human, recovery = EXPECTED[name]
    refund = out.decisions[0]
    assert refund.question == Question.RAMBURSARE_T1                     # M7 și contrafactualul citesc decisions[0]
    assert [d.question for d in out.decisions] == [Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT,
                                                   Question.RECUPERARE_ESCROC, Question.RASPUNS_RECLAMATIE]
    assert refund.decision == verdict, refund.rule_ids
    assert refund.requires_human is human
    if verdict in REFUNDS:
        assert refund.deadline == end_of_next_business_day(ctx.notified_at)
    else:
        assert refund.deadline is None or verdict == Verdict.EXCEPTIE_FRAUDA_CLIENT
    if recovery is None:
        assert recovery_of(out) not in RECOVERY_ACTIONS
    else:
        assert recovery_of(out) == recovery


@pytest.mark.parametrize("name, code", [("card_ecom_fara_3ds", "10.4"), ("plata_dubla", "12.6.1"), ("marfa_nelivrata", "13.1")])
def test_codurile_de_motiv_chargeback(name, code):
    out = evaluate(scenario_ctx(**SCENARIOS[name]))
    assert hit(out, "DSP-52").params["reason_code"] == code
    assert decision(out, Question.RECUPERARE_ESCROC).decision == Verdict.CHARGEBACK


def test_phishing_peste_plafon_cere_aprobare_tot_in_termen():
    ctx = scenario_ctx(**{**SCENARIOS["phishing_link"], "amount": Money(value=7200.0)})
    refund = evaluate(ctx).decisions[0]
    assert refund.decision == Verdict.RAMBURSEAZA_CU_APROBARE and refund.requires_human
    assert refund.deadline == eod(2026, 10, 29) and "DSP-59" in refund.rule_ids


def test_card_visa_secure_chargeback_imposibil_recuperare_propusa_omului():
    out = evaluate(scenario_ctx(**SCENARIOS["card_visa_secure"]))
    assert decision(out, Question.RECUPERARE_ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert "DSP-27" in decision(out, Question.RECUPERARE_ESCROC).rule_ids
    rec = decision(out, Question.RECUPERARE_CLIENT)
    assert rec.decision == Verdict.RECUPERARE_PROPUSA and rec.requires_human
    assert not out.decisions[0].requires_human                           # rambursarea rămâne automată


def test_frauda_client_cu_hold_si_autoritate_notificata_e_exceptia():
    ctx = scenario_ctx(**{**SCENARIOS["frauda_client"], "hold_signal": True, "hold_authority_notified": True})
    out = evaluate(ctx)
    assert out.decisions[0].decision == Verdict.EXCEPTIE_FRAUDA_CLIENT and out.decisions[0].requires_human
    assert recovery_of(out) not in RECOVERY_ACTIONS
    answer = decision(out, Question.RASPUNS_RECLAMATIE)
    assert answer.decision == Verdict.INFORMATII_SUPLIMENTARE and "URM-02" in answer.rule_ids


def test_frauda_client_fara_hold_nu_retine_rambursarea():
    out = evaluate(scenario_ctx(**{**SCENARIOS["frauda_client"], "hold_signal": True}))
    assert out.decisions[0].decision == Verdict.RAMBURSEAZA_CU_APROBARE


def test_reclamatie_tardiva_pe_card_fara_chargeback():
    ctx = scenario_ctx(**{**SCENARIOS["reclamatie_tardiva"], "channel": Channel.CARD, "eci": "07"})
    out = evaluate(ctx)
    assert out.decisions[0].decision == Verdict.RESPINGE_TARDIV
    assert recovery_of(out) not in RECOVERY_ACTIONS


def test_contrafactualul_din_demo_ecranul_a_afisat_suma():
    """Demo 2:10: juratul schimbă un fapt; recuperarea se schimbă, rambursarea rămâne (C-70/25)."""
    base = scenario_ctx(**SCENARIOS["phishing_link"])
    changed = base.model_copy(update={"screen_showed_amount_and_payee": True})
    before, after = evaluate(base), evaluate(changed)
    assert before.decisions[0].decision == after.decisions[0].decision == Verdict.RAMBURSEAZA
    assert decision(before, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert decision(after, Question.RECUPERARE_CLIENT).decision == Verdict.RECUPERARE_PROPUSA


def test_scenariile_cu_rambursare_au_citari_din_registru():
    out = evaluate(scenario_ctx(**SCENARIOS["phishing_link"]))
    refund = out.decisions[0]
    assert refund.supporting_evidence and set(refund.supporting_evidence) <= set(FACT_IDS.values())
    assert any(line.cites for line in refund.rationale)
