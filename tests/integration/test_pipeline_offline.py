"""The dispute judge's real graph, end to end, without network (LLM offline, OSINT from recordings).

It runs on a temporary var/ directory, in a subprocess, so it never touches the demo data.
"""

from __future__ import annotations

import json
import os
import re
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

async def run(sid, action="approve"):
    s = get_service()
    await s.graph()
    case_id = s.create_case(sid)
    await s.run_case(case_id)
    prompts = []
    for _ in range(400):
        await asyncio.sleep(0.25)
        doc = s.rt.cases.get(case_id) or {}
        if (doc.get("interrupt") or {}).get("pending"):
            prompts.append(doc["interrupt"].get("prompt"))
            await s.approve(case_id, action, "test", "OPERATOR-TEST")
        if doc.get("finished_at") or doc.get("status") == "EROARE":
            break
    d = s.detail(case_id)
    letter = d.get("letter") or {}
    return {"status": d["summary"]["status"], "decisions": {x["question"]: x["decision"] for x in d["decisions"]},
            "facts": len(d["facts"]), "letter": letter.get("status"), "subject": letter.get("subject"),
            "body": letter.get("body"), "prompts": prompts,
            "summaries": [n.get("summary") for n in d["pipeline"]["nodes"] if n.get("summary")],
            "fact_summaries": [f["summary"] for f in d["facts"]],
            "messages": [e.message for e in s.rt.bus.history(case_id)],
            "nodes": {n["id"]: n.get("status") for n in d["pipeline"]["nodes"]},
            "rejected_by": d["summary"].get("rejected_by"), "finished": bool((s.rt.cases.get(case_id) or {}).get("finished_at")),
            "verify": s.rt.ledger.verify(case_id).get("valid")}

async def main():
    out = {}
    for sid in ["demo_t1", "card_visa_secure", "reclamatie_tardiva", "frauda_client"]:
        out[sid] = await run(sid)
    out["declined"] = await run("frauda_client", "reject")
    print("RESULT" + json.dumps(out), flush=True)
    await get_service().close()

asyncio.run(main())
os._exit(0)
"""

ROMANIAN = re.compile(r"[ăâîșțĂÂÎȘȚ\u015f\u0163]|\b(?:si|pentru|contestati\w*|rambursat\w*|reguli|cazul|plata|zidul|dosar\w*)\b")


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


def test_declined_refund_ends_and_hands_the_case_to_a_person(results):
    r = results["declined"]
    assert r["decisions"]["rambursare_t1"] == "RAMBURSEAZA_CU_APROBARE" and r["prompts"]
    # the run ends in its own state instead of "in progress" forever
    assert r["finished"] and r["status"] == "REFUZAT"
    assert r["rejected_by"] == "OPERATOR-TEST"
    # no letter promising a refund nobody approved: the person handling the case writes to the customer
    assert r["letter"] is None and r["nodes"]["redactor"] == "skipped"
    assert r["verify"] is True


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
    assert r["prompts"] and "13 months" in r["prompts"][0]


def test_the_letter_is_english_and_specific(results):
    r = results["demo_t1"]
    assert r["letter"] == "draft", r["body"]
    assert r["subject"].startswith("Refund of RON 3,200.00 for a transfer")
    assert r["body"].startswith("Dear ") and "RON 3,200.00" in r["body"]
    assert "Article 173 of Law 209/2019" in r["body"] and "end of the next business day" in r["body"]
    assert all(k in r["body"] for k in ("ANPC", "ANAF", "BNR", "CSALB"))
    assert "T+1" not in r["body"] and "—" not in r["body"] and not re.search(r"\b\d{1,3}(?:\.\d{3})+,\d{2}\b", r["body"])
    late = results["reclamatie_tardiva"]["body"]
    assert "Article 169 of Law 209/2019" in late and "cannot refund" in late


def test_sign_off_prompt_names_the_real_reason(results):
    r = results["frauda_client"]
    assert r["decisions"]["rambursare_t1"] == "RAMBURSEAZA_CU_APROBARE"
    [prompt] = r["prompts"]
    assert re.fullmatch(r"Refund RON 2,890\.00 by \d{1,2} [A-Z][a-z]{2}, 23:59\? Sign-off is needed because .+\.", prompt), prompt
    assert "the customer has risk signals" in prompt and "over the cap" not in prompt


@pytest.mark.parametrize("sid", ["demo_t1", "card_visa_secure", "reclamatie_tardiva", "frauda_client"])
def test_what_a_person_reads_is_english(results, sid):
    r = results[sid]
    texts = r["summaries"] + r["fact_summaries"] + r["messages"] + r["prompts"]
    romanian = [t for t in texts if t and ROMANIAN.search(re.sub(r"https?://\S+|\b[\w.-]+\.(?:example|test)\b", "", t))]
    assert romanian == [], romanian[:5]
