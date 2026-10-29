"""Testele PAY din docs/context/11 §6 (TC-27…TC-32, TC-39, TC-40), excepțiile EX-18/19/25 și calculatoarele §3.

TC-33 (VoP, PAY-14) nu se aplică: verificarea beneficiarului nu e în RuleContext, iar IPR intră în RO din 2027.
"""

from __future__ import annotations

from datetime import date

import pytest

from rules_testkit import decision, eod, hit, make_ctx, outcome, t1, ts
from versoml.contracts import Channel, DisputeType, Money, Question, Verdict
from versoml.shared.rules import evaluate, validate_refund_refusal
from versoml.shared.rules.packs.pay import direct_debit_refund_due, payer_liability, refund_can_be_withheld


def test_TC27_card_fara_sca_rambursare_pana_la_2_12_si_raspundere_0():
    ctx = make_ctx(channel=Channel.CARD, executed_at=ts(2026, 10, 20, 12), notified_at=ts(2026, 11, 27, 9),
                   sca_performed=False, sca_required_by_issuer=False, amount=Money(value=640.0))
    out = evaluate(ctx)
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"
    assert t1(out).deadline == eod(2026, 12, 2)
    assert t1(out).decision == Verdict.RAMBURSEAZA
    assert outcome(out, "PAY-04") == "raspundere_0"
    assert hit(out, "PAY-04").params["raspundere"] == 0.0
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_TC28_card_furat_rambursare_integrala_si_franciza_max_30_eur():
    ctx = make_ctx(channel=Channel.CARD, card_present=True, amount=Money(value=200.0, currency="EUR"),
                   executed_at=ts(2026, 10, 30, 18), notified_at=ts(2026, 11, 2, 8), sca_performed=True,
                   sca_method="chip_pin")
    out = evaluate(ctx)
    assert t1(out).decision in (Verdict.RAMBURSEAZA, Verdict.RAMBURSEAZA_CU_APROBARE)
    assert t1(out).amount == Money(value=200.0, currency="EUR")          # rambursare integrală
    assert t1(out).deadline == eod(2026, 11, 3)
    assert outcome(out, "PAY-05") == "raspundere_max_30_eur"
    assert hit(out, "PAY-05").params["raspundere"] == 30.0                # alocarea finală, decisă de om
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE


@pytest.mark.parametrize("info_provided, late", [(True, True), (False, False)])
def test_TC29_debit_15_09_2025_notificare_28_10_2026(info_provided, late):
    ctx = make_ctx(executed_at=ts(2025, 9, 15), notified_at=ts(2026, 10, 28), tx_info_provided=info_provided)
    out = evaluate(ctx)
    if late:
        assert outcome(out, "PAY-01") == "PAY_LATE_NOTIFICATION"
        assert t1(out).decision == Verdict.RESPINGE_TARDIV
        assert t1(out).requires_human
    else:
        assert outcome(out, "PAY-01") == "limita_nu_se_aplica"
        assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"
        assert t1(out).deadline == eod(2026, 10, 29)


def test_TC29_limita_e_15_10_2026():
    out = evaluate(make_ctx(executed_at=ts(2025, 9, 15), notified_at=ts(2026, 10, 15, 23)))
    assert outcome(out, "PAY-01") == "in_termen"
    out = evaluate(make_ctx(executed_at=ts(2025, 9, 15), notified_at=ts(2026, 10, 16, 0, 5)))
    assert outcome(out, "PAY-01") == "PAY_LATE_NOTIFICATION"


def test_TC30_neglijenta_invocata_fara_loguri_sca_rambursare_si_recuperare_blocata():
    ctx = make_ctx(notified_at=ts(2026, 11, 2, 9), executed_at=ts(2026, 11, 1, 20), sca_performed=None,
                   screen_showed_amount_and_payee=None, client_admits_sharing_credentials=True)
    out = evaluate(ctx)
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"
    assert t1(out).deadline == eod(2026, 11, 3)
    assert outcome(out, "PAY-02") == "PAY_SCA_EVIDENCE_MISSING"
    rec = decision(out, Question.RECUPERARE_CLIENT)
    assert rec.decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert "PAY-02" in rec.rule_ids


