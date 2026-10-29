"""The letter the client zone writes without an LLM: English, specific, one legal citation, and clean for the wall."""

from __future__ import annotations

import re

import pytest

from versoml.shared.rules import check_complaint_letter
from versoml.wall import check_letter
from versoml.zone_client import prompts as P
from versoml.zone_client.agents import _fallback_letter

# the copy notes' lint: none of these may appear in a letter
SLOP = [
    r"—|–", r"!", r"\bsuccessfully\b", r"\bplease\b", r"\bsorry\b", r"\bT\+1\b",
    r"\b(?:rest assured|do not hesitate|don't hesitate|we understand how|hope this (?:letter|message|email) finds you)\b",
    r"\b(?:pursuant to|hereby|herewith|the undersigned|kindly|please note|at your disposal|reclamation|dossier)\b",
    r"\breimburs\w*", r"\b\d{1,3}(?:\.\d{3})+(?:,\d{2})?\s?(?:lei|RON)\b|\b[\d.,]+\s?lei\b",
    r"\b(?:unauthoris|authoris|favour|colour|centre)\w*", r"\b\w+n't\b",
]


def state(verdict: str, *, dispute_type: str = "neautorizata", channel: str = "transfer", refunded: bool = False,
          recovery: str | None = None, points: tuple[str, ...] = ("Please give me my money back.",),
          executed: str = "2026-10-28T12:02:11+00:00", notified: str = "2026-10-28T12:05:30+00:00",
          merchant: str | None = None) -> dict:
    decisions = [{"question": "rambursare_t1", "decision": verdict, "deadline": "2026-10-29T21:59:59+00:00"},
                 {"question": "raspuns_reclamatie", "decision": "INCHIDE", "deadline": "2026-11-18T21:59:59+00:00"}]
    if recovery:
        decisions.append({"question": "recuperare_escroc", "decision": recovery})
    return {
        "case_id": "CT-2026-123456",
        "rule_context": {"case_id": "CT-2026-123456", "amount": {"value": 3200.0, "currency": "RON"},
                         "executed_at": executed, "notified_at": notified, "channel": channel,
                         "dispute_type": dispute_type, "fact_ids": {"amount": "EV-004", "notified_at": "EV-003"}},
        "decisions": decisions,
        "extracted": {"points": [{"text": p, "quote": p} for p in points]},
        "refund": {"done": refunded},
        "records": {"transaction": {"counterparty_name": merchant} if merchant else {}},
    }


CASES = {
    "refunded": state("RAMBURSEAZA", refunded=True, recovery="RECHEMARE"),
    "awaiting_approval": state("RAMBURSEAZA_CU_APROBARE", channel="card", merchant="ELECTRO-SHOP SRL",
                               recovery="CHARGEBACK"),
    "app": state("NU_SE_APLICA_T1", dispute_type="app", channel="transfer_instant", recovery="RECHEMARE",
                 points=("Why didn't the bank stop the transfer?",)),
    "late": state("RESPINGE_TARDIV", channel="card", merchant="GlobalApps Store",
                  executed="2025-08-14T10:20:00+00:00", notified="2026-10-26T09:00:00+00:00"),
    "exception": state("EXCEPTIE_FRAUDA_CLIENT", channel="card", merchant="Moda Demo Store"),
}


def body(letter) -> str:
    return "\n\n".join(p.text for p in letter.paragraphs)


@pytest.mark.parametrize("name", CASES)
def test_fallback_letter_is_plain_and_complete(name):
    letter = _fallback_letter(CASES[name])
    text = body(letter)
    assert letter.paragraphs[0].text == "Dear <CLIENT_1>,"
    assert letter.paragraphs[-1].text == f"Kind regards,\nDisputes team, {P.BANK_NAME}"
    assert "RON 3,200.00" in letter.subject and "RON 3,200.00" in text
    assert f"call us on {P.HELPLINE}" in text and "quoting case CT-2026-123456" in text
    for pattern in SLOP:
        assert not re.search(pattern, text + "\n" + letter.subject), (pattern, text)
    assert len(re.findall(r"\bArticle \d+", text)) <= 1
    assert check_letter(text).passed, check_letter(text).reasons
    outcomes = {h.rule_id: h.outcome for h in check_complaint_letter(text, letter.points_answered, letter.points_answered)}
    assert outcomes["CMP-03"] == "bloc_prezent" and outcomes["CMP-01"] == "toate_punctele"
    words = len(" ".join(p.text for p in letter.paragraphs[1:-1]).split())
    assert 40 <= words <= 230, words


def test_refund_letter_says_what_happened_and_cites_the_law_once():
    text = body(_fallback_letter(CASES["refunded"]))
    assert "On 28 Oct 2026 you told us that you did not make the transfer of RON 3,200.00 earlier that day." in text
    assert "We have refunded the full amount to your account. Thank you for telling us so quickly." in text
    assert text.count("Article 173 of Law 209/2019") == 1 and "end of the next business day" in text
    assert "asking the bank that received the money to return it" in text


def test_refund_awaiting_approval_gives_the_deadline_and_the_merchant():
    letter = _fallback_letter(CASES["awaiting_approval"])
    assert letter.subject == "Refund of RON 3,200.00 for a card payment to ELECTRO-SHOP SRL"
    assert "We will refund the full amount to your account by 29 Oct 2026, 23:59." in body(letter)
    assert "through Visa" in body(letter)


def test_app_letter_answers_the_question_and_gives_the_next_date():
    letter = _fallback_letter(CASES["app"])
    text = body(letter)
    assert letter.subject == "Your claim about the RON 3,200.00 instant transfer"
    assert "You asked why we did not stop the payment." in text and "does not apply" in text
    assert "with their answer by 18 Nov 2026" in text and "hang up and call us" in text
    assert letter.points_answered == ["Why didn't the bank stop the transfer?"]


def test_late_letter_cites_the_13_months():
    text = body(_fallback_letter(CASES["late"]))
    assert "Article 169 of Law 209/2019 allows 13 months" in text and "we cannot refund this payment" in text
    assert "on 14 Aug 2025" in text and "On 26 Oct 2026 you told us" in text


def test_exception_letter_gives_no_reason_only_the_date():
    text = body(_fallback_letter(CASES["exception"]))
    assert "We need more time to finish our review, and we will send you our answer by 18 Nov 2026." in text
    assert "Article" not in text and "fraud" not in text.lower()


def test_points_are_copied_exactly_for_cmp_01():
    letter = _fallback_letter(state("RAMBURSEAZA", points=("Please give me my money back.", "I think it's a ring, "
                                                                                            "block that account.")))
    assert letter.points_answered == ["Please give me my money back.", "I think it's a ring, block that account."]
    assert "You also wrote: “I think it's a ring, block that account.”" in body(letter)


def test_a_refund_that_keeps_the_customers_share_says_what_went_back():
    kept = state("RAMBURSEAZA", refunded=True)
    kept["refund"] = {"done": True, "amount": 3050.0, "currency": "RON", "debited": 3200.0, "payer_liability": 150.0,
                      "retained": True}
    text = body(_fallback_letter(kept))
    assert "We have refunded RON 3,050.00 to your account" in text and "the first RON 150.00" in text
    assert "full amount" not in text and check_letter(text).passed
    assert "We have refunded the full amount" in body(_fallback_letter(CASES["refunded"]))
