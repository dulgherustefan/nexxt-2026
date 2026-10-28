"""M2: semnal de fraudă a clientului (docs/05 §8; excepția C-70/25), ca ansamblu stivuit.

Trăsături: fapte obiective din jurnalele băncii (`versoml.data.features.M2_FEATURES`): contestații anterioare,
dispozitiv cunoscut, istoricul beneficiarului, timpul de la plată la contestație, familiaritatea cu
comerciantul, suma față de obiceiul clientului. Fără date demografice.

Membri:
- `lgbm`: LightGBM (explicații TreeSHAP cu `pred_contrib=True`);
- `lr`: regresie logistică pe trăsături standardizate + indicatori de lipsă (explicații = coeficient x valoare);
- `iforest`: scorul de anomalie IsolationForest, folosit ca trăsătură în stivă (nu ca membru cu vot).
Meta: regresie logistică pe log-odds-urile OOF ale membrilor și pe scorul de anomalie (o calibrare de tip
sigmoid, potrivită cu câteva sute de pozitive pe fold). Împărțire temporală: antrenare pe primele 9 luni din
simulator, test pe ultimele 3 (cu derivă: frauda prietenoasă care pretinde telefon furat și accesul la distanță
la telefonul victimei devin mai dese), 5% etichete inversate.

Ieșirea e un SEMNAL pentru un om, niciodată o decizie: singura excepție de la rambursarea T+1 cere HoldSignal
aprobat de om și notificarea autorității (motorul de reguli).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from versoml.data.features import M2_FEATURES, M2_LABELS_RO, m2_features_from_records
from versoml.ml.common import (binary_metrics, load_pickle, models_dir as _models_dir, read_json, save_pickle,
                            update_metrics, version_tag, write_json)

MODEL_FILE = "m2_client_fraud.txt"
META_FILE = "m2_client_fraud.json"
STACK_FILE = "m2_client_fraud_stack.pkl"
LGB_PARAMS = dict(objective="binary", n_estimators=250, learning_rate=0.05, num_leaves=15, min_child_samples=20,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.9, reg_lambda=1.0, deterministic=True,
                  force_row_wise=True, n_jobs=1, verbose=-1)
LABEL_NOISE = 0.05               # fracția de etichete inversate în simulator (contestații clasate greșit)
TRAIN_DAYS = 270                 # împărțirea temporală: primele 9 luni antrenare, ultimele 3 test
LOG_FEATURES = {"device_age_days", "merchant_familiarity", "hours_purchase_to_dispute", "amount_vs_typical",
                "customer_tenure_days", "prior_disputes_12m"}
# cheile pe care le trimite orchestratorul și echivalentul lor în M2_FEATURES
ALIASES = {"beneficiary_new": ("beneficiary_seen_before", lambda v: 1.0 - float(v)),
           "channel": ("channel_card", lambda v: 1.0 if str(getattr(v, "value", v)) == "card" else 0.0)}


def _ln(rng: np.random.Generator, median: float, sigma: float, lo: float, hi: float) -> float:
    return float(np.clip(math.exp(rng.normal(math.log(median), sigma)), lo, hi))


def simulate_disputes(n: int = 8000, seed: int = 7, fraud_rate: float = 0.18, label_noise: float = LABEL_NOISE,
                      days: int = 365) -> pd.DataFrame:
    """Dispute sintetice etichetate: 1 = clientul contestă o plată proprie, 0 = victimă reală.

    Distribuțiile se suprapun (victime cu mai multe contestații, fraudatori fără istoric, telefon „furat”),
    au derivă în timp (`day`) și `label_noise` etichete inversate; `label_clean` păstrează eticheta adevărată.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        day = float(rng.uniform(0, days))
        drift = day / days
        fraud = rng.random() < fraud_rate * (0.85 + 0.3 * drift)
        r: dict[str, Any] = {k: np.nan for k in M2_FEATURES}
        r["customer_tenure_days"] = float(rng.uniform(40, 6000))
        if fraud:
            card = rng.random() < 0.85
            r["channel_card"] = 1.0 if card else 0.0
            r["prior_disputes_12m"] = float(2 + rng.poisson(1.3)) if rng.random() < 0.55 else float(rng.integers(0, 2))
            claims_stolen = rng.random() < 0.15 + 0.2 * drift            # „mi s-a furat telefonul”, din ce în ce mai des
            r["device_known"] = 0.0 if claims_stolen else 1.0
            r["device_age_days"] = float(rng.uniform(0, 5)) if claims_stolen else float(rng.uniform(30, 2500))
            r["ip_usual"] = 1.0 if rng.random() < 0.7 else 0.0
            r["merchant_familiarity"] = float(rng.poisson(2.2)) if rng.random() < 0.55 else 0.0
            r["hours_purchase_to_dispute"] = _ln(rng, 280, 0.9, 12, 2000) if rng.random() < 0.7 else _ln(rng, 20, 0.9, 1, 48)
            r["amount_vs_typical"] = _ln(rng, 5, 1.0, 0.5, 120)
            r["shipping_matches_profile"] = (1.0 if rng.random() < 0.65 else 0.0) if card else np.nan
            r["sca_strong"] = 1.0 if rng.random() < 0.65 else 0.0
            r["night_tx"] = 1.0 if rng.random() < 0.1 else 0.0
            if not card:
                r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.55 else 0.0
        else:
            p_remote = 0.08 + 0.17 * drift                               # acces la distanță: crește în timp
            kind = rng.choice(["new_device", "cnp", "approved", "remote_access"],
                              p=[0.37 - p_remote / 3, 0.32 - p_remote / 3, 0.31 - p_remote / 3, p_remote])
            r["prior_disputes_12m"] = float(rng.poisson(0.3)) if rng.random() < 0.92 else float(rng.integers(2, 5))
            r["hours_purchase_to_dispute"] = _ln(rng, 14, 1.1, 0.05, 600) if rng.random() < 0.85 else _ln(rng, 200, 0.8, 48, 1500)
            r["amount_vs_typical"] = _ln(rng, 9, 1.1, 0.5, 200)
            r["night_tx"] = 1.0 if rng.random() < 0.2 else 0.0
            if kind == "remote_access":   # acces la distanță pe telefonul victimei: dispozitiv și IP obișnuite
                r["channel_card"] = 1.0 if rng.random() < 0.4 else 0.0
                r["device_known"] = 1.0
                r["device_age_days"] = float(rng.uniform(30, 2500))
                r["ip_usual"] = 1.0 if rng.random() < 0.8 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.75 else float(rng.poisson(1.5))
                r["shipping_matches_profile"] = (1.0 if rng.random() < 0.35 else 0.0) if r["channel_card"] else np.nan
                r["sca_strong"] = 1.0 if rng.random() < 0.7 else 0.0
                if not r["channel_card"]:
                    r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.12 else 0.0
            elif kind == "new_device":
                r["channel_card"] = 0.0
                r["device_known"] = 0.0
                r["device_age_days"] = float(rng.uniform(0, 0.2))
                r["ip_usual"] = 1.0 if rng.random() < 0.08 else 0.0
                r["beneficiary_seen_before"] = 1.0 if rng.random() < 0.04 else 0.0
                r["merchant_familiarity"] = 0.0
                r["sca_strong"] = 0.0
            elif kind == "cnp":
                r["channel_card"] = 1.0
                r["ip_usual"] = 1.0 if rng.random() < 0.2 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.85 else 1.0
                r["shipping_matches_profile"] = 1.0 if rng.random() < 0.12 else 0.0
                r["sca_strong"] = 0.0
            else:  # a aprobat el în aplicație, păcălit de o pagină falsă (Visa Secure)
                r["channel_card"] = 1.0
                r["device_known"] = 1.0
                r["device_age_days"] = float(rng.uniform(30, 2500))
                r["ip_usual"] = 1.0 if rng.random() < 0.5 else 0.0
                r["merchant_familiarity"] = 0.0 if rng.random() < 0.8 else 1.0
                r["shipping_matches_profile"] = 1.0 if rng.random() < 0.2 else 0.0
                r["sca_strong"] = 1.0
        r["label_clean"] = int(fraud)
        r["label"] = int(fraud) ^ int(rng.random() < label_noise)
        r["day"] = day
        rows.append(r)
    return pd.DataFrame(rows, columns=M2_FEATURES + ["label", "label_clean", "day"])


