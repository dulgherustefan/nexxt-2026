"""The numeric verifier: every amount, date, time, IBAN fragment, case ID, phone number and link in a draft must come
from the ledger.

The letter writer copies numbers from the case data, and a model can still get one wrong. Before a letter goes out,
this module reads every number in the draft, in the English formats of versoml/zone_client/fmt.py ("RON 3,200.00",
"29 Oct 2026, 23:59") and the Romanian ones ("3.200,00 lei", "29 octombrie 2026, ora 23:59", "29.10.2026"), plus
"RO61 BDEM •••• 4471" and "CT-2026-123456", and looks for it among the values recorded in the case's ledger facts. A
value the ledger does not hold is a mismatch; the closest recorded value of the same kind is the expected one.

The check knows what a value stands for. A date after "by" or "până la" is a deadline and must be one of the case's
deadlines, a date next to "you told us" is the day the customer reported, and a date that goes with the payment is
the payment date; amounts work the same way (the payment, the refund, the customer's share). A value that is on
file but in the wrong role is a mismatch too. Phone numbers must be the bank's, and links must point to the bank or
to a public authority. Deterministic, no LLM.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from versoml.data.artifacts import BANK_OFFICIAL_PHONE, LEGIT_BRAND_DOMAIN
from versoml.zone_client.fmt import MONTHS, MONTHS_RO, TZ, fmt_date, money, to_local

_MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}
_MONTH_NUM.update({"january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7, "august": 8,
                   "september": 9, "sept": 9, "october": 10, "november": 11, "december": 12})
_MONTH_NUM.update({m: i + 1 for i, m in enumerate(MONTHS_RO)})
_MONTH_NUM.update({"ian": 1, "iun": 6, "iul": 7})
_MONTH_ALT = "|".join(sorted(_MONTH_NUM, key=len, reverse=True))
# "3,200.00" and "3.200,00" alike: groups of three are thousands, one or two digits after the last mark are decimals
_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CUR = r"RON|EUR|EURO|lei|leu|euro"
AMOUNT_RE = re.compile(rf"\b({_CUR})\s?({_NUM})(?![\d.,]*\d)|\b({_NUM})\s?(?:de\s+)?({_CUR})\b", re.IGNORECASE)
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\.?(?:,?\s+(\d{{4}}))?\b|\b({_MONTH_ALT})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b"
                     r"|\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", re.IGNORECASE)
TIME_RE = re.compile(r"(?<![\d:.])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
IBAN_RE = re.compile(r"\bRO\d{2}\s?[A-Z]{4}(?:\s?[0-9A-Z]{4}){4}\b")
MASKED_IBAN_RE = re.compile(r"\b(RO\d{2})\s?([A-Z]{4})?\s?(?:[•*.…x]{2,}\s?)+(\d{4})\b")
TAIL_RE = re.compile(r"\b(?:account|IBAN|contul|contului)\s+(?:ending|care\s+se\s+termin[ăa])\s+(?:in\s+|în\s+|cu\s+)?(\d{4})\b",
                     re.IGNORECASE)
CASE_RE = re.compile(r"\bCT-\d{4}-\d{6}\b")
PHONE_RE = re.compile(r"(?<![\w+])(?:\+|00)40[\s.-]?\(?\d{2,3}\)?(?:[\s.-]?\d{2,4}){2,3}(?!\d)"
                      r"|(?<![\w.,])0\d{2,3}(?:[\s.-]?\d{3,4}){2}(?![\d.,]*\d)")
URL_RE = re.compile(r"\bhttps?://[^\s<>\"'”)]+|\bwww\.[^\s<>\"'”)]+"
                    r"|\b(?:[a-z0-9-]+\.)+(?:ro|com|net|org|eu|info|xyz|top|online|site|example|test|app|io|biz)\b"
                    r"(?:/[^\s<>\"'”)]*)?", re.IGNORECASE)
QUOTED_RE = re.compile(r"“[^”]*”|„[^”]*”")
ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$")
AMOUNT_KEYS = ("amount", "value", "shown_amount", "balance_after", "amount_total", "refunded", "debited",
               "payer_liability")
# the links a letter may give: the bank's own site and the public bodies it names
OFFICIAL_HOSTS = (LEGIT_BRAND_DOMAIN, "anpc.ro", "anpc.gov.ro", "anaf.ro", "bnr.ro", "csalb.ro", "dnsc.ro",
                  "politiaromana.ro")

# what a recorded value stands for, from its field name
_DATE_ROLE_KEYS = {
    "report": ("notified_at", "reported_at", "complaint_received_at", "received_at", "loss_reported_at",
               "customer_told_at"),
    "payment": ("executed_at", "made_at", "ts", "booked_at", "value_date", "date", "transaction_date",
                "processing_date"),
}
ROLE_WORDS = {"deadline": "a deadline", "report": "the day the customer reported", "payment": "the payment date",
              "refund": "the refund", "share": "the customer's share"}

# what a value in the draft stands for, from the words around it (matched on the folded sentence)
_DEADLINE_BEFORE = re.compile(r"(?:\bby|\buntil|\bbefore|\bno\s+later\s+than|\bdue(?:\s+on)?|\bdeadline(?:\s+is)?"
                              r"|\bpana\s+(?:la|pe|in)(?:\s+data\s+de)?|\bcel\s+tarziu(?:\s+(?:la|pe|in))?"
                              r"(?:\s+data\s+de)?|\btermen\w*(?:\s+(?:limita|este))?(?:\s+(?:de|pana\s+la|la))?)"
                              r"\s*(?:the\s+end\s+of\s*|sfarsitul\s+zilei\s+de\s*)?$")
_REPORT_BEFORE = re.compile(r"(?:\btold\s+us(?:\s+about\s+(?:it|this))?|\breported\s+(?:it|this|the\s+\w+\s*)?"
                            r"|\bcontacted\s+us|\breceived\s+your\s+(?:claim|complaint)|\byour\s+report,?"
                            r"|\bne-ati\s+(?:anuntat|informat|spus|scris|contactat|semnalat)|\bati\s+(?:semnalat|sesizat|reclamat)"
                            r"|\bam\s+primit\s+reclamatia\s+dumneavoastra)\s*(?:on|pe|in|la|din)?\s*$")
_REPORT_AFTER = re.compile(r"^\s*,?\s*(?:you\s+(?:told|reported|contacted|wrote)|we\s+received|ne-ati\s+(?:spus|anuntat"
                           r"|informat|scris|contactat|semnalat)|ati\s+(?:semnalat|sesizat|raportat|reclamat)|am\s+primit)")
_LEAD_IN = re.compile(r"\s*(?:on|pe|in|la|din|in\s+data\s+de)?\s*,?\s*")
_PAYMENT_NOUN = re.compile(r"\b(?:payment|transfer|transaction|charge|debit|plat[aăi]\w*|transfer\w*|tranzacti\w*)\b")
_PAYMENT_BEFORE = re.compile(r"(?:\bon|\bof|\bfrom|\bmade(?:\s+on)?|\bpaid(?:\s+on)?|\bdebited(?:\s+on)?|\bdin"
                             r"|\bpe|\bin\s+data\s+de|\bdin\s+data\s+de|\befectuat\w*(?:\s+(?:pe|in|la))?),?\s*$")
_REFUND_BEFORE = re.compile(r"(?:\brefund(?:ed)?(?:\s+you)?|\brefund\s+of|\breturned|\bramburs\w*(?:\s+integral)?"
                            r"|\bv-am\s+rambursat(?:\s+integral)?|\bvom\s+rambursa(?:\s+integral)?)\s*"
                            r"(?:the\s+full\s+amount\s+of\s*|(?:integral\s+)?suma\s+de\s*)?$")
_SHARE_BEFORE = re.compile(r"(?:\bfirst|\bprimii|\bprimele|\bshare\s+of|\bpartea\s+de)\s*$")
_PAYMENT_AMOUNT_BEFORE = re.compile(r"(?:\b(?:payment|transfer|transaction|charge)\s+of|\bin\s+valoare\s+de"
                                    r"|\b(?:plata|transferul|tranzactia)\s+de)\s*$")
_PAYMENT_AMOUNT_AFTER = re.compile(r"^\s*(?:card\s+payment|payment|transfer|instant\s+transfer|transaction)\b")


def _fold(text: str) -> str:
    """Lower case, no diacritics, same length (the role cues are matched on it)."""
    return "".join((unicodedata.normalize("NFKD", ch)[:1] if ch.isalpha() else ch) for ch in text).lower()


def parse_number(raw: str) -> float | None:
    """'3,200.00', '3.200,00', '3.200', '2,99' or '2.99': the last mark with one or two digits after it is the
    decimal point; groups of three are thousands."""
    s = (raw or "").strip()
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        head, _, tail = s.rpartition(sep)
        s = s.replace(sep, "") if len(tail) == 3 else head.replace(sep, "") + "." + tail
    try:
        return float(s)
    except ValueError:
        return None


def phone_key(raw: str) -> str:
    """The national number, digits only: "+40 700 000 100" and "0700 000 100" -> "700000100"."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0040"):
        return digits[4:]
    if digits.startswith("40") and len(digits) == 11:
        return digits[2:]
    return digits.removeprefix("0")


