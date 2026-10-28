"""The check on letters to customers (the wall, layer 5): forbidden terms, canary tokens and personal data.

Any match blocks the letter and sends it to a person. An optional classifier (Haiku, say) can only add blocks;
it can never unblock a deterministic one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from versoml.contracts import FilterResult
from versoml.shared.privacy import PrivacyProxy, get_proxy, normalize_ro
from versoml.wall import journal
from versoml.wall.canary import CanaryRegistry
from versoml.wall.terms import find_terms, labels, snippet

log = logging.getLogger("versoml.wall")

# Personal data that must never appear raw in a letter (it is written masked: "RO49 **** 0000")
BLOCKING_PII = ("CNP", "CARD", "IBAN")

Classifier = Callable[[str], bool]
_default_classifier: Classifier | None = None
_default_registry: CanaryRegistry | None = None


def register_classifier(classifier: Classifier | None) -> None:
    """The classifier `check_letter` uses by default (None turns it off)."""
    global _default_classifier
    _default_classifier = classifier


def _registry() -> CanaryRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = CanaryRegistry()
    return _default_registry


def _tokens(n: int) -> str:
    return f"{n} canary {'token' if n == 1 else 'tokens'}"


def check_letter(
    text: str,
    *,
    case_id: str | None = None,
    classifier: Classifier | None = None,
    registry: CanaryRegistry | None = None,
    proxy: PrivacyProxy | None = None,
) -> FilterResult:
    """Checks a letter. `passed=False` means it doesn't go out: a person looks at it."""
    text = normalize_ro(text or "")
    reasons: list[str] = []
    hits = find_terms(text)
    canaries = (registry if registry is not None else _registry()).scan(text)
    # With a canary in the text, quoting fragments would copy AML content into the logs: then only the label
    for hit in hits:
        where = "" if canaries else f", in “{snippet(text, hit.start, hit.end).rstrip('.')}”"
        reasons.append(f"Forbidden term “{hit.label}”: it {hit.why}{where}.")
    if canaries:
        reasons.append(f"The letter contains {_tokens(canaries)} from the AML files: AML content has leaked.")

    pii_findings = []
    for found in (proxy or get_proxy()).scan(text):
        if found["pii"] and found["type"] in BLOCKING_PII:
            pii_findings.append(f"{found['type']}: {found['masked']}")
    if pii_findings:
        reasons.append("Raw personal data in the letter (write it masked): " + ", ".join(pii_findings) + ".")

    flag = False
    classify = classifier or _default_classifier
    if classify is not None:
        try:
            flag = bool(classify(text))
        except Exception as exc:  # noqa: BLE001 - a broken classifier doesn't let the letter through
            flag = True
            log.warning("Wall: the letter classifier failed (%s)", type(exc).__name__)
            reasons.append("The classifier could not check the letter, so it goes to a person.")
        else:
            if flag:
                reasons.append("The classifier flagged a possible disclosure of an AML review (tipping-off).")

    blocked_terms = labels(hits)
    result = FilterResult(
        passed=not (blocked_terms or canaries or pii_findings or flag),
        blocked_terms=blocked_terms,
        canaries_found=canaries,
        classifier_flag=flag,
        pii_findings=pii_findings,
        reasons=reasons,
        term_spans=[{"start": h.start, "end": h.end, "label": h.label} for h in hits],
    )
    if not result.passed:
        # The journal gets the labels only, never fragments of the letter
        summary = [f"Forbidden term “{label}”." for label in blocked_terms]
        if canaries:
            summary.append(f"{_tokens(canaries)[0].upper()}{_tokens(canaries)[1:]} from the AML files.")
        if pii_findings:
            summary.append("Raw personal data: " + ", ".join(p.split(":")[0] for p in pii_findings) + ".")
        if flag:
            summary.append("Flagged by the classifier.")
        journal.record(5, "letter_block", case_id=case_id, reasons=summary, terms=blocked_terms,
                       detail={"canaries": canaries, "pii": len(pii_findings), "classifier": flag})
    return result
