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
    typ = sections.get("rules_typologies", {})
    ni = sections.get("noninterference", {})
    priv = sections.get("privacy", {})
    inj = sections.get("injection", {})
    letters = sections.get("letter_filter", {})
    ml = sections.get("ml", {})
    m1 = ml.get("m1_classifier") or ml.get("m1") or {}
    m2 = ml.get("m2_client_fraud") or {}
    m5 = ml.get("m5_mule") or ml.get("m5") or {}
    m5t = (m5.get("temporal_split") or {}) if isinstance(m5, dict) else {}
    m5_auc = (m5t.get("ensemble") or m5.get("gbdt_graph") or {}).get("auc") if isinstance(m5, dict) else None
    m5_rules_auc = (m5t.get("rules_only") or m5.get("rules_only") or {}).get("auc") if isinstance(m5, dict) else None
    honest = m1.get("honest") or {}
    free = ((honest.get("templates_to_llm_paraphrases") or {}).get("scenario") or {}).get("ensemble_served") or {}
    xling = ((honest.get("cross_lingual_en_to_ro") or {}).get("scenario") or {}).get("ensemble_served") or {}
    rows = [
        {"name": "Rules: refund verdict on the golden set (40)", "value": rules.get("verdict_accuracy"), "target": "100%"},
        {"name": "Rules: verdict on 300 generated cases", "value": gen.get("verdict_accuracy"), "target": "100%"},
        {"name": "Rules: verdict on the typology cases", "value": typ.get("verdict_accuracy"), "target": "100%"},
        {"name": "Correct refund deadlines", "value": rules.get("deadline_accuracy"), "target": "100%"},
        {"name": "Recall of escalations to a person", "value": rules.get("escalation_recall"), "target": "≥ 0.95"},
        {"name": "Non-interference: leaks across the wall", "value": ni.get("leaks"), "target": "0"},
        {"name": "Non-interference: decisions changed by the AML zone", "value": ni.get("mismatches"), "target": "0"},
        {"name": "Raw personal data sent to the LLM", "value": priv.get("raw_pii_to_llm"), "target": "0"},
        {"name": "Injections detected", "value": inj.get("detection_rate"), "target": "100%"},
        {"name": "Letter check: tipping-off recall", "value": letters.get("tipping_off_recall"), "target": "100%"},
        {"name": "Letter check: clean letters blocked by mistake", "value": letters.get("false_blocks"), "target": "0"},
        {"name": "Injections: false alarms on clean complaints", "value": inj.get("false_positive_rate"), "target": "≈ 0"},
        {"name": "M1 scenario on held-out templates: macro-F1", "value": (m1.get("scenario") or {}).get("macro_f1"), "target": "≥ 0.90"},
        {"name": "M1 scenario calibration on held-out templates: ECE", "value": (m1.get("scenario") or {}).get("ece"), "target": "≤ 0.05"},
        {"name": "M1 scenario, trained on templates, tested on free text", "value": free.get("accuracy"), "target": "comparison"},
        {"name": "M1 scenario, trained on English, tested on Romanian", "value": xling.get("accuracy"), "target": "comparison"},
        {"name": "M2 client-fraud signal: AUC, temporal split", "value": ((m2.get("temporal_split") or {}).get("ensemble") or {}).get("auc"), "target": "≥ 0.80"},
        {"name": "M5 money mules: AUC, temporal split (ensemble)", "value": m5_auc, "target": "≥ 0.85"},
        {"name": "M5 money mules: AUC, rules only (baseline)", "value": m5_rules_auc, "target": "comparison"},
        {"name": "M5: false alarms on hard negatives", "value": (m5t.get("false_positive_rate_hard_negatives") if m5t else
                                                            m5.get("false_positive_rate_hard_negatives") if isinstance(m5, dict) else None), "target": "≈ 0"},
    ]
    for key in sections:   # extension sections bring their own rows
        extra = sections[key].get("summary_rows") if isinstance(sections[key], dict) else None
        if isinstance(extra, list):
            rows += [r for r in extra if isinstance(r, dict) and {"name", "value", "target"} <= set(r)]
    return rows


