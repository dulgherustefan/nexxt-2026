"""Recunoscătorii de date personale pentru texte românești (docs/05 §6.4).

Date personale (se pseudonimizează): CNP, IBAN, card (PAN), telefon RO, e-mail, act de
identitate, nume cunoscute sau precedate de „Subsemnatul", „Doamna" etc.
Identificatori publici (doar etichetă, rămân în text): CUI, denumirea firmei, domenii/URL-uri.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from itertools import permutations

from stdnum import iban as std_iban
from stdnum import luhn
from stdnum.exceptions import ValidationError
from stdnum.ro import cnp as std_cnp
from stdnum.ro import cui as std_cui

from versoml.shared.privacy.text import fold, normalize_ro

# Tipurile care sunt date personale și primesc pseudonim
PII_TYPES = ("CNP", "IBAN", "CARD", "TELEFON", "EMAIL", "CI", "NUME")
# Rolurile din `known` care denumesc entități publice (firma beneficiară, domenii): doar etichetă
PUBLIC_ROLES = frozenset({"FIRMA", "COMPANIE", "BENEFICIAR_PJ", "PJ", "DOMENIU", "CUI", "PUBLIC"})

# Prioritatea la suprapuneri: câștigă valoarea mai sigură / mai sensibilă
_PRIORITY = {"KNOWN": 100, "EMAIL": 90, "IBAN": 80, "CNP": 70, "CARD": 60, "TELEFON": 50,
             "CI": 45, "NUME": 40, "CUI": 30, "FIRMA": 20, "DOMENIU": 10}


@dataclass(frozen=True)
class Finding:
    type: str              # CNP, IBAN, CARD, TELEFON, EMAIL, CI, NUME, CUI, FIRMA, DOMENIU
    start: int
    end: int
    value: str             # textul exact; nu se loghează
    key: str               # forma normalizată, pentru pseudonime stabile
    pii: bool              # False = identificator public, doar etichetat
    role: str | None = None
    source: str = "pattern"  # pattern | known | heuristic
    synthetic: bool = False  # ex. CNP cu județ fictiv 71–79

    @property
    def masked(self) -> str:
        return mask(self.value)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["masked"] = self.masked
        return data


def mask(value: str) -> str:
    """Varianta afișabilă: primele și ultimele două caractere."""
    clean = value.strip()
    if len(clean) <= 4:
        return "•" * len(clean)
    return f"{clean[:2]}{'•' * min(8, len(clean) - 4)}{clean[-2:]}"


# ---------------------------------------------------------------- CNP

_CNP_RE = re.compile(r"(?<!\d)[1-9]\d{12}(?!\d)")
_CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)


def _cnp_check_digit(first12: str) -> str:
    rest = sum(w * int(d) for w, d in zip(_CNP_WEIGHTS, first12)) % 11
    return "1" if rest == 10 else str(rest)


def cnp_status(digits: str) -> tuple[bool, bool]:
    """(e CNP valid, e din zona sintetică). Validarea de bază e `stdnum.ro.cnp`;
    județele fictive 71–79 (docs/06 §2) se acceptă doar cu dată și cifră de control corecte."""
    if std_cnp.is_valid(digits):
        return True, digits[7:9] == "70"
    if len(digits) != 13 or not digits.isdigit() or not 71 <= int(digits[7:9]) <= 79:
        return False, False
    try:
        std_cnp.get_birth_date(digits)
    except ValidationError:
        return False, False
    return _cnp_check_digit(digits[:12]) == digits[12], True


def find_cnp(text: str) -> Iterator[Finding]:
    for m in _CNP_RE.finditer(text):
        valid, synthetic = cnp_status(m.group())
        if valid:
            yield Finding("CNP", m.start(), m.end(), m.group(), m.group(), True, synthetic=synthetic)


# ---------------------------------------------------------------- IBAN

_IBAN_START = re.compile(r"(?i)(?<![a-z0-9])[a-z]{2}\d{2}")
_IBAN_SEPS = " -\u00a0"


def _alnum(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def find_iban(text: str) -> Iterator[Finding]:
    """IBAN-uri valide (mod 97 și structura țării, prin `stdnum.iban`), cu sau fără spații."""
    n = len(text)
    for m in _IBAN_START.finditer(text):
        i = j = m.start()
        chars: list[tuple[str, int]] = []
        while j < n and len(chars) < 34:
            ch = text[j]
            if _alnum(ch):
                chars.append((ch.upper(), j + 1))
                j += 1
            elif ch in _IBAN_SEPS and chars and j + 1 < n and _alnum(text[j + 1]):
                j += 1
            else:
                break
        for length in range(len(chars), 14, -1):
            end = chars[length - 1][1]
            if end < n and _alnum(text[end]):
                continue  # nu tăiem în mijlocul unui grup
            candidate = "".join(c for c, _ in chars[:length])
            if std_iban.is_valid(candidate):
                yield Finding("IBAN", i, end, text[i:end], candidate, True)
                break


# ---------------------------------------------------------------- card

_CARD_RUN = re.compile(r"(?<!\d)\d(?:[ \-\u00a0]?\d){12,30}(?!\d)")


def is_card_number(digits: str) -> bool:
    """PAN plauzibil: 13–19 cifre, Luhn valid, prefix de rețea, nu „0000…"."""
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1 or not luhn.is_valid(digits):
        return False
    if digits[0] in "3456":
        return True
    return digits[0] == "2" and 2221 <= int(digits[:4]) <= 2720  # Mastercard seria 2


