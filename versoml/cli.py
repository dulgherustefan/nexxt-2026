"""The `versoml` command line: setup, the two zone processes, MCP, evaluation, the Bedrock check, the demo."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time

import typer
from rich.console import Console
from rich.table import Table

from versoml.config import ROOT, get_settings

# The default Windows console (cp1252) cannot print ș/ț: switch the output to UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

app = typer.Typer(add_completion=False, help="VersoML: payment disputes refunded by the next business day, with an evidence file for each case.")
console = Console()

# `setup` runs the fast evaluation when it fits in this budget (about 20 s on a laptop, from a fresh var/)
EVAL_BUDGET_S = 60.0


def _seeded() -> bool:
    s = get_settings()
    return s.client_db.exists() and s.aml_db.exists()


def _trained() -> bool:
    return (get_settings().models_dir / "metrics.json").exists()


@app.command()
def seed(seed: int = 7) -> None:
    """Generate the synthetic world and write the two separate databases (client zone, AML zone)."""
    from versoml.data.seed import seed_all

    counts = seed_all(seed=seed)
    table = Table("Table", "Rows", title="Synthetic data")
    for key, value in (counts or {}).items():
        table.add_row(str(key), str(value))
    console.print(table)


@app.command()
def train(seed: int = 7) -> None:
    """Train the ML models (M1, M2, M5) and save their metrics."""
    from versoml.ml.train import train_all

    metrics = train_all(seed=seed)
    console.print_json(json.dumps(metrics, ensure_ascii=False, default=str)[:4000])


def _build_frontend(force: bool = False) -> bool:
    frontend = ROOT / "frontend"
    if (frontend / "dist" / "index.html").exists() and not force:
        return True
    npm = shutil.which("npm")
    if not npm or not (frontend / "package.json").exists():
        console.print("[yellow]npm or frontend/package.json is missing, so the website was not built.[/]")
        return False
    console.print("Building the website (npm install + build)…")
    if not (frontend / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=frontend, check=False, shell=os.name == "nt")
    result = subprocess.run([npm, "run", "build"], cwd=frontend, check=False, shell=os.name == "nt")
    return result.returncode == 0


def _eval_command() -> list[str]:
    return [sys.executable, "-m", "versoml.cli", "eval", "--fast"]


def _stop(proc: subprocess.Popen) -> None:
    """Stop the evaluation and the processes it started (the non-interference run is its child)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()
    try:
        proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _run_fast_eval(budget_s: float = EVAL_BUDGET_S) -> tuple[str, float, str]:
    """Run `versoml eval --fast` in a child process, within `budget_s` seconds.

    Returns ("ok", seconds, report path), ("slow", seconds, "") if it was stopped at the budget, or
    ("failed", seconds, reason).
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    group: dict = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
    began, started = time.time(), time.perf_counter()
    proc = subprocess.Popen(_eval_command(), cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **group)
    try:
        _, err = proc.communicate(timeout=budget_s)
    except subprocess.TimeoutExpired:
        _stop(proc)
        return "slow", time.perf_counter() - started, ""
    seconds = time.perf_counter() - started
    if proc.returncode != 0:
        last = [line for line in (err or "").splitlines() if line.strip()][-1:]
        return "failed", seconds, f"exit code {proc.returncode}" + (f": {last[0].strip()[:200]}" if last else "")
    report = get_settings().var_dir / "eval" / "report.json"
    if not report.exists() or report.stat().st_mtime < began - 1:
        return "failed", seconds, f"{report} was not written"
    return "ok", seconds, str(report)


@app.command()
def setup(seed: int = 7, ui: bool = True,
          evaluate: bool = typer.Option(True, "--eval/--no-eval",
                                        help="End with the fast evaluation (no LLM calls), for the Evaluation page")) -> None:
    """Everything in one command: data, models, website and the fast evaluation."""
    globals()["seed"](seed)
    train(seed)
    if ui:
        _build_frontend(force=True)
    if not evaluate:
        console.print("Skipped the evaluation. Run [bold]versoml eval --fast[/] to fill the Evaluation page.")
    else:
        console.print("Running the fast evaluation (no LLM calls)…")
        status, seconds, detail = _run_fast_eval()
        if status == "ok":
            console.print(f"Evaluation report: {detail} ({seconds:.0f} s). The Evaluation page shows it.")
        elif status == "slow":
            console.print(f"[yellow]The fast evaluation needs more than {EVAL_BUDGET_S:.0f} s on this machine, so setup "
                          "stopped it.[/] Run [bold]versoml eval --fast[/] to fill the Evaluation page.")
        else:
            console.print(f"[yellow]The fast evaluation failed ({detail}).[/] Run [bold]versoml eval --fast[/] to see the "
                          "error and fill the Evaluation page.")
    console.print("[bold]Done.[/] Start with: [bold]versoml up[/]")


@app.command()
def up(no_aml: bool = typer.Option(False, help="Start only the client zone"),
       reload: bool = typer.Option(False, help="Restart when the code changes")) -> None:
    """Start the client zone (:8000) and the AML zone (:8001) as separate processes."""
    s = get_settings()
    if not _seeded():
        console.print("First run: generating the synthetic data…")
        globals()["seed"]()
    if not _trained():
        console.print("Training the ML models…")
        train()
    _build_frontend()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    procs = []
    zones = [("client", "versoml.zone_client.app:app", s.versoml_client_port)]
    if not no_aml:
        zones.append(("aml", "versoml.zone_aml.app:app", s.versoml_aml_port))
    for name, target, port in zones:
        cmd = [sys.executable, "-m", "uvicorn", target, "--host", s.versoml_host, "--port", str(port), "--log-level", "warning"]
        if reload:
            cmd.append("--reload")
        procs.append((name, subprocess.Popen(cmd, cwd=ROOT, env={**env, "VERSOML_ZONE": name})))
    base = f"http://{s.versoml_host}:{s.versoml_client_port}"
    console.print(f"[bold]Client zone[/]  {base}  (console; Demo Bank at {base}/bank; MCP at {base}/mcp/)")
    if not no_aml:
        console.print(f"[bold]AML zone[/]     http://{s.versoml_host}:{s.versoml_aml_port}  (separate process, separate database)")
    console.print("Ctrl+C stops both processes.")
    try:
        while all(p.poll() is None for _, p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        for _, p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


@app.command()
def mcp(zone: str = typer.Option("client", help="client or aml"),
        transport: str = typer.Option("stdio", help="stdio or http"),
        port: int | None = typer.Option(None)) -> None:
    """Start a zone's MCP server (for Claude Desktop, Cursor or another MCP client)."""
    sys.argv = ["versoml-mcp", "--zone", zone, "--transport", transport] + (["--port", str(port)] if port else [])
    from versoml.mcp_server.server import main

    main()


