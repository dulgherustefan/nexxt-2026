"""Demo-ul cap-coadă prin HTTP, cu cele două procese reale (zona client și zona AML).

Pagina falsă „trimite" banii → clientul contestă din Banca Demo → Judecătorul rambursează la T+1 →
DisputeFacts trece prin diodă → pista AML apare în procesul AML → zidul refuză atacurile.
LLM offline și OSINT pe înregistrări: testul nu depinde de rețea.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} nu a pornit")


@pytest.fixture(scope="module")
def zones(tmp_path_factory):
    var = tmp_path_factory.mktemp("var_e2e")
    client_port, aml_port = _free_port(), _free_port()
    env = dict(os.environ, VERSOML_VAR_DIR=str(var), VERSOML_LLM_MODE="offline", VERSOML_OSINT_MODE="fixture", PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               VERSOML_CLIENT_PORT=str(client_port), VERSOML_AML_PORT=str(aml_port), VERSOML_DIODE_SECRET="test-secret")
    seed = subprocess.run([sys.executable, "-m", "versoml.data.seed"], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300)
    assert seed.returncode == 0, seed.stderr[-2000:]
    subprocess.run([sys.executable, "-m", "versoml.ml.train", "--quick"], cwd=ROOT, env=env, capture_output=True, timeout=600)
    procs = []
    for zone, target, port in (("client", "versoml.zone_client.app:app", client_port),
                               ("aml", "versoml.zone_aml.app:app", aml_port)):
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port",
                                       str(port), "--log-level", "warning"], cwd=ROOT, env={**env, "VERSOML_ZONE": zone}))
    try:
        _wait(f"http://127.0.0.1:{client_port}/api/meta")
        _wait(f"http://127.0.0.1:{aml_port}/api/meta")
        yield f"http://127.0.0.1:{client_port}", f"http://127.0.0.1:{aml_port}"
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def _until(fn, timeout: float = 120, every: float = 0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(every)
    return last


def test_meta_reports_two_zones(zones):
    client, aml = zones
    assert httpx.get(f"{client}/api/meta").json()["zone"] == "client"
    assert httpx.get(f"{aml}/api/meta").json()["zone"] == "aml"


def test_demo_flow_refund_and_aml_lead(zones):
    client, aml = zones
    tx = httpx.post(f"{client}/api/demo/scam", json={"customer_ref": "CUST-DEMO-01"}, timeout=30).json()
    assert tx["transaction_id"]
    case_id = httpx.post(f"{client}/api/bank/CUST-DEMO-01/dispute",
                         json={"transaction_id": tx["transaction_id"], "text": None}, timeout=30).json()["case_id"]

    def finished():
        detail = httpx.get(f"{client}/api/cases/{case_id}", timeout=10).json()
        if detail["interrupt"].get("pending"):
            httpx.post(f"{client}/api/cases/{case_id}/approve", json={"action": "approve", "approver": "OPERATOR-TEST"})
        return detail if detail["ledger"].get("sealed") else None

    detail = _until(finished, timeout=180)
    assert detail, "cazul nu s-a terminat"
    t1 = next(d for d in detail["decisions"] if d["question"] == "rambursare_t1")
    assert t1["decision"] in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")
    assert detail["summary"]["status"] == "RAMBURSAT"
    assert all(d["rule_ids"] for d in detail["decisions"])
    bank = httpx.get(f"{client}/api/bank/CUST-DEMO-01").json()
    assert any(n["text"].startswith("We refunded RON ") for n in bank["notifications"])
    verify = httpx.get(f"{client}/api/ledger/{case_id}").json()["verify"]
    assert verify["valid"] is True

    leads = _until(lambda: httpx.get(f"{aml}/api/aml/leads").json(), timeout=60)
    assert leads, "pista AML nu a apărut prin diodă"
    referrals = httpx.get(f"{aml}/api/aml/referrals").json()
    assert any(r["case_id"] == case_id for r in referrals)


def test_wall_attacks_are_blocked(zones):
    client, _ = zones
    for kind in ("read_aml_tool", "letter_tipping_off", "prompt_injection", "diode_text_field"):
        result = httpx.post(f"{client}/api/wall/attack", json={"kind": kind}, timeout=20).json()
        assert result["blocked"] is True, (kind, result)


def test_diode_rejects_unsigned_or_extra_fields(zones):
    _, aml = zones
    bad = httpx.post(f"{aml}/diode/inbox", content=b'{"case_id": "X", "note": "text liber"}',
                     headers={"X-VersoML-Signature": "nope"})
    assert bad.status_code == 400


def test_client_zone_has_no_aml_routes(zones):
    client, _ = zones
    assert httpx.get(f"{client}/api/aml/leads").status_code == 404


def test_intake_preview_and_customer_search(zones):
    client, _ = zones
    found = httpx.get(f"{client}/api/customers", params={"q": "CUST-DEMO-01"}, timeout=20).json()
    assert found and found[0]["customer_ref"] == "CUST-DEMO-01" and found[0]["alias"] == "Demo Customer 01"
    assert set(found[0]) >= {"customer_ref", "alias", "city", "accounts", "last_tx_at"} and len(found) <= 20
    assert "full_name" not in found[0] and "phone" not in found[0]
    preview = httpx.post(f"{client}/api/intake/preview", json={
        "text": "Ieri mi-au dispărut 3.200 lei după un SMS de la curier: https://livrare-bancademo.example/colet/RO1",
        "customer_ref": "CUST-DEMO-01", "source": "email"}, timeout=60).json()
    assert set(preview) == {"language", "injection_suspected", "customer", "match", "extracted"}
    assert preview["customer"]["customer_ref"] == "CUST-DEMO-01" and preview["language"] == "ro"
    assert preview["extracted"]["amounts"] == [3200.0] and preview["extracted"]["urls"]
    assert {"customer_ref", "tx_id", "confidence", "needs_human", "reason", "candidates"} <= set(preview["match"])
    assert httpx.post(f"{client}/api/intake/preview", json={"text": " "}).status_code == 400


def test_free_form_case_without_identifiers_takes_the_declared_path(zones):
    client, _ = zones
    case_id = httpx.post(f"{client}/api/cases", json={"complaint": {
        "text": "Someone took money from my account last week. I did not do it.", "source": "web_form"}}).json()["case_id"]
    httpx.post(f"{client}/api/cases/{case_id}/run")
    detail = _until(lambda: (d := httpx.get(f"{client}/api/cases/{case_id}", timeout=10).json())["ledger"].get("sealed")
                    and d, timeout=180)
    assert detail, "the case did not finish"
    assert detail["match"]["customer_ref"] is None and detail["match"]["needs_human"] is True
    assert [r["node"] for r in detail["routing"]][0] == "colector_tranzactie"
    t1 = next(d for d in detail["decisions"] if d["question"] == "rambursare_t1")
    assert t1["decision"] == "INFORMATII_SUPLIMENTARE" and t1["requires_human"] and "DSP-53" in t1["rule_ids"]
    assert detail["reasons"][0]["decision"] == "INFORMATII_SUPLIMENTARE" and detail["reasons"][0]["rule_id"] == "DSP-53"
    assert detail["numeric_check"]["passed"] is True
    assert detail["campaign"] is None or isinstance(detail["campaign"], dict)
    assert {"scenario_phrase", "approved_by", "approved_at"} <= set(detail["summary"])
    assert isinstance(httpx.get(f"{client}/api/cases/{case_id}/precedents").json(), list)
    assert httpx.get(f"{client}/api/cases/CT-2026-000000/precedents").status_code == 404
    bad = httpx.post(f"{client}/api/cases/{case_id}/approve", json={"action": "pay_now"})
    assert bad.status_code == 400


def test_knowledge_base_endpoints_answer_in_both_zones(zones):
    client, aml = zones
    stats = httpx.get(f"{client}/api/kb/stats", timeout=60).json()
    assert {"chunks", "embedding_model", "dense", "built_at"} <= set(stats)
    assert isinstance(httpx.get(f"{client}/api/kb/search", params={"q": "refund deadline", "k": 3}, timeout=60).json(), list)
    answer = httpx.post(f"{client}/api/kb/ask", json={"question": "By when must the bank refund?"}, timeout=60).json()
    assert {"question", "answer", "citations", "grounded", "mode"} <= set(answer)
    assert isinstance(httpx.get(f"{aml}/api/aml/kb/search", params={"q": "money mule"}, timeout=60).json(), list)
    today = httpx.get(f"{client}/api/stats").json()["today"]
    assert today["timezone"] == "Europe/Bucharest" and len(today["date"]) == 10
