"""Căutare: lanțul de furnizori (ordinea, rezervele), normalizarea, garda de confidențialitate, presa."""

from __future__ import annotations

import json

import httpx
import pytest

from versoml.osint import search
from versoml.osint.search import news_search, privacy_violation, web_search

KEYS = {"serper_api_key": "test-serper", "brave_api_key": "test-brave", "tavily_api_key": "test-tavily",
        "exa_api_key": "test-exa"}


async def test_chain_order_serper_brave_tavily(mock_http, settings_with):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "google.serper.dev":
            return httpx.Response(500)
        if request.url.host == "api.search.brave.com":
            return httpx.Response(401, json={"error": "cheie invalidă"})
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": [
                {"title": "Rezultat Tavily", "url": "https://presa.invalid/articol", "content": "fragment",
                 "published_date": "2026-10-27"}]})
        raise AssertionError(f"furnizor neașteptat: {request.url.host}")

    calls = mock_http(handler)
    with settings_with(**KEYS):
        result = await web_search("magazin online pantofi", n=5)
    assert result.ok and result.mode == "live" and result.data["provider"] == "tavily"
    assert [a["provider"] for a in result.data["attempts"]] == ["serper", "brave", "tavily"]
    assert [a["status"] for a in result.data["attempts"]] == ["eroare", "eroare", "ok"]
    hosts = [c.url.host for c in calls]
    assert hosts.index("api.search.brave.com") > hosts.index("google.serper.dev")
    assert hosts.count("google.serper.dev") == 3  # 5xx → două reîncercări
    item = result.data["results"][0]
    assert {"title", "url", "snippet", "source", "date", "provider"} <= set(item)
    assert item["source"] == "presa.invalid" and item["date"] == "2026-10-27"
    assert calls[-1].headers["authorization"] == "Bearer test-tavily"


async def test_serper_request_shape(mock_http, settings_with):
    body = {"organic": [{"title": "T", "link": "https://site.invalid/a", "snippet": "S", "position": 1}], "credits": 1}
    calls = mock_http(lambda request: httpx.Response(200, json=body))
    with settings_with(serper_api_key="test-serper"):
        result = await web_search("magazin online pantofi", n=4)
    sent = json.loads(calls[0].content)
    assert calls[0].headers["x-api-key"] == "test-serper"
    assert sent == {"q": "magazin online pantofi", "num": 4, "gl": "ro", "hl": "ro"}
    assert result.data["provider"] == "serper" and result.data["results"][0]["url"] == "https://site.invalid/a"


async def test_exa_and_brave_parsers(mock_http, settings_with):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": []}})
        return httpx.Response(200, json={"results": [{"title": "Exa", "url": "https://exa.invalid/x",
                                                      "publishedDate": "2026-10-20", "text": "text exa"}]})

    calls = mock_http(handler)
    with settings_with(brave_api_key="test-brave", exa_api_key="test-exa"):
        result = await web_search("magazin online pantofi")
    assert result.data["provider"] == "exa"
    assert [a["status"] for a in result.data["attempts"]] == ["fara_cheie", "gol", "fara_cheie", "ok"]
    assert calls[0].headers["x-subscription-token"] == "test-brave" and calls[0].url.params["country"] == "RO"
    assert calls[1].headers["x-api-key"] == "test-exa"


async def test_no_keys_falls_back_to_duckduckgo(monkeypatch, mock_http):
    calls = mock_http(lambda request: httpx.Response(500))
    seen = {}

    def fake_ddg(query, n, kind):
        seen["args"] = (query, n, kind)
        return [{"title": "DDG", "href": "https://ddg.invalid/r", "body": "fragment ddg"}]

    monkeypatch.setattr(search, "_ddg_sync", fake_ddg)
    result = await web_search("magazin online pantofi", n=3)
    assert result.data["provider"] == "duckduckgo" and seen["args"] == ("magazin online pantofi", 3, "web")
    assert [a["status"] for a in result.data["attempts"]] == ["fara_cheie"] * 4 + ["ok"]
    assert not calls


