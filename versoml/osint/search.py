"""Căutare web și de presă: Serper → Brave → Tavily → Exa → DuckDuckGo (ultimul fără cheie).

Doar identificatori publici ai beneficiarului (firmă, domeniu, telefon). Interogările care par să
conțină date ale victimei (CNP, număr de card, IBAN) sunt refuzate înainte de orice apel.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from versoml.osint.base import (
    Ctx,
    Interp,
    SourceError,
    ToolResult,
    describe_error,
    expect_status,
    failure,
    http_request,
    is_synthetic_target,
    run_source,
    secret,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import fold, host_from, normalize_phone, normalize_ro, split_domain

Kind = Literal["web", "news"]
PROVIDERS: tuple[str, ...] = ("serper", "brave", "tavily", "exa", "duckduckgo")
PROVIDER_KEYS: dict[str, str | None] = {
    "serper": "serper_api_key",
    "brave": "brave_api_key",
    "tavily": "tavily_api_key",
    "exa": "exa_api_key",
    "duckduckgo": None,
}
# Termenii cu care news_search caută; și, pliați, cei după care marcăm un rezultat ca „de fraudă"
NEWS_QUERY_TERMS = ("țeapă", "fraudă", "înșelăciune", "phishing", "ANPC", "DIICOT", "poliția")
# Cuvinte întregi (pliate, fără diacritice), cu formele flexionare uzuale scrise explicit
FRAUD_TERMS = (
    "teapa", "tepe", "frauda", "fraude", "fraudat", "fraudata", "fraudulos", "frauduloasa", "inselaciune",
    "inselaciuni", "inselatorie", "escroc", "escroci", "escrocherie", "escrocherii", "phishing", "smishing",
    "vishing", "anpc", "diicot", "politia", "plangere", "reclamatie", "reclamatii", "raportat", "raportata",
    "scam", "fraud", "nu dati codul", "furt",
)
TERM_DISPLAY = {
    "teapa": "țeapă", "tepe": "țepe", "frauda": "fraudă", "fraude": "fraude", "fraudat": "fraudat",
    "inselaciune": "înșelăciune", "inselatorie": "înșelătorie", "escroc": "escroc", "escrocherie": "escrocherie",
    "politia": "poliția", "plangere": "plângere", "reclamatie": "reclamație", "anpc": "ANPC", "diicot": "DIICOT",
    "nu dati codul": "„nu dați codul”", "fraudata": "fraudată", "frauduloasa": "frauduloasă",
    "inselaciuni": "înșelăciuni", "reclamatii": "reclamații", "raportata": "raportată",
}
SEARCH_TTL_S = 6 * 3600


# ---------------------------------------------------------------- garda de confidențialitate


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


IBAN_IN_TEXT = re.compile(r"(?i)\b([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?)\b")


def _iban_mod97(value: str) -> bool:
    text = value[4:] + value[:4]
    try:
        return int("".join(str(int(c, 36)) for c in text)) % 97 == 1
    except ValueError:
        return False


def privacy_violation(text: str) -> str | None:
    """Motivul refuzului dacă textul pare să conțină date ale victimei, altfel None."""
    for match in IBAN_IN_TEXT.finditer(text):
        candidate = match.group(1).replace(" ", "").upper()
        if re.fullmatch(r"RO\d{2}[A-Z]{4}[A-Z0-9]{16}", candidate) or _iban_mod97(candidate):
            return "pare să conțină un IBAN"
    compact = re.sub(r"[\s.-]", "", text)
    if re.search(r"(?<!\d)[1-8]\d{12}(?!\d)", compact):
        return "pare să conțină un CNP"
    for run in re.findall(r"(?<!\d)\d{13,19}(?!\d)", compact):
        if _luhn_ok(run):
            return "pare să conțină un număr de card"
    return None


# ---------------------------------------------------------------- furnizori


def _result(title: Any, url: Any, snippet: Any, provider: str, date: Any = None, source: Any = None) -> dict[str, Any]:
    url = str(url or "").strip()
    return {
        "title": normalize_ro(str(title or "")).strip(),
        "url": url,
        "snippet": normalize_ro(str(snippet or "")).strip()[:500],
        "source": str(source or host_from(url) or ""),
        "date": str(date) if date else None,
        "provider": provider,
    }


async def _serper(query: str, n: int, kind: Kind, key: str) -> list[dict[str, Any]]:
    url = "https://google.serper.dev/search" if kind == "web" else "https://google.serper.dev/news"
    resp = await http_request("POST", url, headers={"X-API-KEY": key}, json={"q": query, "num": n, "gl": "ro", "hl": "ro"})
    expect_status(resp)
    items = resp.json().get("organic" if kind == "web" else "news", []) or []
    return [_result(i.get("title"), i.get("link"), i.get("snippet"), "serper", i.get("date"), i.get("source"))
            for i in items]


async def _brave(query: str, n: int, kind: Kind, key: str) -> list[dict[str, Any]]:
    path = "web/search" if kind == "web" else "news/search"
    resp = await http_request(
        "GET",
        f"https://api.search.brave.com/res/v1/{path}",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        params={"q": query, "count": min(n, 20), "country": "RO", "search_lang": "ro"},
    )
    expect_status(resp)
    body = resp.json()
    items = (body.get("web") or {}).get("results", []) if kind == "web" else body.get("results", [])
    return [_result(i.get("title"), i.get("url"), i.get("description"), "brave", i.get("page_age") or i.get("age"),
                    (i.get("meta_url") or {}).get("hostname")) for i in items or []]


async def _tavily(query: str, n: int, kind: Kind, key: str) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "query": query,
        "max_results": min(n, 20),
        "topic": "news" if kind == "news" else "general",
        "search_depth": "basic",
        "include_published_date": True,
    }
    resp = await http_request("POST", "https://api.tavily.com/search",
                              headers={"Authorization": f"Bearer {key}"}, json=body)
    expect_status(resp)
    return [_result(i.get("title"), i.get("url"), i.get("content"), "tavily", i.get("published_date"))
            for i in resp.json().get("results", []) or []]


async def _exa(query: str, n: int, kind: Kind, key: str) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "query": query,
        "numResults": min(n, 25),
        "type": "auto",
        "userLocation": "RO",
        "contents": {"text": {"maxCharacters": 400}},
    }
    if kind == "news":
        body["category"] = "news"
    resp = await http_request("POST", "https://api.exa.ai/search", headers={"x-api-key": key}, json=body)
    expect_status(resp)
    out = []
    for i in resp.json().get("results", []) or []:
        snippet = i.get("text") or " ".join(i.get("highlights") or []) or i.get("summary")
        out.append(_result(i.get("title"), i.get("url"), snippet, "exa", i.get("publishedDate")))
    return out


def _ddg_sync(query: str, n: int, kind: Kind) -> list[dict[str, Any]]:
    from ddgs import DDGS

    client = DDGS(timeout=10)
    if kind == "news":
        return client.news(query, region="ro-ro", safesearch="moderate", max_results=n)
    return client.text(query, region="ro-ro", safesearch="moderate", max_results=n)


def ddg_query(query: str) -> str:
    """DuckDuckGo nu suportă bine OR și parantezele (expiră pe interogări lungi): păstrăm prima frază
    între ghilimele și cel mult trei termeni."""
    if " OR " not in query:
        return query
    quoted = re.findall(r'"[^"]+"', query)
    rest = re.sub(r'"[^"]+"', " ", query)
    terms = [t for t in re.split(r"[\s()]+", rest) if t and t != "OR"]
    return " ".join(quoted[:1] + terms[:3]).strip() or query


async def _duckduckgo(query: str, n: int, kind: Kind, key: str | None) -> list[dict[str, Any]]:
    try:
        items = await asyncio.wait_for(asyncio.to_thread(_ddg_sync, ddg_query(query), n, kind), timeout=15)
    except Exception as exc:  # noqa: BLE001 - ddgs ridică excepție și când nu găsește nimic
        if "no results" in str(exc).lower():
            return []
        raise
    return [_result(i.get("title"), i.get("href") or i.get("url"), i.get("body"), "duckduckgo", i.get("date"),
                    i.get("source")) for i in items or []]


ProviderFn = Callable[[str, int, Kind, Any], Awaitable[list[dict[str, Any]]]]
PROVIDER_FUNCS: dict[str, ProviderFn] = {
    "serper": _serper,
    "brave": _brave,
    "tavily": _tavily,
    "exa": _exa,
    "duckduckgo": _duckduckgo,
}


async def search_chain(query: str, n: int = 8, kind: Kind = "web") -> dict[str, Any]:
    """Încearcă furnizorii în ordine; primul cu rezultate câștigă. Ridică SourceError dacă niciunul nu răspunde."""
    attempts: list[dict[str, Any]] = []
    answered = False
    for name in PROVIDERS:
        key_field = PROVIDER_KEYS[name]
        key = secret(key_field) if key_field else None
        if key_field and not key:
            attempts.append({"provider": name, "status": "fara_cheie"})
            continue
        try:
            items = await PROVIDER_FUNCS[name](query, n, kind, key)
        except Exception as exc:  # noqa: BLE001 - trecem la următorul furnizor
            attempts.append({"provider": name, "status": "eroare", "detail": describe_error(exc)})
            continue
        answered = True
        items = [i for i in items if i.get("url")][:n]
        if not items:
            attempts.append({"provider": name, "status": "gol"})
            continue
        attempts.append({"provider": name, "status": "ok", "count": len(items)})
        return {"query": query, "kind": kind, "provider": name, "results": items, "attempts": attempts}
    if not answered:
        raise SourceError("niciun furnizor de căutare nu a răspuns: " +
                          ", ".join(f"{a['provider']}={a['status']}" for a in attempts))
    return {"query": query, "kind": kind, "provider": None, "results": [], "attempts": attempts}


# ---------------------------------------------------------------- interpretare


def fraud_terms_in(text: str) -> list[str]:
    folded = fold(text)
    return [t for t in FRAUD_TERMS if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", folded)]


def _mentions(entity: str, text: str) -> bool:
    folded, ent = fold(text), fold(entity)
    if not ent:
        return False
    if ent in folded:
        return True
    digits = re.sub(r"\D", "", entity)
    if len(digits) >= 9 and digits[-9:] in re.sub(r"\D", "", text):
        return True
    tokens = [t for t in re.findall(r"[a-z0-9]+", ent) if t not in {"srl", "sa", "sc", "srld", "pfa", "ii"}]
    return bool(tokens) and all(t in folded for t in tokens)


def annotate(results: list[dict[str, Any]], entity: str | None = None) -> list[dict[str, Any]]:
    out = []
    for item in results:
        blob = f"{item.get('title', '')} {item.get('snippet', '')}"
        enriched = dict(item)
        enriched["fraud_terms"] = fraud_terms_in(blob)
        if entity:
            enriched["mentions_entity"] = _mentions(entity, blob + " " + item.get("url", ""))
        out.append(enriched)
    return out


def _provider_label(name: str | None) -> str:
    return {"serper": "Serper (Google)", "brave": "Brave", "tavily": "Tavily", "exa": "Exa",
            "duckduckgo": "DuckDuckGo", "fixture": "înregistrare locală"}.get(name or "", name or "niciun furnizor")


def _build_web(raw: Any, ctx: Ctx) -> Interp:
    results = annotate(list(raw.get("results", [])))
    data = {"query": raw.get("query", ctx.args.get("query")), "provider": raw.get("provider"),
            "results": results, "count": len(results), "attempts": raw.get("attempts", [])}
    if not results:
        return Interp(data, f"Niciun rezultat web pentru „{data['query']}”.", "neutru")
    return Interp(data, f"{len(results)} rezultate web pentru „{data['query']}” (furnizor: "
                        f"{_provider_label(data['provider'])}).", "neutru")


def news_signal(results: list[dict[str, Any]], entity: str) -> tuple[int, str]:
    hits = [r for r in results if r.get("fraud_terms") and r.get("mentions_entity", True)]
    if len(hits) >= int(param("news_red_hits")):
        return len(hits), "rosu"
    if hits:
        return len(hits), "galben"
    return 0, "neutru"


def _build_news(raw: Any, ctx: Ctx) -> Interp:
    entity = ctx.args.get("entity", "")
    results = annotate(list(raw.get("results", [])), entity)
    hits, signal = news_signal(results, entity)
    data = {"entity": entity, "query": raw.get("query"), "provider": raw.get("provider"), "results": results,
            "count": len(results), "fraud_hits": hits, "attempts": raw.get("attempts", [])}
    if hits:
        terms = sorted({TERM_DISPLAY.get(t, t) for r in results for t in r.get("fraud_terms", [])})
        summary = (f"{hits} din {len(results)} rezultate asociază „{entity}” cu termeni de fraudă "
                   f"({', '.join(terms[:5])}); de verificat de analist.")
    elif results:
        summary = f"{len(results)} rezultate despre „{entity}”, fără mențiuni de fraudă."
    else:
        summary = f"Nicio mențiune în presă sau pe forumuri despre „{entity}”."
    return Interp(data, summary, signal)


# ---------------------------------------------------------------- tool-uri


@tool("web_search", zones=("aml",), group="osint-ro")
async def web_search(query: str, n: int = 8) -> ToolResult:
    """Căutare web (Serper → Brave → Tavily → Exa → DuckDuckGo); rezultate normalizate {title, url, snippet, source, date}."""
    query = normalize_ro(query).strip()
    n = max(1, min(int(n), 20))
    args = {"query": query, "n": n}
    if not query:
        return failure("web_search", args, "Interogare goală.", error="query gol")
    if (why := privacy_violation(query)) is not None:
        return failure("web_search", args, f"Interogarea a fost refuzată: {why} (doar identificatori publici ai beneficiarului).",
                       error=f"confidențialitate: {why}")

    async def fetch() -> tuple[Any, str | None]:
        raw = await search_chain(query, n, "web")
        return raw, None

    return await run_source("web_search", args, key=f"web|{n}|{fold(query)}", fetch=fetch, build=_build_web,
                            ttl_s=SEARCH_TTL_S, label="Căutarea web", synthetic=is_synthetic_target(query),
                            fixture_keys=[query], fixture_query=query)


def news_query(entity: str) -> str:
    return f'"{entity}" ({" OR ".join(NEWS_QUERY_TERMS)})'


# Forma juridică la finalul numelui (sensibil la majuscule, ca „sa" din text să nu conteze)
LEGAL_FORM_END = re.compile(r"(?:^|\s)(?:S\.?\s?R\.?\s?L\.?(?:-D)?|S\.?\s?A\.?|SRL-D|PFA|I\.?I\.?|I\.?F\.?|SNC|SCS|SCA|"
                            r"LTD\.?|LLC|GMBH|GmbH|AG|INC\.?|Inc\.?|PLC|SPA|S\.p\.A\.|SARL|BV|B\.V\.|NV|N\.V\.)\s*$")
ORG_PREFIXES = ("asociatia", "fundatia", "universitatea", "spitalul", "primaria", "ministerul", "banca", "cooperativa",
                "institutul", "agentia", "autoritatea", "compania", "societatea", "grupul", "clinica", "federatia")


def entity_kind(entity: str) -> str:
    """„domeniu", „telefon", „cui", „firma" sau „altceva" (de exemplu numele unei persoane)."""
    text = normalize_ro(entity).strip()
    if split_domain(text) is not None and " " not in text:
        return "domeniu"
    if normalize_phone(text):
        return "telefon"
    if re.fullmatch(r"(?:RO\s?)?\d{2,10}", text, re.I):
        return "cui"
    if LEGAL_FORM_END.search(text) or fold(text).split(" ", 1)[0] in ORG_PREFIXES:
        return "firma"
    return "altceva"


