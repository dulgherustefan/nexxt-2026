"""One format for what the agent reads, whoever sent it: the bank's logs, the customer's text or an LLM.

Each function takes the messy value as it arrives and returns it in a published standard, or None when the value
can't be read that way (never a guess dressed up as data):

- money: ISO 4217 currency codes, in a `Money`;
- phone numbers: E.164 (`+40712345678`), Romania as the default country;
- websites: the host in lower case, without "www." and in its IDNA (punycode) form;
- IBANs: checked with the ISO 13616 mod-97 check digits, and one mask everywhere;
- card 3-D Secure: the ECI read against the card's scheme (Visa 05/06/07, Mastercard 02/01/00);
- times: Bucharest local time with the real offset of that day (summer time included);
- fraud type: the categories the EBA guidelines on fraud reporting (EBA/GL/2018/05) use.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from versoml.contracts import Channel, DisputeType, Money, Scenario

TZ = ZoneInfo("Europe/Bucharest")

# ---------------------------------------------------------------- money (ISO 4217)

CURRENCY_WORDS = {
    "RON": ("ron", "lei", "leu"), "EUR": ("eur", "euro", "euros", "€"), "USD": ("usd", "dollar", "dollars", "$"),
    "GBP": ("gbp", "pound", "pounds", "£"), "CHF": ("chf",), "HUF": ("huf", "forint"),
}
_CURRENCY = {w: code for code, words in CURRENCY_WORDS.items() for w in words}


def currency(raw: str | None, default: str | None = "RON") -> str | None:
    """'lei' -> 'RON', '€' -> 'EUR'; an ISO code stays as it is."""
    word = (raw or "").strip().lower().rstrip(".")
    if not word:
        return default
    if word.upper() in CURRENCY_WORDS:
        return word.upper()
    return _CURRENCY.get(word, default)


def money(value: float | str | dict | Money | None, currency_raw: str | None = None) -> Money | None:
    """Any amount the pipeline holds (a float, '3.200,00', {'value', 'currency'}) as a Money, rounded to cents."""
    if value is None:
        return None
    if isinstance(value, Money):
        return value
    if isinstance(value, dict):
        return money(value.get("value"), value.get("currency") or currency_raw)
    if isinstance(value, str):
        text = value.strip().replace(" ", " ")
        # 3.200,00 / 3,200.00 / 3200: the last separator with two digits after it is the decimal one
        m = re.fullmatch(r"([0-9][0-9 .,]*?)(?:([.,])([0-9]{1,2}))?", text)
        if not m:
            return None
        whole = re.sub(r"[ .,]", "", m.group(1))
        value = float(f"{whole}.{m.group(3)}") if m.group(3) else float(whole)
    return Money(value=round(float(value), 2), currency=currency(currency_raw) or "RON")


def closest_amount(mentions: list[Money], target: Money | None) -> Money | None:
    """The amount in the customer's text that is about the disputed payment: same currency first, then the
    nearest value (a courier scam text also mentions the RON 2.99 bait fee)."""
    if not mentions:
        return None
    if target is None:
        return max(mentions, key=lambda m: m.value)
    same = [m for m in mentions if m.currency == target.currency] or mentions
    return min(same, key=lambda m: abs(m.value - target.value))


# ---------------------------------------------------------------- phone numbers (E.164)


def e164(raw: str | None, country_code: str = "40") -> str | None:
    """'0712 345 678', '+40 712-345-678', '0040712345678' -> '+40712345678'. A national number with no
    country code is read as Romanian; anything that can't be a phone number is None."""
    if not raw or raw.startswith("<"):  # a pseudonym such as <TELEFON_1> is not a number
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        number = digits
    elif digits.startswith("00"):
        number = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        number = country_code + digits[1:]
    elif digits.startswith(country_code) and len(digits) == 11:
        number = digits
    else:
        return None
    return f"+{number}" if 8 <= len(number) <= 15 else None


def mask_phone(phone: str | None) -> str | None:
    """+40712345678 -> +40 7•• ••• 678 (enough to recognise it, not to call it)."""
    number = e164(phone) if phone and not phone.startswith("+") else phone
    if not number or len(number) < 8:
        return None
    return f"{number[:3]} {number[3]}•• ••• {number[-3:]}"


# ---------------------------------------------------------------- websites


def host(raw: str | None) -> str | None:
    """'https://WWW.Livrare-BancaDemo.example/colet?id=1' -> 'livrare-bancademo.example'; an internationalized
    name comes back in its ASCII (punycode) form, so look-alike letters can't hide in it."""
    if not raw or raw.startswith("<"):
        return None
    text = raw.strip().strip(".,;:()[]<>\"'")
    parts = urlsplit(text if "://" in text else f"http://{text}")
    name = (parts.hostname or "").rstrip(".").lower().removeprefix("www.")
    if "." not in name or not re.fullmatch(r"[\w.-]+", name):
        return None
    try:
        return name.encode("idna").decode("ascii")
    except UnicodeError:
        return None


