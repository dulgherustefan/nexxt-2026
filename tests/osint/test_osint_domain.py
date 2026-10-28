"""Domenii: RDAP/WHOIS, DNS (DoH cu rezerve), Certificate Transparency, Wayback, geolocalizarea IP."""

from __future__ import annotations

import httpx
import pytest

from versoml.osint import domain
from versoml.osint.base import FIXTURE_NOW


async def test_rdap_scam_domain_six_hours_old(no_network):
    result = await domain.rdap_domain("https://livrare-bancademo.example/confirmare?id=7731")
    assert result.mode == "fixture" and result.signal == "rosu"
    assert result.args == {"domain": "livrare-bancademo.example"}
    assert result.data["age_hours"] == 6.0
    assert result.data["registrar"] == "Registrar Demo SRL"
    assert result.data["privacy_protected"] is True
    assert result.data["abuse_contact"]["email"] == "abuz@registrar-demo.example"
    assert "acum 6 ore" in result.summary and "ascunse" in result.summary
    assert result.retrieved_at == FIXTURE_NOW
    assert not no_network.calls


@pytest.mark.parametrize("name, days, signal", [
    ("bancadem0-plati.test", 2, "rosu"),
    ("confirmare-colet-demo.example", 1, "rosu"),
    ("securitate-bancademo.test", 3, "rosu"),
])
async def test_rdap_other_scam_domains(name, days, signal, no_network):
    result = await domain.rdap_domain(name)
    assert result.data["age_days"] == days and result.signal == signal


async def test_rdap_legit_domain_is_old_and_green(no_network):
    result = await domain.rdap_domain("www.bancademo.example")
    assert result.args["domain"] == "bancademo.example"
    assert result.signal == "verde" and result.data["privacy_protected"] is False
    assert result.data["created"].startswith("2009-03-17")


