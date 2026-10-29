"""Debitul direct (PAY-10, DD-xx), cardul prezent și condițiile 13.x (DSP-24, DSP-52), vulnerabilitatea (DP-04,
VU-xx), recunoașterile neconfirmate (DSP-57) și semnalele pentru consolă (review_flags, reason_codes)."""

from __future__ import annotations

from datetime import date

from rules_testkit import decision, eod, hit, make_ctx, outcome, t1, ts

from versoml.contracts import Channel, DisputeType, Money, Question, Verdict
from versoml.shared.rules import evaluate
from versoml.shared.rules.facts import make_env, visa_condition
from versoml.shared.rules.packs.dsp import chargeback_recoverable, visa_dispute_window
from versoml.shared.rules.params import defaults


def _env():
    return make_env(defaults())


def test_DD01_debit_direct_contestat_in_8_saptamani_rambursare_cu_aprobare_fara_camt056():
    ctx = make_ctx(channel=Channel.DIRECT_DEBIT, dispute_type=DisputeType.DISPUTA_COMERCIANT,
                   executed_at=ts(2026, 10, 1, 9), notified_at=ts(2026, 10, 20, 10))
    out = evaluate(ctx)
    assert outcome(out, "PAY-10") == "PAY_DD_REFUND"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE and t1(out).requires_human
    assert t1(out).deadline == eod(2026, 11, 3)            # 10 zile lucrătoare de la cerere
    escroc = decision(out, Question.RECUPERARE_ESCROC)
    assert escroc.decision == Verdict.RECUPERARE_PROPUSA and "PAY-10" in escroc.rule_ids
    assert not any(r.startswith("REC-") for r in escroc.rule_ids)
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_DD02_debit_direct_dupa_8_saptamani_raspuns_semnat_de_om():
    ctx = make_ctx(channel=Channel.DIRECT_DEBIT, dispute_type=DisputeType.EROARE_PROCESARE,
                   executed_at=ts(2026, 9, 1, 9), notified_at=ts(2026, 10, 28, 10))
    out = evaluate(ctx)
    assert outcome(out, "PAY-10") == "PAY_DD_WINDOW_EXPIRED"
    assert t1(out).decision == Verdict.NU_SE_APLICA_T1 and t1(out).requires_human


