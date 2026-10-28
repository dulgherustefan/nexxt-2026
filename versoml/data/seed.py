"""Seed-ul bazelor pe zone: `python -m versoml.data.seed`.

`seed_all()` șterge și recreează DOUĂ baze separate:
- `settings.client_db` (var/client_zone.db): clienții (lumea + scenariile + variantele din setul de aur),
  conturile, cardurile, dispozitivele, sesiunile, SCA, tranzacțiile, beneficiarii salvați, SIM, disputele
  anterioare, reclamațiile istorice (închise), notificările;
- `settings.aml_db` (var/aml_zone.db): conturile interne și contrapartidele (profil obiectiv, fără date
  demografice și fără numele victimelor), fluxurile (inclusiv cărăușii), alertele de monitorizare, tabelul de
  sesizări (gol), registrul sintetic de firme, indicatorii (domenii, telefoane) și etichetele de adevăr.
Plățile scenariilor live (demo_t1, demo_t1_victima2) NU se scriu: ele se fac în demo prin `post_transfer`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from versoml.data import aml_world, ids
from versoml.data import artifacts as art
from versoml.data.calendar_ro import iso, parse_ts
from versoml.data.repos import connect, epoch, insert, table_columns
from versoml.data.scenarios import SCENARIOS, ScenarioBundle, build_case, build_scenario
from versoml.data.schema import AML_DDL, CLIENT_DDL, CLIENT_TABLES
from versoml.data.text import fmt_ron
from versoml.data.world import World, generate_world, static_catalogs


def _reset(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()


def _cols(conn, table: str) -> list[str]:
    return table_columns(conn, table)


def _with(rows: list[dict], **computed) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        for k, fn in computed.items():
            r[k] = fn(r)
        out.append(r)
    return out


def _bundles(seed: int) -> list[ScenarioBundle]:
    from versoml.data.golden import variant_params

    out = [build_scenario(s, seed) for s in SCENARIOS]
    for p in variant_params(seed):
        b = build_case(p, seed)
        b.title, b.description = p.key, ""
        out.append(b)
    return out


def _case_parts(b: ScenarioBundle) -> dict[str, list[dict]]:
    """Înregistrările zonei client ale unui caz; la cazurile live, fără plata și pașii ei (se fac în demo)."""
    r = b.records
    tx = r["transaction"]
    case_session = tx.get("session_id")
    new_dev = {d["device_id"] for d in r.get("new_devices", [])}
    case_tx_ids = {t["tx_id"] for t in r["transactions"]}
    if b.live:
        devices = [d for d in r["devices"] if d["device_id"] not in new_dev]
        sessions = [s for s in r["sessions"] if s["session_id"] != case_session]
        auths = [a for a in r["auth_events"] if a.get("session_id") != case_session and a.get("tx_id") not in case_tx_ids]
        txs = list(r["history"])
        sims = []
    else:
        devices, sessions, auths = r["devices"], r["sessions"], r["auth_events"]
        txs = list(r["history"]) + list(r["transactions"])
        sims = r.get("sim_events", [])
    return {"customers": [r["customer"]], "accounts": r["accounts"], "cards": r["cards"], "devices": devices,
            "sessions": sessions, "auth_events": auths, "transactions": txs, "payees": r.get("payees", []),
            "sim_events": sims, "prior_disputes": r.get("prior_disputes", [])}


def _notifications(txs: list[dict], customer_ref: str, now_iso: str, prefix: str) -> list[dict]:
    now = parse_ts(now_iso)
    out = []
    for i, t in enumerate(sorted(txs, key=lambda x: x["ts"])[-30:]):
        ts = parse_ts(t["ts"])
        if (now - ts).days <= 10:
            verb = "You paid" if t["direction"] == "debit" else "You received"
            out.append({"notification_id": f"NTF-{prefix}-{i:03d}", "customer_ref": customer_ref, "ts": t["ts"],
                        "kind": "tranzactie", "text": f"{verb} {fmt_ron(t['amount'])}: {t['description']}", "read": True,
                        "synthetic": True})
    return out


def write_client(path: Path, world: World, bundles: list[ScenarioBundle], seed: int) -> dict[str, int]:
    conn = connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(CLIENT_DDL)
    data: dict[str, list[dict]] = {t: [] for t in CLIENT_TABLES}
    data["customers"] += world.customers
    data["accounts"] += world.accounts
    data["cards"] += world.cards
    data["devices"] += world.devices
    data["sessions"] += world.sessions
    data["auth_events"] += world.auth_events
    data["merchants"] += world.merchants
    data["transactions"] += world.card_transactions + world.transfers
    data["payees"] += world.payees
    data["sim_events"] += world.sim_events
    data["prior_disputes"] += world.prior_disputes
    data["notifications"] += world.notifications
    for c in world.complaints:
        data["complaints"].append({"case_id": c["case_id"], "customer_ref": c["customer_ref"], "received_at": c["received_at"],
                                   "received_epoch": epoch(c["received_at"]), "channel_hint": c.get("channel_hint"),
                                   "source": c["source"], "text": c["text"], "attachments_json": c["attachments"],
                                   "transaction_refs_json": c["transaction_refs"], "status": c["status"],
                                   "historical": 1, "outcome": c.get("outcome"), "scenario": c.get("scenario"),
                                   "saved_at": c["received_at"], "synthetic": 1})
    for b in bundles:
        parts = _case_parts(b)
        for k, v in parts.items():
            data[k] += v
        ref = b.records["customer"]["customer_ref"]
        end = iso(min(parse_ts(b.records["transaction"]["ts"]), world.now)) if b.live else b.records["transaction"]["ts"]
        data["notifications"] += _notifications(parts["transactions"], ref, end, ref)
    # coloane calculate și extra
    for a in data["accounts"]:
        a["is_primary"] = a.get("primary", a.get("is_primary", False))
    for d in data["devices"]:
        d["enrolled_epoch"] = epoch(d["enrolled_at"])
    for s in data["sessions"]:
        s["started_epoch"] = epoch(s["started_at"])
    for a in data["auth_events"]:
        a["ts_epoch"] = epoch(a["ts"])
    for s in data["sim_events"]:
        s["ts_epoch"] = epoch(s["ts"])
    for p in data["prior_disputes"]:
        p["opened_epoch"] = epoch(p["opened_at"])
    for n in data["notifications"]:
        n["ts_epoch"] = epoch(n["ts"])
    tx_cols = _cols(conn, "transactions")
    for t in data["transactions"]:
        t["ts_epoch"] = epoch(t["ts"])
        extra = {k: v for k, v in t.items() if k not in tx_cols and not k.startswith("_") and k != "ts_epoch"}
        t["extra_json"] = extra or None
    counts: dict[str, int] = {}
    conn.execute("BEGIN")
    for table in CLIENT_TABLES:
        if table == "meta":
            continue
        recs = _dedupe(table, data[table])
        counts[table] = insert(conn, table, recs, _cols(conn, table))
    meta = {"zone": "client", "seed": str(seed), "world_now": iso(world.now), "generator": "versoml.data.seed",
            "version": "1", "synthetic": "true", "scenarios": json.dumps(list(SCENARIOS)),
            "demo_customers": json.dumps(["CUST-DEMO-01", "CUST-DEMO-02"])}
    insert(conn, "meta", [{"key": k, "value": v} for k, v in meta.items()], ["key", "value"])
    conn.execute("COMMIT")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    return counts


_KEYS = {"customers": "customer_ref", "accounts": "iban", "cards": "card_id", "devices": "device_id",
         "sessions": "session_id", "auth_events": "auth_id", "merchants": "merchant_id", "transactions": "tx_id",
         "sim_events": "event_id", "prior_disputes": "dispute_id", "complaints": "case_id",
         "notifications": "notification_id", "refunds": "refund_id", "flows": "flow_id", "alerts": "alert_id",
         "referrals": "case_id", "companies": "cui", "indicators": "indicator", "synthetic_labels": "iban",
         "patterns": "pattern_id"}


def _dedupe(table: str, recs: list[dict]) -> list[dict]:
    if table == "payees":
        seen: dict[tuple, dict] = {}
        for r in recs:
            seen[(r["customer_ref"], r["iban"])] = r
        return list(seen.values())
    key = _KEYS.get(table)
    if not key:
        return recs
    out: dict[Any, dict] = {}
    for r in recs:
        out[r[key]] = r          # ultimul câștigă (scenariile suprascriu lumea, dacă se suprapun)
    return list(out.values())


def write_aml(path: Path, world: World, bundles: list[ScenarioBundle], seed: int) -> dict[str, int]:
    conn = connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(AML_DDL)
    flows = list(world.flows)
    extra_accounts: list[dict] = []
    labels = list(world.labels)
    for b in bundles:
        aml = b.records["aml"]
        flows += aml["flows"]
        extra_accounts += aml["accounts"]
        labels += aml.get("labels", [])
        for a in b.records["accounts"]:
            extra_accounts.append({"iban": a["iban"], "kind": "internal", "bank_code": ids.OWN_BANK,
                                   "holder_type": "persoana_fizica",
                                   "account_type": "cont_curent_pf" if a["type"] == "curent" else "cont_economii",
                                   "opened_at": a["opened_at"], "status": "activ",
                                   "holder_ref": ids.pseudonym("TIT", b.records["customer"]["customer_ref"]),
                                   "holder_name": None, "cui": None, "synthetic": True})
    accounts = aml_world.build_aml_accounts([], world.aml_accounts + extra_accounts, static_catalogs(seed), flows,
                                            now=world.now)
    alerts = aml_world.compute_alerts(accounts, flows, now=world.now)
    dm = aml_world.demo_mule(seed)["iban"]
    for a in alerts:
        if a["iban"] == dm:
            a["status"] = "nou"
    for f in flows:
        f["ts_epoch"] = epoch(f["ts"])
        f["natural_key"] = f["flow_id"]
    companies = _dedupe("companies", world.companies)
    indicators = [{"indicator": d["domain"], "kind": "domain", "label": d["kind"], "scenario": d.get("scenario"),
                   "first_seen": d.get("registered_at"), "target": d.get("target_brand"), "ip": d.get("ip"), "synthetic": 1}
                  for d in world.domains]
    indicators += [{"indicator": p["phone"], "kind": "phone", "label": p["label"], "scenario": p.get("scenario"),
                    "first_seen": p.get("first_seen"), "target": None, "ip": None, "synthetic": 1} for p in world.phones]
    lab_rows = [{"iban": lab["id"], "label": lab["label"], "segment": lab.get("segment"), "role": lab.get("role"),
                 "hard_negative": lab.get("hard_negative", False), "is_internal": lab.get("is_internal", False),
                 "patterns_json": lab.get("patterns", []), "typologies_json": lab.get("typologies", []), "synthetic": 1}
                for lab in labels]
    patterns = [{"pattern_id": p["pattern_id"], "typology": p["typology"], "family": p["family"], "mules_json": p["mules"],
                 "victims_json": p["victims"], "flow_ids_json": p["flow_ids"], "start": p["start"], "end": p["end"],
                 "amount_in": p["amount_in"], "typologies_json": p.get("typologies", [p["typology"]]), "synthetic": 1}
                for p in world.patterns]
    inel = aml_world.inel_mule(seed)["iban"]
    inel_victims = sorted({f["from_iban"] for f in flows if f["to_iban"] == inel})
    patterns.append({"pattern_id": "PAT-INEL", "typology": "inel_carausi", "family": "VersoML scenario", "mules_json": [inel],
                     "victims_json": inel_victims, "flow_ids_json": [f["flow_id"] for f in flows if inel in (f["from_iban"], f["to_iban"])],
                     "start": None, "end": None, "amount_in": round(sum(f["amount"] for f in flows if f["to_iban"] == inel), 2),
                     "typologies_json": ["fan_in", "rapid_pass_through"], "synthetic": 1})
    counts: dict[str, int] = {}
    conn.execute("BEGIN")
    for table, recs in (("accounts", accounts), ("flows", flows), ("alerts", alerts), ("companies", companies),
                        ("indicators", indicators), ("synthetic_labels", lab_rows), ("patterns", patterns)):
        counts[table] = insert(conn, table, _dedupe(table, recs), _cols(conn, table))
    counts["referrals"] = 0
    meta = {"zone": "aml", "seed": str(seed), "world_now": iso(world.now), "generator": "versoml.data.seed", "version": "1",
            "synthetic": "true", "demo_mule_iban": dm, "inel_mule_iban": inel, "crypto_exchange_iban": art.CRYPTO_EXCHANGE_IBAN,
            "note_labels": "synthetic_labels and patterns are the ground truth, for training and evaluation only"}
    insert(conn, "meta", [{"key": k, "value": v} for k, v in meta.items()], ["key", "value"])
    conn.execute("COMMIT")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    return counts


def seed_all(settings: Any = None, seed: int = 7) -> dict:
    """Generează lumea și scrie DOUĂ baze separate (șterse și recreate). Întoarce numărătorile pe tabele."""
    if settings is None:
        from versoml.config import get_settings
        settings = get_settings()
    t0 = time.time()
    client_path, aml_path = Path(settings.client_db), Path(settings.aml_db)
    world = generate_world(seed)
    bundles = _bundles(seed)
    _reset(client_path)
    _reset(aml_path)
    client_counts = write_client(client_path, world, bundles, seed)
    aml_counts = write_aml(aml_path, world, bundles, seed)
    return {"seed": seed, "client_db": str(client_path), "aml_db": str(aml_path), "client": client_counts,
            "aml": aml_counts, "scenarios": len(SCENARIOS), "materialized_cases": len(bundles),
            "demo_mule_iban": aml_world.demo_mule(seed)["iban"], "seconds": round(time.time() - t0, 2)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Write var/client_zone.db and var/aml_zone.db (synthetic data).")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    print(json.dumps(seed_all(seed=args.seed), ensure_ascii=False, indent=2))
