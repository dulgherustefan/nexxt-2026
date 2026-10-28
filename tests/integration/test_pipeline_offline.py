"""Graful real al Judecătorului, cap-coadă, fără rețea (LLM offline, OSINT pe înregistrări).

Rulează pe un director var/ temporar, într-un subproces, ca să nu atingă datele demo-ului.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = r"""
import asyncio, json, os
from versoml.data.seed import seed_all
from versoml.config import get_settings
seed_all(settings=get_settings())
from versoml.zone_client.service import get_service

async def run(sid):
    s = get_service()
    await s.graph()
    case_id = s.create_case(sid)
    await s.run_case(case_id)
    for _ in range(400):
        await asyncio.sleep(0.25)
        doc = s.rt.cases.get(case_id) or {}
        if (doc.get("interrupt") or {}).get("pending"):
            await s.approve(case_id, "approve", "test", "OPERATOR-TEST")
        if doc.get("finished_at") or doc.get("status") == "EROARE":
            break
    d = s.detail(case_id)
    return {"status": d["summary"]["status"], "decisions": {x["question"]: x["decision"] for x in d["decisions"]},
            "facts": len(d["facts"]), "letter": (d.get("letter") or {}).get("status"),
            "nodes": {n["id"]: n.get("status") for n in d["pipeline"]["nodes"]},
            "verify": s.rt.ledger.verify(case_id).get("valid")}

async def main():
    out = {}
    for sid in ["demo_t1", "card_visa_secure", "reclamatie_tardiva"]:
        out[sid] = await run(sid)
    print("RESULT" + json.dumps(out), flush=True)
    await get_service().close()

asyncio.run(main())
os._exit(0)
"""


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    var = tmp_path_factory.mktemp("var")
    env = dict(os.environ, VERSOML_VAR_DIR=str(var), VERSOML_LLM_MODE="offline", VERSOML_OSINT_MODE="fixture", PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               VERSOML_AML_PORT="8991")
    proc = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT")), None)
    assert line, proc.stderr[-3000:]
    return json.loads(line[len("RESULT"):])


def test_demo_t1_refunds_at_t1(results):
    r = results["demo_t1"]
    assert r["decisions"]["rambursare_t1"] in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")
    assert r["status"] == "RAMBURSAT"
    assert r["letter"] in ("draft", "blocked")
    assert r["verify"] is True
    assert r["facts"] >= 10


def test_all_pipeline_steps_ran(results):
    nodes = results["demo_t1"]["nodes"]
    for step in ("receptor", "clasificator", "ceasornicar", "colector_tranzactie", "colector_sca",
                 "colector_dispozitiv", "motor_reguli", "rambursare", "redactor", "filtru_zid", "sigiliu"):
        assert nodes.get(step) in ("done", "skipped"), (step, nodes.get(step))


def test_visa_secure_refund_despite_strong_auth(results):
    assert results["card_visa_secure"]["decisions"]["rambursare_t1"] in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")


def test_late_claim_rejected_with_human(results):
    r = results["reclamatie_tardiva"]
    assert r["decisions"]["rambursare_t1"] == "RESPINGE_TARDIV"
