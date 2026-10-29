"""The numeric verifier on adversarial drafts: a wrong amount, date, time, IBAN fragment, case ID, phone number or link
is caught, with the value on file, and so is a value on file written in the wrong role (a payment date given as the
deadline); the customer's own quoted words are not checked, except for links and phone numbers. Client zone (English
and Romanian letters) and AML zone (Romanian formats)."""

from __future__ import annotations

from versoml.zone_aml import verificare_numerica as VN
from versoml.zone_client import numeric_check as N
from versoml.zone_client.agents import _fallback_letter

CASE = "CT-2026-123456"
FACTS = [
    {"kind": "bank.transaction", "labels": {"trust": "trusted"},
     "content": {"tx_id": "TX-1", "amount": 3200.0, "currency": "RON", "ts": "2026-10-28T14:02:11+02:00",
                 "counterparty_iban": "RO61BDEM1777286093723598"}},
    {"kind": "clock.started", "labels": {"trust": "trusted"},
     "content": {"notified_at": "2026-10-28T14:05:30+02:00", "t1_deadline": "2026-10-29T23:59:59+02:00",
                 "answer_deadline": "2026-11-18T23:59:59+02:00"}},
    {"kind": "complaint.extracted", "labels": {"trust": "untrusted"}, "content": {"mentioned_amounts": [2.99, 9000.0]}},
    {"kind": "declared.statement", "labels": {"trust": "untrusted"},
     "content": {"amount": {"value": 1850.0, "currency": "RON"}, "date": "2026-10-20"}},
]
GOOD = ("On 28 Oct 2026 you told us that you did not make the transfer of RON 3,200.00 at 14:02. We will refund the "
        "full amount by 29 Oct 2026, 23:59, and answer by 18 Nov 2026, quoting case CT-2026-123456. The money went to "
        "RO61 BDEM •••• 3598.")


def allowed(**kw):
    return N.allowed_from_facts(FACTS, CASE, **kw)


def test_a_correct_letter_passes():
    out = N.check([("paragraph 1", GOOD)], allowed())
    assert out["passed"] and out["checked"] == 8 and out["mismatches"] == []


def test_adversarial_values_are_caught_with_the_value_on_file():
    bad = (GOOD.replace("RON 3,200.00", "RON 3,500.00").replace("29 Oct 2026", "30 Oct 2026")
           .replace("14:02", "15:20").replace(CASE, "CT-2026-999999").replace("•••• 3598", "•••• 1111"))
    out = N.check([("paragraph 2", bad)], allowed())
    found = {m["kind"]: m for m in out["mismatches"]}
    assert not out["passed"] and set(found) == {"amount", "date", "time", "case_id", "iban_tail"}
    assert found["amount"] == {"value": "RON 3,500.00", "expected": "RON 3,200.00", "where": "paragraph 2",
                               "kind": "amount"}
    assert found["date"]["expected"] == "29 Oct 2026" and found["case_id"]["expected"] == CASE
    assert "you wrote “RON 3,500.00”, but the case file has RON 3,200.00" in N.feedback(out["mismatches"])


def test_untrusted_amounts_are_not_on_file_unless_declared():
    assert not N.check([("p", "We refunded RON 9,000.00.")], allowed())["passed"]          # the customer's text only
    assert not N.check([("p", "The payment of RON 1,850.00 you told us about.")], allowed())["passed"]
    declared = allowed(include_untrusted_kinds=("declared.statement",))
    assert N.check([("p", "The payment of RON 1,850.00 you told us about on 20 Oct 2026.")], declared)["passed"]


def test_quoted_customer_words_and_other_formats():
    assert N.check([("p", "You also wrote: “mi-au luat 3.494,60 RON pe 10.09.2026”.")], allowed())["passed"]
    values = {v["kind"] for v in N.extract("Paid RON 3,200.00 on 2026-10-28 and 28.10.2026, 3200 RON, October 28, 2026")}
    assert values == {"amount", "date"}


def test_the_fallback_letter_passes_its_own_check():
    state = {"case_id": CASE,
             "rule_context": {"case_id": CASE, "amount": {"value": 3200.0, "currency": "RON"},
                              "executed_at": "2026-10-28T14:02:11+02:00", "notified_at": "2026-10-28T14:05:30+02:00",
                              "channel": "transfer", "dispute_type": "neautorizata", "fact_ids": {}},
             "decisions": [{"question": "rambursare_t1", "decision": "RAMBURSEAZA_CU_APROBARE",
                            "deadline": "2026-10-29T23:59:59+02:00"},
                           {"question": "raspuns_reclamatie", "decision": "INCHIDE",
                            "deadline": "2026-11-18T23:59:59+02:00"}],
             "extracted": {"points": [{"text": "Please give me my money back.", "quote": ""}]},
             "refund": {"done": False}, "records": {"transaction": {}}}
    letter = _fallback_letter(state, ["Law 209/2019, art. 173"])
    out = N.check(N.sections_of(letter.subject, [p.text for p in letter.paragraphs]), allowed())
    assert out["passed"], out["mismatches"]
    assert any(p.text == "The rules we applied: Law 209/2019, art. 173." for p in letter.paragraphs)


