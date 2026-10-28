"""Garda SSRF: orice conexiune ieșită merge doar spre adrese IP publice.

Două straturi:
1. `assert_url_allowed()` verifică schema, portul și adresele în care se rezolvă gazda, înainte de cerere;
2. `GuardedBackend` reface verificarea la conectare (pe IP-ul efectiv), ca să nu ne prindă DNS rebinding.
"""

from __future__ import annotations

import socket
from typing import Any

import anyio
import httpcore

from versoml.osint.util import is_public_ip, parse_ip

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})


class BlockedAddressError(Exception):
    """Destinație refuzată de garda SSRF."""


class UnresolvableHostError(BlockedAddressError):
    """Gazda nu se rezolvă (nu e o încălcare a gărzii, dar nici nu ne putem conecta)."""


async def _getaddrinfo(host: str, port: int) -> list[str]:
    infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


# Rezolvitorul se poate înlocui în teste (fără rețea)
resolver = _getaddrinfo


async def resolve_public(host: str, port: int = 443) -> list[str]:
    """Rezolvă gazda și întoarce IP-urile; ridică BlockedAddressError dacă vreunul nu e public."""
    host = (host or "").strip().strip("[]")
    if not host:
        raise BlockedAddressError("gazdă lipsă")
    literal = parse_ip(host)
    if literal is not None:
        ips = [str(literal)]
    else:
        try:
            ips = await resolver(host, port)
        except (OSError, socket.gaierror) as exc:
            raise UnresolvableHostError(f"gazda {host} nu se rezolvă ({exc.__class__.__name__})") from exc
    if not ips:
        raise UnresolvableHostError(f"gazda {host} nu are adrese")
    for value in ips:
        ip = parse_ip(value)
        if ip is None or not is_public_ip(ip):
            raise BlockedAddressError(f"adresă nepublică blocată: {host} → {value}")
    return ips


def check_scheme_port(scheme: str, port: int | None) -> int:
    scheme = (scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise BlockedAddressError(f"schemă nepermisă: {scheme or 'lipsă'}")
    effective = port or (443 if scheme == "https" else 80)
    if effective not in ALLOWED_PORTS:
        raise BlockedAddressError(f"port nepermis: {effective}")
    return effective


async def assert_url_allowed(url: str) -> list[str]:
    """Verificarea completă a unui URL; întoarce IP-urile publice ale gazdei."""
    import httpx

    try:
        parsed = httpx.URL(url)
    except Exception as exc:  # noqa: BLE001 - orice URL stricat e refuzat
        raise BlockedAddressError(f"URL invalid: {exc}") from exc
    port = check_scheme_port(parsed.scheme, parsed.port)
    return await resolve_public(parsed.host, port)


class GuardedBackend(httpcore.AsyncNetworkBackend):
    """Backend de rețea pentru httpcore: rezolvă, verifică și se conectează la IP-ul verificat."""

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            ips = await resolve_public(host, port)
        except BlockedAddressError as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        last: Exception | None = None
        for ip in ips:
            try:
                return await self._inner.connect_tcp(
                    ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last = exc
        raise httpcore.ConnectError(f"conectare eșuată la {host}: {last}")

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None):
        raise httpcore.ConnectError("socket-uri Unix nepermise")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)
