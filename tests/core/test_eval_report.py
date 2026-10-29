"""The evaluation report: English headings, and the fast run never rewrites the tracked markdown report."""

from __future__ import annotations

import asyncio
import json

from versoml.config import Settings
from versoml.eval import run


def _isolate(tmp_path, monkeypatch) -> Settings:
    settings = Settings(versoml_var_dir=tmp_path / "var")
    (tmp_path / "reports").mkdir()
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "get_settings", lambda: settings)
    monkeypatch.setattr(run, "_rows", lambda path: [])
    monkeypatch.setattr(run, "eval_noninterference", lambda fast: {"runs": 12, "leaks": 0, "mismatches": 0})
    return settings


def test_fast_eval_writes_only_the_json(tmp_path, monkeypatch):
    settings = _isolate(tmp_path, monkeypatch)
    report = asyncio.run(run.run_all(fast=True))
    assert (settings.var_dir / "eval" / "report.json").exists()
    assert not (tmp_path / "reports" / "eval_report.md").exists()
    assert set(report["paths"]) == {"json"}


def test_full_eval_writes_an_english_markdown_report(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    report = asyncio.run(run.run_all(fast=False))
    md = (tmp_path / "reports" / "eval_report.md").read_text(encoding="utf-8")
    assert md.startswith("# VersoML evaluation report\n") and "| Metric | Value | Target |" in md and "## Details" in md
    names = [row["name"] for row in report["summary"]["rows"]]
    assert "Letter check: tipping-off recall" in names and "Injections detected" in names
    assert all(not any(ch in name for ch in "ăâîșț") for name in names)
    saved = json.loads((tmp_path / "var" / "eval" / "report.json").read_text(encoding="utf-8"))
    assert saved["sections"]["letter_filter"]["tipping_off_recall"] == 1.0
    assert saved["sections"]["letter_filter"]["false_blocks"] == 0


def test_rules_rows_say_they_compare_the_engine_with_the_oracle(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    report = asyncio.run(run.run_all(fast=False))
    names = [row["name"] for row in report["summary"]["rows"]]
    assert not any(name.startswith("Rules:") for name in names)
    assert sum(name.startswith("Rules engine vs oracle:") for name in names) == 5
    md = (tmp_path / "reports" / "eval_report.md").read_text(encoding="utf-8")
    assert "`versoml/data/oracle.py`" in md and "do not say how well the pipeline reads a complaint" in md


def test_injection_effect_on_the_decision_is_measured():
    rows = run._rows(run.GOLDEN_DIR / "golden_40.jsonl") + run._rows(run.GOLDEN_DIR / "generated_300.jsonl")
    out = run.eval_injection(rows)
    assert out["twins_compared"] == out["injection_cases"] == 28
    assert out["decision_moved_toward_injection"] == 0
    assert out["decision_changed_by_injection"] == (out["sign_off_added_by_injection"] + out["other_changes"]
                                                    + out["decision_moved_toward_injection"])


def test_the_clean_twin_has_no_planted_instructions_left():
    from versoml.zone_client.agents import detect_injection
    from versoml.zone_client.matcher import compose_text

    rows = run._rows(run.GOLDEN_DIR / "golden_40.jsonl") + run._rows(run.GOLDEN_DIR / "generated_300.jsonl")
    planted = run._injected_texts()
    for row in (r for r in rows if r["scenario"] == "injectie_document"):
        bare = run._without(row["complaint"], planted)
        assert bare != row["complaint"], row["id"]
        assert detect_injection(compose_text(bare["text"], bare["attachments"])) is None, row["id"]


def test_privacy_eval_counts_with_a_checker_the_masking_does_not_share():
    rows = [{"id": "P1", "complaint": {"text": "IBAN RO49 AAAA 1B31 0075 9384 0000, tel +44 20 7946 0958.",
                                       "attachments": [{"kind": "sms", "content": "scrieți la ana.pop@example.ro"}]}},
            {"id": "P2", "complaint": {"text": "CNP 1900101 401091, scris cu un spațiu.", "attachments": []}}]
    out = run.eval_privacy(rows)
    assert out["checker_found_in_raw_text"] == {"IBAN": 1, "TELEFON": 1, "EMAIL": 1, "CNP": 1}
    assert out["checker_found_after_pseudonymization"] == {"CNP": 1}
    assert out["raw_pii_to_llm"] == 1 and out["masking_recognizers_find_again"] == 0


def _case(case_id: str, started: str, rules_done: str, sealed: str | None, **extra) -> dict:
    nodes = {"motor_reguli": {"finished_at": rules_done}, "rambursare": {"started_at": rules_done}}
    if sealed:
        nodes["sigiliu"] = {"finished_at": sealed}
    return {"case_id": case_id, "started_at": started, "llm_mode": "live", "pipeline_status": nodes, **extra}


def test_case_run_times_come_from_the_stored_documents(tmp_path, monkeypatch):
    import sqlite3

    settings = Settings(versoml_var_dir=tmp_path / "var")
    monkeypatch.setattr(run, "get_settings", lambda: settings)
    assert run.eval_case_runs() == {"status": "no stored case runs"}
    docs = [_case("C1", "2026-10-29T10:00:00+00:00", "2026-10-29T10:00:03+00:00", "2026-10-29T10:00:40+00:00"),
            # 300 s waiting for the sign-off are not counted
            _case("C2", "2026-10-29T11:00:00+00:00", "2026-10-29T11:00:05+00:00", "2026-10-29T11:06:00+00:00",
                  approved_at="2026-10-29T11:05:05+00:00"),
            _case("C3", "2026-10-29T12:00:00+00:00", "2026-10-29T12:00:02+00:00", None),
            # a person picked the payment before the rules ran: left out
            _case("C4", "2026-10-29T13:00:00+00:00", "2026-10-29T13:09:00+00:00", None,
                  interrupt={"kind": "pick_transaction"})]
    with sqlite3.connect(settings.client_db) as conn:
        conn.execute("CREATE TABLE versoml_cases (id TEXT PRIMARY KEY, doc TEXT)")
        conn.executemany("INSERT INTO versoml_cases VALUES (?, ?)", [(d["case_id"], json.dumps(d)) for d in docs])
    out = run.eval_case_runs()
    live = out["by_llm_mode"]["live"]
    assert live["to_refund_decision"] == {"runs": 3, "median_s": 3.0, "p90_s": 5.0, "max_s": 5.0}
    assert live["to_sealed_file_without_wait"] == {"runs": 2, "median_s": 50.0, "p90_s": 60.0, "max_s": 60.0}
    assert [r["value"] for r in out["summary_rows"]] == ["3.0 / 5.0 (3 runs)", "50.0 / 60.0 (2 runs)"]
    assert "not reported" in out["cost"]


def test_only_ratio_rows_are_printed_as_percentages():
    rows = [{"name": "Injections detected", "value": 0.975, "target": "100%", "unit": "ratio"},
            {"name": "Letter check: tipping-off recall", "value": 1, "target": "100%", "unit": "ratio"},
            {"name": "Inference latency, median (s)", "value": 0.4, "target": "measured"},
            {"name": "ms per case", "value": 0.8125, "target": "measured"},
            {"name": "M5 money mules: AUC", "value": 0.87342, "target": ">= 0.85"},
            {"name": "Leaks across the wall", "value": 0, "target": "0"},
            {"name": "Not measured", "value": None, "target": "100%", "unit": "ratio"}]
    md = run._markdown({"at": "2026-10-29T10:00:00Z", "llm_mode": "offline", "summary": {"rows": rows},
                        "sections": {}})
    table = {line.split(" | ")[0][2:]: line.split(" | ")[1] for line in md.splitlines() if line.startswith("| ")}
    assert table["Injections detected"] == "97.5%" and table["Letter check: tipping-off recall"] == "100.0%"
    assert table["Inference latency, median (s)"] == "0.4" and table["ms per case"] == "0.812"
    assert table["M5 money mules: AUC"] == "0.873" and table["Leaks across the wall"] == "0"
    assert table["Not measured"] == "n/a"
