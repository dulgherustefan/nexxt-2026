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

async def run(sid, action="approve", case_id=None):
    s = get_service()
    await s.graph()
    if case_id is None:
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
            "body": letter.get("body"), "metadata": letter.get("metadata"), "cmp": letter.get("cmp_checks"),
            "numeric": letter.get("numeric_check"), "prompts": prompts,
            "summaries": [n.get("summary") for n in d["pipeline"]["nodes"] if n.get("summary")],
            "fact_summaries": [f["summary"] for f in d["facts"]],
            "messages": [e.message for e in s.rt.bus.history(case_id)],
            "nodes": {n["id"]: n.get("status") for n in d["pipeline"]["nodes"]},
            "rejected_by": d["summary"].get("rejected_by"), "finished": bool((s.rt.cases.get(case_id) or {}).get("finished_at")),
            "standard": d.get("standard"),
            "interrupts": [e.data for e in s.rt.bus.history(case_id) if e.name == "interrupt"],
            "tasks": d.get("tasks"), "refund": d.get("refund"), "summary": d["summary"],
            "hits": [[h["rule_id"], h["outcome"]] for h in (d.get("rules") or {}).get("hits", [])],
            "rule_ids": {x["question"]: x["rule_ids"] for x in d["decisions"]},
            "context": {k: (d.get("rule_context") or {}).get(k) for k in ("executed_at", "loss_reported_at", "llm_mode")},
            "signatures": [f["content"] for f in d["facts"] if f["kind"] == "human.signature"],
            "verify": s.rt.ledger.verify(case_id).get("valid")}

async def main():
    out = {}
    for sid in ["demo_t1", "card_visa_secure", "reclamatie_tardiva", "frauda_client"]:
        out[sid] = await run(sid)
    out["declined"] = await run("frauda_client", "reject")
    out["app"] = await run("vishing_securitate")
    out["app_not_confirmed"] = await run("cont_sigur", "reject")
    # the customer of demo_t1 told the bank already; a debit after that moment is disputed in a new case
    s = get_service()
    tx = s.demo_scam("CUST-DEMO-01")
    case_id = await s.bank_dispute("CUST-DEMO-01", tx["transaction_id"], "I did not make this one either.")
    out["after_notice"] = await run(None, case_id=case_id)
    # a customer who writes in Romanian gets the letter in Romanian
    tx = s.demo_scam("CUST-DEMO-01")
    case_id = await s.bank_dispute("CUST-DEMO-01", tx["transaction_id"],
                                   "Bună ziua, nu am făcut eu această plată de 3.200 lei. Am primit un SMS de la curier "
                                   "cu un link https://livrare-bancademo.example/colet și l-am deschis. Vă rog să-mi "
                                   "returnați banii și să-mi spuneți de ce nu ați blocat tranzacția.")
    out["romanian"] = await run(None, case_id=case_id)
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


def test_every_case_gets_a_standard_record(results):
    r = results["demo_t1"]["standard"]
    assert r["schema_version"] == "versoml.case.v1" and r["case_id"].startswith("CT-")
    assert r["payment_type"] in ("credit_transfer", "instant_credit_transfer")
    assert r["fraud_type"] == "payment_order_issued_by_fraudster" and r["amount"]["currency"] == "RON"
    assert r["websites"] == ["livrare-bancademo.example"]
    # a late claim is still classified, and the record says how many days passed
    assert results["reclamatie_tardiva"]["standard"]["days_to_report"] > 395


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


def test_the_letter_explains_the_decision_and_carries_the_review_flags(results):
    r = results["demo_t1"]
    body = r["body"]
    # the decision comes first, then the law, the data used and the main factors, and the customer's rights
    opening = body.split("\n\n")[1]
    assert opening.startswith("We have refunded the full amount of RON 3,200.00")
    assert "To decide, we looked at your complaint, the record of the payment" in body
    assert "The main factors were" in body and "a copy of the information and documents" in body
    assert "A member of our disputes team reviewed and approved this decision." in body
    assert not re.search(r"\b(?:PAY|DSP|CMP|REC|URM|DP)-\d{2}\b", body)            # rule IDs stay in the metadata
    meta = r["metadata"]
    assert meta["ai_assisted"] is True and meta["human_approved"] is True and meta["approved_by"] == "OPERATOR-TEST"
    assert meta["language"] == "en" and "PAY-03" in meta["rule_ids"]
    assert {c["rule_id"]: c["outcome"] for c in r["cmp"]} == {"CMP-01": "toate_punctele", "CMP-03": "bloc_prezent"}


