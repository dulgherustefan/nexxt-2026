"""M4: cât de mult imită o pagină pagina de referință (de exemplu login-ul Banca Demo).

Fără randare: comparăm patru semnale extrase din HTML, fiecare 0–1:
- text: cât din textul paginii de referință (3-grame de cuvinte) apare în pagina candidată, plus simhash;
- formulare: câte din câmpurile referinței (utilizator, parolă...) le are și candidata;
- DOM: cât din secvența de taguri a referinței (4-grame) se regăsește;
- aspect: paleta de culori din CSS și titlul.
Scorul = medie ponderată (WEIGHTS). Conținerea (nu Jaccard) e aleasă intenționat: o pagină de phishing
copiază referința și adaugă câmpuri noi (card, CVV, cod SMS).
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz

from versoml.osint.base import FIXTURES_DIR, ToolResult, failure, tool
from versoml.osint.crawl import _protected_registered, _soup, extract_forms, fetch_with_html, visible_text
from versoml.osint.params import param
from versoml.osint.util import fold, registered_domain

WEIGHTS = {"text": 0.4, "forms": 0.2, "dom": 0.2, "style": 0.2}
SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "path", "meta", "link"})
REFERENCE_DIR = FIXTURES_DIR / "reference"


def _tokens(html: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(visible_text(html)))


def _shingles(items: list[str], k: int) -> set[tuple[str, ...]]:
    if len(items) < k:
        return {tuple(items)} if items else set()
    return {tuple(items[i:i + k]) for i in range(len(items) - k + 1)}


def containment(reference: set | Counter, candidate: set | Counter) -> float:
    if not reference:
        return 0.0
    if isinstance(reference, Counter):
        return sum((reference & candidate).values()) / sum(reference.values())
    return len(reference & candidate) / len(reference)


def simhash(tokens: list[str], bits: int = 64) -> int:
    weights = [0] * bits
    for token, count in Counter(tokens).items():
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
        for i in range(bits):
            weights[i] += count if h >> i & 1 else -count
    return sum(1 << i for i, w in enumerate(weights) if w > 0)


def simhash_similarity(a: int, b: int, bits: int = 64) -> float:
    """1 pentru identice, ~0 pentru texte fără legătură (distanța Hamming medie e bits/2)."""
    distance = bin(a ^ b).count("1")
    return max(0.0, 1 - 2 * distance / bits)


def _tag_sequence(html: str) -> list[str]:
    soup = _soup(html)
    return [t.name for t in soup.find_all(True) if t.name not in SKIP_TAGS][:3000]


def _colors(html: str) -> set[str]:
    found = set()
    for match in re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", html):
        value = match.lower()
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        found.add(value)
    for r, g, b in re.findall(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", html):
        found.add(f"{int(r):02x}{int(g):02x}{int(b):02x}")
    return found


def _title(html: str) -> str:
    soup = _soup(html)
    return fold(soup.title.get_text(" ", strip=True)) if soup.title else ""


def _field_kinds(html: str) -> Counter:
    kinds = Counter()
    for form in extract_forms(html, "https://pagina.invalid/"):
        for field in form["inputs"]:
            if field["kind"] != "other":
                kinds[field["kind"]] += 1
    return kinds


def page_features(html: str) -> dict[str, Any]:
    tokens = _tokens(html)
    return {
        "shingles": _shingles(tokens, 3),
        "simhash": simhash(tokens),
        "fields": _field_kinds(html),
        "tags": _shingles(_tag_sequence(html), 4),
        "colors": _colors(html),
        "title": _title(html),
        "tokens": len(tokens),
    }


@lru_cache(maxsize=16)
def _reference_features(name: str) -> dict[str, Any] | None:
    path = REFERENCE_DIR / f"{name}.html"
    if not path.is_file():
        return None
    return page_features(path.read_text(encoding="utf-8"))


def compare(html: str, reference: str) -> dict[str, Any]:
    ref = _reference_features(reference)
    if ref is None:
        raise KeyError(reference)
    cand = page_features(html)
    text = 0.7 * containment(ref["shingles"], cand["shingles"]) + 0.3 * simhash_similarity(ref["simhash"],
                                                                                          cand["simhash"])
    forms = containment(ref["fields"], cand["fields"]) if ref["fields"] else None
    dom = containment(ref["tags"], cand["tags"])
    palette = len(ref["colors"] & cand["colors"]) / len(ref["colors"] | cand["colors"]) if ref["colors"] else 0.0
    title = fuzz.token_set_ratio(ref["title"], cand["title"]) / 100 if ref["title"] and cand["title"] else 0.0
    style = 0.6 * palette + 0.4 * title
    components = {"text": text, "forms": forms, "dom": dom, "style": style}
    used = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in used)
    score = sum(WEIGHTS[k] * v for k, v in used.items()) / total_weight if total_weight else 0.0
    return {
        "reference": reference,
        "score": round(score, 4),
        "components": {k: (round(v, 4) if v is not None else None) for k, v in components.items()},
        "weights": WEIGHTS,
        "details": {
            "palette_shared": sorted(ref["colors"] & cand["colors"]),
            "reference_fields": dict(ref["fields"]),
            "candidate_fields": dict(cand["fields"]),
            "title_similarity": round(title, 3),
            "candidate_tokens": cand["tokens"],
        },
    }


def _label(reference: str) -> str:
    return {"bancademo_login": "the Demo Bank sign-in page"}.get(reference, f"the reference page {reference}")


def _fmt(value: float) -> str:
    return f"{value:.2f}"


@tool("page_similarity", group="domain-intel")
def page_similarity(html: str, reference: str = "bancademo_login", url: str | None = None) -> ToolResult:
    """M4: similaritatea 0–1 dintre o pagină (HTML) și pagina de referință (text, formulare, DOM, aspect)."""
    started = time.perf_counter()
    args: dict[str, Any] = {"reference": reference, "html_chars": len(html or "")}
    if url:
        args["url"] = url
    if not (html or "").strip():
        return failure("page_similarity", args, "Empty HTML: there is nothing to compare.", error="empty html")
    try:
        data = compare(html, reference)
    except KeyError:
        return failure("page_similarity", args, f"The reference page \"{reference}\" does not exist.",
                       error=f"unknown reference: {reference}")
    score = data["score"]
    domain = registered_domain(url) if url else ""
    data["candidate_domain"] = domain or None
    label = _label(reference)
    if domain and domain in _protected_registered():
        summary, signal = f"The page is on the protected domain {domain} (similarity {_fmt(score)} to {label}).", "verde"
    elif score >= float(param("page_similarity_red")):
        where = f" on {domain}" if domain else ""
        summary, signal = f"The page{where} is {round(score * 100)}% similar to {label}: it imitates it.", "rosu"
    elif score >= float(param("page_similarity_yellow")):
        summary, signal = f"The page is partly similar ({round(score * 100)}%) to {label}.", "galben"
    else:
        summary, signal = f"The page does not resemble {label} (similarity {_fmt(score)}).", "neutru"
    return ToolResult(tool="page_similarity", args=args, ok=True, data=data, summary=summary, signal=signal,
                      mode="offline", latency_ms=int((time.perf_counter() - started) * 1000))


@tool("page_similarity_url", group="domain-intel")
async def page_similarity_url(url: str, reference: str = "bancademo_login") -> ToolResult:
    """Descarcă pagina (sigur, ca fetch_page) și o compară cu pagina de referință (M4)."""
    page, html = await fetch_with_html(url)
    if not html:
        return failure("page_similarity_url", {"url": url, "reference": reference},
                       f"The page could not be compared: {page.summary}", error=page.error or "no HTML",
                       mode=page.mode)
    result = page_similarity(html, reference, url=page.data.get("final_url") or url)
    result.tool = "page_similarity_url"
    result.args = {"url": url, "reference": reference}
    result.mode = page.mode
    result.source_url = page.source_url
    result.retrieved_at = page.retrieved_at
    return result
