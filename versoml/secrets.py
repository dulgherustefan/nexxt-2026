"""Încărcarea cheii Bedrock la rulare și redactarea secretelor din loguri.

Cheia stă în `API_KEY.txt` (exclus din git). Se încarcă doar în variabila de mediu
`AWS_BEARER_TOKEN_BEDROCK`; nu se afișează, nu se loghează, nu ajunge în trasări sau UI.
"""

from __future__ import annotations

import logging
import os
import re

from versoml.config import ROOT

KEY_FILE = ROOT / "API_KEY.txt"
ENV_NAME = "AWS_BEARER_TOKEN_BEDROCK"

_registered: set[str] = set()

# Tipare generice de chei, ca rezervă pentru secretele neînregistrate explicit
_KEY_PATTERNS = [
    re.compile(r"ABSK[A-Za-z0-9+/=]{16,}"),
    re.compile(r"bedrock-api-key-[A-Za-z0-9+/=._-]{16,}"),
    re.compile(r"(?i)(authorization|x-api-key|api[_-]?key)(\"?\s*[:=]\s*\"?)(bearer\s+)?[A-Za-z0-9+/=._-]{12,}"),
]


def register_secret(value: str | None) -> None:
    if value and len(value) >= 8:
        _registered.add(value)


def redact(text: str) -> str:
    """Înlocuiește orice secret cunoscut sau orice șir care arată a cheie cu ***."""
    if not text:
        return text
    for secret in _registered:
        if secret in text:
            text = text.replace(secret, "***")
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) + m.group(2) + "***") if m.lastindex and m.lastindex >= 2 else "***", text)
    return text


def _parse_key_file(raw: str) -> str | None:
    """Acceptă fie cheia simplă, fie o linie `NUME=cheie` (cu sau fără ghilimele)."""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and not line.startswith(("ABSK", "bedrock-api-key-")):
            line = line.split("=", 1)[1].strip()
        line = line.strip().strip('"').strip("'").strip()
        if line.lower().startswith("bearer "):
            line = line[7:].strip()
        if len(line) >= 20:
            return line
    return None


def load_bedrock_key() -> bool:
    """Pune cheia în mediu dacă nu e deja acolo. Întoarce doar dacă există o cheie, nu valoarea ei."""
    existing = os.environ.get(ENV_NAME)
    if existing:
        register_secret(existing)
        return True
    if not KEY_FILE.exists():
        return False
    value = _parse_key_file(KEY_FILE.read_text(encoding="utf-8-sig", errors="ignore"))
    if not value:
        return False
    os.environ[ENV_NAME] = value
    register_secret(value)
    return True


def key_format() -> str:
    """Descrie tipul cheii fără să dezvăluie nimic din ea."""
    value = os.environ.get(ENV_NAME, "")
    if not value:
        return "lipsă"
    if value.startswith("ABSK"):
        return "cheie Bedrock pe termen lung"
    if value.startswith("bedrock-api-key-"):
        return "cheie Bedrock pe termen scurt"
    return "format necunoscut"


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - un log stricat nu trebuie să oprească aplicația
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def install_log_redaction() -> None:
    """Atașează filtrul pe toți handler-ii existenți și pe loggerele zgomotoase."""
    flt = RedactingFilter()
    root = logging.getLogger()
    root.addFilter(flt)
    for handler in root.handlers:
        handler.addFilter(flt)
    for name in ("httpx", "httpcore", "anthropic", "botocore", "urllib3", "uvicorn", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.addFilter(flt)
        if name in ("httpcore", "botocore", "urllib3"):
            logger.setLevel(logging.WARNING)
