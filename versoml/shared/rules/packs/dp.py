"""Pachetul DP: protecția datelor și deciziile automate (docs/context/11 §2.7).

Ambele reguli sunt gărzi aplicate de motor după compunerea deciziilor:
- DP-02 (GDPR art. 22, CJUE SCHUFA C-634/21): nicio decizie defavorabilă exclusiv automată; un scor (M2)
  pe care decizia s-ar sprijini e doar semnal pentru om. Parametrul `require_human_for_unfavourable` e blocat.
- DP-03 (CJUE C-203/22): fiecare decizie are regula, temeiul și explicația.
"""

from __future__ import annotations

from versoml.contracts import Confidence, Decision, DisputeType, Question, RationaleLine, Verdict

from ..context import RuleContextExt
from ..facts import cite
from ..registry import rule

S = Confidence.S
SRC = "docs/context/11 §2.7"

UNFAVOURABLE = {
    Question.RAMBURSARE_T1: {Verdict.RESPINGE_TARDIV, Verdict.EXCEPTIE_FRAUDA_CLIENT},
    Question.RECUPERARE_CLIENT: {Verdict.RECUPERARE_PROPUSA},
}


def is_unfavourable(decision: Decision, x: RuleContextExt) -> bool:
    """Defavorabil pentru client: respingerea, reținerea, recuperarea de la client și „T+1 nu se aplică” la APP
    (clientul pierde regimul de rambursare)."""
    if decision.decision in UNFAVOURABLE.get(decision.question, set()):
        return True
    return (decision.question == Question.RAMBURSARE_T1 and decision.decision == Verdict.NU_SE_APLICA_T1
            and (x.dispute_type == DisputeType.APP or x.credit_fraud))


@rule("DP-02", title="Nicio decizie defavorabilă exclusiv automată; scorul e doar semnal pentru om",
      basis="GDPR art. 22; CJUE C-634/21 SCHUFA (7.12.2023)", confidence=S, pack="DP", source=SRC, kind="garda",
      questions=(Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT, Question.RASPUNS_RECLAMATIE),
      params=("require_human_for_unfavourable",), exceptions=("DP_HUMAN_REVIEW_REQUIRED",), tests=("TC-38",))
def apply_human_review(decision: Decision, x: RuleContextExt, *, reason: str | None = None) -> Decision:
    """O decizie defavorabilă (respingere, reținere, recuperare de la client, APP) o semnează un om. Garda nu
    schimbă verdictul; marchează `requires_human` și adaugă temeiul."""
    if not (is_unfavourable(decision, x) or reason):
        return decision
    rule_ids = decision.rule_ids if "DP-02" in decision.rule_ids else [*decision.rule_ids, "DP-02"]
    text = reason or ("Decizia e defavorabilă clientului: o semnează un om, cu informațiile reale ca să se poată "
                      "abate (GDPR art. 22).")
    cites = cite(x, ["client_fraud_score"]) if reason else []
    return decision.model_copy(update={
        "requires_human": True, "decided_by": "rules+human", "rule_ids": rule_ids,
        "rationale": [*decision.rationale, RationaleLine(text=text, cites=cites)],
    })


@rule("DP-03", title="Fiecare decizie are regula, temeiul și explicația", basis="CJUE C-203/22 Dun & Bradstreet "
      "Austria (27.02.2025)", confidence=S, pack="DP", source=SRC, kind="garda",
      exceptions=("DP_EXPLANATION_MISSING",), tests=("invarianti",))
def explanation_complete(decision: Decision) -> bool:
    """Persoana primește o explicație concisă și inteligibilă a procedurii aplicate: fără ID de regulă sau fără
    explicație, decizia nu pleacă (merge la om cu `DP_EXPLANATION_MISSING`)."""
    return bool(decision.rule_ids) and bool(decision.rationale) and all(r.text.strip() for r in decision.rationale)


__all__ = ["UNFAVOURABLE", "apply_human_review", "explanation_complete", "is_unfavourable"]