# the metrics of the single models this release replaced (var/models/metrics.json of 28.10.2026, 18:46):
# random or same-template splits, so they measured template recall more than skill
OLD_ML = {"m1_scenario_accuracy": 0.9927, "m1_scenario_macro_f1": 0.9927, "m1_scenario_ece": 0.0397,
          "m1_split": "a second corpus from the same templates (seed + 1000)",
          "m2_auc": 0.9908, "m2_split": "random 75/25 split of the simulator",
          "m5_auc": 0.9914, "m5_split": "group CV on one 30-day window (patterns only in the last month)"}


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def ml_markdown(ml: dict) -> list[str]:
    """Tabelele de model: vechi față de nou, membru față de ansamblu, pe împărțiri cinstite."""
    if not isinstance(ml, dict) or "m1_classifier" not in ml:
        return []
    m1, m2, m5 = ml.get("m1_classifier") or {}, ml.get("m2_client_fraud") or {}, ml.get("m5_mule") or {}
    out = ["", "## Models: old vs new", "", "| Model | Old (split) | New, honest split | New, old-style split |", "|---|---|---|---|"]
    rs = ((m1.get("honest") or {}).get("random_split_leaky") or {}).get("scenario", {}).get("ensemble_served", {})
    out.append(f"| M1 scenario accuracy | {_fmt(OLD_ML['m1_scenario_accuracy'])} ({OLD_ML['m1_split']}) | "
               f"{_fmt((m1.get('scenario') or {}).get('accuracy'))} (held-out templates) | {_fmt(rs.get('accuracy'))} (random split) |")
    m2t = (m2.get("temporal_split") or {}).get("ensemble") or {}
    out.append(f"| M2 AUC | {_fmt(OLD_ML['m2_auc'])} ({OLD_ML['m2_split']}) | {_fmt(m2t.get('auc'))} (temporal, 5% label noise; "
               f"{_fmt(m2t.get('auc_clean_labels'))} on clean labels) | {_fmt((m2.get('random_split_old_style') or {}).get('ensemble'))} |")
    m5t = (m5.get("temporal_split") or {}).get("ensemble") or {}
    out.append(f"| M5 AUC | {_fmt(OLD_ML['m5_auc'])} ({OLD_ML['m5_split']}) | {_fmt(m5t.get('auc'))} (temporal, 7-day gap) | "
               f"{_fmt((m5.get('gbdt_graph') or {}).get('auc'))} (group CV, GBDT) |")
    honest = m1.get("honest") or {}
    if honest:
        cols = ["char", "word", "cnb", "emb", "ensemble_fallback", "ensemble_full", "ensemble_served"]
        out += ["", "### M1 scenario accuracy: members vs ensemble", "",
                "`emb` and `ensemble_full` are measured on the rows that have a cached embedding; `ensemble_served` is "
                "what `classify_complaint` returns (the embedding meta-learner only where a vector exists and where it "
                "beat the fallback out of fold).", "",
                "| Split | " + " | ".join(cols) + " | n |", "|---|" + "---|" * (len(cols) + 1)]
        for split, v in honest.items():
            sc = v.get("scenario") or {}
            if not sc:
                continue
            out.append(f"| {split} | " + " | ".join(_fmt((sc.get(c) or {}).get("accuracy")) for c in cols)
                       + f" | {(sc.get('ensemble_served') or sc.get('ensemble_fallback') or {}).get('n', '')} |")
        amb = (honest.get("hard_negatives") or {}).get("ambiguity")
        if amb:
            out.append(f"\nAmbiguity flag on hard negatives: vague or multi-issue complaints flagged "
                       f"{_fmt(amb.get('vague_or_multi_issue_flagged'))}, clear ones flagged {_fmt(amb.get('clear_hard_negatives_flagged'))}.")
    if m2.get("temporal_split"):
        t = m2["temporal_split"]
        out += ["", "### M2 client-fraud signal: members vs ensemble (temporal split)", "",
                "| Member | AUC | PR-AUC | Brier | AUC on clean labels |", "|---|---|---|---|---|"]
        for k in ("lgbm", "lr", "ensemble"):
            r = t.get(k) or {}
            out.append(f"| {k} | {_fmt(r.get('auc'))} | {_fmt(r.get('pr_auc'))} | {_fmt(r.get('brier'))} | {_fmt(r.get('auc_clean_labels'))} |")
        out.append(f"| iforest (stacked feature only) | {_fmt((t.get('iforest_alone') or {}).get('auc'))} | | | |")
    if m5.get("temporal_split"):
        t = m5["temporal_split"]
        out += ["", "### M5 money mules: baselines, members and ensemble (temporal split)", "",
                f"Train: 30-day windows ending {', '.join(a[:10] for a in t.get('train_snapshots_as_of', []))}; test: "
                f"{t.get('test_window', ['', ''])[0][:10]} to {t.get('test_window', ['', ''])[1][:10]} "
                f"({t.get('label_delay_days')}-day gap, {t.get('test_mules')} active mules among {t.get('n_test')} accounts).", "",
                "| Model | AUC | PR-AUC | F1 |", "|---|---|---|---|"]
        for k in ("rules_only", "gbdt_no_graph", "gbdt_graph", "ppr_alone", "iforest_alone", "ensemble"):
            r = t.get(k) or {}
            out.append(f"| {k} | {_fmt(r.get('auc'))} | {_fmt(r.get('pr_auc'))} | {_fmt(r.get('f1'))} |")
        th = m5.get("typology_holdout") or {}
        if th:
            out += ["", "Typology hold-out (trained without that typology, tested on its mules in the last window):", "",
                    "| Typology | Mules | Ensemble AUC | Ensemble recall | Rules-only AUC |", "|---|---|---|---|---|"]
            for k, r in sorted(th.items()):
                if r.get("positives"):
                    out.append(f"| {k} | {r['positives']} | {_fmt(r.get('ensemble_auc'))} | "
                               f"{_fmt(r.get('ensemble_recall_at_thr'))} | {_fmt(r.get('rules_only_auc'))} |")
    lat = ml.get("_latency_ms")
    if lat and "error" not in lat:
        out += ["", "Inference latency (median of repeated calls, warm): " +
                ", ".join(f"{k} {v} ms" for k, v in lat.items()) + "."]
    out += ["", "Notes: every number is on synthetic data. Methods follow docs/08_cercetare_rag_ml_agenti.md: stacking on "
            "out-of-fold predictions (Wolpert 1992; scikit-learn stacking docs), IsolationForest as a stacked feature "
            "(Liu, Ting, Zhou 2008), sigmoid / temperature calibration with few positives (Niculescu-Mizil and Caruana "
            "2005), group splits on unseen templates and temporal splits with a gap (ULB fraud-detection handbook, ch. 5), "
            "LLM paraphrases added on top of templates, never instead of them (Li et al. 2023; Gerstgrasser et al. 2024), "
            "AML typologies after AMLworld (Altman et al. 2023, data at github.com/IBM/AML-Data), PPR as guilt by "
            "association (Koutra et al. 2011)."]
    return out


