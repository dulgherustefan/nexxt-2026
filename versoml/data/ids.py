"""Identificatori sintetici românești (rețetele din docs/context/12 §2) și convențiile de test ale proiectului.

Convenții (docs/06 §2):
- CNP: cifră de control validă, dar cod de județ fictiv 71–79 (nealocat; 70 e cod real SII, deci îl evităm).
  Un validator strict (python-stdnum) le respinge, ceea ce le marchează ca date de test.
- IBAN RO: coduri de bancă fictive BDEM (Banca Demo), XBNK, YBNK, ZBNK, cu cifre de control mod 97 valide.
- CUI: cifră de control INVALIDĂ, ca să nu cadă niciodată pe o firmă reală.
- Telefoane: intervalul fictiv +40700xxxxxx (aceeași convenție ca numerele escrocilor din scenarii).
- IP-uri: doar TEST-NET (RFC 5737): 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24.
- Domenii: escrocii doar pe .example / .test (RFC 2606).
"""

from __future__ import annotations

import hashlib
import ipaddress
import random
import re
from datetime import date

# ---------------------------------------------------------------- CNP

CNP_WEIGHTS = "279146358279"
TEST_COUNTIES = tuple(range(71, 80))           # fictive: în afara listei de județe (01–52) și a codurilor rare 70/80–83
REAL_COUNTIES = frozenset(list(range(1, 47)) + [51, 52])
_S_CODE = {(1900, "M"): 1, (1900, "F"): 2, (1800, "M"): 3, (1800, "F"): 4, (2000, "M"): 5, (2000, "F"): 6}
_CENTURY = {"1": 1900, "2": 1900, "3": 1800, "4": 1800, "5": 2000, "6": 2000}


def cnp_check_digit(first12: str) -> int:
    r = sum(int(a) * int(b) for a, b in zip(first12, CNP_WEIGHTS)) % 11
    return 1 if r == 10 else r


