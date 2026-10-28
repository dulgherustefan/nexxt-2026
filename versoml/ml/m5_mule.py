"""M5: conturi-cărăuș în graful AML (docs/05 §8, docs/06 §4.2).

Pași:
1. trăsături obiective pe cont (`versoml.data.features.node_features`, fereastra de 30 de zile);
2. trăsături de graf: agregare medie pe vecini în stil GraphSAGE (vecini de intrare, de ieșire și la 2 pași,
   prin vecinii care nu sunt hub-uri), PageRank pe subgraful-ego cu 2 pași;
3. LightGBM; explicații cu `pred_contrib=True` (contribuții TreeSHAP);
4. stivă: meta LR (sigmoid) peste logit(GBDT, OOF pe grupuri de tipar), PageRank personalizat din conturile cu plăți
   raportate ca fraudă (fapt observabil; etichetele de adevăr nu intră în trăsături), anomalia IsolationForest pe
   trăsăturile proprii (doar ca trăsătură în stivă) și scorul doar-reguli;
5. comunități Louvain (networkx) și tipologii prin reguli explicite.

Etichetele sunt pe fereastră (cărăușul e activ în tipar în acele 30 de zile). Evaluarea cinstită: împărțire
temporală (antrenare pe ferestrele care se termină la 37, 67 și 97 de zile înainte de WORLD_NOW, test pe ultimele
30 de zile, cu 7 zile de decalaj), tipologii ținute deoparte și baseline-uri: doar reguli, GBDT fără graf, GBDT cu
graf, PPR singur, IsolationForest singur, ansamblul.
Scorul e un semnal pentru analistul AML, nu o decizie; nu folosește date demografice.

`graph` = dict-ul întors de `AmlRepo.neighborhood()`: {"nodes": [{id, kind, features, ...}], "edges": [...]}.
Pentru nodurile-semință scorul folosește exact trăsăturile de la antrenare; pentru nodurile de la marginea
vecinătății (pasul 2) agregarea e aproximativă.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse as sp

from versoml.contracts import AccountScore
from versoml.data.calendar_ro import parse_ts
from versoml.data.features import FEATURE_LABELS_RO, HUB_DEGREE, NODE_FEATURES, THRESHOLDS, node_features
from versoml.ml.common import (best_f1_threshold, binary_metrics, load_pickle, models_dir as _models_dir, read_json,
                            save_pickle, update_metrics, version_tag, write_json)

MODEL_FILE = "m5_mule.txt"
META_FILE = "m5_mule.json"
STACK_FILE = "m5_mule_stack.pkl"
PPR_ALPHA = 0.85                 # PageRank personalizat: probabilitatea de a continua pe muchii
LABEL_DELAY_DAYS = 7             # decalajul dintre ultima fereastră de antrenare și fereastra de test
N_TRAIN_SNAPSHOTS = 3            # ferestre de 30 de zile înaintea decalajului (zilele 37-127 înainte de WORLD_NOW)
HARD_SEGMENTS = {"student", "pensioner", "micro_merchant", "sme", "crypto_trader"}
LABEL_HIGH, LABEL_MID = 0.70, 0.30          # PARAM [U]: pragurile etichetelor carausi_probabil / de_verificat

AGG_FEATURES = ["in_count", "out_count", "in_amount", "out_amount", "distinct_senders", "distinct_receivers",
                "degree_total", "pass_through_ratio", "median_dwell_hours", "share_fwd_24h", "frac_out_crypto",
                "frac_out_cash", "victim_reports", "account_age_days", "is_internal", "night_share"]
_LOG = {"in_count", "out_count", "in_amount", "out_amount", "distinct_senders", "distinct_receivers",
        "degree_total", "median_dwell_hours", "account_age_days", "victim_reports"}
_FILL = {"pass_through_ratio": 0.0, "median_dwell_hours": 720.0, "share_fwd_24h": 0.0, "account_age_days": 3650.0}

LGB_PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, deterministic=True,
                  force_row_wise=True, n_jobs=1, verbose=-1)


# ---------------------------------------------------------------- graful


def _ends(e: dict) -> tuple[str | None, str | None]:
    """Capetele unei muchii: fluxurile au from_iban/to_iban; muchiile din vecinătate au source/target."""
    if "from_iban" in e or "to_iban" in e:
        return e.get("from_iban"), e.get("to_iban")
    return e.get("source"), e.get("target")


def build_graph(edges: list[dict]) -> nx.DiGraph:
    """Graf orientat cu muchii agregate: amount = suma fluxurilor, count = numărul lor."""
    g = nx.DiGraph()
    agg: dict[tuple[str, str], list[float]] = {}
    for e in edges:
        s, t = _ends(e)
        if s is None or t is None or s == t:
            continue
        a = agg.setdefault((s, t), [0.0, 0])
        a[0] += float(e.get("amount") or 0.0)
        a[1] += 1
    for (s, t), (amount, count) in agg.items():
        g.add_edge(s, t, amount=amount, count=count)
    return g


def _transform(feats: dict[str, float | None]) -> list[float]:
    row = []
    for k in AGG_FEATURES:
        v = feats.get(k) if feats else None
        if v is None or (isinstance(v, float) and math.isnan(v)):
            v = _FILL.get(k, 0.0)
        v = float(v)
        row.append(math.log1p(max(v, 0.0)) if k in _LOG else v)
    return row


def _hub_mask(nodes: list[str], feats: dict, kinds: dict, hub_degree: int) -> np.ndarray:
    return np.array([kinds.get(n) in ("exchange", "cash") or ((feats.get(n) or {}).get("degree_total") or 0) > hub_degree
                     for n in nodes], dtype=bool)


def _pagerank(nodes: list[str], edges: list[tuple[str, str, float]], alpha: float = 0.85, iters: int = 60) -> dict[str, float]:
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}
    rows = [idx[s] for s, t, _ in edges]
    cols = [idx[t] for s, t, _ in edges]
    w = np.array([max(a, 1e-9) for _, _, a in edges], dtype=float)
    m = sp.csr_matrix((w, (rows, cols)), shape=(n, n))
    out_w = np.asarray(m.sum(axis=1)).ravel()
    dangling = out_w == 0
    inv = np.where(dangling, 0.0, 1.0 / np.where(dangling, 1.0, out_w))
    p = sp.diags(inv) @ m
    pt = p.T.tocsr()
    x = np.full(n, 1.0 / n)
    for _ in range(iters):
        x_new = alpha * (pt @ x + x[dangling].sum() / n) + (1 - alpha) / n
        if np.abs(x_new - x).sum() < 1e-9:
            x = x_new
            break
        x = x_new
    return {nodes[i]: float(x[i]) for i in range(n)}


def graph_features(g: nx.DiGraph, feats: dict[str, dict], kinds: dict[str, str], *, nodes: list[str],
                   hub_degree: int = HUB_DEGREE) -> pd.DataFrame:
    """Agregări pe vecini (1 și 2 pași) și PageRank pe subgraful-ego, pentru `nodes`."""
    all_nodes = list(g.nodes)
    for n in nodes:
        if n not in g:
            g.add_node(n)
            all_nodes.append(n)
    idx = {n: i for i, n in enumerate(all_nodes)}
    n = len(all_nodes)
    X = np.array([_transform(feats.get(v) or {}) for v in all_nodes], dtype=float) if n else np.zeros((0, len(AGG_FEATURES)))
    hub = _hub_mask(all_nodes, feats, kinds, hub_degree)
    src = [idx[s] for s, t in g.edges]
    dst = [idx[t] for s, t in g.edges]
    ones = np.ones(len(src))
    A_out = sp.csr_matrix((ones, (src, dst)), shape=(n, n))            # i -> j
    A_in = A_out.T.tocsr()                                              # i <- j
    A_all = ((A_out + A_in) > 0).astype(float).tocsr()

    def mean_agg(A: sp.csr_matrix, M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        deg = np.asarray(A.sum(axis=1)).ravel()
        s = A @ M
        with np.errstate(invalid="ignore", divide="ignore"):
            res = s / deg[:, None]
        res[deg == 0] = np.nan
        return res, deg

    h_in, deg_in = mean_agg(A_in, X)
    h_out, deg_out = mean_agg(A_out, X)
    h_all, deg_all = mean_agg(A_all, X)
    A_nh = A_all @ sp.diags((~hub).astype(float))                       # doar vecinii care nu sunt hub-uri
    h_all_f = np.nan_to_num(h_all, nan=0.0)
    s2 = A_nh @ h_all_f
    cnt2 = np.asarray(A_nh.sum(axis=1)).ravel()
    with np.errstate(invalid="ignore", divide="ignore"):
        h2 = s2 / cnt2[:, None]
    h2[cnt2 == 0] = np.nan
    n_hub = np.asarray((A_all @ sp.diags(hub.astype(float))).sum(axis=1)).ravel()
    ext = np.array([kinds.get(v) == "external" for v in all_nodes], dtype=float)
    frac_in_ext = np.asarray(A_in @ ext).ravel()
    with np.errstate(invalid="ignore", divide="ignore"):
        frac_in_ext = np.where(deg_in > 0, frac_in_ext / np.maximum(deg_in, 1), np.nan)
    amount_to_hub = defaultdict(float)
    amount_out = defaultdict(float)
    amount_in = defaultdict(float)
    # propagarea riscului, fără etichete: ce parte din bani vine de la / merge spre conturi care ating
    # indicatorii clasici (rules_score >= 1/3)
    risky = {u: rules_score(feats.get(u) or {}) >= 1 / 3 and not hub[idx[u]] for u in all_nodes}
    risk_in = defaultdict(float)
    risk_out = defaultdict(float)
    for s, t, d in g.edges(data=True):
        amount_out[s] += d["amount"]
        amount_in[t] += d["amount"]
        if hub[idx[t]]:
            amount_to_hub[s] += d["amount"]
        if risky.get(s):
            risk_in[t] += d["amount"]
        if risky.get(t):
            risk_out[s] += d["amount"]

    def max_over(neigh: set[str], key: str, default: float = 0.0) -> float:
        vals = [(feats.get(u) or {}).get(key) for u in neigh if not hub[idx[u]]]
        vals = [float(x) for x in vals if x is not None]
        return max(vals) if vals else default

    rows = []
    for v in nodes:
        i = idx[v]
        row: dict[str, float] = {}
        for j, f in enumerate(AGG_FEATURES):
            row[f"in1_{f}"] = h_in[i, j]
            row[f"out1_{f}"] = h_out[i, j]
            row[f"n2_{f}"] = h2[i, j]
        preds, succs = set(g.predecessors(v)), set(g.successors(v))
        for key in ("distinct_senders", "victim_reports", "frac_out_crypto", "share_fwd_24h", "pass_through_ratio"):
            row[f"in1max_{key}"] = max_over(preds, key)
            row[f"out1max_{key}"] = max_over(succs, key)
        row["in1min_account_age_days"] = -max(-float((feats.get(u) or {}).get("account_age_days") or 3650.0)
                                              for u in preds) if preds else np.nan
        row["in_risk_share"] = risk_in[v] / amount_in[v] if amount_in[v] > 0 else 0.0
        row["out_risk_share"] = risk_out[v] / amount_out[v] if amount_out[v] > 0 else 0.0
        row["deg_in_graph"] = float(deg_in[i])
        row["deg_out_graph"] = float(deg_out[i])
        row["n_hub_neighbors"] = float(n_hub[i])
        row["frac_in_external"] = float(frac_in_ext[i]) if not np.isnan(frac_in_ext[i]) else np.nan
        row["frac_out_to_hubs"] = amount_to_hub[v] / amount_out[v] if amount_out[v] > 0 else 0.0
        # subgraful-ego: v și vecinii non-hub sunt „expandați"; muchiile lor intră în ego
        expanded = [v] + [u for u in set(g.predecessors(v)) | set(g.successors(v)) if not hub[idx[u]]]
        ego_edges: dict[tuple[str, str], float] = {}
        for x in expanded:
            for t in g.successors(x):
                ego_edges[(x, t)] = g[x][t]["amount"]
            for s in g.predecessors(x):
                ego_edges[(s, x)] = g[s][x]["amount"]
        ego_nodes = sorted({a for a, _ in ego_edges} | {b for _, b in ego_edges} | {v})
        pr = _pagerank(ego_nodes, [(a, b, w) for (a, b), w in sorted(ego_edges.items())])
        row["pr_ego"] = pr.get(v, 0.0) * len(ego_nodes)
        row["ego_size"] = math.log1p(len(ego_nodes))
        rows.append(row)
    return pd.DataFrame(rows, index=nodes)


def own_frame(feats: dict[str, dict], nodes: list[str]) -> pd.DataFrame:
    return pd.DataFrame([{k: (np.nan if (feats.get(v) or {}).get(k) is None else float(feats[v][k]))
                          for k in NODE_FEATURES} for v in nodes], index=nodes)


def rules_score(f: dict[str, float | None]) -> float:
    """Baseline doar cu reguli: fracția de indicatori clasici prezenți (0..1)."""
    def v(k: str, d: float = 0.0) -> float:
        x = f.get(k)
        return d if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
    flags = [
        v("distinct_senders") >= 4 and v("pass_through_ratio") >= 0.8,
        v("median_dwell_hours", 720) <= 24 and v("pass_through_ratio") >= 0.7,
        v("frac_out_crypto") + v("frac_out_cash") >= 0.6,
        v("account_age_days", 3650) <= 90,
        v("victim_reports") >= 1,
        v("near_threshold_share") >= 0.5 and v("in_count") >= 3,
    ]
    return sum(flags) / len(flags)


# ---------------------------------------------------------------- date de antrenare: instantanee pe ferestre


def ppr_from_seeds(g: nx.DiGraph, kinds: dict[str, str], feats: dict[str, dict], *, alpha: float = PPR_ALPHA,
                   iters: int = 40, hub_degree: int = HUB_DEGREE) -> dict[str, float]:
    """PageRank personalizat din conturile cu plăți raportate ca fraudă (fapt observabil, nu eticheta modelului).

    Fiecare semință are masa 1 (nu 1/|S|), deci scorul unui cont e suma contribuțiilor semințelor din apropiere:
    aceeași valoare pe graful întregii ferestre (antrenare) și pe vecinătatea locală (inferență). Banii curg pe
    muchii (ponderi = sume); hub-urile (exchange, numerar, conturi cu foarte mulți parteneri) nu propagă.
    """
    nodes = list(g.nodes)
    if not nodes:
        return {}
    idx = {n: i for i, n in enumerate(nodes)}
    hub = _hub_mask(nodes, feats, kinds, hub_degree)
    seeds = np.array([((feats.get(n) or {}).get("victim_reports") or 0) >= 1 and not hub[idx[n]] for n in nodes], dtype=float)
    if not seeds.any():
        return {n: 0.0 for n in nodes}
    rows, cols, w = [], [], []
    for s, t, d in g.edges(data=True):
        if hub[idx[s]] or hub[idx[t]]:
            continue
        rows.append(idx[s])
        cols.append(idx[t])
        w.append(max(float(d.get("amount") or 0.0), 1e-9))
    m = sp.csr_matrix((w, (rows, cols)), shape=(len(nodes), len(nodes)))
    out_w = np.asarray(m.sum(axis=1)).ravel()
    pt = (sp.diags(np.where(out_w > 0, 1.0 / np.where(out_w > 0, out_w, 1.0), 0.0)) @ m).T.tocsr()
    x = (1 - alpha) * seeds
    for _ in range(iters):
        x = alpha * (pt @ x) + (1 - alpha) * seeds
    return {n: float(x[idx[n]]) for n in nodes}


def window_labels(world: Any, *, as_of: datetime, days: int = 30) -> dict[str, dict]:
    """Cărăușii ACTIVI în fereastra (as_of - days, as_of]: contul apare într-un flux al tiparului din fereastră.

    Eticheta e pe fereastră, nu pe cont: un cont recrutat e normal înainte de tipar și cărăuș în fereastra lui.
    """
    lo = as_of - timedelta(days=days)
    flow_ts = getattr(world, "_flow_index", None)
    if flow_ts is None:
        flow_ts = {f["flow_id"]: (parse_ts(f["ts"]), f["from_iban"], f["to_iban"]) for f in world.flows}
        world._flow_index = flow_ts
    out: dict[str, dict] = {}
    for p in world.patterns:
        mules = set(p["mules"])
        for fid in p["flow_ids"]:
            rec = flow_ts.get(fid)
            if rec is None or not (lo < rec[0] <= as_of):
                continue
            for acc in (rec[1], rec[2]):
                if acc in mules and acc not in out:
                    out[acc] = {"pattern": p["pattern_id"], "typology": p["typology"]}
    return out


def training_frame(world: Any, *, days: int = 30, as_of: datetime | None = None) -> dict:
    """Instantaneul la `as_of`: trăsăturile conturilor interne active în fereastră, PPR, reguli și etichetele de
    adevăr ale ferestrei (doar pentru antrenare și evaluare). Toate fluxurile folosite au ts <= as_of."""
    as_of = as_of or world.now
    accounts = {a["iban"]: a for a in world.aml_accounts}
    kinds = {k: a["kind"] for k, a in accounts.items()}
    lo = as_of - timedelta(days=days)
    win = [f for f in world.flows if lo < parse_ts(f["ts"]) <= as_of]
    feats = node_features(win, accounts, as_of=as_of, days=days)
    g = build_graph(win)
    labels = window_labels(world, as_of=as_of, days=days)
    nodes = sorted(n for n, f in feats.items() if kinds.get(n) == "internal" and (f["in_count"] or 0) + (f["out_count"] or 0) > 0)
    y = np.array([1 if n in labels else 0 for n in nodes])
    groups = np.array([labels[n]["pattern"] if n in labels else f"N:{n}" for n in nodes])
    ppr = ppr_from_seeds(g, kinds, feats)
    seg = {lab["id"]: lab.get("segment") for lab in world.labels}
    return {"nodes": nodes, "y": y, "groups": groups, "X_own": own_frame(feats, nodes),
            "X_graph": graph_features(g, feats, kinds, nodes=nodes), "feats": feats, "kinds": kinds,
            "segments": [seg.get(n) for n in nodes], "typologies": [labels.get(n, {}).get("typology") for n in nodes],
            "ppr": np.array([ppr.get(n, 0.0) for n in nodes]), "rules": np.array([rules_score(feats[n]) for n in nodes]),
            "as_of": as_of, "max_flow_ts": max((parse_ts(f["ts"]) for f in win), default=None)}


def _concat(frames: list[dict]) -> dict:
    out = {k: np.concatenate([f[k] for f in frames]) for k in ("y", "groups", "ppr", "rules")}
    out["X_own"] = pd.concat([f["X_own"] for f in frames], ignore_index=True)
    out["X_graph"] = pd.concat([f["X_graph"] for f in frames], ignore_index=True)
    out["segments"] = [s for f in frames for s in f["segments"]]
    out["typologies"] = [t for f in frames for t in f["typologies"]]
    out["nodes"] = [n for f in frames for n in f["nodes"]]
    return out


def _gbm(seed: int):
    import lightgbm as lgb

    return lgb.LGBMClassifier(**LGB_PARAMS, random_state=seed)


def _cv_scores(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, seed: int, n_splits: int = 5) -> np.ndarray:
    from sklearn.model_selection import StratifiedGroupKFold

    oof = np.zeros(len(y))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for tr, te in cv.split(X, y, groups):
        oof[te] = _gbm(seed).fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return oof


def _iso_matrix(X_own: pd.DataFrame) -> np.ndarray:
    return np.array([_transform({k: (None if pd.isna(v) else v) for k, v in row.items()})
                     for row in X_own[AGG_FEATURES].to_dict("records")]) if len(X_own) else np.zeros((0, len(AGG_FEATURES)))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _meta_x(p_gbm: np.ndarray, ppr: np.ndarray, iso: np.ndarray, rules: np.ndarray) -> np.ndarray:
    return np.column_stack([_logit(p_gbm), np.log1p(100.0 * np.asarray(ppr)), iso, rules])


META_INPUTS = ["logit(GBDT on own + graph features)", "log1p(100 x personalized PageRank from reported accounts)",
               "IsolationForest anomaly on own features", "rules-only score"]


def fit_stack(frame: dict, seed: int) -> dict:
    """GBDT (OOF pe grupuri de tipar) + PPR + IsolationForest + reguli -> meta LR (sigmoid), apoi GBDT final."""
    from sklearn.ensemble import IsolationForest
    from sklearn.linear_model import LogisticRegression

    X = pd.concat([frame["X_own"], frame["X_graph"]], axis=1)
    y = frame["y"]
    oof = _cv_scores(X, y, frame["groups"], seed)
    iso = IsolationForest(n_estimators=100, random_state=seed).fit(_iso_matrix(frame["X_own"]))
    iso_s = -iso.score_samples(_iso_matrix(frame["X_own"]))
    meta = LogisticRegression(C=1.0, max_iter=2000).fit(_meta_x(oof, frame["ppr"], iso_s, frame["rules"]), y)
    gbm = _gbm(seed).fit(X, y)
    return {"gbm": gbm, "iforest": iso, "meta": meta, "features": list(X.columns), "oof": oof, "iso_train": iso_s}


def stack_predict(model: dict, frame: dict) -> dict[str, np.ndarray]:
    X = pd.concat([frame["X_own"], frame["X_graph"]], axis=1)[model["features"]]
    p = model["gbm"].predict_proba(X)[:, 1] if len(X) else np.zeros(0)
    iso = -model["iforest"].score_samples(_iso_matrix(frame["X_own"])) if len(X) else np.zeros(0)
    ens = model["meta"].predict_proba(_meta_x(p, frame["ppr"], iso, frame["rules"]))[:, 1] if len(X) else np.zeros(0)
    return {"gbdt_graph": p, "iforest": iso, "ppr": frame["ppr"], "rules_only": frame["rules"], "ensemble": ens}


def train_m5(world: Any = None, *, seed: int = 7, models_dir: str | Path | None = None, quick: bool = False) -> dict:
    """Antrenează M5 pe instantanee de 30 de zile; evaluare temporală (cu decalaj), pe tipologii ținute deoparte și
    în validare încrucișată pe grupuri; salvează modelul final (antrenat pe toate instantaneele)."""
    from concurrent.futures import ThreadPoolExecutor

    if world is None:
        from versoml.data.world import generate_world
        world = generate_world(seed)
    out_dir = _models_dir(models_dir)
    test_as_of = world.now
    train_as_of = [world.now - timedelta(days=30 + LABEL_DELAY_DAYS + 30 * k) for k in range(N_TRAIN_SNAPSHOTS)]
    with ThreadPoolExecutor(max_workers=N_TRAIN_SNAPSHOTS + 1) as ex:
        frames = list(ex.map(lambda a: training_frame(world, as_of=a), [test_as_of] + train_as_of))
    test, trains = frames[0], frames[1:]
    tr = _concat(trains)
    cutoff = test_as_of - timedelta(days=30)
    # 1. împărțirea temporală: antrenare pe ferestrele vechi, test pe ultimele 30 de zile
    m = fit_stack(tr, seed)
    s = stack_predict(m, test)
    y = test["y"]
    own_cols = list(tr["X_own"].columns)
    gbm_own = _gbm(seed).fit(tr["X_own"], tr["y"])
    s["gbdt_no_graph"] = gbm_own.predict_proba(test["X_own"][own_cols])[:, 1]
    thr = best_f1_threshold(tr["y"], m["meta"].predict_proba(_meta_x(m["oof"], tr["ppr"], m["iso_train"], tr["rules"]))[:, 1])
    thr_gbm = best_f1_threshold(tr["y"], m["oof"])
    temporal = {k: binary_metrics(y, s[k], threshold={"ensemble": thr, "gbdt_graph": thr_gbm}.get(k, 0.5))
                for k in ("rules_only", "gbdt_no_graph", "gbdt_graph", "ensemble")}
    from sklearn.metrics import average_precision_score, roc_auc_score

    for k in ("ppr", "iforest"):
        temporal[f"{k}_alone"] = {"auc": round(float(roc_auc_score(y, s[k])), 4),
                                  "pr_auc": round(float(average_precision_score(y, s[k])), 4)}
    temporal["ensemble"]["threshold_from"] = "best F1 on the training snapshots (out-of-fold)"
    seg = np.array(test["segments"], dtype=object)
    hard = np.isin(seg, list(HARD_SEGMENTS)) & (y == 0)
    fpr_hard = round(float(((s["ensemble"] >= thr) & hard).sum() / max(1, hard.sum())), 4)
    # 2. tipologii ținute deoparte: fără cărăușii unei tipologii la antrenare, testați pe ea în ultima fereastră
    typ_tr = np.array([t or "" for t in tr["typologies"]], dtype=object)
    typ_te = np.array([t or "" for t in test["typologies"]], dtype=object)
    X_tr = pd.concat([tr["X_own"], tr["X_graph"]], axis=1)[m["features"]]
    X_te = pd.concat([test["X_own"], test["X_graph"]], axis=1)[m["features"]]
    iso_te = s["iforest"]

    def holdout(t: str) -> tuple[str, dict]:
        keep = typ_tr != t
        g = _gbm(seed).fit(X_tr[keep], tr["y"][keep])
        mask = (typ_te == t) | (y == 0)
        p = g.predict_proba(X_te[mask])[:, 1]
        ens = m["meta"].predict_proba(_meta_x(p, test["ppr"][mask], iso_te[mask], test["rules"][mask]))[:, 1]
        yy = y[mask]
        pos = int(yy.sum())
        if pos == 0:
            return t, {"positives": 0}
        return t, {"positives": pos, "ensemble_auc": round(float(roc_auc_score(yy, ens)), 4),
                   "ensemble_recall_at_thr": round(float((ens[yy == 1] >= thr).mean()), 4),
                   "rules_only_auc": round(float(roc_auc_score(yy, test["rules"][mask])), 4),
                   "rules_only_recall_at_0.5": round(float((test["rules"][mask][yy == 1] >= 0.5).mean()), 4)}

    typologies = [] if quick else sorted({t for t in typ_te if t})    # quick: fără tipologiile ținute deoparte
    typ_holdout = {}
    if typologies:
        with ThreadPoolExecutor(max_workers=min(8, len(typologies))) as ex:
            typ_holdout = dict(ex.map(holdout, typologies))
    # 3. validare încrucișată pe grupuri de tipar, pe toate instantaneele (comparabil cu metricile vechi)
    allf = _concat(frames)
    X_all = pd.concat([allf["X_own"], allf["X_graph"]], axis=1)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_all = ex.submit(_cv_scores, X_all, allf["y"], allf["groups"], seed, 3 if quick else 5)
        f_own = ex.submit(_cv_scores, allf["X_own"], allf["y"], allf["groups"], seed, 3 if quick else 5)
        oof_all, oof_own = f_all.result(), f_own.result()
    thr_all = best_f1_threshold(allf["y"], oof_all)
    final = fit_stack(allf, seed)
    thr_final = best_f1_threshold(allf["y"], final["meta"].predict_proba(
        _meta_x(final["oof"], allf["ppr"], final["iso_train"], allf["rules"]))[:, 1])
    final["gbm"].booster_.save_model(str(out_dir / MODEL_FILE))
    version = version_tag("m5-stack-graph", seed, final["features"], temporal["ensemble"]["auc"])
    save_pickle({"iforest": final["iforest"], "meta": final["meta"], "version": version}, out_dir / STACK_FILE)
    write_json({"version": version, "features": final["features"], "threshold_best_f1": thr_final,
                "label_high": LABEL_HIGH, "label_mid": LABEL_MID, "hub_degree": HUB_DEGREE, "seed": seed,
                "meta_inputs": META_INPUTS, "meta_coef": [round(float(c), 4) for c in final["meta"].coef_[0]],
                "trained_on": f"generate_world(seed): {len(frames)} snapshots of 30 days ending at WORLD_NOW - "
                              f"{[0] + [30 + LABEL_DELAY_DAYS + 30 * k for k in range(N_TRAIN_SNAPSHOTS)]} days"},
               out_dir / META_FILE)
    metrics = {
        "temporal_split": {**temporal, "train_snapshots_as_of": [a.isoformat() for a in train_as_of],
                           "test_window": [cutoff.isoformat(), test_as_of.isoformat()],
                           "label_delay_days": LABEL_DELAY_DAYS,
                           "max_train_flow_ts": max(f["max_flow_ts"] for f in trains).isoformat(),
                           "n_train": int(len(tr["y"])), "n_test": int(len(y)), "test_mules": int(y.sum()),
                           "false_positive_rate_hard_negatives": fpr_hard},
        "typology_holdout": typ_holdout,
        # aceleași chei ca înainte (validare încrucișată pe grupuri de tipar, toate instantaneele)
        "rules_only": binary_metrics(allf["y"], allf["rules"], threshold=0.5),
        "gbdt_no_graph": binary_metrics(allf["y"], oof_own, threshold=best_f1_threshold(allf["y"], oof_own)),
        "gbdt_graph": binary_metrics(allf["y"], oof_all, threshold=thr_all),
        "gbdt_graph_at_0.5": binary_metrics(allf["y"], oof_all, threshold=0.5),
        "ensemble": temporal["ensemble"],
        "cv": "StratifiedGroupKFold(5), grupuri = tiparul de spălare (cărăușii aceluiași tipar stau în același fold); "
              f"{len(frames)} instantanee de 30 de zile",
        "window_days": 30, "n_accounts": int(len(allf["y"])), "mule_rate": round(float(allf["y"].mean()), 4),
        "false_positive_rate_hard_negatives": fpr_hard, "model_version": version, "meta_inputs": META_INPUTS,
        "meta_coef": [round(float(c), 4) for c in final["meta"].coef_[0]],
        "note": "PPR seeds = accounts with incoming payments reported as fraud in the window (an observable fact); "
                "ground-truth labels never reach the features",
    }
    update_metrics(out_dir, "m5_mule", metrics)
    _CACHE.pop(str(out_dir), None)
    return metrics


# ---------------------------------------------------------------- inferență

_CACHE: dict[str, tuple[Any, dict, dict | None]] = {}


def _load(models_dir: str | Path | None = None) -> tuple[Any, dict, dict | None]:
    import lightgbm as lgb

    d = _models_dir(models_dir)
    key = str(d)
    if key not in _CACHE:
        if not (d / MODEL_FILE).exists():
            train_m5(models_dir=d)
        stack = load_pickle(d / STACK_FILE) if (d / STACK_FILE).exists() else None
        _CACHE[key] = (lgb.Booster(model_file=str(d / MODEL_FILE)), read_json(d / META_FILE), stack)
    return _CACHE[key]


def _graph_inputs(graph: dict) -> tuple[nx.DiGraph, dict, dict, list[dict]]:
    nodes = graph.get("nodes", [])
    feats = {n["id"]: (n.get("features") or {}) for n in nodes}
    kinds = {n["id"]: n.get("kind") or "external" for n in nodes}
    g = build_graph(graph.get("edges", []))
    for n in nodes:
        if n["id"] not in g:
            g.add_node(n["id"])
    return g, feats, kinds, nodes


def score_accounts(graph: dict, *, models_dir: str | Path | None = None, top_k: int = 5,
                   include_external: bool = False) -> list[AccountScore]:
    """Scorul de cont-cărăuș pentru conturile Băncii Demo din graf (modelul e antrenat pe conturi interne).

    Scorul e al ansamblului (meta LR peste GBDT, PageRank personalizat din conturile raportate, anomalia
    IsolationForest și scorul doar-reguli); `top_features` sunt contribuțiile TreeSHAP ale GBDT-ului.
    Cu `include_external=True` se punctează și conturile de la alte bănci, dar banca vede doar fluxurile lor cu
    conturile interne, deci scorul lor e orientativ. Nodurile exchange și numerar nu se punctează."""
    booster, meta, stack = _load(models_dir)
    g, feats, kinds, nodes = _graph_inputs(graph)
    allowed = ("internal", "external") if include_external else ("internal",)
    scored = [n["id"] for n in nodes if kinds[n["id"]] in allowed and feats.get(n["id"])]
    if not scored:
        return []
    X_own = own_frame(feats, scored)
    X = pd.concat([X_own, graph_features(g, feats, kinds, nodes=scored)], axis=1)[meta["features"]]
    prob = booster.predict(X)
    contrib = booster.predict(X, pred_contrib=True)
    if stack is not None:
        ppr = ppr_from_seeds(g, kinds, feats)
        iso = -stack["iforest"].score_samples(_iso_matrix(X_own))
        rules = np.array([rules_score(feats[n]) for n in scored])
        prob = stack["meta"].predict_proba(_meta_x(prob, np.array([ppr.get(n, 0.0) for n in scored]), iso, rules))[:, 1]
    comm = communities(graph)
    names = meta["features"]
    out = []
    for i, node in enumerate(scored):
        c = contrib[i][:-1]
        order = np.argsort(-np.abs(c))[:top_k]
        top = [(names[j], round(float(c[j]), 4)) for j in order]
        s = float(prob[i])
        label = "carausi_probabil" if s >= meta["label_high"] else "de_verificat" if s >= meta["label_mid"] else "normal"
        out.append(AccountScore(account=node, score=round(s, 4), label=label, top_features=top, community=comm.get(node)))
    return sorted(out, key=lambda a: -a.score)


def explain_feature(name: str) -> str:
    """Eticheta în română a unei trăsături (pentru UI și pentru narativul RTS)."""
    for prefix, label in (("in1_", "media vecinilor de intrare: "), ("out1_", "media vecinilor de ieșire: "),
                          ("n2_", "media vecinilor la 2 pași: ")):
        if name.startswith(prefix):
            return label + FEATURE_LABELS_RO.get(name[len(prefix):], name[len(prefix):])
    extra = {"pr_ego": "PageRank în subgraful-ego", "ego_size": "mărimea subgrafului-ego",
             "deg_in_graph": "vecini de intrare în graf", "deg_out_graph": "vecini de ieșire în graf",
             "n_hub_neighbors": "vecini hub (exchange, numerar, comercianți mari)",
             "frac_in_external": "ponderea plătitorilor de la alte bănci", "frac_out_to_hubs": "ponderea ieșirilor spre hub-uri"}
    return extra.get(name) or FEATURE_LABELS_RO.get(name, name)


def communities(graph: dict, *, seed: int = 7, resolution: float = 1.0) -> dict[str, int]:
    """Comunități Louvain pe graful neorientat (ponderi = log(1 + sumă)). Indexate după mărime."""
    g, _, _, nodes = _graph_inputs(graph)
    order = sorted(g.nodes)
    idx = {n: i for i, n in enumerate(order)}
    ug = nx.Graph()
    ug.add_nodes_from(range(len(order)))
    for s, t, d in g.edges(data=True):
        w = math.log1p(d["amount"])
        a, b = idx[s], idx[t]
        if ug.has_edge(a, b):
            ug[a][b]["weight"] += w
        else:
            ug.add_edge(a, b, weight=w)
    if ug.number_of_edges() == 0:
        return {n: i for i, n in enumerate(order)}
    comms = nx.community.louvain_communities(ug, weight="weight", resolution=resolution, seed=seed)
    comms = sorted((sorted(c) for c in comms), key=lambda c: (-len(c), c[0]))
    return {order[i]: k for k, c in enumerate(comms) for i in c}


# ---------------------------------------------------------------- tipologii (reguli explicite)

TYPOLOGY_PARAMS = {  # PARAM [U]: praguri de demo, nu reguli din lege
    "fan_in_min_senders": 3, "fan_in_window_h": 168, "fan_out_min_receivers": 3, "fan_out_window_h": 72,
    "pass_through_share": 0.8, "pass_through_window_h": 24, "cycle_max_len": 6, "scatter_min": 3,
    "crypto_cash_share": 0.7, "crypto_cash_min_amount": 1000.0, "structuring_min": 3, "structuring_window_h": 168,
}


def _fmt(x: float) -> str:
    from versoml.data.text import fmt_number_ro
    return fmt_number_ro(x, 0) + " lei"


def detect_typologies(graph: dict, params: dict | None = None) -> list[dict]:
    """Tipologii detectate cu reguli explicite: fan-in, fan-out, tranzit rapid (< 24h), ciclu,
    scatter-gather, gather-scatter, ieșire spre cripto/numerar, structurare. Fiecare cu explicație în română."""
    p = {**TYPOLOGY_PARAMS, **(params or {})}
    nodes = graph.get("nodes", [])
    kinds = {n["id"]: n.get("kind") or "external" for n in nodes}
    feats = {n["id"]: n.get("features") or {} for n in nodes}
    edges = []
    for e in graph.get("edges", []):
        s, t = _ends(e)
        ts = parse_ts(e.get("ts")) if e.get("ts") else None
        if s and t and ts:
            edges.append({"id": e.get("id") or e.get("flow_id"), "s": s, "t": t, "a": float(e.get("amount") or 0), "ts": ts})
    edges.sort(key=lambda e: (e["ts"], str(e["id"])))
    hub = {n for n in kinds if kinds[n] in ("exchange", "cash") or (feats.get(n, {}).get("degree_total") or 0) > HUB_DEGREE}
    inc, out = defaultdict(list), defaultdict(list)
    for e in edges:
        inc[e["t"]].append(e)
        out[e["s"]].append(e)
    found: list[dict] = []

    def add(typ: str, rule: str, center: str | None, accounts: list[str], es: list[dict], expl: str, **extra: Any) -> None:
        found.append({"typology": typ, "rule_id": rule, "center": center, "accounts": sorted(set(accounts)),
                      "edge_ids": [e["id"] for e in es], "amount": round(sum(e["a"] for e in es), 2),
                      "start": min(e["ts"] for e in es).isoformat() if es else None,
                      "end": max(e["ts"] for e in es).isoformat() if es else None,
                      "explanation": expl, "params": {k: v for k, v in p.items() if k.startswith(typ.split("_")[0])},
                      **extra})

    for v in sorted(set(inc) | set(out)):
        if kinds.get(v) in ("exchange", "cash"):
            continue
        ins, outs = inc.get(v, []), out.get(v, [])
        # fan-in
        best: list[dict] = []
        for i, e in enumerate(ins):
            w = [x for x in ins[i:] if x["ts"] <= e["ts"] + timedelta(hours=p["fan_in_window_h"]) and x["s"] not in hub]
            if len({x["s"] for x in w}) > len({x["s"] for x in best}):
                best = w
        if len({x["s"] for x in best}) >= p["fan_in_min_senders"]:
            add("fan_in", "TYP-01", v, [v] + [x["s"] for x in best], best,
                f"Contul a primit bani de la {len({x['s'] for x in best})} plătitori distincți în cel mult "
                f"{p['fan_in_window_h'] // 24} zile (total {_fmt(sum(x['a'] for x in best))}).",
                senders=len({x["s"] for x in best}))
        # fan-out
        best = []
        for i, e in enumerate(outs):
            w = [x for x in outs[i:] if x["ts"] <= e["ts"] + timedelta(hours=p["fan_out_window_h"]) and x["t"] not in hub]
            if len({x["t"] for x in w}) > len({x["t"] for x in best}):
                best = w
        if len({x["t"] for x in best}) >= p["fan_out_min_receivers"]:
            add("fan_out", "TYP-02", v, [v] + [x["t"] for x in best], best,
                f"Contul a trimis bani către {len({x['t'] for x in best})} beneficiari distincți în "
                f"{p['fan_out_window_h']} de ore (total {_fmt(sum(x['a'] for x in best))}).",
                receivers=len({x["t"] for x in best}))
        # tranzit rapid
        rapid, dwell = [], []
        for e in ins:
            if e["s"] in hub and kinds.get(e["s"]) != "cash":
                continue
            fwd = [o for o in outs if e["ts"] <= o["ts"] <= e["ts"] + timedelta(hours=p["pass_through_window_h"])]
            if fwd and sum(o["a"] for o in fwd) >= p["pass_through_share"] * e["a"]:
                rapid.append(e)
                rapid += fwd
                dwell.append((fwd[0]["ts"] - e["ts"]).total_seconds() / 3600)
        if dwell:
            uniq = list({x["id"]: x for x in rapid}.values())
            med = float(np.median(dwell))
            add("rapid_pass_through", "TYP-03", v, [v] + [x["s"] for x in uniq] + [x["t"] for x in uniq], uniq,
                f"{len(dwell)} intrări au plecat mai departe în proporție de cel puțin "
                f"{p['pass_through_share']:.0%} în sub {p['pass_through_window_h']} de ore (mediana: {med:.1f} ore).",
                median_dwell_hours=round(med, 2), occurrences=len(dwell))
        # ieșire spre cripto / numerar
        tot = sum(o["a"] for o in outs)
        cc = [o for o in outs if kinds.get(o["t"]) in ("exchange", "cash")]
        if tot >= p["crypto_cash_min_amount"] and sum(o["a"] for o in cc) >= p["crypto_cash_share"] * tot:
            share = sum(o["a"] for o in cc) / tot
            add("crypto_cash_out", "TYP-07", v, [v] + [o["t"] for o in cc], cc,
                f"{share:.0%} din ieșiri ({_fmt(sum(o['a'] for o in cc))}) au mers spre exchange cripto sau numerar.",
                share=round(share, 4))
        # structurare (smurfing)
        near = [e for e in ins if any(0.9 * t <= e["a"] < t for t in THRESHOLDS)]
        for i, e in enumerate(near):
            w = [x for x in near[i:] if x["ts"] <= e["ts"] + timedelta(hours=p["structuring_window_h"])]
            if len(w) >= p["structuring_min"]:
                add("structuring", "TYP-08", v, [v] + [x["s"] for x in w], w,
                    f"{len(w)} intrări cu sume chiar sub un prag rotund în {p['structuring_window_h'] // 24} zile.")
                break
        # gather-scatter: multe intrări, apoi multe ieșiri spre conturi non-hub, în 72h
        srcs = {e["s"] for e in ins if e["s"] not in hub}
        dsts = {o["t"] for o in outs if o["t"] not in hub}
        if len(srcs) >= p["scatter_min"] and len(dsts) >= p["scatter_min"] and ins and outs:
            first_out = min(o["ts"] for o in outs if o["t"] in dsts)
            last_in = max(e["ts"] for e in ins if e["s"] in srcs)
            if abs((first_out - last_in).total_seconds()) <= 72 * 3600:
                es = [e for e in ins if e["s"] in srcs] + [o for o in outs if o["t"] in dsts]
                add("gather_scatter", "TYP-06", v, [v] + list(srcs) + list(dsts), es,
                    f"Contul a strâns bani de la {len(srcs)} plătitori și i-a împărțit la {len(dsts)} beneficiari.")
    # scatter-gather: s -> {m_i} -> t
    for s in sorted(out):
        mids = {o["t"] for o in out[s] if o["t"] not in hub}
        if len(mids) < p["scatter_min"]:
            continue
        sinks = defaultdict(set)
        for m in mids:
            for o in out.get(m, []):
                if o["t"] != s:
                    sinks[o["t"]].add(m)
        for t, ms in sorted(sinks.items()):
            if len(ms) >= p["scatter_min"]:
                es = [o for o in out[s] if o["t"] in ms] + [o for m in ms for o in out.get(m, []) if o["t"] == t]
                add("scatter_gather", "TYP-05", s, [s, t] + list(ms), es,
                    f"Banii au plecat din {s[-4:]} prin {len(ms)} conturi intermediare și s-au adunat în {t[-4:]}.")
    # cicluri
    g = nx.DiGraph()
    for e in edges:
        if e["s"] not in hub and e["t"] not in hub:
            g.add_edge(e["s"], e["t"])
    seen: set[tuple[str, ...]] = set()
    try:
        cycles = nx.simple_cycles(g, length_bound=p["cycle_max_len"])
        for k, cyc in enumerate(cycles):
            if k > 500:
                break
            if len(cyc) < 3:
                continue
            key = tuple(sorted(cyc))
            if key in seen:
                continue
            seen.add(key)
            ring = set(cyc)
            es = [e for e in edges if e["s"] in ring and e["t"] in ring]
            add("cycle", "TYP-04", None, list(cyc), es,
                f"Banii s-au întors la contul de pornire printr-un ciclu de {len(cyc)} conturi.", length=len(cyc))
    except nx.NetworkXException:  # pragma: no cover
        pass
    return found
