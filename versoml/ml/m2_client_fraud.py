"""M2: semnal de fraudă a clientului (docs/05 §8; excepția C-70/25).

LightGBM pe fapte obiective din jurnalele băncii (`versoml.data.features.M2_FEATURES`): contestații anterioare,
dispozitiv cunoscut, istoricul beneficiarului, timpul de la plată la contestație, familiaritatea cu
comerciantul, suma față de obiceiul clientului. Fără date demografice.

Ieșirea e un SEMNAL pentru un om, niciodată o decizie: singura excepție de la rambursarea T+1 cere HoldSignal
aprobat de om și notificarea autorității (motorul de reguli). Explicațiile vin din `pred_contrib=True`.

Antrenarea folosește un simulator de dispute cu distribuții suprapuse (victime reale vs. clienți care contestă
propriile plăți), nu date reale.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from versoml.data.features import M2_FEATURES, M2_LABELS_RO, m2_features_from_records
from versoml.ml.common import binary_metrics, models_dir as _models_dir, read_json, update_metrics, version_tag, write_json

MODEL_FILE = "m2_client_fraud.txt"
META_FILE = "m2_client_fraud.json"
LGB_PARAMS = dict(objective="binary", n_estimators=250, learning_rate=0.05, num_leaves=15, min_child_samples=20,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.9, reg_lambda=1.0, deterministic=True,
                  force_row_wise=True, n_jobs=1, verbose=-1)


def _ln(rng: np.random.Generator, median: float, sigma: float, lo: float, hi: float) -> float:
    return float(np.clip(math.exp(rng.normal(math.log(median), sigma)), lo, hi))


def simulate_disputes(n: int = 5000, seed: int = 7, fraud_rate: float = 0.18) -> pd.DataFrame:
    """Dispute sintetice etichetate: 1 = clientul contestă o plată proprie, 0 = victimă reală."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        fraud = rng.random() < fraud_rate
        r: dict[str, Any] = {k: np.nan for k in M2_FEATURES}
        r["customer_tenure_days"] = float(rng.uniform(40, 6000))
        if fraud:
            card = rng.random() < 0.85
            r["channel_card"] = 1.0 if card else 0.0
            r["prior_disputes_12m"] = float(2 + rng.poisson(1.5)) if rng.random() < 0.6 else float(rng.integers(0, 2))
            r["device_known"] = 1.0 if rng.random() < 0.8 else 0.0          # unii pretind telefon furat
            r["device_age_days"] = float(rng.uniform(30, 2500)) if r["device_known"] else float(rng.uniform(0, 5))
            r["ip_usual"] = 1.0 if rng.random() < 0.75 else 0.0
            r["merchant_familiarity"] = float(rng.poisson(2.5)) if rng.random() < 0.6 else 0.0
            r["hours_purchase_to_dispute"] = _ln(rng, 300, 0.8, 24, 2000) if rng.random() < 0.75 else _ln(rng, 20, 0.8, 1, 48)
            r["amount_vs_typical"] = _ln(rng, 6, 0.9, 0.5, 120)
            r["shipping_matches_profile"] = (1.0 if rng.random() < 0.7 else 0.0) if card else np.nan
            r["sca_strong"] = 1.0 if rng.random() < 0.7 else 0.0
            r["night_tx"] = 1.0 if rng.random() < 0.08 else 0.0
            if not card:
                r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.6 else 0.0
        else:
            kind = rng.choice(["new_device", "cnp", "approved", "remote_access"], p=[0.35, 0.3, 0.23, 0.12])
            r["prior_disputes_12m"] = float(rng.poisson(0.3)) if rng.random() < 0.95 else float(rng.integers(2, 5))
            r["hours_purchase_to_dispute"] = _ln(rng, 14, 1.0, 0.05, 400) if rng.random() < 0.88 else _ln(rng, 200, 0.7, 48, 1500)
            r["amount_vs_typical"] = _ln(rng, 10, 1.0, 0.5, 200)
            r["night_tx"] = 1.0 if rng.random() < 0.2 else 0.0
            if kind == "remote_access":   # acces la distanță pe telefonul victimei: dispozitiv și IP obișnuite
                r["channel_card"] = 1.0 if rng.random() < 0.4 else 0.0
                r["device_known"] = 1.0
                r["device_age_days"] = float(rng.uniform(30, 2500))
                r["ip_usual"] = 1.0 if rng.random() < 0.8 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.8 else float(rng.poisson(1.5))
                r["shipping_matches_profile"] = (1.0 if rng.random() < 0.3 else 0.0) if r["channel_card"] else np.nan
                r["sca_strong"] = 1.0 if rng.random() < 0.7 else 0.0
                if not r["channel_card"]:
                    r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.1 else 0.0
                r["label"] = 0
                rows.append(r)
                continue
            if kind == "new_device":
                r["channel_card"] = 0.0
                r["device_known"] = 0.0
                r["device_age_days"] = float(rng.uniform(0, 0.2))
                r["ip_usual"] = 1.0 if rng.random() < 0.05 else 0.0
                r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.03 else 0.0
                r["merchant_familiarity"] = 0.0
                r["sca_strong"] = 0.0
            elif kind == "cnp":
                r["channel_card"] = 1.0
                r["ip_usual"] = 1.0 if rng.random() < 0.15 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.9 else 1.0
                r["shipping_matches_profile"] = 1.0 if rng.random() < 0.1 else 0.0
                r["sca_strong"] = 0.0
            else:  # a aprobat el în aplicație, păcălit de o pagină falsă (Visa Secure)
                r["channel_card"] = 1.0
                r["device_known"] = 1.0
                r["device_age_days"] = float(rng.uniform(30, 2500))
                r["ip_usual"] = 1.0 if rng.random() < 0.5 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.85 else 1.0
                r["shipping_matches_profile"] = 1.0 if rng.random() < 0.15 else 0.0
                r["sca_strong"] = 1.0
        r["label"] = int(fraud)
        rows.append(r)
    return pd.DataFrame(rows, columns=M2_FEATURES + ["label"])