async def test_rdap_live_parser_and_404(mock_http):
    rdap = {
        "ldhName": "EXEMPLU-NOU.INVALID",
        "events": [{"eventAction": "registration", "eventDate": "2026-10-27T10:00:00Z"}],
        "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Registrar Mock"]]],
                      "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuz@mock.invalid"]]]}]}],
        "status": ["active"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/exemplu-nou.invalid"):
            return httpx.Response(200, json=rdap)
        return httpx.Response(404, json={"errorCode": 404})

    calls = mock_http(handler)
    found = await domain.rdap_domain("exemplu-nou.invalid")
    assert found.mode == "live" and found.data["registrar"] == "Registrar Mock"
    assert found.data["abuse_contact"]["email"] == "abuz@mock.invalid"
    assert str(calls[0].url) == "https://rdap.org/domain/exemplu-nou.invalid"
    missing = await domain.rdap_domain("nu-exista-deloc.invalid")
    assert missing.ok and missing.signal == "neutru" and "RDAP nu are înregistrare" in missing.summary


def test_rotld_whois_parser():
    text = """
% The WHOIS service offered by ROTLD ...
  Domain Name: domeniu-exemplu.ro
  Registered On: 2026-10-26
  Registrar: Registrar Exemplu
  Domain Status: OK
  Nameserver: ns1.exemplu.invalid
"""
    data = domain.parse_rotld_whois(text, FIXTURE_NOW)
    assert data["registered"] and data["created"].startswith("2026-10-26") and 1.9 < data["age_days"] < 2.5
    old = domain.parse_rotld_whois("  Domain Name: vechi.ro\n  Registered On: Before 2001\n", FIXTURE_NOW)
    assert old["created_before_2001"] is True and old["age_days"] > 9000
    assert domain.parse_rotld_whois("No entries found", FIXTURE_NOW)["registered"] is False


async def test_dns_fixture_scam_has_no_mail_records(no_network):
    result = await domain.dns_records("livrare-bancademo.example")
    assert result.data["A"] == ["203.0.113.45"]
    assert result.data["MX"] == [] and result.data["spf"] is None and result.data["dmarc"] is None
    assert "fără MX, SPF și DMARC" in result.summary or "fără MX, SPF, DMARC" in result.summary


async def test_dns_fixture_legit_bank_is_green(no_network):
    result = await domain.dns_records("bancademo.example")
    assert result.signal == "verde" and result.data["dmarc"].startswith("v=DMARC1; p=reject")


async def test_dns_falls_back_from_cloudflare_to_google(mock_http):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cloudflare-dns.com":
            return httpx.Response(503)
        name = request.url.params["name"]
        if request.url.params["type"] == "A":
            return httpx.Response(200, json={"Status": 0, "Answer": [{"name": name, "type": 1, "data": "198.51.100.9"}]})
        return httpx.Response(200, json={"Status": 0})

    calls = mock_http(handler)
    result = await domain.dns_records("rezerva-dns.invalid")
    assert result.ok and result.data["provider"] == "google" and result.data["A"] == ["198.51.100.9"]
    hosts = [c.url.host for c in calls]
    assert hosts.index("dns.google") > hosts.index("cloudflare-dns.com")
    assert calls[0].headers["accept"] == "application/dns-json"


async def test_ct_scam_cert_five_hours_free_ca(no_network):
    result = await domain.ct_certificates("livrare-bancademo.example")
    assert result.signal == "rosu" and result.data["count"] == 1
    assert result.data["free_ca"] is True and 4.9 < result.data["cert_age_hours"] < 5.1
    assert "1 certificat în total" in result.summary


async def test_ct_legit_has_long_history(no_network):
    result = await domain.ct_certificates("bancademo.example")
    assert result.signal == "verde" and result.data["count"] == 3 and result.data["free_ca"] is False


async def test_ct_falls_back_to_certspotter(mock_http):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "crt.sh":
            return httpx.Response(502)
        return httpx.Response(200, json=[{"id": "1", "dns_names": ["rezerva-ct.invalid"],
                                          "issuer": {"friendly_name": "Let's Encrypt", "name": "C=US, O=Let's Encrypt"},
                                          "not_before": "2026-10-28T08:00:00Z", "not_after": "2027-01-26T08:00:00Z"}])

    mock_http(handler)
    result = await domain.ct_certificates("rezerva-ct.invalid")
    assert result.ok and result.data["provider"] == "certspotter" and result.data["free_ca"] is True


async def test_wayback_none_for_new_domain_and_old_for_legit(no_network):
    new = await domain.wayback_first_seen("livrare-bancademo.example")
    old = await domain.wayback_first_seen("bancademo.example")
    assert new.data["first_seen"] is None and new.signal == "neutru"
    assert old.data["first_seen"].startswith("2010-05-02") and old.signal == "verde"


async def test_wayback_live_cdx(mock_http):
    mock_http(lambda request: httpx.Response(200, json=[["timestamp", "original", "statuscode"],
                                                        ["20200101120000", "http://arhiva.invalid/", "200"]]))
    result = await domain.wayback_first_seen("arhiva.invalid")
    assert result.mode == "live" and result.data["first_seen"].startswith("2020-01-01")


async def test_ip_geo_vps_is_yellow(no_network):
    result = await domain.ip_geo("203.0.113.45")
    assert result.signal == "galben" and result.data["asn"] == "AS64500" and result.data["hosting"] is True


async def test_ip_geo_private_ip_not_looked_up(no_network):
    result = await domain.ip_geo("10.0.0.7")
    assert result.ok and result.mode == "offline" and result.data["public"] is False
    assert not no_network.calls


async def test_ip_geo_live_falls_back_to_ipinfo(mock_http):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "ip-api.com":
            return httpx.Response(200, json={"status": "fail", "message": "quota"})
        return httpx.Response(200, json={"ip": "1.1.1.1", "country": "ZZ", "org": "AS64511 Retea Cloud Mock"})

    mock_http(handler)
    result = await domain.ip_geo("1.1.1.1")
    assert result.data["provider"] == "ipinfo" and result.data["asn"] == "AS64511"
    assert result.data["hosting"] is True and result.signal == "galben"


async def test_invalid_inputs_fail_soft(no_network):
    assert (await domain.rdap_domain("nu e domeniu")).ok is False
    assert (await domain.ip_geo("999.1.1.1")).ok is False
    assert (await domain.dns_records("")).ok is False
