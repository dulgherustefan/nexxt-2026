"""The client zone's access to the knowledge base (versoml.knowledge), with graceful degradation.

The knowledge base informs and cites; it never feeds the rules engine. Every query that leaves the process is
pseudonymized first (the knowledge base may embed it or send it to a model). When the module, its index or the
embeddings are missing, every helper returns an empty result and the case goes on without citations.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

log = logging.getLogger("versoml.client.grounding")

ZONE = "client"


def _kb(zone: str = ZONE):
    try:
        from versoml.knowledge import get_kb
    except Exception as exc:  # noqa: BLE001 - the knowledge base is optional
        log.info("knowledge base unavailable: %s", type(exc).__name__)
        return None
    try:
        return get_kb(zone)
    except Exception as exc:  # noqa: BLE001
        log.warning("knowledge base failed to load: %s", type(exc).__name__)
        return None


def available(zone: str = ZONE) -> bool:
    return _kb(zone) is not None


def hit_dict(hit: Any) -> dict:
    """A Hit as a plain dict with the contract's fields (pydantic model, dataclass or dict)."""
    if hit is None:
        return {}
    if hasattr(hit, "model_dump"):
        data = hit.model_dump(mode="json")
    elif isinstance(hit, dict):
        data = dict(hit)
    else:
        data = {k: getattr(hit, k, None) for k in ("id", "kind", "title", "text", "source", "confidence", "rule_ids",
                                                   "score", "why", "meta")}
    data.setdefault("rule_ids", [])
    data.setdefault("why", {})
    data.setdefault("meta", {})
    return data


def _privacy():
    from versoml.zone_client.runtime import get_runtime

    return get_runtime().privacy


def pseudonymize(text: str, scope: str = "kb-query") -> tuple[str, dict]:
    try:
        return _privacy().pseudonymize(text or "", scope)
    except Exception:  # noqa: BLE001
        return text or "", {}


def search(q: str, k: int = 6, kinds: Iterable[str] | None = None, rule_ids: Iterable[str] | None = None,
           zone: str = ZONE) -> list[dict]:
    kb = _kb(zone)
    if kb is None or not (q or "").strip():
        return []
    query, _ = pseudonymize(q)
    try:
        hits = kb.search(query, k=int(k), kinds=list(kinds) if kinds else None,
                         rule_ids=list(rule_ids) if rule_ids else None)
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.search failed: %s", type(exc).__name__)
        return []
    return [hit_dict(h) for h in hits or []]


def for_rules(rule_ids: Iterable[str], k_per: int = 1, zone: str = ZONE) -> list[dict]:
    kb = _kb(zone)
    ids = [r for r in dict.fromkeys(rule_ids or []) if r]
    if kb is None or not ids:
        return []
    try:
        return [hit_dict(h) for h in kb.for_rules(ids, k_per=k_per) or []]
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.for_rules failed: %s", type(exc).__name__)
        return []


async def ask(question: str, k: int = 6, zone: str = ZONE) -> dict:
    kb = _kb(zone)
    if kb is None:
        return {"question": question, "answer": "The knowledge base is not available.", "citations": [],
                "grounded": False, "mode": "unavailable"}
    query, vault = pseudonymize(question)
    try:
        answer = await kb.ask(query, k=int(k))
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.ask failed: %s", type(exc).__name__)
        return {"question": question, "answer": "The knowledge base could not answer.", "citations": [],
                "grounded": False, "mode": "error"}
    data = answer.model_dump(mode="json") if hasattr(answer, "model_dump") else dict(answer)
    data["question"] = question
    if vault:
        try:
            data["answer"] = _privacy().restore(data.get("answer") or "", vault)
        except Exception:  # noqa: BLE001
            pass
    data["citations"] = [hit_dict(h) for h in data.get("citations") or []]
    return data


def stats(zone: str = ZONE) -> dict:
    kb = _kb(zone)
    if kb is None:
        return {"chunks": {}, "embedding_model": None, "dense": False, "built_at": None, "available": False}
    try:
        data = dict(kb.stats() or {})
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.stats failed: %s", type(exc).__name__)
        data = {}
    data.setdefault("chunks", {})
    data.setdefault("embedding_model", None)
    data.setdefault("dense", False)
    data.setdefault("built_at", None)
    data["available"] = True
    return data


