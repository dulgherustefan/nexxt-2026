"""Data contracts of the knowledge base: retrieved chunks (Hit) and grounded answers (Answer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["rule", "law", "guidance", "typology", "case_study", "precedent"]
KINDS: tuple[str, ...] = ("rule", "law", "guidance", "typology", "case_study", "precedent")
ConfidenceMark = Literal["P", "S", "U"]


class Hit(BaseModel):
    """One retrieved chunk.

    id: "rule:PAY-03", "ctx:<file-stem>#<slug>", "typ:<id>", "case:<slug>#<n>", "prec:<case_id>".
    why: the signals behind the rank, e.g. {"bm25_rank": 2, "dense_rank": 1, "rrf": 0.0325, "dense": true}.
    meta: precedents carry {"outcome": {...}, "scenario": "...", "case_id": "..."}.
    """

    id: str
    kind: Kind
    title: str
    text: str
    source: str
    confidence: ConfidenceMark | None = None
    rule_ids: list[str] = Field(default_factory=list)
    score: float = 0.0
    why: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)


class Answer(BaseModel):
    """A grounded answer: sentences carry [n] markers, 1-based into `citations`."""

    question: str
    answer: str
    citations: list[Hit] = Field(default_factory=list)
    grounded: bool = False
    mode: str = "offline"
