"""Cheile Ed25519 ale zonelor: una pe zonă, generată la prima folosire.

Fișierele: `zone_<zonă>.key` (PKCS8 PEM, privată) și `zone_<zonă>.pub` (SPKI PEM).
Ambele stau în `var/keys/`, exclus din git. Cheia privată nu părăsește procesul zonei.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from versoml.contracts import Zone
from versoml.shared.ledger.canonical import b64url, b64url_decode

_lock = threading.Lock()


@dataclass(frozen=True)
class ZoneKey:
    zone: Zone
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_b64(self) -> str:
        """Cheia publică brută (32 de octeți), în base64url."""
        raw = self.public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return b64url(raw)

    def sign(self, message: bytes) -> str:
        return b64url(self.private_key.sign(message))


def _write_exclusive(path: Path, data: bytes) -> bool:
    """Scrie fișierul doar dacă nu există (sigur între procese). Întoarce dacă l-a scris."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return True


def load_zone_key(zone: Zone | str, keys_dir: Path) -> ZoneKey:
    """Încarcă perechea de chei a zonei sau o generează dacă lipsește."""
    zone = Zone(zone)
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    priv_path = keys_dir / f"zone_{zone.value}.key"
    pub_path = keys_dir / f"zone_{zone.value}.pub"
    with _lock:
        if not priv_path.exists():
            private = Ed25519PrivateKey.generate()
            pem = private.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            _write_exclusive(priv_path, pem)
        private = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise ValueError(f"{priv_path.name} nu conține o cheie Ed25519")
        public = private.public_key()
        pub_pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        if not pub_path.exists() or pub_path.read_bytes() != pub_pem:
            pub_path.write_bytes(pub_pem)
    return ZoneKey(zone=zone, private_key=private, public_key=public)


def verify_signature(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    """Verifică o semnătură Ed25519 cu o cheie publică brută în base64url."""
    try:
        key = Ed25519PublicKey.from_public_bytes(b64url_decode(public_key_b64))
        key.verify(b64url_decode(signature_b64), message)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True