def host_of(raw: str) -> str:
    host = re.sub(r"^https?://", "", (raw or "").strip().lower()).split("/")[0].split("?")[0]
    host = host.rsplit("@", 1)[-1].rstrip(".,;:")
    return host.removeprefix("www.")


def _date_from(m: re.Match, year_hint: int) -> date | None:
    try:
        if m.group(1):
            month = m.group(2).lower()
            # "mai" is also the Romanian for "more": without a year it is not read as a date
            if month == "mai" and not m.group(3):
                return None
            return date(int(m.group(3)) if m.group(3) else year_hint, _MONTH_NUM[month], int(m.group(1)))
        if m.group(4):
            return date(int(m.group(6)), _MONTH_NUM[m.group(4).lower()], int(m.group(5)))
        if m.group(7):
            return date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
        return date(int(m.group(12)), int(m.group(11)), int(m.group(10)))
    except (ValueError, KeyError):
        return None


# a mark ends a sentence when a space follows it and it does not close an abbreviation ("art. 173", "29 oct. 2026")
_SENTENCE_END = re.compile(r"[!?\n]|(?<!\bart)(?<!\bnr)(?<!\balin)(?<!\blit)(?<!\bstr)(?<!\boct)(?<!\bnov)(?<!\bdec)"
                           r"(?<!\bian)(?<!\bfeb)(?<!\bmar)(?<!\bapr)(?<!\biun)(?<!\biul)(?<!\baug)(?<!\bsep)\.(?=\s|$)",
                           re.IGNORECASE)


