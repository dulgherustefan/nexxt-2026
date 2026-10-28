"""Free-form intake: who the customer is and which payment they dispute, from the complaint alone.

A complaint can arrive by email or through a web form with no customer reference and no transaction ID. This module
reads the clues in the text (amounts, dates, links, phone numbers, IBAN fragments, the payee, the channel), finds the
customer through the bank's own records and scores the customer's outgoing payments. Everything is deterministic and
every point a payment gets carries a reason a person can read. No LLM is involved: the raw text stays in the client
zone and the result never goes to a model.

Three outcomes:
- a clear winner (enough points and a clear margin over the next payment): the case goes on with it;
- several payments fit and none stands out: a person picks one (the graph's `pick_transaction` interrupt);
- no customer or no payment fits: the case goes on with the customer's statements only (DSP-53 asks for the rest).

The thresholds are [U] parameters (`match_*` in versoml/shared/rules/params_default.yaml); the point weights below are
the scoring scale and are shown with every candidate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

from rapidfuzz import fuzz, process

from versoml.contracts import MatchCandidate, MatchResult
from versoml.zone_client.agents import AMOUNT_RE, PHONE_RE, _fold, normalize_ro, parse_amount
from versoml.zone_client.fmt import TZ, fmt_date, fmt_datetime, money, to_local

# ---------------------------------------------------------------- the scoring scale (points per clue)

W_AMOUNT_EXACT = 50          # an amount in the complaint equals the payment (to the ban)
W_AMOUNT_NEAR = 25           # within 1% of the payment
W_AMOUNT_SECONDARY = 0.6     # factor for amounts that are not the disputed one (a bait fee, an SMS in an attachment)
W_DATE_SAME = 25             # the payment falls on the day the complaint names
W_DATE_NEXT = 12             # one day off
W_DATE_NEAR = 5              # up to three days off
W_DATE_FAR = -15             # the complaint names a day and the payment is more than a week away from it
W_RECENT = 6                 # no date in the complaint: the payment is from the last three days
W_RECENT_2W = 3              # no date in the complaint: the payment is from the last two weeks
W_TIME = 6                   # a time in the complaint within an hour of the payment
W_IBAN_FULL = 45             # the payee IBAN is in the complaint
W_IBAN_TAIL = 25             # the last four digits of the payee account are in the complaint
W_CARD_TAIL = 15             # the last four digits of the card used are in the complaint
W_PAYEE_NAME = 25            # the payee or merchant is named in the complaint
W_PAYEE_PARTIAL = 12         # part of the payee's name is in the complaint
W_DOMAIN = 30                # a link in the complaint is the merchant's website
W_PHONE = 25                 # a phone number in the complaint is the payee's
W_CHANNEL = 8                # the payment type matches the one the complaint describes
W_CHANNEL_CONFLICT = -12     # the complaint describes a card payment and this is a transfer, or the other way round
W_INSTANT = 4                # the complaint says "instant" and this is an instant transfer
W_DUPLICATE = 10             # the second of two identical charges, when the customer says they were charged twice
W_DUPLICATE_ORIGINAL = -30   # the first of the pair: the customer disputes the second one

FULL_SCORE_POINTS = 80       # the 0-1 score shown in the console: points / 80, capped at 1
MATCH_WINDOW_DAYS = 550      # how far back the ledger is read: 13 months (art. 169) and a margin for late claims
MAX_CANDIDATES = 5
DEFAULT_PARAMS = {"match_auto_min_points": 50, "match_auto_min_margin": 20, "match_candidate_min_points": 20}

NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "o": 1, "un": 1, "una": 1, "doua": 2, "doi": 2, "trei": 3,
                "patru": 4, "cinci": 5, "sase": 6, "sapte": 7, "opt": 8, "noua": 9, "zece": 10}
MONTHS = {
    "january": 1, "jan": 1, "ianuarie": 1, "ian": 1, "february": 2, "feb": 2, "februarie": 2, "march": 3, "mar": 3,
    "martie": 3, "april": 4, "apr": 4, "aprilie": 4, "may": 5, "mai": 5, "june": 6, "jun": 6, "iunie": 6, "iun": 6,
    "july": 7, "jul": 7, "iulie": 7, "iul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "septembrie": 9, "october": 10, "oct": 10, "octombrie": 10, "november": 11, "nov": 11, "noiembrie": 11, "noi": 11,
    "december": 12, "dec": 12, "decembrie": 12,
}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            "luni": 0, "marti": 1, "miercuri": 2, "joi": 3, "vineri": 4, "sambata": 5, "duminica": 6}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM_WORD_RE = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))

ATTACHMENT_SPLIT = re.compile(r"\n*\[(?:Attachment|Atașament|Atasament):[^\]]*\]\n?", re.I)
EUR_RE = re.compile(r"\b(?:eur|euro)\s*(\d{1,3}(?:[., ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?!\d)"
                    r"|(?<![\d.,])(\d{1,3}(?:[., ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(?:eur|euro|€)", re.I)
# "a payment of 3200", "suma de 3.200": a bare number after an amount word counts too
BARE_AMOUNT_RE = re.compile(r"\b(?:payment|transfer|amount|sum|charge|debit|suma|plata|plată|transferul|debitarea)"
                            r"\s+(?:of\s+|de\s+)?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{2,7}(?:[.,]\d{1,2})?)\b(?!\s*%)",
                            re.I)
IBAN_RE = re.compile(r"\b(RO\d{2}\s?[A-Z]{4}(?:\s?[0-9A-Z]{4}){4})\b", re.I)
TAIL_RE = re.compile(r"(?:ending|ends|ended|terminat\w*|se termina|ultimele\s+(?:4|patru)\s+cifre|last\s+(?:4|four)\s+"
                     r"digits)\s*(?:in|with|cu|:|are|sunt)?\s*(?:in\s+)?(\d{4})\b"
                     r"|(?:\*{2,}|•{2,}|\.{3}|…|x{3,})\s?(\d{4})\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DISPUTE_WORDS = re.compile(
    r"\b(?:did\s*n[o']?t|didn'?t|never|not\s+me|wasn'?t\s+me|unauthori[sz]ed|gone|taken|took|stolen|charged|debited"
    r"|withdrawn|missing|disappeared|left\s+my\s+account|went\s+out|sent\s+out|nu\s+am|n-am|nu\s+eu|disparut\w*|luat\w*"
    r"|retras\w*|furat\w*|debitat\w*|neautorizat\w*|lipses\w*|plecat\w*|tras\w*|scos\w*)\b", re.I)
TWICE_RE = re.compile(r"\b(?:twice|two\s+times|double|charged\s+two|de\s+doua\s+ori|de\s+2\s+ori|dubl\w*)\b")
CARD_WORDS = re.compile(r"\b(?:card|cardul\w*|cardului|pos|atm|bancomat|visa|mastercard|3d\s?secure|online\s+(?:payment"
                        r"|purchase|shop\w*|order)|plata\s+online|cumparatur\w*|magazin\w*\s+online|e-?commerce"
                        r"|contactless|merchant|comerciant\w*)\b")
TRANSFER_WORDS = re.compile(r"\b(?:transfer\w*|virament\w*|ordin\s+de\s+plata|bank\s+transfer|wire)\b")
INSTANT_WORDS = re.compile(r"\binstant\w*\b")
PAYEE_CUE = re.compile(r"(?:\bto|\binto|catre|in\s+contul|beneficiar\w*|payee|recipient|destinat\w*|went\s+to|sent\s+to"
                       r"|transferat\w*|virat\w*|account\s+of|contul\s+(?:lui|unei|unui)|in\s+favoarea)\s*[:\-]?\s*$")
SELF_ACCOUNT_CUE = re.compile(r"(?:my\s+(?:account|iban|current\s+account)|from\s+my|contul\s+meu|iban-?ul\s+meu|din\s+contul"
                              r"|de\s+pe\s+contul\s+meu|account\s+number|nr\.?\s+(?:de\s+)?cont|cont\s+nr\.?)\s*[:\-]?\s*$")
SELF_PHONE_CUE = re.compile(r"(?:my\s+(?:phone|number|mobile|phone\s+number)(?:\s+is)?|call\s+me(?:\s+(?:at|on))?|reach\s+me"
                            r"(?:\s+(?:at|on))?|contact\s+me(?:\s+(?:at|on))?|numarul\s+meu(?:\s+(?:este|e))?|telefonul\s+meu"
                            r"(?:\s+(?:este|e))?|ma\s+puteti\s+suna(?:\s+(?:la|pe))?|sunati-?ma(?:\s+(?:la|pe))?|contactati-?ma"
                            r"(?:\s+(?:la|pe))?|tel\.?|telefon\s*:|phone\s*:)\s*[:\-]?\s*$")
SCAM_PHONE_CUE = re.compile(r"(?:called\s+me\s+from|call\s+from|rang\s+me\s+from|calling\s+from|sunat\w*\s+de\s+pe|apelat\w*"
                            r"\s+de\s+pe|de\s+pe\s+numarul|from\s+the\s+number|from\s+number|from\s+a\s+number|numarul|number"
                            r"|whatsapp|sms\s+de\s+la|message\s+from|text\s+from|from)\s*[:\-]?\s*$")


# ---------------------------------------------------------------- the clues in the complaint


@dataclass
class DateMention:
    day: date
    tolerance: int
    text: str
    kind: str          # "absolute" | "relative"


@dataclass
class Amount:
    value: float
    currency: str
    primary: bool
    text: str


@dataclass
class Clues:
    amounts: list[Amount] = field(default_factory=list)
    dates: list[DateMention] = field(default_factory=list)
    times: list[time] = field(default_factory=list)
    ibans: list[tuple[str, str]] = field(default_factory=list)          # (IBAN, "self" | "payee" | "none")
    tails: list[tuple[str, bool]] = field(default_factory=list)         # (last 4 digits, about a card?)
    phones: list[tuple[str, str]] = field(default_factory=list)         # (E.164, "self" | "scam" | "none")
    emails: list[tuple[str, bool]] = field(default_factory=list)        # (address, in an attachment?)
    urls: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)                      # how the customer signs or introduces themselves
    channel: str | None = None                                          # "card" | "transfer" | None (unclear)
    instant: bool = False
    twice: bool = False
    tokens: set[str] = field(default_factory=set)                       # folded words of the complaint body
    reference: datetime | None = None

    def public(self) -> dict:
        """What the preview shows: the values, with phone numbers masked."""
        return {
            "amounts": [{"value": a.value, "currency": a.currency, "primary": a.primary} for a in self.amounts],
            "dates": [m.day.isoformat() for m in self.dates],
            "urls": list(self.urls),
            "phones_masked": [mask_phone(p) for p, _ in self.phones],
        }


def mask_phone(phone: str) -> str:
    """+40700976264 -> +40 7•• ••• 264."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return "•••"
    return f"+{digits[:2]} {digits[2]}•• ••• {digits[-3:]}" if phone.startswith("+") else f"{digits[:2]}•• ••• {digits[-3:]}"


