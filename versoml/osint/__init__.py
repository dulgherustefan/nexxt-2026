"""OSINT și inteligență de domeniu pentru VersoML (docs/06 §4.3).

Toate tool-urile întorc `ToolResult`; cele de rețea sunt async, rapide, nu ridică excepții și respectă
modul `VERSOML_OSINT_MODE` (fixture | live | auto). Registrul pentru serverul MCP: `list_tools()`,
`get_tool(name)`, `call_tool(name, args)`. Sursele și condițiile lor: `versoml/osint/SOURCES.md`.
"""

from versoml.osint.base import ToolResult, call_tool, get_tool, list_tools
from versoml.osint.crawl import fetch_page
from versoml.osint.domain import ct_certificates, dns_records, ip_geo, rdap_domain, wayback_first_seen
from versoml.osint.investigate import extract_artifacts, investigate, plan
from versoml.osint.lookalike import lookalike_score
from versoml.osint.page_similarity import page_similarity, page_similarity_url
from versoml.osint.phone import phone_intel
from versoml.osint.registry_ro import anaf_company, bnr_fx_rates, validate_iban
from versoml.osint.sanctions import sanctions_screen
from versoml.osint.search import news_search, web_search
from versoml.osint.threatintel import (
    openphish_check,
    safe_browsing_check,
    urlhaus_check,
    urlscan_search,
    virustotal_domain,
)

__all__ = [
    "ToolResult", "anaf_company", "bnr_fx_rates", "call_tool", "ct_certificates", "dns_records",
    "extract_artifacts", "fetch_page", "get_tool", "investigate", "ip_geo", "list_tools", "lookalike_score",
    "news_search", "openphish_check", "page_similarity", "page_similarity_url", "phone_intel", "plan",
    "rdap_domain", "safe_browsing_check", "sanctions_screen", "urlhaus_check", "urlscan_search",
    "validate_iban", "virustotal_domain", "wayback_first_seen", "web_search",
]
