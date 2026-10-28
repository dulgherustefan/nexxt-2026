"""Verificarea numerică a ciornei RTS: fiecare sumă, dată, fragment de IBAN și ID de caz trebuie să vină din dosarul AML.

Ciorna o scrie un model; cifrele trebuie să fie exact cele din probele AX-... Modulul citește valorile din text în
formatele folosite în zona AML ("3200 RON", "3.200,00 lei", "RON 3,200.00", "28.10.2026", "28 octombrie 2026",
"RO61 BDEM •••• 4471", "CT-2026-123456", "PL-ABC123") și le caută în conținutul probelor. O valoare care nu e în
dosar e o nepotrivire; valoarea cea mai apropiată de același fel e cea așteptată. Determinist, fără LLM.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bucharest")
LUNI = {"ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
        "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12, "ian": 1, "feb": 2, "mar": 3, "apr": 4,
        "iun": 6, "iul": 7, "aug": 8, "sep": 9, "oct": 10, "noi": 11, "nov": 11, "dec": 12, "january": 1,
        "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "september": 9, "october": 10,
        "november": 11, "december": 12, "jan": 1, "jun": 6, "jul": 7}
_LUNA = "|".join(sorted(LUNI, key=len, reverse=True))
_NUM = r"\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
SUMA_RE = re.compile(rf"\b(RON|EUR|lei)\s?({_NUM})(?!\d)|(?<![\d.,])({_NUM})\s?(RON|EUR|lei)\b", re.I)
DATA_RE = re.compile(rf"\b(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})\b|\b(\d{{4}})-(\d{{2}})-(\d{{2}})\b"
                     rf"|\b(\d{{1,2}})\s+({_LUNA})\.?\s+(\d{{4}})\b", re.I)
IBAN_RE = re.compile(r"\bRO\d{2}\s?[A-Z]{4}(?:\s?[0-9A-Z]{4}){4}\b")
IBAN_MASCAT_RE = re.compile(r"\b(RO\d{2})\s?([A-Z]{4})?\s?(?:[•*.…x]{2,}\s?)+(\d{4})\b")
CAZ_RE = re.compile(r"\b(?:CT-\d{4}-\d{6}|PL-[A-Z0-9]{6})\b")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$")
CHEI_SUMA = ("amount", "value", "amount_in", "amount_out", "amount_total", "suma")


def _numar(raw: str) -> float | None:
    s = raw.replace(" ", "")
    if "," in s and "." in s:
        zec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if zec == "," else ",", "").replace(zec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        cap, _, coada = s.rpartition(sep)
        s = s.replace(sep, "") if len(coada) == 3 else cap.replace(sep, "") + "." + coada
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _local(value: Any) -> datetime | None:
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(TZ)


def extrage(text: str) -> list[dict]:
    """Valorile din text: [{kind, raw, value}], cu kind în amount, date, iban, iban_tail, case_id."""
    text = text or ""
    out: list[dict] = []
    ocupat: list[tuple[int, int]] = []

    def liber(m: re.Match) -> bool:
        return not any(a <= m.start() < b for a, b in ocupat)

    for m in CAZ_RE.finditer(text):
        out.append({"kind": "case_id", "raw": m.group(0), "value": m.group(0)})
        ocupat.append(m.span())
    for m in IBAN_RE.finditer(text):
        out.append({"kind": "iban", "raw": m.group(0), "value": m.group(0).replace(" ", "").upper()})
        ocupat.append(m.span())
    for m in IBAN_MASCAT_RE.finditer(text):
        if liber(m):
            out.append({"kind": "iban_tail", "raw": m.group(0), "value": m.group(3)})
            ocupat.append(m.span())
    for m in DATA_RE.finditer(text):
        if not liber(m):
            continue
        try:
            if m.group(1):
                zi = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            elif m.group(4):
                zi = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
            else:
                zi = date(int(m.group(9)), LUNI[m.group(8).lower()], int(m.group(7)))
        except (ValueError, KeyError):
            continue
        out.append({"kind": "date", "raw": m.group(0), "value": zi})
        ocupat.append(m.span())
    for m in SUMA_RE.finditer(text):
        if not liber(m):
            continue
        valoare = _numar(m.group(2) or m.group(3))
        if valoare is not None:
            out.append({"kind": "amount", "raw": m.group(0).strip(), "value": valoare})
    return out


class Permise:
    """Valorile din dosarul AML, pe tipuri."""

    def __init__(self) -> None:
        self.sume: set[float] = set()
        self.date: set[date] = set()
        self.ibanuri: set[str] = set()
        self.cazuri: set[str] = set()

    def adauga(self, continut: Any, cheie: str = "") -> None:
        if isinstance(continut, dict):
            for k, v in continut.items():
                self.adauga(v, str(k))
        elif isinstance(continut, (list, tuple)):
            for v in continut:
                self.adauga(v, cheie)
        elif isinstance(continut, bool) or continut is None:
            return
        elif isinstance(continut, (int, float)):
            if any(k in cheie.lower() for k in CHEI_SUMA) and continut > 0:
                self.sume.add(round(float(continut), 2))
        elif isinstance(continut, str):
            s = continut.strip()
            if ISO_RE.match(s):
                local = _local(s)
                if local:
                    self.date.add(local.date())
            elif CAZ_RE.fullmatch(s):
                self.cazuri.add(s)
            elif IBAN_RE.fullmatch(s.upper()):
                self.ibanuri.add(s.replace(" ", "").upper())
            else:
                for m in CAZ_RE.finditer(s):
                    self.cazuri.add(m.group(0))


def permise_din(fapte: Iterable[Any], lead_id: str) -> Permise:
    p = Permise()
    p.cazuri.add(lead_id)
    for f in fapte:
        data = f.model_dump(mode="json") if hasattr(f, "model_dump") else dict(f)
        p.adauga(data.get("content") or {})
    return p


def _cel_mai_apropiat(kind: str, valoare: Any, p: Permise) -> str:
    if kind == "amount":
        return f"{min(p.sume, key=lambda x: abs(x - valoare)):.2f} RON" if p.sume else "nicio sumă în dosar"
    if kind == "date":
        return min(p.date, key=lambda d: abs((d - valoare).days)).strftime("%d.%m.%Y") if p.date else "nicio dată în dosar"
    if kind == "case_id":
        return ", ".join(sorted(p.cazuri)[:3]) or "niciun caz în dosar"
    return next((f"{i[:4]} {i[4:8]} •••• {i[-4:]}" for i in sorted(p.ibanuri)), "niciun IBAN în dosar")


def _ok(kind: str, valoare: Any, p: Permise) -> bool:
    if kind == "amount":
        return any(abs(x - valoare) < 0.005 for x in p.sume)
    if kind == "date":
        return valoare in p.date
    if kind == "case_id":
        return valoare in p.cazuri
    if kind == "iban":
        return valoare in p.ibanuri
    if kind == "iban_tail":
        return any(i.endswith(valoare) for i in p.ibanuri)
    return True


def verifica(sectiuni: list[tuple[str, str]], p: Permise) -> dict:
    """{passed, checked, mismatches: [{value, expected, where}]} pentru [(unde, text)]."""
    verificate = 0
    gresite: list[dict] = []
    for unde, text in sectiuni:
        for v in extrage(text):
            verificate += 1
            if not _ok(v["kind"], v["value"], p):
                gresite.append({"value": v["raw"], "expected": _cel_mai_apropiat(v["kind"], v["value"], p),
                                "where": unde, "kind": v["kind"]})
    return {"passed": not gresite, "checked": verificate, "mismatches": gresite}


def sectiuni_rts(out: Any) -> list[tuple[str, str]]:
    """Textele ciornei RTS (titlu, rezumat, indicatori, narațiune, măsuri), cu locul lor."""
    sec = [("titlu", out.title), ("rezumat", out.suspicion_summary)]
    sec += [(f"indicator {i}", x) for i, x in enumerate(out.indicators, 1)]
    sec += [(f"fraza {i}", line.text) for i, line in enumerate(out.narrative, 1)]
    sec += [(f"măsura {i}", x) for i, x in enumerate(out.recommended_measures, 1)]
    return sec


def feedback(gresite: list[dict]) -> str:
    linii = [f"- {m['where']}: ai scris „{m['value']}”, dar dosarul are {m['expected']}" for m in gresite]
    return ("\n\nVerificarea numerică a oprit ciorna anterioară: aceste valori nu sunt în dosar.\n" + "\n".join(linii)
            + "\nRescrie ciorna și copiază exact fiecare sumă, dată și ID din probe.")
