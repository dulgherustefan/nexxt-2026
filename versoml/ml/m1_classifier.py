"""M1: clasificatorul de contestații (docs/05 §8, docs/06 §4.2), ca ansamblu stivuit.

Membrii, pe câte un cap (canal, tipul disputei, scenariu):
- `char`: TF-IDF pe caractere (2–5, `char_wb`) + regresie logistică;
- `word`: TF-IDF pe cuvinte (1–2) + regresie logistică;
- `cnb`: Complement Naive Bayes pe aceleași cuvinte;
- `emb`: regresie logistică pe vectorii de embedding (`versoml.knowledge.embeddings.embed_texts`, namespace "m1"),
  doar când vectorul există (cache-ul static din git sau cel de rulare; apel live doar în modul LLM `live`).
Meta-învățătorul e o regresie logistică multinomială pe log-probabilitățile membrilor, antrenată pe predicții
out-of-fold cu grupuri de șabloane (nicio frază a fold-ului de validare nu e în fold-ul de antrenare), apoi
calibrată prin scalarea temperaturii (un singur parametru, potrivit cu numărul mic de exemple pe clasă). Există
două meta-învățătoare: `full` (cu `emb`) și `fallback` (fără), folosit când embedding-ul lipsește (offline).

Intrarea se normalizează: ş/ţ cu sedilă -> ș/ț cu virgulă, litere mici, fără diacritice; cifrele devin „0";
metadatele (canalul indicat, sursa, tipurile de atașamente) intră ca jetoane. Textul pentru embedding trece prin
mascarea datelor personale (`mask_pii`), ca în restul sistemului nimic brut nu pleacă spre Bedrock.

`ambiguous=True` când diferența dintre primele două scenarii e mică, când probabilitatea e mică, când canalul
prezis nu se potrivește cu scenariul prezis sau când textul are prea puține cuvinte cunoscute: atunci decide un
om sau LLM-ul ajutător. Clasificarea nu decide nimic; regulile decid.

Evaluarea cinstită (în `metrics.json`, secțiunea m1_classifier): grupuri de șabloane ținute deoparte, transfer
între limbi (antrenat pe engleză, testat pe română), șabloane -> parafraze LLM și robustețe la greșeli de tastare,
fiecare membru comparat cu ansamblul.
"""

from __future__ import annotations

import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from versoml.contracts import Channel, Classification, DisputeType, Scenario
from versoml.data.complaints import SCENARIO_LABELS, add_typos, generate_corpus
from versoml.data.text import normalize_ro, strip_diacritics
from versoml.ml.common import (expected_calibration_error, load_pickle, models_dir as _models_dir, save_pickle,
                            update_metrics, version_tag)

MODEL_FILE = "m1_classifier.pkl"
AMBIGUITY_MARGIN = 0.20          # PARAM [U]: sub această diferență între primele două scenarii, cazul e ambiguu
AMBIGUITY_MIN_PROB = 0.50        # PARAM [U]: sub această probabilitate a scenariului prezis, cazul e ambiguu
MIN_KNOWN_WORDS = 3              # PARAM [U]: sub atâtea cuvinte din vocabular, textul nu seamănă cu o reclamație
HEADS = ("channel", "dispute_type", "scenario")
TEXT_MEMBERS = ("char", "word", "cnb")
MEMBERS = TEXT_MEMBERS + ("emb",)
FIXED = {s: lab for s, lab in SCENARIO_LABELS.items() if s not in ("reclamatie_tardiva", "injectie_document")}
EMB_NAMESPACE = "m1"
EMB_INPUT = "classification"
N_TEMPLATES = 45                 # rânduri pe (scenariu, limbă, grup de variante)
N_TYPOLOGY = 10                  # rânduri pe (tipologie, limbă, grup)
META_C = 0.03                    # regularizare puternică: meta-învățătorul nu are voie să învețe detaliile fold-urilor
OOD_QUANTILE = 0.005             # pragul de similaritate: cuantila 0,5% a textelor de antrenare
EMB_TEMPLATE_ROWS = 12           # din fiecare (scenariu, limbă, grup), câte rânduri au vectori în cache-ul static
_EPS = 1e-4


