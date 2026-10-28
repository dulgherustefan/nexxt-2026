"""JSON canonic și hash-uri pentru registrul de probe și pentru diodă.

Forma canonică urmează RFC 8785 (JCS): chei sortate, separatori compacți, UTF-8,
numere în formatul ECMAScript. Așa, un dosar care trece prin browser (JSON.parse /
JSON.stringify) are aceleași hash-uri la întoarcere. Datele calendaristice devin
ISO 8601 cu fus orar, normalizate la UTC.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any
from uuid import UUID

from pydantic import BaseModel

HASH_PREFIX = "sha256:"


def iso_utc(dt: datetime) -> str:
    """ISO 8601 cu offset, în UTC. Un datetime fără fus orar e tratat ca UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_canonical(obj: Any) -> Any:
    """Transformă o valoare Python în tipuri JSON simple, determinist."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, Enum):
        return to_canonical(obj.value)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("canonical JSON: NaN and Infinity are not allowed")
        return obj
    if isinstance(obj, datetime):
        return iso_utc(obj)
    if isinstance(obj, (date, time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, BaseModel):
        return to_canonical(obj.model_dump(mode="python"))
    if isinstance(obj, Mapping):
        return {str(k): to_canonical(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_canonical(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        items = [to_canonical(v) for v in obj]
        return sorted(items, key=canonical_json)
    if isinstance(obj, (bytes, bytearray)):
        return b64url(bytes(obj))
    if isinstance(obj, (PurePath, UUID)):
        return str(obj)
    raise TypeError(f"canonical JSON: unsupported type {type(obj).__name__}")


def _es_number(x: float) -> str:
    """Numărul în formatul ECMAScript (cerința RFC 8785)."""
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    sign = "-" if x < 0 else ""
    parsed = Decimal(repr(abs(x))).as_tuple()  # repr = cele mai puține cifre care refac valoarea
    raw = "".join(map(str, parsed.digits))
    digits = raw.rstrip("0") or "0"
    exponent = int(parsed.exponent) + (len(raw) - len(digits))
    k = len(digits)
    n = k + exponent  # valoarea = 0.d1d2…dk × 10^n
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        body = digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + body


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _es_number(value)
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + _encode(value[k]) for k in keys) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_encode(v) for v in value) + "]"
    raise TypeError(f"canonical JSON: unsupported type {type(value).__name__}")


def canonical_json(obj: Any) -> str:
    """Șirul JSON canonic (RFC 8785)."""
    return _encode(to_canonical(obj))


def canonical_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def normalize_json(obj: Any) -> Any:
    """Valoarea așa cum iese după o trecere prin JSON canonic (ex. 3200.0 → 3200)."""
    return json.loads(canonical_json(obj))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    """SHA-256 hex al formei canonice."""
    return sha256_hex(canonical_bytes(obj))


def prefixed_hash(obj: Any) -> str:
    """Forma `sha256:<hex>` folosită pentru `args_hash`."""
    return HASH_PREFIX + hash_obj(obj)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
