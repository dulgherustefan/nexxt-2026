"""M1: clasificatorul de contestații (docs/05 §8, docs/06 §4.2).

TF-IDF pe caractere (2–5, `char_wb`) și pe cuvinte (1–2) + regresie logistică, calibrată izotonic
(`CalibratedClassifierCV`), câte un cap pentru canal, tipul disputei și scenariu. Intrarea se normalizează:
ş/ţ cu sedilă -> ș/ț cu virgulă, litere mici, apoi fără diacritice (ca textele scrise fără diacritice să
arate la fel); cifrele devin „0". Metadatele (canalul indicat, sursa, tipurile de atașamente) intră ca jetoane.

`ambiguous=True` când diferența dintre primele două scenarii e mică sau când canalul prezis nu se potrivește
cu scenariul prezis: atunci decide un om sau LLM-ul ajutător. Clasificarea nu decide nimic; regulile decid.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from versoml.contracts import Channel, Classification, DisputeType, Scenario
from versoml.data.complaints import SCENARIO_LABELS, generate_corpus
from versoml.data.text import normalize_ro, strip_diacritics
from versoml.ml.common import (expected_calibration_error, load_pickle, models_dir as _models_dir, save_pickle,
                            update_metrics, version_tag)

MODEL_FILE = "m1_classifier.pkl"
AMBIGUITY_MARGIN = 0.20          # PARAM [U]: sub această diferență între primele două scenarii, cazul e ambiguu
AMBIGUITY_MIN_PROB = 0.50        # PARAM [U]: sub această probabilitate a scenariului prezis, cazul e ambiguu
HEADS = ("channel", "dispute_type", "scenario")
FIXED = {s: lab for s, lab in SCENARIO_LABELS.items() if s not in ("reclamatie_tardiva", "injectie_document")}


def normalize_text(text: str, meta: dict | None = None) -> str:
    """Textul normalizat + jetoanele de metadate (aceeași funcție la antrenare și la rulare)."""
    meta = meta or {}
    parts = [text or ""]
    for a in meta.get("attachments") or []:
        if isinstance(a, dict) and a.get("content"):
            parts.append(str(a["content"]))
    t = strip_diacritics(normalize_ro("\n".join(parts))).lower()
    t = re.sub(r"https?://", " url ", t)
    t = re.sub(r"\d", "0", t)
    tokens = []
    if meta.get("channel_hint"):
        tokens.append(f"zzch{str(getattr(meta['channel_hint'], 'value', meta['channel_hint']))}")
    if meta.get("source"):
        tokens.append(f"zzsrc{meta['source']}")
    for a in meta.get("attachments") or []:
        kind = a.get("kind") if isinstance(a, dict) else str(a)
        if kind:
            tokens.append(f"zzatt{kind}")
    return t + " " + " ".join(tokens)


def _vectorizer() -> Any:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion

    return FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=60000, sublinear_tf=True)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=20000, sublinear_tf=True,
                                 token_pattern=r"(?u)\b\w+\b")),
    ])


def _head(seed: int) -> Any:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    return CalibratedClassifierCV(LogisticRegression(C=4.0, max_iter=3000), method="isotonic",
                                  cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=seed))


def _rows_to_xy(rows: list[dict], rng: np.random.Generator | None = None) -> tuple[list[str], dict[str, list[str]]]:
    texts = []
    for r in rows:
        meta = dict(r["meta"])
        if rng is None or rng.random() > 0.3:      # uneori fără conținutul atașamentelor
            meta["attachments"] = r.get("attachments") or meta.get("attachments")
        texts.append(normalize_text(r["text"], meta))
    return texts, {h: [r[h] for r in rows] for h in HEADS}


def train_m1(seed: int = 7, *, models_dir: str | Path | None = None, n_train: int = 260, n_test: int = 80) -> dict:
    from sklearn.metrics import accuracy_score, f1_score

    out_dir = _models_dir(models_dir)
    train_rows = generate_corpus(n_per_scenario=n_train, seed=seed)
    test_rows = generate_corpus(n_per_scenario=n_test, seed=seed + 1000)
    rng = np.random.default_rng(seed)
    X_txt, Y = _rows_to_xy(train_rows, rng)
    T_txt, TY = _rows_to_xy(test_rows, rng)
    vec = _vectorizer()
    X = vec.fit_transform(X_txt)
    T = vec.transform(T_txt)
    heads, metrics = {}, {}
    for h in HEADS:
        clf = _head(seed).fit(X, Y[h])
        heads[h] = clf
        proba = clf.predict_proba(T)
        pred = clf.classes_[proba.argmax(axis=1)]
        y = np.array(TY[h])
        conf = proba.max(axis=1)
        metrics[h] = {"accuracy": round(float(accuracy_score(y, pred)), 4),
                      "macro_f1": round(float(f1_score(y, pred, average="macro")), 4),
                      "ece": round(expected_calibration_error(conf, pred == y), 4), "classes": list(map(str, clf.classes_))}
    model = {"vectorizer": vec, "heads": heads, "seed": seed}
    version = version_tag("m1-tfidf-lr-iso", seed, n_train, metrics["scenario"]["accuracy"])
    model["version"] = version
    save_pickle(model, out_dir / MODEL_FILE)
    _CACHE.pop(str(out_dir), None)
    # ambiguitate pe setul de test
    amb = [_classify_with(model, t, None) for t in test_rows[:: max(1, len(test_rows) // 400)]]
    flagged = [c for c in amb if c.ambiguous]
    # test de stres: doar textul reclamației, fără atașamente și fără metadate
    S = vec.transform([normalize_text(r["text"], None) for r in test_rows])
    stress = {h: round(float(accuracy_score(TY[h], heads[h].classes_[heads[h].predict_proba(S).argmax(axis=1)])), 4)
              for h in HEADS}
    metrics.update({"n_train": len(train_rows), "n_test": len(test_rows), "model_version": version,
                    "ambiguous_rate_sample": round(len(flagged) / max(1, len(amb)), 4),
                    "accuracy_text_only": stress,
                    "held_out": "a corpus generated with another seed (seed+1000): the same templates, other people, styles and facts; "
                                "accuracy on real complaints will be lower"})
    update_metrics(out_dir, "m1_classifier", metrics)
    return metrics


_CACHE: dict[str, dict] = {}


def _load(models_dir: str | Path | None = None) -> dict:
    d = _models_dir(models_dir)
    key = str(d)
    if key not in _CACHE:
        if not (d / MODEL_FILE).exists():
            train_m1(models_dir=d)
        _CACHE[key] = load_pickle(d / MODEL_FILE)
    return _CACHE[key]


def _classify_with(model: dict, row_or_text: Any, meta: dict | None) -> Classification:
    if isinstance(row_or_text, dict):
        text, meta = row_or_text["text"], {**row_or_text["meta"], "attachments": row_or_text.get("attachments")}
    else:
        text = row_or_text
    X = model["vectorizer"].transform([normalize_text(text, meta)])
    out: dict[str, tuple[str, float, dict[str, float]]] = {}
    proba_all: dict[str, float] = {}
    degenerate = False
    for h, clf in model["heads"].items():
        p = clf.predict_proba(X)[0]
        if p.max() < 1.5 / len(p):
            # calibrarea izotonică e plată pentru texte foarte diferite de cele văzute: folosim media
            # estimatorilor de bază (necalibrați) și marcăm cazul ambiguu
            p = np.mean([cc.estimator.predict_proba(X)[0] for cc in clf.calibrated_classifiers_], axis=0)
            degenerate = True
        order = np.argsort(-p)
        dist = {str(c): round(float(v), 4) for c, v in zip(clf.classes_, p)}
        out[h] = (str(clf.classes_[order[0]]), float(p[order[0]]), dist)
        for c, v in dist.items():
            proba_all[f"{h}:{c}"] = v
    s_probs = sorted(out["scenario"][2].values(), reverse=True)
    margin = s_probs[0] - (s_probs[1] if len(s_probs) > 1 else 0.0)
    scen = out["scenario"][0]
    inconsistent = scen in FIXED and (FIXED[scen][0] != out["channel"][0] or FIXED[scen][1] != out["dispute_type"][0])
    return Classification(channel=Channel(out["channel"][0]), dispute_type=DisputeType(out["dispute_type"][0]),
                          scenario=Scenario(scen), probability=round(out["scenario"][1], 4), proba=proba_all,
                          ambiguous=bool(margin < AMBIGUITY_MARGIN or out["scenario"][1] < AMBIGUITY_MIN_PROB
                                         or inconsistent or degenerate),
                          model_version=model["version"],
                          method="ml")


def classify_complaint(text: str, meta: dict | None = None, *, models_dir: str | Path | None = None) -> Classification:
    """Canalul, tipul disputei și scenariul, cu probabilități calibrate.

    `meta` (opțional): {"channel_hint": "card"|..., "source": "app"|..., "attachments": [{"kind", "content"}] sau
    ["sms", ...]}. `proba` are chei prefixate cu capul: "scenario:phishing_link", "channel:card", "dispute_type:app".
    """
    return _classify_with(_load(models_dir), text, meta)
