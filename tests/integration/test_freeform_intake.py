"""Free-form intake end to end, offline, on a freshly seeded world in a subprocess (it never touches the demo data):
the matcher on the golden set freeform_60, a person picking the payment at the `pick_transaction` interrupt, the
declared-facts path when nothing matches, the router's plan, and the numeric check rewriting an adversarial letter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "versoml" / "data" / "golden" / "freeform_60.jsonl"

SCRIPT = r"""
import asyncio, json, os, sys
from versoml.data.seed import seed_all
from versoml.config import get_settings
seed_all(settings=get_settings())
from versoml.zone_client.matcher import eval_matcher
from versoml.zone_client.service import get_service
from versoml.zone_client import prompts as P

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
out = {"eval": eval_matcher(rows=rows)}

async def run(s, complaint, pick=None):
    case_id = s.create_case(complaint=complaint)
    await s.run_case(case_id)
    seen = []
    for _ in range(400):
        await asyncio.sleep(0.2)
        doc = s.rt.cases.get(case_id) or {}
        it = doc.get("interrupt") or {}
        if it.get("pending") and not it.get("resuming"):
            seen.append({"kind": it.get("kind"), "candidates": [c["tx_id"] for c in it.get("candidates") or []]})
            if it.get("kind") == "pick_transaction":
                wrong = await s.approve(case_id, "approve", None, "OPERATOR-TEST")
                seen[-1]["wrong_action"] = wrong
                await s.approve(case_id, "pick_transaction", "test", "OPERATOR-TEST", tx_id=pick(it))
            else:
                await s.approve(case_id, "approve", "test", "OPERATOR-TEST")
        if doc.get("finished_at") or doc.get("status") == "EROARE":
            break
    d = s.detail(case_id)
    facts = d["facts"]
    return {"status": d["summary"]["status"], "error": (s.rt.cases.get(case_id) or {}).get("error"),
            "decisions": {x["question"]: x["decision"] for x in d["decisions"]},
            "match": d.get("match"), "routing": d.get("routing"), "interrupts": seen,
            "reasons": d.get("reasons"), "numeric_check": d.get("numeric_check"),
            "letter": (d.get("letter") or {}).get("body"), "letter_status": (d.get("letter") or {}).get("status"),
            "fact_kinds": [f["kind"] for f in facts],
            "declared_trust": [f["labels"]["trust"] for f in facts if f["kind"] == "declared.statement"],
            "nodes": {n["id"]: n.get("status") for n in d["pipeline"]["nodes"]},
            "events": [e.name for e in s.rt.bus.history(case_id) if e.name],
            "routing_events": [e.data for e in s.rt.bus.history(case_id) if e.name == "routing"],
            "summary": d["summary"], "verify": s.rt.ledger.verify(case_id).get("valid")}

async def main():
    s = get_service()
    await s.graph()
    clear = next(r for r in rows if r["category"] == "clear" and r["customer_ref"])
    out["clear"] = await run(s, {"text": clear["text"], "customer_ref": clear["customer_ref"], "source": "email"})
    out["clear_expected"] = clear["expected"]
    amb = next(r for r in rows if r["category"] == "ambiguous")
    out["ambiguous"] = await run(s, {"text": amb["text"], "customer_ref": amb["customer_ref"]},
                                 pick=lambda it: it["candidates"][-1]["tx_id"])
    out["ambiguous_candidates"] = amb.get("candidates")
    unknown = next(r for r in rows if r["category"] == "unknown_customer")
    out["unknown"] = await run(s, {"text": unknown["text"], "source": "web_form"})
    # an adversarial first draft: the letter writer gets the amount wrong once
    original = s.rt.llm.structured
    calls = {"n": 0}
    async def adversarial(**kw):
        result, info = await original(**kw)
        if kw.get("schema") is P.LetterOut and calls["n"] == 0:
            calls["n"] += 1
            paragraphs = [p.model_copy(update={"text": p.text.replace("RON ", "RON 1")}) for p in result.paragraphs]
            result = result.model_copy(update={"paragraphs": paragraphs})
        return result, info
    s.rt.llm.structured = adversarial
    second = next(r for r in rows if r["category"] == "clear" and r["customer_ref"] and r is not clear)
    out["adversarial"] = await run(s, {"text": second["text"], "customer_ref": second["customer_ref"]})
    s.rt.llm.structured = original
    print("RESULT" + json.dumps(out, default=str), flush=True)
    await s.close()

