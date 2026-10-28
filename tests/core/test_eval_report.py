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
