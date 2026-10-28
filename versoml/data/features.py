"""Trăsături obiective, calculate la fel la antrenare și la rulare (funcții pure, fără model).

- `node_features`: trăsăturile unui cont în zona AML, din fluxurile ferestrei (implicit 30 de zile).
  Doar fapte verificabile despre cont (fluxuri, vârsta contului, tipul): fără vârstă, gen sau naționalitate
  (AI Act art. 5(1)(d); docs/05 §4 DP-*).
- `m2_features_from_records`: trăsăturile semnalului de fraudă a clientului (M2), din jurnalele băncii.

`AmlRepo.neighborhood()` atașează `node_features` fiecărui nod, ca M5 să vadă exact ce a văzut la antrenare.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from versoml.data.calendar_ro import parse_ts

HUB_DEGREE = 40          # nod-hub (exchange, numerar, comerciant mare): inclus în vecinătate, dar neexpandat
THRESHOLDS = (1000.0, 5000.0, 10000.0, 50000.0)   # praguri rotunde pentru structurare (PARAM [U])

NODE_FEATURES = [
    "in_count", "out_count", "in_amount", "out_amount", "distinct_senders", "distinct_receivers", "degree_total",
    "pass_through_ratio", "median_dwell_hours", "share_fwd_24h", "frac_out_crypto", "frac_out_cash",
    "frac_in_exchange", "frac_in_cash", "victim_reports", "night_share", "burstiness", "max_in_24h",
    "near_threshold_share", "in_amount_cv", "days_active", "account_age_days", "is_internal", "is_business",
]

FEATURE_LABELS_RO = {
    "in_count": "număr de intrări", "out_count": "număr de ieșiri", "in_amount": "total intrări (lei)",
    "out_amount": "total ieșiri (lei)", "distinct_senders": "plătitori distincți", "distinct_receivers": "beneficiari distincți",
    "degree_total": "contrapartide distincte", "pass_through_ratio": "raport ieșiri / intrări",
    "median_dwell_hours": "timp median între intrare și următoarea ieșire (ore)",
    "share_fwd_24h": "ponderea intrărilor urmate de o ieșire în 24 de ore", "frac_out_crypto": "ponderea ieșirilor spre exchange cripto",
    "frac_out_cash": "ponderea ieșirilor în numerar", "frac_in_exchange": "ponderea intrărilor de la exchange",
    "frac_in_cash": "ponderea depunerilor de numerar", "victim_reports": "intrări raportate ca fraudă (dispută sau rechemare)",
    "night_share": "activitate între 00:00 și 05:00", "burstiness": "activitate în rafale", "max_in_24h": "intrări maxime în 24 de ore",
    "near_threshold_share": "intrări chiar sub un prag rotund", "in_amount_cv": "variația sumelor primite",
    "days_active": "zile active / fereastră", "account_age_days": "vechimea contului (zile)", "is_internal": "cont la Banca Demo",
    "is_business": "cont de persoană juridică",
}

_COLS = ["flow_id", "ts", "from_iban", "to_iban", "amount", "channel", "reported_fraud", "case_id"]


def flows_frame(flows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(flows, pd.DataFrame):
        df = flows.copy()
    else:
        df = pd.DataFrame([{k: f.get(k) for k in _COLS} for f in flows], columns=_COLS)
    if not len(df):
        return pd.DataFrame(columns=_COLS)
    if not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    df["amount"] = df["amount"].astype(float)
    df["reported_fraud"] = df["reported_fraud"].fillna(0).astype(int)
    return df


def _nan(x: float | None) -> float:
    return float("nan") if x is None else float(x)


def node_features(flows: list[dict] | pd.DataFrame, accounts: dict[str, dict], *, as_of: datetime,
                  days: int = 30, nodes: Iterable[str] | None = None) -> dict[str, dict[str, float | None]]:
    """Trăsăturile fiecărui nod din fluxurile ferestrei (as_of - days, as_of].

    `accounts`: iban -> dict cu `kind` (internal/external/exchange/cash), `holder_type`, `opened_at`.
    Întoarce valori JSON-serializabile (NaN devine None).
    """
    df = flows_frame(flows)
    as_of_ts = pd.Timestamp(as_of).tz_convert("UTC")
    lo = as_of_ts - pd.Timedelta(days=days)
    w = df[(df["ts"] > lo) & (df["ts"] <= as_of_ts)].copy()
    want = list(dict.fromkeys(nodes)) if nodes is not None else sorted(set(w["from_iban"]) | set(w["to_iban"]))
    out: dict[str, dict[str, float | None]] = {}
    if not want:
        return out
    kind = {k: (v.get("kind") or "external") for k, v in accounts.items()}
    w["to_kind"] = w["to_iban"].map(kind).fillna("external")
    w["from_kind"] = w["from_iban"].map(kind).fillna("external")
    local = w["ts"].dt.tz_convert("Europe/Bucharest")
    w["night"] = (local.dt.hour < 5).astype(int)
    w["date"] = local.dt.date
    near = np.zeros(len(w), dtype=bool)
    for t in THRESHOLDS:
        near |= (w["amount"].to_numpy() >= 0.9 * t) & (w["amount"].to_numpy() < t)
    w["near"] = near.astype(int)

    in_g, out_g = w.groupby("to_iban"), w.groupby("from_iban")
    in_count, out_count = in_g.size(), out_g.size()
    in_amount, out_amount = in_g["amount"].sum(), out_g["amount"].sum()
    senders, receivers = in_g["from_iban"].nunique(), out_g["to_iban"].nunique()
    pairs = pd.concat([w[["from_iban", "to_iban"]].set_axis(["node", "cp"], axis=1),
                       w[["to_iban", "from_iban"]].set_axis(["node", "cp"], axis=1)])
    degree = pairs.groupby("node")["cp"].nunique()
    crypto_out = w[w["to_kind"] == "exchange"].groupby("from_iban")["amount"].sum()
    cash_out = w[w["to_kind"] == "cash"].groupby("from_iban")["amount"].sum()
    exch_in = w[w["from_kind"] == "exchange"].groupby("to_iban")["amount"].sum()
    cash_in = w[w["from_kind"] == "cash"].groupby("to_iban")["amount"].sum()
    reported = w[w["reported_fraud"] == 1].groupby("to_iban").size()
    near_in = w[w["near"] == 1].groupby("to_iban").size()
    in_std, in_mean = in_g["amount"].std(), in_g["amount"].mean()
    ev = pd.concat([w[["from_iban", "ts", "night", "date"]].set_axis(["node", "ts", "night", "date"], axis=1),
                    w[["to_iban", "ts", "night", "date"]].set_axis(["node", "ts", "night", "date"], axis=1)])
    ev_g = ev.groupby("node")
    night = ev_g["night"].mean()
    days_active = ev_g["date"].nunique() / float(days)
    ev = ev.sort_values(["node", "ts"])
    gaps = ev.groupby("node")["ts"].diff().dt.total_seconds() / 3600.0
    ev = ev.assign(gap=gaps)
    gap_g = ev.dropna(subset=["gap"]).groupby("node")["gap"]
    g_mean, g_std, g_n = gap_g.mean(), gap_g.std(), gap_g.size()
    # intrări în 24h (fereastră glisantă)
    inc = w[["to_iban", "ts", "amount"]].sort_values(["to_iban", "ts"])
    if len(inc):
        roll = inc.set_index("ts").groupby("to_iban")["amount"].rolling("24h").count()
        max24 = roll.groupby(level=0).max()
    else:
        max24 = pd.Series(dtype=float)
    # timpul de staționare: de la fiecare intrare la prima ieșire de după ea
    inc2 = w[["to_iban", "ts"]].set_axis(["node", "ts"], axis=1).sort_values("ts")
    outs = w[["from_iban", "ts"]].set_axis(["node", "ts_out"], axis=1).sort_values("ts_out")
    if len(inc2) and len(outs):
        mg = pd.merge_asof(inc2, outs, left_on="ts", right_on="ts_out", by="node", direction="forward")
        dwell = (mg["ts_out"] - mg["ts"]).dt.total_seconds() / 3600.0
        dwell = dwell.fillna((as_of_ts - mg["ts"]).dt.total_seconds() / 3600.0).clip(upper=days * 24.0)
        mg = mg.assign(dwell=dwell, fwd24=(dwell < 24).astype(float))
        dwell_med = mg.groupby("node")["dwell"].median()
        fwd24 = mg.groupby("node")["fwd24"].mean()
    else:
        dwell_med, fwd24 = pd.Series(dtype=float), pd.Series(dtype=float)

    def g(series: pd.Series, node: str, default: float = 0.0) -> float:
        v = series.get(node, default)
        return float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else default

    for node in want:
        acc = accounts.get(node, {})
        ia, oa = g(in_amount, node), g(out_amount, node)
        ic = g(in_count, node)
        opened = parse_ts(acc.get("opened_at")) if acc.get("opened_at") else None
        mean_gap, std_gap = g(g_mean, node, float("nan")), g(g_std, node, float("nan"))
        burst = (std_gap - mean_gap) / (std_gap + mean_gap) if g(g_n, node) >= 2 and (std_gap + mean_gap) > 0 else float("nan")
        feats = {
            "in_count": ic, "out_count": g(out_count, node), "in_amount": ia, "out_amount": oa,
            "distinct_senders": g(senders, node), "distinct_receivers": g(receivers, node),
            "degree_total": g(degree, node),
            "pass_through_ratio": min(oa / ia, 3.0) if ia > 0 else float("nan"),
            "median_dwell_hours": g(dwell_med, node, float("nan")),
            "share_fwd_24h": g(fwd24, node, float("nan")),
            "frac_out_crypto": g(crypto_out, node) / oa if oa > 0 else 0.0,
            "frac_out_cash": g(cash_out, node) / oa if oa > 0 else 0.0,
            "frac_in_exchange": g(exch_in, node) / ia if ia > 0 else 0.0,
            "frac_in_cash": g(cash_in, node) / ia if ia > 0 else 0.0,
            "victim_reports": g(reported, node),
            "night_share": g(night, node),
            "burstiness": burst,
            "max_in_24h": g(max24, node),
            "near_threshold_share": g(near_in, node) / ic if ic > 0 else 0.0,
            "in_amount_cv": (g(in_std, node, float("nan")) / g(in_mean, node, 1.0)) if ic >= 2 else float("nan"),
            "days_active": g(days_active, node),
            "account_age_days": float((as_of - opened).days) if opened else float("nan"),
            "is_internal": 1.0 if acc.get("kind") == "internal" else 0.0,
            "is_business": 1.0 if acc.get("holder_type") == "persoana_juridica" else 0.0,
        }
        out[node] = {k: (None if isinstance(v, float) and math.isnan(v) else round(float(v), 6)) for k, v in feats.items()}
    return out


def is_hub(node_kind: str | None, feats: dict | None, hub_degree: int = HUB_DEGREE) -> bool:
    if node_kind in ("exchange", "cash"):
        return True
    return bool(feats) and (feats.get("degree_total") or 0) > hub_degree


# ---------------------------------------------------------------- M2: fraudă a clientului

M2_FEATURES = [
    "prior_disputes_12m", "device_known", "device_age_days", "ip_usual", "beneficiary_seen_before",
    "merchant_familiarity", "hours_purchase_to_dispute", "amount_vs_typical", "shipping_matches_profile",
    "sca_strong", "night_tx", "channel_card", "customer_tenure_days",
]
M2_LABELS_RO = {
    "prior_disputes_12m": "contestații în ultimele 12 luni", "device_known": "dispozitiv cunoscut",
    "device_age_days": "vechimea dispozitivului (zile)", "ip_usual": "IP obișnuit al clientului",
    "beneficiary_seen_before": "beneficiar folosit anterior", "merchant_familiarity": "cumpărături anterioare la același comerciant",
    "hours_purchase_to_dispute": "ore de la plată la contestație", "amount_vs_typical": "suma față de mediana clientului",
    "shipping_matches_profile": "livrare la adresa clientului", "sca_strong": "SCA puternic, cu suma și beneficiarul afișate",
    "night_tx": "plată între 00:00 și 06:00", "channel_card": "plată cu cardul", "customer_tenure_days": "vechimea clientului (zile)",
}


def m2_features_from_records(*, tx: dict, history: list[dict], devices: list[dict], prior_disputes: list[dict],
                             auth_events: list[dict], sessions: list[dict], customer: dict | None,
                             notified_at: datetime | str) -> dict[str, float | None]:
    """Trăsăturile M2 dintr-o tranzacție contestată și istoricul clientului (doar fapte din jurnale)."""
    t_ts = parse_ts(tx["ts"])
    notified = parse_ts(notified_at)
    prior = [d for d in prior_disputes
             if notified - timedelta(days=365) <= parse_ts(d["opened_at"]) < notified and d.get("tx_ref") != tx["tx_id"]]
    dev_id = tx.get("device_id") or next((a["device_id"] for a in auth_events if a.get("tx_id") == tx["tx_id"] and a.get("device_id")), None)
    dev = next((d for d in devices if d["device_id"] == dev_id), None)
    session = next((s for s in sessions if s["session_id"] == tx.get("session_id")), None)
    if dev is None:
        device_known, device_age = None, None
    else:
        enrolled = parse_ts(dev["enrolled_at"])
        same_session = session is not None and dev.get("enrollment_session_id") == session["session_id"]
        device_known = 1.0 if (t_ts - enrolled) >= timedelta(hours=24) and not same_session else 0.0
        device_age = max(0.0, (t_ts - enrolled).total_seconds() / 86400.0)
    before = [h for h in history if parse_ts(h["ts"]) < t_ts and h["tx_id"] != tx["tx_id"]]
    ips = {h.get("ip") for h in before if h.get("ip")} | {s.get("ip") for s in sessions
                                                         if s.get("ip") and parse_ts(s["started_at"]) < t_ts - timedelta(hours=1)}
    ip = tx.get("ip") or (session or {}).get("ip")
    ip_usual = None if not ip else (1.0 if ip in ips else 0.0)
    debits = [h["amount"] for h in before if h["direction"] == "debit"]
    typical = float(np.median(debits)) if debits else None
    is_card = tx["channel"] == "card"
    if is_card:
        same = [h for h in before if h.get("merchant_id") and h.get("merchant_id") == tx.get("merchant_id")
                and parse_ts(h["ts"]) >= t_ts - timedelta(days=365)]
        familiarity = float(len(same))
        seen = None
    else:
        same = [h for h in before if h.get("counterparty_iban") and h.get("counterparty_iban") == tx.get("counterparty_iban")]
        familiarity = float(len(same))
        seen = 1.0 if same else 0.0
    pay_auth = [a for a in auth_events if a.get("tx_id") == tx["tx_id"] and a.get("purpose") == "payment"]
    strong = any(a["method"] == "app_push" and a.get("screen_showed_amount_and_payee") for a in pay_auth)
    tenure = None
    if customer and customer.get("customer_since"):
        tenure = float((t_ts.date() - datetime.fromisoformat(customer["customer_since"]).date()).days)
    feats = {
        "prior_disputes_12m": float(len(prior)),
        "device_known": device_known,
        "device_age_days": device_age,
        "ip_usual": ip_usual,
        "beneficiary_seen_before": seen,
        "merchant_familiarity": familiarity,
        "hours_purchase_to_dispute": max(0.0, (notified - t_ts).total_seconds() / 3600.0),
        "amount_vs_typical": (tx["amount"] / typical) if typical else None,
        "shipping_matches_profile": tx.get("shipping_matches_profile"),
        "sca_strong": 1.0 if (strong and device_known == 1.0) else 0.0,
        "night_tx": 1.0 if t_ts.hour < 6 else 0.0,
        "channel_card": 1.0 if is_card else 0.0,
        "customer_tenure_days": tenure,
    }
    return {k: (None if v is None else round(float(v), 4)) for k, v in feats.items()}