# ---------------------------------------------------------------- textul


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


def mask_pii(text: str) -> str:
    """Datele personale recunoscute (telefon, e-mail, IBAN, card, CNP) devin <TIP>; restul rămâne."""
    from versoml.shared.privacy import scan

    text = normalize_ro(text or "")
    spans = sorted(((d["start"], d["end"], d["type"]) for d in scan(text) if d.get("pii")), reverse=True)
    for start, end, kind in spans:
        text = text[:start] + f"<{kind}>" + text[end:]
    return text[:2000]


def _row_meta(r: dict) -> dict:
    return {**(r.get("meta") or {}), "attachments": r.get("attachments") or (r.get("meta") or {}).get("attachments")}


# ---------------------------------------------------------------- corpusul


def build_corpus(seed: int = 7, *, n_templates: int = N_TEMPLATES, n_typology: int = N_TYPOLOGY,
                 llm: bool = True) -> list[dict]:
    """Șabloane EN și RO (3 grupuri de variante), reclamații pe tipologii și corpusul LLM din git.

    Fiecare rând are `group` (0..2): fold-ul de șabloane folosit la stivuire și la evaluare. Rândurile LLM au
    grupul lotului de generare. `emb_candidate` marchează rândurile cu vectori în cache-ul static.
    """
    from versoml.data.corpus_llm import load_llm_corpus
    from versoml.data.typologies import typology_corpus

    rows: list[dict] = []
    for lang in ("en", "ro"):
        for g in range(3):
            part = generate_corpus(n_templates, seed, language=lang, group=g)
            seen: dict[str, int] = {}
            for r in part:
                k = seen.get(r["scenario"], 0)
                seen[r["scenario"]] = k + 1
                r["emb_candidate"] = k < EMB_TEMPLATE_ROWS
            rows += part
            rows += [{**r, "emb_candidate": False} for r in typology_corpus(n_typology, seed, language=lang, group=g)]
    if llm:
        # vague / multi-issue complaints have no single right label: evaluation only (the ambiguity flag)
        rows += [{**r, "emb_candidate": True, "eval_only": bool(r.get("expect_ambiguous"))} for r in load_llm_corpus()]
    return rows


def embedding_texts(rows: list[dict]) -> list[str]:
    return [mask_pii(r["text"]) for r in rows]


def lookup_embeddings(rows: list[dict]) -> tuple[np.ndarray | None, np.ndarray]:
    """Vectorii din cache (fără apeluri live) și masca rândurilor care îi au."""
    try:
        from versoml.knowledge.embeddings import get_embedder, normalize_text as emb_norm
    except Exception:  # noqa: BLE001 - modulul de embeddings lipsește: doar membrii de text
        return None, np.zeros(len(rows), dtype=bool)
    texts = [emb_norm(t) for t in embedding_texts(rows)]
    try:
        matrix, found = get_embedder().lookup(texts, EMB_INPUT, namespace=EMB_NAMESPACE)
    except Exception:  # noqa: BLE001
        return None, np.zeros(len(rows), dtype=bool)
    found = np.asarray(found, dtype=bool)
    return (np.asarray(matrix, dtype=np.float32) if found.any() else None), found


def build_embedding_cache(seed: int = 7) -> dict:
    """O singură dată, live: vectorii rândurilor `emb_candidate` intră în cache-ul static din git."""
    from versoml.knowledge.embeddings import embed_texts

    rows = [r for r in build_corpus(seed) if r.get("emb_candidate")]
    texts = embedding_texts(rows)
    t0 = time.time()
    out = embed_texts(texts, EMB_INPUT, namespace=EMB_NAMESPACE, allow_live=True, static=True)
    return {"rows": len(rows), "ok": out is not None, "seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- membrii și stiva


def _vectorizers() -> tuple[Any, Any]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, max_features=80000, sublinear_tf=True)
    word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=30000, sublinear_tf=True,
                           token_pattern=r"(?u)\b\w+\b")
    return char, word