def find_card(text: str) -> Iterator[Finding]:
    for m in _CARD_RUN.finditer(text):
        groups = [(g.start() + m.start(), g.end() + m.start(), g.group()) for g in re.finditer(r"\d+", m.group())]
        used_until = -1
        for a, (start, _, _) in enumerate(groups):
            if start < used_until:
                continue
            best: tuple[int, str] | None = None
            digits = ""
            for b in range(a, len(groups)):
                digits += groups[b][2]
                if len(digits) > 19:
                    break
                if len(digits) >= 13 and is_card_number(digits) and not cnp_status(digits)[0]:
                    best = (b, digits)
            if best:
                b, digits = best
                end = groups[b][1]
                yield Finding("CARD", start, end, text[start:end], digits, True)
                used_until = end


# ---------------------------------------------------------------- telefon RO

_PHONE_RE = re.compile(
    r"(?<![\w+])"
    r"(?:(?:\+|00)\s?40[ .\-]?(?:\(0\)[ .\-]?)?|\(?0)"
    r"\(?([237])"
    r"((?:\)?[ .\-]?\d){8})"
    r"(?!\d)"
)


_DATE_LIKE = re.compile(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}")


def find_phone(text: str) -> Iterator[Finding]:
    """Numere românești: +40 / 0040 / 07xx / 02x / 03x, cu spații, puncte sau cratime."""
    for m in _PHONE_RE.finditer(text):
        if _DATE_LIKE.search(m.group()):
            continue  # „02.10.2026 14:30" e o dată, nu un telefon
        nsn = m.group(1) + re.sub(r"\D", "", m.group(2))
        yield Finding("TELEFON", m.start(), m.end(), m.group(), "+40" + nsn, True)


# ---------------------------------------------------------------- e-mail

_EMAIL_RE = re.compile(
    r"(?<![\w.+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*@"
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}"
    r"(?![\w\-])"
)


def find_email(text: str) -> Iterator[Finding]:
    for m in _EMAIL_RE.finditer(text):
        yield Finding("EMAIL", m.start(), m.end(), m.group(), m.group().lower(), True)


# ---------------------------------------------------------------- act de identitate

_CI_RE = re.compile(
    r"(?:\b(?i:seria|serie|buletin(?:ul)?|carte(?:a)?\s+de\s+identitate)|\bCI\b|\bC\.I\.)\s*:?\s*"
    r"([A-Za-z]{2})\s*(?i:nr\.?|num[ăa]r(?:ul)?)?\s*(\d{6,7})\b"
)


def find_identity_card(text: str) -> Iterator[Finding]:
    for m in _CI_RE.finditer(text):
        start = m.start(1)
        yield Finding("CI", start, m.end(), text[start:m.end()], m.group(1).upper() + m.group(2), True)


# ---------------------------------------------------------------- nume (euristic, după un declanșator)

_UP = "A-ZĂÂÎȘȚ"
_LOW = "a-zăâîșț"
_NAME_WORD = rf"(?:[{_UP}][{_LOW}]+(?:-[{_UP}][{_LOW}]+)?|[{_UP}]{{2,}}(?:-[{_UP}]{{2,}})?)"
_NAME_RE = re.compile(
    r"(?i:\b(?:subsemnat(?:ul|a)|numele\s+meu\s+(?:este|e)|m[ăa]\s+numesc|domnul(?:ui)?|doamna|doamnei|"
    r"dl\.?|dna\.?|d-l|d-na|d-lui|d-nei|titular(?:ul|a)?(?:\s+(?:contului|cardului))?|"
    r"nume(?:\s+(?:și|si)\s+prenume)?)\s*[:,]?\s+)"
    rf"(?P<name>{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,2}})"
)
_NOT_NAMES = {"banca", "bancii", "client", "clientul", "clientului", "operator", "operatorul", "director",
              "directorul", "judecator", "avocat", "agent", "agentul", "ofiter", "ofiterul", "demo", "urma"}


def name_key(name: str) -> str:
    """Cheia stabilă a unui nume: tokenii pliați, sortați (ordinea nu contează)."""
    return " ".join(sorted(t for t in re.split(r"[\s\-]+", fold(normalize_ro(name))) if t))


