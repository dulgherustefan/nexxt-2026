"""The numeric verifier: every amount, date, time, IBAN fragment and case ID in a draft must come from the ledger.

The letter writer copies numbers from the case data, and a model can still get one wrong. Before a letter goes out,
this module reads every number in the draft in the formats of versoml/zone_client/fmt.py ("RON 3,200.00",
"29 Oct 2026, 23:59", "29 Oct", "RO61 BDEM •••• 4471", "CT-2026-123456") and looks for it among the values recorded
in the case's ledger facts. A value the ledger does not hold is a mismatch; the closest recorded value of the same
kind is the expected one. Deterministic, no LLM.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

from versoml.zone_client.fmt import MONTHS, fmt_date, money, to_local

_MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}
_MONTH_NUM.update({"january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7, "august": 8,
                   "september": 9, "sept": 9, "october": 10, "november": 11, "december": 12})
_MONTH_ALT = "|".join(sorted(_MONTH_NUM, key=len, reverse=True))
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
AMOUNT_RE = re.compile(rf"\b(RON|EUR|lei)\s?({_NUM})\b|\b({_NUM})\s?(RON|EUR|lei)\b", re.I)
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\.?(?:,?\s+(\d{{4}}))?\b|\b({_MONTH_ALT})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b"
                     r"|\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", re.I)
TIME_RE = re.compile(r"(?<![\d:.])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
IBAN_RE = re.compile(r"\bRO\d{2}\s?[A-Z]{4}(?:\s?[0-9A-Z]{4}){4}\b")
MASKED_IBAN_RE = re.compile(r"\b(RO\d{2})\s?([A-Z]{4})?\s?(?:[•*.…x]{2,}\s?)+(\d{4})\b")
TAIL_RE = re.compile(r"\b(?:account|IBAN)\s+ending\s+(?:in\s+)?(\d{4})\b", re.I)
CASE_RE = re.compile(r"\bCT-\d{4}-\d{6}\b")
ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$")
AMOUNT_KEYS = ("amount", "value", "shown_amount", "balance_after", "amount_total", "refunded")


def _parse_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _date_from(m: re.Match, year_hint: int) -> date | None:
    try:
        if m.group(1):
            month = _MONTH_NUM[m.group(2).lower()]
            return date(int(m.group(3)) if m.group(3) else year_hint, month, int(m.group(1)))
        if m.group(4):
            return date(int(m.group(6)), _MONTH_NUM[m.group(4).lower()], int(m.group(5)))
        if m.group(7):
            return date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
        return date(int(m.group(12)), int(m.group(11)), int(m.group(10)))
    except (ValueError, KeyError):
        return None


def extract(text: str, *, year_hint: int | None = None) -> list[dict]:
    """The values a draft states: [{kind, raw, value, start}] with kind in amount, date, time, iban, case_id.
    The customer's own words, quoted in the letter (“...”), are theirs, not the bank's: they are not checked."""
    text = re.sub(r"“[^”]*”", lambda m: " " * len(m.group(0)), text or "")
    year = year_hint or datetime.now().year
    out: list[dict] = []
    spans: list[tuple[int, int]] = []

    def add(kind: str, m: re.Match, value: Any, group: int = 0) -> None:
        out.append({"kind": kind, "raw": m.group(group).strip(), "value": value, "start": m.start(group)})
        spans.append((m.start(group), m.end(group)))

    for m in CASE_RE.finditer(text):
        add("case_id", m, m.group(0))
    for m in IBAN_RE.finditer(text):
        add("iban", m, m.group(0).replace(" ", "").upper())
    for m in MASKED_IBAN_RE.finditer(text):
        if not any(a <= m.start() < b for a, b in spans):
            add("iban_tail", m, (m.group(1).upper(), m.group(3)))
    for m in TAIL_RE.finditer(text):
        add("iban_tail", m, (None, m.group(1)))
    for m in AMOUNT_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        value = _parse_number(m.group(2) or m.group(3))
        currency = (m.group(1) or m.group(4) or "RON").upper().replace("LEI", "RON")
        if value is not None:
            add("amount", m, (round(value, 2), currency))
    for m in DATE_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        day = _date_from(m, year)
        if day:
            add("date", m, day)
    for m in TIME_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        add("time", m, f"{int(m.group(1)):02d}:{m.group(2)}")
    return sorted(out, key=lambda v: v["start"])


def _walk(value: Any, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, str(k))
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v, key)
    else:
        yield key, value


class Allowed:
    """The values the ledger holds, by kind."""

    def __init__(self) -> None:
        self.amounts: set[tuple[float, str]] = set()
        self.dates: set[date] = set()
        self.times: set[str] = set()
        self.ibans: set[str] = set()
        self.case_ids: set[str] = set()

    def add_datetime(self, value: Any) -> None:
        local = to_local(value)
        if local is None:
            return
        self.dates.add(local.date())
        if isinstance(value, datetime) or (isinstance(value, str) and ("T" in value or " " in value.strip())):
            self.times.add(f"{local:%H:%M}")

    def add_content(self, content: Any, currency: str = "RON") -> None:
        cur = currency
        if isinstance(content, dict) and isinstance(content.get("currency"), str):
            cur = content["currency"].upper()
        for key, value in _walk(content):
            low = key.lower()
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)) and any(k in low for k in AMOUNT_KEYS) and value > 0:
                self.amounts.add((round(float(value), 2), cur))
            elif isinstance(value, datetime):
                self.add_datetime(value)
            elif isinstance(value, str):
                if ISO_DT.match(value.strip()):
                    self.add_datetime(value.strip())
                elif CASE_RE.fullmatch(value.strip()):
                    self.case_ids.add(value.strip())
                elif IBAN_RE.fullmatch(value.strip().upper()):
                    self.ibans.add(value.strip().replace(" ", "").upper())


def allowed_from_facts(facts: Iterable[Any], case_id: str, *, include_untrusted_kinds: Iterable[str] = ()) -> Allowed:
    """The values a letter may state: those in the case's trusted ledger facts, plus the kinds of untrusted facts
    named in `include_untrusted_kinds` (the customer's statements, on the declared-facts path)."""
    allowed = Allowed()
    allowed.case_ids.add(case_id)
    extra = set(include_untrusted_kinds)
    for f in facts:
        data = f.model_dump(mode="json") if hasattr(f, "model_dump") else dict(f)
        trust = ((data.get("labels") or {}).get("trust") or "trusted")
        if trust != "trusted" and data.get("kind") not in extra:
            continue
        content = data.get("content") or {}
        allowed.add_content(content, (content.get("currency") or "RON") if isinstance(content, dict) else "RON")
    return allowed


def _closest(kind: str, value: Any, allowed: Allowed) -> str:
    if kind == "amount":
        pool = [a for a in allowed.amounts if a[1] == value[1]] or list(allowed.amounts)
        if not pool:
            return "no amount on file"
        best = min(pool, key=lambda a: abs(a[0] - value[0]))
        return money(best[0], best[1])
    if kind == "date":
        if not allowed.dates:
            return "no date on file"
        return fmt_date(min(allowed.dates, key=lambda d: abs((d - value).days)))
    if kind == "time":
        if not allowed.times:
            return "no time on file"
        mins = lambda t: int(t[:2]) * 60 + int(t[3:])  # noqa: E731
        return min(allowed.times, key=lambda t: abs(mins(t) - mins(value)))
    if kind == "case_id":
        return sorted(allowed.case_ids)[0] if allowed.case_ids else "no case ID on file"
    if kind in ("iban", "iban_tail"):
        return next((f"{i[:4]} {i[4:8]} •••• {i[-4:]}" for i in sorted(allowed.ibans)), "no IBAN on file")
    return ""


def _ok(kind: str, value: Any, allowed: Allowed) -> bool:
    if kind == "amount":
        return any(abs(a - value[0]) < 0.005 and c == value[1] for a, c in allowed.amounts)
    if kind == "date":
        return value in allowed.dates
    if kind == "time":
        return value in allowed.times
    if kind == "case_id":
        return value in allowed.case_ids
    if kind == "iban":
        return value in allowed.ibans
    if kind == "iban_tail":
        country, tail = value
        return any(i.endswith(tail) and (country is None or i.startswith(country)) for i in allowed.ibans)
    return True


def check(sections: list[tuple[str, str]], allowed: Allowed, *, year_hint: int | None = None) -> dict:
    """Checks every value in [(where, text)] against the ledger: {passed, checked, mismatches: [{value, expected,
    where}]}."""
    checked = 0
    mismatches: list[dict] = []
    years = [d.year for d in allowed.dates]
    hint = year_hint or (max(years) if years else None)
    for where, text in sections:
        for v in extract(text, year_hint=hint):
            checked += 1
            if not _ok(v["kind"], v["value"], allowed):
                mismatches.append({"value": v["raw"], "expected": _closest(v["kind"], v["value"], allowed),
                                   "where": where, "kind": v["kind"]})
    return {"passed": not mismatches, "checked": checked, "mismatches": mismatches}


def sections_of(subject: str, paragraphs: Iterable[str]) -> list[tuple[str, str]]:
    return [("subject", subject or "")] + [(f"paragraph {i}", p) for i, p in enumerate(paragraphs, 1)]


def feedback(mismatches: list[dict]) -> str:
    """The rewrite instruction: each wrong value with the value on file."""
    lines = [f"- {m['where']}: you wrote “{m['value']}”, but the case file has {m['expected']}" for m in mismatches]
    return ("\n\nThe numeric check stopped the previous draft: these values are not in the case file.\n" + "\n".join(lines)
            + "\nWrite the letter again and copy every amount, date, time and ID exactly from the case data.")
