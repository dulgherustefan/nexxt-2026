"""Fixture-uri comune pentru testele OSINT: setări izolate, fără chei, fără rețea."""

from __future__ import annotations

import os
import socket

import httpx
import pytest

from versoml.osint import base, netguard, search

NO_KEYS = {field: None for field in base.KEY_ENV}

# SMS-ul din scenariul demo_t1 (sintetic): curier fals → pagina care imită Banca Demo
DEMO_T1_SMS = (
    "Curier Demo: coletul tău AWB 7731 nu a putut fi livrat. Confirmă livrarea și achită taxa de 4,99 lei: "
    "https://livrare-bancademo.example/confirmare?id=7731 . Detalii la 0700 000 111. "
    "Plata se face către EXPRES LIVRARE DEMO SRL, CUI 44712025."
)


@pytest.fixture(autouse=True)
def _live_gate(request):
    if request.node.get_closest_marker("live") and os.environ.get("VERSOML_LIVE_TESTS") != "1":
        pytest.skip("test live: rulează doar cu VERSOML_LIVE_TESTS=1")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch, request):
    """Fiecare test: var/ temporar (cache gol), fără chei, mod auto, fără așteptări între reîncercări."""
    if not request.node.get_closest_marker("live"):
        monkeypatch.setattr(base, "RETRY_BASE_DELAY", 0.0)
        monkeypatch.setattr(base, "HOST_MIN_INTERVAL_S", {})
    with base.override_settings(versoml_var_dir=tmp_path / "var", versoml_osint_mode="auto", **NO_KEYS) as current:
        yield current


@pytest.fixture
def settings_with(tmp_path):
    """Setări cu valori date (de exemplu chei de test), păstrând izolarea."""

    def make(**values):
        merged = {"versoml_var_dir": tmp_path / "var", "versoml_osint_mode": "auto", **NO_KEYS, **values}
        return base.override_settings(**merged)

    return make


class RecordingTransport(httpx.AsyncBaseTransport):
    """Transport care refuză orice cerere și o înregistrează (ca să dovedim că nu s-a ieșit în rețea)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        raise httpx.ConnectError("rețea interzisă în test", request=request)


@pytest.fixture
def no_network(monkeypatch):
    transport = RecordingTransport()

    async def no_dns(host, port):
        transport.calls.append(f"dns:{host}")
        raise OSError("DNS interzis în test")

    def no_socket_dns(*args, **kwargs):
        transport.calls.append(f"socket:{args[0] if args else ''}")
        raise OSError("DNS interzis în test")

    def no_ddg(query, n, kind):
        transport.calls.append(f"ddg:{query}")
        raise RuntimeError("DuckDuckGo interzis în test")

    monkeypatch.setattr(netguard, "resolver", no_dns)
    monkeypatch.setattr(socket, "getaddrinfo", no_socket_dns)
    monkeypatch.setattr(search, "_ddg_sync", no_ddg)
    with base.use_transport(transport):
        yield transport


@pytest.fixture
def mock_http():
    """Instalează un handler httpx.MockTransport; întoarce lista cererilor primite."""
    calls: list[httpx.Request] = []
    holder: dict = {}

    def install(handler):
        def wrapped(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        holder["ctx"] = base.use_transport(httpx.MockTransport(wrapped))
        holder["ctx"].__enter__()
        return calls

    yield install
    if "ctx" in holder:
        holder["ctx"].__exit__(None, None, None)


@pytest.fixture
def public_resolver(monkeypatch):
    """Rezolvitor fals: orice gazdă → un IP public (fără DNS real); gazdele din `private` → IP privat."""
    private: dict[str, str] = {}

    async def resolve(host, port):
        return [private.get(host, "8.8.8.8")]

    monkeypatch.setattr(netguard, "resolver", resolve)
    return private