def eval_ml_latency() -> dict:
    """Median inference time per call, warm, for the trained models (skipped when they are not trained)."""
    import statistics

    d = get_settings().models_dir
    out: dict[str, float] = {}
    if (d / "m1_classifier.pkl").exists():
        from versoml.ml.m1_classifier import classify_complaint

        text = "Got an SMS about a parcel, opened the link and then RON 3,200 left my account."
        classify_complaint(text, models_dir=d, allow_live=False)
        ts = []
        for _ in range(15):
            t = time.perf_counter()
            classify_complaint(text, models_dir=d, allow_live=False)
            ts.append((time.perf_counter() - t) * 1000)
        out["M1"] = round(statistics.median(ts), 1)
    if (d / "m2_client_fraud.txt").exists():
        from versoml.ml.m2_client_fraud import client_fraud_signal

        f = {"prior_disputes_12m": 1, "device_known": 1, "hours_purchase_to_dispute": 30, "channel_card": 1}
        client_fraud_signal(f, models_dir=d)
        ts = []
        for _ in range(15):
            t = time.perf_counter()
            client_fraud_signal(f, models_dir=d)
            ts.append((time.perf_counter() - t) * 1000)
        out["M2"] = round(statistics.median(ts), 1)
    if (d / "m5_mule.txt").exists() and get_settings().aml_db.exists():
        from versoml.data.aml_world import demo_mule
        from versoml.data.repos import AmlRepo
        from versoml.ml.m5_mule import score_accounts

        g = AmlRepo(get_settings().aml_db).neighborhood([demo_mule(7)["iban"]], hops=2, days=30)
        if g.get("nodes"):
            score_accounts(g, models_dir=d)
            ts = []
            for _ in range(7):
                t = time.perf_counter()
                score_accounts(g, models_dir=d)
                ts.append((time.perf_counter() - t) * 1000)
            out["M5 (demo neighbourhood)"] = round(statistics.median(ts), 1)
    return out