def precedents(text: str, k: int = 3, exclude_case_id: str | None = None) -> list[dict]:
    """Closed cases like this one. `text` must already be pseudonymized."""
    kb = _kb(ZONE)
    if kb is None or not (text or "").strip():
        return []
    try:
        hits = kb.precedents(text, k=int(k), exclude_case_id=exclude_case_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.precedents failed: %s", type(exc).__name__)
        return []
    out = []
    for h in hits or []:
        hit = hit_dict(h)
        meta = hit.get("meta") or {}
        out.append({"hit": hit, "outcome": outcome_view(meta.get("outcome") or {}),
                    "case_id_masked": mask_case_id(meta.get("case_id"))})
    return out


def outcome_view(outcome: dict) -> dict:
    """The keys the case page shows, whether the precedent came from the golden sets or from a sealed live case."""
    view = dict(outcome)
    view.setdefault("decision", outcome.get("verdict") or outcome.get("rambursare_t1"))
    if "recovered" not in view and outcome.get("recovery") is not None:
        view["recovered"] = outcome["recovery"] not in ("", "NU_RECOMANDAM_RECUPERARE", "NONE", None)
    if "status" not in view and outcome.get("requires_human") is not None:
        view["status"] = "signed by a person" if outcome["requires_human"] else "decided by the rules"
    return view


def add_precedent(case_id: str, text: str, outcome: dict, meta: dict | None = None) -> bool:
    """Stores a sealed case as a precedent. `text` must already be pseudonymized."""
    kb = _kb(ZONE)
    if kb is None:
        return False
    try:
        kb.add_precedent(case_id, text, outcome, meta=meta)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("kb.add_precedent failed: %s", type(exc).__name__)
        return False


def embed(texts: list[str], input_type: str = "clustering", namespace: str = "campaign"):
    """L2-normalized vectors for pseudonymized texts, or None (no embeddings offline or without the module)."""
    if not texts:
        return None
    try:
        from versoml.knowledge import embed_texts

        return embed_texts(texts, input_type=input_type, namespace=namespace)
    except Exception as exc:  # noqa: BLE001 - RawPIIError included: nothing is sent, the caller falls back
        log.info("embed_texts unavailable: %s", type(exc).__name__)
        return None


def mask_case_id(case_id: Any) -> str:
    s = str(case_id or "")
    return f"{s[:8]}••{s[-2:]}" if len(s) > 10 else ("••" if s else "")


# ---------------------------------------------------------------- plain references for the letter

_RO_TO_EN = [(r"\bLegea\s+nr\.\s*", "Law "), (r"\bLegea\b", "Law"), (r"\bL209\b", "Law 209/2019"),
             (r"\bCJUE\b", "CJEU"), (r"\balin\.", "para."), (r"\blit\.", "letter"), (r"\bși\b", "and")]
_LEGAL = re.compile(r"\b(?:Law|CJEU|GDPR|PSD2|Regulation|Directive|Emergency Ordinance|OUG)\b|\bart\.\s?\d")
_RO_CHARS = re.compile(r"[ăâîșțĂÂÎȘȚ]")
_WALL = re.compile(r"129/2019|ONPCSB|money\s+laundering|spălare|AML|suspicious", re.I)


def _clean_reference(raw: str) -> str | None:
    text = re.sub(r"\s*\([^)]*\(?[^)]*\)?[^)]*\)\s*$", "", raw.strip()).strip().rstrip(".")
    for pattern, repl in _RO_TO_EN:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"\bArticles?\s+(?=\d)", "art. ", text)
    text = re.sub(r"\s*[–—]\s*", "-", text)
    text = re.sub(r"(Law \d+/\d{4})\s+(art\.)", r"\1, \2", text)
    # a reference names the act, not a date: every number in the letter is checked against the case file
    text = re.sub(r",?\s+\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}$", "", text)
    text = re.sub(r"^(CJEU ruling C-\d+/\d+)\s+[A-Z][\w-]+$", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    if text and _LEGAL.search(text) and not _RO_CHARS.search(text) and not _WALL.search(text) and len(text) <= 90:
        return text
    return None


def plain_reference_parts(hit: dict) -> list[str]:
    """The citable legal references of a hit, in English: from the rule's legal basis (meta.basis), else its source
    or title. None of them when the hit is unverified [U], Romanian-only, or anything the anti-tipping-off wall
    would stop."""
    if (hit.get("confidence") or "") == "U":
        return []
    for raw in ((hit.get("meta") or {}).get("basis") or "", hit.get("source") or "", hit.get("title") or ""):
        parts = [p for p in (_clean_reference(x) for x in str(raw).split(";")) if p]
        if parts:
            return parts
    return []


def plain_reference(hit: dict) -> str | None:
    """"Law 209/2019, art. 173" for a hit, or None (see plain_reference_parts)."""
    parts = plain_reference_parts(hit)
    return parts[0] if parts else None


def plain_references(hits: Iterable[dict], limit: int = 3) -> list[str]:
    out: list[str] = []
    for hit in hits:
        for ref in plain_reference_parts(hit):
            if not any(ref.startswith(x) or x.startswith(ref) for x in out):
                out.append(ref)
    return out[:limit]