def test_TC31_transfer_autorizat_dupa_apel_de_la_banca_e_app():
    ctx = make_ctx(dispute_type=DisputeType.APP, sca_performed=True, screen_showed_amount_and_payee=True,
                   client_admits_approving_in_app=True, device_known=True)
    out = evaluate(ctx)
    assert outcome(out, "PAY-12") == "PAY_APP_SCAM"
    assert t1(out).decision == Verdict.NU_SE_APLICA_T1
    assert t1(out).requires_human
    answer = decision(out, Question.RASPUNS_RECLAMATIE)
    assert "CMP-01" in answer.rule_ids and answer.deadline is not None


def test_PAY03_explicatia_in_engleza_cu_termenul_si_temeiul():
    out = evaluate(make_ctx(executed_at=ts(2026, 10, 28, 9), notified_at=ts(2026, 10, 28, 10)))
    assert hit(out, "PAY-03").explanation == (
        "Refund due by 29 Oct 2026, 23:59, the end of the business day after the customer reported it on "
        "28 Oct 2026, 10:00 (Law 209/2019, art. 173; CJEU C-70/25). The account returns to its state before "
        "the payment, with a value date no later than the debit date.")
    assert t1(out).next_actions[0] == ("The engine issues the (simulated) refund instruction for RON 1,000.00 by "
                                       "29 Oct 2026, 23:59")
    big = evaluate(make_ctx(amount=Money(value=7200.0), executed_at=ts(2026, 10, 28, 9),
                            notified_at=ts(2026, 10, 28, 10)))
    assert t1(big).next_actions[0] == ("Get human sign-off on the RON 7,200.00 refund by 29 Oct 2026, 23:59 "
                                       "(reasons: DSP-59)")
    assert hit(big, "DSP-59").explanation.startswith("The amount of RON 7,200.00 is above the automatic refund cap "
                                                      "(RON 5,000.00, a bank setting).")


def test_TC32_debitare_directa():
    assert direct_debit_refund_due(date(2026, 9, 1), date(2026, 10, 20)) == date(2026, 11, 3)
    assert direct_debit_refund_due(date(2026, 9, 1), date(2026, 10, 28)) is None   # PAY_DD_WINDOW_EXPIRED


def _tc39_ctx(**kw):
    base = dict(amount=Money(value=700.0, currency="EUR"), executed_at=ts(2026, 11, 1, 21), notified_at=ts(2026, 11, 2, 9),
                sca_performed=True, sca_method="app_push", screen_showed_amount_and_payee=True,
                client_admits_sharing_credentials=True, device_known=False)
    base.update(kw)
    return make_ctx(**base)


def test_TC39_refuz_pentru_neglijenta_grava_e_blocat():
    ctx = _tc39_ctx()
    guard = validate_refund_refusal(ctx, "REFUSED_GROSS_NEGLIGENCE")
    assert not guard.allowed and guard.code == "PAY_REFUSAL_ON_GN_BLOCKED" and guard.rule_id == "PAY-15"
    out = evaluate(ctx)
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"
    assert t1(out).deadline == eod(2026, 11, 3)
    assert t1(out).decision == Verdict.RAMBURSEAZA                       # 700 EUR ≈ 3.500 RON, sub plafon
    assert outcome(out, "PAY-06") == "PAY_RECOVERY_REVIEW"
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.RECUPERARE_PROPUSA


