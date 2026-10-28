"""The campaign linker: other client-zone cases that look like the same scam.

Three signals, all information for a person (the rules never read them, and nothing crosses the wall):
1. shared indicators: the same payee IBAN, the same registered domain, the same phone number;
2. M6 entity resolution (versoml/ml/m6_entity_resolution.py), which also links transitively and by company name;
3. narrative similarity between the pseudonymized complaints: embeddings (versoml.knowledge.embed_texts) when they
   are available, a TF-IDF cosine otherwise.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

log = logging.getLogger("versoml.client.campaign")

# similarity at which two stories alone link two cases (information only, never a decision input)
NARRATIVE_THRESHOLD = {"embedding": 0.88, "lexical": 0.6}
MAX_OTHERS = 200


def _norm_domain(value: str) -> str:
    from versoml.data.ids import registered_domain

    return registered_domain(value or "")


def _norm_phone(value: str) -> str:
    from versoml.data.ids import normalize_phone

    return normalize_phone(value or "")


def _norm_iban(value: str) -> str:
    return (value or "").replace(" ", "").upper()


def normalize(ind: dict) -> dict[str, set[str]]:
    return {"ibans": {_norm_iban(v) for v in ind.get("ibans") or [] if v},
            "domains": {d for d in (_norm_domain(v) for v in ind.get("domains") or []) if d},
            "phones": {p for p in (_norm_phone(v) for v in ind.get("phones") or []) if len(p) >= 8}}


def mask(kind: str, value: str) -> str:
    if kind == "iban":
        return f"{value[:4]} {value[4:8]} •••• {value[-4:]}" if len(value) > 12 else value
    if kind == "phone":
        return f"{value[:3]} 7•• ••• {value[-3:]}" if len(value) > 6 else "•••"
    return value


def lexical_similarity(a: str, texts: list[str]) -> list[float]:
    if not texts or not (a or "").strip():
        return [0.0] * len(texts)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit_transform([a, *texts])
        return [float(x) for x in (matrix[1:] @ matrix[0].T).toarray().ravel()]
    except Exception:  # noqa: BLE001 - an empty vocabulary, for example
        return [0.0] * len(texts)


def narrative_similarity(text: str, others: list[str],
                         embed: Callable[[list[str]], Any] | None = None) -> tuple[list[float], str]:
    """Cosine similarity of `text` with each of `others` (all pseudonymized), and the method used."""
    if embed is not None and others:
        try:
            vectors = embed([text, *others])
        except Exception as exc:  # noqa: BLE001
            log.info("embeddings unavailable: %s", type(exc).__name__)
            vectors = None
        if vectors is not None and len(vectors) == len(others) + 1:
            return [float(vectors[0] @ v) for v in vectors[1:]], "embedding"
    return lexical_similarity(text, others), "lexical"


def link(case_id: str, indicators: dict, narrative: str, others: list[dict],
         embed: Callable[[list[str]], Any] | None = None) -> dict | None:
    """The campaign this case belongs to, or None. `others`: [{case_id, indicators, narrative}]."""
    others = [o for o in others if o.get("case_id") and o["case_id"] != case_id][:MAX_OTHERS]
    if not others:
        return None
    mine = normalize(indicators)
    shared: dict[str, set[str]] = {"iban": set(), "domain": set(), "phone": set()}
    links: dict[str, list[str]] = {}
    for o in others:
        theirs = normalize(o.get("indicators") or {})
        for kind, key in (("iban", "ibans"), ("domain", "domains"), ("phone", "phones")):
            common = mine[key] & theirs[key]
            if common:
                shared[kind] |= common
                links.setdefault(o["case_id"], []).append(f"same {kind}")
    # M6: the same signals, transitively and with company names (one IBAN, domain and phone per case)
    try:
        from versoml.ml.m6_entity_resolution import link_cases

        def row(cid: str, ind: dict[str, set[str]]) -> dict:
            return {"case_id": cid, "iban": next(iter(sorted(ind["ibans"])), None),
                    "domain": next(iter(sorted(ind["domains"])), None), "phone": next(iter(sorted(ind["phones"])), None)}

        rows = [row(case_id, mine)] + [row(o["case_id"], normalize(o.get("indicators") or {})) for o in others]
        for cluster in link_cases(rows):
            if case_id in cluster.get("case_ids", []):
                for cid in cluster["case_ids"]:
                    if cid != case_id:
                        links.setdefault(cid, []).append("linked by entity resolution (M6)")
    except Exception as exc:  # noqa: BLE001 - M6 is optional; the direct matches above still count
        log.info("M6 unavailable: %s", type(exc).__name__)
    best = 0.0
    method = "lexical"
    with_text = [o for o in others if (o.get("narrative") or "").strip()]
    if (narrative or "").strip() and with_text:
        sims, method = narrative_similarity(narrative, [o["narrative"] for o in with_text], embed)
        threshold = NARRATIVE_THRESHOLD[method]
        for o, sim in zip(with_text, sims):
            if sim >= threshold:
                links.setdefault(o["case_id"], []).append(f"similar story ({sim:.2f})")
            if o["case_id"] in links:
                best = max(best, sim)
    if not links:
        return None
    case_ids = sorted({case_id, *links})
    campaign_id = "CMP-" + hashlib.sha256(case_ids[0].encode()).hexdigest()[:6].upper()
    indicators_out = [{"kind": kind, "value_masked": mask(kind, v)} for kind in ("iban", "domain", "phone")
                      for v in sorted(shared[kind])]
    return {"campaign_id": campaign_id, "case_ids": case_ids, "shared_indicators": indicators_out,
            "similarity": round(max(0.0, min(1.0, best)), 3), "method": method,
            "links": [{"case_id": cid, "why": sorted(set(why))} for cid, why in sorted(links.items())]}