def train_m2(seed: int = 7, *, models_dir: str | Path | None = None) -> dict:
    import lightgbm as lgb
    from sklearn.metrics import brier_score_loss
    from sklearn.model_selection import train_test_split

    out_dir = _models_dir(models_dir)
    df = simulate_disputes(seed=seed)
    tr, te = train_test_split(df, test_size=0.25, random_state=seed, stratify=df["label"])
    model = lgb.LGBMClassifier(**LGB_PARAMS, random_state=seed).fit(tr[M2_FEATURES], tr["label"])
    p = model.predict_proba(te[M2_FEATURES])[:, 1]
    metrics = {"held_out": binary_metrics(te["label"].to_numpy(), p, threshold=0.5),
               "brier": round(float(brier_score_loss(te["label"], p)), 4), "n_train": int(len(tr)), "n_test": int(len(te)),
               "fraud_rate": round(float(df["label"].mean()), 4),
               "note": "a signal for a person; overlapping synthetic distributions, not real data"}
    final = lgb.LGBMClassifier(**LGB_PARAMS, random_state=seed).fit(df[M2_FEATURES], df["label"])
    final.booster_.save_model(str(out_dir / MODEL_FILE))
    version = version_tag("m2-lgbm", seed, M2_FEATURES, metrics["held_out"]["auc"])
    write_json({"version": version, "features": M2_FEATURES, "seed": seed}, out_dir / META_FILE)
    metrics["model_version"] = version
    update_metrics(out_dir, "m2_client_fraud", metrics)
    _CACHE.pop(str(out_dir), None)
    return metrics


_CACHE: dict[str, tuple[Any, dict]] = {}


def _load(models_dir: str | Path | None = None) -> tuple[Any, dict]:
    import lightgbm as lgb

    d = _models_dir(models_dir)
    if str(d) not in _CACHE:
        if not (d / MODEL_FILE).exists():
            train_m2(models_dir=d)
        _CACHE[str(d)] = (lgb.Booster(model_file=str(d / MODEL_FILE)), read_json(d / META_FILE))
    return _CACHE[str(d)]


def client_fraud_signal(features: dict, *, models_dir: str | Path | None = None, top_k: int = 5) -> dict:
    """{score, top_features: [(nume, contribuție)], model_version, labels_ro}. Lipsurile devin NaN.

    Contribuțiile sunt în spațiul log-odds (TreeSHAP); pozitive = împing spre „clientul contestă o plată proprie".
    """
    booster, meta = _load(models_dir)
    row = []
    for k in meta["features"]:
        v = features.get(k)
        row.append(np.nan if v is None else float(v))
    X = pd.DataFrame([row], columns=meta["features"])
    score = float(booster.predict(X)[0])
    contrib = booster.predict(X, pred_contrib=True)[0][:-1]
    order = np.argsort(-np.abs(contrib))[:top_k]
    top = [(meta["features"][i], round(float(contrib[i]), 4)) for i in order]
    return {"score": round(score, 4), "top_features": top, "model_version": meta["version"],
            "labels_ro": {k: M2_LABELS_RO.get(k, k) for k, _ in top}, "signal_only": True}


def features_from_repo(repo: Any, customer_ref: str, tx_id: str, notified_at: Any) -> dict:
    """Trăsăturile M2 citite prin `ClientRepo` (pentru orchestrator)."""
    tx = repo.get_transaction(tx_id)
    if tx is None:
        raise KeyError(tx_id)
    history = repo.list_transactions(customer_ref, days=365, as_of=notified_at)
    sessions = []
    if tx.get("session_id"):
        s = repo.get_session(tx["session_id"])
        sessions = [s] if s else []
    return m2_features_from_records(tx=tx, history=history, devices=repo.get_device_history(customer_ref),
                                    prior_disputes=repo.get_prior_disputes(customer_ref, 12, as_of=notified_at),
                                    auth_events=repo.get_auth_events(tx_id), sessions=sessions,
                                    customer=repo.get_customer(customer_ref), notified_at=notified_at)
