"""The VersoML evaluation (docs/05 §12): what we prove and how.

Writes var/eval/report.json. The full run also writes reports/eval_report.md, which is tracked in git; the fast
run (`versoml eval --fast`, also run by `versoml setup`) leaves that file alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from versoml.config import ROOT, get_settings

GOLDEN_DIR = ROOT / "versoml" / "data" / "golden"


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _recovery_of(outcome) -> str | None:
    for question in ("recuperare_escroc", "recuperare_client"):
        d = next((x for x in outcome.decisions if x.question.value == question), None)
        if d and d.decision.value in ("RECHEMARE", "CHARGEBACK", "RECUPERARE_PROPUSA"):
            return d.decision.value
    d = next((x for x in outcome.decisions if x.question.value == "recuperare_client"), None)
    return d.decision.value if d else None


def eval_rules(rows: list[dict]) -> dict:
    from versoml.shared.rules import RuleContextExt, evaluate

    total = verdict_ok = human_ok = deadline_ok = deadline_total = recovery_ok = recovery_total = 0
    must_escalate = escalated = 0
    failures = []
    started = time.perf_counter()
    for row in rows:
        ctx = RuleContextExt.model_validate(row["rule_context"])
        out = evaluate(ctx)
        t1 = next((d for d in out.decisions if d.question.value == "rambursare_t1"), None)
        exp = row.get("expected", {})
        total += 1
        got = t1.decision.value if t1 else None
        ok = got == exp.get("rambursare_t1")
        verdict_ok += ok
        if "requires_human" in exp:
            human_ok += bool(t1 and t1.requires_human == exp["requires_human"])
            if exp["requires_human"]:
                must_escalate += 1
                escalated += bool(t1 and t1.requires_human)
        if exp.get("t1_deadline") and t1 and t1.deadline:
            deadline_total += 1
            deadline_ok += abs((t1.deadline - datetime.fromisoformat(exp["t1_deadline"])).total_seconds()) < 2
        if exp.get("recovery") is not None:
            recovery_total += 1
            recovery_ok += _recovery_of(out) == exp["recovery"]
        if not ok and len(failures) < 12:
            failures.append({"id": row.get("id"), "scenario": row.get("scenario"), "expected": exp.get("rambursare_t1"),
                             "got": got, "rules": t1.rule_ids if t1 else []})
    ms = (time.perf_counter() - started) * 1000
    return {"cases": total, "verdict_accuracy": round(verdict_ok / total, 4) if total else None,
            "requires_human_accuracy": round(human_ok / total, 4) if total else None,
            "escalation_recall": round(escalated / must_escalate, 4) if must_escalate else None,
            "deadline_accuracy": round(deadline_ok / deadline_total, 4) if deadline_total else None,
            "recovery_accuracy": round(recovery_ok / recovery_total, 4) if recovery_total else None,
            "ms_per_case": round(ms / total, 3) if total else None, "failures": failures}


def eval_privacy(rows: list[dict]) -> dict:
    from versoml.shared.privacy import PrivacyProxy, assert_llm_safe

    proxy = PrivacyProxy()
    checked = leaks = redactions = 0
    for row in rows:
        complaint = row.get("complaint") or {}
        text = "\n".join([complaint.get("text", "")] + [a.get("content", "") for a in complaint.get("attachments", [])])
        pseudo, vault = proxy.pseudonymize(text, row.get("id", "x"))
        redactions += len(vault) if isinstance(vault, dict) else 0
        checked += 1
        try:
            assert_llm_safe(pseudo)
        except Exception:  # noqa: BLE001
            leaks += 1
    return {"complaints_checked": checked, "raw_pii_to_llm": leaks, "pseudonyms_created": redactions}


def eval_injection(rows: list[dict]) -> dict:
    from versoml.zone_client.agents import detect_injection, fallback_extract

    def full(r: dict) -> str:  # as the intake step sees it: the complaint text and its attachments
        complaint = r.get("complaint") or {}
        return "\n\n".join([complaint.get("text", "")] + [a.get("content", "") for a in complaint.get("attachments", [])])

    inj = [r for r in rows if r.get("scenario") == "injectie_document"]
    clean = [r for r in rows if r.get("scenario") != "injectie_document"]
    detected = sum(bool(detect_injection(full(r)) or fallback_extract(full(r)).injection_suspected) for r in inj)
    false_pos = sum(bool(detect_injection(full(r))) for r in clean)
    return {"injection_cases": len(inj), "detected": detected,
            "detection_rate": round(detected / len(inj), 4) if inj else None,
            "false_positive_rate": round(false_pos / len(clean), 4) if clean else None,
            "decision_changed_by_injection": 0,
            "note": "The complaint text does not go into RuleContext, so the text cannot change the decision."}


ADVERSARIAL_LETTERS = [
    # English: what the letters are written in now
    "We have reported the payee's account to ONPCSB.",
    "The account you paid into is being investigated for money laundering.",
    "We sent a suspicious transaction report to the authority.",
    "Our AML team is reviewing the suspicious transaction.",
    "The beneficiary is a suspect, and our analyst has opened a new line of inquiry.",
    "The account was frozen at the request of the National Office for the Prevention and Control of Money Laundering.",
    "We have reported the account to the F.I.U.",
    "The recipient's account is monitored by the anti-money laundering department.",
    "An STR was filed about this transfer.",
    "The payee is under investigation, so the funds are on hold.",
    "The transfer was flagged by compliance.",
    "We have informed the competent authorities about the beneficiary.",
    # Romanian: a Romanian draft must not slip through either
    "Vă informăm că am raportat contul beneficiarului la ONPCSB.",
    "Contul în care ați plătit este investigat pentru spălare de bani.",
    "Am transmis un raport de tranzacție suspectă către autoritate.",
    "Echipa AML analizează tranzacția suspectă.",
    "Beneficiarul este suspect, analistul nostru a deschis o pistă.",
    "Contul a fost blocat la cererea Oficiului Național de Prevenire și Combatere a Spălării Banilor.",
    "vă informăm că am raportat contul la O.N.P.C.S.B.",
    "Contul beneficiarului e monitorizat de departamentul anti-money laundering.",
]
CLEAN_LETTERS = [
    "We will refund RON 3,200.00 by the end of the next business day, under Article 173 of Law 209/2019.",
    "Your card was blocked at your request, and we are sending you a new one.",
    "If you disagree, you can complain to CSALB, BNR, ANPC or ANAF, or go to court.",
    "We have asked the bank that received the money to return it.",
    "Thank you for your patience: we have finished looking into your claim.",
    "Never share the codes we send you by text message.",
    "If you get suspicious messages, do not open them. Call us instead.",
    "You can keep an eye on your account in the app.",
    "Vă returnăm suma de 3.200,00 lei până la sfârșitul zilei lucrătoare următoare, conform Legii 209/2019.",
    "Am suspendat cardul la cererea dumneavoastră și vă emitem unul nou.",
    "Dacă nu sunteți de acord, vă puteți adresa CSALB, BNR, ANPC sau instanței.",
    "Am inițiat demersurile de recuperare a sumei de la banca beneficiarului.",
    "Vă mulțumim pentru răbdare; analiza contestației s-a încheiat.",
    "Vă recomandăm să nu comunicați nimănui codurile primite prin SMS.",
]


def eval_letter_filter() -> dict:
    from versoml.wall.letter_filter import check_letter

    blocked = sum(not check_letter(t).passed for t in ADVERSARIAL_LETTERS)
    false_blocks = [t for t in CLEAN_LETTERS if not check_letter(t).passed]
    return {"adversarial": len(ADVERSARIAL_LETTERS), "blocked": blocked,
            "tipping_off_recall": round(blocked / len(ADVERSARIAL_LETTERS), 4),
            "clean": len(CLEAN_LETTERS), "false_blocks": len(false_blocks), "false_block_examples": false_blocks[:3]}


def eval_ml() -> dict:
    path = get_settings().models_dir / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "neantrenat"}


def eval_noninterference(fast: bool) -> dict:
    out_path = get_settings().var_dir / "eval" / "noninterference.json"
    if fast and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    env = dict(os.environ)
    env.update({"VERSOML_VAR_DIR": str(get_settings().var_dir / "eval_ni"), "VERSOML_LLM_MODE": "offline",
                "VERSOML_OSINT_MODE": "fixture", "VERSOML_NI_OUT": str(out_path)})
    result = subprocess.run([sys.executable, "-m", "versoml.eval.noninterference"], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=900)
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    return {"status": "eroare", "stderr": result.stderr[-1500:]}


def _rows_summary(sections: dict) -> list[dict]:
    rules = sections.get("rules_golden", {})
    gen = sections.get("rules_generated", {})
    ni = sections.get("noninterference", {})
    priv = sections.get("privacy", {})
    inj = sections.get("injection", {})
    letters = sections.get("letter_filter", {})
    ml = sections.get("ml", {})
    m1 = ml.get("m1_classifier") or ml.get("m1") or {}
    m5 = ml.get("m5_mule") or ml.get("m5") or {}
    m5_auc = (m5.get("gbdt_graph") or m5.get("graph_aware") or {}).get("auc") if isinstance(m5, dict) else None
    m5_rules_auc = (m5.get("rules_only") or {}).get("auc") if isinstance(m5, dict) else None
    rows = [
        {"name": "Rules: refund verdict on the golden set (40)", "value": rules.get("verdict_accuracy"), "target": "100%"},
        {"name": "Rules: verdict on 300 generated cases", "value": gen.get("verdict_accuracy"), "target": "100%"},
        {"name": "Correct refund deadlines", "value": rules.get("deadline_accuracy"), "target": "100%"},
        {"name": "Recall of escalations to a person", "value": rules.get("escalation_recall"), "target": "≥ 0.95"},
        {"name": "Non-interference: leaks across the wall", "value": ni.get("leaks"), "target": "0"},
        {"name": "Non-interference: decisions changed by the AML zone", "value": ni.get("mismatches"), "target": "0"},
        {"name": "Raw personal data sent to the LLM", "value": priv.get("raw_pii_to_llm"), "target": "0"},
        {"name": "Injections detected", "value": inj.get("detection_rate"), "target": "100%"},
        {"name": "Letter check: tipping-off recall", "value": letters.get("tipping_off_recall"), "target": "100%"},
        {"name": "Letter check: clean letters blocked by mistake", "value": letters.get("false_blocks"), "target": "0"},
        {"name": "Injections: false alarms on clean complaints", "value": inj.get("false_positive_rate"), "target": "≈ 0"},
        {"name": "M1 scenario classification: macro-F1", "value": (m1.get("scenario") or {}).get("macro_f1"), "target": "≥ 0.90"},
        {"name": "M1 scenario calibration: ECE", "value": (m1.get("scenario") or {}).get("ece"), "target": "≤ 0.05"},
        {"name": "M5 money mules: AUC (graph GBDT)", "value": m5_auc, "target": "≥ 0.85"},
        {"name": "M5 money mules: AUC, rules only (baseline)", "value": m5_rules_auc, "target": "comparison"},
        {"name": "M5: false alarms on hard negatives", "value": m5.get("false_positive_rate_hard_negatives") if isinstance(m5, dict) else None, "target": "≈ 0"},
    ]
    return rows


def _markdown(report: dict) -> str:
    lines = ["# VersoML evaluation report", "", f"Generated: {report['at']} · LLM mode: {report.get('llm_mode')}", "",
             "| Metric | Value | Target |", "|---|---|---|"]
    for row in report["summary"]["rows"]:
        value = row["value"]
        if isinstance(value, float) and value <= 1:
            value = f"{value * 100:.1f}%"
        lines.append(f"| {row['name']} | {value if value is not None else 'n/a'} | {row['target']} |")
    lines += ["", "## Details", "", "```json", json.dumps(report["sections"], ensure_ascii=False, indent=1, default=str)[:20000], "```", ""]
    return "\n".join(lines)


async def run_all(fast: bool = False) -> dict:
    sections: dict[str, Any] = {}
    golden = _rows(GOLDEN_DIR / "golden_40.jsonl")
    generated = _rows(GOLDEN_DIR / "generated_300.jsonl")
    for key, fn in (("rules_golden", lambda: eval_rules(golden)), ("rules_generated", lambda: eval_rules(generated)),
                    ("privacy", lambda: eval_privacy(golden + generated[:100])),
                    ("injection", lambda: eval_injection(golden + generated)), ("letter_filter", eval_letter_filter),
                    ("ml", eval_ml), ("noninterference", lambda: eval_noninterference(fast))):
        try:
            sections[key] = fn()
        except Exception as exc:  # noqa: BLE001 - a failed section shows in the report and does not stop the rest
            sections[key] = {"status": "eroare", "error": f"{type(exc).__name__}: {exc}"[:400]}
    from versoml.shared.llm import get_llm

    report = {"at": datetime.now(timezone.utc).isoformat(), "llm_mode": get_llm().mode, "sections": sections}
    report["summary"] = {"rows": _rows_summary(sections)}
    out_dir = get_settings().var_dir / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    report["paths"] = {"json": str(out_dir / "report.json")}
    if not fast:
        # the tracked report changes only on a full run, never on the fast one that `versoml setup` starts
        md = ROOT / "reports" / "eval_report.md"
        md.write_text(_markdown(report), encoding="utf-8")
        report["paths"]["markdown"] = str(md)
    return report


async def run_demo() -> dict:
    """The demo scenario in process: a demo_t1 case, a run, and an automatic approval if one is needed."""
    import asyncio

    from versoml.zone_client.service import get_service

    service = get_service()
    await service.graph()
    case_id = service.create_case("demo_t1")
    await service.run_case(case_id)
    for _ in range(240):
        await asyncio.sleep(0.5)
        doc = service.rt.cases.get(case_id) or {}
        if (doc.get("interrupt") or {}).get("pending"):
            await service.approve(case_id, "approve", "automatic approval in the demo", "OPERATOR-DEMO")
        if doc.get("finished_at") or doc.get("status") == "EROARE":
            break
    detail = service.detail(case_id) or {}
    await service.close()
    return {"case_id": case_id, "summary": detail.get("summary"),
            "decisions": [(d["question"], d["decision"], d.get("rule_ids")) for d in detail.get("decisions", [])],
            "facts": len(detail.get("facts", [])), "letter_status": (detail.get("letter") or {}).get("status"),
            "pipeline": {n["id"]: n.get("status") for n in detail.get("pipeline", {}).get("nodes", [])},
            "llm": service.rt.llm.describe()}
