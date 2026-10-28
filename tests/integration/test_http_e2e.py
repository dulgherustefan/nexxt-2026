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
    subprocess.run([sys.executable, "-m", "versoml.ml.train"], cwd=ROOT, env=env, capture_output=True, timeout=600)
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
