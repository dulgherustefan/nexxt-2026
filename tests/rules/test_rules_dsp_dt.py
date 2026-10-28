"""Cazurile de test DT-01…DT-20 din docs/context/14 §10 (date sintetice, ora României).

`now` = momentul analizei la intake (notificarea), cu excepția testelor care cer explicit altceva (DT-07, DT-14).
DT-18 (a) (atașamentul altui client, PAN în clar) ține de filtrul zidului (`versoml.wall`), nu de motor.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from rules_testkit import decision, deadline, eod, hit, make_ctx, outcome, t1, ts
from versoml.contracts import Channel, DisputeType, Money, Question, RuleContext, Scenario, Verdict
from versoml.shared.rules import Ce3Txn, ce3_check, check_adr_block, evaluate, validate_refund_refusal, validate_reversal
from versoml.shared.rules.packs.dsp import (
    scheme_deadline_status, visa_allocation_stage_due, visa_collaboration_stage_due, visa_fraud_report_due,
)

ESCROC, CLIENT, ANSWER = Question.RECUPERARE_ESCROC, Question.RECUPERARE_CLIENT, Question.RASPUNS_RECLAMATIE


def flag(out) -> str:
    return hit(out, "DSP-52").params["recuperabil"]


def dt01(**kw):
    base = dict(channel=Channel.CARD, card_scheme="visa", executed_at=ts(2026, 10, 1, 15), processing_date=date(2026, 10, 2),
                amount=Money(value=850.0), notified_at=ts(2026, 10, 26, 9, 30), sca_performed=False,
                sca_required_by_issuer=False, eci="07", cavv_present=False, intake_authenticated=True,
                prior_disputes_12m=0, prior_disputes_120d=0, police_report_filed=False)
    base.update(kw)
    return make_ctx(**base)


def test_DT01_cnp_fara_sca_rambursare_raspundere_0_si_chargeback_104():
    out = evaluate(dt01())
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE" and t1(out).deadline == eod(2026, 10, 27)
    assert outcome(out, "PAY-04") == "raspundere_0"                                    # art. 177 lit. d)
    assert flag(out) == "DA" and hit(out, "DSP-52").params["reason_code"] == "10.4"
    assert outcome(out, "DSP-25") == "DSP_FRAUD_REPORT_DUE"
    assert deadline(out, "DSP-25").due_at == eod(2026, 11, 30)
    assert deadline(out, "DSP-24", "10.4").due_at == eod(2027, 1, 30)
    assert outcome(out, "DSP-32") == "certificare_permisa"
    assert decision(out, ANSWER).deadline == eod(2026, 11, 16)
    assert outcome(out, "DSP-54") == "garda_plangere"                                 # lipsa plângerii nu blochează
    esc = decision(out, ESCROC)
    assert esc.decision == Verdict.CHARGEBACK and esc.requires_human and esc.deadline == eod(2027, 1, 30)


def dt02(**kw):
    base = dict(channel=Channel.CARD, card_scheme="visa", executed_at=ts(2026, 10, 22, 21, 47),
                processing_date=date(2026, 10, 23), amount=Money(value=1249.0), notified_at=ts(2026, 10, 23, 9, 12),
                intake_authenticated=True, eci="05", cavv_present=True, visa_secure_auth_confirmation=True,
                sca_performed=True, sca_method="biometric", screen_showed_amount_and_payee=True, device_known=False,
                client_admits_sharing_credentials=True)
    base.update(kw)
    return make_ctx(**base)


def test_DT02_phishing_curier_visa_secure_rambursare_si_dosar_de_recuperare():
    out = evaluate(dt02())
    assert t1(out).decision == Verdict.RAMBURSEAZA and t1(out).deadline == eod(2026, 10, 26)
    assert outcome(out, "PAY-06") == "PAY_RECOVERY_REVIEW"
    rec = decision(out, CLIENT)
    assert rec.decision == Verdict.RECUPERARE_PROPUSA and rec.requires_human
    assert outcome(out, "DSP-27") == "DSP_NOT_CHARGEABLE" and flag(out) == "NU"
    assert decision(out, ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert deadline(out, "DSP-25").due_at == eod(2026, 12, 21)
    assert decision(out, ANSWER).deadline == eod(2026, 11, 13)
    assert deadline(out, "CMP-02").due_at == eod(2026, 12, 15)
    assert outcome(out, "DSP-50") == "semnale_autentificare"                          # dispozitiv nou, înregistrat
    assert outcome(out, "PAY-15") == "garda_c70_25"


def dt03(**kw):
    base = dict(channel=Channel.CARD, card_scheme="visa", executed_at=ts(2026, 10, 27, 9, 40),
                notified_at=ts(2026, 10, 27, 10, 5), amount=Money(value=2300.0), classification_ambiguous=True,
                device_known=True, sca_performed=True, sca_method="biometric", screen_showed_amount_and_payee=True,
                client_admits_approving_in_app=True, eci="05", cavv_present=True)
    base.update(kw)
    return make_ctx(**base)


def test_DT03_vishing_ambiguu_merge_la_om_cu_scadenta_t1_fara_refuz():
    ctx = dt03()
    out = evaluate(ctx)
    assert outcome(out, "DSP-50") == "DSP_AUTH_AMBIGUOUS"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE
    assert t1(out).requires_human and t1(out).deadline == eod(2026, 10, 28)
    assert flag(out) == "NU"
    assert not validate_refund_refusal(ctx, "aprobat_in_aplicatie").allowed


def test_DT03_ambiguitatea_poate_veni_si_prin_params():
    plain = RuleContext.model_validate(dt03(classification_ambiguous=False).model_dump())
    out = evaluate(plain, {"_classification_ambiguous": True})
    assert outcome(out, "DSP-50") == "DSP_AUTH_AMBIGUOUS"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE


def test_DT03_varianta_suma_din_push_difera():
    out = evaluate(dt03(screen_showed_amount_and_payee=False))
    assert outcome(out, "PAY-08") == "PAY_SCA_EVIDENCE_MISSING"


def test_DT04_cripto_cumparat_de_titular_e_app_fara_t1():
    ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.APP, purchase_type="crypto_nft",
                   cardholder_participated=True, amount=Money(value=4000.0), executed_at=ts(2026, 10, 24, 16),
                   notified_at=ts(2026, 10, 26, 11))
    out = evaluate(ctx)
    assert outcome(out, "PAY-12") == "PAY_APP_SCAM"
    assert t1(out).decision == Verdict.NU_SE_APLICA_T1 and t1(out).deadline is None
    assert flag(out) == "NU" and hit(out, "DSP-52").params["blocking_rules"] == ["DSP-29"]
    assert outcome(out, "DSP-51") == "traseu_sprijin"
    assert decision(out, ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert decision(out, ANSWER).deadline == eod(2026, 11, 16)


def test_DT04_varianta_nu_eu_am_cumparat_pista_neautorizata_cu_jurnal_sca():
    ctx = make_ctx(channel=Channel.CARD, purchase_type="crypto_nft", cardholder_participated=False, eci="07",
                   amount=Money(value=4000.0), executed_at=ts(2026, 10, 24, 16), notified_at=ts(2026, 10, 26, 11))
    out = evaluate(ctx)
    assert t1(out).decision in (Verdict.RAMBURSEAZA, Verdict.RAMBURSEAZA_CU_APROBARE)
    assert "PAY-02" in t1(out).rule_ids and outcome(out, "PAY-02") == "PAY_SCA_EVIDENCE_MISSING"


@pytest.mark.parametrize("info_provided", [True, False])
def test_DT05_debit_15_09_2025_notificare_27_10_2026(info_provided):
    ctx = make_ctx(channel=Channel.CARD, eci="07", executed_at=ts(2025, 9, 15, 12), processing_date=date(2025, 9, 16),
                   notified_at=ts(2026, 10, 27, 10), tx_info_provided=info_provided)
    out = evaluate(ctx)
    if info_provided:
        assert outcome(out, "PAY-01") == "PAY_LATE_NOTIFICATION"
        assert deadline(out, "PAY-01").due_at == eod(2026, 10, 15)
        assert t1(out).decision == Verdict.RESPINGE_TARDIV and t1(out).requires_human
        assert decision(out, ANSWER).deadline == eod(2026, 11, 17)
    else:
        assert outcome(out, "PAY-03") == "PAY_REFUND_DUE" and t1(out).deadline == eod(2026, 10, 28)
    assert outcome(out, "DSP-24") == "PAY_CHARGEBACK_WINDOW"
    assert flag(out) == "NU"


@pytest.mark.parametrize("n, code, value", [(36, "DSP_DISPUTE_LIMIT_EXCEEDED", "NU"), (35, "sub_limita", "DA")])
def test_DT06_limita_de_35_de_dispute(n, code, value):
    out = evaluate(dt01(prior_disputes_120d=n, prior_disputes_12m=n))
    assert outcome(out, "DSP-26") == code
    assert flag(out) == value
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"


def test_DT07_scrisoare_pe_hartie_termen_t1_depasit_la_inregistrare():
    ctx = make_ctx(channel=Channel.CARD, eci="07", executed_at=ts(2026, 10, 16, 13), notified_at=ts(2026, 10, 19, 11),
                   now=ts(2026, 10, 21, 10), intake_authenticated=False, signed_letter=False,
                   claimed_amount_low_confidence=True, amount=Money(value=780.0))
    out = evaluate(ctx)
    assert outcome(out, "DSP-03") == "DSP_REFUND_SLA_BREACHED"
    assert t1(out).deadline == eod(2026, 10, 20)
    assert t1(out).next_actions[0].startswith("escaladare imediată")
    assert decision(out, ANSWER).deadline == eod(2026, 11, 9)
    assert outcome(out, "DSP-32") == "DSP_CARDHOLDER_PROOF_MISSING"
    assert outcome(out, "DSP-57") == "suma_de_confirmat"
    assert t1(out).requires_human and t1(out).amount == Money(value=780.0)
    assert decision(out, ANSWER).decision == Verdict.INFORMATII_SUPLIMENTARE


def test_DT08_eci_06_recuperabil_incert_rambursarea_neschimbata():
    out = evaluate(dt01(eci="06"))
    assert outcome(out, "DSP-31") == "DSP_RULE_UNVERIFIED"
    assert flag(out) == "INCERT"
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE" and t1(out).deadline == eod(2026, 10, 27)
    assert decision(out, ESCROC).requires_human


def test_DT09_131_nelivrat_fara_dovada_contactarii_comerciantului():
    ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.DISPUTA_COMERCIANT, scenario=Scenario.MARFA_NELIVRATA,
                   processing_date=date(2026, 10, 20), executed_at=ts(2026, 10, 19, 12), notified_at=ts(2026, 10, 26, 10),
                   merchant_contact_proof=False, amount=Money(value=499.0))
    out = evaluate(ctx)
    assert outcome(out, "DSP-53") == "DSP_EVIDENCE_MISSING"
    assert deadline(out, "DSP-24", "Cel mai devreme").due_at == eod(2026, 11, 4)
    assert deadline(out, "DSP-24", "(emitent)").due_at == eod(2027, 2, 17)
    assert t1(out).decision == Verdict.NU_SE_APLICA_T1 and not t1(out).requires_human
    answer = decision(out, ANSWER)
    assert answer.deadline == eod(2026, 11, 16) and answer.decision == Verdict.INFORMATII_SUPLIMENTARE
    assert visa_collaboration_stage_due("raspuns_disputa_acquirer", date(2026, 11, 4))[0] == date(2026, 12, 4)


def test_DT10a_atm_fara_numerar_139_termen_neverificat():
    ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.EROARE_PROCESARE, purchase_type="atm_cash",
                   card_present=True, amount=Money(value=500.0), executed_at=ts(2026, 10, 24, 12),
                   notified_at=ts(2026, 10, 26, 9))
    out = evaluate(ctx)
    assert hit(out, "DSP-20").explanation.startswith("Condiția Visa 13.9")
    assert outcome(out, "DSP-24") == "DSP_DEADLINE_UNVERIFIED"
    assert flag(out) == "INCERT" and t1(out).decision == Verdict.NU_SE_APLICA_T1


def test_DT10b_conditie_inexistenta_121():
    ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.EROARE_PROCESARE, visa_condition="12.1")
    out = evaluate(ctx)
    assert outcome(out, "DSP-20") == "DSP_UNKNOWN_CONDITION"
    assert flag(out) == "INCERT"


def test_DT10c_preautorizare_nedeblocata_nu_e_chargeback():
    ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.EROARE_PROCESARE, preauth_release_late=True)
    out = evaluate(ctx)
    assert outcome(out, "PAY-09") == "PAY_PREAUTH_RELEASE_LATE"
    assert flag(out) == "NU"
    assert decision(out, ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_DT11_mastercard_4837_candidat_omul_alege_ruta():
    out = evaluate(dt01(card_scheme="mastercard"))
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE" and t1(out).deadline == eod(2026, 10, 27)
    assert hit(out, "DSP-40").explanation.startswith("Cod Mastercard candidat: 4837")
    assert outcome(out, "DSP-42") == "DSP_RULE_UNVERIFIED" and outcome(out, "DSP-43") == "DSP_RULE_UNVERIFIED"
    assert flag(out) == "INCERT" and hit(out, "DSP-52").params["reason_code"] == "4837"
    esc = decision(out, ESCROC)
    assert esc.decision == Verdict.CHARGEBACK and esc.requires_human


DEV = "dev-SYN-7c41e9a2b6d03f55"     # 24 de caractere


def test_DT12_ce3_indeplinit_retinere_propusa_four_eyes():
    disputed = Ce3Txn(txn_id="TX-SYN-9001", processed_on=date(2026, 10, 20), merchant_id="M-SYN-1", device_id=DEV,
                      shipping_address="sha256:adr-01")
    priors = [Ce3Txn(txn_id=f"TX-SYN-80{i}", processed_on=date(2026, 10, 20) - timedelta(days=days), merchant_id="M-SYN-1",
                     device_id=DEV, shipping_address="sha256:adr-01") for i, days in enumerate((150, 210))]
    res = ce3_check(disputed, priors, dispute_on=date(2026, 10, 26))
    assert res.met and res.code == "DSP_CE3_MET" and len(res.qualifying) == 2
    ctx = dt01(ce3_met=True, eci="07", processing_date=date(2026, 10, 20), executed_at=ts(2026, 10, 19, 20))
    out = evaluate(ctx)
    assert outcome(out, "DSP-30") == "DSP_CE3_MET" and flag(out) == "NU"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE
    assert any("notificarea către autoritate" in a for a in t1(out).next_actions)
    # omul infirmă: rambursare; notificarea netrimisă: PAY_FRAUD_NOTICE_MISSING; trimisă: excepția
    assert outcome(evaluate(ctx.model_copy(update={"ce3_met": False})), "PAY-03") == "PAY_REFUND_DUE"
    missing = evaluate(ctx.model_copy(update={"hold_signal": True}))
    assert outcome(missing, "PAY-03") == "PAY_FRAUD_NOTICE_MISSING"
    assert t1(missing).decision == Verdict.RAMBURSEAZA_CU_APROBARE
    held = evaluate(ctx.model_copy(update={"hold_signal": True, "hold_authority_notified": True}))
    assert t1(held).decision == Verdict.EXCEPTIE_FRAUDA_CLIENT


def test_DT13_ce3_din_24_10_2026_device_si_fingerprint_sunt_un_element():
    disputed = Ce3Txn(txn_id="TX-SYN-9101", processed_on=date(2026, 8, 10), merchant_id="M-SYN-A", device_id=DEV,
                      fingerprint="fp-SYN-0123456789abcdef0123")
    priors = [Ce3Txn(txn_id="TX-SYN-8101", processed_on=date(2026, 2, 1), merchant_id="M-SYN-B", device_id=DEV,
                     fingerprint="fp-SYN-0123456789abcdef0123"),
              Ce3Txn(txn_id="TX-SYN-8102", processed_on=date(2026, 3, 1), merchant_id="M-SYN-C", device_id=DEV,
                     fingerprint="fp-SYN-0123456789abcdef0123")]
    res = ce3_check(disputed, priors, dispute_on=date(2026, 9, 1), as_of=date(2026, 10, 27))
    assert not res.met and res.code == "DSP_CE3_NOT_MET"
    old = ce3_check(disputed.model_copy(update={"merchant_id": "M-SYN-B"}),
                    [p.model_copy(update={"merchant_id": "M-SYN-B"}) for p in priors], dispute_on=date(2026, 9, 1))
    assert old.met                                   # înainte de 24.10.2026: două elemente separate
    reported = [priors[0].model_copy(update={"reported_fraud": True}), priors[1]]
    assert ce3_check(disputed, reported, dispute_on=date(2026, 9, 1), as_of=date(2026, 10, 27)).code == "DSP_CE3_NOT_MET"
    due, conf = visa_allocation_stage_due("raspuns_emitent_prearbitraj", date(2026, 10, 27))
    assert due == date(2026, 11, 26) and conf.value == "U"


def test_DT14_prearbitraj_fara_raspuns_termen_in_risc():
    due, _ = visa_allocation_stage_due("raspuns_emitent_prearbitraj", date(2026, 10, 1))
    assert due == date(2026, 10, 31)
    assert scheme_deadline_status(due, ts(2026, 10, 28, 10), 5) == ("DSP_SCHEME_DEADLINE_AT_RISK", 3)
    assert scheme_deadline_status(due, ts(2026, 10, 20, 10), 5)[0] == "in_termen"
    assert scheme_deadline_status(due, ts(2026, 11, 1, 10), 5)[0] == "termen_expirat"


def test_DT15_reversarea_creditului():
    ok = validate_reversal("comerciant_a_rambursat")
    assert ok.allowed and any("aprobare umană" in a for a in ok.next_actions)
    blocked = validate_reversal("neglijenta_grava")
    assert not blocked.allowed and blocked.code == "DSP_REVERSAL_BLOCKED"
    assert any("PAY-06" in a for a in blocked.next_actions)


@pytest.mark.parametrize("hour, liability_rule", [(11, "PAY-05"), (16, "PAY-04")])
def test_DT16_card_pierdut_tranzactii_inainte_si_dupa_notificare(hour, liability_rule):
    ctx = make_ctx(channel=Channel.CARD, card_present=True, amount=Money(value=200.0 if hour == 11 else 300.0),
                   executed_at=ts(2026, 10, 24, hour, 30 if hour == 11 else 0), loss_reported_at=ts(2026, 10, 24, 14),
                   notified_at=ts(2026, 10, 25, 10), sca_performed=True, sca_method="chip_pin")
    out = evaluate(ctx)
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE" and t1(out).deadline == eod(2026, 10, 26)
    assert hit(out, liability_rule) is not None
    if liability_rule == "PAY-05":
        assert hit(out, "PAY-05").params["raspundere"] == 150.0           # max. 30 EUR la cursul [U] 5,00
    else:
        assert hit(out, "PAY-04").params["raspundere"] == 0.0             # art. 177 lit. c)
    assert flag(out) == "INCERT"


def test_DT16_o_tranzactie_se_contesta_o_singura_data():
    out = evaluate(dt01(existing_dispute_for_txn=True))
    assert outcome(out, "DSP-21") == "DSP_DUPLICATE_DISPUTE" and flag(out) == "NU"


def test_DT17a_card_de_credit_pe_numele_victimei():
    out = evaluate(make_ctx(channel=Channel.CARD, credit_fraud=True, notified_at=ts(2026, 11, 2, 10)))
    assert outcome(out, "DSP-16") == "DSP_ROUTE_CREDIT_FRAUD"
    assert decision(out, ANSWER).deadline == eod(2026, 12, 2)
    assert any("Biroul de Credit" in a for a in t1(out).next_actions)
    assert t1(out).decision == Verdict.NU_SE_APLICA_T1 and t1(out).requires_human


def test_DT17b_implicarea_unui_angajat_raspundere_0_si_conformitate():
    out = evaluate(make_ctx(staff_involvement=True, sca_performed=True))
    assert outcome(out, "PAY-04") == "DSP_STAFF_INVOLVEMENT"
    rec = decision(out, CLIENT)
    assert rec.decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert any("conformitatea" in a for a in rec.next_actions)


def test_DT18b_raspuns_final_fara_cai_de_sesizare():
    assert check_adr_block("Vă returnăm suma. Cu stimă, Banca Demo").outcome == "CMP_ADR_BLOCK_MISSING"


def test_DT18c_instructiune_injectata_suma_din_jurnal():
    out = evaluate(make_ctx(channel=Channel.CARD, eci="07", amount=Money(value=320.0), injection_suspected=True,
                            claimed_amount=9999.0))
    assert outcome(out, "DSP-57") == "DSP_SECURITY_SIGNAL"
    assert t1(out).amount == Money(value=320.0)
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE and t1(out).requires_human


def test_DT19_banca_a_constatat_frauda_inaintea_clientului():
    ctx = make_ctx(channel=Channel.CARD, eci="07", bank_noted_at=ts(2026, 10, 22, 18), executed_at=ts(2026, 10, 22, 11),
                   notified_at=ts(2026, 10, 26, 9))
    out = evaluate(ctx)
    assert outcome(out, "DSP-58") == "ancora_constatare"
    assert t1(out).deadline == eod(2026, 10, 23)
    assert outcome(out, "DSP-03") == "DSP_REFUND_SLA_BREACHED"
    notif = evaluate(ctx, {"refund_anchor_mode": "notificare"})                      # parametrul [U]
    assert t1(notif).deadline == eod(2026, 10, 27)


def test_DT20_comerciant_see_fara_sca():
    out = evaluate(dt01(sca_not_applied_reason="payee_no_sca"))
    assert outcome(out, "PAY-07") == "PAY_RECOVERY_FROM_PAYEE_PSP"
    assert "DSP_RULE_UNVERIFIED" in hit(out, "PAY-07").explanation
    assert t1(out).deadline == eod(2026, 10, 27)


def test_DSP25_lecturile_termenului_de_raport():
    assert visa_fraud_report_due(date(2026, 10, 1), date(2026, 10, 26), None) == (date(2026, 11, 30), True)
    # notificare târzie: lecturile diferă → data mai devreme, semnalată
    assert visa_fraud_report_due(date(2026, 6, 1), date(2026, 7, 20), None) == (date(2026, 7, 31), False)
    assert visa_fraud_report_due(date(2026, 6, 1), date(2026, 7, 20), "max") == (date(2026, 8, 19), True)
    assert visa_fraud_report_due(date(2026, 6, 1), date(2026, 7, 20), "after_day_60") == (date(2026, 7, 31), True)
