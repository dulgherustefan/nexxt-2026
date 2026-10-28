"""Filtrul scrisorilor către client (zidul, stratul 5): termeni interziși + canary + date personale.

Orice potrivire blochează scrisoarea și o trimite la un om. Un clasificator opțional
(de ex. Haiku) poate doar adăuga blocări, niciodată nu poate debloca una deterministă.
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

# Datele personale care nu au ce căuta brute într-o scrisoare (se maschează: „RO49 **** 0000")
BLOCKING_PII = ("CNP", "CARD", "IBAN")

Classifier = Callable[[str], bool]
_default_classifier: Classifier | None = None
_default_registry: CanaryRegistry | None = None


def register_classifier(classifier: Classifier | None) -> None:
    """Clasificatorul folosit implicit de `check_letter` (None îl dezactivează)."""
    global _default_classifier
    _default_classifier = classifier


def _registry() -> CanaryRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = CanaryRegistry()
    return _default_registry


def check_letter(
    text: str,
    *,
    case_id: str | None = None,
    classifier: Classifier | None = None,
    registry: CanaryRegistry | None = None,
    proxy: PrivacyProxy | None = None,
) -> FilterResult:
    """Verifică o scrisoare. `passed=False` înseamnă: nu pleacă, merge la om."""
    text = normalize_ro(text or "")
    reasons: list[str] = []
    hits = find_terms(text)
    canaries = (registry if registry is not None else _registry()).scan(text)
    # Cu un canary în text, fragmentele ar copia conținut AML în jurnale: atunci dăm doar eticheta
    for hit in hits:
        where = "" if canaries else f", în fragmentul „{snippet(text, hit.start, hit.end)}”"
        reasons.append(f"Termen interzis «{hit.label}»: {hit.why}{where}.")
    if canaries:
        reasons.append(f"Scrisoarea conține {canaries} token(uri) canary din dosarele AML: conținut AML scurs.")

    pii_findings = []
    for found in (proxy or get_proxy()).scan(text):
        if found["pii"] and found["type"] in BLOCKING_PII:
            pii_findings.append(f"{found['type']}: {found['masked']}")
    if pii_findings:
        reasons.append("Date personale brute în scrisoare (se scriu mascat): " + ", ".join(pii_findings) + ".")

    flag = False
    classify = classifier or _default_classifier
    if classify is not None:
        try:
            flag = bool(classify(text))
        except Exception as exc:  # noqa: BLE001 - un clasificator căzut nu lasă scrisoarea să treacă
            flag = True
            log.warning("Zid: clasificatorul scrisorii a eșuat (%s)", type(exc).__name__)
            reasons.append("Clasificatorul nu a putut verifica scrisoarea; merge la om.")
        else:
            if flag:
                reasons.append("Clasificatorul a semnalat o posibilă dezvăluire a unei analize AML (tipping-off).")

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
        # În jurnal intră doar etichetele, fără fragmente din scrisoare
        summary = [f"Termen interzis «{label}»." for label in blocked_terms]
        if canaries:
            summary.append(f"{canaries} token(uri) canary din dosarele AML.")
        if pii_findings:
            summary.append("Date personale brute: " + ", ".join(p.split(":")[0] for p in pii_findings) + ".")
        if flag:
            summary.append("Semnalat de clasificator.")
        journal.record(5, "letter_block", case_id=case_id, reasons=summary, terms=blocked_terms,
                       detail={"canaries": canaries, "pii": len(pii_findings), "classifier": flag})
    return result
