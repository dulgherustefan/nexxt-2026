"""Pachetul REC (extensie, [S]/[U]): rechemarea transferurilor, după docs/05 §3–4 și ghidurile EPC."""

from __future__ import annotations

from rules_testkit import decision, deadline, eod, hit, make_ctx, outcome, ts
from versoml.contracts import Channel, DisputeType, Money, Question, Verdict
from versoml.shared.rules import evaluate

ESCROC = Question.RECUPERARE_ESCROC


def iban_ro(bank: str, account: str) -> str:
    """IBAN RO sintetic, cu cifre de control valide (ISO 7064 mod 97-10); băncile BDEM/XBNK nu există la BNR."""
    bban = bank + account
    digits = "".join(str(int(c, 36)) for c in bban + "RO00")
    return f"RO{98 - int(digits) % 97:02d}{bban}"


BDEM = iban_ro("BDEM", "1B31007593840000")
XBNK = iban_ro("XBNK", "1B31007593840000")


def test_iban_sintetic_are_cifre_de_control_valide():
    for iban in (BDEM, XBNK):
        rearranged = iban[4:] + iban[:4]
        assert int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def test_REC01_REC02_sct_inst_eur_camt056_frad_si_15_zile_bancare():
    ctx = make_ctx(channel=Channel.TRANSFER_INSTANT, amount=Money(value=1500.0, currency="EUR"),
                   beneficiary_iban="DE89370400440532013000", executed_at=ts(2026, 11, 20, 9),
                   notified_at=ts(2026, 11, 20, 10))
    out = evaluate(ctx)
    assert outcome(out, "REC-01") == "camt056_FRAD"
    due = deadline(out, "REC-02").due_at
    assert due == eod(2026, 12, 15)                     # 30.11 și 1.12 nu sunt zile bancare în calendarul RO
    assert "recall" in deadline(out, "REC-02").name.lower()
    esc = decision(out, ESCROC)
    assert esc.decision == Verdict.RECHEMARE and esc.requires_human and esc.deadline == due
    assert any("camt.056" in a for a in esc.next_actions)
    target = evaluate(ctx, {"banking_calendar": "target2"})
    assert deadline(target, "REC-02").due_at == eod(2026, 12, 11)


def test_REC02_sct_non_instant_foloseste_parametrul_U():
    ctx = make_ctx(amount=Money(value=900.0, currency="EUR"), notified_at=ts(2026, 11, 20, 10),
                   executed_at=ts(2026, 11, 19, 9))
    assert "an assumption" in hit(evaluate(ctx), "REC-02").explanation
    out = evaluate(ctx, {"sct_recall_answer_banking_days": 10})
    assert deadline(out, "REC-02").due_at == eod(2026, 12, 8)


def test_REC03_beneficiar_la_banca_demo_blocare_interna():
    out = evaluate(make_ctx(beneficiary_iban=BDEM))
    assert outcome(out, "REC-03") == "rechemare_interna"
    assert hit(out, "REC-01") is None and hit(out, "REC-04") is None
    esc = decision(out, ESCROC)
    assert esc.decision == Verdict.RECHEMARE and esc.deadline is None
    assert any("Block the amount in the beneficiary's account internally" in a for a in esc.next_actions)
    other = evaluate(make_ctx(beneficiary_iban=XBNK), {"same_bank_codes": ["BDEM", "XBNK"]})
    assert outcome(other, "REC-03") == "rechemare_interna"


def test_REC04_ron_catre_alta_banca_procedura_neverificata():
    out = evaluate(make_ctx(beneficiary_iban=XBNK))
    assert outcome(out, "REC-04") == "rechemare_ron"
    assert not [d for d in out.deadlines if d.rule_id == "REC-04"]          # fără termen implicit [U]
    assert decision(out, ESCROC).decision == Verdict.RECHEMARE
    out10 = evaluate(make_ctx(beneficiary_iban=XBNK, now=ts(2026, 11, 20, 10), notified_at=ts(2026, 11, 20, 10)),
                     {"ron_recall_answer_banking_days": 10})
    assert deadline(out10, "REC-04").due_at == eod(2026, 12, 8)


def test_REC05_dupa_fereastra_de_13_luni_nu_se_propune_rechemarea():
    out = evaluate(make_ctx(executed_at=ts(2025, 8, 1), notified_at=ts(2026, 10, 27)))
    assert outcome(out, "REC-05") == "REC_WINDOW_EXPIRED"
    assert decision(out, ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_REC_app_rechemare_urgenta():
    out = evaluate(make_ctx(channel=Channel.TRANSFER_INSTANT, dispute_type=DisputeType.APP,
                            amount=Money(value=18500.0), beneficiary_new=True))
    esc = decision(out, ESCROC)
    assert esc.decision == Verdict.RECHEMARE
    assert esc.next_actions[0].startswith("URGENT")
    assert "PAY-12" in esc.rule_ids


def test_REC_nu_se_aplica_la_carduri_sau_la_disputa_cu_comerciantul():
    card = evaluate(make_ctx(channel=Channel.CARD, eci="07"))
    assert all(h.rule_id[:3] != "REC" for h in card.hits)
    merchant = evaluate(make_ctx(dispute_type=DisputeType.DISPUTA_COMERCIANT))
    assert decision(merchant, ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE
