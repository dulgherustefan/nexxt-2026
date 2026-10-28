"""Punctul de control pe fiecare apel de tool: Cedar (cedarpy), default deny, jurnal de decizii.

- `authorize(principal, action, zona, context)` → `PolicyDecision`, cu motivul în română.
- `guarded(...)`: decorator pentru funcții sync și async; ridică `PolicyDenied`.
- `recent_decisions(limit)`: jurnalul circular; `subscribe(cb)`: abonare (ex. SSE pentru refuzuri).
- Dacă cedarpy nu poate fi folosit, decide evaluatorul Python echivalent și motivul o spune explicit.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import math
import os
import threading
from collections import deque
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from versoml.contracts import PolicyDecision, Zone
from versoml.shared.policy import fallback
from versoml.shared.policy.entities import (
    GROUPS,
    KNOWN_ACTIONS,
    ROOT_GROUP,
    PrincipalRef,
    base_entities,
    parse_principal,
    request_entities,
    valid_action_name,
)

log = logging.getLogger("versoml.policy")

POLICY_FILE = Path(__file__).with_name("policies.cedar")
WALL_BASIS = "zidul anti-tipping-off, Legea 129/2019 art. 38 alin. (2)"

POLICY_TEXT: dict[str, str] = {
    "client-agents-tools": "agenții Judecătorului folosesc tool-urile de citire și ciornă ale zonei client",
    "operator-client-tools": "operatorul uman folosește tool-urile zonei client",
    "motor-system-tools": "motorul de reguli citește registrul, verifică scrisorile și trimite fapte prin diodă",
    "motor-refund": "doar motorul de reguli emite rambursarea, sub plafon sau după aprobarea unui om",
    "mcp-client-tools": "clientul MCP al zonei client are doar lista lui de tool-uri",
    "aml-agents-tools": "agenții Investigatorului folosesc tool-urile zonei AML",
    "analyst-aml-tools": "analistul AML citește și decide pistele",
    "analyst-hold": "doar analistul AML (om) emite semnalul HOLD spre zona client",
    "mcp-aml-tools": "clientul MCP al zonei AML are doar lista lui de tool-uri",
    "wall-client-not-in-aml": "un principal din zona client nu acționează niciodată în zona AML",
    "wall-aml-not-in-client": "un principal din zona AML nu acționează direct în zona client, doar prin diodă",
    "wall-client-no-aml-actions": "tool-urile AML nu sunt accesibile din zona client",
    "wall-aml-no-client-actions": "tool-urile zonei client nu sunt accesibile din zona AML",
    "refund-only-motor": "rambursarea o emite doar motorul de reguli, niciodată un agent sau un om direct",
    "no-llm-moves-money": "niciun agent LLM nu mută bani",
    "hold-only-analyst": "semnalul HOLD îl emite doar analistul AML",
    "facts-only-from-client": "faptele trec dioda doar dinspre zona client spre AML",
    "mcp-no-effects": "un client MCP nu mută bani și nu folosește dioda",
    "default-deny": "nicio politică nu permite cererea (refuz implicit)",
    "invalid-request": "cererea e invalidă (zonă sau nume de acțiune necunoscute)",
}

_MAX_LOG = 1000
_log: deque[PolicyDecision] = deque(maxlen=_MAX_LOG)
_log_lock = threading.Lock()
_subscribers: list[tuple[Callable[[PolicyDecision], None], bool]] = []

_engine_lock = threading.Lock()
_engine_mode = os.environ.get("VERSOML_POLICY_ENGINE", "auto").lower()  # auto | cedar | python
_cedar_state: dict[str, Any] = {}


class PolicyDenied(PermissionError):
    """Apelul a fost refuzat de politici. `decision` conține motivul și politicile."""

    def __init__(self, decision: PolicyDecision):
        self.decision = decision
        super().__init__(decision.reason)


# ------------------------------------------------------------ motorul Cedar

def _cedar() -> tuple[Any, Any, Any]:
    """(modulul cedarpy, PolicySet, Entities), parsate o singură dată. Ridică excepția dacă nu merge."""
    with _engine_lock:
        if "error" in _cedar_state:
            raise RuntimeError(_cedar_state["error"])
        if "policies" not in _cedar_state:
            try:
                import cedarpy

                policies = cedarpy.PolicySet.from_str(POLICY_FILE.read_text(encoding="utf-8"))
                entities = cedarpy.Entities.from_json_str(json.dumps(list(base_entities())))
            except Exception as exc:  # noqa: BLE001 - orice problemă trece pe evaluatorul de rezervă
                _cedar_state["error"] = f"{type(exc).__name__}: {exc}"
                raise
            _cedar_state.update(module=cedarpy, policies=policies, entities=entities)
        return _cedar_state["module"], _cedar_state["policies"], _cedar_state["entities"]


def engine_status() -> dict[str, Any]:
    """Ce evaluator e activ (pentru panoul zidului)."""
    if _engine_mode == "python":
        return {"engine": "python", "ok": False, "detail": "Forțat pe evaluatorul Python (VERSOML_POLICY_ENGINE=python)."}
    try:
        _cedar()
    except Exception as exc:  # noqa: BLE001
        return {"engine": "python", "ok": False, "detail": f"cedarpy indisponibil ({type(exc).__name__}); evaluator de rezervă."}
    return {"engine": "cedar", "ok": True, "detail": f"Cedar (cedarpy), {POLICY_FILE.name}, default deny."}


def set_engine(mode: str) -> None:
    """„auto” (Cedar, cu rezervă Python), „cedar” sau „python” (doar pentru teste și incidente)."""
    global _engine_mode
    if mode not in ("auto", "cedar", "python"):
        raise ValueError("motor necunoscut")
    _engine_mode = mode


def reload_policies() -> None:
    """Recitește `policies.cedar` la următoarea decizie."""
    with _engine_lock:
        _cedar_state.clear()


# ------------------------------------------------------------ cererea

def _zone(value: Zone | str) -> str:
    return value.value if isinstance(value, Zone) else Zone(str(value).strip().lower()).value


def _sanitize(value: Any) -> Any:
    """Contextul în tipuri Cedar: bool, long, string, set, record (Cedar nu are float)."""
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, Enum):
        return _sanitize(value.value)
    if isinstance(value, int):
        return value if -(2**63) <= value < 2**63 else str(value)
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(v) for v in value if v is not None]
    return str(value)


def _evaluate(p: PrincipalRef, action: str, zone: str, ctx: dict[str, Any]) -> tuple[bool, list[str], str, str]:
    """(permis, politici, motor, avertisment)."""
    if _engine_mode != "python":
        try:
            cedarpy, policies, base = _cedar()
            extra = request_entities(p, action)
            entities = base.with_added_json_str(json.dumps(extra)) if extra else base
            result = cedarpy.is_authorized(
                {
                    "principal": {"type": p.type, "id": p.id},
                    "action": {"type": "Action", "id": action},
                    "resource": {"type": "Zone", "id": zone},
                    "context": ctx,
                },
                policies,
                entities,
            )
            names = result.diagnostics.id_annotations_by_reason
            ids = sorted(names.get(r, r) for r in result.diagnostics.reasons)
            warning = f" (avertisment: {len(result.diagnostics.errors)} politici au dat eroare la evaluare)" \
                if result.diagnostics.errors else ""
            return result.allowed, ids, "cedar", warning
        except Exception as exc:  # noqa: BLE001
            if _engine_mode == "cedar":
                raise
            note = f"[ATENȚIE: cedarpy indisponibil ({type(exc).__name__}); a decis evaluatorul Python de rezervă] "
            allowed, ids = fallback.evaluate(fallback.Request(p, action, zone, ctx))
            log.error("Politici: cedarpy indisponibil, folosesc evaluatorul Python de rezervă: %s", type(exc).__name__)
            return allowed, sorted(ids), "python", note
    allowed, ids = fallback.evaluate(fallback.Request(p, action, zone, ctx))
    return allowed, sorted(ids), "python", "[ATENȚIE: evaluatorul Python de rezervă e forțat; Cedar nu rulează] "


def _reason(allowed: bool, ids: list[str], p: PrincipalRef, action: str, zone: str) -> str:
    if allowed:
        return f"Permis ({', '.join(ids)}): {POLICY_TEXT.get(ids[0], ids[0])}."
    if not p.known:
        return f"Refuzat implicit: principalul «{p.name}» nu e cunoscut; nicio politică nu-l permite (default deny)."
    if not ids and action == "refund.issue" and p.type == "System" and zone == "client":
        return ("Refuzat: rambursarea cere context.within_auto_cap == true (sub plafon, fără semnale) "
                "sau context.approved_by_human == true (aprobarea unui om).")
    if not ids:
        return (f"Refuzat implicit: nicio politică nu-i permite lui {p.name} să apeleze «{action}» "
                f"în zona {zone} (default deny).")
    texts = "; ".join(POLICY_TEXT.get(i, i) for i in ids)
    wall = f" ({WALL_BASIS})" if any(i.startswith("wall-") for i in ids) else ""
    return f"Refuzat de politicile {', '.join(ids)}: {texts}{wall}. Cererea: {p.name} → «{action}» în zona {zone}."


def decide(principal: str, action: str, resource_zone: Zone | str, context: dict | None = None) -> PolicyDecision:
    """Decizia, fără jurnalizare (pentru listări de tool-uri)."""
    p = parse_principal(principal)
    action = str(action or "").strip()
    now = datetime.now(timezone.utc)
    try:
        zone = _zone(resource_zone)
    except ValueError:
        return PolicyDecision(allowed=False, principal=p.uid, action=action, resource=f"Zone::{resource_zone!r}",
                              reason=f"Refuzat: zona «{resource_zone}» nu există.", policy_ids=["invalid-request"], at=now)
    resource = f'Zone::"{zone}"'
    if not valid_action_name(action) or action in GROUPS or action == ROOT_GROUP:
        return PolicyDecision(allowed=False, principal=p.uid, action=action, resource=resource,
                              reason=f"Refuzat: «{action}» nu e un nume de tool valid.", policy_ids=["invalid-request"], at=now)
    ctx = _sanitize(dict(context or {}))
    allowed, ids, _engine, note = _evaluate(p, action, zone, ctx)
    reason = (note if note.startswith("[") else "") + _reason(allowed, ids, p, action, zone) + \
        (note if not note.startswith("[") else "")
    return PolicyDecision(allowed=allowed, principal=p.uid, action=action, resource=resource, reason=reason,
                          policy_ids=ids or ["default-deny"], at=now, engine=_engine,
                          case_id=str(ctx.get("case_id")) if ctx.get("case_id") else None)


def _record(decision: PolicyDecision) -> None:
    with _log_lock:
        _log.append(decision)
        subscribers = list(_subscribers)
    if not decision.allowed:
        log.info("Politici: refuz %s → %s (%s)", decision.principal, decision.action, ", ".join(decision.policy_ids))
    for callback, denied_only in subscribers:
        if denied_only and decision.allowed:
            continue
        try:
            callback(decision)
        except Exception:  # noqa: BLE001 - un abonat stricat nu oprește controlul
            log.exception("Politici: abonatul a eșuat")


def authorize(principal: str, action: str, resource_zone: Zone | str, context: dict | None = None) -> PolicyDecision:
    """Decide și jurnalizează. `context` poate avea `within_auto_cap` și `approved_by_human` (bool)."""
    decision = decide(principal, action, resource_zone, context)
    _record(decision)
    return decision


def enforce(principal: str, action: str, resource_zone: Zone | str, context: dict | None = None) -> PolicyDecision:
    """Ca `authorize`, dar ridică `PolicyDenied` la refuz."""
    decision = authorize(principal, action, resource_zone, context)
    if not decision.allowed:
        raise PolicyDenied(decision)
    return decision


def guarded(principal: str, action: str, zone: Zone | str, *, context: dict | Callable[..., dict] | None = None):
    """Decorator: verifică politica înainte de fiecare apel (sync sau async) și ridică `PolicyDenied`.

    `context` poate fi un dict fix sau o funcție care primește argumentele apelului.
    """

    def build_context(args: tuple, kwargs: dict) -> dict:
        if callable(context):
            return dict(context(*args, **kwargs) or {})
        return dict(context or {})

    def decorator(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                enforce(principal, action, zone, build_context(args, kwargs))
                return await fn(*args, **kwargs)

            wrapper: Callable = async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                enforce(principal, action, zone, build_context(args, kwargs))
                return fn(*args, **kwargs)

            wrapper = sync_wrapper
        wrapper.__versoml_policy__ = {"principal": principal, "action": action, "zone": _zone(zone)}  # type: ignore[attr-defined]
        return wrapper

    return decorator


def recent_decisions(limit: int = 50, *, denied_only: bool = False) -> list[PolicyDecision]:
    """Ultimele decizii, cele mai noi primele."""
    with _log_lock:
        items = list(_log)
    items.reverse()
    if denied_only:
        items = [d for d in items if not d.allowed]
    return items[: max(0, limit)]


def clear_decisions() -> None:
    with _log_lock:
        _log.clear()


def subscribe(callback: Callable[[PolicyDecision], None], *, denied_only: bool = False) -> Callable[[], None]:
    """Abonează o funcție la fiecare decizie. Întoarce funcția de dezabonare.

    Pentru SSE din FastAPI: `loop.call_soon_threadsafe(queue.put_nowait, d)` în callback.
    """
    entry = (callback, denied_only)
    with _log_lock:
        _subscribers.append(entry)

    def unsubscribe() -> None:
        with _log_lock:
            if entry in _subscribers:
                _subscribers.remove(entry)

    return unsubscribe


def allowed_tools(principal: str, zone: Zone | str, context: dict | None = None) -> list[str]:
    """Tool-urile cunoscute pe care principalul le poate apela în zonă (pentru listarea MCP)."""
    return [a for a in KNOWN_ACTIONS if decide(principal, a, zone, context).allowed]