def test_a_value_on_file_in_the_wrong_role_is_caught():
    # the payment date (28 Oct) written as the refund deadline: on file, but not as a deadline
    out = N.check([("paragraph 1", "We will refund the full amount by 28 Oct 2026, 23:59.")], allowed())
    [m] = out["mismatches"]
    assert m["role"] == "deadline" and m["value"] == "28 Oct 2026" and m["expected"] == "29 Oct 2026"
    assert "you wrote “28 Oct 2026” as a deadline" in N.feedback(out["mismatches"])
    # and a deadline written as the day the customer told us
    out = N.check([("p", "On 29 Oct 2026 you told us that you did not make the transfer.")], allowed())
    assert [m["role"] for m in out["mismatches"]] == ["report"]
    told = ("On 28 Oct 2026 you told us that you did not make the transfer of RON 3,200.00 on 28 Oct 2026. We will "
            "refund you by 29 Oct 2026, 23:59.")
    assert N.check([("p", told)], allowed())["passed"]


def test_refund_and_share_amounts_keep_their_roles():
    facts = FACTS + [{"kind": "refund.instruction", "labels": {"trust": "trusted"},
                      "content": {"amount": 3050.0, "currency": "RON", "debited": 3200.0, "payer_liability": 150.0}}]
    ok = N.allowed_from_facts(facts, CASE)
    good = "We have refunded RON 3,050.00 to your account: the first RON 150.00 of the loss stays with you."
    assert N.check([("p", good)], ok)["passed"]
    out = N.check([("p", "We have refunded RON 3,200.00 to your account.")], ok)
    assert [(m["role"], m["expected"]) for m in out["mismatches"]] == [("refund", "RON 3,050.00")]


def test_romanian_letters_are_read_in_romanian_formats():
    ro = ("V-am rambursat integral suma de 3.200,00 lei în contul dumneavoastră până la 29 octombrie 2026, ora 23:59. "
          "Pe 28 octombrie 2026 ne-ați informat că nu ați autorizat transferul din 28.10.2026. Vă vom comunica "
          "răspunsul până la 18 noiembrie 2026, menționând numărul cazului CT-2026-123456.")
    out = N.check([("p", ro)], allowed())
    assert out["passed"] and out["checked"] == 7, out
    kinds = {(v["kind"], v["role"]) for v in N.extract(ro, year_hint=2026)}
    assert {("amount", "refund"), ("date", "deadline"), ("date", "report"), ("date", "payment")} <= kinds
    bad = N.check([("p", "V-am rambursat suma de 3.500,00 lei până la 28 octombrie 2026.")], allowed())
    assert {m["kind"] for m in bad["mismatches"]} == {"amount", "date"}
    assert N.parse_number("3.200,00") == N.parse_number("3,200.00") == 3200.0
    # "mai" is also "more": without a year it is not a date
    assert N.extract("Nu mai trebuie să faceți nimic, cu 3 mai multe zile.", year_hint=2026) == []


def test_phone_numbers_and_links_must_be_the_banks():
    good = ("Call us on +40 700 000 100 or 0700 000 100. You can also go to www.csalb.ro or anpc.ro, or write to "
            "ajutor@bancademo.example.")
    assert N.check([("p", good)], allowed())["passed"]
    bad = N.check([("p", "Call +40 721 123 456 back, or open https://livrare-bancademo.example/colet to check.")],
                  allowed())
    assert [m["kind"] for m in bad["mismatches"]] == ["phone", "url"]
    assert bad["mismatches"][0]["expected"].startswith("only the bank's helpline")
    # quotes hide the customer's numbers, never their links or phone numbers
    quoted = N.check([("p", "You wrote: „am deschis https://livrare-bancademo.example și am pierdut 3.494,60 lei”.")],
                     allowed())
    assert [m["kind"] for m in quoted["mismatches"]] == ["url"]


# ---------------------------------------------------------------- AML zone: Romanian formats

AML_FACTS = [{"content": {"case_id": "CT-2026-111111", "amount": {"value": 3200.0, "currency": "RON"},
                          "executed_at": "2026-10-28T14:02:11+02:00",
                          "beneficiary": {"iban": "RO61BDEM1777286093723598"}}},
             {"content": {"top": [{"account": "RO61BDEM1777286093723598", "score": 0.93}], "amount_total": 7950.0}}]


def test_aml_rts_draft_numbers():
    p = VN.permise_din(AML_FACTS, "PL-ABC123")
    good = [("rezumat", "Contul RO61 BDEM •••• 3598 a primit 3.200,00 RON pe 28.10.2026 (CT-2026-111111), în total "
                        "7950 RON; pista PL-ABC123.")]
    assert VN.verifica(good, p) == {"passed": True, "checked": 6, "mismatches": []}
    bad = [("fraza 1", "Contul RO61 BDEM •••• 9999 a primit 4.100 lei pe 27 octombrie 2026 (CT-2026-222222).")]
    out = VN.verifica(bad, p)
    assert not out["passed"] and {m["kind"] for m in out["mismatches"]} == {"iban_tail", "amount", "date", "case_id"}
    assert next(m for m in out["mismatches"] if m["kind"] == "amount")["expected"] == "3200.00 RON"
    assert "ai scris „4.100 lei”" in VN.feedback(out["mismatches"])