def _expand(p: np.ndarray, have: list[str], classes: list[str]) -> np.ndarray:
    """Probabilitățile unui membru pe lista completă de clase (o clasă absentă la antrenare primește 0)."""
    if list(have) == classes:
        return p
    out = np.zeros((p.shape[0], len(classes)))
    idx = {c: i for i, c in enumerate(classes)}
    for j, c in enumerate(have):
        out[:, idx[c]] = p[:, j]
    return out


def _fit_members(texts: list[str], E: np.ndarray | None, has_e: np.ndarray, Y: dict[str, np.ndarray],
                 heads: tuple[str, ...], seed: int) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB

    char_v, word_v = _vectorizers()
    Xc, Xw = char_v.fit_transform(texts), word_v.fit_transform(texts)
    m: dict[str, Any] = {"char_v": char_v, "word_v": word_v, "heads": {h: {} for h in heads}}
    use_e = E is not None and has_e.sum() >= 50

    def fit(task: tuple[str, str]) -> tuple[str, str, Any]:
        h, k = task
        y = Y[h]
        if k == "char":
            return h, k, LogisticRegression(C=4.0, max_iter=3000, tol=1e-3).fit(Xc, y)
        if k == "word":
            return h, k, LogisticRegression(C=4.0, max_iter=3000, tol=1e-3).fit(Xw, y)
        if k == "cnb":
            return h, k, ComplementNB(alpha=0.3).fit(Xw, y)
        return h, k, LogisticRegression(C=2.0, max_iter=3000, tol=1e-3).fit(E[has_e], y[has_e])

    tasks = [(h, k) for h in heads for k in TEXT_MEMBERS] + [(h, "emb") for h in heads
                                                            if use_e and len(set(Y[h][has_e])) > 1]
    with ThreadPoolExecutor(max_workers=min(len(tasks), _WORKERS)) as ex:   # LR elibereaza GIL-ul in BLAS
        for h, k, est in ex.map(fit, tasks):
            m["heads"][h][k] = est
    return m


def _member_proba(m: dict, texts: list[str], E: np.ndarray | None, has_e: np.ndarray, classes: dict) -> dict:
    Xc, Xw = m["char_v"].transform(texts), m["word_v"].transform(texts)
    out: dict[str, dict[str, np.ndarray | None]] = {}
    for h, hm in m["heads"].items():
        cl = classes[h]
        res = {"char": _expand(hm["char"].predict_proba(Xc), list(hm["char"].classes_), cl),
               "word": _expand(hm["word"].predict_proba(Xw), list(hm["word"].classes_), cl),
               "cnb": _expand(hm["cnb"].predict_proba(Xw), list(hm["cnb"].classes_), cl), "emb": None}
        if "emb" in hm and E is not None and has_e.any():
            pe = np.full((len(texts), len(cl)), np.nan)
            pe[has_e] = _expand(hm["emb"].predict_proba(E[has_e]), list(hm["emb"].classes_), cl)
            res["emb"] = pe
        out[h] = res
    return out


_WORKERS = max(2, min(12, (os.cpu_count() or 2)))


def _centroids(Xw: Any, y: np.ndarray) -> np.ndarray:
    cl = sorted(set(y))
    c = np.vstack([np.asarray(Xw[y == k].mean(axis=0)).ravel() for k in cl])
    return c / np.clip(np.linalg.norm(c, axis=1, keepdims=True), 1e-12, None)


def _max_similarity(Xw: Any, centroids: np.ndarray) -> np.ndarray:
    return np.asarray((Xw @ centroids.T).max(axis=1)).ravel() if Xw.shape[0] else np.zeros(0)