def test_a_romanian_complaint_gets_a_romanian_letter(results):
    r = results["romanian"]
    body = r["body"]
    assert r["letter"] == "draft", (body, r["numeric"])
    assert r["metadata"]["language"] == "ro" and r["metadata"]["ai_assisted"] is True
    assert r["subject"].startswith("Rambursarea transferului de 3.200,00 lei")
    assert body.startswith("Bună ziua, ") and body.rstrip().endswith("Echipa de contestații, Demo Bank")
    assert "V-am rambursat integral suma de 3.200,00 lei" in body
    assert "art. 173 din Legea nr. 209/2019" in body and "sfârșitul următoarei zile lucrătoare" in body
    assert "Ne-ați întrebat de ce nu am oprit plata." in body
    assert all(k in body for k in ("ANPC", "ANAF", "BNR", "CSALB"))
    # Romanian formats and diacritics with a comma below; none of the English letter's wording
    assert "\u015f" not in body and "\u0163" not in body and "ș" in body and "ț" in body
    assert not re.search(r"\bRON\s?\d|\b\d{1,3}(?:,\d{3})+\.\d{2}\b|\b(?:Dear|Kind regards|refund)\b", body)
    # the customer's words and their link are not quoted back
    assert "livrare-bancademo" not in body and "Vă rog să-mi returnați" not in body
    assert r["numeric"]["passed"] and r["numeric"]["checked"] >= 4
    assert {c["rule_id"]: c["outcome"] for c in r["cmp"]} == {"CMP-01": "toate_punctele", "CMP-03": "bloc_prezent"}


def test_sign_off_prompt_names_the_real_reason(results):
    r = results["frauda_client"]
    assert r["decisions"]["rambursare_t1"] == "RAMBURSEAZA_CU_APROBARE"
    [prompt] = r["prompts"]
    assert re.fullmatch(r"Refund RON 2,890\.00 by \d{1,2} [A-Z][a-z]{2}, 23:59\? Sign-off is needed because .+\.", prompt), prompt
    assert "the customer has risk signals" in prompt and "over the cap" not in prompt


@pytest.mark.parametrize("sid", ["demo_t1", "card_visa_secure", "reclamatie_tardiva", "frauda_client", "app",
                                 "app_not_confirmed", "after_notice", "romanian"])
def test_what_a_person_reads_is_english(results, sid):
    r = results[sid]
    texts = r["summaries"] + r["fact_summaries"] + r["messages"] + r["prompts"]
    romanian = [t for t in texts if t and ROMANIAN.search(re.sub(r"https?://\S+|\b[\w.-]+\.(?:example|test)\b", "", t))]
    assert romanian == [], romanian[:5]


def test_an_app_route_waits_for_a_signature_with_a_reason(results):
    r = results["app"]
    assert r["decisions"]["rambursare_t1"] == "NU_SE_APLICA_T1" and r["status"] == "TRASEU_APP"
    [prompt] = r["prompts"]
    assert "does not apply" in prompt and "refunded by" in prompt
    assert r["interrupts"][0]["deadline"]                          # the refund clock travels with the question
    [signature] = r["signatures"]
    assert signature["reason_code"] == "FACTS_CONFIRMED" and signature["reason_text"] and signature["note"] == "test"


def test_a_route_a_person_does_not_confirm_is_refunded_on_their_signature(results):
    r = results["app_not_confirmed"]
    assert r["status"] == "RAMBURSAT" and r["decisions"]["rambursare_t1"] == "RAMBURSEAZA_CU_APROBARE"
    assert r["signatures"][0]["reason_code"] == "FACTS_DISPUTED"
    assert "We have refunded the full amount" in r["body"]          # the letter follows the signed decision


def test_the_refund_goes_to_the_account_debited_and_records_the_customers_share(results):
    r = results["demo_t1"]
    refund = r["refund"]
    assert refund["amount"] == refund["debited"] == 3200.0 and refund["currency"] == "RON"
    assert refund["to_account"].startswith("RO") and "•" in refund["to_account"]
    assert refund["retained"] is False and refund["payer_liability"] == 150.0      # EUR 30 at the [U] rate, waived


def test_a_reading_without_a_live_model_is_flagged_and_signed(results):
    r = results["demo_t1"]
    assert r["context"]["llm_mode"] == "offline" and r["summary"]["llm_degraded"] is True
    assert ["DSP-57", "extragere_de_confirmat"] in r["hits"]
    assert r["decisions"]["rambursare_t1"] == "RAMBURSEAZA_CU_APROBARE" and r["prompts"]
    assert "read without a live model" in r["prompts"][0]


def test_reporting_an_unauthorized_payment_opens_a_block_task_and_a_decline_a_reply_task(results):
    [block] = [t for t in results["demo_t1"]["tasks"] if t["kind"] == "block_instrument"]
    assert block["due_at"] and block["status"] == "open" and "177" in block["basis"]
    reply = next(t for t in results["declined"]["tasks"] if t["kind"] == "written_answer")
    assert reply["due_at"] and "224" in reply["basis"]


def test_a_debit_after_the_customers_report_is_the_banks_loss(results):
    r = results["after_notice"]
    assert r["context"]["loss_reported_at"] < r["context"]["executed_at"]
    assert ["PAY-04", "raspundere_0"] in r["hits"] and ["DSP-58", "ancora_constatare"] in r["hits"]
    assert "PAY-04" in r["rule_ids"]["recuperare_client"] and r["decisions"]["recuperare_client"] == "NU_RECOMANDAM_RECUPERARE"
    assert r["status"] == "RAMBURSAT" and r["refund"]["payer_liability"] == 0.0
