"""freeform_60: reclamații libere fără transaction_refs, pentru matcher; integritatea față de lumea seed-uită."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

import pytest

from versoml.data.freeform import WINDOW_DAYS, _matches, _national, build_freeform
from versoml.data.golden import FREEFORM_60, TYPOLOGY_CASES, read_jsonl, typology_cases
from versoml.data.oracle import expected_outcome
from versoml.data.text import fold, has_cedilla


@pytest.fixture(scope="module")
def ff():
    return read_jsonl(FREEFORM_60)


@pytest.fixture(scope="module")
def debits(world):
    from datetime import timedelta

    from versoml.data.calendar_ro import parse_ts

    out: dict[str, list[dict]] = {}
    lo = world.now - timedelta(days=WINDOW_DAYS)
    for t in world.card_transactions + world.transfers:
        if t["direction"] == "debit" and lo <= parse_ts(t["ts"]) <= world.now:
            out.setdefault(t["customer_ref"], []).append(t)
    return out


def test_schema_and_mix(ff):
    assert len(ff) == 60 and len({l["gid"] for l in ff}) == 60
    for l in ff:
        assert {"gid", "text", "language", "customer_ref", "expected", "scenario", "notes"} <= set(l)
        assert set(l["expected"]) == {"customer_ref", "tx_id", "needs_human"}
        assert l["expected"]["needs_human"] is (l["expected"]["tx_id"] is None)
        assert "transaction_refs" not in l and not has_cedilla(l["text"]) and l["language"] in ("ro", "en")
    assert Counter(l["category"] for l in ff) == {"clear": 36, "ambiguous": 12, "no_match": 4, "unknown_customer": 8}
    assert Counter(l["language"] for l in ff) == {"ro": 30, "en": 30}
    assert sum(1 for l in ff if l["category"] == "clear" and l["customer_ref"] is None) == 10


def test_file_is_reproducible_from_the_world(ff, world):
    assert json.dumps(build_freeform(world, 7), ensure_ascii=False) == json.dumps(ff, ensure_ascii=False)


def test_clear_cases_match_exactly_one_payment(ff, world, debits):
    customers = {c["customer_ref"]: c for c in world.customers}
    for l in (x for x in ff if x["category"] == "clear"):
        ref, tx_id = l["expected"]["customer_ref"], l["expected"]["tx_id"]
        tx = next(t for t in debits[ref] if t["tx_id"] == tx_id)
        assert tx["customer_ref"] == ref and tx["direction"] == "debit"
        ev = l["evidence"]
        from datetime import date

        day = date.fromisoformat(ev["date"]) if ev["date"] else None
        got = _matches(debits[ref], amount=ev["amount"], day=day, payee=ev["payee"])
        assert [t["tx_id"] for t in got] == [tx_id], l["gid"]
        if l["customer_ref"] is None:   # identified by name + phone / e-mail, unique in the world
            c = customers[ref]
            same = [x for x in world.customers if fold(x["full_name"]) == fold(c["full_name"])]
            assert len(same) == 1 and (_national(c["phone"]) in l["text"] or c["email"] in l["text"].lower())
            assert sum(1 for x in world.customers if x["phone"] == c["phone"]) == 1


def test_ambiguous_cases_have_two_candidates(ff, debits):
    from datetime import date

    for l in (x for x in ff if x["category"] == "ambiguous"):
        ref, ev = l["expected"]["customer_ref"], l["evidence"]
        got = _matches(debits[ref], payee=ev["payee"], lo=date.fromisoformat(ev["date_from"]), hi=date.fromisoformat(ev["date_to"]))
        assert sorted(t["tx_id"] for t in got) == sorted(l["candidates"]) and len(got) == 2, l["gid"]
        assert l["expected"]["tx_id"] is None and l["expected"]["needs_human"] is True


def test_unknown_customers_do_not_exist(ff, world):
    refs = {c["customer_ref"] for c in world.customers}
    names = {fold(c["full_name"]) for c in world.customers}
    for l in (x for x in ff if x["category"] == "unknown_customer"):
        assert l["expected"]["customer_ref"] is None
        assert l["customer_ref"] is None or l["customer_ref"] not in refs
        assert not any(n in fold(l["text"]) for n in names if len(n) > 8)


def test_expected_transactions_are_in_the_seeded_database(ff, seeded):
    conn = sqlite3.connect(seeded["client_db"])
    for l in ff:
        if l["expected"]["tx_id"]:
            row = conn.execute("SELECT customer_ref, direction FROM transactions WHERE tx_id = ?",
                               (l["expected"]["tx_id"],)).fetchone()
            assert row == (l["expected"]["customer_ref"], "debit"), l["gid"]
        if l["expected"]["customer_ref"]:
            assert conn.execute("SELECT 1 FROM customers WHERE customer_ref = ?", (l["expected"]["customer_ref"],)).fetchone()
    conn.close()


def test_typology_cases_follow_the_oracle():
    lines = read_jsonl(TYPOLOGY_CASES)
    assert json.dumps(typology_cases(7), ensure_ascii=False) == json.dumps(lines, ensure_ascii=False)
    assert len({l["typology"] for l in lines}) == len(lines) >= 20
    for l in lines:
        e = l["expected"]
        assert {k: e[k] for k in e if k != "injection_suspected"} == expected_outcome(l["rule_context"])
    assert sum(1 for l in lines if l["typology_signals"]) >= 10