def mask_iban(iban: str) -> str:
    s = (iban or "").replace(" ", "").upper()
    return f"{s[:4]} {s[4:8]} •••• {s[-4:]}" if len(s) > 12 else s


def compose_text(text: str, attachments: Iterable[Any] | None = None) -> str:
    """The complaint as the intake step sees it: the body, then each attachment under a marker."""
    parts = [normalize_ro(text or "")]
    for a in attachments or []:
        kind = a.get("kind") if isinstance(a, dict) else getattr(a, "kind", "attachment")
        content = a.get("content") if isinstance(a, dict) else getattr(a, "content", "")
        if content:
            parts.append(f"[Attachment: {kind}]\n{normalize_ro(content)}")
    return "\n\n".join(parts)


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(a, min(b, len(chars))):
            chars[i] = " "
    return "".join(chars)


def _sentences(text: str) -> list[tuple[int, int]]:
    out, start = [], 0
    for m in re.finditer(r"[.!?\n]+", text):
        out.append((start, m.end()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


def _amounts(full: str, body_len: int) -> tuple[list[Amount], list[tuple[int, int]]]:
    found: list[tuple[int, int, float, str]] = []
    for m in AMOUNT_RE.finditer(full):
        value = parse_amount(m.group(1) or m.group(2))
        if value is not None:
            found.append((m.start(), m.end(), value, "RON"))
    for m in EUR_RE.finditer(full):
        value = parse_amount(m.group(1) or m.group(2))
        if value is not None:
            found.append((m.start(), m.end(), value, "EUR"))
    taken = [(a, b) for a, b, _, _ in found]
    for m in BARE_AMOUNT_RE.finditer(full):
        if any(a <= m.start(1) < b for a, b in taken):
            continue
        value = parse_amount(m.group(1))
        if value is not None and value >= 10:
            found.append((m.start(1), m.end(1), value, "RON"))
    found.sort()
    folded = _fold(full)
    sentences = _sentences(folded)
    body = [f for f in found if f[0] < body_len]
    salient = set()
    for start, end, value, _ in body:
        sent = next(((a, b) for a, b in sentences if a <= start < b), (0, len(folded)))
        if DISPUTE_WORDS.search(folded[sent[0]:sent[1]]):
            salient.add(value)
    if body and not salient:
        salient.add(max(v for _, _, v, _ in body))
    counts: dict[float, int] = {}
    for _, _, v, _ in body:
        counts[v] = counts.get(v, 0) + 1
    salient |= {v for v, n in counts.items() if n > 1}
    amounts: list[Amount] = []
    seen: set[tuple[float, str, bool]] = set()
    for start, end, value, currency in found:
        primary = start < body_len and value in salient
        key = (value, currency, primary)
        if key in seen:
            continue
        seen.add(key)
        amounts.append(Amount(value=value, currency=currency, primary=primary, text=full[start:end]))
    # an amount that is primary once is not listed again as secondary
    primaries = {(a.value, a.currency) for a in amounts if a.primary}
    amounts = [a for a in amounts if a.primary or (a.value, a.currency) not in primaries]
    return amounts, taken + [(f[0], f[1]) for f in found]


def _year_for(month: int, day: int, ref: date) -> date | None:
    try:
        d = date(ref.year, month, day)
    except ValueError:
        return None
    if d > ref + timedelta(days=1):
        try:
            d = date(ref.year - 1, month, day)
        except ValueError:
            return None
    return d


def _mk(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_dates(folded: str, ref: datetime) -> tuple[list[DateMention], list[tuple[int, int]]]:
    """Dates the complaint mentions, absolute ("27.10.2026", "27 Oct", "October 27", "27 octombrie") and relative
    ("yesterday", "ieri", "alaltăieri", "on Monday", "luni", "two days ago", "acum 3 zile", "last week"), in either
    language. `folded` is lower case without diacritics; `ref` is when the bank received the complaint."""
    ref_day = to_local(ref).date()
    out: list[DateMention] = []
    spans: list[tuple[int, int]] = []

    def add(day: date | None, tol: int, m: re.Match, kind: str) -> None:
        if day is None or day > ref_day + timedelta(days=1):
            return
        out.append(DateMention(day=day, tolerance=tol, text=m.group(0).strip(), kind=kind))
        spans.append((m.start(), m.end()))

    def free(m: re.Match) -> bool:
        return not any(a < m.end() and m.start() < b for a, b in spans)

    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", folded):
        add(_mk(int(m.group(1)), int(m.group(2)), int(m.group(3))), 0, m, "absolute")
    for m in re.finditer(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b", folded):
        if free(m):
            add(_mk(int(m.group(3)), int(m.group(2)), int(m.group(1))), 0, m, "absolute")
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\b\.?(?:,?\s+(\d{{4}}))?", folded):
        if free(m):
            month, day = MONTHS[m.group(2)], int(m.group(1))
            add(_mk(int(m.group(3)), month, day) if m.group(3) else _year_for(month, day, ref_day), 0, m, "absolute")
    for m in re.finditer(rf"\b({_MONTH_RE})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", folded):
        if free(m) and m.group(1) not in ("mai", "noi"):
            month, day = MONTHS[m.group(1)], int(m.group(2))
            add(_mk(int(m.group(3)), month, day) if m.group(3) else _year_for(month, day, ref_day), 0, m, "absolute")
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", folded):
        if free(m) and 1 <= int(m.group(2)) <= 12:
            add(_year_for(int(m.group(2)), int(m.group(1)), ref_day), 0, m, "absolute")
    for m in re.finditer(r"\b(?:on|pe|din|data\s+de|la\s+data\s+de|dated?)\s+(\d{1,2})[./](\d{1,2})\b(?![./]\d)", folded):
        if free(m):
            add(_year_for(int(m.group(2)), int(m.group(1)), ref_day), 0, m, "absolute")

    relative: list[tuple[str, int, int]] = [
        (r"\b(?:the\s+)?day\s+before\s+yesterday\b|\balalta(?:ieri|-ieri|seara)\b", 2, 0),
        (r"\byesterday\b|\bieri\b", 1, 0),
        (r"\blast\s+night\b|\baseara\b", 1, 1),
        (r"\b(?:today|this\s+(?:morning|afternoon|evening)|tonight|earlier\s+today|azi|astazi|azi-?\s?dimineata"
         r"|de\s+dimineata|in\s+aceasta\s+dimineata|diseara|in\s+seara\s+asta)\b", 0, 0),
        (r"\bazi-?\s?noapte\b", 0, 1),
        (r"\b(?:a|one)\s+week\s+ago\b|\bacum\s+o\s+saptamana\b", 7, 2),
        (r"\blast\s+week\b|\bsaptamana\s+trecuta\b", 10, 4),
        (r"\bthis\s+week\b|\bsaptamana\s+(?:aceasta|asta)\b", 3, 3),
        (r"\blast\s+month\b|\bluna\s+trecuta\b", 30, 15),
    ]
    for pattern, back, tol in relative:
        for m in re.finditer(pattern, folded):
            if free(m):
                add(ref_day - timedelta(days=back), tol, m, "relative")
    for m in re.finditer(rf"\b(\d{{1,2}}|{_NUM_WORD_RE})\s+days?\s+ago\b|\bacum\s+(\d{{1,2}}|{_NUM_WORD_RE})\s+zile\b", folded):
        if free(m):
            raw = m.group(1) or m.group(2)
            n = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
            if 0 < n <= 60:
                add(ref_day - timedelta(days=n), 0 if n < 3 else 1, m, "relative")
    for m in re.finditer(rf"\b(\d|{_NUM_WORD_RE})\s+weeks?\s+ago\b|\bacum\s+(\d|{_NUM_WORD_RE})\s+saptamani\b", folded):
        if free(m):
            raw = m.group(1) or m.group(2)
            n = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0)
            if 0 < n <= 8:
                add(ref_day - timedelta(days=7 * n), 3, m, "relative")
    for m in re.finditer(r"\b(?:last\s+|this\s+past\s+|over\s+the\s+|this\s+|at\s+the\s+|in\s+)?weekend(?:ul)?"
                         r"(?:\s+trecut|\s+acesta)?\b", folded):
        if free(m):
            days_back = (ref_day.weekday() - 5) % 7 or (7 if ref_day.weekday() == 5 else 0)
            add(ref_day - timedelta(days=days_back), 1, m, "relative")
    for m in re.finditer(r"\b(?:on\s+|last\s+|this\s+past\s+|this\s+)?(monday|tuesday|wednesday|thursday|friday|saturday"
                         r"|sunday|luni|marti|miercuri|joi|vineri|sambata|duminica)\b", folded):
        if not free(m):
            continue
        word = m.group(1)
        before = folded[max(0, m.start() - 14):m.start()]
        if word == "luni" and re.search(rf"(?:\d|\b(?:{_NUM_WORD_RE}|cateva|multe|ultimele|ultimii|de))\s*$", before):
            continue  # "13 luni" are months, not Monday
        back = (ref_day.weekday() - WEEKDAYS[word]) % 7 or 7
        add(ref_day - timedelta(days=back), 0, m, "relative")
    return out, spans


def parse_times(folded: str) -> list[time]:
    out: list[time] = []
    for m in re.finditer(r"(?<![\d.:/-])(\d{1,2})[:h](\d{2})(?![\d:/])", folded):
        h, mi = int(m.group(1)), int(m.group(2))
        if h <= 23 and mi <= 59:
            out.append(time(h, mi))
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", folded):
        h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3).startswith("p"):
            h += 12
        if h <= 23 and mi <= 59:
            out.append(time(h, mi))
    for m in re.finditer(r"\b(?:ora|orele)\s+(\d{1,2})\b(?![:.]\d)", folded):
        if int(m.group(1)) <= 23:
            out.append(time(int(m.group(1)), 0))
    return list(dict.fromkeys(out))


def _context(folded: str, start: int, chars: int = 48) -> str:
    return folded[max(0, start - chars):start]


def parse_clues(text: str, attachments: Iterable[Any] | None = None, *, received_at: datetime | None = None,
                channel_hint: str | None = None) -> Clues:
    """Everything the matcher reads in a complaint (the body and its attachments)."""
    full = compose_text(text, attachments)
    body_len = (ATTACHMENT_SPLIT.search(full).start() if ATTACHMENT_SPLIT.search(full) else len(full))
    folded = _fold(full)
    ref = received_at or datetime.now(TZ)
    clues = Clues(reference=ref)
    clues.amounts, amount_spans = _amounts(full, body_len)

    try:
        from versoml.osint.investigate import extract_artifacts

        artifacts = extract_artifacts(full)
    except Exception:  # noqa: BLE001 - without the OSINT helpers the links are read with a plain pattern
        artifacts = {"urls": re.findall(r"https?://[^\s\"'<>)]+", full), "domains": []}
    clues.urls = [u.rstrip(".,;") for u in artifacts.get("urls") or []][:6]
    clues.domains = list(dict.fromkeys([*(artifacts.get("domains") or [])]))[:6]
    spans = list(amount_spans)
    for m in re.finditer(r"https?://\S+|\b(?:[a-z0-9-]+\.)+[a-z]{2,24}/\S*", folded):
        spans.append((m.start(), m.end()))

    for m in IBAN_RE.finditer(full):
        iban = m.group(1).replace(" ", "").upper()
        ctx = _context(folded, m.start())
        kind = "payee" if PAYEE_CUE.search(ctx) else "self" if SELF_ACCOUNT_CUE.search(ctx) else "none"
        if m.start() >= body_len:
            kind = "payee" if kind == "none" else kind
        clues.ibans.append((iban, kind))
        spans.append((m.start(), m.end()))
    for m in TAIL_RE.finditer(folded):
        tail = m.group(1) or m.group(2)
        near = folded[max(0, m.start() - 30):m.start() + 8]
        clues.tails.append((tail, bool(re.search(r"\bcard", near))))
        spans.append((m.start(), m.end()))
    for m in EMAIL_RE.finditer(full):
        clues.emails.append((m.group(0).lower(), m.start() >= body_len))
        spans.append((m.start(), m.end()))
    for m in PHONE_RE.finditer(full):
        raw = m.group(0)
        if raw.startswith("<"):
            continue
        from versoml.data.ids import normalize_phone

        phone = normalize_phone(raw)
        ctx = _context(folded, m.start())
        if SELF_PHONE_CUE.search(ctx):
            kind = "self"
        elif SCAM_PHONE_CUE.search(ctx) or m.start() >= body_len:
            kind = "scam"
        else:
            kind = "none"
        if phone not in [p for p, _ in clues.phones]:
            clues.phones.append((phone, kind))
        spans.append((m.start(), m.end()))

    cleaned = _blank(folded, spans)
    clues.dates, date_spans = parse_dates(cleaned, ref)
    clues.times = parse_times(_blank(cleaned, date_spans))

    body = full[:body_len]
    try:
        from versoml.shared.privacy.recognizers import find_names

        clues.names = list(dict.fromkeys(f.value for f in find_names(body)))
    except Exception:  # noqa: BLE001 - without the recognizers a name never identifies anyone on its own
        clues.names = []
    body_folded = folded[:body_len]
    if channel_hint:
        clues.channel = "card" if str(channel_hint) == "card" else "transfer"
        clues.instant = str(channel_hint) == "transfer_instant"
    else:
        card, transfer = bool(CARD_WORDS.search(body_folded)), bool(TRANSFER_WORDS.search(body_folded))
        clues.channel = "card" if card and not transfer else "transfer" if transfer and not card else None
        clues.instant = bool(INSTANT_WORDS.search(body_folded))
    clues.twice = bool(TWICE_RE.search(body_folded))
    clues.tokens = {t for t in re.findall(r"[a-z0-9]+", body_folded) if len(t) >= 3}
    return clues


# ---------------------------------------------------------------- who the customer is


@dataclass
class CustomerGuess:
    customer_ref: str
    points: int
    reasons: list[str]


def _name_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in re.split(r"[\s\-]+", _fold(name or "")) if len(t) >= 2)


def identify_customer(repo: Any, clues: Clues, customer_ref: str | None = None) -> list[CustomerGuess]:
    """The customers the complaint points to, best first. The customer's own account, phone or email count most; a
    name counts only where the customer signs or introduces themselves (a payee can be named anywhere)."""
    if customer_ref:
        try:
            if repo.get_customer(customer_ref):
                return [CustomerGuess(customer_ref, 10, ["Customer reference given with the complaint"])]
        except Exception:  # noqa: BLE001
            pass
    votes: dict[str, CustomerGuess] = {}

    def vote(ref: str | None, points: int, reason: str) -> None:
        if not ref or points <= 0:
            return
        guess = votes.setdefault(ref, CustomerGuess(ref, 0, []))
        guess.points += points
        if reason not in guess.reasons:
            guess.reasons.append(reason)

    for iban, kind in clues.ibans:
        if kind == "payee":
            continue
        owner = repo.find_customer_by_iban(iban)
        vote(owner, 3 if kind == "self" else 1, f"The complaint gives the customer's own IBAN ({mask_iban(iban)})")
    for phone, kind in clues.phones:
        if kind == "scam":
            continue
        for ref in repo.find_customers_by_phone(phone):
            vote(ref, 3 if kind == "self" else 1, f"The phone number in the complaint ({mask_phone(phone)}) is the "
                                                  "customer's")
    for email, in_attachment in clues.emails:
        if in_attachment:
            continue
        for ref in repo.find_customers_by_email(email):
            vote(ref, 2, "The email address in the complaint is the customer's")
    if clues.names:
        wanted = [_name_tokens(n) for n in clues.names]
        wanted = [w for w in wanted if len(w) >= 2]
        if wanted:
            for row in _customer_index(repo):
                tokens = _name_tokens(row.get("full_name") or f"{row.get('first_name', '')} {row.get('last_name', '')}")
                if tokens and any(w == tokens or (len(w) >= 2 and w <= tokens and len(tokens) <= len(w) + 1)
                                  for w in wanted):
                    vote(row["customer_ref"], 2, "The name the complaint is signed with is the customer's")
    return sorted(votes.values(), key=lambda g: (-g.points, g.customer_ref))


_INDEX_CACHE: dict[str, list[dict]] = {}


def _customer_index(repo: Any) -> list[dict]:
    key = str(getattr(repo, "db_path", id(repo)))
    if key not in _INDEX_CACHE:
        try:
            _INDEX_CACHE[key] = repo.customer_index()
        except Exception:  # noqa: BLE001
            _INDEX_CACHE[key] = []
    return _INDEX_CACHE[key]


def reset_cache() -> None:
    _INDEX_CACHE.clear()


# ---------------------------------------------------------------- which payment


_PAYEE_STOP = {"demo", "exemplu", "example", "fictiv", "sintetic", "synthetic", "fictitious", "srl", "the", "and",
               "online", "shop", "store", "magazin", "banca", "bank", "atm", "pos", "transfer", "payment", "plata",
               "retragere", "debit", "direct", "from", "catre", "to", "for", "pentru", "abonament", "company", "ltd"}


def _payee_tokens(name: str) -> list[str]:
    cleaned = re.sub(r"\((?:sintetic|fictiv|synthetic|fictitious)\)", " ", _fold(name or ""))
    cleaned = re.sub(r"\b(?:s\.?r\.?l\.?|s\.?a\.?)\b", " ", cleaned)
    return [t for t in re.findall(r"[a-z0-9]+", cleaned) if len(t) >= 3 and t not in _PAYEE_STOP]


def _payee_hit(name: str, tokens: set[str]) -> tuple[int, list[str]]:
    wanted = _payee_tokens(name)
    if not wanted or not tokens:
        return 0, []
    found = []
    pool = list(tokens)
    for t in wanted:
        if t in tokens or (len(t) >= 4 and process.extractOne(t, pool, scorer=fuzz.ratio, score_cutoff=88)):
            found.append(t)
    if found and len(found) == len(wanted) and (len(wanted) >= 2 or len(found[0]) >= 4):
        return W_PAYEE_NAME, found
    if found and len(found) * 2 >= len(wanted) and max(len(t) for t in found) >= 5:
        return W_PAYEE_PARTIAL, found
    return 0, []


def _registered(domain: str) -> str:
    from versoml.data.ids import registered_domain

    return registered_domain(domain or "")


def _tx_local(tx: dict) -> datetime | None:
    return to_local(tx.get("ts") or tx.get("executed_at"))


def _channel(tx: dict) -> str:
    return str(tx.get("channel") or tx.get("type") or "")


def score_transaction(tx: dict, clues: Clues, *, merchant: dict | None = None, card_tails: dict[str, str] | None = None,
                      ) -> tuple[int, list[str]]:
    """The points one outgoing payment gets from the complaint's clues, and a reason for each."""
    points, reasons = 0, []
    amount = float(tx.get("amount") or 0)
    currency = tx.get("currency") or "RON"

    best, why = 0.0, ""
    for a in clues.amounts:
        if a.currency.upper() != str(currency).upper():
            continue
        factor = 1.0 if a.primary else W_AMOUNT_SECONDARY
        if abs(a.value - amount) < 0.005:
            value, text = W_AMOUNT_EXACT * factor, f"same amount as in the complaint ({money(amount, currency)})"
        elif amount > 0 and abs(a.value - amount) <= 0.01 * amount:
            value, text = W_AMOUNT_NEAR * factor, f"amount within 1% of the {money(a.value, currency)} in the complaint"
        else:
            continue
        if value > best:
            best, why = value, text + ("" if a.primary else ", an amount the complaint mentions in passing")
    if best:
        points += round(best)
        reasons.append(why)

    local = _tx_local(tx)
    if local and clues.dates:
        gap = min(max(0, abs((local.date() - m.day).days) - m.tolerance) for m in clues.dates)
        mention = min(clues.dates, key=lambda m: max(0, abs((local.date() - m.day).days) - m.tolerance))
        if gap == 0:
            points += W_DATE_SAME
            reasons.append(f"made on {fmt_date(local)}, the day the complaint names (\u201c{mention.text}\u201d)")
        elif gap == 1:
            points += W_DATE_NEXT
            reasons.append(f"made on {fmt_date(local)}, one day from the date in the complaint")
        elif gap <= 3:
            points += W_DATE_NEAR
            reasons.append(f"made on {fmt_date(local)}, a few days from the date in the complaint")
        elif gap > 7:
            points += W_DATE_FAR
            reasons.append(f"made on {fmt_date(local)}, more than a week from the date in the complaint")
    elif local and clues.reference:
        age = (to_local(clues.reference) - local).total_seconds() / 86400
        if 0 <= age <= 3:
            points += W_RECENT
            reasons.append("made in the three days before the complaint")
        elif 0 <= age <= 14:
            points += W_RECENT_2W
            reasons.append("made in the two weeks before the complaint")
    if local and clues.times and best:
        minutes = min(abs((local.hour * 60 + local.minute) - (t.hour * 60 + t.minute)) for t in clues.times)
        if minutes <= 60:
            points += W_TIME
            reasons.append(f"made at {local:%H:%M}, close to the time in the complaint")

    payee_iban = (tx.get("counterparty_iban") or "").replace(" ", "").upper()
    if payee_iban and payee_iban.startswith("RO"):
        if any(i == payee_iban for i, _ in clues.ibans):
            points += W_IBAN_FULL
            reasons.append(f"the payee IBAN {mask_iban(payee_iban)} is in the complaint")
        elif any(t == payee_iban[-4:] and not card for t, card in clues.tails):
            points += W_IBAN_TAIL
            reasons.append(f"the payee account ends in {payee_iban[-4:]}, as the complaint says")
    if card_tails and tx.get("card_id") in card_tails and any(t == card_tails[tx["card_id"]] for t, _ in clues.tails):
        points += W_CARD_TAIL
        reasons.append(f"paid with the card ending in {card_tails[tx['card_id']]}, as the complaint says")

    payee = tx.get("counterparty_name") or (merchant or {}).get("name") or ""
    value, words = _payee_hit(payee, clues.tokens)
    if not value and (merchant or {}).get("name") and merchant["name"] != payee:
        value, words = _payee_hit(merchant["name"], clues.tokens)
    if value:
        points += value
        reasons.append(("the payee is named in the complaint" if value == W_PAYEE_NAME
                        else "part of the payee's name is in the complaint") + f" ({', '.join(words)})")
    site = (merchant or {}).get("domain")
    if site and clues.domains and any(_registered(d) == _registered(site) for d in clues.domains):
        points += W_DOMAIN
        reasons.append(f"the link in the complaint is the merchant's website ({_registered(site)})")
    counterpart_phone = tx.get("counterparty_phone") or tx.get("payee_phone")
    if counterpart_phone and any(p == counterpart_phone for p, _ in clues.phones):
        points += W_PHONE
        reasons.append("the payee's phone number is in the complaint")

    channel = _channel(tx)
    kind = "card" if channel == "card" else "transfer" if channel.startswith("transfer") else ""
    if clues.channel and kind:
        if clues.channel == kind:
            points += W_CHANNEL
            reasons.append("a card payment, as the complaint describes" if kind == "card"
                           else "a transfer, as the complaint describes")
        else:
            points += W_CHANNEL_CONFLICT
            reasons.append("the complaint describes a card payment, and this is a transfer" if clues.channel == "card"
                           else "the complaint describes a transfer, and this is a card payment")
    if clues.instant and channel == "transfer_instant":
        points += W_INSTANT
        reasons.append("an instant transfer, as the complaint says")
    return points, reasons


def _outgoing(tx: dict) -> bool:
    direction = str(tx.get("direction") or "debit").lower()
    kind = str(tx.get("kind") or "")
    status = str(tx.get("status") or "booked")
    return direction in ("debit", "out") and "refund" not in kind and not status.startswith("respins")


def _params(params: dict | None) -> dict:
    if params is not None:
        return {**DEFAULT_PARAMS, **{k: v for k, v in params.items() if k in DEFAULT_PARAMS}}
    try:
        from versoml.shared.rules import get_params

        values = get_params()
        return {k: values.get(k, v) for k, v in DEFAULT_PARAMS.items()}
    except Exception:  # noqa: BLE001 - without the parameters file, the defaults
        return dict(DEFAULT_PARAMS)


def _score(points: int) -> float:
    return round(max(0.0, min(1.0, points / FULL_SCORE_POINTS)), 2)


def _candidate(tx: dict, points: int, reasons: list[str]) -> MatchCandidate:
    local = _tx_local(tx)
    return MatchCandidate(
        tx_id=str(tx.get("tx_id") or tx.get("id")), amount=float(tx.get("amount") or 0),
        currency=tx.get("currency") or "RON", ts=local.isoformat(timespec="seconds") if local else str(tx.get("ts")),
        payee=tx.get("counterparty_name") or tx.get("description"), channel=_channel(tx) or None, direction="out",
        score=_score(points), points=points, reasons=reasons)


def _describe(c: MatchCandidate) -> str:
    when = fmt_datetime(c.ts)
    what = "card payment" if c.channel == "card" else "instant transfer" if c.channel == "transfer_instant" else "transfer"
    to = f" at {c.payee}" if c.channel == "card" and c.payee else ""
    return f"{what} of {money(c.amount, c.currency)}{to} on {when}"


def _mark_duplicates(scored: list[tuple[int, list[str], dict]], clues: Clues) -> None:
    """When the customer says they were charged twice, the second of two identical charges is the disputed one."""
    if not clues.twice:
        return
    for i, (_, _, a) in enumerate(scored):
        for j, (_, _, b) in enumerate(scored):
            if i >= j:
                continue
            same = (abs(float(a.get("amount") or 0) - float(b.get("amount") or 0)) < 0.005
                    and (a.get("merchant_id") or a.get("counterparty_iban") or a.get("counterparty_name"))
                    == (b.get("merchant_id") or b.get("counterparty_iban") or b.get("counterparty_name")))
            ta, tb = _tx_local(a), _tx_local(b)
            if not same or not ta or not tb or abs((ta - tb).total_seconds()) > 600:
                continue
            later, earlier = (i, j) if ta > tb else (j, i)
            p, r, t = scored[later]
            scored[later] = (p + W_DUPLICATE, [*r, "the second of two identical charges minutes apart, and the "
                                                    "customer says they were charged twice"], t)
            p, r, t = scored[earlier]
            scored[earlier] = (p + W_DUPLICATE_ORIGINAL, [*r, "the first of two identical charges: the customer "
                                                              "disputes the second one"], t)


def match_transactions(repo: Any, customer_ref: str, clues: Clues, *, taken: dict[str, str] | None = None,
                       params: dict | None = None) -> tuple[list[MatchCandidate], int, int]:
    """The customer's outgoing payments that fit the complaint, best first, with (top points, margin)."""
    p = _params(params)
    ref = clues.reference or datetime.now(TZ)
    try:
        txs = repo.list_transactions(customer_ref, MATCH_WINDOW_DAYS, as_of=to_local(ref) + timedelta(minutes=5))
    except TypeError:
        txs = repo.list_transactions(customer_ref, MATCH_WINDOW_DAYS)
    txs = [t for t in txs or [] if _outgoing(t) and str(t.get("tx_id")) not in (taken or {})]
    if not txs:
        return [], 0, 0
    merchants = {}
    try:
        merchants = repo.get_merchants(t.get("merchant_id") for t in txs)
    except Exception:  # noqa: BLE001
        merchants = {}
    try:
        cards = repo.customer_cards_last4(customer_ref)
    except Exception:  # noqa: BLE001
        cards = {}
    scored = []
    for tx in txs:
        points, reasons = score_transaction(tx, clues, merchant=merchants.get(tx.get("merchant_id")), card_tails=cards)
        scored.append((points, reasons, tx))
    _mark_duplicates(scored, clues)
    scored.sort(key=lambda s: (-s[0], str(s[2].get("ts") or "")), reverse=False)
    top = scored[0][0]
    second = scored[1][0] if len(scored) > 1 else 0
    floor = int(p["match_candidate_min_points"])
    listed = [s for s in scored if s[0] >= floor][:MAX_CANDIDATES]
    return [_candidate(tx, pts, why) for pts, why, tx in listed], top, top - max(second, 0)


def _taken(repo: Any, customer_ref: str, exclude_case_id: str | None, extra: dict[str, str] | None) -> dict[str, str]:
    taken: dict[str, str] = dict(extra or {})
    for fn in ("disputed_tx_ids", "refunded_tx_ids"):
        try:
            method = getattr(repo, fn)
            found = method(customer_ref, exclude_case_id=exclude_case_id) if fn == "disputed_tx_ids" else method(customer_ref)
            for k, v in (found or {}).items():
                taken.setdefault(k, v)
        except Exception:  # noqa: BLE001
            continue
    return taken


def match_complaint(repo: Any, *, text: str, attachments: Iterable[Any] | None = None, customer_ref: str | None = None,
                    transaction_refs: Iterable[str] | None = None, channel_hint: str | None = None,
                    received_at: datetime | None = None, exclude_case_id: str | None = None,
                    taken: dict[str, str] | None = None, params: dict | None = None,
                    clues: Clues | None = None) -> MatchResult:
    """Identify the customer and the disputed payment. Pure apart from reading the bank's records through `repo`."""
    p = _params(params)
    clues = clues or parse_clues(text, attachments, received_at=received_at, channel_hint=channel_hint)

    # 1. a transaction reference given with the complaint wins, if it is the customer's outgoing payment
    for ref in transaction_refs or []:
        tx = repo.get_transaction(ref) if ref else None
        if not tx:
            continue
        owner = tx.get("customer_ref")
        if customer_ref and owner != customer_ref:
            continue
        cand = _candidate(tx, FULL_SCORE_POINTS, ["transaction reference given with the complaint"])
        return MatchResult(
            customer_ref=owner, customer_match_reason=("Customer reference given with the complaint" if customer_ref
                                                       else "Identified from the transaction reference given"),
            customer_confidence=1.0, tx_id=cand.tx_id, confidence=1.0, needs_human=False, method="given",
            reason=f"The complaint names payment {cand.tx_id}: the {_describe(cand)}.", candidates=[cand])

    # 2. the customer
    guesses = identify_customer(repo, clues, customer_ref)
    chosen: CustomerGuess | None = None
    corroborated = False
    if guesses and guesses[0].points >= 3 and (len(guesses) == 1 or guesses[1].points < guesses[0].points):
        chosen = guesses[0]
    elif guesses:
        # weaker clues (a name in the signature, a number without context): the customer whose ledger has a clear
        # match is the one, if exactly one has it
        clear = []
        for g in guesses[:5]:
            cands, top, margin = match_transactions(repo, g.customer_ref, clues,
                                                    taken=_taken(repo, g.customer_ref, exclude_case_id, taken), params=p)
            if cands and top >= p["match_auto_min_points"] and margin >= p["match_auto_min_margin"]:
                clear.append(g)
        if len(clear) == 1:
            chosen, corroborated = clear[0], True
    if chosen is None:
        why = ("The complaint's details point to more than one customer" if len(guesses) > 1
               else "The complaint gives no detail that identifies a customer")
        return MatchResult(customer_ref=None, customer_match_reason=None, tx_id=None, confidence=0.0, needs_human=True,
                           method="none", reason=f"{why}: the claim goes on with what the customer says, and a "
                                                 "person asks for the missing details.")
    customer_reason = chosen.reasons[0] + (", and that customer has a payment that fits the complaint"
                                           if corroborated else "")
    customer_conf = 1.0 if chosen.points >= 10 else round(min(1.0, chosen.points / 5), 2)

    # 3. the payment
    excluded = _taken(repo, chosen.customer_ref, exclude_case_id, taken)
    cands, top, margin = match_transactions(repo, chosen.customer_ref, clues, taken=excluded, params=p)
    base = {"customer_ref": chosen.customer_ref, "customer_match_reason": customer_reason,
            "customer_confidence": customer_conf, "candidates": cands}
    if cands and top >= p["match_auto_min_points"] and margin >= p["match_auto_min_margin"]:
        best = cands[0]
        confidence = round(best.score * min(1.0, margin / 40), 2)
        return MatchResult(**base, tx_id=best.tx_id, confidence=confidence, needs_human=False, method="matched",
                           reason=f"One payment fits: the {_describe(best)} ({'; '.join(best.reasons[:3])}).")
    if cands:
        return MatchResult(**base, tx_id=None, confidence=round(cands[0].score * 0.5, 2), needs_human=True,
                           method="none",
                           reason=(f"{len(cands)} payments fit the complaint and none stands out" if len(cands) > 1
                                   else "One payment partly fits the complaint, not enough to be sure")
                           + ": a person picks the right one.")
    if excluded:
        # the payment that fits may be the one an open case is already about: say so, a person checks
        again, top_all, margin_all = match_transactions(repo, chosen.customer_ref, clues, taken={}, params=p)
        if again and again[0].tx_id in excluded and top_all >= p["match_auto_min_points"] \
                and margin_all >= p["match_auto_min_margin"]:
            return MatchResult(**{**base, "candidates": []}, tx_id=None, confidence=0.0, needs_human=True, method="none",
                               reason=f"The payment that fits ({again[0].tx_id}) is already disputed or refunded in case "
                                      f"{excluded[again[0].tx_id]}: a person checks whether this is the same claim.")
    note = " Payments already disputed or refunded were left out." if excluded else ""
    return MatchResult(**base, tx_id=None, confidence=0.0, needs_human=True, method="none",
                       reason="No outgoing payment in the customer's records fits the complaint: the claim goes on with "
                              "what the customer says, and a person asks for the missing details." + note)


def picked(result: MatchResult, tx_id: str | None, approver: str) -> MatchResult:
    """The result after a person picked a payment from the candidates (or "none of these")."""
    chosen = next((c for c in result.candidates if c.tx_id == tx_id), None) if tx_id else None
    if chosen is None:
        return result.model_copy(update={"tx_id": None, "needs_human": True, "method": "none", "confidence": 0.0,
                                         "reason": f"{approver} found none of the candidate payments right: the claim "
                                                   "goes on with what the customer says."})
    return result.model_copy(update={"tx_id": chosen.tx_id, "needs_human": False, "method": "picked", "confidence": 1.0,
                                     "reason": f"{approver} picked the {_describe(chosen)}."})


# ---------------------------------------------------------------- the customer's statements (declared facts)


def declared_facts(clues: Clues) -> dict:
    """What the customer says about the payment, for the declared-facts path. Untrusted: it never replaces the bank's
    records, and the rules only use it to ask for the missing details."""
    primary = [a for a in clues.amounts if a.primary] or clues.amounts
    amount = max(primary, key=lambda a: a.value) if primary else None
    day = min(clues.dates, key=lambda m: m.tolerance).day if clues.dates else None
    return {"amount": {"value": amount.value, "currency": amount.currency} if amount else None,
            "date": day.isoformat() if day else None,
            "channel": ("transfer_instant" if clues.instant and clues.channel != "card" else clues.channel),
            "urls": clues.urls[:3], "domains": clues.domains[:3],
            "phones_masked": [mask_phone(p) for p, _ in clues.phones][:3],
            "iban_tails": [t for t, card in clues.tails if not card][:3],
            "payee_ibans_masked": [mask_iban(i) for i, k in clues.ibans if k != "self"][:3]}


# ---------------------------------------------------------------- evaluation on the free-form golden set

FREEFORM_PATH = Path(__file__).resolve().parents[1] / "data" / "golden" / "freeform_60.jsonl"


def eval_matcher(path: Path | str | None = None, repo: Any = None, *, params: dict | None = None,
                 rows: list[dict] | None = None) -> dict:
    """Accuracy of the free-form intake on the golden set (freeform_60.jsonl): the right payment on the clear cases,
    a person on every ambiguous or unknown case, and no wrong automatic match.

    Each row: {gid, text, language, customer_ref|null, expected: {customer_ref|null, tx_id|null, needs_human},
    scenario, notes}, optionally `received_at` and `attachments`. Relative dates ("yesterday") are read from
    `received_at`, else from the synthetic world's clock (meta.world_now)."""
    if rows is None:
        source = Path(path) if path else FREEFORM_PATH
        if not source.exists():
            return {"status": "missing", "path": str(source)}
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if repo is None:
        from versoml.data.repos import ClientRepo

        repo = ClientRepo()
    world_now = None
    try:
        world_now = repo.world_now()
    except Exception:  # noqa: BLE001
        world_now = None
    clear = clear_ok = human = human_ok = wrong = customer_n = customer_ok = 0
    details = []
    for row in rows:
        exp = row.get("expected") or {}
        received = None
        if row.get("received_at"):
            received = datetime.fromisoformat(str(row["received_at"]).replace("Z", "+00:00"))
        result = match_complaint(repo, text=row.get("text") or "", attachments=row.get("attachments"),
                                 customer_ref=row.get("customer_ref"), received_at=received or world_now,
                                 channel_hint=row.get("channel_hint"), params=params)
        auto = not result.needs_human and result.tx_id is not None
        if exp.get("needs_human"):
            human += 1
            human_ok += int(not auto)
        else:
            clear += 1
            clear_ok += int(auto and result.tx_id == exp.get("tx_id"))
        if auto and result.tx_id != exp.get("tx_id"):
            wrong += 1
        if exp.get("customer_ref") is not None or row.get("customer_ref") is None:
            customer_n += 1
            customer_ok += int(result.customer_ref == exp.get("customer_ref"))
        if (auto and result.tx_id != exp.get("tx_id")) or (not exp.get("needs_human") and not auto) or \
                (exp.get("needs_human") and auto):
            details.append({"gid": row.get("gid"), "expected": exp, "got": {"customer_ref": result.customer_ref,
                            "tx_id": result.tx_id, "needs_human": result.needs_human}, "reason": result.reason})
    return {
        "n": len(rows),
        "clear": {"n": clear, "correct": clear_ok, "accuracy": round(clear_ok / clear, 4) if clear else None},
        "needs_human": {"n": human, "flagged": human_ok, "recall": round(human_ok / human, 4) if human else None},
        "wrong_auto_matches": wrong,
        "customer": {"n": customer_n, "correct": customer_ok,
                     "accuracy": round(customer_ok / customer_n, 4) if customer_n else None},
        "targets": {"clear_accuracy": 0.95, "needs_human_recall": 1.0, "wrong_auto_matches": 0},
        "passed": bool((not clear or clear_ok / clear >= 0.95) and (not human or human_ok == human) and wrong == 0),
        "errors": details[:20],
    }


def eval_section(fast: bool = False) -> dict:
    """The free-form intake section of the evaluation report (versoml/eval/run.py)."""
    r = eval_matcher()
    if r.get("status") == "missing":
        return r
    clear, human = r["clear"], r["needs_human"]
    r["summary_rows"] = [
        {"name": "Free-form intake: right payment on clear cases", "value": clear["accuracy"], "target": ">= 0.95"},
        {"name": "Free-form intake: ambiguous or unknown sent to a person", "value": human["recall"], "target": "1.0"},
        {"name": "Free-form intake: wrong automatic matches", "value": r["wrong_auto_matches"], "target": "0"},
    ]
    r["markdown"] = ["## Free-form intake (freeform_60)", "",
                     f"Clear cases: {clear['correct']}/{clear['n']} right payment. Ambiguous or unknown: "
                     f"{human['flagged']}/{human['n']} sent to a person. Wrong automatic matches: {r['wrong_auto_matches']}.", ""]
    return r