# ---------------------------------------------------------------- IBAN (ISO 13616)


def iban(raw: str | None) -> str | None:
    """The IBAN without spaces and in capitals, or None when its check digits are wrong."""
    s = re.sub(r"\s", "", raw or "").upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", s):
        return None
    moved = s[4:] + s[:4]
    number = "".join(str(int(ch, 36)) for ch in moved)
    return s if int(number) % 97 == 1 else None


def mask_iban(raw: str | None) -> str | None:
    """RO49BDEM1234567890120001 -> 'RO49 BDEM •••• 0001': country, bank and the last four digits."""
    s = re.sub(r"\s", "", raw or "").upper()
    return f"{s[:4]} {s[4:8]} •••• {s[-4:]}" if len(s) > 12 else None


# ---------------------------------------------------------------- card 3-D Secure

ThreeDS = Literal["authenticated", "attempted", "not_authenticated"]
# Visa (and Amex, JCB, Diners) and Mastercard number the same outcomes differently
ECI = {
    "visa": {"05": "authenticated", "06": "attempted", "07": "not_authenticated"},
    "mastercard": {"02": "authenticated", "01": "attempted", "00": "not_authenticated"},
}


def eci_code(raw: str | int | None) -> str | None:
    """'5', 5 or ' 05' -> '05'."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    return text.zfill(2) if text.isdigit() and len(text) <= 2 else None


def three_ds(eci: str | int | None, scheme: str | None) -> ThreeDS | None:
    """What the ECI says about 3-D Secure, for this card's scheme. None when the code isn't one this scheme uses
    (for example a Visa code on a Mastercard): the record says so instead of guessing."""
    code = eci_code(eci)
    table = ECI.get((scheme or "").lower())
    return table.get(code) if code and table else None  # type: ignore[return-value]


# ---------------------------------------------------------------- time


def local(value: datetime) -> datetime:
    """A time in Bucharest, with that day's offset (+02:00 in winter, +03:00 in summer). A time without an offset
    is taken to be Bucharest time already: that is how the bank's systems and its customers write it."""
    return value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)


def local_noon(day: date) -> datetime:
    """A day the customer gave without a time: noon in Bucharest, so the date can't slip by a time zone."""
    return datetime.combine(day, time(12, 0), tzinfo=TZ)


# ---------------------------------------------------------------- fraud type (EBA/GL/2018/05)

EbaFraudType = Literal[
    "card_lost_or_stolen", "card_not_received", "counterfeit_card", "card_details_theft", "card_other",
    "payment_order_issued_by_fraudster", "payment_order_modified_by_fraudster", "manipulation_of_payer",
]

EBA_LABELS: dict[str, str] = {
    "card_lost_or_stolen": "Card lost or stolen",
    "card_not_received": "Card not received",
    "counterfeit_card": "Counterfeit card",
    "card_details_theft": "Card details theft",
    "card_other": "Other unauthorised card payment",
    "payment_order_issued_by_fraudster": "Payment order issued by the fraudster",
    "payment_order_modified_by_fraudster": "Payment order modified by the fraudster",
    "manipulation_of_payer": "Manipulation of the payer",
}


def eba_fraud_type(channel: Channel | str | None, dispute_type: DisputeType | str | None,
                   scenario: Scenario | str | None = None, pos_entry_mode: str | None = None) -> EbaFraudType | None:
    """The EBA fraud reporting category for a dispute; None when it isn't fraud (a merchant dispute, a processing
    error). Unauthorised payments and payments the customer was tricked into making are reported apart."""
    kind = DisputeType(dispute_type) if dispute_type in DisputeType._value2member_map_ or isinstance(dispute_type, DisputeType) else None
    if kind == DisputeType.APP:
        return "manipulation_of_payer"
    if kind != DisputeType.NEAUTORIZATA:
        return None
    if str(getattr(channel, "value", channel)) == Channel.CARD.value:
        if pos_entry_mode in ("chip", "contactless", "magstripe", "atm"):
            return "card_lost_or_stolen"
        if str(getattr(scenario, "value", scenario)) in (Scenario.PHISHING_LINK.value, Scenario.CARD_ECOM_FARA_3DS.value,
                                                         Scenario.CARD_VISA_SECURE.value, Scenario.INJECTIE_DOCUMENT.value):
            return "card_details_theft"
        return "card_details_theft" if pos_entry_mode == "ecommerce" else "card_other"
    return "payment_order_issued_by_fraudster"