def test_DD03_debit_direct_fara_mandat_ramane_pe_art_173():
    ctx = make_ctx(channel=Channel.DIRECT_DEBIT)
    out = evaluate(ctx)
    assert hit(out, "PAY-10") is None
    assert outcome(out, "PAY-03") == "PAY_REFUND_DUE"
    assert decision(out, Question.RECUPERARE_ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_DD04_debit_direct_sepa_in_euro_fara_motiv():
    ctx = make_ctx(channel=Channel.DIRECT_DEBIT, dispute_type=DisputeType.DISPUTA_COMERCIANT,
                   amount=Money(value=80.0, currency="EUR"))
    assert hit(evaluate(ctx), "PAY-10").explanation.count("No reason is needed") == 1


def test_card_prezent_la_POS_conditia_candidat_10_3_cu_termen():
    ctx = make_ctx(channel=Channel.CARD, pos_entry_mode="chip", processing_date=date(2026, 10, 27))
    assert visa_condition(ctx) == "10.3"
    value, blocking, code = chargeback_recoverable(ctx, _env())
    assert (value, code) == ("INCERT", "10.3") and blocking == ["DSP-24"]
    out = evaluate(ctx)
    assert outcome(out, "DSP-24") == "DSP_DEADLINE_UNVERIFIED"
    assert outcome(out, "DSP-25") == "DSP_FRAUD_REPORT_DUE"
    assert decision(out, Question.RECUPERARE_ESCROC).decision == Verdict.CHARGEBACK


def test_card_prezent_termen_expirat_nu_mai_e_chargeback():
    ctx = make_ctx(channel=Channel.CARD, pos_entry_mode="contactless", processing_date=date(2026, 1, 5),
                   executed_at=ts(2026, 1, 5), notified_at=ts(2026, 10, 27))
    assert chargeback_recoverable(ctx, _env())[:2] == ("NU", ["DSP-24"])


def test_retragere_ATM_neautorizata_merge_la_om():
    ctx = make_ctx(channel=Channel.CARD, pos_entry_mode="atm", purchase_type="atm_cash")
    assert visa_condition(ctx) is None
    assert chargeback_recoverable(ctx, _env())[:2] == ("INCERT", ["DSP-52"])


def test_problemele_cu_comerciantul_se_mapeaza_pe_13x():
    for issue, cond in (("recurring_cancelled", "13.2"), ("not_as_described", "13.3"),
                        ("credit_not_processed", "13.6"), ("cancelled", "13.7")):
        ctx = make_ctx(channel=Channel.CARD, dispute_type=DisputeType.DISPUTA_COMERCIANT, merchant_issue=issue)
        assert visa_condition(ctx) == cond
        assert chargeback_recoverable(ctx, _env())[2] == cond


def test_13_1_agentie_de_turism_asteapta_30_de_zile_iar_data_de_livrare_inlocuieste_asteptarea():
    base = {"channel": Channel.CARD, "dispute_type": DisputeType.DISPUTA_COMERCIANT, "visa_condition": "13.1",
            "processing_date": date(2026, 10, 1)}
    travel = visa_dispute_window(make_ctx(merchant_mcc="4722", **base), _env())
    assert travel.earliest == date(2026, 10, 31)
    promised = visa_dispute_window(make_ctx(expected_delivery_date=date(2026, 11, 10), **base), _env())
    assert promised.earliest == date(2026, 11, 10) and promised.due == date(2027, 3, 10)


def test_VU01_client_vulnerabil_merge_la_om_si_nu_are_dosar_de_neglijenta():
    ctx = make_ctx(vulnerability_signals=["varsta", "constrangere"], screen_showed_amount_and_payee=True,
                   client_admits_approving_in_app=True, sca_performed=True)
    out = evaluate(ctx)
    assert outcome(out, "DP-04") == "DP_VULNERABLE_CUSTOMER"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE and "DP-04" in t1(out).rule_ids
    client = decision(out, Question.RECUPERARE_CLIENT)
    assert client.decision == Verdict.NU_RECOMANDAM_RECUPERARE and client.requires_human
    assert all(d.requires_human for d in out.decisions)


def test_VU02_inainte_de_neglijenta_grava_clientul_e_invitat_sa_relateze():
    ctx = make_ctx(screen_showed_amount_and_payee=True, client_admits_approving_in_app=True, sca_performed=True)
    client = decision(evaluate(ctx), Question.RECUPERARE_CLIENT)
    assert client.decision == Verdict.RECUPERARE_PROPUSA
    assert any("account of events" in m for m in client.missing_evidence)
    invited = decision(evaluate(make_ctx(screen_showed_amount_and_payee=True, client_admits_approving_in_app=True,
                                         sca_performed=True, customer_account_invited=True)),
                       Question.RECUPERARE_CLIENT)
    assert not any("account of events" in m for m in invited.missing_evidence)


def test_recunoasterile_neconfirmate_cer_un_om():
    out = evaluate(make_ctx(unconfirmed_admissions=["client_admits_sharing_credentials"]))
    assert outcome(out, "DSP-57") == "extragere_de_confirmat"
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE


def test_review_flags_si_reason_codes_au_forma_pentru_consola():
    from versoml.zone_client.service import reason_codes, review_flags

    doc = {"case_id": "CT-2026-TEST", "status": "RAMBURSAT", "llm_mode": "offline",
           "classification_conflict": {"reason": "the records say card fraud"},
           "extracted": {"to_confirm": ["client_admits_approving_in_app"]},
           "rules": {"hits": [{"rule_id": "DP-04", "outcome": "DP_VULNERABLE_CUSTOMER", "explanation": "x"}]}}
    flags = review_flags(doc)
    assert [f["code"] for f in flags] == ["type_conflict", "llm_degraded", "to_confirm", "vulnerability"]
    assert all(set(f) == {"code", "severity", "text"} and f["severity"] in ("info", "warn", "block") for f in flags)
    assert flags[-1]["severity"] == "block"
    codes = {c["code"]: c for c in reason_codes(["approve", "reject"])}
    assert codes["OTHER"]["actions"] == ["approve", "reject"] and codes["OTHER"]["note_required"] is True
    assert codes["FRAUD_SUSPECTED"]["actions"] == ["reject"] and codes["FRAUD_SUSPECTED"]["note_required"] is False
    assert all(set(c) == {"code", "label", "actions", "note_required"} for c in codes.values())