def _sentence_bounds(text: str, start: int, end: int) -> tuple[str, str]:
    """The folded text of the sentence before and after a value."""
    left = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    right = next((m.start() for m in _SENTENCE_END.finditer(text, end)), len(text))
    return _fold(text[left:start]), _fold(text[end:right])


def _date_role(text: str, start: int, end: int) -> str | None:
    before, after = _sentence_bounds(text, start, end)
    if _DEADLINE_BEFORE.search(before):
        return "deadline"
    if _REPORT_BEFORE.search(before) or (_LEAD_IN.fullmatch(before) and _REPORT_AFTER.search(after)):
        return "report"
    if _PAYMENT_BEFORE.search(before) and _PAYMENT_NOUN.search(before):
        return "payment"
    return None


def _amount_role(text: str, start: int, end: int) -> str | None:
    before, after = _sentence_bounds(text, start, end)
    if _SHARE_BEFORE.search(before):
        return "share"
    if _REFUND_BEFORE.search(before):
        return "refund"
    if _PAYMENT_AMOUNT_BEFORE.search(before) or _PAYMENT_AMOUNT_AFTER.search(after):
        return "payment"
    return None


def extract(text: str, *, year_hint: int | None = None) -> list[dict]:
    """The values a draft states: [{kind, raw, value, start, role}] with kind in amount, date, time, iban,
    iban_tail, case_id, phone and url, and role (for dates and amounts) when the words around the value say it.
    The customer's own words, quoted in the letter (“...” or „...”), are theirs, not the bank's: their numbers are
    not checked. Phone numbers and links are checked everywhere, quotes included."""
    text = text or ""
    masked = QUOTED_RE.sub(lambda m: " " * len(m.group(0)), text)
    year = year_hint or datetime.now(TZ).year
    out: list[dict] = []
    spans: list[tuple[int, int]] = []

    def taken(m: re.Match, group: int = 0) -> bool:
        return any(a <= m.start(group) < b or a < m.end(group) <= b for a, b in spans)

    def add(kind: str, m: re.Match, value: Any, group: int = 0, role: str | None = None) -> None:
        raw = m.group(group).strip()
        out.append({"kind": kind, "raw": raw.rstrip(".,;:") if kind == "url" else raw, "value": value,
                    "start": m.start(group), "role": role})
        spans.append((m.start(group), m.end(group)))

    for m in CASE_RE.finditer(masked):
        add("case_id", m, m.group(0))
    for m in IBAN_RE.finditer(masked):
        add("iban", m, m.group(0).replace(" ", "").upper())
    for m in MASKED_IBAN_RE.finditer(masked):
        if not taken(m):
            add("iban_tail", m, (m.group(1).upper(), m.group(3)))
    for m in TAIL_RE.finditer(masked):
        add("iban_tail", m, (None, m.group(1)))
    for m in URL_RE.finditer(text):
        if not taken(m):
            add("url", m, host_of(m.group(0).rstrip(".,;:")))
    for m in PHONE_RE.finditer(text):
        if not taken(m):
            add("phone", m, phone_key(m.group(0)))
    for m in AMOUNT_RE.finditer(masked):
        if taken(m):
            continue
        value = parse_number(m.group(2) or m.group(3))
        currency = (m.group(1) or m.group(4) or "RON").upper()
        currency = {"LEI": "RON", "LEU": "RON", "EURO": "EUR"}.get(currency, currency)
        if value is not None:
            add("amount", m, (round(value, 2), currency), role=_amount_role(masked, m.start(), m.end()))
    for m in DATE_RE.finditer(masked):
        if taken(m):
            continue
        day = _date_from(m, year)
        if day:
            add("date", m, day, role=_date_role(masked, m.start(), m.end()))
    for m in TIME_RE.finditer(masked):
        if taken(m):
            continue
        add("time", m, f"{int(m.group(1)):02d}:{m.group(2)}")
    return sorted(out, key=lambda v: v["start"])


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, (*path, str(k)))
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v, path)
    else:
        yield path, value


