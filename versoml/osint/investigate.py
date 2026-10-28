"""Orchestrarea OSINT: extrage artefactele dintr-un text (SMS, e-mail) și rulează în paralel tool-urile
potrivite pentru fiecare artefact. Planul se fixează din tipurile de artefacte înainte de orice apel
(Plan-Then-Execute); conținutul paginilor nu poate adăuga pași. Nu ridică niciodată excepții.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from versoml.osint import crawl, domain, lookalike, phone, registry_ro, sanctions, search, threatintel
from versoml.osint.page_similarity import page_similarity as similarity_of
from versoml.osint.base import ToolResult, describe_error, failure, secret, sort_results, tool
from versoml.osint.util import host_from, normalize_phone, normalize_ro, split_domain

ARTIFACT_KEYS = ("domains", "urls", "phones", "cuis", "ibans", "companies")
MAX_PER_KIND = 5
DEFAULT_TIMEOUT_S = 20.0
MAX_CONCURRENCY = 12

# ---------------------------------------------------------------- extragerea artefactelor

_TRAIL = ".,;:!?)]}»”\"'"
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'«»]+")
BARE_URL_RE = re.compile(r"(?i)(?<![@\w./-])((?:[^\W_][\w-]*\.)+[^\W\d_]{2,24}/[^\s<>\"'«»]*)")
DOMAIN_RE = re.compile(r"(?i)(?<![@\w.-])((?:[^\W_](?:[\w-]{0,61}[^\W_])?\.)+[^\W\d_]{2,24})(?![\w-])")
PHONE_RE = re.compile(r"(?<![\w+])(\+?\d[\d\s().-]{7,16}\d)(?![\w])")
IBAN_RE = re.compile(r"(?i)\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?)\b")
CUI_LABEL_RE = re.compile(
    r"(?i)\b(?:CUI|CIF|C\.U\.I\.|C\.I\.F\.|cod(?:ul)?\s+fiscal|cod(?:ul)?\s+unic(?:\s+de\s+înregistrare)?)"
    r"\s*[:.]?\s*((?:RO\s?)?\d{2,10})\b")
CUI_VAT_RE = re.compile(r"\bRO\s?(\d{2,10})\b")
COMPANY_RE = re.compile(
    r"\b((?:S\.?C\.?\s+)?(?:[A-ZĂÂÎȘȚ][A-Za-zĂÂÎȘȚăâîșț0-9&'-]*\s+){1,6}"
    r"(?:S\.?R\.?L\.?(?:-D)?|S\.?A\.?|SNC|PFA|LTD|LLC|GMBH))(?![\w])")
LEGAL_FORM_RE = re.compile(r"^(?:S\.?R\.?L\.?(?:-D)?|S\.?A\.?|SNC|PFA|LTD|LLC|GMBH)$")
COMPANY_PREFIXES = re.compile(r"^(?:S\.?C\.?\s+|Firma\s+|Societatea\s+|Compania\s+|Beneficiar(?:ul)?:?\s+)+", re.I)


def _dedup(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _company_name(match: str) -> str:
    """Numele firmei: fără prefixe („Firma”, „Beneficiar:”); dacă există o rulare cu majuscule, doar ea."""
    words = COMPANY_PREFIXES.sub("", match).split()
    if not words:
        return ""
    form, body = words[-1], words[:-1]
    run: list[str] = []
    for word in reversed(body):
        if word.isupper() or not any(c.isalpha() for c in word):
            run.insert(0, word)
        else:
            break
    chosen = run if run and len(run) < len(body) else body
    return " ".join([*chosen, form]).strip()


def _clean_url(url: str) -> str:
    url = url.rstrip(_TRAIL)
    return url if "://" in url else "https://" + url


def extract_artifacts(text: str, exclude: set[str] | None = None) -> dict[str, list[str]]:
    """Domenii, URL-uri, telefoane RO, IBAN-uri, CUI-uri și firme dintr-un text neîncrezut.

    `exclude` scoate identificatorii cunoscuți ai victimei (de exemplu IBAN-ul sau telefonul ei).
    """
    text = normalize_ro(text or "")
    excluded = {e.replace(" ", "").lower() for e in (exclude or set())}
    urls = [_clean_url(m.group(0)) for m in URL_RE.finditer(text)]
    stripped = URL_RE.sub(" ", text)
    for match in BARE_URL_RE.finditer(stripped):
        if split_domain(host_from(match.group(1))):
            urls.append(_clean_url(match.group(1)))
    urls = _dedup(urls)
    stripped = BARE_URL_RE.sub(" ", stripped)
    domains: list[str] = []
    for url in urls:
        parts = split_domain(host_from(url))
        if parts:
            domains.append(parts.host)
    for match in DOMAIN_RE.finditer(stripped):
        candidate = match.group(1).rstrip(".").lower()
        parts = split_domain(candidate)
        if parts and parts.suffix and not candidate.replace(".", "").isdigit():
            domains.append(parts.host)
    ibans = _dedup([m.group(1).replace(" ", "").upper() for m in IBAN_RE.finditer(text)
                    if _plausible_iban(m.group(1).replace(" ", "").upper())])
    without_ibans = IBAN_RE.sub(" ", stripped)
    phones = _dedup([p for p in (normalize_phone(m.group(1)) for m in PHONE_RE.finditer(without_ibans)) if p])
    cuis = [m.group(1).upper().replace(" ", "") for m in CUI_LABEL_RE.finditer(without_ibans)]
    cuis += [m.group(1) for m in CUI_VAT_RE.finditer(without_ibans)]
    cuis = _dedup([c.removeprefix("RO") for c in cuis])
    phones = [p for p in phones if p.lstrip("+")[2:] not in cuis and p.lstrip("+") not in cuis]
    companies = _dedup([_company_name(m.group(1)) for m in COMPANY_RE.finditer(text)])
    found = {
        "domains": _dedup(domains),
        "urls": urls,
        "phones": phones,
        "cuis": cuis,
        "ibans": ibans,
        "companies": companies,
    }
    return {k: [v for v in values if v.replace(" ", "").lower() not in excluded] for k, values in found.items()}


def _plausible_iban(value: str) -> bool:
    lengths = registry_ro.IBAN_LENGTHS
    return len(value) == lengths.get(value[:2], -1)


# ---------------------------------------------------------------- planul


Step = tuple[str, Callable[..., Any], dict[str, Any]]
# Chei acceptate și la singular (apelanții construiesc uneori {kind + "s": [...]})
KEY_ALIASES = {"domain": "domains", "url": "urls", "phone": "phones", "cui": "cuis", "iban": "ibans",
               "company": "companies", "companys": "companies", "firma": "companies", "firme": "companies"}


def _normalize_artifacts(artifacts: dict[str, Any]) -> dict[str, list[str]]:
    merged: dict[str, list[Any]] = {key: [] for key in ARTIFACT_KEYS}
    for key, values in (artifacts or {}).items():
        canonical = KEY_ALIASES.get(str(key).lower(), str(key).lower())
        if canonical in merged:
            merged[canonical] += [values] if isinstance(values, str) else list(values or [])
    out: dict[str, list[str]] = {}
    for key in ARTIFACT_KEYS:
        out[key] = _dedup([normalize_ro(str(v)).strip() for v in merged[key]])[:MAX_PER_KIND]
    hosts = [host_from(u) for u in out["urls"]]
    out["domains"] = _dedup([*(split_domain(d).host for d in out["domains"] if split_domain(d)),
                             *(h for h in hosts if split_domain(h))])[:MAX_PER_KIND * 2]
    out["phones"] = _dedup([normalize_phone(p) or p for p in out["phones"]])
    return out


def _keyed_enabled() -> dict[str, bool]:
    return {
        "urlhaus_check": bool(secret("urlhaus_auth_key")),
        "urlscan_search": bool(secret("urlscan_api_key")),
        "virustotal_domain": bool(secret("virustotal_api_key")),
        "safe_browsing_check": bool(secret("google_safe_browsing_key")),
    }


def plan(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    """Planul fix: ce tool rulează pentru ce artefact (fără să apeleze nimic)."""
    a = _normalize_artifacts(artifacts)
    keyed = _keyed_enabled()
    steps: list[dict[str, Any]] = []
    url_hosts = {host_from(u) for u in a["urls"]}
    for d in a["domains"]:
        for name in ("rdap_domain", "dns_records", "ct_certificates", "wayback_first_seen", "news_search",
                     "lookalike_score", "ip_geo"):
            steps.append({"tool": name, "target": d})
        if d not in url_hosts:
            steps.append({"tool": "openphish_check", "target": d})
            steps.append({"tool": "fetch_page", "target": f"https://{d}/"})
            steps.append({"tool": "page_similarity", "target": f"https://{d}/"})
        for name in ("urlhaus_check", "urlscan_search", "virustotal_domain"):
            if keyed[name]:
                steps.append({"tool": name, "target": d})
    for u in a["urls"]:
        steps += [{"tool": "fetch_page", "target": u}, {"tool": "page_similarity", "target": u},
                  {"tool": "openphish_check", "target": u}]
        if keyed["safe_browsing_check"]:
            steps.append({"tool": "safe_browsing_check", "target": u})
    steps += [{"tool": "phone_intel", "target": p} for p in a["phones"]]
    steps += [{"tool": "anaf_company", "target": c} for c in a["cuis"]]
    steps += [{"tool": "validate_iban", "target": i} for i in a["ibans"]]
    for c in a["companies"]:
        steps += [{"tool": "sanctions_screen", "target": c}, {"tool": "news_search", "target": c}]
    return steps


# ---------------------------------------------------------------- execuția


async def _guarded(name: str, target: str, call: Callable[[], Awaitable[Any] | Any], timeout_s: float,
                   limiter: asyncio.Semaphore) -> Any:
    started = time.perf_counter()
    try:
        async with limiter:
            value = call()
            if inspect.isawaitable(value):
                value = await asyncio.wait_for(value, timeout=timeout_s)
            return value
    except (asyncio.TimeoutError, TimeoutError):
        return failure(name, {"target": target}, f"{name} nu a terminat în {timeout_s:.0f} s pentru {target}.",
                       error="timeout", mode="live", started=started)
    except Exception as exc:  # noqa: BLE001 - investigația nu se oprește din cauza unui tool
        return failure(name, {"target": target}, f"{name} a eșuat pentru {target}.", error=describe_error(exc),
                       started=started)


async def investigate(artifacts: dict, timeout_s: float = DEFAULT_TIMEOUT_S) -> list[ToolResult]:
    """Rulează în paralel toate tool-urile potrivite artefactelor; rezultatele, sortate roșu → verde."""
    try:
        a = _normalize_artifacts(artifacts or {})
    except Exception as exc:  # noqa: BLE001
        return [failure("investigate", {"artifacts": str(artifacts)[:200]}, "Artefacte invalide.",
                        error=describe_error(exc))]
    keyed = _keyed_enabled()
    limiter = asyncio.Semaphore(MAX_CONCURRENCY)
    url_hosts = {host_from(u) for u in a["urls"]}

    def run(name: str, target: str, call: Callable[[], Any]) -> Awaitable[Any]:
        return _guarded(name, target, call, timeout_s, limiter)

    # Etapa 1: tool-uri independente
    stage1: dict[tuple[str, str], Awaitable[Any]] = {}
    pages: dict[str, Awaitable[Any]] = {}
    for d in a["domains"]:
        stage1[("rdap_domain", d)] = run("rdap_domain", d, lambda d=d: domain.rdap_domain(d))
        stage1[("dns_records", d)] = run("dns_records", d, lambda d=d: domain.dns_records(d))
        stage1[("ct_certificates", d)] = run("ct_certificates", d, lambda d=d: domain.ct_certificates(d))
        stage1[("wayback_first_seen", d)] = run("wayback_first_seen", d, lambda d=d: domain.wayback_first_seen(d))
        if d not in url_hosts:
            stage1[("openphish_check", d)] = run("openphish_check", d, lambda d=d: threatintel.openphish_check(d))
        stage1[("news_search", d)] = run("news_search", d, lambda d=d: search.news_search(d))
        if keyed["urlhaus_check"]:
            stage1[("urlhaus_check", d)] = run("urlhaus_check", d, lambda d=d: threatintel.urlhaus_check(d))
        if keyed["urlscan_search"]:
            stage1[("urlscan_search", d)] = run("urlscan_search", d, lambda d=d: threatintel.urlscan_search(d))
        if keyed["virustotal_domain"]:
            stage1[("virustotal_domain", d)] = run("virustotal_domain", d,
                                                   lambda d=d: threatintel.virustotal_domain(d))
        if d not in url_hosts:
            pages[f"https://{d}/"] = run("fetch_page", d, lambda d=d: crawl.fetch_with_html(f"https://{d}/"))
    for u in a["urls"]:
        pages[u] = run("fetch_page", u, lambda u=u: crawl.fetch_with_html(u))
        stage1[("openphish_check", u)] = run("openphish_check", u, lambda u=u: threatintel.openphish_check(u))
        if keyed["safe_browsing_check"]:
            stage1[("safe_browsing_check", u)] = run("safe_browsing_check", u,
                                                     lambda u=u: threatintel.safe_browsing_check(u))
    for p in a["phones"]:
        stage1[("phone_intel", p)] = run("phone_intel", p, lambda p=p: phone.phone_intel(p))
    for c in a["cuis"]:
        stage1[("anaf_company", c)] = run("anaf_company", c, lambda c=c: registry_ro.anaf_company(c))
    for i in a["ibans"]:
        stage1[("validate_iban", i)] = run("validate_iban", i, lambda i=i: registry_ro.validate_iban(i))
    for c in a["companies"]:
        stage1[("sanctions_screen", c)] = run("sanctions_screen", c, lambda c=c: sanctions.sanctions_screen(c))
        stage1[("news_search", c)] = run("news_search", c, lambda c=c: search.news_search(c))

    keys = list(stage1)
    gathered = await asyncio.gather(*stage1.values(), *pages.values())
    values, page_values = gathered[:len(keys)], gathered[len(keys):]
    results: dict[tuple[str, str], Any] = dict(zip(keys, values))
    out: list[ToolResult] = [v for v in values if isinstance(v, ToolResult)]

    # Etapa 2: tool-uri care folosesc rezultatele etapei 1
    stage2: list[Awaitable[Any]] = []
    for url, value in zip(pages, page_values):
        if isinstance(value, tuple):
            page, html = value
            out.append(page)
            if html:
                final = page.data.get("final_url") or url
                stage2.append(run("page_similarity", url,
                                  lambda html=html, final=final: similarity_of(html, url=final)))
        elif isinstance(value, ToolResult):
            out.append(value)
    for d in a["domains"]:
        rdap, ct, dns = results.get(("rdap_domain", d)), results.get(("ct_certificates", d)), results.get(("dns_records", d))
        age = rdap.data.get("age_hours") if isinstance(rdap, ToolResult) and rdap.ok else None
        cert_age = ct.data.get("cert_age_hours") if isinstance(ct, ToolResult) and ct.ok else None
        stage2.append(run("lookalike_score", d, lambda d=d, age=age, cert_age=cert_age:
                          lookalike.lookalike_score(d, age_hours=age, cert_age_hours=cert_age)))
        if isinstance(dns, ToolResult) and dns.ok:
            for ip in (dns.data.get("A") or [])[:2]:
                stage2.append(run("ip_geo", ip, lambda ip=ip: domain.ip_geo(ip)))
    out += [v for v in await asyncio.gather(*stage2) if isinstance(v, ToolResult)]
    return sort_results(out)


@tool("investigate", zones=("aml", "client"), group="osint", input_schema={
    "type": "object",
    "properties": {
        "artifacts": {
            "type": "object",
            "description": "Identificatori publici ai atacului sau ai beneficiarului (niciodată ai victimei).",
            "properties": {k: {"type": "array", "items": {"type": "string"}} for k in ARTIFACT_KEYS},
            "additionalProperties": False,
        },
        "timeout_s": {"type": "number", "default": DEFAULT_TIMEOUT_S},
    },
    "required": ["artifacts"],
})
async def investigate_tool(artifacts: dict, timeout_s: float = DEFAULT_TIMEOUT_S) -> list[ToolResult]:
    """Rulează în paralel toate tool-urile OSINT potrivite pentru domenii, URL-uri, telefoane, CUI-uri, IBAN-uri și firme."""
    return await investigate(artifacts, timeout_s=timeout_s)


@tool("extract_artifacts", zones=("aml", "client"), group="osint")
def extract_artifacts_tool(text: str) -> ToolResult:
    """Extrage din text (SMS, e-mail) domeniile, URL-urile, telefoanele RO, IBAN-urile, CUI-urile și firmele."""
    started = time.perf_counter()
    found = extract_artifacts(text)
    labels = {"domains": "domenii", "urls": "URL-uri", "phones": "telefoane", "cuis": "CUI-uri", "ibans": "IBAN-uri",
              "companies": "firme"}
    parts = [f"{len(v)} {labels[k]}" for k, v in found.items() if v]
    summary = "Artefacte găsite: " + (", ".join(parts) if parts else "niciunul") + "."
    return ToolResult(tool="extract_artifacts", args={"text_chars": len(text or "")}, ok=True, data=found,
                      summary=summary, signal="neutru", mode="offline",
                      latency_ms=int((time.perf_counter() - started) * 1000))
