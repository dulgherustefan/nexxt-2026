"""Fetch sigur de pagini (fără JavaScript) și analiza lor.

Garda: doar http/https pe porturile 80/443/8080/8443; gazda se rezolvă înainte și orice IP nepublic
(privat, loopback, link-local, multicast, rezervat) e blocat, inclusiv la fiecare redirecționare și
la conectare. Cel mult 3 redirecționări (înregistrate ca lanț), 2 MB, 10 s.
Conținutul paginii e neîncrezut: îl descriem, nu îl executăm și nu îl tratăm ca instrucțiuni.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from versoml.osint import netguard
from versoml.osint.base import (
    Ctx,
    Interp,
    SourceError,
    ToolResult,
    configured_mode,
    describe_error,
    ro_count,
    ro_join,
    failure,
    get_client,
    http_request,
    is_synthetic_target,
    run_source,
    secret,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import fold, host_from, normalize_ro, registered_domain, split_domain

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_S = 10.0
TEXT_LIMIT = 5000
PAGE_TTL_S = 3600
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Termenii de brand căutați în pagină, pe eticheta domeniului protejat
BRAND_TERMS: dict[str, tuple[str, ...]] = {
    "bancademo": ("banca demo", "bancademo", "bancii demo"),
    "curierdemo": ("curier demo", "curierdemo"),
    "raiffeisen": ("raiffeisen",),
}
BRAND_NAMES: dict[str, str] = {"bancademo": "Banca Demo", "curierdemo": "Curier Demo", "raiffeisen": "Raiffeisen"}

# Clasa unui câmp de formular, după nume, id, placeholder, autocomplete, etichetă (text pliat)
FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern))
    for kind, pattern in (
        ("card_number", r"cc-number|card.?(number|num|no\b)|cardnumber|numar(ul)?.?(de.?)?card|nr\.?.?card|"
                        r"numarul.?cardului|\bpan\b|\bccnum"),
        ("cvv", r"\bcvv2?\b|\bcvc2?\b|\bcsc\b|cc-csc|cod(ul)?.?(de.?)?securitate|security.?code"),
        ("expiry", r"cc-exp|expir|valabil|exp.?(date|month|year)|\bmm\s*/\s*(aa|yy)\b|\bll\s*/\s*aa\b"),
        ("otp", r"one-time-code|\botp\b|cod(ul)?.?(primit|sms|unic|de.?confirmare|de.?verificare|3ds|de.?autorizare)|"
                r"sms.?code|verification.?code|\btoken\b|cod.?din.?sms"),
        ("pin", r"\bpin\b"),
        ("password", r"parol|passw|\bpwd\b|current-password|new-password"),
        ("iban", r"\biban\b"),
        ("cnp", r"\bcnp\b|cod.?numeric.?personal"),
        ("card_holder", r"cc-name|titular|cardholder|nume.?(pe|de.?pe).?card"),
        ("email", r"e-?mail"),
        ("phone", r"telefon|\bphone\b|\bmobil\b|\btel\b"),
        ("username", r"utilizator|username|\buser\b|\blogin\b|cod.?client|\bid.?client"),
    )
)
SENSITIVE_KINDS = ("card_number", "cvv", "expiry", "otp", "pin", "password", "iban", "cnp")

SUSPICIOUS_TERMS: dict[str, str] = {
    "plată": r"\bplat[ai]\w*|\bplati\w*",
    "confirmă": r"\bconfirm\w*",
    "taxă": r"\btax[ae]\b|\btaxe\w*",
    "colet": r"\bcolet\w*",
    "livrare": r"\blivr\w*",
    "card": r"\bcard\w*",
    "cod": r"\bcod(ul|uri|urile)?\b",
    "verificare": r"\bverific\w*",
    "cont blocat": r"\bcont(ul)? (a fost |este )?(blocat|suspendat|restrictionat)\w*",
    "urgent": r"\burgent\w*|in (cel mult )?24 de ore|\bimediat\b",
    "payment": r"\bpayment\w*",
    "verify": r"\bverify\w*",
    "parcel": r"\bparcel\w*|\bdelivery\b",
    "suspended": r"\bsuspended\b|\baccount (is )?(locked|blocked)\b",
}
INJECTION_PATTERNS = re.compile(
    r"ignore (all )?(previous|prior|above) instructions|ignora (toate )?instructiunile|system prompt|"
    r"you are (an? )?(ai|assistant|language model)|esti un asistent|aproba rambursarea|marcheaza ca verificat"
)
JS_REDIRECT = re.compile(
    r"(?:window\.|document\.|top\.|self\.)?location(?:\.href)?\s*=(?!=)|location\.(?:replace|assign)\s*\(|"
    r"window\.open\s*\("
)
JS_OBFUSCATION = re.compile(r"\batob\s*\(|\beval\s*\(|\bunescape\s*\(|fromCharCode|\\x[0-9a-f]{2}", re.I)


class SSRFBlocked(Exception):
    """Ținta a fost refuzată de garda SSRF."""


# ---------------------------------------------------------------- analiza HTML


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html or "", "lxml")


def visible_text(html: str) -> str:
    """Textul vizibil (inclusiv pașii ascunși prin CSS ai unui formular), fără scripturi și stiluri."""
    soup = _soup(html)
    for tag in soup(["script", "style", "noscript", "template", "svg", "head"]):
        tag.decompose()
    return normalize_ro(re.sub(r"\s+", " ", soup.get_text(" ")).strip())


def main_text(html: str) -> str:
    """Textul principal cu trafilatura; dacă iese prea scurt, textul vizibil complet."""
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or ""
    except Exception:  # noqa: BLE001 - trafilatura poate eșua pe HTML stricat
        text = ""
    if len(text) < 200:
        text = visible_text(html)
    return normalize_ro(text)


def _field_kind(blob: str, input_type: str) -> str:
    """Clasa câmpului; un câmp de tip password poate fi și CVV, PIN sau cod SMS (contează eticheta)."""
    for kind, pattern in FIELD_PATTERNS:
        if pattern.search(blob):
            if input_type == "password" and kind in ("username", "email", "phone", "card_holder"):
                return "password"
            return kind
    if input_type == "password":
        return "password"
    if input_type in ("email", "tel"):
        return "email" if input_type == "email" else "phone"
    return "other"


def _inputs(container, soup) -> list[dict[str, Any]]:
    labels = {lbl.get("for"): lbl.get_text(" ", strip=True) for lbl in soup.find_all("label") if lbl.get("for")}
    fields = []
    for el in container.find_all(["input", "select", "textarea"]):
        input_type = (el.get("type") or ("select" if el.name == "select" else "text")).lower()
        if input_type in ("hidden", "submit", "button", "image", "reset"):
            continue
        attrs = [el.get(a) or "" for a in ("name", "id", "placeholder", "autocomplete", "aria-label", "title")]
        blob = fold(" ".join([*attrs, labels.get(el.get("id"), "")]))
        fields.append({
            "name": el.get("name") or el.get("id") or "",
            "type": input_type,
            "placeholder": normalize_ro(el.get("placeholder") or ""),
            "label": normalize_ro(labels.get(el.get("id"), "")),
            "kind": _field_kind(blob, input_type),
        })
    return fields


def extract_forms(html: str, base_url: str) -> list[dict[str, Any]]:
    """Formularele (și câmpurile din afara lor, ca pseudo-formular) cu clasa fiecărui câmp."""
    soup = _soup(html)
    page_domain = registered_domain(base_url)
    forms = []
    for form in soup.find_all("form"):
        action = urljoin(base_url, form.get("action") or "")
        action_domain = registered_domain(action)
        fields = _inputs(form, soup)
        forms.append({
            "action": action,
            "method": (form.get("method") or "get").lower(),
            "external": bool(action_domain and page_domain and action_domain != page_domain),
            "inputs": fields,
            "flags": sorted({f["kind"] for f in fields if f["kind"] in SENSITIVE_KINDS}),
        })
    for form in soup.find_all("form"):
        form.decompose()
    loose = _inputs(soup, soup)
    if loose:
        forms.append({"action": None, "method": None, "external": False, "inputs": loose,
                      "flags": sorted({f["kind"] for f in loose if f["kind"] in SENSITIVE_KINDS}),
                      "outside_form": True})
    return forms


def brand_mentions(text: str) -> dict[str, int]:
    folded = fold(text)
    counts = {}
    for brand, terms in BRAND_TERMS.items():
        n = sum(len(re.findall(rf"(?<![a-z]){re.escape(term)}(?![a-z])", folded)) for term in set(terms))
        if n:
            counts[brand] = n
    return counts


def suspicious_keywords(text: str) -> dict[str, int]:
    folded = fold(text)
    found = {}
    for label, pattern in SUSPICIOUS_TERMS.items():
        n = len(re.findall(pattern, folded))
        if n:
            found[label] = n
    return found


def analyze_html(html: str, url: str) -> dict[str, Any]:
    """Tot ce se poate spune despre pagină fără să rulăm JavaScript."""
    soup = _soup(html)
    title = normalize_ro(soup.title.get_text(" ", strip=True)) if soup.title else ""
    page_domain = registered_domain(url)
    scripts_ext, js_hints = [], set()
    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            absolute = urljoin(url, src)
            if registered_domain(absolute) and registered_domain(absolute) != page_domain:
                scripts_ext.append(absolute)
        else:
            code = script.string or script.get_text() or ""
            if JS_REDIRECT.search(code):
                js_hints.add("redirecționare JS (location/window.open)")
            if JS_OBFUSCATION.search(code):
                js_hints.add("cod ascuns (atob/eval/escape)")
    for el in soup.find_all(attrs={"onload": True}):
        if JS_REDIRECT.search(el.get("onload") or ""):
            js_hints.add("redirecționare JS în onload")
    refresh = None
    for meta in soup.find_all("meta"):
        if (meta.get("http-equiv") or "").lower() == "refresh":
            match = re.search(r"url\s*=\s*['\"]?([^'\";]+)", meta.get("content") or "", re.I)
            refresh = urljoin(url, match.group(1).strip()) if match else (meta.get("content") or "")
    alts = " ".join(img.get("alt") or "" for img in soup.find_all("img"))
    text = visible_text(html)
    forms = extract_forms(html, url)
    asks = sorted({flag for form in forms for flag in form["flags"]})
    brands = brand_mentions(f"{title} {text} {alts}")
    keywords = suspicious_keywords(f"{title} {text}")
    return {
        "title": title,
        "text": main_text(html)[:TEXT_LIMIT],
        "text_chars": len(text),
        "forms": forms,
        "asks": asks,
        "asks_card": any(k in asks for k in ("card_number", "cvv", "expiry")),
        "asks_otp": "otp" in asks,
        "asks_password": "password" in asks or "pin" in asks,
        "external_form_action": any(f.get("external") for f in forms),
        "brands": brands,
        "external_scripts": sorted(set(scripts_ext))[:20],
        "meta_refresh": refresh,
        "js_redirect_hints": sorted(js_hints),
        "keywords": keywords,
        "injection_suspected": bool(INJECTION_PATTERNS.search(fold(text))),
        "page_domain": page_domain,
    }


def _protected_registered() -> set[str]:
    domains = list(param("protected_domains")) + list(param("allowlist_domains"))
    return {registered_domain(d) or d for d in domains}


def interpret_page(data: dict[str, Any]) -> tuple[str, str]:
    """Semnalul paginii: roșu dacă cere card/OTP și folosește un brand protejat, pe alt domeniu."""
    domain = data.get("page_domain") or ""
    on_brand = domain in _protected_registered()
    data["on_protected_domain"] = on_brand
    brands = [BRAND_NAMES.get(b, b) for b in data.get("brands", {})]
    asks = data.get("asks", [])
    wants = []
    if data.get("asks_card"):
        wants.append("datele cardului")
    if data.get("asks_otp"):
        wants.append("codul primit prin SMS")
    if data.get("asks_password"):
        wants.append("parola")
    wanted = ro_join(wants) or "date sensibile"
    under = (f"sub brandul {brands[0]}, deși nu e pe domeniul acestuia" if len(brands) == 1
             else f"sub brandurile {ro_join(brands)}, deși nu e pe domeniile lor")
    if on_brand:
        return f"Pagina e pe domeniul protejat {domain}.", "verde"
    if (data.get("asks_card") or data.get("asks_otp")) and brands:
        extra = "; formularul trimite datele pe alt domeniu" if data.get("external_form_action") else ""
        return f"Pagina de pe {domain} cere {wanted}, {under}{extra}.", "rosu"
    if data.get("asks_card") or data.get("asks_otp"):
        return f"Pagina de pe {domain} cere {wanted}, fără brand protejat vizibil.", "galben"
    if data.get("asks_password") and brands:
        return f"Pagina de pe {domain} cere {wanted}, {under}.", "galben"
    if data.get("injection_suspected"):
        return f"Pagina de pe {domain} conține text care pare o instrucțiune pentru un sistem AI.", "galben"
    if data.get("meta_refresh") or data.get("js_redirect_hints"):
        return f"Pagina de pe {domain} redirecționează automat vizitatorul.", "galben"
    if asks:
        return f"Pagina de pe {domain} are câmpuri sensibile ({', '.join(asks)}).", "neutru"
    return f"Pagina de pe {domain} nu cere date sensibile.", "neutru"


# ---------------------------------------------------------------- fetch


def _decode(body: bytes, response_charset: str | None) -> str:
    charset = response_charset
    if not charset:
        match = re.search(rb"<meta[^>]+charset=['\"]?([a-zA-Z0-9_-]+)", body[:4096], re.I)
        charset = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def _read_capped(response: httpx.Response) -> tuple[bytes, bool]:
    buf = bytearray()
    async for chunk in response.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            del buf[MAX_BYTES:]
            return bytes(buf), True
    return bytes(buf), False


async def _fetch_live(url: str) -> dict[str, Any]:
    """GET fără JavaScript, cu redirecționările urmate manual și verificate una câte una."""
    client = get_client()
    chain: list[dict[str, Any]] = []
    current = url
    async with asyncio.timeout(FETCH_TIMEOUT_S):
        for hop in range(MAX_REDIRECTS + 1):
            try:
                await netguard.assert_url_allowed(current)
            except netguard.BlockedAddressError as exc:
                return {"url": url, "final_url": current, "redirects": chain, "error": f"blocat: {exc}"}
            request = client.build_request("GET", current, headers={
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.6",
            })
            response = await client.send(request, stream=True)
            try:
                location = response.headers.get("location")
                if response.status_code in REDIRECT_STATUSES and location:
                    target = urljoin(str(response.url), location)
                    chain.append({"url": current, "status": response.status_code, "location": target})
                    if hop >= MAX_REDIRECTS:
                        return {"url": url, "final_url": current, "redirects": chain,
                                "error": f"prea multe redirecționări (peste {MAX_REDIRECTS})"}
                    current = target
                    continue
                body, truncated = await _read_capped(response)
                content_type = response.headers.get("content-type", "")
                return {
                    "url": url,
                    "final_url": str(response.url),
                    "status": response.status_code,
                    "content_type": content_type,
                    "server": response.headers.get("server"),
                    "redirects": chain,
                    "html": _decode(body, response.charset_encoding),
                    "bytes": len(body),
                    "truncated": truncated,
                }
            finally:
                await response.aclose()
    raise SourceError("lanț de redirecționări neterminat")  # pragma: no cover


async def jina_markdown(url: str) -> str:
    """Varianta markdown prin Jina Reader (randată la ei); cheia e opțională."""
    headers = {"X-Return-Format": "markdown"}
    key = secret("jina_api_key")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = await http_request("GET", f"https://r.jina.ai/{url}", headers=headers, total_timeout=20.0, retries=1)
    if resp.status_code != 200:
        raise SourceError(f"Jina HTTP {resp.status_code}")
    return normalize_ro(resp.text)[:8000]


def _build_page(raw: dict[str, Any], ctx: Ctx, holder: dict[str, Any]) -> Interp:
    url = raw.get("url") or ctx.args.get("url", "")
    final_url = raw.get("final_url") or url
    base = {"url": url, "final_url": final_url, "status": raw.get("status"), "redirects": raw.get("redirects", []),
            "content_type": raw.get("content_type", "text/html"), "truncated": bool(raw.get("truncated"))}
    if raw.get("error"):
        hops = ro_count(len(base["redirects"]), "redirecționare", "redirecționări")
        return Interp(base, f"Pagina nu a fost descărcată: {raw['error']} (după {hops}).",
                      "galben" if "blocat" in raw["error"] else "neutru", ok=False, error=raw["error"])
    html = raw.get("html") or ""
    holder["html"] = html
    holder["final_url"] = final_url
    encoded = html.encode("utf-8", "ignore")
    base.update({"html_bytes": raw.get("bytes", len(encoded)), "html_sha256": hashlib.sha256(encoded).hexdigest()})
    if "html" not in (base["content_type"] or "html") and "xml" not in (base["content_type"] or ""):
        return Interp(base, f"Resursa nu e o pagină HTML ({base['content_type']}).", "neutru")
    data = {**base, **analyze_html(html, final_url)}
    summary, signal = interpret_page(data)
    data["similarity"] = _similarity(html)
    score = (data["similarity"] or {}).get("score")
    if score is not None and score >= float(param("page_similarity_red")) and not data["on_protected_domain"]:
        summary += f" Seamănă {round(score * 100)}% cu pagina de autentificare Banca Demo."
        signal = "rosu"
    if base["redirects"]:
        hops = ro_count(len(base["redirects"]), "redirecționare", "redirecționări")
        summary += f" {hops[0].upper()}{hops[1:]} înainte de pagină."
    return Interp(data, summary, signal)


def _similarity(html: str, reference: str = "bancademo_login") -> dict[str, Any] | None:
    """M4 calculat direct aici, ca HTML-ul (neîncrezut, mare) să nu mai circule între agenți."""
    try:
        from versoml.osint.page_similarity import compare

        result = compare(html, reference)
    except Exception:  # noqa: BLE001 - M4 e un plus; fetch-ul rămâne valid fără el
        return None
    return {"reference": reference, "score": result["score"], "components": result["components"]}


def _url_keys(url: str) -> list[str]:
    host = host_from(url)
    stripped = re.sub(r"^[a-z]+://", "", url.strip(), flags=re.I)
    path_only = stripped.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    keys = [stripped, path_only, host]
    parts = split_domain(host)
    if parts:
        keys.append(parts.registered)
    return list(dict.fromkeys(k for k in keys if k))


def normalize_url(url: str) -> str:
    url = normalize_ro(url).strip().strip("<>\"'")
    if url and "://" not in url:
        url = "https://" + url
    return url


async def fetch_with_html(url: str, reader: bool = False) -> tuple[ToolResult, str | None]:
    """Ca `fetch_page`, dar întoarce și HTML-ul (pentru M4); HTML-ul nu intră în ToolResult."""
    url = normalize_url(url)
    args: dict[str, Any] = {"url": url}
    if reader:
        args["reader"] = True
    try:
        parsed = httpx.URL(url)
        netguard.check_scheme_port(parsed.scheme, parsed.port)
    except (netguard.BlockedAddressError, httpx.InvalidURL, ValueError) as exc:
        return failure("fetch_page", args, f"URL refuzat: {exc}.", error=f"url refuzat: {exc}"), None
    synthetic = is_synthetic_target(url)
    if not synthetic and configured_mode() != "fixture":
        try:
            await netguard.assert_url_allowed(url)
        except netguard.UnresolvableHostError:
            pass  # lăsăm sursa să încerce; în modul auto cade pe cache
        except netguard.BlockedAddressError as exc:
            return failure("fetch_page", args, f"Adresa a fost blocată de garda SSRF: {exc}.",
                           error=f"ssrf: {exc}", signal="galben"), None
    holder: dict[str, Any] = {}

    async def fetch() -> tuple[Any, str | None]:
        raw = await _fetch_live(url)
        return raw, url

    page = await run_source("fetch_page", args, key=url, fetch=fetch,
                            build=lambda raw, ctx: _build_page(raw, ctx, holder),
                            ttl_s=PAGE_TTL_S, label="Pagina", synthetic=synthetic, fixture_keys=_url_keys(url))
    if reader and page.ok and page.mode in ("live", "cache") and not synthetic:
        try:
            page.data["markdown"] = await jina_markdown(url)
        except Exception as exc:  # noqa: BLE001 - markdown-ul e opțional
            page.data["markdown_error"] = describe_error(exc)
    return page, holder.get("html")


@tool("fetch_page", group="domain-intel")
async def fetch_page(url: str, reader: bool = False) -> ToolResult:
    """Descarcă sigur o pagină (fără JS, garda SSRF, ≤3 redirecționări, ≤2 MB) și descrie formularele, brandurile și semnalele de phishing."""
    page, _ = await fetch_with_html(url, reader=reader)
    return page
