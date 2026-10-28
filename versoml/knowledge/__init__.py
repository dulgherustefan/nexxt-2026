"""VersoML knowledge base: hybrid retrieval (BM25 + Bedrock embeddings + RRF) and grounded answers.

    from versoml.knowledge import get_kb
    kb = get_kb("client")            # the AML zone ("aml") never loads client precedents
    hits = kb.search("By when must the bank refund an unauthorized payment?")
    answer = await kb.ask("Ce face banca dacă plătitorul a fost grav neglijent?")

Heavy modules load on first use, so importing this package is cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from versoml.knowledge.models import Answer, Hit

if TYPE_CHECKING:  # pragma: no cover
    from versoml.knowledge.embeddings import embed_texts
    from versoml.knowledge.kb import KnowledgeBase, get_kb

__all__ = ["Answer", "Hit", "KnowledgeBase", "embed_texts", "get_kb"]


def __getattr__(name: str) -> Any:
    if name == "embed_texts":
        from versoml.knowledge.embeddings import embed_texts

        return embed_texts
    if name in ("KnowledgeBase", "get_kb"):
        from versoml.knowledge import kb

        return getattr(kb, name)
    raise AttributeError(f"module 'versoml.knowledge' has no attribute {name!r}")
