"""Knowledge base settings. Values come from the environment or `.env` (prefix VERSOML_KB_)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from versoml.config import ROOT


class KBSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="VERSOML_KB_", extra="ignore")

    # Embedding model on Bedrock (us-east-1). Chosen on the eval set (versoml/knowledge/eval_queries.jsonl):
    # cohere.embed-v4:0 had the best dense and hybrid scores on the Romanian and English queries.
    embed_model: str = "cohere.embed-v4:0"
    # None = follow the LLM mode (live, or auto with a key). True/False forces live calls on or off.
    embed_live: bool | None = None
    # Reciprocal rank fusion: score = sum of weight / (k + rank) over the signals
    rrf_k: int = 60
    rrf_weight_bm25: float = 0.5
    rrf_weight_dense: float = 1.0
    rrf_weight_char: float = 0.3
    # Default MMR trade-off when a caller asks for diversity (1.0 = relevance only)
    mmr_lambda: float = 0.7
    # Optional second stage: Cohere Rerank 3.5 on Bedrock over the fused top candidates. Off by default:
    # general-purpose rerankers did poorly on legal text (LegalBench-RAG), so it stays an experiment.
    rerank: bool = False
    rerank_model: str = "cohere.rerank-v3-5:0"
    rerank_candidates: int = 20


@lru_cache
def get_kb_settings() -> KBSettings:
    return KBSettings()
