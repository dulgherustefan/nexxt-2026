"""Inteligență despre domenii: RDAP (cu WHOIS ROTLD pentru .ro), DNS prin DoH, Certificate Transparency,
Wayback Machine și geolocalizarea IP-ului."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from versoml.osint.base import (
    Ctx,
    Interp,
    SourceError,
    ToolResult,
    en_ago,
    en_count,
    en_dt,
    expect_status,
    failure,
    fmt_age,
    fmt_dt,
    hours_since,
    http_request,
    is_synthetic_target,
    parse_dt,
    ro_count,
    ro_join,
    run_source,
    tool,
)
from versoml.osint.params import param
from versoml.osint.util import is_public_ip, is_test_net, normalize_ro, parse_ip, split_domain

DAY_H = 24.0
FREE_CA_MARKERS = ("let's encrypt", "lets encrypt", "zerossl", "buypass", "google trust services", "ca gratuit demo")
PRIVACY_MARKERS = re.compile(r"redacted|privacy|proxy|withheld|not disclosed|data protected|gdpr|masked|ascuns",
                             re.I)
HOSTING_HINTS = re.compile(r"hosting|cloud|vps|server|datacenter|data center|ovh|hetzner|digitalocean|amazon|aws|"
                           r"google|microsoft|azure|linode|akamai|vultr|contabo|leaseweb|m247|choopa", re.I)


def _domain_args(domain: str) -> tuple[str | None, dict[str, Any]]:
    parts = split_domain(domain)
    if parts is None:
        return None, {"domain": normalize_ro(domain).strip()}
    return parts.registered, {"domain": parts.registered}


def _age_signal(hours: float | None) -> str:
    if hours is None:
        return "neutru"
    days = hours / DAY_H
    if days < float(param("domain_age_red_days")):
        return "rosu"
    if days < float(param("domain_age_yellow_days")):
        return "galben"
    if days >= float(param("domain_age_green_days")):
        return "verde"
    return "neutru"


# ---------------------------------------------------------------- RDAP / WHOIS


def _vcard(entity: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    card = entity.get("vcardArray") or []
    if len(card) >= 2 and isinstance(card[1], list):
        for item in card[1]:
            if isinstance(item, list) and len(item) >= 4 and isinstance(item[3], str):
                out.setdefault(item[0], item[3])
    return out


def _entities(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for entity in node.get("entities", []) or []:
        found.append(entity)
        found.extend(_entities(entity))
    return found


def parse_rdap(raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    events = {e.get("eventAction"): e.get("eventDate") for e in raw.get("events", []) or []}
    created = parse_dt(events.get("registration"))
    registrar, abuse, privacy = None, {}, bool(raw.get("redacted"))
    for entity in _entities(raw):
        roles = entity.get("roles", []) or []
        card = _vcard(entity)
        if "registrar" in roles and registrar is None:
            registrar = card.get("fn")
        if "abuse" in roles:
            abuse = {"email": card.get("email", "").removeprefix("mailto:") or None,
                     "phone": card.get("tel", "").removeprefix("tel:") or None}
        if "registrant" in roles:
            blob = " ".join([card.get("fn", ""), card.get("org", "")] +
                            [r.get("title", "") for r in entity.get("remarks", []) or []])
            if PRIVACY_MARKERS.search(blob) or not card.get("fn"):
                privacy = True
    hours = hours_since(created, now)
    return {
        "domain": (raw.get("ldhName") or "").lower() or None,
        "created": created.isoformat() if created else None,
        "expires": events.get("expiration"),
        "last_changed": events.get("last changed"),
        "age_hours": hours,
        "age_days": round(hours / DAY_H, 2) if hours is not None else None,
        "registrar": registrar,
        "abuse_contact": abuse or None,
        "privacy_protected": privacy,
        "status": raw.get("status", []),
        "nameservers": sorted({(n.get("ldhName") or "").lower() for n in raw.get("nameservers", []) or []} - {""}),
        "source": "rdap",
    }


def parse_rotld_whois(text: str, now: datetime) -> dict[str, Any]:
    def field(name: str) -> str | None:
        match = re.search(rf"^\s*{name}:\s*(.+?)\s*$", text, re.M | re.I)
        return match.group(1) if match else None

    if re.search(r"no entries found", text, re.I):
        return {"registered": False, "source": "whois.rotld.ro"}
    reg = field("Registered On")
    created, before_2001 = None, False
    if reg and reg.lower().startswith("before"):
        before_2001 = True
        created = datetime(2001, 1, 1, tzinfo=timezone.utc)
    elif reg:
        created = parse_dt(reg)
    hours = hours_since(created, now)
    return {
        "domain": field("Domain Name"),
        "registered": True,
        "created": None if before_2001 else (created.isoformat() if created else None),
        "created_before_2001": before_2001,
        "age_hours": hours,
        "age_days": round(hours / DAY_H, 2) if hours is not None else None,
        "registrar": field("Registrar"),
        "status": [s.strip() for s in re.findall(r"^\s*Domain Status:\s*(.+)$", text, re.M)],
        "nameservers": sorted({n.strip().lower() for n in re.findall(r"^\s*Nameserver:\s*(\S+)", text, re.M)}),
        "privacy_protected": True,  # ROTLD nu publică titularul pe portul 43
        "source": "whois.rotld.ro",
    }


def _build_rdap(raw: Any, ctx: Ctx) -> Interp:
    domain = ctx.args["domain"]
    if isinstance(raw, dict) and raw.get("_whois"):
        data = parse_rotld_whois(raw["_whois"], ctx.now)
        if not data.get("registered"):
            return Interp(data, f"The domain {domain} is not in the ROTLD registry.", "galben")
    elif isinstance(raw, dict) and raw.get("_status") == 404:
        data = {"domain": domain, "registered": None, "source": "rdap"}
        return Interp(data, f"RDAP has no record for {domain} (not registered, or a TLD without RDAP).", "neutru")
    else:
        data = parse_rdap(raw, ctx.now)
    hours = data.get("age_hours")
    signal = _age_signal(hours)
    if data.get("created_before_2001"):
        summary = f"The domain {domain} was registered before 2001 (registrar: {data.get('registrar') or 'unknown'})."
    elif hours is None:
        summary = f"RDAP does not show when {domain} was registered."
    else:
        summary = (f"The domain {domain} was registered {en_ago(hours)} ({en_dt(parse_dt(data['created']))}) "
                   f"through {data.get('registrar') or 'an unknown registrar'}")
        summary += "; the registrant's details are hidden." if data.get("privacy_protected") else "."
    return Interp(data, summary, signal)


async def _rdap_fetch(domain: str) -> tuple[Any, str | None]:
    url = f"https://rdap.org/domain/{domain}"
    resp = await http_request("GET", url, headers={"Accept": "application/rdap+json, application/json"},
                              follow_redirects=True)
    if resp.status_code == 404:
        return {"_status": 404}, url
    expect_status(resp)
    return resp.json(), str(resp.url)


async def _whois_rotld(domain: str) -> tuple[Any, str | None]:
    reader, writer = await asyncio.wait_for(asyncio.open_connection("whois.rotld.ro", 43), timeout=6)
    try:
        writer.write(f"{domain}\r\n".encode("ascii"))
        await writer.drain()
        chunks = []
        async with asyncio.timeout(8):
            while chunk := await reader.read(4096):
                chunks.append(chunk)
                if sum(map(len, chunks)) > 65536:
                    break
    finally:
        writer.close()
    text = b"".join(chunks).decode("utf-8", "replace")
    if "Domain Name" not in text and "No entries" not in text:
        raise SourceError("răspuns WHOIS neașteptat")
    return {"_whois": text}, "whois://whois.rotld.ro"


@tool("rdap_domain", group="domain-intel")
async def rdap_domain(domain: str) -> ToolResult:
    """Data înregistrării domeniului (RDAP; WHOIS ROTLD pentru .ro), registrarul, contactul de abuz și vârsta în ore/zile."""
    registered, args = _domain_args(domain)
    if registered is None:
        return failure("rdap_domain", args, f"Invalid domain: {args['domain']}.", error="invalid domain")
    is_ro = registered.endswith(".ro")
    fetch = (lambda: _whois_rotld(registered)) if is_ro else (lambda: _rdap_fetch(registered))
    return await run_source("rdap_domain", args, key=registered, fetch=fetch, build=_build_rdap, ttl_s=86400,
                            label="WHOIS ROTLD" if is_ro else "RDAP", synthetic=is_synthetic_target(registered))


# ---------------------------------------------------------------- DNS


DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT")
DOH_PROVIDERS = (
    ("cloudflare", "https://cloudflare-dns.com/dns-query"),
    ("google", "https://dns.google/resolve"),
)


async def _doh_query(endpoint: str, name: str, rtype: str) -> dict[str, Any]:
    resp = await http_request("GET", endpoint, params={"name": name, "type": rtype},
                              headers={"Accept": "application/dns-json"}, total_timeout=6.0, retries=1)
    expect_status(resp)
    return resp.json()


async def _dnspython_query(name: str, rtype: str) -> dict[str, Any]:
    import dns.asyncresolver
    import dns.resolver

    try:
        answer = await dns.asyncresolver.resolve(name, rtype, lifetime=5)
    except dns.resolver.NXDOMAIN:
        return {"Status": 3}
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return {"Status": 0}
    return {"Status": 0, "Answer": [{"name": name, "data": r.to_text()} for r in answer]}


async def _dns_fetch(host: str) -> tuple[Any, str | None]:
    queries = [(host, t, t) for t in DNS_TYPES] + [(f"_dmarc.{host}", "TXT", "DMARC")]
    last_error: Exception | None = None
    for provider, endpoint in DOH_PROVIDERS:
        try:
            answers = await asyncio.gather(*(_doh_query(endpoint, n, t) for n, t, _ in queries))
            return {"provider": provider, "answers": {label: a for (_, _, label), a in zip(queries, answers)}}, endpoint
        except Exception as exc:  # noqa: BLE001 - încercăm următorul rezolvitor
            last_error = exc
    try:
        answers = await asyncio.gather(*(_dnspython_query(n, t) for n, t, _ in queries))
        return {"provider": "dnspython", "answers": {label: a for (_, _, label), a in zip(queries, answers)}}, None
    except Exception as exc:  # noqa: BLE001
        raise SourceError(f"DNS indisponibil ({last_error or exc})") from exc


def _records(answer: dict[str, Any]) -> list[str]:
    values = []
    for item in answer.get("Answer", []) or []:
        data = str(item.get("data", "")).strip()
        if data:
            values.append(data.strip('"').replace('" "', ""))
    return values


def _build_dns(raw: Any, ctx: Ctx) -> Interp:
    host = ctx.args["domain"]
    answers = raw.get("answers", {})
    nxdomain = answers.get("A", {}).get("Status") == 3 and answers.get("NS", {}).get("Status") == 3
    records = {t: _records(answers.get(t, {})) for t in DNS_TYPES}
    spf = [t for t in records["TXT"] if t.lower().startswith("v=spf1")]
    dmarc = [t for t in _records(answers.get("DMARC", {})) if t.lower().startswith("v=dmarc1")]
    data = {"domain": host, "provider": raw.get("provider"), "nxdomain": nxdomain, **records,
            "spf": spf[0] if spf else None, "dmarc": dmarc[0] if dmarc else None}
    if nxdomain:
        return Interp(data, f"Domeniul {host} nu există în DNS (NXDOMAIN): posibil deja suspendat.", "neutru")
    parts = []
    if records["A"]:
        parts.append("A: " + ", ".join(records["A"][:4]))
    if records["NS"]:
        parts.append("NS: " + ", ".join(r.rstrip(".") for r in records["NS"][:3]))
    missing = [label for label, value in (("MX", records["MX"]), ("SPF", spf), ("DMARC", dmarc)) if not value]
    summary = f"DNS {host}: " + ("; ".join(parts) or "fără înregistrări A/NS")
    summary += f"; fără {ro_join(missing)}." if missing else "; are MX, SPF și DMARC."
    strict_dmarc = bool(dmarc) and re.search(r"p\s*=\s*(reject|quarantine)", dmarc[0], re.I) is not None
    signal = "verde" if records["MX"] and spf and strict_dmarc else "neutru"
    return Interp(data, summary, signal)


@tool("dns_records", group="domain-intel")
async def dns_records(domain: str) -> ToolResult:
    """Înregistrările A/AAAA/MX/NS/TXT (plus SPF și DMARC) prin DNS-over-HTTPS (Cloudflare, Google), cu dnspython ca rezervă."""
    parts = split_domain(domain)
    if parts is None:
        return failure("dns_records", {"domain": domain}, f"Domeniu invalid: {domain}.", error="domeniu invalid")
    host = parts.host
    args = {"domain": host}
    return await run_source("dns_records", args, key=host, fetch=lambda: _dns_fetch(host), build=_build_dns,
                            ttl_s=3600, label="DNS", synthetic=is_synthetic_target(host),
                            fixture_keys=[host, parts.registered])


# ---------------------------------------------------------------- Certificate Transparency

CRT_TIMEOUT_S = 15.0


def _norm_crtsh(item: dict[str, Any]) -> dict[str, Any]:
    issuer = item.get("issuer_name") or ""
    org = re.search(r"O=([^,]+)", issuer)
    return {
        "id": str(item.get("id") or item.get("serial_number") or ""),
        "issuer": issuer,
        "issuer_org": (org.group(1).strip().strip('"') if org else issuer) or None,
        "names": sorted(set(str(item.get("name_value") or item.get("common_name") or "").lower().split())),
        "not_before": item.get("not_before"),
        "not_after": item.get("not_after"),
        "logged_at": item.get("entry_timestamp") or item.get("not_before"),
        "serial": item.get("serial_number"),
    }


def _norm_certspotter(item: dict[str, Any]) -> dict[str, Any]:
    issuer = item.get("issuer") or {}
    return {
        "id": str(item.get("id") or item.get("cert_sha256") or ""),
        "issuer": issuer.get("name") or "",
        "issuer_org": issuer.get("friendly_name") or None,
        "names": sorted({n.lower() for n in item.get("dns_names", []) or []}),
        "not_before": item.get("not_before"),
        "not_after": item.get("not_after"),
        "logged_at": item.get("not_before"),
        "serial": None,
    }


async def _crtsh(domain: str) -> list[dict[str, Any]]:
    resp = await http_request("GET", "https://crt.sh/", params={"q": domain, "output": "json"},
                              total_timeout=CRT_TIMEOUT_S, retries=0, timeout=CRT_TIMEOUT_S)
    expect_status(resp)
    return [_norm_crtsh(i) for i in resp.json()]


async def _certspotter(domain: str) -> list[dict[str, Any]]:
    resp = await http_request(
        "GET", "https://api.certspotter.com/v1/issuances",
        params=[("domain", domain), ("include_subdomains", "true"), ("expand", "dns_names"), ("expand", "issuer")],
        total_timeout=10.0, retries=1,
    )
    expect_status(resp)
    return [_norm_certspotter(i) for i in resp.json()]


async def _ct_fetch(domain: str) -> tuple[Any, str | None]:
    crt = asyncio.create_task(_crtsh(domain))
    spot = asyncio.create_task(_certspotter(domain))
    try:
        try:
            return {"provider": "crt.sh", "entries": await crt}, f"https://crt.sh/?q={domain}"
        except Exception:  # noqa: BLE001 - crt.sh e adesea lent; rezerva e Cert Spotter
            return {"provider": "certspotter", "entries": await spot}, "https://api.certspotter.com/v1/issuances"
    finally:
        for task in (crt, spot):
            if not task.done():
                task.cancel()


def _build_ct(raw: Any, ctx: Ctx) -> Interp:
    domain = ctx.args["domain"]
    entries = raw.get("entries", []) if isinstance(raw, dict) else raw
    unique = {e.get("id") or e.get("serial") or f"{e.get('issuer')}|{e.get('not_before')}": e for e in entries}
    certs = list(unique.values())
    seen = [d for d in (parse_dt(c.get("logged_at")) for c in certs) if d]
    first, last = (min(seen), max(seen)) if seen else (None, None)
    issuers = sorted({c.get("issuer_org") or c.get("issuer") or "" for c in certs} - {""})
    free = [i for i in issuers if any(m in i.lower() for m in FREE_CA_MARKERS)]
    hours = hours_since(first, ctx.now)
    data = {"domain": domain, "provider": raw.get("provider") if isinstance(raw, dict) else None,
            "count": len(certs), "first_seen": first.isoformat() if first else None,
            "last_seen": last.isoformat() if last else None, "cert_age_hours": hours, "issuers": issuers,
            "free_ca": bool(free), "free_ca_issuers": free,
            "certificates": sorted(certs, key=lambda c: str(c.get("logged_at")))[-10:]}
    if not certs:
        return Interp(data, f"No certificate in Certificate Transparency for {domain}.", "neutru")
    earliest = min(certs, key=lambda c: parse_dt(c.get("logged_at")) or ctx.now)
    first_issuer = earliest.get("issuer_org") or earliest.get("issuer") or "an unknown issuer"
    first_free = any(m in first_issuer.lower() for m in FREE_CA_MARKERS)
    data["first_issuer"] = first_issuer
    ca = f"issued by {first_issuer}" + (" (a free CA)" if first_free else "")
    summary = (f"The first certificate for {domain} appeared in CT {en_ago(hours)} ({en_dt(first)}), {ca}; "
               f"{en_count(len(certs), 'certificate')} in total.")
    if hours is not None and hours < float(param("cert_age_red_hours")):
        signal = "rosu"
    elif hours is not None and hours < float(param("cert_age_yellow_days")) * DAY_H:
        signal = "galben"
    else:
        signal = "verde"
    return Interp(data, summary, signal)


@tool("ct_certificates", group="domain-intel")
async def ct_certificates(domain: str) -> ToolResult:
    """Certificatele din Certificate Transparency (crt.sh, cu Cert Spotter ca rezervă): prima apariție, emitenții, numărul."""
    registered, args = _domain_args(domain)
    if registered is None:
        return failure("ct_certificates", args, f"Invalid domain: {args['domain']}.", error="invalid domain")
    return await run_source("ct_certificates", args, key=registered, fetch=lambda: _ct_fetch(registered),
                            build=_build_ct, ttl_s=6 * 3600, label="Certificate Transparency",
                            synthetic=is_synthetic_target(registered))


# ---------------------------------------------------------------- Wayback Machine


async def _wayback_fetch(domain: str) -> tuple[Any, str | None]:
    url = "https://web.archive.org/cdx/search/cdx"
    try:
        resp = await http_request("GET", url, params={
            "url": domain, "matchType": "domain", "output": "json", "fl": "timestamp,original,statuscode",
            "limit": "1"}, total_timeout=12.0, retries=1)
        expect_status(resp)
        return {"provider": "cdx", "rows": resp.json() if resp.text.strip() else []}, url
    except Exception:  # noqa: BLE001 - rezerva: API-ul de disponibilitate
        avail = "https://archive.org/wayback/available"
        resp = await http_request("GET", avail, params={"url": domain, "timestamp": "19960101"}, retries=1)
        expect_status(resp)
        closest = (resp.json().get("archived_snapshots") or {}).get("closest") or {}
        rows = [["timestamp", "original", "statuscode"]]
        if closest.get("timestamp"):
            rows.append([closest["timestamp"], closest.get("url"), closest.get("status")])
        return {"provider": "available", "rows": rows}, avail


def _build_wayback(raw: Any, ctx: Ctx) -> Interp:
    domain = ctx.args["domain"]
    rows = [r for r in raw.get("rows", []) if r and r[0] != "timestamp"]
    if not rows:
        data = {"domain": domain, "first_seen": None, "captures": 0, "provider": raw.get("provider")}
        return Interp(data, f"Nicio captură în Wayback Machine pentru {domain} (obișnuit pentru un domeniu nou).",
                      "neutru")
    first = parse_dt(rows[0][0])
    hours = hours_since(first, ctx.now)
    data = {"domain": domain, "first_seen": first.isoformat() if first else None, "first_url": rows[0][1],
            "age_hours": hours, "captures": None, "provider": raw.get("provider")}
    summary = f"Prima captură Wayback pentru {domain}: {fmt_dt(first)} (acum {fmt_age(hours)})."
    days = (hours or 0) / DAY_H
    signal = "verde" if days >= float(param("domain_age_green_days")) else (
        "galben" if days < float(param("domain_age_yellow_days")) else "neutru")
    return Interp(data, summary, signal)


@tool("wayback_first_seen", group="domain-intel")
async def wayback_first_seen(domain: str) -> ToolResult:
    """Prima captură a domeniului în Wayback Machine (CDX, cu API-ul de disponibilitate ca rezervă)."""
    registered, args = _domain_args(domain)
    if registered is None:
        return failure("wayback_first_seen", args, f"Domeniu invalid: {args['domain']}.", error="domeniu invalid")
    return await run_source("wayback_first_seen", args, key=registered, fetch=lambda: _wayback_fetch(registered),
                            build=_build_wayback, ttl_s=86400, label="Wayback Machine",
                            synthetic=is_synthetic_target(registered))


# ---------------------------------------------------------------- IP


async def _ip_fetch(ip: str) -> tuple[Any, str | None]:
    fields = "status,message,country,countryCode,regionName,city,isp,org,as,asname,hosting,proxy,mobile,query"
    try:
        url = f"http://ip-api.com/json/{ip}"
        resp = await http_request("GET", url, params={"fields": fields}, retries=1)
        expect_status(resp)
        body = resp.json()
        if body.get("status") != "success":
            raise SourceError(f"ip-api: {body.get('message', 'eșec')}")
        return {"provider": "ip-api", **body}, url
    except Exception:  # noqa: BLE001 - rezerva: ipinfo (HTTPS, fără cheie, limitat)
        url = f"https://ipinfo.io/{ip}/json"
        resp = await http_request("GET", url, retries=1)
        expect_status(resp)
        return {"provider": "ipinfo", **resp.json()}, url


def _build_ip(raw: Any, ctx: Ctx) -> Interp:
    ip = ctx.args["ip"]
    if raw.get("provider") == "ipinfo":
        org = raw.get("org") or ""
        asn, _, as_name = org.partition(" ")
        data = {"ip": ip, "provider": "ipinfo", "country": raw.get("country"), "country_code": raw.get("country"),
                "city": raw.get("city"), "asn": asn if asn.startswith("AS") else None, "as_name": as_name or org,
                "isp": as_name or org, "hosting": bool(HOSTING_HINTS.search(org)) or None, "proxy": None,
                "hostname": raw.get("hostname")}
    else:
        asn_field = raw.get("as") or ""
        data = {"ip": ip, "provider": raw.get("provider", "ip-api"), "country": raw.get("country"),
                "country_code": raw.get("countryCode"), "city": raw.get("city"),
                "asn": asn_field.split(" ", 1)[0] if asn_field else None,
                "as_name": raw.get("asname") or (asn_field.split(" ", 1)[1] if " " in asn_field else None),
                "isp": raw.get("isp"), "org": raw.get("org"), "hosting": raw.get("hosting"),
                "proxy": raw.get("proxy"), "mobile": raw.get("mobile")}
    where = ", ".join(x for x in (data.get("city"), data.get("country")) if x) or "loc necunoscut"
    network = " ".join(x for x in (data.get("asn"), data.get("isp") or data.get("as_name")) if x) or "rețea necunoscută"
    if data.get("hosting") or data.get("proxy"):
        kind = "hosting/VPS" if data.get("hosting") else "proxy"
        return Interp(data, f"IP-ul {ip} e într-o rețea de {kind} ({network}, {where}).", "galben")
    return Interp(data, f"IP-ul {ip}: {network}, {where}.", "neutru")


@tool("ip_geo", group="domain-intel")
async def ip_geo(ip: str) -> ToolResult:
    """Țara, ASN-ul și indicatorul de hosting pentru un IP (ip-api.com, cu ipinfo ca rezervă)."""
    parsed = parse_ip(ip)
    args = {"ip": str(parsed) if parsed else ip}
    if parsed is None:
        return failure("ip_geo", args, f"IP invalid: {ip}.", error="ip invalid")
    synthetic = is_test_net(parsed)
    if not synthetic and not is_public_ip(parsed):
        return ToolResult(tool="ip_geo", args=args, ok=True, data={"ip": str(parsed), "public": False},
                          summary=f"IP-ul {parsed} e privat sau rezervat; nu se geolocalizează.", signal="neutru",
                          mode="offline")
    return await run_source("ip_geo", args, key=str(parsed), fetch=lambda: _ip_fetch(str(parsed)), build=_build_ip,
                            ttl_s=86400, label="Geolocalizarea IP", synthetic=synthetic)
