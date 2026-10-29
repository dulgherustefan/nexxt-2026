"""The human gate over HTTP: the signer comes from a signed operator session, a signature is bound to the decision it
was shown, whoever set a threshold does not sign the cases decided under it, an MCP proposal never signs, and the
evidence file opens only to an operator while the public QR check answers only to the root in the code."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from versoml.config import Settings
from versoml.shared.events import now
from versoml.shared.policy import sessions
from versoml.shared.rules import params as rule_params
from versoml.zone_client import app as app_module
from versoml.zone_client.runtime import ClientRuntime
from versoml.zone_client.service import PARAMS_LOG, ClientService

CASE = "CT-2026-111111"
PENDING = {"pending": True, "kind": "aprobare_rambursare", "verdict": "RAMBURSEAZA_CU_APROBARE",
           "prompt": "Approve the refund of RON 6,200.00?", "options": ["approve", "reject"], "amount": 6200.0,
           "deadline": "2026-10-30T21:59:59+00:00", "rule_ids": ["DSP-59"]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    settings = Settings(versoml_var_dir=tmp_path / "var", versoml_operator_mode="demo", versoml_operator_secret=None,
                        versoml_diode_secret=None)
    monkeypatch.setattr(sessions, "get_settings", lambda: settings)
    monkeypatch.setattr(rule_params, "params_path", lambda: tmp_path / "rules_params.json")
    svc = ClientService(ClientRuntime(settings=settings))
    resumed: list = []
    svc._drive = lambda case_id, run_id, payload: payload
    svc._spawn = resumed.append
    monkeypatch.setattr(app_module, "get_service", lambda: svc)
    return svc, resumed, TestClient(app_module.app), settings


def _case(svc: ClientService, case_id: str = CASE, decided: bool = True, **interrupt) -> None:
    svc.rt.cases.put(case_id, {"case_id": case_id, "status": "ASTEAPTA_APROBARE", "run_id": "RUN-1",
                               "received_at": now().isoformat(), "complaint": {"text": "I did not make this payment."},
                               "interrupt": {**PENDING, **interrupt}})
    if decided:
        _decided(svc, case_id)


def _decided(svc: ClientService, case_id: str = CASE) -> None:
    svc.rt.ledger.append(case_id, "rules.outcome", "rules.engine", {"engine": "test"}, {"verdict": "x"}, "Rules ran")


def _login(client: TestClient) -> tuple[dict, dict]:
    body = client.post("/api/session/demo").json()
    return {"Authorization": f"Bearer {body['token']}"}, body["operator"]


def _token(client: TestClient, headers: dict, case_id: str = CASE) -> str:
    return client.get(f"/api/cases/{case_id}", headers=headers).json()["interrupt"]["approval_token"]


# ---------------------------------------------------------------- who signs


def test_the_console_gets_a_named_demo_operator(world):
    _, _, client, _ = world
    headers, operator = _login(client)
    assert operator["operator_id"].startswith("DEMO-OPERATOR-") and operator["demo"] is True
    assert client.get("/api/session", headers=headers).json()["operator"]["operator_id"] == operator["operator_id"]
    assert client.get("/api/session").status_code == 401


def test_an_approval_needs_a_session_and_the_signer_is_never_the_body(world):
    svc, resumed, client, _ = world
    _case(svc)
    body = {"action": "approve", "approver": "OPERATOR-90"}
    assert client.post(f"/api/cases/{CASE}/approve", json=body).status_code == 401
    assert client.post(f"/api/cases/{CASE}/approve", json=body,
                       headers={"Authorization": "Bearer v1.forged.token"}).status_code == 401
    headers, operator = _login(client)
    ok = client.post(f"/api/cases/{CASE}/approve", headers=headers,
                     json={**body, "approval_token": _token(client, headers), "reason_code": "FACTS_CONFIRMED"})
    assert ok.status_code == 200 and ok.json()["ok"]
    [command] = resumed
    assert command.resume["approver"] == operator["operator_id"] != "OPERATOR-90"
    assert command.resume["session"]["demo"] is True and command.resume["reason_code"] == "FACTS_CONFIRMED"
    [fact] = [f for f in svc.rt.ledger.facts(CASE) if f.kind == "human.session"]
    assert fact.content["operator"]["demo"] is True and fact.content["approval_token"] == "matched"
    assert "demo session" in fact.summary and operator["operator_id"] in fact.summary
    # the same decision cannot be signed twice
    again = client.post(f"/api/cases/{CASE}/approve", headers=headers, json={"action": "approve"})
    assert again.status_code == 409


def test_a_signature_is_bound_to_the_decision_it_was_shown(world):
    svc, resumed, client, _ = world
    _case(svc)
    headers, _ = _login(client)
    shown = _token(client, headers)
    missing = client.post(f"/api/cases/{CASE}/approve", headers=headers, json={"action": "approve"})
    assert missing.status_code == 409 and "approval_token" in missing.json()["detail"]
    svc.rt.cases.update(CASE, {"interrupt": {**PENDING, "amount": 9200.0}})          # the decision changed meanwhile
    stale = client.post(f"/api/cases/{CASE}/approve", headers=headers, json={"action": "approve", "approval_token": shown})
    assert stale.status_code == 409 and "changed" in stale.json()["detail"]
    assert not resumed
    fresh = client.post(f"/api/cases/{CASE}/approve", headers=headers,
                        json={"action": "reject", "approval_token": _token(client, headers)})
    assert fresh.status_code == 200 and resumed[0].resume["reason_code"] == "FACTS_DISPUTED"


def test_reason_codes_are_checked_and_roles_are_enforced(world):
    svc, resumed, client, _ = world
    _case(svc)
    headers, _ = _login(client)
    token = _token(client, headers)
    bad = client.post(f"/api/cases/{CASE}/approve", headers=headers,
                      json={"action": "approve", "approval_token": token, "reason_code": "FRAUD_SUSPECTED"})
    assert bad.status_code == 400 and "does not fit approve" in bad.json()["detail"]
    rules_only, _ = sessions.issue("OP-RULES", "Rules admin", ["rules"])
    no_role = client.post(f"/api/cases/{CASE}/approve", headers={"Authorization": f"Bearer {rules_only}"},
                          json={"action": "approve", "approval_token": token})
    assert no_role.status_code == 403 and "approver role" in no_role.json()["detail"]
    signer_only, _ = sessions.issue("OP-SIGN", "Signer", ["approver"])
    put = client.put("/api/rules/params", json={"auto_refund_cap_ron": 2000},
                     headers={"Authorization": f"Bearer {signer_only}"})
    assert put.status_code == 403 and "rules role" in put.json()["detail"]
    assert client.post(f"/api/cases/{CASE}/approve", headers=headers, json={"action": "pay_now"}).status_code == 400
    assert not resumed


# ---------------------------------------------------------------- separation of duties


def test_whoever_set_a_threshold_does_not_sign_cases_decided_under_it(world):
    svc, resumed, client, _ = world
    _case(svc, "CT-2026-000001")                                   # decided before the change
    alice, alice_op = _login(client)
    bob, _ = _login(client)
    assert client.put("/api/rules/params", json={"auto_refund_cap_ron": 2000}).status_code == 401
    changed = client.put("/api/rules/params", json={"auto_refund_cap_ron": 2000}, headers=alice)
    assert changed.status_code == 200 and changed.json()["auto_refund_cap_ron"] == 2000
    [log] = client.get("/api/rules/changes", headers=bob).json()
    assert log["operator"]["operator_id"] == alice_op["operator_id"]
    assert log["changed"] == {"auto_refund_cap_ron": {"from": 5000, "to": 2000, "default": False}}
    assert [f.kind for f in svc.rt.ledger.facts(PARAMS_LOG)] == ["rules.params_changed"]

    _case(svc, "CT-2026-000002")                                   # decided under Alice's cap
    sign = {"action": "approve"}
    refused = client.post("/api/cases/CT-2026-000002/approve", headers=alice,
                          json={**sign, "approval_token": _token(client, alice, "CT-2026-000002")})
    assert refused.status_code == 403
    assert "Separation of duties" in refused.json()["detail"] and "auto_refund_cap_ron" in refused.json()["detail"]
    earlier = client.post("/api/cases/CT-2026-000001/approve", headers=alice,
                          json={**sign, "approval_token": _token(client, alice, "CT-2026-000001")})
    assert earlier.status_code == 200
    other = client.post("/api/cases/CT-2026-000002/approve", headers=bob,
                        json={**sign, "approval_token": _token(client, bob, "CT-2026-000002")})
    assert other.status_code == 200 and len(resumed) == 2

    # back to the reviewed default: the cases decided after that are hers to sign again
    assert client.put("/api/rules/params", json={"auto_refund_cap_ron": 5000}, headers=alice).status_code == 200
    _case(svc, "CT-2026-000003")
    after_reset = client.post("/api/cases/CT-2026-000003/approve", headers=alice,
                              json={**sign, "approval_token": _token(client, alice, "CT-2026-000003")})
    assert after_reset.status_code == 200


def test_a_change_counts_from_before_it_is_written(world):
    svc, _, client, _ = world
    alice, alice_op = _login(client)
    client.put("/api/rules/params", json={"client_fraud_signal_threshold": 0.9}, headers=alice)
    [fact] = svc.rt.ledger.facts(PARAMS_LOG)
    setters = svc._params_setters(fact.retrieved_at - timedelta(microseconds=1))
    assert setters["client_fraud_signal_threshold"]["operator_id"] == alice_op["operator_id"]


# ---------------------------------------------------------------- MCP proposals


def test_an_mcp_proposal_is_recorded_and_signs_nothing(world):
    svc, resumed, client, _ = world
    _case(svc)
    out = client.post(f"/api/cases/{CASE}/proposals", json={"action": "approve", "note": "looks fine"})
    assert out.status_code == 200 and out.json()["signed"] is False
    assert not resumed and svc.rt.cases.get(CASE)["interrupt"]["pending"] is True
    [fact] = [f for f in svc.rt.ledger.facts(CASE) if f.kind == "decision.proposal"]
    assert fact.labels.trust.value == "untrusted" and "Not a signature" in fact.summary
    headers, _ = _login(client)
    detail = client.get(f"/api/cases/{CASE}", headers=headers).json()
    assert detail["proposals"][0]["action"] == "approve" and detail["proposals"][0]["fact_id"] == fact.fact_id
    assert client.post(f"/api/cases/{CASE}/proposals", json={"action": "pay"}).status_code == 400
    _case(svc, "CT-2026-000009", kind="pick_transaction", candidates=[{"tx_id": "TX-1"}])
    assert client.post("/api/cases/CT-2026-000009/proposals", json={"action": "approve"}).status_code == 409
    assert client.post("/api/cases/CT-2026-404404/proposals", json={"action": "approve"}).status_code == 404


# ---------------------------------------------------------------- the evidence file and the public check


def test_the_evidence_file_opens_only_to_an_operator_and_reading_never_seals(world):
    svc, _, client, _ = world
    _case(svc)
    headers, _ = _login(client)
    assert client.get(f"/api/ledger/{CASE}").status_code == 401
    assert client.get(f"/api/ledger/{CASE}/export").status_code == 401
    assert client.get(f"/api/ledger/{CASE}/export", headers=headers).status_code == 409   # nothing sealed yet
    assert svc.rt.ledger.latest_seal(CASE) is None
    svc.rt.ledger.seal(CASE)
    svc.rt.ledger.append(CASE, "case.note", "test", {}, {"n": 1}, "One more entry")
    snapshot = client.get(f"/api/ledger/{CASE}", headers=headers).json()
    dossier = client.get(f"/api/ledger/{CASE}/export", headers=headers).json()
    assert len(snapshot["facts"]) == 2 and snapshot["sealed"] is False
    assert dossier["seal"]["count"] == 1 and svc.rt.ledger.latest_seal(CASE)["count"] == 1
    # a whole file is checked for anyone; the console's short form reads the ledger, so it needs a session
    assert client.post("/api/verify", json=dossier).json()["checks"]
    short = {"case_id": CASE, "facts": snapshot["facts"], "seal": snapshot["seal"]}
    assert client.post("/api/verify", json=short).status_code == 401
    assert client.post("/api/verify", json=short, headers=headers).status_code == 200


def test_the_public_qr_check_answers_only_to_the_root_in_the_code(world):
    svc, _, client, _ = world
    _case(svc)
    seal = svc.rt.ledger.seal(CASE)
    assert seal["qr_text"].endswith(f"/verify/{CASE}#{seal['root']}")
    ok = client.post("/api/verify/seal", json={"case_id": CASE, "root": seal["root"]})
    assert ok.status_code == 200
    body = ok.json()
    assert body["intact"] and body["current"] and body["signature_valid"] and body["count"] == 1
    assert "facts" not in body and "Rules ran" not in str(body) and "'verdict'" not in str(body)  # no entry leaks
    assert client.post("/api/verify/seal", json={"case_id": CASE}).status_code == 400
    assert client.post("/api/verify/seal", json={"case_id": CASE, "root": "xyz"}).status_code == 400
    wrong = client.post("/api/verify/seal", json={"case_id": CASE, "root": "0" * 64})
    unknown = client.post("/api/verify/seal", json={"case_id": "CT-2026-999999", "root": seal["root"]})
    assert wrong.status_code == unknown.status_code == 404 and wrong.json() == unknown.json()


def test_strict_mode_hands_out_no_demo_sessions(world, monkeypatch):
    svc, _, client, settings = world
    _case(svc)
    demo, _ = _login(client)
    strict = settings.model_copy(update={"versoml_operator_mode": "strict"})
    monkeypatch.setattr(sessions, "get_settings", lambda: strict)
    assert client.post("/api/session/demo").status_code == 403
    assert client.get(f"/api/ledger/{CASE}", headers=demo).status_code == 401
    token, _ = sessions.issue("OP-17", "Ana Pop", ["approver"])
    assert client.get(f"/api/ledger/{CASE}", headers={"Authorization": f"Bearer {token}"}).status_code == 200