def test_EX25_alte_motive_de_refuz_sunt_blocate_si_reale_permise():
    ctx = _tc39_ctx()
    for reason in ("neglijenta_grava", "sca_reusita", "otp_divulgat", "aprobat_in_aplicatie"):
        assert validate_refund_refusal(ctx, reason).code == "PAY_REFUSAL_ON_GN_BLOCKED"
    assert validate_refund_refusal(ctx, "frauda_client").code == "PAY_FRAUD_NOTICE_MISSING"
    held = _tc39_ctx(hold_signal=True, hold_authority_notified=True)
    assert validate_refund_refusal(held, "frauda_client").allowed
    late = make_ctx(executed_at=ts(2025, 9, 15), notified_at=ts(2026, 10, 28))
    assert validate_refund_refusal(late, "tardiv").allowed


@pytest.mark.parametrize("notified, verdict, code", [
    (False, Verdict.RAMBURSEAZA_CU_APROBARE, "PAY_FRAUD_NOTICE_MISSING"),
    (True, Verdict.EXCEPTIE_FRAUDA_CLIENT, "PAY_FRAUD_SUSPECTED"),
])
def test_TC40_suspiciune_de_frauda_comunicata_sau_nu(notified, verdict, code):
    out = evaluate(make_ctx(hold_signal=True, hold_authority_notified=notified))
    assert outcome(out, "PAY-03") == code
    assert t1(out).decision == verdict
    assert t1(out).requires_human
    assert t1(out).deadline == eod(2026, 10, 28)


def test_EX18_dupa_13_luni_raspuns_motivat_in_termenul_reclamatiei():
    out = evaluate(make_ctx(executed_at=ts(2025, 9, 15), notified_at=ts(2026, 10, 27)))
    assert t1(out).decision == Verdict.RESPINGE_TARDIV
    assert decision(out, Question.RASPUNS_RECLAMATIE).deadline == eod(2026, 11, 17)


def test_EX19_sca_necerut_raspundere_0_chiar_cu_neglijenta_invocata():
    ctx = make_ctx(sca_performed=False, client_admits_sharing_credentials=True)
    out = evaluate(ctx)
    assert t1(out).decision == Verdict.RAMBURSEAZA
    assert outcome(out, "PAY-04") == "raspundere_0"
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE


# ---------------------------------------------------------------- calculatoarele din docs/context/11 §3


def test_calc_payer_liability():
    assert payer_liability(450, payer_fraud=False, art177_case=True, intent_or_gross_negligence_proven=False,
                           lost_stolen_misappropriated=True, cap=30) == 0
    assert payer_liability(200, payer_fraud=False, art177_case=False, intent_or_gross_negligence_proven=False,
                           lost_stolen_misappropriated=True, cap=30) == 30
    assert payer_liability(200, payer_fraud=False, art177_case=False, intent_or_gross_negligence_proven=True,
                           lost_stolen_misappropriated=True, cap=30) == 200
    assert payer_liability(200, payer_fraud=True, art177_case=True, intent_or_gross_negligence_proven=False,
                           lost_stolen_misappropriated=True, cap=30) == 200


def test_calc_refund_can_be_withheld_neglijenta_nu_e_parametru():
    assert refund_can_be_withheld(False, False) is False
    assert refund_can_be_withheld(True, False) is False
    assert refund_can_be_withheld(True, True) is True


def test_calc_franciza_in_lei_foloseste_cursul_parametru():
    out = evaluate(make_ctx(amount=Money(value=4000.0)), {"eur_ron_rate": 4.9})
    assert hit(out, "PAY-05").params["raspundere"] == pytest.approx(147.0)
    assert hit(out, "PAY-05").params["eur_ron_rate"] == 4.9


@pytest.mark.parametrize("retain", [False, True])
def test_franciza_de_30_eur_se_retine_sau_se_renunta_la_ea(retain):
    out = evaluate(make_ctx(amount=Money(value=4000.0)), {"retain_payer_liability": retain})
    found = hit(out, "PAY-05")
    assert found.params["raspundere"] == 150.0
    assert ("keeps it back" in found.explanation) is retain and ("waives it" in found.explanation) is not retain
