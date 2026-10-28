"""Test de fum live pentru OSINT: `python -m versoml.osint.smoke`.

Afișează doar numele tool-ului, ok, modul, semnalul și rezumatul. Folosește ținte publice, fără date de
client, și cel mult două interogări Serper (planul gratuit numără creditele).
"""

from __future__ import annotations

import asyncio
import os
import sys

from versoml.osint import base, search
from versoml.osint.crawl import fetch_page
from versoml.osint.domain import ct_certificates, dns_records, ip_geo, rdap_domain, wayback_first_seen
from versoml.osint.investigate import extract_artifacts, investigate
from versoml.osint.lookalike import lookalike_score
from versoml.osint.registry_ro import anaf_company, bnr_fx_rates, validate_iban
from versoml.osint.sanctions import sanctions_screen
from versoml.osint.search import news_search, web_search
from versoml.osint.threatintel import openphish_check, urlscan_search
from versoml.secrets import install_log_redaction

SERPER_BUDGET = int(os.environ.get("VERSOML_SMOKE_SERPER_BUDGET", "2"))  # 0 = DuckDuckGo în loc de Serper
DEMO_SMS = ("Curier Demo: confirmă livrarea și achită taxa de 4,99 lei: https://livrare-bancademo.example/confirmare?id=7731 "
            "Info: 0700 000 111")


def _limit_serper(budget: int) -> None:
    original = search.PROVIDER_FUNCS["serper"]
    used = {"n": 0}

    async def limited(query, n, kind, key):
        if used["n"] >= budget:
            raise RuntimeError("bugetul Serper al testului de fum s-a terminat")
        used["n"] += 1
        return await original(query, n, kind, key)

    search.PROVIDER_FUNCS["serper"] = limited


def _line(result: base.ToolResult) -> str:
    return f"{result.tool:20} ok={str(result.ok):5} {result.mode:8} {result.signal:7} {result.summary}"


async def main() -> int:
    install_log_redaction()
    _limit_serper(SERPER_BUDGET)
    checks = [
        rdap_domain("example.com"),
        rdap_domain("raiffeisen.ro"),
        dns_records("example.com"),
        ct_certificates("example.com"),
        wayback_first_seen("example.com"),
        ip_geo("1.1.1.1"),
        fetch_page("https://example.com/"),
        openphish_check("example.com"),
        anaf_company("9000000402"),
        bnr_fx_rates(30),
        sanctions_screen("Zzyzx Qwerty Holdings"),
        web_search("DNSC avertizare phishing curierat", n=5),
        news_search("dnsc.ro", n=5),
        urlscan_search("example.com"),
    ]
    with base.override_settings(versoml_osint_mode="live"):
        results = []
        for coro in checks:  # pe rând, ca să respectăm limitele de rată
            results.append(await coro)
        results.append(lookalike_score("raiffeisen-plati.ro"))
        results.append(validate_iban("RO54RZBR0000060012345678"))
    for result in results:
        print(_line(result))
    print("-- investigate pe SMS-ul sintetic (fixtures, fără rețea):")
    for result in await investigate(extract_artifacts(DEMO_SMS)):
        print("   " + _line(result))
    await base.aclose_clients()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
