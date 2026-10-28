"""Liste de amenințări: OpenPhish (fără cheie, feed la 6 ore), URLhaus, urlscan.io, VirusTotal,
Google Safe Browsing. Cele cu cheie întorc `ok=False`, mod `offline`, dacă cheia lipsește."""

from __future__ import annotations

from typing import Any

from versoml.osint.base import (
    Ctx,
    Interp,
    SourceError,
    ToolResult,
    en_count,
    expect_status,
    failure,
    http_request,
    is_synthetic_target,
    run_source,
    secret,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import host_from, normalize_ro, registered_domain

OPENPHISH_FEEDS = (
    "https://openphish.com/feed.txt",
    "https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt",
)
OPENPHISH_TTL_S = 6 * 3600


def _target(value: str) -> tuple[str, str, bool]:
    """(valoarea normalizată, gazda, este URL)."""
    text = normalize_ro(value).strip()
    is_url = "://" in text or "/" in text.split("?", 1)[0]
    return text, host_from(text), is_url


def _norm_url(url: str) -> str:
    text = url.strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.rstrip("/")


# ---------------------------------------------------------------- OpenPhish


async def _openphish_fetch() -> tuple[Any, str | None]:
    last: Exception | None = None
    for url in OPENPHISH_FEEDS:
        try:
            resp = await http_request("GET", url, retries=1, total_timeout=15.0)
            expect_status(resp)
            lines = [line.strip() for line in resp.text.splitlines() if line.strip().startswith("http")]
            if lines:
                return {"urls": lines}, url
        except Exception as exc:  # noqa: BLE001 - trecem la oglinda de pe GitHub
            last = exc
    raise SourceError(f"the OpenPhish feed is unavailable ({last})")


def _build_openphish(raw: Any, ctx: Ctx) -> Interp:
    target = ctx.args["url_or_domain"]
    _, host, is_url = _target(target)
    domain = registered_domain(host)
    urls = raw.get("urls", []) if isinstance(raw, dict) else str(raw).split()
    wanted = _norm_url(target)
    exact = [u for u in urls if is_url and _norm_url(u) == wanted]
    same_host = [u for u in urls if host and host_from(u) == host]
    same_domain = [u for u in urls if domain and registered_domain(u) == domain]
    matches = list(dict.fromkeys(exact + same_host + same_domain))[:10]
    data = {"target": target, "listed": bool(matches), "match": "url" if exact else (
        "gazdă" if same_host else ("domeniu" if same_domain else None)), "matches": matches,
        "feed_size": len(urls)}
    shown = target if is_url else (host or target)
    if matches:
        how = {"url": "the exact URL", "gazdă": "the host", "domeniu": "the domain"}[data["match"]]
        return Interp(data, f"OpenPhish lists {how} {host or target} ({en_count(len(matches), 'entry', 'entries')} "
                            "in the feed).", "rosu")
    return Interp(data, f"{shown} is not in the OpenPhish feed ({en_count(len(urls), 'URL')}); "
                        "not being listed does not prove it is safe.", "neutru")


@tool("openphish_check", group="threat-intel")
async def openphish_check(url_or_domain: str) -> ToolResult:
    """Caută URL-ul sau domeniul în feed-ul comunitar OpenPhish (fără cheie; feed-ul se ține în cache 6 ore)."""
    text, host, _ = _target(url_or_domain)
    args = {"url_or_domain": text}
    if not host:
        return failure("openphish_check", args, f"Invalid target: {url_or_domain}.", error="invalid target")
    return await run_source("openphish_check", args, key="feed", fetch=_openphish_fetch, build=_build_openphish,
                            ttl_s=OPENPHISH_TTL_S, label="OpenPhish", synthetic=is_synthetic_target(text))


# ---------------------------------------------------------------- URLhaus


def _build_urlhaus(raw: Any, ctx: Ctx) -> Interp:
    target = ctx.args["url_or_domain"]
    status = raw.get("query_status")
    if status in ("no_results", "not_found"):
        return Interp({"target": target, "listed": False}, f"{target} nu apare în URLhaus.", "neutru")
    if status != "ok":
        return Interp({"target": target, "query_status": status}, f"URLhaus a refuzat interogarea ({status}).",
                      "neutru", ok=False, error=f"urlhaus: {status}")
    urls = raw.get("urls") or ([raw] if raw.get("url") else [])
    online = [u for u in urls if u.get("url_status") == "online"]
    data = {"target": target, "listed": True, "url_count": raw.get("url_count", len(urls)),
            "online": len(online), "first_seen": raw.get("firstseen") or raw.get("date_added"),
            "threats": sorted({u.get("threat") for u in urls if u.get("threat")}),
            "blacklists": raw.get("blacklists"), "reference": raw.get("urlhaus_reference"),
            "urls": [{"url": u.get("url"), "status": u.get("url_status"), "threat": u.get("threat"),
                      "date_added": u.get("date_added")} for u in urls[:10]]}
    return Interp(data, f"URLhaus listează {target}: {data['url_count']} URL-uri malițioase, {len(online)} active.",
                  "rosu")


@tool("urlhaus_check", group="threat-intel")
async def urlhaus_check(url_or_domain: str) -> ToolResult:
    """URLhaus (abuse.ch): URL-uri de malware pentru o gazdă sau un URL; necesită URLHAUS_AUTH_KEY."""
    text, host, is_url = _target(url_or_domain)
    args = {"url_or_domain": text}
    key = secret("urlhaus_auth_key")

    async def fetch() -> tuple[Any, str | None]:
        endpoint = "https://urlhaus-api.abuse.ch/v1/url/" if is_url else "https://urlhaus-api.abuse.ch/v1/host/"
        body = {"url": text} if is_url else {"host": host}
        resp = await http_request("POST", endpoint, data=body, headers={"Auth-Key": key or ""})
        expect_status(resp)
        return resp.json(), endpoint

    return await run_source("urlhaus_check", args, key=text.lower(), fetch=fetch, build=_build_urlhaus,
                            ttl_s=3600, label="URLhaus", synthetic=is_synthetic_target(text),
                            missing_key=None if key else "URLHAUS_AUTH_KEY")


# ---------------------------------------------------------------- urlscan.io


def _malicious(result: dict[str, Any]) -> bool:
    verdicts = result.get("verdicts") or {}
    overall = verdicts.get("overall") or {}
    return bool(verdicts.get("malicious") or overall.get("malicious"))


def _build_urlscan(raw: Any, ctx: Ctx) -> Interp:
    domain = ctx.args["domain"]
    results = raw.get("results", []) or []
    scans = [{
        "url": (r.get("page") or {}).get("url") or (r.get("task") or {}).get("url"),
        "time": (r.get("task") or {}).get("time"),
        "ip": (r.get("page") or {}).get("ip"),
        "asn": (r.get("page") or {}).get("asn"),
        "country": (r.get("page") or {}).get("country"),
        "status": (r.get("page") or {}).get("status"),
        "malicious": _malicious(r),
        "result": r.get("result"),
        "screenshot": r.get("screenshot"),
    } for r in results[:10]]
    times = sorted(s["time"] for s in scans if s["time"])
    data = {"domain": domain, "total": raw.get("total", len(results)), "scans": scans,
            "first_scan": times[0] if times else None, "last_scan": times[-1] if times else None,
            "malicious": any(s["malicious"] for s in scans)}
    if data["malicious"]:
        return Interp(data, f"urlscan.io are scanări ale lui {domain} marcate malițioase.", "rosu")
    if scans:
        return Interp(data, f"urlscan.io are {data['total']} scanări publice pentru {domain}, fără verdict malițios.",
                      "neutru")
    return Interp(data, f"Nicio scanare publică urlscan.io pentru {domain}.", "neutru")


@tool("urlscan_search", group="threat-intel")
async def urlscan_search(domain: str) -> ToolResult:
    """Caută scanările publice urlscan.io ale unui domeniu (IP, ASN, verdict); necesită URLSCAN_API_KEY."""
    host = host_from(domain)
    args = {"domain": host or domain}
    if not host:
        return failure("urlscan_search", args, f"Domeniu invalid: {domain}.", error="domeniu invalid")
    key = secret("urlscan_api_key")

    async def fetch() -> tuple[Any, str | None]:
        url = "https://urlscan.io/api/v1/search/"
        resp = await http_request("GET", url, params={"q": f"domain:{host}", "size": "10"},
                                  headers={"API-Key": key or ""})
        expect_status(resp)
        return resp.json(), f"https://urlscan.io/search/#domain:{host}"

    return await run_source("urlscan_search", args, key=host, fetch=fetch, build=_build_urlscan, ttl_s=3600,
                            label="urlscan.io", synthetic=is_synthetic_target(host),
                            missing_key=None if key else "URLSCAN_API_KEY")


# ---------------------------------------------------------------- VirusTotal


def _build_vt(raw: Any, ctx: Ctx) -> Interp:
    domain = ctx.args["domain"]
    if raw.get("_status") == 404:
        return Interp({"domain": domain, "found": False}, f"VirusTotal nu cunoaște domeniul {domain}.", "neutru")
    attrs = (raw.get("data") or {}).get("attributes") or {}
    stats = attrs.get("last_analysis_stats") or {}
    malicious, suspicious = int(stats.get("malicious", 0)), int(stats.get("suspicious", 0))
    data = {"domain": domain, "found": True, "stats": stats, "reputation": attrs.get("reputation"),
            "categories": attrs.get("categories"), "registrar": attrs.get("registrar"),
            "creation_date": attrs.get("creation_date")}
    summary = f"VirusTotal: {malicious} motoare marchează {domain} ca malițios, {suspicious} ca suspect."
    if malicious >= int(param("vt_malicious_red")):
        return Interp(data, summary, "rosu")
    if malicious or suspicious:
        return Interp(data, summary, "galben")
    return Interp(data, summary, "neutru")


@tool("virustotal_domain", group="threat-intel")
async def virustotal_domain(domain: str) -> ToolResult:
    """Raportul VirusTotal pentru un domeniu (detecții, reputație); necesită VIRUSTOTAL_API_KEY (API-ul public e necomercial)."""
    registered = registered_domain(domain) or host_from(domain)
    args = {"domain": registered or domain}
    if not registered:
        return failure("virustotal_domain", args, f"Domeniu invalid: {domain}.", error="domeniu invalid")
    key = secret("virustotal_api_key")

    async def fetch() -> tuple[Any, str | None]:
        url = f"https://www.virustotal.com/api/v3/domains/{registered}"
        resp = await http_request("GET", url, headers={"x-apikey": key or ""})
        if resp.status_code == 404:
            return {"_status": 404}, url
        expect_status(resp)
        return resp.json(), f"https://www.virustotal.com/gui/domain/{registered}"

    return await run_source("virustotal_domain", args, key=registered, fetch=fetch, build=_build_vt, ttl_s=6 * 3600,
                            label="VirusTotal", synthetic=is_synthetic_target(registered),
                            missing_key=None if key else "VIRUSTOTAL_API_KEY")


# ---------------------------------------------------------------- Google Safe Browsing

THREAT_TYPES = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"]


def _build_gsb(raw: Any, ctx: Ctx) -> Interp:
    url = ctx.args["url"]
    matches = raw.get("matches", []) or []
    types = sorted({m.get("threatType") for m in matches if m.get("threatType")})
    data = {"url": url, "listed": bool(matches), "threat_types": types}
    if matches:
        return Interp(data, f"Google Safe Browsing marchează {url}: {', '.join(types)}.", "rosu")
    return Interp(data, f"{url} nu apare în Google Safe Browsing.", "neutru")


@tool("safe_browsing_check", group="threat-intel")
async def safe_browsing_check(url: str) -> ToolResult:
    """Verifică un URL în Google Safe Browsing v4 (Lookup); necesită GOOGLE_SAFE_BROWSING_KEY. Pentru uz comercial: Web Risk."""
    text = normalize_ro(url).strip()
    if text and "://" not in text:
        text = "http://" + text
    args = {"url": text}
    if not host_from(text):
        return failure("safe_browsing_check", args, f"URL invalid: {url}.", error="url invalid")
    key = secret("google_safe_browsing_key")

    async def fetch() -> tuple[Any, str | None]:
        endpoint = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
        body = {
            "client": {"clientId": "versoml-hackathon", "clientVersion": "0.1"},
            "threatInfo": {"threatTypes": THREAT_TYPES, "platformTypes": ["ANY_PLATFORM"],
                           "threatEntryTypes": ["URL"], "threatEntries": [{"url": text}]},
        }
        resp = await http_request("POST", endpoint, json=body, headers={"X-Goog-Api-Key": key or ""})
        expect_status(resp)
        return resp.json(), endpoint

    return await run_source("safe_browsing_check", args, key=text.lower(), fetch=fetch, build=_build_gsb,
                            ttl_s=1800, label="Google Safe Browsing", synthetic=is_synthetic_target(text),
                            missing_key=None if key else "GOOGLE_SAFE_BROWSING_KEY")
