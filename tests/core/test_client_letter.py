"""The letter the client zone writes without an LLM: in the customer's language, specific, with the decision first and
what CJEU C-203/22 and Law 209/2019 ask a letter to say, and clean for the wall."""

from __future__ import annotations

import re

import pytest

from versoml.shared.rules import check_complaint_letter
from versoml.wall import check_letter
from versoml.zone_client import numeric_check as N
from versoml.zone_client import prompts as P
from versoml.zone_client.agents import _fallback_letter, letter_language, ro_reference

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
          merchant: str | None = None, language: str | None = None) -> dict:
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
        "extracted": {"points": [{"text": p, "quote": p} for p in points],
                      **({"language": language} if language else {})},
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


def points_of(st: dict) -> list[str]:
    return [p["text"] for p in st["extracted"]["points"]]


def romanian(st: dict) -> dict:
    return {**st, "extracted": {**st["extracted"], "language": "ro"}}


def numbers_ok(st: dict, letter) -> dict:
    """The numeric check with the case file a fixture state implies."""
    ctx = st["rule_context"]
    allowed = N.allowed_from_facts([], ctx["case_id"])
    allowed.add_content({k: ctx.get(k) for k in ("amount", "executed_at", "notified_at")}, "RON")
    for d in st["decisions"]:
        allowed.add_content({"deadline": d.get("deadline")}, "RON")
    back = st.get("refund") or {}
    if back.get("done") and back.get("amount"):
        allowed.add_content({k: back.get(k) for k in ("amount", "debited", "payer_liability")}, "RON",
                            kind="refund.instruction")
    return N.check(N.sections_of(letter.subject, [p.text for p in letter.paragraphs]), allowed)


RULE_ID = re.compile(r"\b(?:PAY|DSP|CMP|REC|URM|DP|AML)-\d{2}\b")


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
    assert len(re.findall(r"\bArticle \d+", text)) <= 1 and not RULE_ID.search(text)
    assert check_letter(text).passed, check_letter(text).reasons
    outcomes = {h.rule_id: h.outcome for h in check_complaint_letter(text, points_of(CASES[name]))}
    assert outcomes["CMP-03"] == "bloc_prezent" and outcomes["CMP-01"] == "toate_punctele"
    assert numbers_ok(CASES[name], letter)["passed"]
    words = len(" ".join(p.text for p in letter.paragraphs[1:-1]).split())
    assert 60 <= words <= 340, words


@pytest.mark.parametrize("name", CASES)
def test_a_romanian_complaint_gets_the_same_letter_in_romanian(name):
    st = romanian(CASES[name])
    letter = _fallback_letter(st)
    text = body(letter)
    assert letter.paragraphs[0].text == "Bună ziua, <CLIENT_1>,"
    assert letter.paragraphs[-1].text == f"Cu stimă,\nEchipa de contestații, {P.BANK_NAME}"
    assert "3.200,00 lei" in letter.subject and "3.200,00 lei" in text
    assert f"ne puteți suna la {P.HELPLINE}" in text and "numărul cazului CT-2026-123456" in text
    # Romanian formats and diacritics with a comma below, and none of the English letter's words
    assert "\u015f" not in text and "\u0163" not in text and "ț" in text
    assert not re.search(r"\bRON\s?\d|\b\d{1,3}(?:,\d{3})+\.\d{2}\b|\b(?:Oct|Nov|Aug)\b|\bT\+1\b|—|–", text)
    assert not re.search(r"\b(?:the|and|refund|you|your|claim)\b", text, re.IGNORECASE), text
    # no word-for-word calques from English
    assert not re.search(r"nu ezitați|liniștea dumneavoastră|cu succes|reimburs|la finalul zilei|vă rugăm", text, re.IGNORECASE)
    assert not RULE_ID.search(text)
    assert check_letter(text).passed, check_letter(text).reasons
    outcomes = {h.rule_id: h.outcome for h in check_complaint_letter(text, points_of(st))}
    assert outcomes == {"CMP-01": "toate_punctele", "CMP-03": "bloc_prezent"}, outcomes
    assert numbers_ok(st, letter)["passed"], numbers_ok(st, letter)["mismatches"]


def test_the_language_comes_from_the_intake_step():
    assert letter_language(romanian(CASES["refunded"])) == "ro"
    assert letter_language(CASES["refunded"]) == "en"
    assert letter_language({"complaint": {"text": "Nu am făcut eu plata, vă rog să-mi returnați banii."}}) == "ro"
    assert letter_language({}) == "en"


