"""Baza toolkit-ului OSINT: ToolResult, modurile de lucru, clientul HTTP comun, cache-ul SQLite,
înregistrările locale (fixtures) și registrul de tool-uri pentru serverul MCP.

Moduri (`VERSOML_OSINT_MODE`):
- `fixture`: doar `versoml/osint/fixtures/<tool>/<cheie>.json`, fără rețea;
- `live`: sursa reală (cu cache proaspăt), fără rezervă pe înregistrări;
- `auto`: cache proaspăt → sursa reală → cache expirat → înregistrare locală.
Țintele sintetice (.example, .test, TEST-NET, +40 700 000 xxx, registrul sintetic) merg mereu pe fixture.
"""

from __future__ import annotations

import asyncio
import contextlib
import email.utils
import inspect
import json
import logging
import re
import sqlite3
import threading
import time
import typing
import weakref
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from versoml.config import Settings, get_settings
from versoml.contracts import OsintFinding
from versoml.osint.netguard import BlockedAddressError, GuardedBackend
from versoml.osint.util import (
    fold,
    host_from,
    is_synthetic_phone,
    is_test_net,
    normalize_phone,
    normalize_ro,
    parse_ip,
)
from versoml.secrets import redact, register_secret

log = logging.getLogger("versoml.osint")

Signal = Literal["rosu", "galben", "verde", "neutru"]
Mode = Literal["live", "fixture", "cache", "offline"]
SIGNAL_ORDER: dict[str, int] = {"rosu": 0, "galben": 1, "neutru": 2, "verde": 3}

RO_TZ = ZoneInfo("Europe/Bucharest")
# „Acum"-ul fix al înregistrărilor locale: vârstele din fixtures se calculează față de el
FIXTURE_NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=RO_TZ)
PACKAGE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = PACKAGE_DIR / "fixtures"


def now_ro() -> datetime:
    return datetime.now(RO_TZ)


# ---------------------------------------------------------------- contractul


class ToolResult(BaseModel):
    """Rezultatul oricărui tool OSINT (docs/06 §4.3)."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    signal: Signal = "neutru"
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=now_ro)
    mode: Mode = "offline"
    latency_ms: int = 0
    error: str | None = None

    def target(self) -> str:
        """Ținta interogată (primul argument), pentru UI și registru."""
        for value in self.args.values():
            if isinstance(value, str) and value:
                return value
        return self.tool

    def as_finding(self, target: str | None = None, fact_id: str | None = None) -> OsintFinding:
        return OsintFinding(
            tool=self.tool,
            target=target or self.target(),
            ok=self.ok,
            summary=self.summary,
            signal=self.signal,
            fact_id=fact_id,
            source_url=self.source_url,
            mode=self.mode,
        )


def sort_results(results: Sequence[ToolResult]) -> list[ToolResult]:
    """Roșu → galben → neutru → verde; la egalitate, întâi cele reușite, apoi după nume."""
    return sorted(results, key=lambda r: (SIGNAL_ORDER.get(r.signal, 9), not r.ok, r.tool, r.target()))


# ---------------------------------------------------------------- setări și chei

_settings_override: Settings | None = None


def settings() -> Settings:
    return _settings_override or get_settings()


@contextlib.contextmanager
def override_settings(**values: Any) -> Iterator[Settings]:
    """Pentru teste: înlocuiește temporar setările (chei, mod, director var)."""
    global _settings_override
    previous = _settings_override
    _settings_override = Settings(**values)
    try:
        yield _settings_override
    finally:
        _settings_override = previous


KEY_ENV = {
    "serper_api_key": "SERPER_API_KEY",
    "brave_api_key": "BRAVE_API_KEY",
    "tavily_api_key": "TAVILY_API_KEY",
    "exa_api_key": "EXA_API_KEY",
    "jina_api_key": "JINA_API_KEY",
    "urlscan_api_key": "URLSCAN_API_KEY",
    "virustotal_api_key": "VIRUSTOTAL_API_KEY",
    "urlhaus_auth_key": "URLHAUS_AUTH_KEY",
    "google_safe_browsing_key": "GOOGLE_SAFE_BROWSING_KEY",
}


def secret(field_name: str) -> str | None:
    """Valoarea unei chei opționale (și o înregistrează pentru redactarea din loguri)."""
    value = getattr(settings(), field_name, None)
    if value is None:
        return None
    raw = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
    raw = raw.strip()
    if not raw:
        return None
    register_secret(raw)
    return raw


def configured_mode() -> Literal["fixture", "live", "auto"]:
    return settings().versoml_osint_mode


# ---------------------------------------------------------------- timp și formatare


def parse_dt(value: Any) -> datetime | None:
    """ISO 8601 (cu sau fără Z), dată simplă sau timestamp Wayback (AAAALLZZhhmmss)."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if re.fullmatch(r"\d{14}", text):
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def hours_since(then: datetime | None, now: datetime) -> float | None:
    if then is None:
        return None
    return round((now - then).total_seconds() / 3600, 2)


