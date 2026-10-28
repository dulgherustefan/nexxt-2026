"""Sancțiuni: potrivire fuzzy pe lista sintetică și pe lista UE (OpenSanctions eu_fsf, din fișier local)."""

from __future__ import annotations

import httpx
import pytest

from versoml.osint import sanctions
from versoml.osint.sanctions import normalize_name, sanctions_screen

EU_CSV = (
    "id,schema,name,aliases,birth_date,countries,addresses,identifiers,sanctions,phones,emails,program_ids,dataset,"
    "first_seen,last_seen,last_change\n"
    "mock-1,Company,ZETA MOCK TRADING LIMITED,Zeta Mock Trade;ZMT,,zz,,,Mock program,,,MOCK-1,eu_fsf,,,\n"
    "mock-2,Person,Persoana Mock Inventata,,,zz,,,Mock program,,,MOCK-2,eu_fsf,,,\n"
)


@pytest.mark.parametrize("name", ["Cripto Schimb Demo S.R.L.", "CRYPTO SCHIMB DEMO", "cripto  schimb  demo srl"])
async def test_synthetic_watchlist_hits(name, no_network):
    result = await sanctions_screen(name)
    assert result.signal == "rosu" and result.data["matches"][0]["entity_id"] == "SIN-004"
    assert "de verificat de un om" in result.summary
    assert not no_network.calls


async def test_person_and_variant_spelling(no_network):
    result = await sanctions_screen("Ivan Exempluov")
    assert result.signal == "rosu" and result.data["matches"][0]["schema"] == "Person"


async def test_scenario_company_is_clean(no_network):
    result = await sanctions_screen("EXPRES LIVRARE DEMO SRL")
    assert result.signal == "verde" and result.data["best_score"] < 85


async def test_short_common_token_does_not_match(no_network):
    result = await sanctions_screen("Demo")
    assert result.signal == "verde"


async def test_eu_list_from_local_file(tmp_path, monkeypatch, settings_with):
    path = tmp_path / "eu.csv"
    path.write_text(EU_CSV, encoding="utf-8")
    monkeypatch.setattr(sanctions, "eu_fsf_path", lambda: path)
    with settings_with(versoml_osint_mode="fixture"):
        result = await sanctions_screen("Zeta Mock Trading Ltd")
    assert result.signal == "rosu" and result.data["matches"][0]["list"] == "eu_fsf"
    assert result.mode == "cache" and "OpenSanctions" in result.summary


async def test_eu_list_download(tmp_path, monkeypatch, mock_http):
    path = tmp_path / "descarcat.csv"
    monkeypatch.setattr(sanctions, "eu_fsf_path", lambda: path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/latest/eu_fsf/targets.simple.csv"):
            return httpx.Response(307, headers={"location": "https://data.opensanctions.org/artifacts/eu_fsf/v1/targets.simple.csv"})
        return httpx.Response(200, text=EU_CSV)

    calls = mock_http(handler)
    result = await sanctions_screen("Persoana Mock Inventata")
    assert path.is_file() and result.mode == "live" and result.signal == "rosu"
    assert len(calls) == 2


async def test_synthetic_names_skip_real_list(tmp_path, monkeypatch, no_network):
    path = tmp_path / "eu.csv"
    path.write_text(EU_CSV, encoding="utf-8")
    monkeypatch.setattr(sanctions, "eu_fsf_path", lambda: path)
    result = await sanctions_screen("ZETA MOCK DEMO SRL")
    assert [l["id"] for l in result.data["lists"]] == ["sintetic", "eu_fsf"]
    assert result.data["lists"][1]["status"].startswith("omisă")


def test_normalize_name_drops_legal_forms_and_diacritics():
    assert normalize_name("S.C. Ţepe Şi Înşelăciuni S.R.L.") == "tepe si inselaciuni"
    assert normalize_name("SRL") == "srl"


async def test_too_short_name_fails_soft():
    result = await sanctions_screen("A")
    assert result.ok is False
