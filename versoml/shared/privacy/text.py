"""Normalizarea textului românesc, folosită de PrivacyProxy, zid și politici.

- `normalize_ro`: NFC și ș/ț cu virgulă dedesubt în loc de cedilă (regula de intrare).
- `fold`: litere mici, fără diacritice, cratime unificate, cu aceeași lungime ca textul,
  ca pozițiile găsite pe textul pliat să fie valabile și în original.
"""

from __future__ import annotations

import unicodedata

# Cedilă → virgulă dedesubt (scrise cu escape-uri, ca sursa să nu conțină cedile)
_CEDILLA = str.maketrans({"\u015f": "ș", "\u015e": "Ș", "\u0163": "ț", "\u0162": "Ț"})

# Cratime și spații speciale → forma simplă (un caracter pentru un caracter)
_DASHES = "\u2010\u2011\u2012–—\u2015\u2212\ufe58\ufe63\uff0d"
_SPACES = "\u00a0\u2007\u202f\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2008\u2009\u200a\u3000"


def normalize_ro(text: str) -> str:
    """NFC și ș/ț corecte (virgulă dedesubt)."""
    if not text:
        return text or ""
    return unicodedata.normalize("NFC", text).translate(_CEDILLA)


def _fold_char(ch: str) -> str:
    if ch in _DASHES:
        return "-"
    if ch in _SPACES:
        return " "
    base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    if len(base) != 1:
        base = ch
    low = base.lower()
    return low if len(low) == 1 else base


def fold(text: str) -> str:
    """Text pliat pentru potriviri: fără diacritice, litere mici, aceeași lungime."""
    return "".join(_fold_char(ch) for ch in text)


def strip_diacritics(text: str) -> str:
    """Varianta fără diacritice, păstrând literele mari."""
    out = []
    for ch in text:
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        out.append(base if len(base) == 1 else ch)
    return "".join(out)