def _meta_x(probs: dict[str, np.ndarray | None], members: tuple[str, ...]) -> np.ndarray:
    return np.hstack([np.log(np.clip(probs[k], _EPS, 1.0)) for k in members])


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _fit_meta(X: np.ndarray, y: np.ndarray, classes: list[str], seed: int) -> dict:
    """LR multinomială pe log-probabilitățile OOF + temperatură aleasă pe predicții meta tot OOF."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    lr = LogisticRegression(C=META_C, max_iter=3000)
    n_splits = max(2, min(5, int(np.bincount(np.unique(y, return_inverse=True)[1]).min())))
    logits = cross_val_predict(lr, X, y, cv=StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed),
                               method="decision_function")
    labels = np.searchsorted(np.array(sorted(set(y))), y)
    best_t, best_nll = 1.0, math.inf
    for t in np.logspace(-0.7, 0.7, 29):
        p = _softmax(logits / t)
        nll = -float(np.mean(np.log(np.clip(p[np.arange(len(y)), labels], 1e-12, 1.0))))
        if nll < best_nll:
            best_t, best_nll = float(t), nll
    lr.fit(X, y)
    oof_correct = np.array(sorted(set(y)))[logits.argmax(axis=1)] == y
    return {"lr": lr, "T": best_t, "classes": classes, "_oof_correct": oof_correct}


def _meta_proba(meta: dict, X: np.ndarray) -> np.ndarray:
    z = meta["lr"].decision_function(X)
    if z.ndim == 1:
        z = np.stack([-z, z], axis=1)
    return _expand(_softmax(z / meta["T"]), list(meta["lr"].classes_), meta["classes"])


def fit_stack(rows: list[dict], *, folds: np.ndarray, E: np.ndarray | None, has_e: np.ndarray,
              heads: tuple[str, ...] = HEADS, seed: int = 7) -> dict:
    """Membri pe fiecare fold de șabloane -> predicții OOF -> meta-învățătoare; apoi membrii refăcuți pe tot."""
    texts = [normalize_text(r["text"], _row_meta(r)) for r in rows]
    Y = {h: np.array([r[h] for r in rows]) for h in heads}
    classes = {h: sorted(set(Y[h])) for h in heads}
    oof = {h: {k: np.full((len(rows), len(classes[h])), np.nan) for k in MEMBERS} for h in heads}

    def one_fold(f: Any) -> tuple[np.ndarray, dict]:
        tr, te = folds != f, folds == f
        m = _fit_members([t for t, ok in zip(texts, tr) if ok], None if E is None else E[tr], has_e[tr],
                         {h: Y[h][tr] for h in heads}, heads, seed)
        return te, _member_proba(m, [t for t, ok in zip(texts, te) if ok], None if E is None else E[te], has_e[te],
                                 classes)

    uniq = sorted(set(folds.tolist()))
    with ThreadPoolExecutor(max_workers=len(uniq) + 1) as ex:
        final_future = ex.submit(_fit_members, texts, E, has_e, Y, heads, seed)
        for te, p in ex.map(one_fold, uniq):
            for h in heads:
                for k in MEMBERS:
                    if p[h][k] is not None:
                        oof[h][k][te] = p[h][k]
        members = final_future.result()
    metas: dict[str, dict] = {}
    for h in heads:
        metas[h] = {"fallback": _fit_meta(_meta_x(oof[h], TEXT_MEMBERS), Y[h], classes[h], seed)}
        full_rows = has_e & ~np.isnan(oof[h]["emb"]).any(axis=1)
        if E is not None and full_rows.sum() >= 100 and len(set(Y[h][full_rows])) == len(classes[h]):
            X_full = _meta_x({k: oof[h][k][full_rows] for k in MEMBERS}, MEMBERS)
            metas[h]["full"] = _fit_meta(X_full, Y[h][full_rows], classes[h], seed)
            # selecția modelului, tot pe OOF: meta cu embedding se servește doar dacă bate fallback-ul pe aceleași rânduri
            acc_full = float(metas[h]["full"]["_oof_correct"].mean())
            acc_fb = float(metas[h]["fallback"]["_oof_correct"][full_rows].mean())
            metas[h]["use_full"] = acc_full > acc_fb
            metas[h]["oof_accuracy"] = {"full": round(acc_full, 4), "fallback_same_rows": round(acc_fb, 4)}
        for meta in metas[h].values():
            if isinstance(meta, dict):
                meta.pop("_oof_correct", None)
    # similaritatea cu centroizii claselor (cuvinte): sub prag, textul nu seamănă cu nicio reclamație văzută
    Xw = members["word_v"].transform(texts)
    cent = _centroids(Xw, Y["scenario"] if "scenario" in heads else Y[heads[0]])
    sims = _max_similarity(Xw, cent)
    return {"members": members, "metas": metas, "classes": classes, "heads": heads, "centroids": cent,
            "ood_threshold": float(np.quantile(sims, OOD_QUANTILE)),
            "emb_dim": None if E is None else int(E.shape[1]), "n_rows": len(rows), "n_emb_rows": int(has_e.sum())}


def predict_stack(model: dict, rows: list[dict], E: np.ndarray | None = None, has_e: np.ndarray | None = None) -> dict:
    """{head: {member: proba | None, "fallback": proba, "full": proba | None (NaN pe rândurile fără vector)}}."""
    texts = [normalize_text(r["text"], _row_meta(r)) for r in rows]
    has_e = np.zeros(len(rows), dtype=bool) if has_e is None else has_e
    probs = _member_proba(model["members"], texts, E, has_e, model["classes"])
    out = {}
    for h in model["heads"]:
        res = dict(probs[h])
        res["fallback"] = _meta_proba(model["metas"][h]["fallback"], _meta_x(probs[h], TEXT_MEMBERS))
        res["full"] = None
        if "full" in model["metas"][h] and probs[h]["emb"] is not None and has_e.any():
            full = np.full_like(res["fallback"], np.nan)
            full[has_e] = _meta_proba(model["metas"][h]["full"], _meta_x({k: probs[h][k][has_e] for k in MEMBERS}, MEMBERS))
            res["full"] = full
        res["use_full"] = bool(model["metas"][h].get("use_full"))
        out[h] = res
    return out


def ensemble_proba(pred_head: dict) -> np.ndarray:
    """Ansamblul servit: meta `full` acolo unde există vectorul, altfel `fallback`."""
    p = pred_head["fallback"].copy()
    if pred_head.get("full") is not None and pred_head.get("use_full", True):
        ok = ~np.isnan(pred_head["full"]).any(axis=1)
        p[ok] = pred_head["full"][ok]
    return p


# ---------------------------------------------------------------- evaluare


def _score(y: np.ndarray, p: np.ndarray, classes: list[str]) -> dict:
    from sklearn.metrics import f1_score

    pred = np.array(classes)[p.argmax(axis=1)]
    conf = p.max(axis=1)
    return {"accuracy": round(float((pred == y).mean()), 4),
            "macro_f1": round(float(f1_score(y, pred, average="macro", labels=sorted(set(y)), zero_division=0)), 4),
            "ece": round(expected_calibration_error(conf, pred == y), 4), "n": int(len(y))}


def evaluate(model: dict, rows: list[dict], E: np.ndarray | None = None, has_e: np.ndarray | None = None,
             heads: tuple[str, ...] | None = None) -> dict:
    """Fiecare membru și ansamblul (fallback, full pe rândurile cu vector, servit) pe `rows`."""
    heads = heads or model["heads"]
    pred = predict_stack(model, rows, E, has_e)
    has_e = np.zeros(len(rows), dtype=bool) if has_e is None else has_e
    out: dict[str, Any] = {}
    for h in heads:
        y = np.array([r[h] for r in rows])
        cl = model["classes"][h]
        res = {k: _score(y, pred[h][k], cl) for k in TEXT_MEMBERS}
        res["ensemble_fallback"] = _score(y, pred[h]["fallback"], cl)
        if pred[h]["emb"] is not None and has_e.any():
            res["emb"] = _score(y[has_e], pred[h]["emb"][has_e], cl)
            res["fallback_same_rows"] = _score(y[has_e], pred[h]["fallback"][has_e], cl)
            if pred[h].get("full") is not None:
                res["ensemble_full"] = _score(y[has_e], pred[h]["full"][has_e], cl)
        res["ensemble_served"] = _score(y, ensemble_proba(pred[h]), cl)
        best = max(TEXT_MEMBERS, key=lambda k: res[k]["accuracy"])
        res["best_text_member"] = best
        out[h] = res
    return out


def _noisy(rows: list[dict], seed: int, rate: float = 0.12) -> list[dict]:
    import random

    rng = random.Random(seed)
    return [{**r, "text": add_typos(strip_diacritics(r["text"]), rng, rate)} for r in rows]


def _sel(rows: list[dict], E: np.ndarray | None, has_e: np.ndarray, mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return [rows[i] for i in idx], (None if E is None else E[idx]), has_e[idx]


def honest_evaluation(rows: list[dict], E: np.ndarray | None, has_e: np.ndarray, seed: int = 7) -> dict:
    """Patru împărțiri cinstite + împărțirea aleatoare veche (pentru comparație); modelele se antrenează în paralel."""
    group = np.array([r["group"] for r in rows])
    lang = np.array([r["language"] for r in rows])
    src = np.array([r["source"] for r in rows])
    kind = np.array([r.get("kind") or "" for r in rows])
    rng = np.random.default_rng(seed)
    rand = rng.random(len(rows)) < 0.25
    no_e = np.zeros(len(rows), dtype=bool)
    train_ok = np.array([not r.get("eval_only") for r in rows])
    plans = {
        # 1. șabloane ținute deoparte: antrenare pe grupurile 0 și 1 (OOF pe grup), test pe grupul 2
        "held_out": ((group != 2) & train_ok, HEADS, E, has_e, None),
        # 2. transfer între limbi: doar șabloanele în engleză
        "cross": ((lang == "en") & (src != "llm") & train_ok, ("scenario",), E, has_e, None),
        # 3. șabloane -> text liber: fără corpusul LLM
        "tmpl": ((src != "llm") & train_ok, ("scenario",), E, has_e, None),
        # 4. împărțirea aleatoare veche: aceleași șabloane în antrenare și test (doar pentru comparație)
        "random": ((src == "template") & ~rand, ("scenario",), None, no_e, 3),
    }

    def fit(name: str) -> tuple[str, dict]:
        mask, heads, EE, he, nf = plans[name]
        tr_rows, tr_E, tr_h = _sel(rows, EE, he, mask)
        folds = np.arange(len(tr_rows)) % nf if nf else np.array([r["group"] for r in tr_rows]) % 2
        return name, fit_stack(tr_rows, folds=folds, E=tr_E, has_e=tr_h, heads=heads, seed=seed)

    with ThreadPoolExecutor(max_workers=len(plans)) as ex:
        models = dict(ex.map(fit, list(plans)))
    m = models["held_out"]
    out: dict[str, Any] = {}
    te_rows, te_E, te_h = _sel(rows, E, has_e, (group == 2) & (src != "llm"))
    out["held_out_templates"] = {"train": "template groups 0+1 (EN+RO, typologies) + LLM batches 0+1, "
                                          "out-of-fold on group 0 vs 1",
                                 "test": "template group 2: phrase variants never seen in training",
                                 **evaluate(m, te_rows, te_E, te_h)}
    out["typo_noise"] = {"test": "held-out group 2, diacritics stripped and 12% of words with a typo",
                         **evaluate(m, _noisy(te_rows, seed), None, None, heads=("scenario",))}
    llm2 = (group == 2) & (src == "llm") & (kind != "hard_negative")
    if llm2.any():
        l_rows, l_E, l_h = _sel(rows, E, has_e, llm2)
        out["held_out_llm_batch"] = {"test": "LLM paraphrases of batch 2 (other writers)", **evaluate(m, l_rows, l_E, l_h)}
    ro_rows, ro_E, ro_h = _sel(rows, E, has_e, (lang == "ro") & (src != "typology"))
    out["cross_lingual_en_to_ro"] = {"train": "English templates only", "test": "Romanian templates and LLM paraphrases",
                                     **evaluate(models["cross"], ro_rows, ro_E, ro_h, heads=("scenario",))}
    para = (src == "llm") & (kind != "hard_negative")
    if para.any():
        p_rows, p_E, p_h = _sel(rows, E, has_e, para)
        out["templates_to_llm_paraphrases"] = {"train": "templates only (EN+RO, typologies)",
                                               "test": "LLM paraphrases and typology complaints, EN+RO",
                                               **evaluate(models["tmpl"], p_rows, p_E, p_h, heads=("scenario",))}
    hard = (src == "llm") & (kind == "hard_negative")
    if hard.any():
        h_rows, h_E, h_h = _sel(rows, E, has_e, hard)
        exp = np.array([bool(r.get("expect_ambiguous")) for r in h_rows])
        c_rows, c_E, c_h = _sel(h_rows, h_E, h_h, ~exp)
        res = evaluate(models["tmpl"], c_rows, c_E, c_h, heads=("scenario", ))   # labelled hard negatives only
        flagged = np.array([c["ambiguous"] for c in _classify_rows(models["held_out"], h_rows)])
        res["ambiguity"] = {"vague_or_multi_issue_flagged": round(float(flagged[exp].mean()), 4) if exp.any() else None,
                            "clear_hard_negatives_flagged": round(float(flagged[~exp].mean()), 4) if (~exp).any() else None}
        out["hard_negatives"] = {"model": "templates-only model (scenario, on changed-mind, subscription, processing-error "
                                          "and friendly-fraud texts); held-out model (ambiguity flag, text only)",
                                 **res}
    r_rows, _, _ = _sel(rows, None, no_e, (src == "template") & rand)
    out["random_split_leaky"] = {"note": "random 75/25 split of template rows: test texts share templates with "
                                         "training texts (what the old 0.99 measured)",
                                 **evaluate(models["random"], r_rows, heads=("scenario",))}
    return out


# ---------------------------------------------------------------- antrenarea


def train_m1(seed: int = 7, *, models_dir: str | Path | None = None, evaluate_honestly: bool = True) -> dict:
    out_dir = _models_dir(models_dir)
    t0 = time.time()
    all_rows = build_corpus(seed)
    E_all, has_all = lookup_embeddings(all_rows)
    keep = np.array([not r.get("eval_only") for r in all_rows])
    rows, E, has_e = _sel(all_rows, E_all, has_all, keep)
    folds = np.array([r["group"] for r in rows])
    model = fit_stack(rows, folds=folds, E=E, has_e=has_e, seed=seed)
    version = version_tag("m1-stack", seed, len(rows), int(has_e.sum()), sorted(model["metas"]["scenario"]))
    model.update({"version": version, "seed": seed})
    save_pickle(model, out_dir / MODEL_FILE)
    _CACHE.pop(str(out_dir), None)
    metrics: dict[str, Any] = {
        "model_version": version, "members": list(MEMBERS), "meta": "multinomial LR on out-of-fold log-probabilities "
        "(folds = template phrase groups), temperature-scaled", "n_rows": len(rows), "n_rows_with_embedding": int(has_e.sum()),
        "embedding_member": "available" if "full" in model["metas"]["scenario"] else "unavailable (fallback meta only)",
        "corpus": {s: int(sum(1 for r in rows if r["source"] == s)) for s in ("template", "typology", "llm")},
        "languages": {lang: int(sum(1 for r in rows if r["language"] == lang)) for lang in ("en", "ro")},
        "temperature": {h: {k: round(v["T"], 3) for k, v in model["metas"][h].items() if isinstance(v, dict) and "T" in v}
                        for h in HEADS},
        "embedding_meta_served": {h: bool(model["metas"][h].get("use_full")) for h in HEADS},
        "embedding_meta_oof": {h: model["metas"][h].get("oof_accuracy") for h in HEADS},
        "eval_only_rows": int((~keep).sum()),
    }
    if evaluate_honestly:
        ev = honest_evaluation(all_rows, E_all, has_all, seed)
        metrics["honest"] = ev
        ho = ev["held_out_templates"]
        for h in HEADS:   # the headline numbers are the held-out-template ones
            metrics[h] = {**ho[h]["ensemble_served"], "classes": model["classes"][h]}
        metrics["accuracy_text_only"] = {"scenario": ev["typo_noise"]["scenario"]["ensemble_served"]["accuracy"]}
    metrics["seconds"] = round(time.time() - t0, 1)
    update_metrics(out_dir, "m1_classifier", metrics)
    return metrics


_CACHE: dict[str, dict] = {}


def _load(models_dir: str | Path | None = None) -> dict:
    d = _models_dir(models_dir)
    key = str(d)
    if key not in _CACHE:
        if not (d / MODEL_FILE).exists():
            train_m1(models_dir=d, evaluate_honestly=False)
        _CACHE[key] = load_pickle(d / MODEL_FILE)
    return _CACHE[key]


def _query_embedding(text: str, allow_live: bool | None) -> np.ndarray | None:
    if allow_live is None:
        from versoml.config import get_settings

        allow_live = get_settings().versoml_llm_mode == "live"   # în auto/offline/replay: doar din cache
    try:
        from versoml.knowledge.embeddings import embed_texts

        v = embed_texts([mask_pii(text)], EMB_INPUT, namespace=EMB_NAMESPACE, allow_live=allow_live)
    except Exception:  # noqa: BLE001 - embedding-ul e un membru opțional
        return None
    return None if v is None else np.asarray(v, dtype=np.float32)


def _classify_rows(model: dict, rows: list[dict], E: np.ndarray | None = None) -> list[dict]:
    has_e = np.ones(len(rows), dtype=bool) if E is not None else np.zeros(len(rows), dtype=bool)
    pred = predict_stack(model, rows, E, has_e)
    Xw = model["members"]["word_v"].transform([normalize_text(r["text"], _row_meta(r)) for r in rows])
    known = np.asarray((Xw > 0).sum(axis=1)).ravel()
    sims = _max_similarity(Xw, model["centroids"])
    out = []
    for i in range(len(rows)):
        res: dict[str, Any] = {"proba": {}}
        for h in model["heads"]:
            p = ensemble_proba({k: (v[i:i + 1] if isinstance(v, np.ndarray) else v) for k, v in pred[h].items()})[0]
            cl = model["classes"][h]
            order = np.argsort(-p)
            res[h] = (cl[order[0]], float(p[order[0]]), sorted(p, reverse=True))
            for c, v in zip(cl, p):
                res["proba"][f"{h}:{c}"] = round(float(v), 4)
        s_probs = res["scenario"][2]
        margin = s_probs[0] - (s_probs[1] if len(s_probs) > 1 else 0.0)
        scen = res["scenario"][0]
        inconsistent = scen in FIXED and (FIXED[scen][0] != res["channel"][0] or FIXED[scen][1] != res["dispute_type"][0])
        res["ambiguous"] = bool(margin < AMBIGUITY_MARGIN or res["scenario"][1] < AMBIGUITY_MIN_PROB or inconsistent
                                or known[i] < MIN_KNOWN_WORDS or sims[i] < model["ood_threshold"])
        res["similarity"] = round(float(sims[i]), 4)
        res["embedding"] = E is not None
        out.append(res)
    return out


def classify_complaint(text: str, meta: dict | None = None, *, models_dir: str | Path | None = None,
                       allow_live: bool | None = None) -> Classification:
    """Canalul, tipul disputei și scenariul, cu probabilități calibrate (ansamblul stivuit).

    `meta` (opțional): {"channel_hint": "card"|..., "source": "app"|..., "attachments": [{"kind", "content"}] sau
    ["sms", ...]}. `proba` are chei prefixate cu capul: "scenario:phishing_link", "channel:card", "dispute_type:app".
    Membrul de embedding intră doar dacă vectorul textului există (cache sau, în modul LLM `live`, Bedrock);
    altfel decide meta-învățătorul fără el. `model_version` se termină în "+emb" sau "+text".
    """
    model = _load(models_dir)
    row = {"text": text, "meta": dict(meta or {}), "attachments": (meta or {}).get("attachments")}
    E = _query_embedding(text, allow_live) if "full" in model["metas"]["scenario"] else None
    if E is not None and E.shape[1] != model.get("emb_dim"):
        E = None
    res = _classify_rows(model, [row], E)[0]
    return Classification(channel=Channel(res["channel"][0]), dispute_type=DisputeType(res["dispute_type"][0]),
                          scenario=Scenario(res["scenario"][0]), probability=round(res["scenario"][1], 4),
                          proba=res["proba"], ambiguous=res["ambiguous"],
                          model_version=model["version"] + ("+emb" if res["embedding"] else "+text"), method="ml")