def eval_data() -> dict:
    """Sizes of the synthetic data that the models and the matcher use (read from the committed files)."""
    from versoml.data.corpus_llm import LLM_CORPUS

    ff = _rows(GOLDEN_DIR / "freeform_60.jsonl")
    llm = _rows(LLM_CORPUS)
    from collections import Counter

    return {"freeform_60": {"lines": len(ff), "by_category": dict(Counter(r.get("category") for r in ff)),
                            "by_language": dict(Counter(r.get("language") for r in ff))},
            "llm_corpus": {"rows": len(llm), "by_kind": dict(Counter(r.get("kind") for r in llm)),
                           "by_language": dict(Counter(r.get("language") for r in llm)),
                           "scrubbed_rows": sum(1 for r in llm if r.get("scrubbed"))}}


# Extension point: other modules add evaluation sections here (retrieval, the free-text matcher, ...).
# Each entry is (section key, "module:function"); the function takes `fast: bool` and returns a dict that may
# carry "summary_rows" ([{name, value, target}]) and "markdown" (a list of lines for the report). A module that
# is not there yet is skipped.
OPTIONAL_SECTIONS: list[tuple[str, str]] = [
    ("retrieval", "versoml.knowledge.evaluate:eval_section"),
    ("matcher", "versoml.zone_client.matcher:eval_section"),
]


def register_section(key: str, target: str) -> None:
    if (key, target) not in OPTIONAL_SECTIONS:
        OPTIONAL_SECTIONS.append((key, target))


def _optional_sections(fast: bool) -> dict[str, dict]:
    import importlib

    out: dict[str, dict] = {}
    for key, target in OPTIONAL_SECTIONS:
        mod_name, _, fn_name = target.partition(":")
        try:
            fn = getattr(importlib.import_module(mod_name), fn_name)
        except (ImportError, AttributeError):
            continue
        try:
            out[key] = fn(fast)
        except Exception as exc:  # noqa: BLE001 - a failed section shows in the report and does not stop the rest
            out[key] = {"status": "eroare", "error": f"{type(exc).__name__}: {exc}"[:400]}
    return out


def _markdown(report: dict) -> str:
    lines = ["# VersoML evaluation report", "", f"Generated: {report['at']} · LLM mode: {report.get('llm_mode')}", "",
             "| Metric | Value | Target |", "|---|---|---|"]
    for row in report["summary"]["rows"]:
        value = row["value"]
        if isinstance(value, float) and value <= 1:
            value = f"{value * 100:.1f}%"
        lines.append(f"| {row['name']} | {value if value is not None else 'n/a'} | {row['target']} |")
    lines += ml_markdown(report["sections"].get("ml") or {})
    for key, sec in report["sections"].items():
        if isinstance(sec, dict) and isinstance(sec.get("markdown"), list):
            lines += [""] + [str(x) for x in sec["markdown"]]
    lines += ["", "## Details", "", "```json", json.dumps(report["sections"], ensure_ascii=False, indent=1, default=str)[:30000], "```", ""]
    return "\n".join(lines)


async def run_all(fast: bool = False) -> dict:
    sections: dict[str, Any] = {}
    golden = _rows(GOLDEN_DIR / "golden_40.jsonl")
    generated = _rows(GOLDEN_DIR / "generated_300.jsonl")
    typology = _rows(GOLDEN_DIR / "typology_cases.jsonl")

    def ml() -> dict:
        m = eval_ml()
        if isinstance(m, dict) and "m1_classifier" in m:
            try:
                m["_latency_ms"] = eval_ml_latency()
            except Exception as exc:  # noqa: BLE001 - the latency is extra information, not a reason to lose the metrics
                m["_latency_ms"] = {"error": f"{type(exc).__name__}"}
        return m

    for key, fn in (("rules_golden", lambda: eval_rules(golden)), ("rules_generated", lambda: eval_rules(generated)),
                    ("rules_typologies", lambda: eval_rules(typology)),
                    ("privacy", lambda: eval_privacy(golden + generated[:100])),
                    ("injection", lambda: eval_injection(golden + generated)), ("letter_filter", eval_letter_filter),
                    ("ml", ml), ("data", eval_data), ("noninterference", lambda: eval_noninterference(fast))):
        try:
            sections[key] = fn()
        except Exception as exc:  # noqa: BLE001 - a failed section shows in the report and does not stop the rest
            sections[key] = {"status": "eroare", "error": f"{type(exc).__name__}: {exc}"[:400]}
    sections.update(_optional_sections(fast))
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
