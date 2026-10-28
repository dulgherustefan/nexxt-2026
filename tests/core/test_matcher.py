"""Free-form intake: the clues in a complaint, the customer, the disputed payment, and when a person has to pick.

An in-memory bank (no database, no network). The golden set freeform_60 runs in tests/integration."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from versoml.zone_client import matcher as M
from versoml.zone_client.fmt import TZ

REF = datetime(2026, 10, 28, 10, 0, tzinfo=TZ)          # a Wednesday


def ts(day: int, hh: int = 12, mm: int = 0, month: int = 10) -> str:
    return datetime(2026, month, day, hh, mm, tzinfo=TZ).isoformat()


def tx(tx_id, amount, day, payee, *, channel="transfer", kind="transfer", iban="RO27YBNK0000000000004471",
       merchant_id=None, hh=12, mm=0, month=10, direction="debit", card_id=None):
    return {"tx_id": tx_id, "customer_ref": "CUST-A", "direction": direction, "kind": kind, "channel": channel,
            "amount": amount, "currency": "RON", "ts": ts(day, hh, mm, month), "counterparty_name": payee,
            "counterparty_iban": iban, "merchant_id": merchant_id, "card_id": card_id, "status": "booked"}


class FakeRepo:
    def __init__(self, txs=None, customers=None, accounts=None, disputed=None):
        self.txs = {t["tx_id"]: t for t in txs or []}
        self.customers = customers or {"CUST-A": {"customer_ref": "CUST-A", "first_name": "Ana", "last_name": "Testescu",
                                                  "full_name": "Ana Testescu", "phone": "+40700111222",
                                                  "email": "ana.testescu@mail.example", "city": "Iași"}}
        self.accounts = accounts or {"RO91BDEM1965526721994674": "CUST-A"}
        self.disputed = disputed or {}

    def get_customer(self, ref):
        return self.customers.get(ref)

    def get_transaction(self, tx_id):
        return self.txs.get(tx_id)

    def list_transactions(self, ref, days=90, as_of=None):
        return [t for t in self.txs.values() if t["customer_ref"] == ref]

    def find_customer_by_iban(self, iban):
        return self.accounts.get(iban)

    def find_customers_by_phone(self, phone):
        return [r for r, c in self.customers.items() if c.get("phone") == phone]

    def find_customers_by_email(self, email):
        return [r for r, c in self.customers.items() if c.get("email") == email]

    def customer_index(self):
        return list(self.customers.values())

    def customer_cards_last4(self, ref):
        return {"CARD-1": "1234"}

    def get_merchants(self, ids):
        return {"M-1": {"merchant_id": "M-1", "name": "Moda Demo Store", "domain": "modademo.example"}}

    def disputed_tx_ids(self, ref, exclude_case_id=None):
        return dict(self.disputed)

    def refunded_tx_ids(self, ref):
        return {}


@pytest.fixture(autouse=True)
def _fresh_index():
    M.reset_cache()
    yield
    M.reset_cache()


PARAMS = {"match_auto_min_points": 50, "match_auto_min_margin": 20, "match_candidate_min_points": 20}


def run(repo, text, **kw):
    return M.match_complaint(repo, text=text, received_at=REF, params=PARAMS, **kw)


# ---------------------------------------------------------------- dates, Romanian and English


@pytest.mark.parametrize("text, expected", [
    ("yesterday", date(2026, 10, 27)), ("ieri", date(2026, 10, 27)), ("alaltăieri", date(2026, 10, 26)),
    ("the day before yesterday", date(2026, 10, 26)), ("today", date(2026, 10, 28)), ("azi", date(2026, 10, 28)),
    ("on Monday", date(2026, 10, 26)), ("luni", date(2026, 10, 26)), ("vineri", date(2026, 10, 23)),
    ("last Friday", date(2026, 10, 23)), ("two days ago", date(2026, 10, 26)), ("acum 3 zile", date(2026, 10, 25)),
    ("pe 10 septembrie", date(2026, 9, 10)), ("on sep 18", date(2026, 9, 18)), ("14/09", date(2026, 9, 14)),
    ("în data de 06.09.2026", date(2026, 9, 6)), ("27 Oct 2026", date(2026, 10, 27)), ("October 27", date(2026, 10, 27)),
    ("2026-10-25", date(2026, 10, 25)), ("on 27.10", date(2026, 10, 27)), ("aseară", date(2026, 10, 27)),
])
def test_dates_ro_and_en(text, expected):
    found = M.parse_clues(text, received_at=REF).dates
    assert expected in [m.day for m in found], (text, found)


def test_luni_after_a_number_means_months_not_monday():
    assert M.parse_clues("am descoperit după 13 luni", received_at=REF).dates == []


def test_dates_never_in_the_future_and_amounts_are_not_dates():
    clues = M.parse_clues("I paid 12.10 lei on 30 December", received_at=REF)
    assert [m.day for m in clues.dates] == [date(2025, 12, 30)]          # last year's 30 December
    assert [(a.value, a.currency) for a in clues.amounts] == [(12.1, "RON")]


def test_amount_formats_and_salience():
    clues = M.parse_clues("I did not make the RON 3,200.00 payment. I only paid the 2,99 lei fee. 3.494,60 RON and "
                          "4836.76 lei and EUR 30", received_at=REF)
    values = {a.value: a.primary for a in clues.amounts}
    assert values[3200.0] is True and values[2.99] is False
    assert {3494.6, 4836.76, 30.0} <= set(values)


def test_times_and_channel():
    clues = M.parse_clues("At 14:02 an instant transfer went out, around 2 pm", received_at=REF)
    assert [t.strftime("%H:%M") for t in clues.times] == ["14:02", "14:00"]
    assert clues.channel == "transfer" and clues.instant


# ---------------------------------------------------------------- which payment


def test_clear_winner_is_matched_with_reasons():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea"), tx("TX-2", 120.5, 27, "Supermarket"),
                     tx("TX-3", 3150.0, 12, "Ion Pop")])
    r = run(repo, "Ieri au plecat 3.200 lei din contul meu către Julia Oprea, nu am făcut eu plata.",
            customer_ref="CUST-A")
    assert r.tx_id == "TX-1" and not r.needs_human and r.method == "matched"
    top = r.candidates[0]
    assert top.score == 1.0 and any("same amount" in x for x in top.reasons)
    assert any("the day the complaint names" in x for x in top.reasons)
    assert any("payee is named" in x for x in top.reasons)


def test_two_similar_payments_need_a_person():
    repo = FakeRepo([tx("TX-1", 250.0, 20, "Cinema Exemplu", channel="card", kind="card_pos"),
                     tx("TX-2", 250.0, 21, "Cinema Exemplu", channel="card", kind="card_pos")])
    r = run(repo, "Cinema Exemplu took RON 250 from my card last week, twice I think not", customer_ref="CUST-A")
    assert r.needs_human and r.tx_id is None and {c.tx_id for c in r.candidates} == {"TX-1", "TX-2"}


def test_no_payment_fits_goes_to_declared_facts():
    repo = FakeRepo([tx("TX-1", 80.0, 27, "Taxi Exemplu")])
    r = run(repo, "Someone took RON 9,999.00 from my account on 2 October.", customer_ref="CUST-A")
    assert r.needs_human and r.tx_id is None and r.candidates == [] and r.customer_ref == "CUST-A"
    declared = M.declared_facts(M.parse_clues("Someone took RON 9,999.00 from my account on 2 October.", received_at=REF))
    assert declared["amount"] == {"value": 9999.0, "currency": "RON"} and declared["date"] == "2026-10-02"


def test_charged_twice_picks_the_second_charge():
    repo = FakeRepo([tx("TX-0", 412.37, 24, "North Demo Supermarket", channel="card", kind="card_pos", hh=12, mm=3),
                     tx("TX-A", 412.37, 24, "North Demo Supermarket", channel="card", kind="card_pos", hh=12, mm=4)])
    r = run(repo, "The same amount, RON 412.37, was taken twice at North Demo Supermarket.", customer_ref="CUST-A")
    assert r.tx_id == "TX-A" and not r.needs_human


def test_outgoing_only_and_open_disputes_are_left_out():
    repo = FakeRepo([tx("TX-IN", 3200.0, 27, "Salary", direction="credit"), tx("TX-1", 3200.0, 27, "Julia Oprea")],
                    disputed={"TX-1": "CT-2026-111111"})
    r = run(repo, "RON 3,200 left my account yesterday", customer_ref="CUST-A")
    assert r.tx_id is None and r.needs_human and "CT-2026-111111" in r.reason


def test_merchant_website_in_the_complaint_scores():
    repo = FakeRepo([tx("TX-1", 199.0, 25, "Moda Demo Store", channel="card", kind="card_ecom", merchant_id="M-1"),
                     tx("TX-2", 199.0, 25, "Other Shop", channel="card", kind="card_ecom")])
    r = run(repo, "An order on https://modademo.example/checkout for RON 199 that I never placed", customer_ref="CUST-A")
    assert r.tx_id == "TX-1" and any("merchant's website" in x for x in r.candidates[0].reasons)


def test_transaction_reference_given_wins():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea")])
    r = run(repo, "Please refund", transaction_refs=["TX-1"])
    assert r.tx_id == "TX-1" and r.method == "given" and r.customer_ref == "CUST-A" and r.confidence == 1.0


def test_a_person_picks_or_says_none():
    repo = FakeRepo([tx("TX-1", 250.0, 20, "Cinema"), tx("TX-2", 250.0, 21, "Cinema")])
    r = run(repo, "RON 250 to Cinema last week", customer_ref="CUST-A")
    assert M.picked(r, "TX-2", "OPERATOR-7").tx_id == "TX-2"
    none = M.picked(r, None, "OPERATOR-7")
    assert none.tx_id is None and none.needs_human and "OPERATOR-7" in none.reason


# ---------------------------------------------------------------- who the customer is


def test_customer_found_by_their_phone_number():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea")])
    r = run(repo, "Yesterday RON 3,200 went out of my account. My phone number is 0700 111 222.")
    assert r.customer_ref == "CUST-A" and "phone number" in r.customer_match_reason and r.tx_id == "TX-1"


def test_the_payee_iban_never_identifies_the_complainant():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea")], accounts={"RO61BDEM1777286093723598": "CUST-A"})
    r = run(repo, "I sent RON 3,200 to RO61 BDEM 1777 2860 9372 3598 yesterday, it was a scam.")
    assert r.customer_ref is None and r.needs_human


def test_signature_name_needs_a_matching_payment():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea")])
    found = run(repo, "Yesterday RON 3,200 left my account.\n\nKind regards,\nAna Testescu")
    assert found.customer_ref == "CUST-A" and found.tx_id == "TX-1"
    assert "confirmed" in found.customer_match_reason or "payment that fits" in found.customer_match_reason
    unknown = run(repo, "Something is wrong with my account.\n\nKind regards,\nAna Testescu")
    assert unknown.customer_ref is None and unknown.needs_human


def test_unknown_customer():
    r = run(FakeRepo(), "My name is Ion Necunoscut, someone took RON 500 from me. Call me at 0799 999 999.")
    assert r.customer_ref is None and r.tx_id is None and r.needs_human


def test_eval_matcher_on_rows_counts_wrong_auto_matches():
    repo = FakeRepo([tx("TX-1", 3200.0, 27, "Julia Oprea"), tx("TX-2", 250.0, 20, "Cinema"),
                     tx("TX-3", 250.0, 21, "Cinema")])
    rows = [{"gid": "A", "text": "Ieri 3.200 lei către Julia Oprea", "customer_ref": "CUST-A",
             "received_at": REF.isoformat(), "expected": {"customer_ref": "CUST-A", "tx_id": "TX-1", "needs_human": False}},
            {"gid": "B", "text": "RON 250 to Cinema last week", "customer_ref": "CUST-A", "received_at": REF.isoformat(),
             "expected": {"customer_ref": "CUST-A", "tx_id": None, "needs_human": True}}]
    out = M.eval_matcher(repo=repo, rows=rows, params=PARAMS)
    assert out["clear"]["accuracy"] == 1.0 and out["needs_human"]["recall"] == 1.0
    assert out["wrong_auto_matches"] == 0 and out["passed"] is True