# ---------------------------------------------------------------- membrii


def _lr_frame(X: pd.DataFrame, medians: dict[str, float]) -> np.ndarray:
    cols = []
    for k in M2_FEATURES:
        v = X[k].astype(float)
        miss = v.isna().astype(float)
        v = v.fillna(medians[k])
        if k in LOG_FEATURES:
            v = np.log1p(v.clip(lower=0))
        cols += [v.to_numpy(), miss.to_numpy()]
    return np.column_stack(cols)


def _lr_names() -> list[str]:
    return [n for k in M2_FEATURES for n in (k, f"{k}__missing")]


def _fit_members(X: pd.DataFrame, y: np.ndarray, seed: int) -> dict:
    import lightgbm as lgb
    from sklearn.ensemble import IsolationForest
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    medians = {k: float(np.nanmedian(X[k].to_numpy(dtype=float))) if X[k].notna().any() else 0.0 for k in M2_FEATURES}
    Z = _lr_frame(X, medians)
    scaler = StandardScaler().fit(Z)
    lr = LogisticRegression(C=0.5, max_iter=2000).fit(scaler.transform(Z), y)
    gbm = lgb.LGBMClassifier(**LGB_PARAMS, random_state=seed).fit(X[M2_FEATURES], y)
    iso = IsolationForest(n_estimators=100, random_state=seed).fit(scaler.transform(Z))
    return {"lgbm": gbm, "lr": lr, "scaler": scaler, "medians": medians, "iforest": iso}


