"""Pachetul DP: protecția datelor și deciziile automate (docs/context/11 §2.7).

Ambele reguli sunt gărzi aplicate de motor după compunerea deciziilor:
- DP-02 (GDPR art. 22, CJUE SCHUFA C-634/21): nicio decizie defavorabilă exclusiv automată; un scor (M2)
  pe care decizia s-ar sprijini e doar semnal pentru om. Parametrul `require_human_for_unfavourable` e blocat.
- DP-03 (CJUE C-203/22): fiecare decizie are regula, temeiul și explicația.
"""

from __future__ import annotations

from versoml.contracts import Confidence, Decision, DisputeType, Question, RationaleLine, Verdict

from ..context import RuleContextExt
from ..facts import Env, cite
from ..registry import Finding, rule

S = Confidence.S
SRC = "docs/context/11 §2.7"

UNFAVOURABLE = {
    Question.RAMBURSARE_T1: {Verdict.RESPINGE_TARDIV, Verdict.EXCEPTIE_FRAUDA_CLIENT},
    Question.RECUPERARE_CLIENT: {Verdict.RECUPERARE_PROPUSA},
}


def is_unfavourable(decision: Decision, x: RuleContextExt) -> bool:
    """Defavorabil pentru client: respingerea, reținerea, recuperarea de la client și „T+1 nu se aplică” la APP
    sau când clientul spune că nu a autorizat plata (clientul pierde regimul de rambursare)."""
    if decision.decision in UNFAVOURABLE.get(decision.question, set()):
        return True
    return (decision.question == Question.RAMBURSARE_T1 and decision.decision == Verdict.NU_SE_APLICA_T1
            and (x.dispute_type == DisputeType.APP or x.credit_fraud or x.customer_claims_unauthorised is True))


@rule("DP-02", title="No adverse decision is fully automated; the score is only a signal for a human",
      basis="GDPR art. 22; CJEU ruling C-634/21 SCHUFA (7 Dec 2023)", confidence=S, pack="DP", source=SRC,
      kind="garda", questions=(Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT, Question.RASPUNS_RECLAMATIE),
      params=("require_human_for_unfavourable",), exceptions=("DP_HUMAN_REVIEW_REQUIRED",), tests=("TC-38",))
def apply_human_review(decision: Decision, x: RuleContextExt, *, reason: str | None = None) -> Decision:
    """A human signs off an adverse decision (rejection, hold, recovery from the customer, APP). The guard does
    not change the verdict. It sets `requires_human` and adds the legal basis."""
    if not (is_unfavourable(decision, x) or reason):
        return decision
    rule_ids = decision.rule_ids if "DP-02" in decision.rule_ids else [*decision.rule_ids, "DP-02"]
    text = reason or ("The decision is adverse to the customer. A human with the full facts signs it off and can "
                      "override it (GDPR art. 22).")
    cites = cite(x, ["client_fraud_score"]) if reason else []
    return decision.model_copy(update={
        "requires_human": True, "decided_by": "rules+human", "rule_ids": rule_ids,
        "rationale": [*decision.rationale, RationaleLine(text=text, cites=cites)],
    })


VULNERABILITY_LABELS = {"varsta": "age", "boala": "illness", "doliu": "bereavement", "constrangere": "coercion",
                        "confuzie": "confusion"}


@rule("DP-04", title="A vulnerable customer always goes to a person and is never refused on gross negligence",
      basis="Good practice: UK PSR PS25/5 (vulnerability overrides the consumer standard of caution); PSR recital 82 "
            "(Council text ST-8221-2026-INIT, future law)", confidence=Confidence.U, pack="DP", source=SRC,
      questions=(Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT), exceptions=("DP_VULNERABLE_CUSTOMER",),
      tests=("VU-01",))
def dp_04_vulnerable_customer(x: RuleContextExt, env: Env) -> Finding | None:
    """The complaint shows signs of vulnerability (age, illness, bereavement, coercion, confusion), each backed by an
    exact quote. Every decision on the case goes to a person, and gross negligence is never a ground to recover the
    loss from the customer. This is good practice, not a statutory duty under Law 209/2019."""
    if not x.vulnerability_signals:
        return None
    listed = ", ".join(VULNERABILITY_LABELS.get(k, k) for k in x.vulnerability_signals)
    return Finding("DP-04", "DP_VULNERABLE_CUSTOMER",
                   f"The complaint shows signs of vulnerability ({listed}). A person handles the case, and gross "
                   "negligence is not used against the customer.", ("vulnerability_signals",),
                   data={"signals": list(x.vulnerability_signals)})


@rule("DP-03", title="Every decision states its rule, legal basis and explanation", basis="CJEU ruling C-203/22 "
      "Dun & Bradstreet Austria (27 Feb 2025)", confidence=S, pack="DP", source=SRC, kind="garda",
      exceptions=("DP_EXPLANATION_MISSING",), tests=("invarianti",))
def explanation_complete(decision: Decision) -> bool:
    """The person gets a concise, intelligible explanation of the procedure applied. Without a rule ID or an
    explanation, the decision does not go out (it goes to a human with `DP_EXPLANATION_MISSING`)."""
    return bool(decision.rule_ids) and bool(decision.rationale) and all(r.text.strip() for r in decision.rationale)


__all__ = ["UNFAVOURABLE", "apply_human_review", "explanation_complete", "is_unfavourable"]
