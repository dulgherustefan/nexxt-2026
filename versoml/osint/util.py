"""Utilitare comune OSINT: text românesc, domenii (IDN, sufix public), IP-uri, telefoane."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

# s/t cu sedilă (U+015F, U+0163, U+015E, U+0162) → cu virgulă dedesubt (U+0219, U+021B, U+0218, U+021A)
_CEDILLA = str.maketrans({chr(0x015F): "ș", chr(0x0163): "ț", chr(0x015E): "Ș", chr(0x0162): "Ț"})

# TLD-uri rezervate (RFC 2606/6761). Pe .example și .test stau domeniile sintetice ale demo-ului.
RESERVED_TLDS = frozenset({"example", "test", "invalid", "localhost"})
SYNTHETIC_TLDS = frozenset({"example", "test"})
# Rețelele de documentare (RFC 5737, RFC 3849): IP-urile sintetice ale scenariilor
TEST_NETS = tuple(
    ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def normalize_ro(text: str | None) -> str:
    """NFC + s/t cu sedilă → ș/ț (virgulă dedesubt)."""
    return unicodedata.normalize("NFC", text or "").translate(_CEDILLA)


def strip_diacritics(text: str | None) -> str:
    """Elimină diacriticele (ă→a, ș→s), după normalizarea ș/ț."""
    decomposed = unicodedata.normalize("NFKD", normalize_ro(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def fold(text: str | None) -> str:
    """Formă de comparare: fără diacritice, litere mici, spații comprimate."""
    return re.sub(r"\s+", " ", strip_diacritics(text).casefold()).strip()


# ---------------------------------------------------------------- domenii


@dataclass(frozen=True)
class DomainParts:
    host: str            # ASCII (punycode), litere mici
    unicode_host: str    # forma Unicode, pentru afișare și schelet
    subdomain: str
    label: str           # eticheta înregistrabilă, ASCII
    unicode_label: str
    suffix: str

    @property
    def registered(self) -> str:
        return f"{self.label}.{self.suffix}" if self.suffix else self.label

    @property
    def unicode_registered(self) -> str:
        return f"{self.unicode_label}.{self.suffix}" if self.suffix else self.unicode_label

    @property
    def is_idn(self) -> bool:
        return "xn--" in self.host


@lru_cache(maxsize=1)
def _extractor():
    import tldextract

    # suffix_list_urls=() → doar lista publică inclusă în pachet, fără rețea
    return tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def host_from(value: str | None) -> str:
    """Gazda dintr-un URL sau domeniu, litere mici, fără port, credențiale sau punct final."""
    raw = normalize_ro(value).strip().strip("<>\"'()[]{}")
    if not raw:
        return ""
    if "://" not in raw:
        raw = "//" + raw
    try:
        host = urlsplit(raw).hostname or ""
    except ValueError:
        return ""
    return host.strip().rstrip(".").lower()


def to_ascii(host: str) -> str:
    """Domeniu → ASCII (IDNA 2008 / UTS 46), cu rezervă pe codecul IDNA 2003."""
    host = host.strip().rstrip(".").lower()
    if not host or host.isascii():
        return host
    try:
        import idna

        return idna.encode(host, uts46=True, transitional=False).decode("ascii")
    except Exception:  # noqa: BLE001 - etichete invalide: încercăm codecul vechi
        try:
            return host.encode("idna").decode("ascii")
        except UnicodeError:
            return host


def to_unicode(host: str) -> str:
    """Decodează etichetele punycode (xn--) în Unicode."""
    labels = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = label[4:].encode("ascii").decode("punycode")
            except UnicodeError:
                pass
        labels.append(label)
    return ".".join(labels)


def split_domain(value: str | None) -> DomainParts | None:
    """Împarte gazda în subdomeniu, etichetă și sufix public (cu TLD-urile rezervate tratate separat)."""
    host = host_from(value)
    if not host or parse_ip(host) is not None:
        return None
    ascii_host = to_ascii(host)
    labels = [p for p in ascii_host.split(".") if p]
    if not labels:
        return None
    if labels[-1] in RESERVED_TLDS:
        suffix = labels[-1]
        label = labels[-2] if len(labels) >= 2 else ""
        sub = ".".join(labels[:-2])
    else:
        ext = _extractor()(ascii_host)
        suffix, label, sub = ext.suffix, ext.domain, ext.subdomain
        if not suffix:
            return None
    if not label:
        return None
    return DomainParts(
        host=ascii_host,
        unicode_host=to_unicode(ascii_host),
        subdomain=sub,
        label=label,
        unicode_label=to_unicode(label),
        suffix=suffix,
    )


def registered_domain(value: str | None) -> str:
    parts = split_domain(value)
    return parts.registered if parts else ""


# ---------------------------------------------------------------- IP-uri


def parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None


def is_test_net(ip: IPAddress) -> bool:
    return any(ip in net for net in TEST_NETS if net.version == ip.version)


def is_public_ip(ip: IPAddress) -> bool:
    """Doar adrese globale unicast; blochează privat, loopback, link-local, multicast, rezervat, CGNAT."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None and not is_public_ip(embedded):
            return False
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_private
        and not ip.is_unspecified
    )


# ---------------------------------------------------------------- telefoane


def normalize_phone(value: str | None) -> str | None:
    """Număr → E.164. Numerele românești ies ca +40 urmat de 9 cifre; altele, doar dacă au prefix internațional."""
    raw = normalize_ro(value).strip()
    if not raw:
        return None
    international = raw.startswith("+") or raw.startswith("00")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("40") and len(digits) == 11:
        return "+" + digits
    if not international and digits.startswith("0") and len(digits) == 10:
        return "+40" + digits[1:]
    if international and 8 <= len(digits) <= 15 and not digits.startswith("40"):
        return "+" + digits
    return None


def is_synthetic_phone(e164: str | None) -> bool:
    """Numerele de demo: +40 700 000 xxx."""
    return bool(e164) and e164.startswith("+40700000") and len(e164) == 12