def find_names(text: str) -> Iterator[Finding]:
    for m in _NAME_RE.finditer(text):
        name = m.group("name")
        if fold(name.split()[0].split("-")[0]) in _NOT_NAMES:
            continue
        yield Finding("NUME", m.start("name"), m.end("name"), name, name_key(name), True, source="heuristic")


# ---------------------------------------------------------------- entități cunoscute

def parse_role(value: str) -> tuple[str, str | None]:
    """„CLIENT" → ("CLIENT", None); „<CLIENT_2>" sau „CLIENT_2" → ("CLIENT", "<CLIENT_2>")."""
    raw = value.strip().strip("<>").strip().upper()
    m = re.fullmatch(r"([A-Z][A-Z_]*?)_(\d+)", raw)
    if m:
        return m.group(1), f"<{m.group(1)}_{m.group(2)}>"
    return (re.sub(r"[^A-Z_]", "_", raw) or "PERSOANA"), None


def find_known(text: str, known: Mapping[str, str] | None) -> Iterator[Finding]:
    """Nume cunoscute, potrivite fără diacritice, fără majuscule și în orice ordine a cuvintelor."""
    if not known:
        return
    folded = fold(text)
    for name, role_value in known.items():
        tokens = [t for t in re.split(r"[\s\-]+", fold(normalize_ro(name))) if t]
        if not tokens:
            continue
        role, _ = parse_role(role_value)
        orders = set(permutations(tokens)) if len(tokens) <= 3 else {tuple(tokens), tuple(reversed(tokens))}
        for order in orders:
            pattern = r"(?<![\w])" + r"[\s\-]+".join(map(re.escape, order)) + r"(?![\w])"
            for m in re.finditer(pattern, folded):
                yield Finding("NUME", m.start(), m.end(), text[m.start():m.end()], " ".join(sorted(tokens)),
                              role not in PUBLIC_ROLES, role=role, source="known")


# ---------------------------------------------------------------- identificatori publici (doar etichetă)

_CUI_CONTEXT = re.compile(
    r"(?i:\b(?:cui|cif|cod(?:ul)?\s+(?:unic\s+de\s+[îi]nregistrare|fiscal|de\s+identificare\s+fiscal[ăa]))\s*:?\s*)"
    r"((?:RO\s?)?\d{2,10})\b"
)
_CUI_BARE = re.compile(r"\bRO\d{2,10}\b")
_COMPANY_RE = re.compile(
    rf"(?<![\w])(?:S\.?C\.?\s+)?(?:[{_UP}0-9][\w&'\-]*\s+){{1,6}}(?:S\.?R\.?L\.?|S\.?A\.?)(?![\w])"
)
_DOMAIN_RE = re.compile(
    r"(?i)(?<![@\w.\-])(?:https?://)?(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?![\w\-])"
    r"(?:/[^\s<>\"']*)?"
)


def find_public(text: str) -> Iterator[Finding]:
    for m in _CUI_CONTEXT.finditer(text):
        value = m.group(1)
        yield Finding("CUI", m.start(1), m.end(1), value, re.sub(r"\s", "", value).upper(), False)
    for m in _CUI_BARE.finditer(text):
        if std_cui.is_valid(m.group()):
            yield Finding("CUI", m.start(), m.end(), m.group(), m.group(), False)
    for m in _COMPANY_RE.finditer(text):
        yield Finding("FIRMA", m.start(), m.end(), m.group(), fold(m.group()), False)
    for m in _DOMAIN_RE.finditer(text):
        yield Finding("DOMENIU", m.start(), m.end(), m.group(), m.group().lower(), False)


# ---------------------------------------------------------------- toate împreună

def _priority(f: Finding) -> int:
    return _PRIORITY["KNOWN"] if f.source == "known" else _PRIORITY[f.type]


def resolve(findings: Iterable[Finding]) -> list[Finding]:
    """Păstrează potrivirile fără suprapuneri, în ordinea priorității, apoi le sortează după poziție."""
    chosen: list[Finding] = []
    for f in sorted(findings, key=lambda f: (-_priority(f), -(f.end - f.start), f.start)):
        if all(f.end <= c.start or f.start >= c.end for c in chosen):
            chosen.append(f)
    return sorted(chosen, key=lambda f: f.start)


def detect(text: str, known: Mapping[str, str] | None = None, *, public: bool = True) -> list[Finding]:
    """Toate potrivirile dintr-un text (date personale și, opțional, identificatori publici)."""
    found: list[Finding] = []
    found += find_known(text, known)
    found += find_email(text)
    found += find_iban(text)
    found += find_cnp(text)
    found += find_card(text)
    found += find_phone(text)
    found += find_identity_card(text)
    found += find_names(text)
    if public:
        found += find_public(text)
    return resolve(found)