def generate_cnp(birth_date: date, sex: str, county: int, nnn: int) -> str:
    """CNP cu cifră de control validă. `county` ar trebui să fie din TEST_COUNTIES."""
    s = _S_CODE[(birth_date.year // 100 * 100, sex)]
    body = f"{s}{birth_date:%y%m%d}{county:02d}{nnn:03d}"
    return body + str(cnp_check_digit(body))


def cnp_checksum_ok(cnp: str) -> bool:
    return len(cnp) == 13 and cnp.isdigit() and cnp_check_digit(cnp[:12]) == int(cnp[12])


def cnp_county(cnp: str) -> int:
    return int(cnp[7:9])


def is_test_cnp(cnp: str) -> bool:
    """CNP sintetic al proiectului: cifră de control validă și județ fictiv 71–79."""
    return cnp_checksum_ok(cnp) and cnp_county(cnp) in TEST_COUNTIES


def validate_cnp(cnp: str, *, allow_test_counties: bool = True, today: date | None = None) -> list[str]:
    """Lista de erori (goală = valid). Cu `allow_test_counties=False` se comportă ca un validator strict."""
    if len(cnp) != 13 or not cnp.isdigit():
        return ["format: sunt necesare exact 13 cifre"]
    errors: list[str] = []
    if cnp[0] not in _CENTURY:
        errors.append(f"S={cnp[0]} nepermis")
    county = cnp_county(cnp)
    if county not in REAL_COUNTIES and not (allow_test_counties and county in TEST_COUNTIES):
        errors.append(f"cod județ JJ={county:02d} nepermis")
    if cnp[9:12] == "000":
        errors.append("NNN=000 (interval 001-999)")
    year = _CENTURY.get(cnp[0], 1900) + int(cnp[1:3])
    try:
        born = date(year, int(cnp[3:5]), int(cnp[5:7]))
        if born > (today or date.today()):
            errors.append("data nașterii este în viitor")
    except ValueError:
        errors.append("data nașterii inexistentă")
    if cnp_check_digit(cnp[:12]) != int(cnp[12]):
        errors.append("cifra de control greșită")
    return errors


# ---------------------------------------------------------------- CUI / CIF

CUI_WEIGHTS = "753217532"


def cui_check_digit(body: str) -> int:
    """`body` = cifrele fără cifra de control (max. 9)."""
    return sum(int(a) * int(b) for a, b in zip(body.zfill(9), CUI_WEIGHTS)) * 10 % 11 % 10


def normalize_cui(value: str) -> str:
    v = value.upper().replace(" ", "").replace("-", "").replace(".", "")
    return v[2:] if v.startswith("RO") else v


def cui_checksum_ok(value: str) -> bool:
    cui = normalize_cui(value)
    return cui.isdigit() and 2 <= len(cui) <= 10 and cui[0] != "0" and cui_check_digit(cui[:-1]) == int(cui[-1])


def validate_cui(value: str) -> list[str]:
    cui = normalize_cui(value)
    if not cui.isdigit():
        return ["format: doar cifre (după eliminarea prefixului RO)"]
    if not 2 <= len(cui) <= 10:
        return ["lungime în afara intervalului 2-10"]
    if cui[0] == "0":
        return ["începe cu 0"]
    if cui_check_digit(cui[:-1]) != int(cui[-1]):
        return ["cifra de control greșită"]
    return []


def make_invalid_cui(body: str) -> str:
    """CUI cu cifra de control greșită în mod deliberat (nu poate fi o firmă reală)."""
    good = cui_check_digit(body)
    bad = (good + 1 + int(hashlib.sha256(body.encode()).hexdigest(), 16) % 9) % 10
    if bad == good:  # imposibil matematic (1..9 față de good), dar păstrăm garda
        bad = (good + 5) % 10
    return body + str(bad)


def generate_invalid_cui(rng: random.Random, length: int = 8) -> str:
    body = str(rng.randint(1, 9)) + "".join(rng.choice("0123456789") for _ in range(length - 2))
    return make_invalid_cui(body)


# ---------------------------------------------------------------- IBAN RO

OWN_BANK = "BDEM"
FICTIVE_BANKS: dict[str, str] = {
    "BDEM": "Banca Demo (fictivă)",
    "XBNK": "Banca X (fictivă)",
    "YBNK": "Banca Y (fictivă)",
    "ZBNK": "Banca Z (fictivă)",
}
OTHER_BANKS = ("XBNK", "YBNK", "ZBNK")


def _numeric(s: str) -> int:
    return int("".join(str(int(c, 36)) for c in s))


def iban_check_digits(country: str, bban: str) -> str:
    return f"{98 - _numeric((bban + country + '00').upper()) % 97:02d}"


def make_iban(bank: str, account16: str) -> str:
    account16 = account16.upper()
    if len(account16) != 16 or len(bank) != 4:
        raise ValueError("IBAN RO: cod bancă de 4 litere + 16 caractere")
    return "RO" + iban_check_digits("RO", bank + account16) + bank + account16


def generate_iban(rng: random.Random, bank: str = OWN_BANK) -> str:
    return make_iban(bank, "".join(rng.choice("0123456789") for _ in range(16)))


def normalize_iban(iban: str) -> str:
    return re.sub(r"\s+", "", iban or "").upper()


def validate_iban_ro(iban: str) -> list[str]:
    s = normalize_iban(iban)
    if not re.fullmatch(r"RO\d{2}[A-Z]{4}[0-9A-Z]{16}", s):
        return ["format: RO + 2 cifre + 4 litere (cod bancă) + 16 alfanumerice = 24"]
    if _numeric(s[4:] + s[:4]) % 97 != 1:
        return ["cifre de control (mod 97) greșite"]
    return []


def iban_bank_code(iban: str) -> str:
    return normalize_iban(iban)[4:8]


def bank_bic(code: str) -> str:
    return f"{code}ROBU"


def mask_iban(iban: str) -> str:
    s = normalize_iban(iban)
    return f"{s[:4]} {s[4:8]} **** **** **** {s[-4:]}"


def format_iban(iban: str) -> str:
    s = normalize_iban(iban)
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))