def test_ddg_gets_a_short_query():
    assert search.ddg_query(search.news_query("X MOCK SRL")) == '"X MOCK SRL" țeapă fraudă înșelăciune'
    assert search.ddg_query('"0700000111" OR "+40700000111"') == '"0700000111"'
    assert search.ddg_query("magazin online pantofi") == "magazin online pantofi"


async def test_all_providers_down_is_failure(monkeypatch):
    def broken(query, n, kind):
        raise RuntimeError("rețea căzută")

    monkeypatch.setattr(search, "_ddg_sync", broken)
    result = await web_search("magazin online pantofi")
    assert result.ok is False and result.mode == "live" and "niciun furnizor" in result.error


async def test_synthetic_query_uses_fixture(no_network):
    result = await web_search('"0700000111" OR "+40700000111"')
    assert result.mode == "fixture" and result.data["count"] == 3
    assert not no_network.calls


@pytest.mark.parametrize("query, reason", [
    ("6010315431239 reclamație", "CNP"),
    ("card 4111 1111 1111 1111 furat", "card"),
    ("RO54RZBR0000060012345678 fraudă", "IBAN"),
])
async def test_privacy_guard_refuses_victim_data(query, reason, no_network):
    assert reason in privacy_violation(query)
    result = await web_search(query)
    assert result.ok is False and "refuzată" in result.summary
    assert not no_network.calls


async def test_news_search_company_is_red(no_network):
    result = await news_search("EXPRES LIVRARE DEMO SRL")
    assert result.mode == "fixture" and result.signal == "rosu" and result.data["fraud_hits"] == 2
    assert "țepe" in result.summary or "înșelăciune" in result.summary
    assert result.args == {"entity": "EXPRES LIVRARE DEMO SRL", "n": 8}


async def test_news_search_new_domain_has_nothing(no_network):
    result = await news_search("livrare-bancademo.example")
    assert result.ok and result.signal == "neutru" and result.data["count"] == 0


async def test_news_query_biases_romanian_fraud_terms(mock_http, settings_with):
    calls = mock_http(lambda request: httpx.Response(200, json={"news": [
        {"title": "Firma Mock acuzată de înșelăciune", "link": "https://stiri.invalid/a", "snippet": "Poliția investighează Firma Mock",
         "date": "acum 2 zile", "source": "Știri Mock"}]}))
    with settings_with(serper_api_key="test-serper"):
        result = await news_search("FIRMA MOCK SRL")
    sent = json.loads(calls[0].content)
    assert str(calls[0].url) == "https://google.serper.dev/news"
    for term in ("țeapă", "fraudă", "înșelăciune", "phishing", "ANPC", "DIICOT", "poliția"):
        assert term in sent["q"]
    assert sent["q"].startswith('"FIRMA MOCK SRL"')
    assert sent["gl"] == "ro" and result.signal == "galben" and result.data["fraud_hits"] == 1


@pytest.mark.parametrize("entity, kind", [
    ("EXPRES LIVRARE DEMO SRL", "firma"), ("Alfa Beta S.R.L.", "firma"), ("Asociația de Proprietari Demo", "firma"),
    ("livrare-bancademo.example", "domeniu"), ("+40700000111", "telefon"), ("44712025", "cui"),
    ("Ion Popescu", "altceva"), ("DNSC", "altceva"),
])
def test_entity_kind(entity, kind):
    assert search.entity_kind(entity) == kind


async def test_news_search_refuses_person_names_live(no_network, settings_with):
    with settings_with(serper_api_key="test-serper"):
        result = await news_search("Ion Popescu")
    assert result.ok is False and result.error == "entitate nepermisă"
    assert "persoanelor fizice" in result.summary
    assert not no_network.calls
