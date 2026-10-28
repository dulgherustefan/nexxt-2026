"""Generatoare de identificatori sintetici pentru testele platformei (nume unic, ca să nu se ciocnească)."""

from __future__ import annotations

from stdnum import iban as std_iban

CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)


def make_cnp(sex: str, yymmdd: str, county: int, nnn: int) -> str:
    """CNP sintetic cu cifră de control validă (docs/context/12 §2.1)."""
    body = f"{sex}{yymmdd}{county:02d}{nnn:03d}"
    rest = sum(w * int(d) for w, d in zip(CNP_WEIGHTS, body)) % 11
    return body + ("1" if rest == 10 else str(rest))


def make_iban(bank: str = "BDEM", account: str = "0000060012345678") -> str:
    """IBAN RO sintetic (bancă fictivă BDEM/XBNK, docs/06 §2) cu cifre de control valide."""
    bban = bank + account
    return "RO" + std_iban.calc_check_digits("RO00" + bban) + bban
