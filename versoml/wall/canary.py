"""Canary tokens planted in the AML files (the wall, layer 5).

The registry keeps ONLY the SHA-256 hashes of the tokens (`var/wall/canary_hashes.json`), so the client-zone
scanner recognizes a leaked token without holding any AML content. Detection survives capitals, spaces,
punctuation, Unicode hyphens, invisible characters, Cyrillic and Greek lookalikes, 0/1/8 for O/I/B and reversed text.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeVar

log = logging.getLogger("versoml.wall.canary")
T = TypeVar("T")
_RETRIES = 200
_PAUSE = 0.005

PREFIX = "ZX"
BODY_LEN = 10
BASE32 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
_HASH_DOMAIN = "versoml:canary:v1:"

# Common lookalikes -> the Latin letter (Cyrillic and Greek)
_CONFUSABLES = str.maketrans({
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041a": "K", "\u041c": "M", "\u041d": "H", "\u041e": "O",
    "\u0420": "P", "\u0421": "C", "\u0422": "T", "\u0423": "Y", "\u0425": "X", "\u0430": "a", "\u0435": "e",
    "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u043a": "k", "\u043c": "m",
    "\u0442": "t", "\u0417": "3", "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H",
    "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N", "\u039f": "O", "\u03a1": "P", "\u03a4": "T",
    "\u03a5": "Y", "\u03a7": "X", "\u03bf": "o", "\u03c7": "x",
})
_DIGIT_FIX = str.maketrans({"0": "O", "1": "I", "8": "B"})


def _compact(text: str) -> str:
    """Letters and digits only, in capitals, after NFKC and the lookalike map."""
    norm = unicodedata.normalize("NFKC", text).translate(_CONFUSABLES).upper()
    return "".join(ch for ch in norm if ch.isascii() and ch.isalnum())


def token_hash(token: str) -> str:
    """The hash of a token, after normalization (the form stored in the registry)."""
    compact = _compact(token)
    body = compact[len(PREFIX):].translate(_DIGIT_FIX)
    return hashlib.sha256(f"{_HASH_DOMAIN}{PREFIX}{body}".encode("ascii")).hexdigest()


def _candidates(compact: str) -> Iterator[str]:
    for stream in (compact, compact[::-1]):
        start = 0
        while True:
            i = stream.find(PREFIX, start)
            if i < 0:
                break
            body = stream[i + len(PREFIX): i + len(PREFIX) + BODY_LEN].translate(_DIGIT_FIX)
            if len(body) == BODY_LEN and all(c in BASE32 for c in body):
                yield PREFIX + body
            start = i + 1


@contextmanager
def _file_lock(path: Path, timeout: float = 5.0) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):  # on Windows: PermissionError while the lock is being deleted
            if time.monotonic() > deadline:
                with suppress(FileNotFoundError, PermissionError):
                    lock.unlink()  # a lock left behind by a stopped process
                deadline = time.monotonic() + timeout
            time.sleep(_PAUSE)
    try:
        yield
    finally:
        os.close(fd)
        for _ in range(_RETRIES):
            try:
                lock.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(_PAUSE)


def _retry(operation: Callable[[], T]) -> T:
    """Retries the operations Windows refuses for a moment (a file moved or deleted by another thread)."""
    for attempt in range(_RETRIES):
        try:
            return operation()
        except PermissionError:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_PAUSE)
    raise AssertionError("unreachable")


def default_path() -> Path:
    from versoml.config import get_settings

    return get_settings().var_dir / "wall" / "canary_hashes.json"


class CanaryRegistry:
    """`mint(lead_id)` in the AML zone; `scan(text)` anywhere. The file holds only hashes."""

    def __init__(self, path: Path | str | None = None, *, secret: bytes | None = None):
        self.path = Path(path) if path else default_path()
        self._secret = secret
        self._lock = threading.Lock()
        self._hashes: frozenset[str] = frozenset()
        self._stamp: tuple[float, int] | None = None

    # ------------------------------------------------------------ the file

    def _read_file(self) -> set[str]:
        """The hashes in the file (empty if there is no file). Read errors are raised: an empty registry is never guessed."""
        try:
            raw = _retry(lambda: self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return set()
        data = json.loads(raw)
        return {h for h in data.get("hashes", []) if isinstance(h, str) and len(h) == 64}

    def _load(self) -> frozenset[str]:
        try:
            stat = self.path.stat()
            stamp: tuple[float, int] | None = (stat.st_mtime, stat.st_size)
        except FileNotFoundError:
            stamp = None
        with self._lock:
            if stamp != self._stamp:
                try:
                    self._hashes = frozenset(self._read_file())
                    self._stamp = stamp
                except (OSError, ValueError):
                    log.warning("Canary: could not reload the registry; using the last known hashes")
            return self._hashes

    def register_hash(self, digest: str) -> None:
        """Adds a hash (without knowing the token)."""
        digest = digest.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("not a SHA-256 hash")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, _file_lock(self.path):
            hashes = self._read_file()  # an error here stops the write: the registry is never half rewritten
            if digest in hashes:
                return
            hashes.add(digest)
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            body = json.dumps({"version": 1, "algorithm": "sha256", "prefix": PREFIX, "hashes": sorted(hashes)},
                              indent=0)
            _retry(lambda: tmp.write_text(body, encoding="utf-8"))
            _retry(lambda: os.replace(tmp, self.path))
            self._stamp = None

    def register_token(self, token: str) -> str:
        digest = token_hash(token)
        self.register_hash(digest)
        return digest

    # ------------------------------------------------------------ public API

    def mint(self, lead_id: str) -> str:
        """A new token for an AML lead, shaped ZX-XXXXXXXXXX (base32). Only its hash is stored."""
        if self._secret:
            raw = hmac.new(self._secret, f"canary:{lead_id}".encode("utf-8"), hashlib.sha256).digest()
        else:
            raw = secrets.token_bytes(16)
        body = base64.b32encode(raw).decode("ascii")[:BODY_LEN]
        token = f"{PREFIX}-{body}"
        self.register_token(token)
        return token

    def scan(self, text: str) -> int:
        """How many occurrences of known tokens the text contains."""
        hashes = self._load()
        if not hashes or not text:
            return 0
        return sum(1 for cand in _candidates(_compact(text)) if token_hash(cand) in hashes)

    def contains(self, text: str) -> bool:
        return self.scan(text) > 0

    def hashes(self) -> frozenset[str]:
        return self._load()

    def __len__(self) -> int:
        return len(self._load())

    def __bool__(self) -> bool:
        # an empty registry is still a registry: `registry or CanaryRegistry()` must not replace it
        return True