@app.command("check-bedrock")
def check_bedrock(full: bool = False) -> None:
    """Step 0: which region and which models work with the key (the key itself is never printed)."""
    from versoml.shared.llm.probe import probe_bedrock

    report = probe_bedrock(full=full)
    console.print(report.get("verdict"))
    if report.get("recommended"):
        console.print_json(json.dumps(report["recommended"]))


@app.command("eval")
def run_eval(fast: bool = typer.Option(False, help="Skip the full graph runs when their results already exist")) -> None:
    """The evaluation: rules on the golden set, escalations, non-interference, PII, injection, ML. Writes the report."""
    from versoml.eval.run import run_all

    report = asyncio_run(run_all(fast=fast))
    console.print(f"Report: {report.get('paths', {})}")
    summary = report.get("summary", {})
    table = Table("Metric", "Value", "Target", title="VersoML · evaluation")
    for row in summary.get("rows", []):
        table.add_row(row["name"], str(row["value"]), str(row.get("target", "")))
    console.print(table)


@app.command()
def demo() -> None:
    """Run the demo scenario end to end, without the website (a quick check)."""
    from versoml.eval.run import run_demo

    console.print_json(json.dumps(asyncio_run(run_demo()), ensure_ascii=False, default=str)[:6000])


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    app()
