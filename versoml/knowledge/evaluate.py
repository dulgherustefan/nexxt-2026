"""Retrieval evaluation (BM25, dense, hybrid) on hand-labelled queries, and a grounding check of ask().

`retrieval_eval()` reports Recall@1/3/5, Hit@1/3/5, MRR@10 and nDCG@10 per method and per language, and
writes var/eval/kb.json. Query vectors of the eval set are committed, so the offline run still measures the
dense and hybrid methods. `hybrid_offline` is the degraded mode (no query vector): BM25 + char n-grams.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path

import numpy as np

from versoml.config import get_settings
from versoml.knowledge.build import eval_questions
from versoml.knowledge.index import ranking
from versoml.knowledge.kb import DEFAULT_KINDS, KnowledgeBase
from versoml.knowledge.text import normalize_ro

KS = (1, 3, 5)
METHODS = ("bm25", "dense", "hybrid", "hybrid_offline")


def relevant_items(row: dict) -> list[str]:
    return [f"rule:{r}" for r in row.get("expected_rule_ids", [])] + list(row.get("expected_ids", []))


def _matches(item: str, chunk_id: str) -> bool:
    return chunk_id.startswith(item[:-1]) if item.endswith("*") else chunk_id == item


def _first_rank(item: str, ranked: list[str]) -> int | None:
    for r, cid in enumerate(ranked, start=1):
        if _matches(item, cid):
            return r
    return None


def score_ranking(row: dict, ranked: list[str]) -> dict:
    items = relevant_items(row)
    ranks = [_first_rank(item, ranked[:10]) for item in items]
    out: dict = {}
    for k in KS:
        found = sum(1 for r in ranks if r is not None and r <= k)
        out[f"recall@{k}"] = found / len(items) if items else 0.0
        out[f"hit@{k}"] = 1.0 if found else 0.0
    first = min((r for r in ranks if r is not None), default=None)
    out["mrr@10"] = 1.0 / first if first else 0.0
    gains = sorted({r for r in ranks if r is not None})
    dcg = sum(1.0 / math.log2(r + 1) for r in gains)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(items), 10) + 1))
    out["ndcg@10"] = dcg / ideal if ideal else 0.0
    return out


def _mean(rows: list[dict]) -> dict:
    if not rows:
        return {}
    keys = rows[0].keys()
    return {k: round(float(np.mean([r[k] for r in rows])), 4) for k in keys}


def _rankings(kb: KnowledgeBase, query: str, k: int = 10) -> dict[str, list[str]]:
    """Top chunk IDs for each method, over the same candidates (the default kinds)."""
    kb._ensure_index()
    cand = kb._candidates(list(DEFAULT_KINDS), None)
    q = normalize_ro(query).strip()
    ids = [c.id for c in kb._chunks]
    out: dict[str, list[str]] = {}
    bm = kb.bm25_scores(q)
    out["bm25"] = [ids[i] for i in ranking(bm, cand, k)]
    matrix, found = kb.embedder.lookup([q], "search_query", namespace="kb", model=kb.model)
    if found[0] and kb._has_vec.any():
        ds = kb._dense @ matrix[0]
        ds[~kb._has_vec] = -1.0
        out["dense"] = [ids[i] for i in ranking(ds, cand, k)]
    else:
        out["dense"] = []
    out["hybrid"] = [h.id for h in kb.search(query, k=k)]
    order, _, _ = kb._rank(q, cand, namespace="kb", use_dense=False)  # the path without a query vector
    out["hybrid_offline"] = [ids[i] for i in order[:k]]
    return out


def retrieval_eval(kb: KnowledgeBase | None = None, *, write: bool = True, path: Path | None = None) -> dict:
    """Recall@1/3/5, Hit@1/3/5, MRR@10, nDCG@10 for bm25, dense, hybrid (and the offline hybrid)."""
    kb = kb or KnowledgeBase("client")
    questions = eval_questions()
    per_method: dict[str, list[dict]] = {m: [] for m in METHODS}
    per_lang: dict[str, dict[str, list[dict]]] = {}
    details = []
    started = time.perf_counter()
    dense_missing = 0
    latencies = []
    for row in questions:
        t0 = time.perf_counter()
        ranked = _rankings(kb, row["query"])
        latencies.append((time.perf_counter() - t0) * 1000)
        if not ranked["dense"]:
            dense_missing += 1
        entry = {"id": row["id"], "lang": row["lang"], "query": row["query"], "relevant": relevant_items(row)}
        for method in METHODS:
            scores = score_ranking(row, ranked[method])
            per_method[method].append(scores)
            per_lang.setdefault(row["lang"], {}).setdefault(method, []).append(scores)
            entry[method] = {"top5": ranked[method][:5], **{k: v for k, v in scores.items() if k in ("recall@5", "mrr@10")}}
        details.append(entry)
    report = {
        "queries": len(questions),
        "by_lang": {lang: len(v["bm25"]) for lang, v in per_lang.items()},
        "embedding_model": kb.model,
        "dense_query_vectors_missing": dense_missing,
        "methods": {m: _mean(v) for m, v in per_method.items()},
        "methods_by_lang": {lang: {m: _mean(v) for m, v in d.items()} for lang, d in per_lang.items()},
        "kb": kb.stats(),
        "seconds": round(time.perf_counter() - started, 2),
        "query_ms_p50": round(float(np.median(latencies)), 2) if latencies else None,
        "details": details,
    }
    m = report["methods"]
    report["target_hybrid_ge_single_recall@5"] = bool(m and m["hybrid"]["recall@5"] >= max(m["bm25"]["recall@5"], m["dense"]["recall@5"]))
    report["grounding"] = grounding_check(kb)
    if write:
        out = path or get_settings().var_dir / "eval" / "kb.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report["path"] = str(out)
    return report


def _citation_relevant(row: dict, hit) -> bool:
    if any(_matches(item, hit.id) for item in relevant_items(row)):
        return True
    return bool(set(row.get("expected_rule_ids", [])) & set(hit.rule_ids))


def grounding_check(kb: KnowledgeBase, *, llm=None) -> dict:
    """ask() on the questions marked "ask": citation precision, grounded rate, verified quotes (offline by default)."""
    from versoml.config import Settings
    from versoml.knowledge.answer import _MARKER
    from versoml.shared.llm import LLMClient

    rows = [r for r in eval_questions() if r.get("ask")]
    client = llm or LLMClient(Settings(versoml_llm_mode="offline", versoml_var_dir=kb.settings.var_dir))
    previous, kb._llm = kb._llm, client

    async def ask_all():
        return [await kb.ask(r["query"]) for r in rows]

    try:
        if _running_loop():  # called from async code: run the answers on a worker thread with its own loop
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=1) as pool:
                answers = pool.submit(asyncio.run, ask_all()).result()
        else:
            answers = asyncio.run(ask_all())
    finally:
        kb._llm = previous
    total = relevant = grounded = with_answer = markers_ok = 0
    per = []
    for row, answer in zip(rows, answers):
        if answer is None:
            continue
        cits = answer.citations
        rel = sum(1 for h in cits if _citation_relevant(row, h))
        total += len(cits)
        relevant += rel
        grounded += int(answer.grounded)
        with_answer += int(bool(cits))
        numbers = {int(n) for m in _MARKER.findall(answer.answer) for n in m.strip(" []").split(",")}
        markers_ok += int(all(1 <= n <= len(cits) for n in numbers))
        per.append({"id": row["id"], "grounded": answer.grounded, "citations": [h.id for h in cits],
                    "relevant": rel, "mode": answer.mode})
    n = len(per) or 1
    return {
        "questions": len(per),
        "citation_precision": round(relevant / total, 4) if total else 0.0,
        "grounded_rate": round(grounded / n, 4),
        "answered_rate": round(with_answer / n, 4),
        "markers_valid_rate": round(markers_ok / n, 4),
        "details": per,
    }


def _running_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def eval_section(fast: bool = False) -> dict:
    """The retrieval section of the evaluation report (versoml/eval/run.py)."""
    r = retrieval_eval()
    m = r["methods"]
    r.pop("details", None)
    r["summary_rows"] = [
        {"name": f"Knowledge base Recall@5 ({name})", "value": round(m[name]["recall@5"], 3), "target": ">= 0.80" if name == "hybrid" else ""}
        for name in ("bm25", "dense", "hybrid") if name in m
    ] + [{"name": "Knowledge base answers fully cited", "value": r["grounding"].get("grounded_rate"), "target": "1.0"}]
    r["markdown"] = ["## Knowledge base retrieval", "", f"{r['queries']} labelled queries ({r['by_lang']}), model {r['embedding_model']}.", "",
                     "| Method | R@1 | R@5 | MRR@10 | nDCG@10 |", "|---|---|---|---|---|"]
    r["markdown"] += [f"| {name} | {v['recall@1']:.3f} | {v['recall@5']:.3f} | {v['mrr@10']:.3f} | {v['ndcg@10']:.3f} |" for name, v in m.items()]
    r["markdown"].append("")
    return r
