"""Graful Judecătorului (LangGraph): colectori în paralel, întrerupere pentru semnătura umană."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from versoml.zone_client import agents as A


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
    classification: dict
    clock: dict
    records: Annotated[dict, merge]
    fact_map: Annotated[dict, merge]
    domain_intel: Annotated[dict, merge]
    rule_context: dict
    rules: dict
    decisions: list
    refund: dict
    debate: dict
    recovery: dict
    letter: dict
    sealed: bool


COLLECTORS = ["colector_tranzactie", "colector_sca", "colector_dispozitiv", "colector_domeniu"]


def build_graph(checkpointer=None):
    graph = StateGraph(CaseState)
    graph.add_node("receptor", A.receptor)
    graph.add_node("clasificator", A.clasificator)
    graph.add_node("ceasornicar", A.ceasornicar)
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
    graph.add_edge("receptor", "clasificator")
    graph.add_edge("clasificator", "ceasornicar")
    for name in COLLECTORS:
        graph.add_edge("ceasornicar", name)
    graph.add_edge(COLLECTORS, "motor_reguli")
    graph.add_edge("motor_reguli", "outbox_aml")
    graph.add_edge("outbox_aml", "rambursare")
    # dezbaterea și recuperarea nu depind una de alta: rulează în paralel, după rambursare
    graph.add_edge("rambursare", "dezbatere")
    graph.add_edge("rambursare", "recuperare")
    graph.add_edge(["dezbatere", "recuperare"], "redactor")
    graph.add_edge("redactor", "sigiliu")
    graph.add_edge("sigiliu", END)
    return graph.compile(checkpointer=checkpointer)
