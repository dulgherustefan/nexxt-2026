"""Testele CMP și DP din docs/context/11 §6 (TC-34…TC-36, TC-38) și excepțiile EX-21, EX-22.

TC-37 (cererea CSALB de ștergere din Biroul de Credit) nu ține de contestațiile de plată din MVP.
TC-38, partea ANAF (consimțământul pentru venit), nu se aplică: motorul nu interoghează ANAF.
"""

from __future__ import annotations

from datetime import date

import pytest

from rules_testkit import DEFAULTS, decision, deadline, eod, hit, make_ctx, outcome, t1, ts
from versoml.contracts import DisputeType, Question, Verdict
from versoml.shared.rules import ParamsError, check_adr_block, check_complaint_letter, check_points_answered, evaluate
from versoml.shared.rules import set_params
from versoml.shared.rules.packs.cmp import credit_complaint_deadline
from versoml.shared.rules.packs.dp import explanation_complete

ANSWER = Question.RASPUNS_RECLAMATIE
FULL_ADR = ("Dacă nu sunteți de acord, vă puteți adresa ANPC, ANAF, BNR sau Centrului de Soluționare Alternativă "
            "a Litigiilor în Domeniul Bancar (CSALB).")


def test_TC34_ceasul_porneste_la_primire_nu_la_posta_si_alerta_de_raspuns_intermediar():
    # ștampila poștei 23.10.2026; primită 28.10.2026; fără răspuns intermediar la 17.11.2026
    ctx = make_ctx(executed_at=ts(2026, 10, 20), notified_at=ts(2026, 10, 28, 10),
                   complaint_received_at=ts(2026, 10, 28, 10), now=ts(2026, 11, 17, 9))
    out = evaluate(ctx)
    assert deadline(out, "CMP-01").due_at == eod(2026, 11, 18)
    assert deadline(out, "CMP-02").due_at == eod(2026, 12, 18)
    assert outcome(out, "CMP-02") == "CMP_HOLDING_REPLY_REQUIRED"
    assert outcome(out, "CMP-01") == "CMP_DEADLINE_RISK"
    assert decision(out, ANSWER).deadline == eod(2026, 11, 18)


def test_EX21_reclamatie_prin_posta_inregistrata_mai_tarziu():
    # primirea contează; notificarea despre plată poate fi mai veche (ex. apel la call center)
    ctx = make_ctx(notified_at=ts(2026, 10, 23, 9), complaint_received_at=ts(2026, 10, 28, 10))
    out = evaluate(ctx)
    assert deadline(out, "CMP-01").due_at == eod(2026, 11, 18)
    assert t1(out).deadline == eod(2026, 10, 26)        # T+1 curge de la notificare


def test_TC35_reclamatie_la_credit_30_de_zile():
    assert credit_complaint_deadline(date(2026, 11, 2)) == date(2026, 12, 2)
    out = evaluate(make_ctx(credit_fraud=True, notified_at=ts(2026, 11, 2, 12)))
    assert deadline(out, "CMP-04").due_at == eod(2026, 12, 2)
    assert hit(out, "CMP-01") is None


def test_TC36_raspuns_final_fara_cai_de_sesizare_e_blocat():
    assert check_adr_block("Vă returnăm suma.").outcome == "CMP_ADR_BLOCK_MISSING"
    partial = check_adr_block("Vă puteți adresa ANPC, BNR sau CSALB.")
    assert partial.outcome == "CMP_ADR_BLOCK_MISSING" and "ANAF" in partial.explanation
    assert check_adr_block(FULL_ADR).outcome == "bloc_prezent"
    assert check_adr_block(FULL_ADR.replace("ș", "ş")).outcome == "bloc_prezent"      # textul se normalizează


def test_TC38_configurarea_care_ar_scoate_omul_e_respinsa():
    with pytest.raises(ParamsError) as exc:
        set_params({"require_human_for_unfavourable": False})
    assert exc.value.errors[0]["code"] == "DP_HUMAN_REVIEW_REQUIRED"
    with pytest.raises(ParamsError):
        evaluate(make_ctx(), {"require_human_for_unfavourable": False})
    assert set_params({"require_human_for_unfavourable": True})["require_human_for_unfavourable"] is True


@pytest.mark.parametrize("external, due", [(False, (2026, 11, 18)), (True, (2026, 12, 18))])
def test_EX22_prelungirea_doar_cu_motiv_independent_de_banca(external, due):
    ctx = make_ctx(notified_at=ts(2026, 10, 28, 10), now=ts(2026, 11, 16, 9),
                   holding_reply_sent_at=ts(2026, 11, 16, 8), delay_reason_external=external)
    out = evaluate(ctx)
    assert outcome(out, "CMP-02") == ("prelungire_valida" if external else "prelungire_nepermisa")
    assert decision(out, ANSWER).deadline == eod(*due)


def test_CMP01_scrisoarea_raspunde_la_fiecare_punct():
    points = ["Vreau banii înapoi", "De ce nu ați blocat plata?"]
    assert check_points_answered(points, ["vreau banii înapoi"]).outcome == "CMP_POINT_UNANSWERED"
    assert check_points_answered(points, points).outcome == "toate_punctele"
    hits = check_complaint_letter(FULL_ADR, points, points)
    assert [h.rule_id for h in hits] == ["CMP-01", "CMP-03"] and all(h.version for h in hits)


def test_CMP_raspunsul_cere_om_si_contine_caile_de_sesizare():
    out = evaluate(make_ctx())
    answer = decision(out, ANSWER)
    assert answer.requires_human and answer.decided_by == "rules+human"
    assert {"CMP-01", "CMP-02", "CMP-03"} <= set(answer.rule_ids)
    assert any("ANPC, ANAF, BNR and CSALB" in a for a in answer.next_actions)
    assert answer.decision == t1(out).decision


# ---------------------------------------------------------------- DP-02, DP-03


@pytest.mark.parametrize("kw, question, verdict", [
    ({"executed_at": ts(2025, 8, 1), "notified_at": ts(2026, 10, 27)}, Question.RAMBURSARE_T1, Verdict.RESPINGE_TARDIV),
    ({"hold_signal": True, "hold_authority_notified": True}, Question.RAMBURSARE_T1, Verdict.EXCEPTIE_FRAUDA_CLIENT),
    ({"dispute_type": DisputeType.APP}, Question.RAMBURSARE_T1, Verdict.NU_SE_APLICA_T1),
    ({"screen_showed_amount_and_payee": True, "client_admits_approving_in_app": True, "sca_performed": True},
     Question.RECUPERARE_CLIENT, Verdict.RECUPERARE_PROPUSA),
])
def test_DP02_deciziile_defavorabile_le_semneaza_un_om(kw, question, verdict):
    out = evaluate(make_ctx(**kw), DEFAULTS)
    d = decision(out, question)
    assert d.decision == verdict
    assert d.requires_human and d.decided_by == "rules+human" and "DP-02" in d.rule_ids
    assert outcome(out, "DP-02") == "DP_HUMAN_REVIEW_REQUIRED"


def test_DP02_scorul_m2_e_doar_semnal_pentru_om():
    out = evaluate(make_ctx(client_fraud_score=0.93))
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE
    assert "DP-02" in t1(out).rule_ids and "URM-03" in t1(out).rule_ids
    assert any("EV-" in c for line in t1(out).rationale for c in line.cites)


def test_DP03_fiecare_decizie_are_regula_si_explicatie():
    out = evaluate(make_ctx())
    assert all(explanation_complete(d) for d in out.decisions)
    assert outcome(out, "DP-03") is None