# ---------------------------------------------------------------- ONRC (format nou, cifra neoficială)


def onrc_check_digit(first13: str) -> int:
    return sum(int(c) for c in str(ord(first13[0]) % 10) + first13[1:]) % 10


def generate_onrc(rng: random.Random, year: int, register: str = "J", county: int | None = None) -> str:
    jj = 0 if year > 2024 else (county if county is not None else rng.choice([40, 12, 22, 35, 13, 8]))
    body = f"{register}{year:04d}{rng.randint(1, 999999):06d}{jj:02d}"
    return body + str(onrc_check_digit(body))


# ---------------------------------------------------------------- telefoane

FICTIVE_PHONE_PREFIX = "+40700"


def fictive_phone(n: int) -> str:
    """+40700 + 6 cifre. Numerele sub 100000 sunt rezervate scenariilor (ex. +40700000111)."""
    return f"{FICTIVE_PHONE_PREFIX}{n:06d}"


def normalize_phone(value: str) -> str:
    """Formă E.164 pentru numere românești: '0700 000 111' / '0040700000111' -> '+40700000111'."""
    digits = re.sub(r"[^\d+]", "", value or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "+4" + digits
    if digits.startswith("40") and len(digits) == 11:
        digits = "+" + digits
    return digits


# ---------------------------------------------------------------- IP-uri TEST-NET (RFC 5737)

TEST_NETS = {
    "home": ipaddress.ip_network("198.51.100.0/24"),     # conexiunile de acasă ale clienților
    "mobile": ipaddress.ip_network("192.0.2.0/24"),      # date mobile ale clienților
    "attacker": ipaddress.ip_network("203.0.113.0/24"),  # infrastructura escrocilor
}


def test_ip(rng: random.Random, kind: str = "home") -> str:
    net = TEST_NETS[kind]
    return str(net.network_address + rng.randint(1, 254))


def is_test_net_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in TEST_NETS.values())


# ---------------------------------------------------------------- domenii

RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")
_MULTI_SUFFIXES = ("com.ro", "org.ro", "co.uk", "com.md", "info.ro", "gov.ro")


def host_of(url_or_domain: str) -> str:
    s = (url_or_domain or "").strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.split("@")[-1].split(":")[0]
    return s.strip(".")


def registered_domain(url_or_domain: str) -> str:
    """Domeniul înregistrat (eTLD+1), fără listă publică de sufixe: 'plata.x.example' -> 'x.example'."""
    host = host_of(url_or_domain)
    if host.startswith("www."):
        host = host[4:]
    labels = [p for p in host.split(".") if p]
    if len(labels) <= 2:
        return ".".join(labels)
    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def is_reserved_domain(domain: str) -> bool:
    return host_of(domain).endswith(RESERVED_TLDS)


# ---------------------------------------------------------------- utilitare deterministe


def stable_int(*parts: object, bits: int = 48) -> int:
    """Întreg stabil între procese (nu depinde de PYTHONHASHSEED)."""
    h = hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()
    return int(h, 16) % (1 << bits)


def sub_rng(*parts: object) -> random.Random:
    """Generator aleator derivat, determinist, pentru un sub-flux (ex. ('demo-mule', 7))."""
    return random.Random(stable_int(*parts, bits=63))


def hex_id(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def pseudonym(prefix: str, value: str, salt: str = "versoml-sintetic") -> str:
    """Pseudonim stabil (ex. TIT-1a2b3c4d) pentru o referință internă; nu se poate inversa fără tabel."""
    return f"{prefix}-{hashlib.sha256(f'{salt}:{value}'.encode()).hexdigest()[:8]}"
