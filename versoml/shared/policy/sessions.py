"""Operator sessions and approval tokens: who signs a decision, and what they were shown when they signed.

- A session is `v1.<payload>.<mac>`. The payload names the operator, their roles and whether it is a demo session;
  the mac is HMAC-SHA256 with the server's secret. The approver of a decision comes from it, never from the body.
- Demo mode (`VERSOML_OPERATOR_MODE=demo`) hands each console a named demo operator, and the ledger records every
  signature made with one as a demo signature. In strict mode only the bank's sign-in issues sessions (`issue`).
- An approval token is an HMAC over what the console showed with a pending decision: the case, the run, the kind of
  decision, the verdict, the amount and the deadline. A signature sends it back; a decision that changed since has
  another token, so a person never signs something they were not shown.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from versoml.config import get_settings

APPROVER = "approver"  # signs case decisions and picks the disputed payment
RULES = "rules"        # changes the rules engine's parameters
ROLES = (APPROVER, RULES)
DEMO_PREFIX = "DEMO-OPERATOR-"
VERSION = "v1"
MIN_SECRET = 16

_generated: bytes | None = None
_lock = threading.Lock()


class SessionError(Exception):
    """The session is missing, malformed, forged, expired or not accepted here. The message says which."""


@dataclass(frozen=True)
class OperatorSession:
    session_id: str
    operator_id: str
    name: str
    roles: tuple[str, ...]
    demo: bool
    issued_at: datetime
    expires_at: datetime

    def has(self, role: str) -> bool:
        return role in self.roles

    def public(self) -> dict[str, Any]:
        """What the console and the ledger may show: everything except the token."""
        return {"session_id": self.session_id, "operator_id": self.operator_id, "name": self.name,
                "roles": list(self.roles), "demo": self.demo, "issued_at": self.issued_at.isoformat(),
                "expires_at": self.expires_at.isoformat()}


def _secret() -> bytes:
    configured = get_settings().versoml_operator_secret
    value = configured.get_secret_value() if configured else ""
    if value:
        if len(value) < MIN_SECRET:
            raise SessionError(f"VERSOML_OPERATOR_SECRET is too short: use at least {MIN_SECRET} characters.")
        return value.encode("utf-8")
    global _generated
    with _lock:
        if _generated is None:
            _generated = secrets.token_bytes(32)
        return _generated


def _mac(purpose: str, message: bytes) -> bytes:
    return hmac.new(_secret(), purpose.encode("ascii") + b"\x00" + message, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _utc(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def demo_mode() -> bool:
    return get_settings().versoml_operator_mode == "demo"


def issue(operator_id: str, name: str, roles: list[str] | tuple[str, ...], *, demo: bool = False,
          hours: float | None = None, now: datetime | None = None) -> tuple[str, OperatorSession]:
    """A signed session for an operator the bank has signed in: (token, session). The sign-in calls this."""
    unknown = sorted(set(roles) - set(ROLES))
    if unknown or not roles:
        raise ValueError(f"Unknown or missing roles: {', '.join(unknown) or '(none)'}; use {', '.join(ROLES)}.")
    operator_id = str(operator_id or "").strip()
    if not operator_id or len(operator_id) > 64:
        raise ValueError("operator_id is missing or too long")
    issued = int((now or datetime.now(UTC)).timestamp())
    life = get_settings().versoml_session_hours if hours is None else hours
    payload = {"sid": secrets.token_hex(8), "op": operator_id, "name": str(name or operator_id)[:80],
               "roles": [r for r in ROLES if r in roles], "demo": bool(demo), "iat": issued,
               "exp": issued + max(60, int(life * 3600))}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = f"{VERSION}.{_b64(raw)}.{_b64(_mac('session', raw))}"
    return token, _session(payload)


def issue_demo(now: datetime | None = None) -> tuple[str, OperatorSession]:
    """A named demo operator for the public demo, with the approver role only: anyone can get one, so the rules
    role (the parameters every later case is decided under) comes only from a real sign-in. Refused outside demo
    mode."""
    if not demo_mode():
        raise SessionError("Demo sessions are off on this server (VERSOML_OPERATOR_MODE=strict): sign in through "
                           "the bank's sign-in.")
    tag = secrets.token_hex(2).upper()
    return issue(f"{DEMO_PREFIX}{tag}", f"Demo operator {tag}", (APPROVER,), demo=True, now=now)


def _session(payload: dict[str, Any]) -> OperatorSession:
    return OperatorSession(session_id=str(payload["sid"]), operator_id=str(payload["op"]), name=str(payload["name"]),
                           roles=tuple(payload["roles"]), demo=bool(payload["demo"]), issued_at=_utc(payload["iat"]),
                           expires_at=_utc(payload["exp"]))


def read(token: str | None, now: datetime | None = None) -> OperatorSession:
    """The session behind a token. Raises `SessionError` with the reason in plain English."""
    if not token:
        raise SessionError("No operator session: a person signs in before signing decisions, changing rule "
                           "parameters or opening the evidence file.")
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != VERSION:
        raise SessionError("The operator session is malformed: sign in again.")
    try:
        raw, mac = _unb64(parts[1]), _unb64(parts[2])
    except (ValueError, binascii.Error) as exc:
        raise SessionError("The operator session is malformed: sign in again.") from exc
    if not hmac.compare_digest(mac, _mac("session", raw)):
        raise SessionError("The operator session's signature does not match this server: sign in again.")
    try:
        payload = json.loads(raw)
        session = _session(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise SessionError("The operator session is malformed: sign in again.") from exc
    if not session.roles or set(session.roles) - set(ROLES):
        raise SessionError("The operator session names an unknown role: sign in again.")
    if (now or datetime.now(UTC)) >= session.expires_at:
        raise SessionError("The operator session has expired: sign in again.")
    if session.demo and not demo_mode():
        raise SessionError("Demo sessions are off on this server: sign in through the bank's sign-in.")
    return session


def _amount(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def approval_token(case_id: str, run_id: str | None, pending: dict[str, Any]) -> str:
    """The token for a pending decision, from what the console shows with it (and, for a payment pick, the
    candidates). Any change to one of them gives another token."""
    shown = {"case_id": str(case_id), "run_id": str(run_id or ""), "kind": str(pending.get("kind") or ""),
             "verdict": str(pending.get("verdict") or ""), "amount": _amount(pending.get("amount")),
             "deadline": str(pending.get("deadline") or ""),
             "candidates": sorted(str(c.get("tx_id")) for c in pending.get("candidates") or [] if isinstance(c, dict))}
    return _b64(_mac("approval", json.dumps(shown, sort_keys=True, separators=(",", ":")).encode("utf-8")))


def same_token(sent: str | None, expected: str | None) -> bool:
    return bool(sent and expected) and hmac.compare_digest(str(sent), str(expected))