def _date_role_of(path: tuple[str, ...]) -> str | None:
    for key in reversed(path):
        low = key.lower()
        if "deadline" in low or low.startswith("due") or low.endswith("_due"):
            return "deadline"
        for role, keys in _DATE_ROLE_KEYS.items():
            if low in keys:
                return role
    return None


def _amount_role_of(path: tuple[str, ...], kind: str | None) -> str | None:
    leaf = path[-1].lower() if path else ""
    parents = [p.lower() for p in path[:-1]]
    if leaf == "payer_liability":
        return "share"
    if leaf == "refunded" or (kind == "refund.instruction" and leaf == "amount"):
        return "refund"
    if leaf in ("debited", "shown_amount"):
        return "payment"
    if leaf == "amount" or (leaf == "value" and ("amount" in parents or (kind or "").startswith("bank.transaction"))):
        return "payment"
    return None


class Allowed:
    """The values the ledger holds, by kind, and by role for dates and amounts."""

    def __init__(self) -> None:
        self.amounts: set[tuple[float, str]] = set()
        self.dates: set[date] = set()
        self.times: set[str] = set()
        self.ibans: set[str] = set()
        self.case_ids: set[str] = set()
        self.phones: set[str] = {phone_key(BANK_OFFICIAL_PHONE)}
        self.hosts: set[str] = set(OFFICIAL_HOSTS)
        self.date_roles: dict[str, set[date]] = {}
        self.amount_roles: dict[str, set[tuple[float, str]]] = {}

    def add_datetime(self, value: Any, role: str | None = None) -> None:
        local = to_local(value)
        if local is None:
            return
        self.dates.add(local.date())
        if role:
            self.date_roles.setdefault(role, set()).add(local.date())
        if isinstance(value, datetime) or (isinstance(value, str) and ("T" in value or " " in value.strip())):
            self.times.add(f"{local:%H:%M}")

    def add_content(self, content: Any, currency: str = "RON", kind: str | None = None) -> None:
        cur = currency
        if isinstance(content, dict) and isinstance(content.get("currency"), str):
            cur = content["currency"].upper()
        for path, value in _walk(content):
            low = path[-1].lower() if path else ""
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)) and any(k in low for k in AMOUNT_KEYS) and value > 0:
                amount = (round(float(value), 2), cur)
                self.amounts.add(amount)
                role = _amount_role_of(path, kind)
                if role:
                    self.amount_roles.setdefault(role, set()).add(amount)
            elif isinstance(value, datetime):
                self.add_datetime(value, _date_role_of(path))
            elif isinstance(value, str):
                v = value.strip()
                if ISO_DT.match(v):
                    self.add_datetime(v, _date_role_of(path))
                elif CASE_RE.fullmatch(v):
                    self.case_ids.add(v)
                elif IBAN_RE.fullmatch(v.upper()):
                    self.ibans.add(v.replace(" ", "").upper())
                elif "phone" in low and len(phone_key(v)) >= 9:
                    self.phones.add(phone_key(v))


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
        allowed.add_content(content, (content.get("currency") or "RON") if isinstance(content, dict) else "RON",
                            kind=data.get("kind"))
    return allowed