def ro_count(n: int, singular: str, plural: str) -> str:
    """Acordul numeralului în română: 1 oră, 5 ore, 20 de ore."""
    if n == 1:
        return f"1 {singular}"
    rest = n % 100
    if n != 0 and (rest == 0 or rest >= 20):
        return f"{n} de {plural}"
    return f"{n} {plural}"


def ro_join(items: Sequence[str]) -> str:
    """„a”, „a și b”, „a, b și c”."""
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " și " + items[-1]


def fmt_dec(value: float, digits: int = 2) -> str:
    """Zecimale cu virgulă, ca în română."""
    return f"{value:.{digits}f}".replace(".", ",")


def fmt_age(hours: float | None) -> str:
    if hours is None:
        return "vârstă necunoscută"
    if hours < 0:
        return "în viitor (dată inconsecventă)"
    if hours < 48:
        return ro_count(max(int(round(hours)), 0), "oră", "ore")
    days = hours / 24
    if days < 60:
        return ro_count(int(days), "zi", "zile")
    if days < 730:
        return ro_count(int(days // 30), "lună", "luni")
    return ro_count(int(days // 365), "an", "ani")


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "necunoscut"
    return value.astimezone(RO_TZ).strftime("%d.%m.%Y, %H:%M")


# ---------------------------------------------------------------- English, for what the website shows

MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def en_count(n: int, singular: str, plural: str | None = None) -> str:
    """'1 hour', '5 hours'."""
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def en_join(items: Sequence[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def en_ago(hours: float | None) -> str:
    """'6 hours ago', '3 days ago', '2 years ago'."""
    if hours is None:
        return "at an unknown time"
    if hours < 0:
        return "with a date in the future (inconsistent)"
    if hours < 48:
        return en_count(max(int(round(hours)), 0), "hour") + " ago"
    days = hours / 24
    if days < 60:
        return en_count(int(days), "day") + " ago"
    if days < 730:
        return en_count(int(days // 30), "month") + " ago"
    return en_count(int(days // 365), "year") + " ago"


def en_dt(value: datetime | None) -> str:
    """'29 Oct 2026, 23:59' (Bucharest time, 24-hour)."""
    if value is None:
        return "unknown"
    local = value.astimezone(RO_TZ)
    return f"{local.day} {MONTHS_EN[local.month - 1]} {local.year}, {local:%H:%M}"


# ---------------------------------------------------------------- HTTP

USER_AGENT = "VersoMLBot/0.1 (hackathon NEXXT 2026)"
TIMEOUT = httpx.Timeout(12.0, connect=5.0)
TOTAL_TIMEOUT_S = 12.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRIES = 2
RETRY_BASE_DELAY = 0.5
RETRY_AFTER_CAP_S = 3.0
# Intervalul minim între cereri spre aceeași gazdă (ANAF cere cel mult 1 cerere/secundă)
HOST_MIN_INTERVAL_S: dict[str, float] = {
    "webservicesp.anaf.ro": 1.05,
    "ip-api.com": 1.4,
    "crt.sh": 1.0,
    "web.archive.org": 1.0,
    "archive.org": 1.0,
    "openphish.com": 2.0,
    "whois.rotld.ro": 1.0,
}


class SourceError(Exception):
    """Sursa a răspuns, dar nu cu ce așteptam (status, format)."""


_transport_override: httpx.AsyncBaseTransport | None = None
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = weakref.WeakKeyDictionary()
_host_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)
_host_next: dict[str, float] = {}


def _build_transport() -> httpx.AsyncBaseTransport:
    if _transport_override is not None:
        return _transport_override
    transport = httpx.AsyncHTTPTransport(retries=0)
    pool = getattr(transport, "_pool", None)
    if pool is not None and hasattr(pool, "_network_backend"):
        pool._network_backend = GuardedBackend()  # garda SSRF la conectare, pentru orice cerere
    return transport


def get_client() -> httpx.AsyncClient:
    """Clientul comun al buclei curente (timeout: conectare 5 s, citire 12 s)."""
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            transport=_build_transport(),
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        _clients[loop] = client
    return client


@contextlib.contextmanager
def use_transport(transport: httpx.AsyncBaseTransport) -> Iterator[None]:
    """Pentru teste: toate cererile trec prin transportul dat (de exemplu httpx.MockTransport)."""
    global _transport_override
    previous = _transport_override
    _transport_override = transport
    _clients.clear()
    try:
        yield
    finally:
        _transport_override = previous
        _clients.clear()


async def aclose_clients() -> None:
    for client in list(_clients.values()):
        await client.aclose()
    _clients.clear()


async def _throttle(host: str) -> None:
    interval = HOST_MIN_INTERVAL_S.get(host)
    if not interval:
        return
    loop = asyncio.get_running_loop()
    locks = _host_locks.setdefault(loop, {})
    lock = locks.setdefault(host, asyncio.Lock())
    async with lock:
        wait = _host_next.get(host, 0.0) - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _host_next[host] = time.monotonic() + interval


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return 0.0
    if value.isdigit():
        return min(float(value), RETRY_AFTER_CAP_S)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min((when - datetime.now(timezone.utc)).total_seconds(), RETRY_AFTER_CAP_S))


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.ConnectError) and any(m in str(exc) for m in ("non-public", "not allowed", "nepublic", "nepermis")):
        return False
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


async def http_request(
    method: str,
    url: str,
    *,
    retries: int = RETRIES,
    total_timeout: float = TOTAL_TIMEOUT_S,
    **kwargs: Any,
) -> httpx.Response:
    """O cerere cu reîncercări pe 5xx/429 (backoff exponențial), limită de ritm pe gazdă și timeout total."""
    client = get_client()
    host = httpx.URL(url).host
    delay = RETRY_BASE_DELAY
    async with asyncio.timeout(total_timeout):
        for attempt in range(retries + 1):
            await _throttle(host)
            try:
                response = await client.request(method, url, **kwargs)
            except Exception as exc:  # noqa: BLE001 - decidem mai jos dacă reîncercăm
                if attempt >= retries or not _retryable(exc):
                    raise
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if response.status_code in RETRY_STATUSES and attempt < retries:
                wait = max(delay, _retry_after(response))
                await response.aclose()
                await asyncio.sleep(wait)
                delay *= 2
                continue
            return response
    raise SourceError("reîncercări epuizate")  # pragma: no cover


def expect_status(response: httpx.Response, ok: Sequence[int] = (200,)) -> None:
    if response.status_code not in ok:
        raise SourceError(f"HTTP {response.status_code}")


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, (SourceError, BlockedAddressError)):
        return redact(str(exc))[:200]
    if isinstance(exc, httpx.HTTPError):
        return redact(f"{exc.__class__.__name__}: {exc}")[:200]
    return redact(f"{exc.__class__.__name__}: {exc}")[:200]


# ---------------------------------------------------------------- cache SQLite


@dataclass
class CacheHit:
    raw: Any
    source_url: str | None
    created_at: datetime
    stale: bool


class Cache:
    """Cache-ul rezultatelor live, în `var/osint_cache.db`, cu TTL pe tool."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._run(
            "CREATE TABLE IF NOT EXISTS osint_cache (tool TEXT NOT NULL, key TEXT NOT NULL, "
            "created_at REAL NOT NULL, expires_at REAL NOT NULL, source_url TEXT, payload TEXT NOT NULL, "
            "PRIMARY KEY (tool, key))"
        )

    def _run(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        with self._lock:
            con = sqlite3.connect(self.path, timeout=5)
            try:
                rows = con.execute(sql, params).fetchall()
                con.commit()
                return rows
            finally:
                con.close()

    def get(self, tool: str, key: str, *, allow_stale: bool = False) -> CacheHit | None:
        try:
            rows = self._run(
                "SELECT created_at, expires_at, source_url, payload FROM osint_cache WHERE tool=? AND key=?",
                (tool, key),
            )
        except sqlite3.Error:
            return None
        if not rows:
            return None
        created, expires, source_url, payload = rows[0]
        stale = expires < time.time()
        if stale and not allow_stale:
            return None
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return CacheHit(raw, source_url, datetime.fromtimestamp(created, RO_TZ), stale)

    def put(self, tool: str, key: str, raw: Any, source_url: str | None, ttl_s: float) -> None:
        now = time.time()
        try:
            payload = json.dumps(raw, ensure_ascii=False, default=str)
            self._run(
                "INSERT OR REPLACE INTO osint_cache (tool, key, created_at, expires_at, source_url, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (tool, key, now, now + ttl_s, source_url, payload),
            )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            log.warning("cache osint: nu am putut salva %s (%s)", tool, exc.__class__.__name__)

    def clear(self) -> None:
        self._run("DELETE FROM osint_cache")


_caches: dict[Path, Cache] = {}


def get_cache() -> Cache:
    path = settings().var_dir / "osint_cache.db"
    cache = _caches.get(path)
    if cache is None:
        cache = _caches[path] = Cache(path)
    return cache


# ---------------------------------------------------------------- înregistrări locale


@dataclass
class Fixture:
    raw: Any
    source_url: str | None
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)


def fixture_key(value: str) -> str:
    """Cheia fișierului: formă pliată, fără schemă, doar [a-z0-9._+-]."""
    text = fold(value)
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = re.sub(r"[^a-z0-9._+-]+", "_", text).strip("._")
    return text[:150] or "_"


def _read_fixture(path: Path) -> Fixture:
    meta = json.loads(path.read_text(encoding="utf-8"))
    raw = meta.pop("raw", None)
    raw_file = meta.get("raw_file")
    if raw_file:
        raw = (path.parent / raw_file).read_text(encoding="utf-8")
    for raw_key, name in (meta.get("raw_files") or {}).items():
        if isinstance(raw, dict):
            raw[raw_key] = (path.parent / name).read_text(encoding="utf-8")
    return Fixture(raw=raw, source_url=meta.get("source_url"), path=path, meta=meta)


def load_fixture(tool: str, keys: Sequence[str], query: str | None = None) -> Fixture | None:
    """Caută `fixtures/<tool>/<cheie>.json`; pentru căutări, și după termenii `match` din fișiere.

    Un fișier stricat se ignoră (cu avertisment), ca tool-ul să rămână fail-soft.
    """
    try:
        return _find_fixture(tool, keys, query)
    except (OSError, ValueError) as exc:
        log.warning("fixture osint %s stricat (%s)", tool, exc.__class__.__name__)
        return None


def _find_fixture(tool: str, keys: Sequence[str], query: str | None) -> Fixture | None:
    folder = FIXTURES_DIR / tool
    if not folder.is_dir():
        return None
    for key in keys:
        path = folder / f"{fixture_key(key)}.json"
        if path.is_file():
            return _read_fixture(path)
    if query:
        folded = fold(query)
        digits = re.sub(r"\D", "", query)
        for path in sorted(folder.glob("*.json")):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for term in meta.get("match", []):
                term_f = fold(term)
                if term_f and (term_f in folded or (term_f.isdigit() and term_f in digits)):
                    return _read_fixture(path)
    return None


def fixture_text(relative: str) -> str:
    return (FIXTURES_DIR / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------- ținte sintetice

SYNTHETIC_NAME_TOKENS = frozenset({"demo", "exemplu", "fictiv", "fictiva", "fictive", "sintetic", "sintetica"})


@lru_cache(maxsize=1)
def synthetic_registry() -> dict[str, Any]:
    path = FIXTURES_DIR / "synthetic_registry.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_synthetic_target(value: str | None) -> bool:
    """True pentru ținte care nu trebuie să ajungă niciodată la o sursă reală.

    Domeniile și URL-urile sunt sintetice doar după TLD (.example, .test) sau IP (TEST-NET); regula pe
    cuvinte („demo", „exemplu") se aplică doar textului liber și numelor de firme.
    """
    text = normalize_ro(value).strip()
    if not text:
        return False
    host = host_from(text) if " " not in text else ""
    ip = parse_ip(host) if host else parse_ip(text)
    if ip is not None:
        return is_test_net(ip)
    if host and host.rsplit(".", 1)[-1] in ("example", "test"):
        return True
    if host and "." in host and re.fullmatch(r"[a-z0-9.-]+", host) and not text.replace(".", "").isdigit():
        return False
    lowered = text.lower()
    if re.search(r"[\w-]\.(example|test)(?![\w-])", lowered):
        return True
    if re.search(r"(?<![\d.])(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}(?![\d.])", text):
        return True
    for candidate in re.findall(r"\+?\d[\d\s().-]{7,16}\d", text):
        if is_synthetic_phone(normalize_phone(candidate)):
            return True
    registry = synthetic_registry()
    compact = re.sub(r"[\s.-]", "", text.upper())
    if compact.removeprefix("RO") in set(registry.get("cuis", [])):
        return True
    if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", compact) and compact[4:8] in set(registry.get("bank_codes", [])):
        return True
    tokens = set(re.findall(r"[a-z0-9]+", fold(text)))
    if tokens & SYNTHETIC_NAME_TOKENS:
        return True
    folded = fold(text)
    return any(fold(name) in folded for name in registry.get("companies", []))


# ---------------------------------------------------------------- execuția unei surse


@dataclass
class Ctx:
    mode: Mode
    now: datetime
    args: dict[str, Any]


@dataclass
class Interp:
    """Interpretarea unui răspuns brut: datele normalizate, propoziția în română și semnalul."""

    data: dict[str, Any]
    summary: str
    signal: Signal = "neutru"
    ok: bool = True
    error: str | None = None


Fetcher = Callable[[], Awaitable[tuple[Any, str | None]]]
Builder = Callable[[Any, Ctx], Interp]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def result(
    tool: str,
    args: dict[str, Any],
    interp: Interp,
    *,
    mode: Mode,
    started: float,
    source_url: str | None = None,
    retrieved_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> ToolResult:
    data = dict(interp.data)
    if extra:
        data.update(extra)
    return ToolResult(
        tool=tool,
        args=args,
        ok=interp.ok,
        data=data,
        summary=normalize_ro(interp.summary),
        signal=interp.signal,
        source_url=source_url,
        retrieved_at=retrieved_at or now_ro(),
        mode=mode,
        latency_ms=_elapsed_ms(started),
        error=interp.error,
    )


def failure(
    tool: str,
    args: dict[str, Any],
    summary: str,
    *,
    error: str,
    mode: Mode = "offline",
    started: float | None = None,
    data: dict[str, Any] | None = None,
    signal: Signal = "neutru",
) -> ToolResult:
    return ToolResult(
        tool=tool,
        args=args,
        ok=False,
        data=data or {},
        summary=normalize_ro(summary),
        signal=signal,
        mode=mode,
        latency_ms=_elapsed_ms(started) if started else 0,
        error=redact(error),
    )


def _safe_build(build: Builder, raw: Any, ctx: Ctx, label: str) -> Interp:
    try:
        return build(raw, ctx)
    except Exception as exc:  # noqa: BLE001 - un răspuns ciudat nu oprește investigația
        log.warning("osint %s: unexpected format (%s)", label, exc.__class__.__name__)
        return Interp(
            data={},
            summary=f"{label}: the response came in an unexpected format.",
            ok=False,
            error=f"unexpected format: {exc.__class__.__name__}: {str(exc)[:120]}",
        )


async def run_source(
    tool: str,
    args: dict[str, Any],
    *,
    key: str,
    fetch: Fetcher,
    build: Builder,
    ttl_s: float,
    label: str,
    synthetic: bool = False,
    fixture_keys: Sequence[str] | None = None,
    fixture_query: str | None = None,
    missing_key: str | None = None,
) -> ToolResult:
    """Aplică modul de lucru pentru o sursă: fixture, cache, live, rezerve. Nu ridică excepții."""
    started = time.perf_counter()
    mode = "fixture" if synthetic else configured_mode()
    keys = list(fixture_keys or [key])

    def from_fixture() -> ToolResult | None:
        fx = load_fixture(tool, keys, fixture_query)
        if fx is None:
            return None
        interp = _safe_build(build, fx.raw, Ctx("fixture", FIXTURE_NOW, args), label)
        extra = {"synthetic": bool(fx.meta.get("synthetic", True))}
        return result(tool, args, interp, mode="fixture", started=started, source_url=fx.source_url,
                      retrieved_at=FIXTURE_NOW, extra=extra)

    if mode == "fixture":
        found = from_fixture()
        if found is not None:
            return found
        why = "synthetic target" if synthetic else "fixture mode"
        return failure(tool, args, f"{label}: there is no local record for {key} ({why}).",
                       error="missing fixture", started=started)

    cache = get_cache()
    hit = cache.get(tool, key)
    if hit is not None:
        interp = _safe_build(build, hit.raw, Ctx("cache", now_ro(), args), label)
        return result(tool, args, interp, mode="cache", started=started, source_url=hit.source_url,
                      retrieved_at=hit.created_at)

    if missing_key:
        if mode == "auto":
            found = from_fixture()
            if found is not None:
                return found
        return failure(tool, args, f"{label}: needs the {missing_key} key, which is not configured.",
                       error=f"missing key {missing_key}", started=started)

    try:
        raw, source_url = await fetch()
    except Exception as exc:  # noqa: BLE001 - orice eroare a sursei devine rezultat, nu excepție
        err = describe_error(exc)
        log.info("osint %s: the source failed (%s)", tool, err)
        if mode == "auto":
            stale = cache.get(tool, key, allow_stale=True)
            if stale is not None:
                interp = _safe_build(build, stale.raw, Ctx("cache", now_ro(), args), label)
                return result(tool, args, interp, mode="cache", started=started, source_url=stale.source_url,
                              retrieved_at=stale.created_at, extra={"cache_stale": True, "live_error": err})
            found = from_fixture()
            if found is not None:
                found.data["live_error"] = err
                return found
        return failure(tool, args, f"{label} did not respond ({err}).", error=err, mode="live", started=started)

    retrieved = now_ro()
    interp = _safe_build(build, raw, Ctx("live", retrieved, args), label)
    if interp.ok:
        cache.put(tool, key, raw, source_url, ttl_s)
    return result(tool, args, interp, mode="live", started=started, source_url=source_url, retrieved_at=retrieved)


# ---------------------------------------------------------------- registrul de tool-uri (pentru MCP)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable[..., Any]
    description: str
    zones: tuple[str, ...]
    group: str
    effect: str
    is_async: bool
    input_model: type[BaseModel]
    input_schema: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "zones": list(self.zones),
            "group": self.group,
            "effect": self.effect,
            "is_async": self.is_async,
            "input_schema": self.input_schema,
        }


_REGISTRY: dict[str, ToolSpec] = {}
TOOL_MODULES = (
    "search", "crawl", "domain", "lookalike", "page_similarity",
    "threatintel", "registry_ro", "sanctions", "phone", "investigate",
)


def _input_model(name: str, fn: Callable[..., Any]) -> type[BaseModel]:
    hints = typing.get_type_hints(fn)
    fields: dict[str, Any] = {}
    for pname, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[pname] = (hints.get(pname, Any), default)
    return create_model(f"{name}_input", __config__=ConfigDict(extra="forbid"), **fields)


def tool(
    name: str,
    *,
    description: str | None = None,
    zones: Sequence[str] = ("client", "aml"),
    group: str = "osint",
    effect: str = "citire",
    input_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Înregistrează o funcție ca tool (nume, descriere, zone, schemă JSON a argumentelor)."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        model = _input_model(name, fn)
        doc = description or (inspect.getdoc(fn) or name).split("\n\n")[0].replace("\n", " ").strip()
        _REGISTRY[name] = ToolSpec(
            name=name,
            fn=fn,
            description=normalize_ro(doc),
            zones=tuple(zones),
            group=group,
            effect=effect,
            is_async=inspect.iscoroutinefunction(fn),
            input_model=model,
            input_schema=input_schema or model.model_json_schema(),
        )
        return fn

    return decorate


def _ensure_loaded() -> None:
    import importlib

    for module in TOOL_MODULES:
        importlib.import_module(f"versoml.osint.{module}")


def list_tools() -> list[dict[str, Any]]:
    """Tool-urile, cu descriere și schema JSON a argumentelor (pentru serverul MCP)."""
    _ensure_loaded()
    return [spec.as_dict() for spec in sorted(_REGISTRY.values(), key=lambda s: s.name)]


def get_tool(name: str) -> ToolSpec:
    _ensure_loaded()
    if name not in _REGISTRY:
        raise KeyError(f"unknown OSINT tool: {name}")
    return _REGISTRY[name]


async def call_tool(name: str, args: dict[str, Any] | None = None) -> ToolResult | list[ToolResult]:
    """Validează argumentele pe schemă și apelează tool-ul. Erorile devin ToolResult, nu excepții."""
    args = dict(args or {})
    try:
        spec = get_tool(name)
    except KeyError as exc:
        return failure(name, args, f"Unknown tool: {name}.", error=str(exc))
    try:
        params = spec.input_model.model_validate(args)
    except ValidationError as exc:
        return failure(name, args, f"Invalid arguments for {name}.", error=str(exc)[:300])
    kwargs = {k: getattr(params, k) for k in type(params).model_fields}
    try:
        value = spec.fn(**kwargs)
        if inspect.isawaitable(value):
            value = await value
    except Exception as exc:  # noqa: BLE001 - tool-urile nu au voie să rupă agentul
        return failure(name, args, f"{name} failed unexpectedly.", error=describe_error(exc))
    return value