@tool("news_search", zones=("aml",), group="osint-ro")
async def news_search(entity: str, n: int = 8) -> ToolResult:
    """Presă și forumuri românești despre o entitate a beneficiarului (firmă cu formă juridică, domeniu, telefon, CUI), cu termeni de fraudă."""
    entity = normalize_ro(entity).strip()
    n = max(1, min(int(n), 20))
    args = {"entity": entity, "n": n}
    if not entity:
        return failure("news_search", args, "Entitate goală.", error="entity gol")
    if (why := privacy_violation(entity)) is not None:
        return failure("news_search", args, f"Căutarea a fost refuzată: {why} (doar identificatori publici ai beneficiarului).",
                       error=f"confidențialitate: {why}")
    synthetic = is_synthetic_target(entity)
    if not synthetic and entity_kind(entity) == "altceva":
        return failure("news_search", args,
                       "Căutarea de presă acceptă doar firme (cu formă juridică), domenii, telefoane sau CUI-uri; "
                       "numele persoanelor fizice nu se caută pe web.", error="entitate nepermisă")
    query = news_query(entity)

    async def fetch() -> tuple[Any, str | None]:
        attempts: list[dict[str, Any]] = []
        try:
            news = await search_chain(query, n, "news")
            if news["results"]:
                return news, None
            attempts = news["attempts"]
        except SourceError as exc:
            attempts = [{"provider": "news", "status": "eroare", "detail": str(exc)[:200]}]
        web = await search_chain(query, n, "web")
        web["attempts"] = attempts + web["attempts"]
        return web, None

    return await run_source("news_search", args, key=f"news|{n}|{fold(entity)}", fetch=fetch, build=_build_news,
                            ttl_s=SEARCH_TTL_S, label="Căutarea de presă", synthetic=synthetic,
                            fixture_keys=[entity], fixture_query=entity)

