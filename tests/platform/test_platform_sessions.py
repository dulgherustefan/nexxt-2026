"""Operator sessions and approval tokens: signed, short-lived, demo ones marked, bound to what a person was shown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from versoml.config import Settings
from versoml.shared.policy import sessions
from versoml.shared.policy.sessions import SessionError

PENDING = {"kind": "aprobare_rambursare", "verdict": "RAMBURSEAZA_CU_APROBARE", "amount": 6200.0,
           "deadline": "2026-10-30T21:59:59+00:00", "prompt": "Approve?"}


@pytest.fixture(autouse=True)
def demo_settings(tmp_path, monkeypatch):
    settings = Settings(versoml_var_dir=tmp_path / "var", versoml_operator_mode="demo", versoml_operator_secret=None)
    monkeypatch.setattr(sessions, "get_settings", lambda: settings)
    return settings


def _with(monkeypatch, **changes) -> None:
    settings = Settings(versoml_var_dir="var", **{"versoml_operator_mode": "demo", **changes})
    monkeypatch.setattr(sessions, "get_settings", lambda: settings)


def test_a_session_round_trips_and_names_its_operator():
    token, issued = sessions.issue("OP-17", "Ana Pop", ["approver"])
    session = sessions.read(token)
    assert session == issued and session.has("approver") and not session.has("rules") and not session.demo
    assert set(session.public()) == {"session_id", "operator_id", "name", "roles", "demo", "issued_at", "expires_at"}
    assert token not in str(session.public())


def test_a_demo_session_is_a_named_demo_operator_with_both_roles():
    token, session = sessions.issue_demo()
    assert session.operator_id.startswith("DEMO-OPERATOR-") and session.demo
    assert session.roles == ("approver", "rules") and sessions.read(token).demo
    other = sessions.issue_demo()[1]
    assert other.session_id != session.session_id


@pytest.mark.parametrize("token", [None, "", "v1.abc", "v2.a.b", "v1.!!!.???", "nonsense"])
def test_missing_or_malformed_sessions_are_refused(token):
    with pytest.raises(SessionError):
        sessions.read(token)


def test_a_changed_payload_or_another_servers_secret_is_refused(monkeypatch):
    token, _ = sessions.issue("OP-17", "Ana", ["approver"])
    head, payload, mac = token.split(".")
    forged = sessions._b64(sessions._unb64(payload).replace(b'"approver"', b'"rules"'))
    with pytest.raises(SessionError, match="signature"):
        sessions.read(f"{head}.{forged}.{mac}")
    _with(monkeypatch, versoml_operator_secret="another-server-secret-0123")
    with pytest.raises(SessionError, match="signature"):
        sessions.read(token)


def test_sessions_expire():
    start = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    token, session = sessions.issue("OP-17", "Ana", ["approver"], hours=1, now=start)
    assert sessions.read(token, now=start + timedelta(minutes=59)) == session
    with pytest.raises(SessionError, match="expired"):
        sessions.read(token, now=start + timedelta(hours=1))


def test_strict_mode_issues_no_demo_sessions_and_refuses_old_ones(monkeypatch):
    _with(monkeypatch, versoml_operator_secret="a-configured-secret-0123456789")
    demo_token, _ = sessions.issue_demo()
    _with(monkeypatch, versoml_operator_mode="strict", versoml_operator_secret="a-configured-secret-0123456789")
    with pytest.raises(SessionError, match="Demo sessions are off"):
        sessions.issue_demo()
    with pytest.raises(SessionError, match="Demo sessions are off"):
        sessions.read(demo_token)
    token, _ = sessions.issue("OP-17", "Ana", ["approver"])
    assert sessions.read(token).operator_id == "OP-17"


def test_a_short_configured_secret_fails_closed(monkeypatch):
    _with(monkeypatch, versoml_operator_secret="short")
    with pytest.raises(SessionError, match="too short"):
        sessions.issue("OP-17", "Ana", ["approver"])


def test_roles_are_checked():
    with pytest.raises(ValueError):
        sessions.issue("OP-17", "Ana", ["admin"])
    with pytest.raises(ValueError):
        sessions.issue("OP-17", "Ana", [])


def test_the_approval_token_is_bound_to_what_was_shown():
    token = sessions.approval_token("CT-2026-111111", "RUN-1", PENDING)
    assert token == sessions.approval_token("CT-2026-111111", "RUN-1", {**PENDING, "amount": 6200})
    assert token == sessions.approval_token("CT-2026-111111", "RUN-1", {**PENDING, "prompt": "other words"})
    for changed in ({"verdict": "RESPINGE_TARDIV"}, {"amount": 6200.5}, {"deadline": "2026-10-31T21:59:59+00:00"},
                    {"kind": "semnatura_decizie"}):
        assert token != sessions.approval_token("CT-2026-111111", "RUN-1", {**PENDING, **changed}), changed
    assert token != sessions.approval_token("CT-2026-111112", "RUN-1", PENDING)
    assert token != sessions.approval_token("CT-2026-111111", "RUN-2", PENDING)      # a re-run is a new decision
    pick = {"kind": "pick_transaction", "candidates": [{"tx_id": "TX-1"}, {"tx_id": "TX-2"}]}
    assert sessions.approval_token("C", "R", pick) != sessions.approval_token("C", "R", {**pick, "candidates": []})
    assert sessions.same_token(token, token) and not sessions.same_token(None, token) and not sessions.same_token(token, "x")
