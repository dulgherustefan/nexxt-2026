"""`versoml kb build`: chunk the sources, write the committed snapshot, and (with --live) embed it.

The committed vectors cover the static corpus, the golden precedents and the eval queries, so the offline
evaluation still measures dense and hybrid retrieval. Vectors for texts that are no longer in the corpus are
pruned, which keeps versoml/data/kb small.
"""

from __future__ import annotations

import json
from pathlib import Path

from versoml.knowledge import corpus
from versoml.knowledge.embeddings import Embedder, cache_key, get_embedder, model_spec

EVAL_QUERIES = Path(__file__).with_name("eval_queries.jsonl")


def eval_questions(path: Path = EVAL_QUERIES) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("//"):
            rows.append(json.loads(line))
    return rows


def query_texts() -> list[str]:
    """Every query text whose vector is committed (the retrieval eval; the grounding check reuses its questions)."""
    return list(dict.fromkeys(row["query"] for row in eval_questions()))


def build(*, live: bool = False, model: str | None = None, kb_dir: Path | None = None,
          embedder: Embedder | None = None) -> dict:
    kb_dir = Path(kb_dir) if kb_dir else corpus.KB_DIR
    spec = model_spec(model)
    emb = embedder or get_embedder()
    static = corpus.build_static_corpus()
    precedents = corpus.golden_precedents()
    groups = {
        "kb": ([c.embed_text() for c in static], "search_document"),
        "precedents": ([c.embed_text() for c in precedents], "search_document"),
    }
    queries = query_texts()
    report: dict = {"model": spec.model_id, "live": live, "vectors": {}}
    if live:
        for namespace, (texts, input_type) in groups.items():
            out = emb.embed(texts, input_type, namespace=namespace, allow_live=True, static=True, model=spec.model_id)
            report["vectors"][namespace] = "ok" if out is not None else f"failed: {emb.stats.last_error}"
        out = emb.embed(queries, "search_query", namespace="kb", allow_live=True, static=True, model=spec.model_id)
        report["vectors"]["queries"] = "ok" if out is not None else f"failed: {emb.stats.last_error}"
        # prune vectors of texts that are gone
        keep_kb = {cache_key(spec.model_id, "search_document", t) for t in groups["kb"][0]}
        keep_kb |= {cache_key(spec.model_id, "search_query", t) for t in queries}
        emb.static_cache("kb", spec.model_id).flush(keep=keep_kb)
        keep_prec = {cache_key(spec.model_id, "search_document", t) for t in groups["precedents"][0]}
        emb.static_cache("precedents", spec.model_id).flush(keep=keep_prec)
    coverage = {}
    for namespace, (texts, input_type) in groups.items():
        _, found = emb.lookup(texts, input_type, namespace=namespace, model=spec.model_id)
        coverage[namespace] = {"chunks": len(texts), "with_vectors": int(found.sum())}
    _, found = emb.lookup(queries, "search_query", namespace="kb", model=spec.model_id)
    coverage["queries"] = {"queries": len(queries), "with_vectors": int(found.sum())}
    report["coverage"] = coverage
    manifest = corpus.write_snapshot(static, precedents, model=spec.model_id, kb_dir=kb_dir,
                                     extra={"coverage": coverage})
    report["manifest"] = manifest
    report["files"] = {p.name: p.stat().st_size for p in sorted(kb_dir.glob("*")) if p.is_file()}
    report["total_bytes"] = sum(report["files"].values())
    return report