def _pool(kind: str, role: str | None, allowed: Allowed) -> set:
    if kind == "date":
        return allowed.date_roles.get(role or "", set()) or allowed.dates
    if kind == "amount":
        return allowed.amount_roles.get(role or "", set()) or allowed.amounts
    return set()


def _closest(kind: str, value: Any, allowed: Allowed, role: str | None = None) -> str:
    if kind == "amount":
        everything = _pool("amount", role, allowed)
        pool = [a for a in everything if a[1] == value[1]] or list(everything)
        if not pool:
            return "no amount on file"
        best = min(pool, key=lambda a: abs(a[0] - value[0]))
        return money(best[0], best[1])
    if kind == "date":
        pool = _pool("date", role, allowed)
        if not pool:
            return "no date on file"
        return fmt_date(min(pool, key=lambda d: abs((d - value).days)))
    if kind == "time":
        if not allowed.times:
            return "no time on file"
        def mins(t: str) -> int:
            return int(t[:2]) * 60 + int(t[3:])
        return min(allowed.times, key=lambda t: abs(mins(t) - mins(value)))
    if kind == "case_id":
        return min(allowed.case_ids) if allowed.case_ids else "no case ID on file"
    if kind in ("iban", "iban_tail"):
        return next((f"{i[:4]} {i[4:8]} •••• {i[-4:]}" for i in sorted(allowed.ibans)), "no IBAN on file")
    if kind == "phone":
        return f"only the bank's helpline ({BANK_OFFICIAL_PHONE})"
    if kind == "url":
        return "no link on file (only the bank's site or a public authority's)"
    return ""


def _on_file(kind: str, value: Any, allowed: Allowed) -> bool:
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
    if kind == "phone":
        return value in allowed.phones
    if kind == "url":
        return any(value == h or value.endswith("." + h) for h in allowed.hosts)
    return True


def _in_role(kind: str, value: Any, role: str | None, allowed: Allowed) -> bool:
    """A dated or priced value whose role the words give must be one of that role's values on file (when the file
    has any for that role)."""
    if not role or kind not in ("date", "amount"):
        return True
    pool = (allowed.date_roles if kind == "date" else allowed.amount_roles).get(role)
    if not pool:
        return True
    if kind == "date":
        return value in pool
    return any(abs(a - value[0]) < 0.005 and c == value[1] for a, c in pool)


def check(sections: list[tuple[str, str]], allowed: Allowed, *, year_hint: int | None = None) -> dict:
    """Checks every value in [(where, text)] against the ledger: {passed, checked, mismatches: [{value, expected,
    where, kind, role?}]}. `role` is there when the value is on file but stands for something else (a payment date
    written as a deadline)."""
    checked = 0
    mismatches: list[dict] = []
    years = [d.year for d in allowed.dates]
    hint = year_hint or (max(years) if years else None)
    for where, text in sections:
        for v in extract(text, year_hint=hint):
            checked += 1
            kind, value, role = v["kind"], v["value"], v.get("role")
            if not _on_file(kind, value, allowed):
                mismatches.append({"value": v["raw"], "expected": _closest(kind, value, allowed, role),
                                   "where": where, "kind": kind})
            elif not _in_role(kind, value, role, allowed):
                mismatches.append({"value": v["raw"], "expected": _closest(kind, value, allowed, role),
                                   "where": where, "kind": kind, "role": role})
    return {"passed": not mismatches, "checked": checked, "mismatches": mismatches}


def sections_of(subject: str, paragraphs: Iterable[str]) -> list[tuple[str, str]]:
    return [("subject", subject or "")] + [(f"paragraph {i}", p) for i, p in enumerate(paragraphs, 1)]


def feedback(mismatches: list[dict]) -> str:
    """The rewrite instruction: each wrong value with the value on file."""
    lines = []
    for m in mismatches:
        role = f" as {ROLE_WORDS[m['role']]}" if m.get("role") in ROLE_WORDS else ""
        lines.append(f"- {m['where']}: you wrote “{m['value']}”{role}, but the case file has {m['expected']}")
    return ("\n\nThe numeric check stopped the previous draft: these values are not in the case file.\n" + "\n".join(lines)
            + "\nWrite the letter again and copy every amount, date, time and ID exactly from the case data, each in its "
              "own place (a deadline as the deadline, the payment date as the payment date). Give no phone number or "
              "link other than the bank's.")
