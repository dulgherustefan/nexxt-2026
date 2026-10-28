"""Linia de comandă `versoml`: setup, rulare pe două procese, MCP, evaluare, verificarea Bedrock, demo."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from versoml.config import ROOT, get_settings

# Consola Windows implicită (cp1252) nu poate afișa ș/ț: ieșirea trece pe UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

app = typer.Typer(add_completion=False, help="VersoML: contestații la T+1, pista AML, zid anti-tipping-off.")
console = Console()


def _seeded() -> bool:
    s = get_settings()
    return s.client_db.exists() and s.aml_db.exists()


def _trained() -> bool:
    return (get_settings().models_dir / "metrics.json").exists()


@app.command()
def seed(seed: int = 7) -> None:
    """Generează lumea sintetică și scrie cele două baze separate (client, AML)."""
    from versoml.data.seed import seed_all

    counts = seed_all(seed=seed)
    table = Table("Tabel", "Rânduri", title="Date sintetice")
    for key, value in (counts or {}).items():
        table.add_row(str(key), str(value))
    console.print(table)


@app.command()
def train(seed: int = 7) -> None:
    """Antrenează modelele ML (M1, M2, M5) și salvează metricile."""
    from versoml.ml.train import train_all

    metrics = train_all(seed=seed)
    console.print_json(json.dumps(metrics, ensure_ascii=False, default=str)[:4000])


def _build_frontend(force: bool = False) -> bool:
    frontend = ROOT / "frontend"
    if (frontend / "dist" / "index.html").exists() and not force:
        return True
    npm = shutil.which("npm")
    if not npm or not (frontend / "package.json").exists():
        console.print("[yellow]npm sau frontend/package.json lipsește: UI-ul nu se construiește.[/]")
        return False
    console.print("Construiesc interfața (npm install + build)…")
    if not (frontend / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=frontend, check=False, shell=os.name == "nt")
    result = subprocess.run([npm, "run", "build"], cwd=frontend, check=False, shell=os.name == "nt")
    return result.returncode == 0


@app.command()
def setup(seed: int = 7, ui: bool = True) -> None:
    """Totul dintr-o comandă: date, modele, interfață."""
    globals()["seed"](seed)
    train(seed)
    if ui:
        _build_frontend(force=True)
    console.print("[bold]Gata.[/] Pornește cu: [bold]versoml up[/]")


@app.command()
def up(no_aml: bool = typer.Option(False, help="Pornește doar zona client"),
       reload: bool = typer.Option(False, help="Repornire la modificarea codului")) -> None:
    """Pornește zona client (:8000) și zona AML (:8001) ca procese separate."""
    s = get_settings()
    if not _seeded():
        console.print("Prima rulare: generez datele sintetice…")
        globals()["seed"]()
    if not _trained():
        console.print("Antrenez modelele ML…")
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
    console.print(f"[bold]Zona client[/]  http://{s.versoml_host}:{s.versoml_client_port}  (consola, Banca Demo, MCP la /mcp/)")
    if not no_aml:
        console.print(f"[bold]Zona AML[/]     http://{s.versoml_host}:{s.versoml_aml_port}  (proces separat, bază separată)")
    console.print("Ctrl+C oprește ambele procese.")
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
def mcp(zone: str = typer.Option("client", help="client sau aml"),
        transport: str = typer.Option("stdio", help="stdio sau http"),
        port: int | None = typer.Option(None)) -> None:
    """Pornește serverul MCP al unei zone (pentru Claude Desktop, Cursor sau alt client MCP)."""
    sys.argv = ["versoml-mcp", "--zone", zone, "--transport", transport] + (["--port", str(port)] if port else [])
    from versoml.mcp_server.server import main

    main()


@app.command("check-bedrock")
def check_bedrock(full: bool = False) -> None:
    """Pasul 0: ce regiune și ce modele merg cu cheia (fără s-o afișeze)."""
    from versoml.shared.llm.probe import probe_bedrock

    report = probe_bedrock(full=full)
    console.print(report.get("verdict"))
    if report.get("recommended"):
        console.print_json(json.dumps(report["recommended"]))


@app.command("eval")
def run_eval(fast: bool = typer.Option(False, help="Sare peste rulările complete ale grafului")) -> None:
    """Evaluarea: reguli pe setul de aur, escaladări, neinterferență, PII, injecție, ML. Scrie raportul."""
    from versoml.eval.run import run_all

    report = asyncio_run(run_all(fast=fast))
    console.print(f"Raport: {report.get('paths', {})}")
    summary = report.get("summary", {})
    table = Table("Metrică", "Valoare", "Țintă", title="VersoML · evaluare")
    for row in summary.get("rows", []):
        table.add_row(row["name"], str(row["value"]), str(row.get("target", "")))
    console.print(table)


@app.command()
def demo() -> None:
    """Rulează scenariul demo cap-coadă, fără UI (verificare rapidă)."""
    from versoml.eval.run import run_demo

    console.print_json(json.dumps(asyncio_run(run_demo()), ensure_ascii=False, default=str)[:6000])


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    app()
