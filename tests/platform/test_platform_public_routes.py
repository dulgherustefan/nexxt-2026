"""What the public website reaches without a session: a case without its evidence, the demo customers' accounts
only, no customer search, no rule changes from a demo session, the demo reset only from this machine, and no file
outside frontend/dist through the website's catch-all route."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from versoml.config import Settings
from versoml.shared.events import now
from versoml.shared.policy import sessions
from versoml.shared.rules import params as rule_params
from versoml.zone_aml import app as aml_app
from versoml.zone_client import app as app_module
from versoml.zone_client.runtime import ClientRuntime
from versoml.zone_client.service import ClientService

CASE = "CT-2026-222222"
IBAN = "RO49AAAA1B31007593840000"
CANDIDATES = [{"tx_id": "TX-1", "amount": 3200.0, "counterparty_iban": IBAN}]


@pytest.fixture
def world(tmp_path, monkeypatch):
    settings = Settings(versoml_var_dir=tmp_path / "var", versoml_operator_mode="demo", versoml_operator_secret=None,
                        versoml_diode_secret=None)
    monkeypatch.setattr(sessions, "get_settings", lambda: settings)
    monkeypatch.setattr(rule_params, "params_path", lambda: tmp_path / "rules_params.json")
    svc = ClientService(ClientRuntime(settings=settings))
    monkeypatch.setattr(app_module, "get_service", lambda: svc)
    return svc, TestClient(app_module.app)


def _login(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {client.post('/api/session/demo').json()['token']}"}


def _case(svc: ClientService) -> None:
    svc.rt.cases.put(CASE, {
        "case_id": CASE, "status": "ASTEAPTA_APROBARE", "run_id": "RUN-1", "received_at": now().isoformat(),
        "verdict": "RAMBURSEAZA_CU_APROBARE", "deadline": "2026-10-30T21:59:59+00:00",
        "complaint": {"text": "I did not make this payment.",
                      "attachments": [{"kind": "sms", "content": f"Pay the fee to {IBAN}"}]},
        "extracted": {"ibans": [IBAN], "points": [{"text": "the customer did not pay"}]},
        "rule_context": {"beneficiary_iban": IBAN, "screen_showed_amount_and_payee": False},
        "clock": {"t1_deadline": "2026-10-30T21:59:59+00:00", "answer_deadline": "2026-11-13T21:59:59+00:00"},
        "letter": {"status": "draft", "body": "We are refunding RON 3,200.00 by the end of tomorrow."},
        "match": {"customer_ref": "CUST-DEMO-01", "tx_id": None, "reason": "Two payments fit", "candidates": CANDIDATES},
        "interrupt": {"pending": True, "kind": "pick_transaction", "prompt": "Which payment?", "candidates": CANDIDATES,
                      "options": ["pick_transaction"], "deadline": "2026-10-30T21:59:59+00:00"}})
    svc.rt.ledger.append(CASE, "bank.transaction", "bank-core.get_transaction", {"tx_id": "TX-1"},
                         {"amount": 3200.0, "currency": "RON", "counterparty_iban": IBAN,
                          "counterparty_name": "Mule Account SRL", "ts": now().isoformat()}, "Payment of RON 3,200.00")


# ---------------------------------------------------------------- the case view


def test_a_case_without_a_session_shows_no_evidence(world):
    svc, client = world
    _case(svc)
    public = client.get(f"/api/cases/{CASE}")
    assert public.status_code == 200
    body = public.json()
    assert IBAN not in json.dumps(body) and "Mule Account SRL" not in json.dumps(body)
    assert body["redacted"] is True
    assert not {"extracted", "rule_context", "story"} & set(body)
    assert body["complaint"]["attachments"] == [] and body["complaint"]["text"]
    [fact] = body["facts"]
    assert "content" not in fact and fact["summary"] == "Payment of RON 3,200.00" and fact["sha256"]
    assert "candidates" not in body["match"] and "candidates" not in body["interrupt"]
    # what the phone demo and the public case view read is still there
    assert body["summary"]["status"] == "ASTEAPTA_APROBARE"
    assert body["clock"]["t1_deadline"] and body["letter"]["body"].startswith("We are refunding")
    assert body["interrupt"]["pending"] is True and body["ledger"]["count"] == 1


def test_an_operator_sees_the_whole_case_and_a_bad_session_is_refused(world):
    svc, client = world
    _case(svc)
    full = client.get(f"/api/cases/{CASE}", headers=_login(client)).json()
    assert "redacted" not in full and full["rule_context"]["beneficiary_iban"] == IBAN
    assert full["facts"][0]["content"]["counterparty_iban"] == IBAN and full["complaint"]["attachments"]
    assert full["interrupt"]["candidates"] and full["match"]["candidates"]
    assert client.get(f"/api/cases/{CASE}", headers={"Authorization": "Bearer v1.forged.token"}).status_code == 401
    assert client.get("/api/cases/CT-2026-404404").status_code == 404


def test_public_events_keep_the_trace_but_not_the_tool_data():
    base = {"zone": "client", "run_id": "RUN-1", "case_id": CASE, "seq": 3, "ts": "2026-10-29T10:00:00Z"}
    call = {**base, "type": "TOOL_CALL_END", "name": "bank-core.get_transaction", "message": "responded",
            "data": {"tool": "bank-core.get_transaction", "args": {"tx_id": "TX-1"},
                     "result": {"ok": True, "preview": {"counterparty_iban": IBAN}}}}
    assert app_module.public_event(call) == {**call, "data": {"tool": "bank-core.get_transaction"}}
    pick = {**base, "type": "CUSTOM", "name": "interrupt", "message": "Which payment?",
            "data": {"kind": "pick_transaction", "candidates": CANDIDATES, "deadline": "2026-10-30"}}
    assert app_module.public_event(pick)["data"] == {"kind": "pick_transaction", "deadline": "2026-10-30"}
    fact = {**base, "type": "CUSTOM", "name": "fact", "message": "Payment of RON 3,200.00",
            "data": {"fact_id": "EV-001", "kind": "bank.transaction", "sha256": "ab"}}
    assert app_module.public_event(fact) == fact


class _Bus:
    def __init__(self, events):
        self.events = events

    async def subscribe(self, channel: str):
        for event in self.events:
            yield event


def _stream(svc, monkeypatch, headers: list[tuple[bytes, bytes]]) -> list[dict]:
    from versoml.contracts import AgentEvent, EventType, Zone

    event = AgentEvent(type=EventType.TOOL_CALL_END, zone=Zone.CLIENT, run_id="RUN-1", case_id=CASE, seq=1, ts=now(),
                       name="bank-core.get_transaction",
                       data={"tool": "bank-core.get_transaction", "args": {"tx_id": "TX-1"},
                             "result": {"preview": {"counterparty_iban": IBAN}}})
    monkeypatch.setattr(svc.rt, "bus", _Bus([event]))

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def run() -> list[dict]:
        request = Request({"type": "http", "method": "GET", "path": f"/api/cases/{CASE}/events", "headers": headers},
                          receive)
        response = await app_module.case_events(CASE, request)
        return [json.loads(item["data"]) async for item in response.body_iterator]

    return asyncio.run(run())


def test_the_event_stream_without_a_session_drops_the_tool_data(world, monkeypatch):
    svc, client = world
    [public] = _stream(svc, monkeypatch, [])
    assert public["data"] == {"tool": "bank-core.get_transaction"} and public["seq"] == 1
    token = client.post("/api/session/demo").json()["token"]
    [full] = _stream(svc, monkeypatch, [(b"authorization", f"Bearer {token}".encode())])
    assert full["data"]["result"]["preview"]["counterparty_iban"] == IBAN


# ---------------------------------------------------------------- roles, customers, the Demo Bank, the demo controls


def test_a_demo_session_approves_but_cannot_change_the_rules(world):
    _, client = world
    demo = _login(client)
    assert client.get("/api/session", headers=demo).json()["operator"]["roles"] == ["approver"]
    refused = client.put("/api/rules/params", json={"auto_refund_cap_ron": 1e9}, headers=demo)
    assert refused.status_code == 403
    assert "Demo sessions can approve cases only" in refused.json()["detail"]
    assert "auto_refund_cap_ron" not in refused.json()["detail"]     # the Rules page reads field names from it
    assert rule_params.get_params()["auto_refund_cap_ron"] == 5000
    token, _ = sessions.issue("OP-RULES", "Rules admin", ["rules"])
    ok = client.put("/api/rules/params", json={"auto_refund_cap_ron": 2000}, headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json()["auto_refund_cap_ron"] == 2000


def test_the_customer_search_needs_a_session(world, monkeypatch):
    svc, client = world
    monkeypatch.setattr(svc, "customers", lambda q, limit: [{"customer_ref": "CUST-DEMO-01", "q": q}])
    assert client.get("/api/customers", params={"q": "+40722000000"}).status_code == 401
    found = client.get("/api/customers", params={"q": "CUST-DEMO-01"}, headers=_login(client))
    assert found.status_code == 200 and found.json()[0]["customer_ref"] == "CUST-DEMO-01"


def test_the_demo_bank_opens_only_the_demo_customers(world, monkeypatch):
    svc, client = world
    opened: list[str] = []
    monkeypatch.setattr(svc, "bank_view", lambda ref: opened.append(ref) or {"customer_ref": ref})

    async def dispute(ref, tx_id, text):
        opened.append(ref)
        return "CT-2026-000001"

    monkeypatch.setattr(svc, "bank_dispute", dispute)
    for ref in ("CUST-DEMO-01", "CUST-DEMO-02"):
        assert client.get(f"/api/bank/{ref}").status_code == 200
    assert client.get("/api/bank/CUST-000123").status_code == 404
    assert client.post("/api/bank/CUST-000123/dispute", json={"transaction_id": "TX-1"}).status_code == 404
    assert client.post("/api/bank/CUST-DEMO-01/dispute", json={"transaction_id": "TX-1"}).json()["case_id"]
    assert opened == ["CUST-DEMO-01", "CUST-DEMO-02", "CUST-DEMO-01"]


def test_the_fake_payment_needs_a_session(world, monkeypatch):
    svc, client = world
    monkeypatch.setattr(svc, "demo_scam", lambda ref: {"transaction_id": "TX-9", "amount": 3200.0, "ref": ref})
    assert client.post("/api/demo/scam", json={"customer_ref": "CUST-DEMO-01"}).status_code == 401
    paid = client.post("/api/demo/scam", json={"customer_ref": "CUST-DEMO-01"}, headers=_login(client))
    assert paid.status_code == 200 and paid.json()["transaction_id"] == "TX-9"


def test_the_demo_reset_works_only_from_this_machine(world):
    svc, client = world
    _case(svc)
    assert client.post("/api/demo/reset").status_code == 403                       # not a loopback address
    local = TestClient(app_module.app, client=("127.0.0.1", 50000))
    tunnelled = local.post("/api/demo/reset", headers={"X-Forwarded-For": "203.0.113.5, 3.4.5.6"})
    assert tunnelled.status_code == 403 and "tunnel" in tunnelled.json()["detail"]
    assert svc.rt.cases.get(CASE)
    assert local.post("/api/demo/reset").json() == {"ok": True} and not svc.rt.cases.get(CASE)
    assert TestClient(app_module.app, client=("::1", 50000)).post("/api/demo/reset").status_code == 200


# ---------------------------------------------------------------- the website's catch-all route


@pytest.mark.parametrize("module", [app_module, aml_app], ids=["client", "aml"])
def test_the_website_serves_no_file_outside_dist(module, tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>console</title>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "frontend" / ".env").write_text("SECRET_KEY=do-not-serve", encoding="utf-8")
    monkeypatch.setattr(module, "DIST", dist)
    client = TestClient(module.app)
    assert client.get("/favicon.svg").text == "<svg/>"
    for path in ("/%2e%2e%2f.env", "/%2e%2e/.env", "/..%2f.env", "/%2e%2e%2f%2e%2e%2ffrontend%2f.env"):
        answer = client.get(path)
        assert "do-not-serve" not in answer.text, path
        assert answer.text.startswith("<!doctype html>"), path               # the console's page, not the file
    # the route's own check, whatever the HTTP client does to the path first
    for path in ("../.env", "../../frontend/.env", str(tmp_path / "frontend" / ".env")):
        assert module.spa(path).path == dist / "index.html", path
