"""Seed-ul pe zone și depozitele de date (ClientRepo, AmlRepo)."""

from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

import pytest

from versoml.contracts import AttackRef, BeneficiaryRef, Complaint, DisputeFacts, Money
from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.aml_world import demo_mule
from versoml.data.calendar_ro import parse_ts
from versoml.data.repos import AmlRepo, ClientRepo
from versoml.data.scenarios import SCENARIOS, build_scenario, to_dispute_facts
from versoml.data.schema import AML_TABLES, CLIENT_TABLES
from versoml.data.world import WORLD_NOW


def _tables(path) -> set[str]:
    with sqlite3.connect(path) as c:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_seed_counts(seeded):
    res = seeded["result"]
    assert seeded["client_db"].exists() and seeded["aml_db"].exists()
    assert res["client"]["customers"] >= 400 and res["client"]["transactions"] > 10000
    assert res["aml"]["flows"] > 50000 and res["aml"]["alerts"] > 0
    assert res["aml"]["referrals"] == 0 and res["client"]["refunds"] == 0
    assert res["materialized_cases"] == 40


def test_zone_separation(seeded):
    client, aml = _tables(seeded["client_db"]), _tables(seeded["aml_db"])
    assert set(CLIENT_TABLES) <= client and set(AML_TABLES) <= aml
    assert not client & {"flows", "alerts", "referrals", "synthetic_labels", "patterns", "indicators", "companies"}
    assert not aml & {"customers", "complaints", "cards", "devices", "sessions", "auth_events", "transactions",
                      "prior_disputes", "sim_events", "notifications", "refunds", "payees"}


