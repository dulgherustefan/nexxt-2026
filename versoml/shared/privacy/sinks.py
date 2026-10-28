"""Pașaportul datelor: verificarea destinațiilor (docs/05 §6.1 p. 4 și §6.4, zidul stratul 4)."""

from __future__ import annotations

from typing import Any

from versoml.contracts import Labels, Sink, Trust

_AML_CONF = ("aml", "aml-only")


def explain_sink(labels: Labels | dict[str, Any], sink: Sink | str) -> tuple[bool, str]:
    """(permis, motiv în română) pentru o valoare cu etichetele date și o destinație."""
    labels = labels if isinstance(labels, Labels) else Labels.model_validate(labels)
    sink = Sink(sink)
    if sink not in labels.sinks:
        allowed = ", ".join(s.value for s in labels.sinks) or "niciuna"
        return False, f"Destinația «{sink.value}» nu e în pașaportul valorii (permise: {allowed})."
    if labels.conf in _AML_CONF and sink in (Sink.CLIENT, Sink.LETTER, Sink.OSINT):
        return False, "Zidul: datele AML nu ajung niciodată în zona client, în scrisoare sau în surse publice."
    if labels.conf == "client" and sink is Sink.OSINT:
        return False, "Datele victimei nu pleacă niciodată spre surse publice; OSINT primește doar identificatori publici."
    if labels.trust is Trust.UNTRUSTED and sink in (Sink.LETTER, Sink.OSINT):
        return False, "Textul neîncrezut (al escrocului, al paginilor web) nu intră în scrisoare și nu pleacă spre surse publice."
    if sink is Sink.LLM and labels.conf == "client":
        return True, "Permis spre LLM doar pseudonimizat (PrivacyProxy.pseudonymize, apoi assert_llm_safe)."
    return True, "Permis de pașaportul datelor."


def check_sink(labels: Labels | dict[str, Any], sink: Sink | str) -> bool:
    """True dacă valoarea are voie să ajungă în destinația dată."""
    return explain_sink(labels, sink)[0]
