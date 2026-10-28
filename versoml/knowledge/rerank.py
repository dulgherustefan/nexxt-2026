"""Optional second stage: Cohere Rerank 3.5 on Bedrock over the fused top candidates (off by default).

Live only when live calls are allowed; the query passes the PII guard first. Any failure keeps the fused order.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

log = logging.getLogger("versoml.knowledge.rerank")

# backend(model_id, query, documents, top_n) -> [(index, relevance_score)], best first
RerankBackend = Callable[[str, str, list[str], int], list[tuple[int, float]]]
_backend: RerankBackend | None = None


def set_backend(backend: RerankBackend | None) -> None:
    """Replace the Bedrock call (tests)."""
    global _backend
    _backend = backend


def _bedrock(model_id: str, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    from versoml.knowledge.embeddings import get_embedder

    backend = get_embedder().backend
    client = backend.client() if hasattr(backend, "client") else None
    if client is None:
        raise RuntimeError("no Bedrock client")
    body = {"query": query, "documents": documents, "top_n": top_n, "api_version": 2}
    response = client.invoke_model(modelId=model_id, body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                   contentType="application/json", accept="application/json")
    data = json.loads(response["body"].read())
    return [(int(r["index"]), float(r["relevance_score"])) for r in data.get("results", [])]


def rerank_order(kb, query: str, order: list[int], why: dict[int, dict]) -> list[int]:
    from versoml.knowledge.settings import get_kb_settings

    settings = get_kb_settings()
    head, tail = order[: settings.rerank_candidates], order[settings.rerank_candidates:]
    if len(head) < 2:
        return order
    if _backend is None and not kb.embedder.live_allowed(None):
        for i in head:
            why[i]["rerank"] = "skipped (no live calls)"
        return order
    try:
        from versoml.shared.privacy import assert_llm_safe

        assert_llm_safe(query)
        docs = [kb._chunks[i].embed_text()[:4000] for i in head]
        if any(kb._chunks[i].kind == "precedent" for i in head):
            assert_llm_safe(docs)
        results = (_backend or _bedrock)(settings.rerank_model, query, docs, len(docs))
    except Exception as exc:  # noqa: BLE001 - the fused order is a correct answer too
        log.warning("Rerank skipped: %s", type(exc).__name__)
        for i in head:
            why[i]["rerank"] = "failed"
        return order
    ranked = []
    for pos, (idx, score) in enumerate(results, start=1):
        if 0 <= idx < len(head) and head[idx] not in ranked:
            ranked.append(head[idx])
            why[head[idx]]["rerank_rank"] = pos
            why[head[idx]]["rerank_score"] = round(score, 4)
    ranked += [i for i in head if i not in ranked]
    return ranked + tail
