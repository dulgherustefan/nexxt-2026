"""`versoml setup` ends with the fast evaluation, so the Evaluation page has a report after setup."""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from versoml import cli
from versoml.config import Settings

runner = CliRunner()


@pytest.fixture
def steps(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cli, "seed", lambda seed=7: calls.append("seed"))
    monkeypatch.setattr(cli, "train", lambda seed=7: calls.append("train"))
    monkeypatch.setattr(cli, "_build_frontend", lambda force=False: calls.append("ui") or True)
    return calls


def _eval_returns(monkeypatch, calls: list[str], outcome: tuple[str, float, str]) -> None:
    def fake(budget_s: float = cli.EVAL_BUDGET_S):
        calls.append("eval")
        return outcome

    monkeypatch.setattr(cli, "_run_fast_eval", fake)


def test_setup_ends_with_the_fast_evaluation(steps, monkeypatch):
    _eval_returns(monkeypatch, steps, ("ok", 21.7, "/tmp/var/eval/report.json"))
    result = runner.invoke(cli.app, ["setup"])
    assert result.exit_code == 0, result.output
    assert steps == ["seed", "train", "ui", "eval"]
    assert "report.json" in result.output and "versoml up" in result.output


@pytest.mark.parametrize("outcome", [("slow", 60.2, ""), ("failed", 3.0, "exit code 1")])
def test_setup_tells_the_user_to_run_the_evaluation_when_it_cannot_finish(steps, monkeypatch, outcome):
    _eval_returns(monkeypatch, steps, outcome)
    result = runner.invoke(cli.app, ["setup", "--no-ui"])
    assert result.exit_code == 0, result.output
    assert steps == ["seed", "train", "eval"]
    assert "versoml eval --fast" in " ".join(result.output.split())


def test_setup_can_skip_the_evaluation(steps, monkeypatch):
    _eval_returns(monkeypatch, steps, ("ok", 1.0, "x"))
    result = runner.invoke(cli.app, ["setup", "--no-ui", "--no-eval"])
    assert result.exit_code == 0 and steps == ["seed", "train"]
    assert "versoml eval --fast" in " ".join(result.output.split())


def test_fast_eval_runner_reports_the_written_file(tmp_path, monkeypatch):
    settings = Settings(versoml_var_dir=tmp_path / "var")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    report = settings.var_dir / "eval" / "report.json"
    script = f"import pathlib; p = pathlib.Path({str(report)!r}); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{{}}')"
    monkeypatch.setattr(cli, "_eval_command", lambda: [sys.executable, "-c", script])
    status, seconds, detail = cli._run_fast_eval(budget_s=60)
    assert status == "ok" and detail == str(report) and seconds < 60


def test_fast_eval_runner_stops_at_the_budget(monkeypatch):
    monkeypatch.setattr(cli, "_eval_command", lambda: [sys.executable, "-c", "import time; time.sleep(30)"])
    status, seconds, _ = cli._run_fast_eval(budget_s=1)
    assert status == "slow" and seconds < 15


def test_fast_eval_runner_reports_a_failure(monkeypatch):
    monkeypatch.setattr(cli, "_eval_command", lambda: [sys.executable, "-c", "import sys; sys.exit(3)"])
    status, _, detail = cli._run_fast_eval(budget_s=60)
    assert status == "failed" and "3" in detail
