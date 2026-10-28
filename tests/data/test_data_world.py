"""Lumea sintetică: determinism, validitatea identificatorilor, convențiile de test, tipologiile AML."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import timedelta

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.aml_world import demo_mule
from versoml.data.calendar_ro import parse_ts
from versoml.data.text import has_cedilla
from versoml.data.world import generate_world

FIELDS = ["customers", "accounts", "cards", "devices", "sessions", "auth_events", "card_transactions", "transfers",
          "merchants", "companies", "domains", "complaints", "aml_accounts", "flows", "patterns", "alerts", "labels"]


def _digest(w) -> str:
    return hashlib.sha256(json.dumps({k: getattr(w, k) for k in FIELDS}, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def test_deterministic_and_seed_sensitive(world):
    assert _digest(world) == _digest(generate_world(7, cache=False))        # a fresh run, not the in-process copy
    other = generate_world(8, n_customers=40)              # memo keeps two worlds: the seed-7 one stays cached
    assert other.customers[0]["full_name"] != world.customers[0]["full_name"] or other.customers[0]["cnp"] != world.customers[0]["cnp"]


def test_sizes(world):
    assert len(world.customers) == 2000
    assert len(world.card_transactions) > 100000 and len(world.transfers) > 50000
    assert len(world.flows) > 300000
    internal_mules = [l for l in world.labels if l["label"] == "mule" and l["is_internal"]]
    assert len(internal_mules) >= 300
    assert sum(1 for l in world.labels if l["hard_negative"]) >= 600


def test_cached_world_is_an_independent_copy(world):
    a, b = generate_world(7), generate_world(7)
    assert a is not b and a.customers[0] == b.customers[0]
    a.customers[0]["full_name"] = "changed"
    assert generate_world(7).customers[0]["full_name"] != "changed"


def test_patterns_are_spread_over_the_history(world):
    days = [(world.now - parse_ts(p["start"])).days for p in world.patterns if p["typology"] != "demo_ring"]
    assert min(days) <= 10 and max(days) >= 90
    # a fresh mule is opened shortly before its pattern, not before WORLD_NOW
    opened = {a["iban"]: parse_ts(a["opened_at"]) for a in world.aml_accounts if a.get("opened_at")}
    for p in world.patterns:
        for m in p["mules"]:
            if m in opened:
                assert opened[m] <= parse_ts(p["end"])


def test_alerts_match_the_reference_definition():
    from versoml.data.aml_world import compute_alerts

    t0 = world_now = generate_world(7, n_customers=40).now
    ib = "RO00BDEM0000000000000001"
    accounts = [{"iban": ib, "kind": "internal", "opened_at": (t0 - timedelta(days=20)).isoformat()},
                {"iban": art.CRYPTO_EXCHANGE_IBAN, "kind": "exchange"}, {"iban": art.CASH_NODE, "kind": "cash"}]
    flows = [{"ts": (t0 - timedelta(days=3, hours=k)).isoformat(), "from_iban": f"S{k}", "to_iban": ib, "amount": 4000.0,
              "channel": "transfer"} for k in range(6)]
    flows += [{"ts": (t0 - timedelta(days=2)).isoformat(), "from_iban": ib, "to_iban": art.CRYPTO_EXCHANGE_IBAN,
               "amount": 23000.0, "channel": "transfer_instant"}]
    rules = {a["rule_id"] for a in compute_alerts(accounts, flows, now=world_now)}
    assert {"TM-01", "TM-02", "TM-04"} <= rules


def test_typologies_cover_amlworld_samld_paysim(world):
    typ = Counter(p["typology"] for p in world.patterns)
    for t in ["fan_in", "fan_out", "cycle", "gather_scatter", "scatter_gather", "bipartite", "stack", "random",
              "smurfing", "layered_fan_out", "rapid_pass_through", "behavioural_change", "demo_ring"]:
        assert typ[t] >= 1, t
    fams = {p["family"] for p in world.patterns}
    assert {"AMLworld", "SAML-D", "PaySim/SAML-D"} <= fams


def test_customers_are_synthetic_and_valid(world):
    for c in world.customers:
        assert c["synthetic"] is True
        assert ids.is_test_cnp(c["cnp"]), c["cnp"]
        assert c["phone"].startswith(ids.FICTIVE_PHONE_PREFIX)
        assert c["email"].endswith("@mail.example")
        assert not has_cedilla(c["full_name"] + c["address"] + c["city"])


def test_ibans_and_banks(world):
    banks = set(ids.FICTIVE_BANKS)
    for a in world.accounts:
        assert ids.validate_iban_ro(a["iban"]) == [] and ids.iban_bank_code(a["iban"]) == "BDEM"
    for f in world.flows[::50]:
        for node in (f["from_iban"], f["to_iban"]):
            if node != art.CASH_NODE:
                assert ids.validate_iban_ro(node) == [] and ids.iban_bank_code(node) in banks, node


def test_companies_have_invalid_cui(world):
    assert world.companies
    for c in world.companies:
        assert c["cui_checksum_valid"] is False
        assert ids.validate_cui(c["cui"]) == ["wrong check digit"], c


def test_ips_domains_phones(world):
    for s in world.sessions:
        assert ids.is_test_net_ip(s["ip"])
    for d in world.devices:
        assert ids.is_test_net_ip(d["first_ip"])
    for a in world.auth_events:
        assert a["ip"] is None or ids.is_test_net_ip(a["ip"])
    for t in world.card_transactions[::20] + world.transfers[::20]:
        assert t["ip"] is None or ids.is_test_net_ip(t["ip"])
    for d in world.domains:
        assert ids.is_reserved_domain(d["domain"])
    for m in world.merchants:
        assert m["domain"] is None or ids.is_reserved_domain(m["domain"])
    for p in world.phones:
        assert p["phone"].startswith(ids.FICTIVE_PHONE_PREFIX)


def test_no_cedilla_in_texts(world):
    for t in world.card_transactions[::25] + world.transfers[::25]:
        assert not has_cedilla(t["description"])
    for c in world.complaints:
        assert not has_cedilla(c["text"]) and not any(has_cedilla(a["content"]) for a in c["attachments"])


def test_all_records_marked_synthetic(world):
    for k in ["customers", "accounts", "cards", "devices", "sessions", "auth_events", "merchants", "companies",
              "domains", "aml_accounts", "patterns", "alerts", "labels"]:
        assert all(r.get("synthetic") is True for r in getattr(world, k)), k
    assert all(f["synthetic"] is True for f in world.flows[::100])


def test_flows_and_aml_accounts_carry_no_person_names(world):
    names = {c["full_name"] for c in world.customers}
    refs = {f["reference"] for f in world.flows}
    assert not any(n in r for n in names for r in refs)
    persons = [a for a in world.aml_accounts if a["holder_type"] in ("persoana_fizica", "necunoscut")]
    assert all(a["holder_name"] is None for a in persons)
    assert not any(k in a for a in world.aml_accounts for k in ("birth_date", "sex", "age", "nationality", "cnp"))


def test_balances_never_negative(world):
    assert all(a["balance"] >= 0 for a in world.accounts)


def test_demo_mule_ring(world):
    dm = demo_mule(7)["iban"]
    assert ids.iban_bank_code(dm) == "BDEM" and ids.validate_iban_ro(dm) == []
    lab = next(l for l in world.labels if l["id"] == dm)
    assert lab["label"] == "mule"
    now = world.now
    ins = [f for f in world.flows if f["to_iban"] == dm and parse_ts(f["ts"]) >= now - timedelta(days=7)]
    banks = {ids.iban_bank_code(f["from_iban"]) for f in ins}
    assert len({f["from_iban"] for f in ins}) == 3 and banks <= {"XBNK", "YBNK"}
    for f in ins:
        t_in = parse_ts(f["ts"])
        fwd = [o for o in world.flows if o["from_iban"] == dm and o["to_iban"] == art.CRYPTO_EXCHANGE_IBAN
               and t_in <= parse_ts(o["ts"]) <= t_in + timedelta(hours=6)]
        assert sum(o["amount"] for o in fwd) > 0.85 * f["amount"]
    assert any(f["reported_fraud"] for f in ins)
