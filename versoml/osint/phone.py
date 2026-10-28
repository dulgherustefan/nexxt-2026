"""Telefoane: normalizare E.164, tipul numărului românesc și raportările publice ale numărului (web/forumuri).

Tipul se deduce din prima cifră a numărului național [U]: 7 = mobil, 2/3 = fix (geografic),
800 = apel gratuit, 801 = cost partajat, 90x = tarif special. Operatorul nu se poate afla din
numerotație (portabilitatea numerelor), așa că nu îl ghicim.
"""

from __future__ import annotations

import time
from typing import Any

from versoml.osint.base import ToolResult, failure, tool
from versoml.osint.search import annotate, news_signal, web_search
from versoml.osint.util import is_synthetic_phone, normalize_phone, normalize_ro


def classify(e164: str) -> dict[str, Any]:
    """Tipul și forma națională a unui număr E.164."""
    info: dict[str, Any] = {"e164": e164, "synthetic": is_synthetic_phone(e164), "type_confidence": "U",
                            "operator": None,
                            "operator_note": "nedeterminabil din numerotație (portabilitatea numerelor)"}
    if not e164.startswith("+40"):
        info.update({"country": "străin", "type": "internațional", "national": None})
        return info
    nsn = e164[3:]
    info["country"] = "RO"
    info["national"] = f"0{nsn[:3]} {nsn[3:6]} {nsn[6:]}"
    if nsn.startswith("7"):
        kind = "mobil"
    elif nsn.startswith(("21", "31")):
        kind = "fix (București)"
    elif nsn[0] in "23":
        kind = "fix (geografic)"
    elif nsn.startswith("800"):
        kind = "apel gratuit"
    elif nsn.startswith("801"):
        kind = "cost partajat"
    elif nsn.startswith("90"):
        kind = "tarif special"
    else:
        kind = "necunoscut"
    info["type"] = kind
    return info


def search_query(e164: str) -> str:
    nsn = e164[3:] if e164.startswith("+40") else e164.lstrip("+")
    if e164.startswith("+40"):
        variants = [f"0{nsn}", e164, f"0{nsn[:3]} {nsn[3:6]} {nsn[6:]}"]
    else:
        variants = [e164]
    return " OR ".join(f'"{v}"' for v in variants)


@tool("phone_intel", zones=("aml",), group="osint-ro")
async def phone_intel(phone: str) -> ToolResult:
    """Normalizează numărul (E.164), îi spune tipul (mobil/fix/special) și caută raportări publice ale lui (țepe, apeluri false)."""
    started = time.perf_counter()
    raw = normalize_ro(phone).strip()
    e164 = normalize_phone(raw)
    if e164 is None:
        return failure("phone_intel", {"phone": raw}, f"Număr de telefon nerecunoscut: {raw}.", error="număr invalid")
    args = {"phone": e164}
    info = classify(e164)
    search = await web_search(search_query(e164), n=8)
    reports = [r for r in annotate(search.data.get("results", []), e164) if r.get("mentions_entity")]
    hits, signal = news_signal(reports, e164)
    data = {**info, "reports": reports, "report_count": len(reports), "fraud_reports": hits,
            "search": {"query": search.args.get("query"), "mode": search.mode, "ok": search.ok,
                       "provider": search.data.get("provider"), "error": search.error}}
    shown = info.get("national") or e164
    kind = info["type"] + (", sintetic" if info["synthetic"] else "")
    if hits:
        summary = (f"Numărul {shown} ({kind}) apare în {hits} raportări publice cu termeni de fraudă "
                   f"(din {len(reports)} mențiuni).")
    elif reports:
        summary = f"Numărul {shown} ({kind}) apare în {len(reports)} pagini, fără mențiuni de fraudă."
    elif search.ok:
        summary = f"Numărul {shown} ({kind}): nicio raportare publică găsită."
    else:
        summary = f"Numărul {shown} ({kind}); căutarea raportărilor nu a reușit: {search.summary}"
    return ToolResult(tool="phone_intel", args=args, ok=True, data=data, summary=summary, signal=signal,
                      source_url=search.source_url, retrieved_at=search.retrieved_at,
                      mode=search.mode if search.ok else "offline",
                      latency_ms=int((time.perf_counter() - started) * 1000))