def test_aml_db_has_no_victim_names_or_cnps(seeded):
    with sqlite3.connect(seeded["client_db"]) as c:
        people = c.execute("SELECT full_name, cnp FROM customers").fetchall()
    names = {p[0] for p in people}
    cnps = {p[1] for p in people}
    with sqlite3.connect(seeded["aml_db"]) as c:
        for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for col in [r[1] for r in c.execute(f"PRAGMA table_info({table})") if r[2] == "TEXT"]:
                values = [r[0] for r in c.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL")]
                for v in values:
                    assert not (set(re.findall(r"\d{13}", v)) & cnps), (table, col)
                if col in ("holder_name", "reference", "beneficiary_name", "label", "name", "title", "detail",
                           "payload_json", "victim_ref"):
                    for v in values:
                        assert not any(n in v for n in names), (table, col, v)


def test_client_repo_customer_and_balance(seeded):
    repo = ClientRepo(seeded["client_db"], clock=lambda: WORLD_NOW)
    c = repo.get_customer("CUST-DEMO-01")
    assert c["alias"] == "Demo Customer 01" and c["synthetic"] is True and ids.is_test_cnp(c["cnp"])
    assert repo.balance("CUST-DEMO-01") == pytest.approx(12450.00)
    assert c["primary_iban"].startswith("RO") and ids.iban_bank_code(c["primary_iban"]) == "BDEM"
    assert repo.get_customer("CUST-NU-EXISTA") is None
    # plata demo nu e scrisă la seed
    assert repo.get_transaction("TX-900015-A") is None


def test_client_repo_phishing_records(seeded):
    repo = ClientRepo(seeded["client_db"], clock=lambda: WORLD_NOW)
    b = build_scenario("phishing_link")
    tx = repo.get_transaction(b.complaint.transaction_refs[0])
    assert tx["amount"] == 1850.0 and tx["direction"] == "debit"
    auths = repo.get_auth_events(tx["tx_id"])
    enroll = [a for a in auths if a["purpose"] == "device_enrollment"]
    assert enroll and enroll[0]["method"] == "sms_otp" and enroll[0]["screen_showed_amount_and_payee"] is False
    assert "new device" in enroll[0]["otp_text"] and "RON" not in enroll[0]["otp_text"]
    s = repo.get_session(tx["session_id"])
    assert int((parse_ts(tx["ts"]) - parse_ts(s["clicked_at"])).total_seconds()) == 125
    devs = repo.get_device_history("CUST-SC-01")
    assert any(d["enrollment_session_id"] == tx["session_id"] for d in devs)
    assert repo.beneficiary_seen_before("CUST-SC-01", tx["counterparty_iban"]) is False
    txs = repo.list_transactions("CUST-SC-01", days=90, as_of=b.complaint.received_at)
    assert txs and txs[0]["ts"] >= txs[-1]["ts"]


def test_client_repo_other_lookups(seeded):
    repo = ClientRepo(seeded["client_db"], clock=lambda: WORLD_NOW)
    fc = build_scenario("frauda_client")
    assert len(repo.get_prior_disputes("CUST-SC-07", 12, as_of=fc.complaint.received_at)) == 4
    pd = build_scenario("plata_dubla")
    dups = repo.find_duplicates(pd.complaint.transaction_refs[0])
    assert [d["tx_id"] for d in dups] == [pd.records["duplicate_of"]]
    ss = build_scenario("sim_swap")
    ev = repo.sim_swap_events("CUST-SC-06", before=ss.records["transaction"]["ts"], hours=48)
    assert len(ev) == 1 and ev[0]["kind"] == "sim_swap"
    with sqlite3.connect(seeded["client_db"]) as c:
        ref, iban = c.execute("SELECT customer_ref, counterparty_iban FROM transactions WHERE counterparty_iban IS NOT NULL "
                              "AND direction='debit' AND kind='utility' LIMIT 1").fetchone()
    assert repo.beneficiary_seen_before(ref, iban) is True
    assert repo.get_merchant("M-SYN-0001")["synthetic"] is True
    assert repo.list_complaints() == []
    assert len(repo.list_complaints(include_historical=True)) > 50


def test_complaint_roundtrip(dbs):
    repo = ClientRepo(dbs[0], clock=lambda: WORLD_NOW)
    b = build_scenario("demo_t1")
    repo.save_complaint(b.complaint)
    repo.save_complaint(b.complaint)                       # upsert
    got = repo.get_complaint(b.complaint.case_id)
    assert Complaint.model_validate(got) == b.complaint
    assert [c["case_id"] for c in repo.list_complaints()] == [b.complaint.case_id]
    assert got["status"] == "NOU"


def test_post_transfer_and_refund_idempotent(dbs, clock):
    repo = ClientRepo(dbs[0], clock=clock)
    start = repo.balance("CUST-DEMO-01")
    b = build_scenario("demo_t1")
    r1 = repo.apply_scenario(b)
    assert r1["created"] and r1["balance_after"] == pytest.approx(start - 3200)
    assert repo.apply_scenario(b)["created"] is False
    assert repo.balance("CUST-DEMO-01") == pytest.approx(start - 3200)
    auths = repo.get_auth_events(r1["tx_id"])
    assert {(a["method"], a["purpose"]) for a in auths} == {("sms_otp", "device_enrollment"), ("none", "payment")}
    assert repo.beneficiary_seen_before("CUST-DEMO-01", r1["to_iban"]) is False
    # plată live fără meta: autentificare implicită cu suma și beneficiarul afișate
    r2 = repo.post_transfer("CUST-DEMO-01", ids.make_iban("XBNK", "1234567890123456"), 100.0,
                            {"idempotency_key": "k-1", "beneficiary_name": "Test Beneficiar"})
    assert r2["created"] and repo.post_transfer("CUST-DEMO-01", r2["to_iban"], 100.0, {"idempotency_key": "k-1"})["created"] is False
    assert repo.get_auth_events(r2["tx_id"])[0]["screen_showed_amount_and_payee"] is True
    with pytest.raises(ValueError):
        repo.post_transfer("CUST-DEMO-01", "RO00XXXX", 10.0, {})
    bal = repo.balance("CUST-DEMO-01")
    f1 = repo.post_refund("CT-2026-900015", "CUST-DEMO-01", 3200.0, "refund:CT-2026-900015")
    f2 = repo.post_refund("CT-2026-900015", "CUST-DEMO-01", 3200.0, "refund:CT-2026-900015")
    assert f1["created"] and not f2["created"] and f2["idempotent_replay"]
    assert repo.balance("CUST-DEMO-01") == pytest.approx(bal + 3200)
    with pytest.raises(ValueError):
        repo.post_refund("CT-ALT", "CUST-DEMO-01", 3200.0, "refund:CT-2026-900015")
    notes = [n["text"] for n in repo.list_notifications("CUST-DEMO-01", 5)]
    assert "We refunded RON 3,200.00 for dispute CT-2026-900015." in notes
    assert any("activated on a new device" in n for n in notes) and any(n.startswith("You sent RON 3,200.00 to ") for n in notes)


def test_aml_profile_has_no_demographics(seeded):
    repo = AmlRepo(seeded["aml_db"], clock=lambda: WORLD_NOW)
    p = repo.account_profile(demo_mule(7)["iban"])
    assert p["kind"] == "internal" and p["age_days"] == 41 and p["holder_name"] is None
    assert p["turnover_30d_in"] > 10000 and p["alerts"] >= 1
    assert not {"birth_date", "sex", "gender", "age", "nationality", "cnp", "full_name"} & set(p)
    assert repo.account_profile("RO00NUEXISTA") is None
    assert repo.list_alerts()


def test_aml_neighborhood_demo_mule(seeded):
    repo = AmlRepo(seeded["aml_db"], clock=lambda: WORLD_NOW)
    dm = demo_mule(7)["iban"]
    g = repo.neighborhood([dm], hops=2, days=30)
    ids_ = {n["id"] for n in g["nodes"]}
    assert dm in ids_ and art.CRYPTO_EXCHANGE_IBAN in ids_
    seed_node = next(n for n in g["nodes"] if n["id"] == dm)
    assert seed_node["is_seed"] and seed_node["features"]["distinct_senders"] == 3
    assert next(n for n in g["nodes"] if n["id"] == art.CRYPTO_EXCHANGE_IBAN)["hub"] is True
    assert all({"id", "source", "target", "amount", "ts"} <= set(e) for e in g["edges"])
    assert len(repo.flows(dm, days=30)) >= 6


def test_aml_ingest_and_referrals(dbs, clock):
    client, aml = ClientRepo(dbs[0], clock=clock), AmlRepo(dbs[1], clock=clock)
    b1, b2 = build_scenario("demo_t1"), build_scenario("demo_t1_victima2")
    r1, r2 = client.apply_scenario(b1), client.apply_scenario(b2)
    aml.ingest_demo_payment(r1["from_iban"], r1["to_iban"], r1["amount"], r1["ts"])
    aml.ingest_demo_payment(r1["from_iban"], r1["to_iban"], r1["amount"], r1["ts"])      # idempotent
    aml.ingest_demo_payment("CUST-DEMO-02", r2["to_iban"], r2["amount"], r2["ts"])      # prin pseudonim
    dm = demo_mule(7)["iban"]
    ins = [f for f in aml.flows(dm, days=30) if f["to_iban"] == dm and f["feed"] == "demo_ingest"]
    assert len(ins) == 2 and {f["from_iban"] for f in ins} == {r1["from_iban"], r2["from_iban"]}
    for b in (b1, b2):
        aml.save_referral(to_dispute_facts(b))
    refs = aml.list_referrals()
    assert [r["case_id"] for r in refs] == ["CT-2026-900015", "CT-2026-900016"]
    assert all(r["flow_id"] and r["flow_id"].startswith("FL-LIVE-") for r in refs)
    assert all(r["victim_ref"].startswith("VCT-") for r in refs)
    g = aml.neighborhood([dm], hops=1, days=30)
    assert next(n for n in g["nodes"] if n["id"] == dm)["features"]["victim_reports"] >= 3
    # sesizare fără flux în core feed: se creează un flux din pseudonimul victimei
    facts = DisputeFacts(case_id="CT-TEST-1", victim_ref="VCT-test", channel="transfer", dispute_type="neautorizata",
                         amount=Money(value=777.0), executed_at=WORLD_NOW - timedelta(days=1),
                         beneficiary=BeneficiaryRef(iban=dm, name="X"), attack=AttackRef(domain=art.SCAM_DOMAIN_DEMO))
    aml.save_referral(facts)
    assert aml.get_referral("CT-TEST-1")["flow_id"].startswith("FL-REF-")
    aml.set_referral_lead("CT-TEST-1", "LEAD-1")
    assert aml.get_referral("CT-TEST-1")["lead_id"] == "LEAD-1"


def test_live_scenarios_not_seeded_but_others_are(seeded):
    repo = ClientRepo(seeded["client_db"], clock=lambda: WORLD_NOW)
    for sid, spec in SCENARIOS.items():
        b = build_scenario(sid)
        tx = repo.get_transaction(b.complaint.transaction_refs[0])
        assert (tx is None) == spec.live, sid
        assert repo.get_customer(spec.customer_ref) is not None
