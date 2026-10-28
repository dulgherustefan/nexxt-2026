"""`versoml kb ...`: build the knowledge base, search it, ask it, evaluate it."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

kb_app = typer.Typer(add_completion=False, help="Knowledge base: hybrid retrieval and grounded answers.")
console = Console()


@kb_app.command("build")
def build_cmd(live: bool = typer.Option(False, "--live", help="Embed the corpus and the eval queries on Bedrock"),
              model: str | None = typer.Option(None, help="Embedding model (default: the VERSOML_KB_EMBED_MODEL setting)")) -> None:
    """Chunk the sources into versoml/data/kb; with --live, also embed them (committed float16 vectors)."""
    from versoml.knowledge.build import build
    from versoml.knowledge.kb import reset_kb

    report = build(live=live, model=model)
    reset_kb()
    counts = report["manifest"]["counts"]
    table = Table("Item", "Value", title="Knowledge base build")
    table.add_row("Model", report["model"])
    table.add_row("Chunks (static)", str(counts["static"]))
    table.add_row("Precedents", str(counts["precedents"]))
    table.add_row("By kind", ", ".join(f"{k} {v}" for k, v in counts["by_kind"].items()))
    for name, cov in report["coverage"].items():
        total = cov.get("chunks", cov.get("queries"))
        table.add_row(f"Vectors: {name}", f"{cov['with_vectors']} / {total}")
    for name, status in report.get("vectors", {}).items():
        table.add_row(f"Embedding: {name}", status)
    table.add_row("Committed size", f"{report['total_bytes'] / 1e6:.2f} MB")
    console.print(table)


def _hits_table(hits, title: str) -> Table:
    table = Table("#", "ID", "Kind", "Mark", "Score", "Why", title=title)
    for n, hit in enumerate(hits, start=1):
        why = {k: v for k, v in hit.why.items() if k.endswith("_rank") or k in ("rule_id_boost", "fallback")}
        table.add_row(str(n), hit.id, hit.kind, hit.confidence or "", f"{hit.score:.4f}", json.dumps(why))
    return table


@kb_app.command("search")
def search_cmd(query: str, k: int = 6, zone: str = typer.Option("client", help="client or aml"),
               kind: list[str] = typer.Option(None, help="Filter by kind (repeatable)"),
               rule: list[str] = typer.Option(None, help="Filter by rule ID (repeatable)"),
               precedents: bool = typer.Option(False, help="Search past cases instead (client zone)")) -> None:
    """Hybrid search (BM25 + dense + RRF)."""
    from versoml.knowledge import get_kb

    kb = get_kb(zone)  # type: ignore[arg-type]
    hits = kb.precedents(query, k=k) if precedents else kb.search(query, k=k, kinds=kind or None, rule_ids=rule or None)
    console.print(_hits_table(hits, f"{zone} zone · {query}"))
    for n, hit in enumerate(hits[:3], start=1):
        console.print(f"[bold][{n}] {hit.title}[/] ({hit.source})")
        console.print(" ".join(hit.text.split())[:400])


@kb_app.command("ask")
def ask_cmd(question: str, k: int = 6, zone: str = typer.Option("client", help="client or aml")) -> None:
    """A grounded answer: every sentence cites retrieved chunks; quotes are checked against them."""
    import asyncio

    from versoml.knowledge import get_kb

    answer = asyncio.run(get_kb(zone).ask(question, k=k))  # type: ignore[arg-type]
    console.print(f"[bold]{answer.answer}[/]")
    console.print(f"grounded={answer.grounded} mode={answer.mode}")
    for n, hit in enumerate(answer.citations, start=1):
        console.print(f"[{n}] {hit.id} · {hit.title} ({hit.source})")


@kb_app.command("eval")
def eval_cmd() -> None:
    """Retrieval metrics for BM25, dense and hybrid, plus the grounding check. Writes var/eval/kb.json."""
    from versoml.knowledge.evaluate import retrieval_eval

    report = retrieval_eval()
    table = Table("Method", "Recall@1", "Recall@3", "Recall@5", "Hit@5", "MRR@10", "nDCG@10",
                  title=f"Retrieval · {report['queries']} queries · {report['embedding_model']}")
    for method, m in report["methods"].items():
        table.add_row(method, *(f"{m[key]:.3f}" for key in ("recall@1", "recall@3", "recall@5", "hit@5", "mrr@10", "ndcg@10")))
    console.print(table)
    g = report["grounding"]
    console.print(f"Grounding (offline ask, {g['questions']} questions): citation precision {g['citation_precision']:.3f}, "
                  f"grounded {g['grounded_rate']:.2f}, valid markers {g['markers_valid_rate']:.2f}")
    if report["dense_query_vectors_missing"]:
        console.print(f"[yellow]{report['dense_query_vectors_missing']} queries have no committed vector; run "
                      "`versoml kb build --live`.[/]")
    console.print(f"Report: {report.get('path')}")