asyncio.run(main())
sys.stdout.flush()
os._exit(0)
"""


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    if not GOLDEN.exists():
        pytest.skip("freeform_60.jsonl is not there yet")
    var = tmp_path_factory.mktemp("var_freeform")
    env = dict(os.environ, VERSOML_VAR_DIR=str(var), VERSOML_LLM_MODE="offline", VERSOML_OSINT_MODE="fixture",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1", VERSOML_AML_PORT="8992")
    proc = subprocess.run([sys.executable, "-c", SCRIPT, str(GOLDEN)], cwd=ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=900)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT")), None)
    assert line, proc.stderr[-3000:]
    return json.loads(line[len("RESULT"):])


def test_matcher_meets_the_targets_on_freeform_60(results):
    ev = results["eval"]
    assert ev["n"] == 60
    assert ev["clear"]["accuracy"] >= 0.95, ev["errors"]
    assert ev["needs_human"]["recall"] == 1.0, ev["errors"]
    assert ev["wrong_auto_matches"] == 0, ev["errors"]


def test_clear_free_form_case_runs_on_the_matched_payment(results):
    r = results["clear"]
    assert r["error"] is None and r["verify"] is True
    assert r["match"]["tx_id"] == results["clear_expected"]["tx_id"] and r["match"]["method"] == "matched"
    assert r["interrupts"] == [] or all(i["kind"] != "pick_transaction" for i in r["interrupts"])
    assert "intake.match" in r["fact_kinds"] and "routing.plan" in r["fact_kinds"]
    assert {"match", "routing"} <= set(r["events"])
    assert len(r["routing_events"]) == 5 and all({"node", "run", "reason"} <= set(e) for e in r["routing_events"])
    assert r["decisions"]["rambursare_t1"] != "INFORMATII_SUPLIMENTARE"
    assert r["reasons"] and all(x["sentence"].endswith(").") for x in r["reasons"])
    assert r["summary"]["scenario_phrase"]


def test_ambiguous_case_waits_for_a_person_and_resumes_on_the_pick(results):
    r = results["ambiguous"]
    [pick] = [i for i in r["interrupts"] if i["kind"] == "pick_transaction"]
    assert set(pick["candidates"]) >= set(results["ambiguous_candidates"])
    assert pick["wrong_action"]["ok"] is False                       # approve is not an answer to a payment pick
    assert r["match"]["method"] == "picked" and r["match"]["tx_id"] == pick["candidates"][-1]
    assert "human.pick_transaction" in r["fact_kinds"] and r["fact_kinds"].count("intake.match") == 1
    assert r["error"] is None and r["nodes"]["identificare"] == "done" and r["verify"] is True


def test_unknown_customer_goes_down_the_declared_facts_path(results):
    r = results["unknown"]
    assert r["error"] is None and r["match"]["customer_ref"] is None and r["match"]["tx_id"] is None
    assert r["decisions"]["rambursare_t1"] == "INFORMATII_SUPLIMENTARE"
    assert r["decisions"]["raspuns_reclamatie"] == "INFORMATII_SUPLIMENTARE"
    assert r["declared_trust"] == ["untrusted"]
    assert r["nodes"]["rambursare"] == "skipped" and r["nodes"]["outbox_aml"] == "skipped"
    assert r["nodes"]["colector_sca"] == "skipped" and r["status"] == "IN_ANALIZA"
    assert "refund.instruction" not in r["fact_kinds"] and "wall.diode_sent" not in r["fact_kinds"]
    assert "phone number or IBAN registered with us" in r["letter"] and r["letter_status"] == "draft"
    assert r["reasons"][0]["rule_id"] == "DSP-53"


def test_adversarial_letter_is_rewritten_with_the_values_on_file(results):
    r = results["adversarial"]
    check = r["numeric_check"]
    assert check["rewritten"] is True and check["passed"] is True, check
    assert r["letter_status"] == "draft" and "letter.numeric_check" in r["fact_kinds"]
    assert "numeric_check" in r["events"]
