"""Jurnalul zidului: blocările (scrisori, diodă, scanner), pentru `GET /api/wall` și SSE.

Evenimentele nu conțin niciodată conținut AML sau corpul unui pachet respins: doar stratul,
tipul, cazul, motivele și termenii găsiți.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("versoml.wall")

_events: deque[dict[str, Any]] = deque(maxlen=500)
_lock = threading.Lock()
_subscribers: list[Callable[[dict[str, Any]], None]] = []


def record(layer: int, kind: str, *, case_id: str | None = None, reasons: list[str] | None = None,
           terms: list[str] | None = None, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Adaugă un eveniment: {at, layer, kind, case_id, reasons, terms, detail}."""
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "layer": layer,
        "kind": kind,
        "case_id": case_id,
        "reasons": list(reasons or []),
        "terms": list(terms or []),
        "detail": dict(detail or {}),
    }
    with _lock:
        _events.append(event)
        subscribers = list(_subscribers)
    log.info("Zid: blocare strat %s (%s) pe cazul %s", layer, kind, case_id or "-")
    for callback in subscribers:
        try:
            callback(event)
        except Exception:  # noqa: BLE001
            log.exception("Zid: abonatul a eșuat")
    return event


def recent(limit: int = 50, *, kind: str | None = None) -> list[dict[str, Any]]:
    """Ultimele evenimente, cele mai noi primele."""
    with _lock:
        items = list(_events)
    items.reverse()
    if kind:
        items = [e for e in items if e["kind"] == kind]
    return items[: max(0, limit)]


def blocks(limit: int = 50) -> list[dict[str, Any]]:
    """Forma pentru `GET /api/wall` → `blocks:[{at, case_id, reasons, terms}]` (doar scrisorile)."""
    return [{k: e[k] for k in ("at", "case_id", "reasons", "terms")} for e in recent(limit, kind="letter_block")]


def subscribe(callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
    with _lock:
        _subscribers.append(callback)

    def unsubscribe() -> None:
        with _lock:
            if callback in _subscribers:
                _subscribers.remove(callback)

    return unsubscribe


def clear() -> None:
    with _lock:
        _events.clear()