def _member_scores(m: dict, X: pd.DataFrame) -> dict[str, np.ndarray]:
    Zs = m["scaler"].transform(_lr_frame(X, m["medians"]))
    booster = m["lgbm"].booster_ if hasattr(m["lgbm"], "booster_") else m["lgbm"]
    p_gbm = booster.predict(X[M2_FEATURES])
    return {"lgbm": np.asarray(p_gbm, dtype=float), "lr": m["lr"].predict_proba(Zs)[:, 1],
            "iforest": -m["iforest"].score_samples(Zs)}


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _meta_x(s: dict[str, np.ndarray]) -> np.ndarray:
    return np.column_stack([_logit(s["lgbm"]), _logit(s["lr"]), s["iforest"]])


def fit_stack(X: pd.DataFrame, y: np.ndarray, seed: int = 7, n_splits: int = 5) -> dict:
    """OOF pe StratifiedKFold -> meta LR (sigmoid) pe [logit lgbm, logit lr, anomalie]; membrii refăcuți pe tot."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    oof = {k: np.zeros(len(y)) for k in ("lgbm", "lr", "iforest")}
    for tr, te in StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(X, y):
        s = _member_scores(_fit_members(X.iloc[tr], y[tr], seed), X.iloc[te])
        for k in oof:
            oof[k][te] = s[k]
    meta = LogisticRegression(C=1.0, max_iter=2000).fit(_meta_x(oof), y)
    return {"members": _fit_members(X, y, seed), "meta": meta}


def stack_scores(model: dict, X: pd.DataFrame) -> dict[str, np.ndarray]:
    s = _member_scores(model["members"], X)
    s["ensemble"] = model["meta"].predict_proba(_meta_x(s))[:, 1]
    return s


# ---------------------------------------------------------------- antrenare


def train_m2(seed: int = 7, *, models_dir: str | Path | None = None) -> dict:
    from sklearn.metrics import brier_score_loss
    from sklearn.model_selection import train_test_split

    out_dir = _models_dir(models_dir)
    df = simulate_disputes(seed=seed)
    tr, te = df[df["day"] < TRAIN_DAYS], df[df["day"] >= TRAIN_DAYS]
    m = fit_stack(tr[M2_FEATURES], tr["label"].to_numpy(), seed)
    s = stack_scores(m, te[M2_FEATURES])
    y_te, y_clean = te["label"].to_numpy(), te["label_clean"].to_numpy()
    temporal = {}
    for k in ("lgbm", "lr", "ensemble"):
        temporal[k] = {**binary_metrics(y_te, s[k], threshold=0.5),
                       "auc_clean_labels": binary_metrics(y_clean, s[k])["auc"],
                       "brier": round(float(brier_score_loss(y_te, s[k])), 4)}
    temporal["iforest_alone"] = {"auc": binary_metrics(y_te, s["iforest"])["auc"],
                                 "note": "unsupervised anomaly score; used only as a stacked feature"}
    # vechea împărțire aleatoare, pentru comparație (aceeași perioadă amestecată)
    rtr, rte = train_test_split(df, test_size=0.25, random_state=seed, stratify=df["label"])
    rs = stack_scores(fit_stack(rtr[M2_FEATURES], rtr["label"].to_numpy(), seed), rte[M2_FEATURES])
    final = fit_stack(df[M2_FEATURES], df["label"].to_numpy(), seed)
    final["members"]["lgbm"].booster_.save_model(str(out_dir / MODEL_FILE))
    version = version_tag("m2-stack", seed, M2_FEATURES, temporal["ensemble"]["auc"])
    save_pickle({"lr": final["members"]["lr"], "scaler": final["members"]["scaler"],
                 "medians": final["members"]["medians"], "iforest": final["members"]["iforest"],
                 "meta": final["meta"], "version": version}, out_dir / STACK_FILE)
    write_json({"version": version, "features": M2_FEATURES, "seed": seed, "members": ["lgbm", "lr", "iforest"],
                "meta_coef": [round(float(c), 4) for c in final["meta"].coef_[0]]}, out_dir / META_FILE)
    metrics = {"held_out": temporal["ensemble"], "temporal_split": temporal,
               "split": f"temporal: train on simulated days 0-{TRAIN_DAYS}, test on days {TRAIN_DAYS}-365 (drift: more "
                        "'stolen phone' friendly fraud and more remote-access victims later)",
               "label_noise": LABEL_NOISE,
               "random_split_old_style": {k: binary_metrics(rte["label"].to_numpy(), rs[k])["auc"] for k in ("lgbm", "lr", "ensemble")},
               "brier": temporal["ensemble"]["brier"], "n_train": int(len(tr)), "n_test": int(len(te)),
               "fraud_rate": round(float(df["label"].mean()), 4), "model_version": version,
               "meta": "logistic regression on out-of-fold [logit LightGBM, logit LR, IsolationForest anomaly]",
               "note": "a signal for a person; overlapping synthetic distributions with label noise, not real data"}
    update_metrics(out_dir, "m2_client_fraud", metrics)
    _CACHE.pop(str(out_dir), None)
    return metrics


_CACHE: dict[str, tuple[Any, dict, dict | None]] = {}


def _load(models_dir: str | Path | None = None) -> tuple[Any, dict, dict | None]:
    import lightgbm as lgb

    d = _models_dir(models_dir)
    if str(d) not in _CACHE:
        if not (d / MODEL_FILE).exists():
            train_m2(models_dir=d)
        stack = load_pickle(d / STACK_FILE) if (d / STACK_FILE).exists() else None
        _CACHE[str(d)] = (lgb.Booster(model_file=str(d / MODEL_FILE)), read_json(d / META_FILE), stack)
    return _CACHE[str(d)]


def _row(features: dict, names: list[str]) -> list[float]:
    f = dict(features or {})
    for alias, (name, conv) in ALIASES.items():
        if f.get(name) is None and f.get(alias) is not None:
            try:
                f[name] = conv(f[alias])
            except (TypeError, ValueError):
                pass
    out = []
    for k in names:
        v = f.get(k)
        try:
            out.append(np.nan if v is None else float(v))
        except (TypeError, ValueError):
            out.append(np.nan)
    return out


def client_fraud_signal(features: dict, *, models_dir: str | Path | None = None, top_k: int = 5) -> dict:
    """{score, top_features: [(nume, contribuție)], model_version, labels_ro, members, lr_top_features, signal_only}.

    Lipsurile devin NaN. `score` vine din ansamblu (meta LR peste LightGBM, LR și anomalia IsolationForest);
    `top_features` sunt contribuțiile TreeSHAP ale LightGBM (log-odds; pozitive = împing spre „clientul contestă
    o plată proprie"), `lr_top_features` contribuțiile regresiei logistice (coeficient x valoare standardizată).
    Acceptă și cheile orchestratorului `beneficiary_new` și `channel`.
    """
    booster, meta, stack = _load(models_dir)
    X = pd.DataFrame([_row(features, meta["features"])], columns=meta["features"])
    p_gbm = float(booster.predict(X)[0])
    contrib = booster.predict(X, pred_contrib=True)[0][:-1]
    order = np.argsort(-np.abs(contrib))[:top_k]
    top = [(meta["features"][i], round(float(contrib[i]), 4)) for i in order]
    out = {"top_features": top, "model_version": meta["version"],
           "labels_ro": {k: M2_LABELS_RO.get(k, k) for k, _ in top}, "signal_only": True}
    if stack is None:   # artefacte vechi: doar GBDT
        return {"score": round(p_gbm, 4), **out, "members": {"lgbm": round(p_gbm, 4)}}
    m = {"lgbm": booster, "lr": stack["lr"], "scaler": stack["scaler"], "medians": stack["medians"],
         "iforest": stack["iforest"]}
    s = _member_scores(m, X)
    score = float(stack["meta"].predict_proba(_meta_x(s))[:, 1][0])
    zs = m["scaler"].transform(_lr_frame(X, m["medians"]))[0]
    lc = zs * stack["lr"].coef_[0]
    names = _lr_names()
    lr_top = [(names[i], round(float(lc[i]), 4)) for i in np.argsort(-np.abs(lc))[:top_k]]
    return {"score": round(score, 4), **out, "lr_top_features": lr_top,
            "members": {"lgbm": round(float(s["lgbm"][0]), 4), "lr": round(float(s["lr"][0]), 4),
                        "anomaly": round(float(s["iforest"][0]), 4)}}


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
