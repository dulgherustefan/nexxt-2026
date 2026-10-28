"""Utilitare comune pentru modele: directorul de artefacte, salvare/încărcare, metrici."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np


def models_dir(path: str | Path | None = None) -> Path:
    if path is not None:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return p
    from versoml.config import get_settings

    return get_settings().models_dir


def save_pickle(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def load_pickle(path: Path) -> Any:
    with open(path, "rb") as fh:
        return pickle.load(fh)


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def update_metrics(models_path: Path, section: str, metrics: dict) -> dict:
    """Actualizează o secțiune din metrics.json (alte module își păstrează secțiunile)."""
    path = models_path / "metrics.json"
    data = read_json(path) if path.exists() else {}
    data[section] = metrics
    write_json(data, path)
    return data


def version_tag(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"{prefix}-{h}"


def expected_calibration_error(conf: np.ndarray, correct: np.ndarray, n_bins: int = 10) -> float:
    """ECE pe încrederea clasei prezise (intervale egale)."""
    conf = np.asarray(conf, dtype=float)
    correct = np.asarray(correct, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def binary_metrics(y: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> dict:
    from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

    y = np.asarray(y).astype(int)
    pred = (np.asarray(score) >= threshold).astype(int)
    return {"auc": round(float(roc_auc_score(y, score)), 4),
            "pr_auc": round(float(average_precision_score(y, score)), 4),
            "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
            "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
            "threshold": round(float(threshold), 4), "n": int(len(y)), "positives": int(y.sum())}


def best_f1_threshold(y: np.ndarray, score: np.ndarray) -> float:
    from sklearn.metrics import precision_recall_curve

    p, r, t = precision_recall_curve(np.asarray(y).astype(int), np.asarray(score))
    f1 = 2 * p * r / np.clip(p + r, 1e-12, None)
    if len(t) == 0:
        return 0.5
    i = int(np.nanargmax(f1[:-1])) if len(f1) > 1 else 0
    return float(t[i])
