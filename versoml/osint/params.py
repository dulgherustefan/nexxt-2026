"""Pragurile euristice ale tool-urilor OSINT.

Toate sunt [U]: alese de echipă pentru demo, neverificate într-o sursă oficială. Nu sunt reguli de
decizie (deciziile le ia motorul de reguli); colorează doar semnalele pentru om. Se pot schimba la
rulare cu `set_params()` sau din variabila de mediu `VERSOML_OSINT_PARAMS` (JSON).
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULTS: dict[str, Any] = {
    # vârsta domeniului (RDAP/WHOIS); notele de research sugerează <7 zile foarte puternic, <30 puternic [U]
    "domain_age_red_days": 7,
    "domain_age_yellow_days": 30,
    "domain_age_green_days": 365,
    # primul certificat văzut în CT
    "cert_age_red_hours": 72,
    "cert_age_yellow_days": 30,
    # M3 și M4
    "lookalike_red": 0.85,
    "lookalike_yellow": 0.5,
    "page_similarity_red": 0.7,
    "page_similarity_yellow": 0.45,
    # sancțiuni (scor rapidfuzz 0–100)
    "sanctions_red": 92,
    "sanctions_yellow": 85,
    # firmă înregistrată recent (ANAF)
    "company_new_days": 180,
    # VirusTotal: câte motoare „malicious" fac semnalul roșu
    "vt_malicious_red": 2,
    # presă/forumuri: câte rezultate cu termeni de fraudă fac semnalul roșu
    "news_red_hits": 2,
    # domenii protejate implicit (M3, pagini); se pot da și prin VERSOML_PROTECTED_DOMAINS
    "protected_domains": ["bancademo.example", "curierdemo.example", "raiffeisen.ro"],
    # domenii legitime care nu se marchează ca sosii (de completat de bancă)
    "allowlist_domains": [],
}

_overrides: dict[str, Any] = {}


def _env_overrides() -> dict[str, Any]:
    raw = os.environ.get("VERSOML_OSINT_PARAMS", "").strip()
    result: dict[str, Any] = {}
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                result.update(loaded)
        except json.JSONDecodeError:
            pass
    protected = os.environ.get("VERSOML_PROTECTED_DOMAINS", "").strip()
    if protected:
        result["protected_domains"] = [d.strip().lower() for d in protected.split(",") if d.strip()]
    return result


def get_params() -> dict[str, Any]:
    return {**DEFAULTS, **_env_overrides(), **_overrides}


def param(name: str) -> Any:
    return get_params()[name]


def set_params(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"parametri necunoscuți: {sorted(unknown)}")
    _overrides.update(updates)
    return get_params()


def reset_params() -> None:
    _overrides.clear()
