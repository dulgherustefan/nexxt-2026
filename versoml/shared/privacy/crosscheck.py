"""A doua verificare a datelor personale, independentă de recunoscătorii care maschează (`recognizers.py`).

Nu împarte cod cu ei: își alege singură candidații (adrese de e-mail, forme de IBAN, șiruri de grupuri de cifre)
și îi validează cu python-stdnum (`stdnum.ro.cnp`, `stdnum.iban`, Luhn) și cu lungimile E.164 pentru telefoane.
Caută doar numele primite (numele cunoscute ale cazului), pe ferestre de cuvinte pliate. Nu are model NER: un
nume scris liber, care nu e printre cele cunoscute, nu îl vede.

Garda dinaintea apelului spre LLM (`PrivacyProxy.assert_llm_safe`) cere ca ambele verificări să nu găsească nimic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from stdnum import iban as std_iban
from stdnum import luhn
from stdnum.exceptions import ValidationError
from stdnum.ro import cnp as std_cnp

from versoml.shared.privacy.text import fold, mask, normalize_ro

_EMAIL = re.compile(r"[^\s@<>()\[\]{}\"',;:]+@[^\s@<>()\[\]{}\"',;:]+\.[A-Za-z]{2,24}")
_IBAN = re.compile(r"(?i)(?<![a-z0-9])[a-z]{2}\d{2}(?:[ \-\u00a0]?[a-z0-9]){11,32}")
# un șir de grupuri de cifre cu câte un separator între ele, dar nu o sumă („+12.500,00"); „(0)" și
# parantezele se scot înainte
_RUN = re.compile(r"(?<![\w+])\+?(?>\d+(?:[ .\-\u00a0]\d+)*)(?!\w|,\d)")
_PARENS = re.compile(r"\s*\(0\)\s*|\s*[()]\s*")
_DATE = re.compile(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}-\d{2}-\d{2}")
# separatorii acceptați în interiorul unei valori: un card nu se scrie cu puncte, un CNP doar cu spații
_SEPARATORS = {"CNP": " \u00a0", "CARD": " -\u00a0", "TELEFON": " .-\u00a0"}


def _is_cnp(digits: str) -> bool:
    if std_cnp.is_valid(digits):
        return True
    if len(digits) != 13 or not 71 <= int(digits[7:9]) <= 79:
        return False
    try:  # județele fictive 71-79 (docs/06 §2): data și cifra de control trebuie să fie reale
        std_cnp.get_birth_date(digits)
    except (ValidationError, ValueError):
        return False
    return std_cnp.calc_check_digit(digits[:12]) == digits[12]


def _is_card(digits: str) -> bool:
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1 or not luhn.is_valid(digits):
        return False
    return digits[0] in "3456" or 2221 <= int(digits[:4]) <= 2720


def _phone(digits: str, plus: bool, lead: str) -> str | None:
    """Numărul în forma E.164, sau None: cu „+" sau „00" lipit de prefixul de țară (`lead` = primul grup), 8-15
    cifre; fără prefix, 10 cifre care încep cu 02, 03 sau 07."""
    if plus:
        number = digits
    elif lead.startswith("00") and len(lead) > 2:
        number = digits[2:]
    else:
        return "+40" + digits[1:] if len(digits) == 10 and digits[0] == "0" and digits[1] in "237" else None
    return "+" + number if 8 <= len(number) <= 15 and number[0] != "0" else None


def _numbers(text: str) -> Iterator[tuple[str, str]]:
    """(tip, valoare) pentru fiecare CNP, card sau telefon. Într-un șir de grupuri câștigă potrivirea cea mai lungă."""
    for m in _RUN.finditer(_PARENS.sub(" ", text)):
        run = m.group()
        plus = run.startswith("+")
        parts = re.split(r"([ .\-\u00a0])", run.lstrip("+"))
        groups, seps = parts[0::2], parts[1::2]
        candidates = []
        for i in range(len(groups)):
            digits = ""
            for j in range(i, len(groups)):
                digits += groups[j]
                if len(digits) > 19:
                    break
                inner = seps[i:j]
                raw = "".join(g + s for g, s in zip(groups[i:j + 1], [*inner, ""]))
                if len(digits) == 13 and digits[0] != "0" and all(s in _SEPARATORS["CNP"] for s in inner) \
                        and _is_cnp(digits):
                    candidates.append((i, j, "CNP", digits))
                elif all(s in _SEPARATORS["CARD"] for s in inner) and _is_card(digits):
                    candidates.append((i, j, "CARD", digits))
                elif all(s in _SEPARATORS["TELEFON"] for s in inner) and not _DATE.search(raw) \
                        and (number := _phone(digits, plus and i == 0, groups[i])):
                    candidates.append((i, j, "TELEFON", number))
        taken: list[tuple[int, int]] = []
        for i, j, kind, value in sorted(candidates, key=lambda c: (c[0] - c[1], c[0])):
            if all(j < a or i > b for a, b in taken):
                taken.append((i, j))
                yield kind, value


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", fold(normalize_ro(text)))


def _blank(text: str, start: int, end: int) -> str:
    """Șterge o valoare găsită (cu spații, aceeași lungime), ca cifrele ei să nu mai fie citite și ca telefon."""
    return text[:start] + " " * (end - start) + text[end:]


def cross_check(text: str, names: Iterable[str] = ()) -> list[dict[str, str]]:
    """Datele personale găsite în text: [{type, masked}], fără valori. `names` = numele persoanelor din caz."""
    found: list[dict[str, str]] = []
    text = normalize_ro(text or "")
    for m in _EMAIL.finditer(text):
        found.append({"type": "EMAIL", "masked": mask(m.group())})
        text = _blank(text, m.start(), m.end())
    pos = 0
    while m := _IBAN.search(text, pos):
        compact = re.sub(r"[ \-\u00a0]", "", m.group()).upper()
        size = next((n for n in range(len(compact), 14, -1) if std_iban.is_valid(compact[:n])), None)
        if not size:
            pos = m.start() + 1
            continue
        found.append({"type": "IBAN", "masked": mask(compact[:size])})
        pos = m.start()
        while size:  # până după ultimul caracter al IBAN-ului: potrivirea poate cuprinde și cuvântul următor
            size -= text[pos].isalnum()
            pos += 1
        text = _blank(text, m.start(), pos)
    found += [{"type": kind, "masked": mask(value)} for kind, value in _numbers(text)]
    words = _words(text)
    windows: dict[int, set[tuple[str, ...]]] = {}
    for name in names:
        tokens = tuple(sorted(_words(name)))
        if not tokens:
            continue
        n = len(tokens)
        if n not in windows:
            windows[n] = {tuple(sorted(words[i:i + n])) for i in range(len(words) - n + 1)}
        if tokens in windows[n]:
            found.append({"type": "NUME", "masked": mask(name)})
    return found