def test_refund_letter_gives_the_decision_first_and_cites_the_law_once():
    text = body(_fallback_letter(CASES["refunded"]))
    opening = text.split("\n\n")[1]
    assert opening.startswith("We have refunded the full amount of RON 3,200.00 to your account.")
    assert ("On 28 Oct 2026 you told us that you did not make the transfer that left your account earlier that day. "
            "Thank you for telling us so quickly.") in opening
    assert text.count("Article 173 of Law 209/2019") == 1 and "end of the next business day" in text
    assert "asking the bank that received the money to return it" in text


def test_refund_awaiting_approval_gives_the_deadline_and_the_merchant():
    letter = _fallback_letter(CASES["awaiting_approval"])
    assert letter.subject == "Refund of RON 3,200.00 for a card payment to ELECTRO-SHOP SRL"
    assert "We will refund the full amount of RON 3,200.00 to your account by 29 Oct 2026, 23:59." in body(letter)
    assert "through Visa" in body(letter)
    instant = _fallback_letter(state("RAMBURSEAZA", channel="transfer_instant"))
    assert instant.subject == "Refund of RON 3,200.00 for an instant transfer"


def test_app_letter_answers_the_question_and_gives_the_next_date():
    letter = _fallback_letter(CASES["app"])
    text = body(letter)
    assert letter.subject == "Your claim about the RON 3,200.00 instant transfer"
    assert text.split("\n\n")[1].startswith("We cannot refund the instant transfer of RON 3,200.00 straight away")
    assert "You asked why we did not stop the payment." in text and "does not apply" in text
    assert "with their answer by 18 Nov 2026" in text and "hang up and call us" in text
    assert letter.points_answered == ["Why didn't the bank stop the transfer?"]


def test_late_letter_cites_the_13_months():
    text = body(_fallback_letter(CASES["late"]))
    assert text.split("\n\n")[1].startswith("We cannot refund the card payment of RON 3,200.00 to GlobalApps Store")
    assert "Article 169 of Law 209/2019 allows 13 months" in text and "You told us after that period." in text
    assert "made on 14 Aug 2025" in text and "On 26 Oct 2026 you told us" in text


def test_exception_letter_gives_no_reason_only_the_date():
    text = body(_fallback_letter(CASES["exception"], ["Law 209/2019, art. 173"], reviewed_by="OPERATOR-01"))
    assert text.split("\n\n")[1].startswith("We need more time to finish our review of your claim")
    assert "We will send you our decision on the refund by 18 Nov 2026." in text
    assert "Article" not in text and "fraud" not in text.lower()
    # a fraud hold says nothing about how the bank decides: no data, factors, reviewer or rules
    for said in ("we looked at", "main factor", "reviewed and approved", "The rules we applied", "copy of the"):
        assert said not in text


def test_the_letter_explains_the_decision():
    """CJEU C-203/22 (Dun & Bradstreet) and Law 209/2019, art. 224-225: the data used, the main factor, what would
    change an unfavorable outcome, the right to the documents and to contest, the complaint routes."""
    late = body(_fallback_letter(CASES["late"], ["Law 209/2019, art. 169"], reviewed_by="OPERATOR-01"))
    assert "To decide, we looked at your complaint, the record of the payment and the date you reported it." in late
    assert "The main factor was the time between the payment and your report" in late
    assert "If you have documents showing that you told us about this payment earlier" in late
    assert "A member of our disputes team reviewed and approved this decision." in late
    assert "give us your point of view or ask for the decision to be reviewed again" in late
    assert "The rules we applied: Law 209/2019, art. 169." in late
    app = state("NU_SE_APLICA_T1", dispute_type="app", channel="transfer_instant", recovery="RECHEMARE")
    app["rule_context"].update(sca_performed=True, screen_showed_amount_and_payee=True, device_known=True)
    text = body(_fallback_letter(app))
    assert "we looked at your complaint, the record of the payment, the authentication record, the device used for " \
           "the payment and the date you reported it" in text
    assert "The main factors were that the payment was confirmed in your banking app and that the screen showed" in text
    assert "If you did not approve the payment in the app yourself, tell us in your reply" in text
    # a person who did not sign is not claimed; a favorable decision offers the documents, not a new review
    refund = body(_fallback_letter(CASES["refunded"]))
    assert "reviewed and approved" not in refund and "ask for the decision to be reviewed again" not in refund
    assert "You can ask us for a copy of the information and documents we used for this decision" in refund


