"""Normalizarea textului românesc și formatarea sumelor (docs/context/12 §5.3).

Regula proiectului: ș/ț cu virgulă dedesubt (U+0219/U+021B). Intrarea se normalizează
(ş/ţ cu sedilă, U+015F/U+0163, devin ș/ț) înainte de orice comparație.
"""

from __future__ import annotations

import re
import unicodedata

SPRE_VIRGULA = str.maketrans("şţŞŢ", "șțȘȚ")
FARA_DIACRITICE = str.maketrans("ăâîșțĂÂÎȘȚşţŞŢ", "aaistAAISTstST")
_CEDILA = set("şţŞŢ")


def normalize_ro(text: str) -> str:
    """ş/ţ cu sedilă -> ș/ț cu virgulă. Restul textului rămâne neschimbat."""
    return text.translate(SPRE_VIRGULA)


def strip_diacritics(text: str) -> str:
    """Elimină diacriticele românești (ă â î ș ț, inclusiv formele cu sedilă)."""
    out = text.translate(FARA_DIACRITICE)
    # orice alt semn combinat (ex. é din nume străine)
    return "".join(c for c in unicodedata.normalize("NFD", out) if not unicodedata.combining(c))


def has_cedilla(text: str) -> bool:
    return any(c in _CEDILA for c in text)


def fold(text: str) -> str:
    """Formă de comparație: virgulă, fără diacritice, litere mici, spații comprimate."""
    return re.sub(r"\s+", " ", strip_diacritics(normalize_ro(text)).lower()).strip()


def fmt_number_ro(value: float, decimals: int = 2) -> str:
    """3200.5 -> '3.200,50' (separator de mii punct, zecimale cu virgulă)."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_lei(value: float, style: int = 0) -> str:
    """Variante de scriere a unei sume, ca în reclamațiile reale.

    0: '3.200 lei' (fără zecimale dacă suma e întreagă), 1: '3.200,00 lei', 2: '3200 RON', 3: '3.200 RON',
    4: '3200 de lei'.
    """
    whole = abs(value - round(value)) < 1e-9
    if style == 1:
        return f"{fmt_number_ro(value)} lei"
    if style == 2:
        return f"{value:.0f} RON" if whole else f"{value:.2f} RON"
    if style == 3:
        return f"{fmt_number_ro(value, 0 if whole else 2)} RON"
    if style == 4:
        return f"{value:.0f} de lei" if whole else f"{fmt_number_ro(value)} lei"
    return f"{fmt_number_ro(value, 0 if whole else 2)} lei"


LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
        "septembrie", "octombrie", "noiembrie", "decembrie"]
ZILE = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]
