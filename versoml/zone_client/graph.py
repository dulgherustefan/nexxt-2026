"""The dispute judge's graph (LangGraph): identification, a router that sends only the collectors a case needs
(LangGraph Send), the collectors in parallel, and interrupts for a person (picking the payment, approving)."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from versoml.zone_client import agents as A
from versoml.zone_client.routing import COLLECTORS


def merge(left: dict | None, right: dict | None) -> dict:
    out = dict(left or {})
    out.update(right or {})
    return out


class CaseState(TypedDict, total=False):
    case_id: str
    run_id: str
    scenario_hint: str
    complaint: dict
    pseudo: dict
    extracted: dict
    llm_mode: str
    match: dict
    declared: dict
    classification: dict
    clock: dict
    routing: list
    records: Annotated[dict, merge]
    fact_map: Annotated[dict, merge]
    domain_intel: Annotated[dict, merge]
    campaign: dict | None
    rule_context: dict
    rules: dict
    decisions: list
    refund: dict
    debate: dict
    recovery: dict
    letter: dict
    sealed: bool


def route_collectors(state: dict) -> list[Send] | str:
    """The router's plan as LangGraph Sends: each chosen collector gets the case state; none chosen goes straight to
    the rules engine."""
    chosen = [step["node"] for step in state.get("routing") or [] if step.get("run")]
    if not chosen:
        return "motor_reguli"
    return [Send(node, state) for node in chosen]


def build_graph(checkpointer=None):
    graph = StateGraph(CaseState)
    graph.add_node("receptor", A.receptor)
    graph.add_node("identificare", A.identificare)
    graph.add_node("clasificator", A.clasificator)
    graph.add_node("ceasornicar", A.ceasornicar)
    graph.add_node("router", A.router)
    for name in COLLECTORS:
        graph.add_node(name, getattr(A, name))
    graph.add_node("motor_reguli", A.motor_reguli)
    graph.add_node("outbox_aml", A.outbox_aml)
    graph.add_node("rambursare", A.rambursare)
    graph.add_node("dezbatere", A.dezbatere)
    graph.add_node("recuperare", A.recuperare)
    graph.add_node("redactor", A.redactor)
    graph.add_node("sigiliu", A.sigiliu)

    graph.add_edge(START, "receptor")
    graph.add_edge("receptor", "identificare")
    graph.add_edge("identificare", "clasificator")
    graph.add_edge("clasificator", "ceasornicar")
    graph.add_edge("ceasornicar", "router")
    graph.add_conditional_edges("router", route_collectors, [*COLLECTORS, "motor_reguli"])
    # the Sent collectors run in the same step; the rules engine runs once, after all of them
    for name in COLLECTORS:
        graph.add_edge(name, "motor_reguli")
    graph.add_edge("motor_reguli", "outbox_aml")
    graph.add_edge("outbox_aml", "rambursare")
    # the debate and the recovery do not depend on each other: they run in parallel, after the refund
    graph.add_edge("rambursare", "dezbatere")
    graph.add_edge("rambursare", "recuperare")
    graph.add_edge(["dezbatere", "recuperare"], "redactor")
    graph.add_edge("redactor", "sigiliu")
    graph.add_edge("sigiliu", END)
    return graph.compile(checkpointer=checkpointer)
