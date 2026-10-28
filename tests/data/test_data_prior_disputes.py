"""Prior disputes: the archived ones from the seed plus the complaints filed live in the same session."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from versoml.contracts import Complaint
from versoml.data.calendar_ro import parse_ts
from versoml.data.repos import ClientRepo
from versoml.data.world import WORLD_NOW

CUSTOMER = "CUST-DEMO-01"      # no archived disputes in the seed


def _complaint(case_id: str, received_at, tx_ref: str = "TX-900015-A", customer_ref: str = CUSTOMER) -> Complaint:
    return Complaint(case_id=case_id, customer_ref=customer_ref, received_at=received_at, transaction_refs=[tx_ref],
                     text="I did not make this payment.", source="app")


def test_second_dispute_in_a_session_counts_the_first(dbs, clock):
    repo = ClientRepo(dbs[0], clock=clock)
    now = parse_ts(clock())
    assert repo.get_prior_disputes(CUSTOMER, 12) == []
    repo.save_complaint(_complaint("CT-2026-100001", now - timedelta(minutes=30)))
    # the case under analysis is never its own prior dispute
    assert repo.get_prior_disputes(CUSTOMER, 12, exclude_case_id="CT-2026-100001") == []
    assert repo.get_prior_disputes(CUSTOMER, 12) == []
    repo.save_complaint(_complaint("CT-2026-100002", now - timedelta(minutes=5)))
    prior = repo.get_prior_disputes(CUSTOMER, 12, exclude_case_id="CT-2026-100002")
    assert [d["case_id"] for d in prior] == ["CT-2026-100001"]
    first = prior[0]
    assert first["source"] == "live" and first["tx_ref"] == "TX-900015-A"
    assert parse_ts(first["opened_at"]) == now - timedelta(minutes=30)
    # without an explicit case, the customer's latest complaint is the one being analysed
    assert [d["case_id"] for d in repo.get_prior_disputes(CUSTOMER, 12)] == ["CT-2026-100001"]


def test_as_of_counts_only_complaints_received_before_it(dbs, clock):
    repo = ClientRepo(dbs[0], clock=clock)
    now = parse_ts(clock())
    first, second = now - timedelta(hours=2), now - timedelta(minutes=10)
    repo.save_complaint(_complaint("CT-2026-100011", first))
    repo.save_complaint(_complaint("CT-2026-100012", second))
    assert [d["case_id"] for d in repo.get_prior_disputes(CUSTOMER, 12, as_of=second)] == ["CT-2026-100011"]
    assert repo.get_prior_disputes(CUSTOMER, 12, as_of=first) == []


def test_live_complaints_outside_the_window_do_not_count(dbs, clock):
    repo = ClientRepo(dbs[0], clock=clock)
    now = parse_ts(clock())
    repo.save_complaint(_complaint("CT-2026-100021", now - timedelta(days=400)))
    repo.save_complaint(_complaint("CT-2026-100022", now - timedelta(minutes=1)))
    assert repo.get_prior_disputes(CUSTOMER, 12, exclude_case_id="CT-2026-100022") == []
    assert [d["case_id"] for d in repo.get_prior_disputes(CUSTOMER, 24, exclude_case_id="CT-2026-100022")] == [
        "CT-2026-100021"]


def test_archived_and_live_disputes_add_up_without_double_counting(dbs, clock):
    repo = ClientRepo(dbs[0], clock=clock)
    with sqlite3.connect(dbs[0]) as c:
        ref, n = c.execute("SELECT customer_ref, COUNT(*) FROM prior_disputes WHERE customer_ref LIKE 'CUST-0%' "
                           "GROUP BY customer_ref ORDER BY COUNT(*) DESC, customer_ref LIMIT 1").fetchone()
        historical = c.execute("SELECT COUNT(*) FROM complaints WHERE customer_ref=? AND historical=1", (ref,)).fetchone()[0]
    assert historical == n          # each archived dispute also has its closed complaint in the seed
    archived = repo.get_prior_disputes(ref, 12, as_of=WORLD_NOW)
    assert archived and all(d["source"] == "archive" for d in archived)
    repo.save_complaint(_complaint("CT-2026-100031", WORLD_NOW + timedelta(hours=1), customer_ref=ref))
    repo.save_complaint(_complaint("CT-2026-100032", WORLD_NOW + timedelta(hours=2), customer_ref=ref))
    prior = repo.get_prior_disputes(ref, 12, exclude_case_id="CT-2026-100032")
    assert len(prior) == len(archived) + 1
    assert prior[-1]["case_id"] == "CT-2026-100031" and prior[-1]["source"] == "live"
    assert [d["opened_at"] for d in prior] == sorted(d["opened_at"] for d in prior)
