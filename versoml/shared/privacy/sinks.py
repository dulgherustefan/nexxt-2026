"""Pașaportul datelor: verificarea destinațiilor (docs/05 §6.1 p. 4 și §6.4, zidul stratul 4)."""

from __future__ import annotations

from typing import Any

from versoml.contracts import Labels, Sink, Trust

_AML_CONF = ("aml", "aml-only")


def explain_sink(labels: Labels | dict[str, Any], sink: Sink | str) -> tuple[bool, str]:
    """(allowed, reason) for a value with the given labels and a destination."""
    labels = labels if isinstance(labels, Labels) else Labels.model_validate(labels)
    sink = Sink(sink)
    if sink not in labels.sinks:
        allowed = ", ".join(s.value for s in labels.sinks) or "none"
        return False, f"The destination \"{sink.value}\" is not in this value's data passport (allowed: {allowed})."
    if labels.conf in _AML_CONF and sink in (Sink.CLIENT, Sink.LETTER, Sink.OSINT):
        return False, "The wall: AML data never reaches the client zone, a letter or a public source."
    if labels.conf == "client" and sink is Sink.OSINT:
        return False, "The victim's data never goes to public sources; OSINT gets public identifiers only."
    if labels.trust is Trust.UNTRUSTED and sink in (Sink.LETTER, Sink.OSINT):
        return False, "Untrusted text (from the fraudster or from web pages) never goes into a letter or to public sources."
    if sink is Sink.LLM and labels.conf == "client":
        return True, "Allowed to the LLM only when pseudonymized (PrivacyProxy.pseudonymize, then assert_llm_safe)."
    return True, "Allowed by the data passport."


def check_sink(labels: Labels | dict[str, Any], sink: Sink | str) -> bool:
    """True dacă valoarea are voie să ajungă în destinația dată."""
    return explain_sink(labels, sink)[0]
