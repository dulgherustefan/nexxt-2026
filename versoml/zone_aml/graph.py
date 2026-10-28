"""Graful Investigatorului (LangGraph): graf + ML și OSINT în paralel, apoi analistul."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from versoml.zone_aml import agents as A


class LeadState(TypedDict, total=False):
    lead_id: str
    run_id: str
    referrals: list
    ibans: list
    fact_ids: list
    accounts: list
    typologies: list
    graph_fact: str
    osint: list
    osint_summary: str
    innocent: list
    recommendation: str
    clocks: list
    rules_fact: str
    rts: dict | None
    decision: str


def build_graph(checkpointer=None):
    graph = StateGraph(LeadState)
    for name in ("receptor_fapte", "graf_ml", "osint", "nevinovatie", "reguli_aml", "redactor_rts", "analist", "sigiliu"):
        graph.add_node(name, getattr(A, name))
    graph.add_edge(START, "receptor_fapte")
    graph.add_edge("receptor_fapte", "graf_ml")
    graph.add_edge("receptor_fapte", "osint")
    graph.add_edge(["graf_ml", "osint"], "nevinovatie")
    graph.add_edge("nevinovatie", "reguli_aml")
    graph.add_edge("reguli_aml", "redactor_rts")
    graph.add_edge("redactor_rts", "analist")
    graph.add_edge("analist", "sigiliu")
    graph.add_edge("sigiliu", END)
    return graph.compile(checkpointer=checkpointer)