def test_the_customers_words_are_never_quoted_back():
    points = ("Please give me my money back.", "I think it's a ring, block that account.",
              "My neighbour says the shop on the corner sells phones cheaper.")
    st = state("RAMBURSEAZA", points=points)
    letter = _fallback_letter(st)
    text = body(letter)
    assert letter.points_answered == list(points)              # the writer's own list still copies them exactly
    assert "ring" not in text and "neighbour" not in text and "“" not in text
    assert "You asked us to act on the account that received the money." in text
    assert "We have read the other details in your message" in text
    # CMP-01 reads the letter: the point about the shop has no answer in it, and says so
    hit = check_complaint_letter(text, points)[0]
    assert hit.outcome == "CMP_POINT_UNANSWERED" and "shop on the corner" in hit.explanation
    ro = body(_fallback_letter(romanian(state("RAMBURSEAZA", points=("Blocați contul escrocilor!",)))))
    assert "escroc" not in ro and "Ne-ați cerut să luăm măsuri privind contul care a primit banii." in ro


def test_a_refund_that_keeps_the_customers_share_says_what_went_back():
    kept = state("RAMBURSEAZA", refunded=True)
    kept["refund"] = {"done": True, "amount": 3050.0, "currency": "RON", "debited": 3200.0, "payer_liability": 150.0,
                      "retained": True}
    letter = _fallback_letter(kept)
    text = body(letter)
    assert "We have refunded RON 3,050.00 to your account" in text and "the first RON 150.00" in text
    assert letter.subject == "Refund of RON 3,050.00 for a transfer"
    assert "full amount" not in text and check_letter(text).passed
    assert numbers_ok(kept, letter)["passed"], numbers_ok(kept, letter)["mismatches"]
    assert "ask for the decision to be reviewed again" in text            # keeping a share is unfavorable
    ro = body(_fallback_letter(romanian(kept)))
    assert "V-am rambursat suma de 3.050,00 lei" in ro and "primii 150,00 lei din pierdere" in ro
    assert "We have refunded the full amount" in body(_fallback_letter(CASES["refunded"]))


def test_romanian_letters_read_like_a_romanian_bank():
    text = body(_fallback_letter(romanian(CASES["refunded"]), ["Law 209/2019, art. 173", "CJEU ruling C-70/25"]))
    assert text.split("\n\n")[1].startswith("V-am rambursat integral suma de 3.200,00 lei în contul dumneavoastră.")
    assert "Conform art. 173 din Legea nr. 209/2019, suntem obligați să rambursăm" in text
    assert "Prevederile legale aplicate: Legea nr. 209/2019, art. 173; hotărârea CJUE în cauza C-70/25." in text
    assert P.ADR_TEXT_RO in text
    late = body(_fallback_letter(romanian(CASES["late"])))
    assert "efectuată pe 14 august 2025" in late and "Pe 26 octombrie 2026 ne-ați informat" in late
    app = _fallback_letter(romanian(CASES["app"]))
    assert app.subject == "Reclamația dumneavoastră privind transferul instant de 3.200,00 lei"
    assert "Ne-ați întrebat de ce nu am oprit plata." in body(app)
    assert "vă vom comunica răspunsul acesteia până la 18 noiembrie 2026" in body(app)
    assert ro_reference("GEO 50/2010, art. 42 and art. 43") == "OUG nr. 50/2010, art. 42 și art. 43"


def test_the_declared_facts_letter_asks_for_the_details_in_either_language():
    st = state("INFORMATII_SUPLIMENTARE")
    st["declared"] = {"amount": {"value": 1850.0, "currency": "RON"}}
    st["match"] = {"customer_ref": None}
    en = body(_fallback_letter(st))
    assert en.split("\n\n")[1].startswith("We cannot decide on your claim about the payment of RON 1,850.00 yet")
    assert "the phone number or IBAN registered with us" in en and "by 18 Nov 2026" in en
    ro = body(_fallback_letter(romanian(st)))
    assert "Nu putem lua încă o decizie cu privire la reclamația dumneavoastră privind plata de 1.850,00 lei" in ro
    assert "numărul de telefon sau IBAN-ul înregistrat la noi" in ro and "până la 18 noiembrie 2026" in ro
    assert check_letter(ro).passed and check_letter(en).passed


# ---------------------------------------------------------------- the DNSC draft

def test_the_dnsc_draft_carries_the_customers_link_as_unconfirmed():
    from versoml.zone_client.agents import _fallback_dnsc

    draft = _fallback_dnsc({"domain": "livrare-bancademo.example", "url": "https://livrare-bancademo.example/colet",
                            "phones": ["+40721123456"], "domain_age_hours": 30})
    assert "URL reported by the customer, not yet confirmed by the bank: https://livrare-bancademo.example/colet." \
           in draft.body
    assert "the customer says the scammer used, not yet confirmed by the bank: +40721123456" in draft.body
    assert "Domain: livrare-bancademo.example." in draft.body and draft.indicators[0] == "livrare-bancademo.example"
