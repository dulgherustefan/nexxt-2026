"""Pachetul URM (EXTENSIE): reguli de produs VersoML, absente din catalogul docs/context.

Vin din docs/05 §3–5 (corecturile verificate, tabelul de reguli, „regula de aur”) sau sunt propuneri:
- URM-01 [S] AI Act art. 5 alin. (1) lit. d): fără scoruri din trăsături personale; doar fapte obiective.
- URM-02 [S] Legea 129/2019 art. 38 alin. (2): interdicția de tipping-off; pedeapsa la art. 47 alin. (1).
- URM-03 [U] semnalele de risc care trimit rambursarea la om (pragurile sunt parametri).
- URM-04 [U] propunerea de RTS din indicii obiective (pragurile sunt parametri); decide analistul.
"""

from __future__ import annotations

import re
import unicodedata

from versoml.contracts import Confidence, Question, Zone

from ..context import AmlRuleContext, RuleContextExt
from ..facts import Env, fmt_num, refund_track, refund_withheld, risk_signals
from ..registry import Finding, rule

S, U = Confidence.S, Confidence.U
SRC = "docs/05 §3–5 (not in the docs/context catalog)"


def _tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return [t for t in re.split(r"[^a-z0-9]+", plain) if t]


OBJECT_PREFIXES = {"account", "cont", "card", "device", "dispozitiv", "domain", "domeniu"}


def prohibited_features(features: list[str], prohibited: list[str]) -> list[str]:
    """Trăsăturile din scor care sunt trăsături personale (potrivire pe cuvinte întregi, fără diacritice).

    Vechimea unui obiect („account_age_days”, vârsta contului) e un fapt obiectiv, nu vârsta unei persoane:
    termenul interzis precedat de numele obiectului nu se socotește trăsătură personală.
    """
    hits = []
    for feature in features:
        toks = _tokens(feature)
        for term in prohibited:
            tt = _tokens(term)
            if tt and any(toks[i:i + len(tt)] == tt and not (i > 0 and toks[i - 1] in OBJECT_PREFIXES)
                          for i in range(len(toks) - len(tt) + 1)):
                hits.append(feature)
                break
    return hits


@rule("URM-01", title="No profiling on personal traits: objective facts only, human decision",
      basis="AI Act, art. 5(1)(d); Commission Guidelines C(2025) 884 (docs/05 §3)", confidence=S, pack="URM",
      source=SRC, zone=Zone.AML, questions=(Question.PISTA_AML, Question.RTS),
      params=("aml_prohibited_features",), exceptions=("URM_PROFILING_FEATURE",), tests=("URM-T1",))
def urm_01_objective_facts(a: AmlRuleContext, env: Env) -> Finding | None:
    """Assessing a money mule account on objective, verifiable facts, with a human decision, is allowed. A
    “predisposition” score built from demographic data is not. Prohibited traits (a [U] list) take the score
    out of the decision."""
    if not a.features_used:
        return None
    bad = prohibited_features(a.features_used, env.p("aml_prohibited_features"))
    if bad:
        return Finding("URM-01", "URM_PROFILING_FEATURE",
                       f"The score uses personal traits ({', '.join(bad)}), so it cannot support a proposal "
                       "(AI Act, art. 5(1)(d)). It must be recalculated from objective facts only.",
                       ("features_used",), data={"features": bad})
    return Finding("URM-01", "fapte_obiective",
                   "The score uses only objective facts about accounts and transactions, with no personal traits.",
                   ("features_used",))


@rule("URM-02", title="Tipping-off ban: only the HOLD signal goes to the client zone",
      basis="Law 129/2019, art. 38(2); penalty: art. 47(1) (docs/05 §3)", confidence=S, pack="URM",
      source=SRC, zone=Zone.AML, questions=(Question.PISTA_AML, Question.RTS, Question.RASPUNS_RECLAMATIE),
      exceptions=("AML_TIPPING_OFF_BAN",), tests=("URM-T2",))
def urm_02_tipping_off(a: AmlRuleContext, env: Env) -> Finding:
    """The customer and third parties learn nothing about the AML analysis or an STR. Only the HOLD signal
    (yes/no), approved by a human, goes to the client zone, and letters pass through the wall filter.
    Art. 47(1) punishes a breach with 6 months to 3 years in prison, or a fine."""
    return Finding("URM-02", "AML_TIPPING_OFF_BAN",
                   "No information about the analysis or a report reaches the customer or third parties. Only the "
                   "HOLD signal (yes/no), approved by a human, goes to the client zone (Law 129/2019, art. 38(2); "
                   "penalty under art. 47(1): 6 months to 3 years in prison, or a fine).")


@rule("URM-03", title="Automatic refund only when the customer shows no risk signals",
      basis="VersoML proposal (docs/05 §3 and §5: “under the cap and no signals”); signals are candidates for the "
            "PAY-03 exception, not grounds for refusal", confidence=U, pack="URM", source=SRC,
      questions=(Question.RAMBURSARE_T1, Question.RECUPERARE_ESCROC),
      params=("client_fraud_signal_threshold", "prior_disputes_signal_threshold"), tests=("frauda_client",))
def urm_03_risk_signals(x: RuleContextExt, env: Env) -> Finding | None:
    """An M2 score above the threshold, or too many disputes in 12 months, sends the refund to a human, still
    within the refund deadline. Signals do not withhold or refuse anything. Only a confirmed suspicion reported
    to the authority does that (PAY-03)."""
    if not refund_track(x) or refund_withheld(x):
        return None
    signals = risk_signals(x, env)
    if signals:
        return Finding("URM-03", "semnale_de_risc",
                       "Risk signals, so a human decides, still within the refund deadline: "
                       + "; ".join(t for t, _ in signals) + ".",
                       tuple(f for _, fs in signals for f in fs), data={"signals": [t for t, _ in signals]})
    parts = [f"{x.prior_disputes_12m} disputes in 12 months"]
    if x.client_fraud_score is not None:
        parts.insert(0, f"M2 score {fmt_num(x.client_fraud_score)}")
    return Finding("URM-03", "fara_semnale", "No customer risk signals (" + ", ".join(parts) + ").",
                   ("client_fraud_score", "prior_disputes_12m"))


def str_indicators(a: AmlRuleContext, env: Env) -> list[tuple[str, tuple[str, ...]]]:
    """Indiciile obiective care fac o propunere de RTS (URM-04); scorul iese dacă folosește trăsături interzise."""
    out: list[tuple[str, tuple[str, ...]]] = []
    score_ok = not prohibited_features(a.features_used, env.p("aml_prohibited_features"))
    thr = env.p("aml_mule_score_threshold")
    if score_ok and a.top_mule_score is not None and a.top_mule_score >= thr:
        out.append((f"the M5 money mule score is {fmt_num(a.top_mule_score)} ([U] threshold: {fmt_num(thr)})",
                    ("top_mule_score",)))
    if a.victims >= env.p("aml_min_linked_victims") and a.typologies:
        out.append((f"{a.victims} victims linked to the same account, with typologies: {', '.join(a.typologies)}",
                    ("victims", "typologies")))
    return out


@rule("URM-04", title="STR proposal from objective indicators; the analyst decides",
      basis="VersoML proposal (docs/05 §5 and §7.2); Law 129/2019, art. 6 for the reporting duty",
      confidence=U, pack="URM", source=SRC, zone=Zone.AML, questions=(Question.RTS,),
      params=("aml_mule_score_threshold", "aml_min_linked_victims", "aml_prohibited_features"), tests=("URM-T4",))
def urm_04_str_indicators(a: AmlRuleContext, env: Env) -> Finding | None:
    """A money mule score above the threshold, or several victims linked to the same account with a typology,
    trigger an STR proposal for the analyst. The thresholds are [U]. The analyst decides whether there is a
    suspicion."""
    indicators = str_indicators(a, env)
    if not indicators:
        return None
    text = "Objective indicators for an STR, for the analyst to confirm: " + "; ".join(t for t, _ in indicators)
    if a.osint_red_flags:
        text += f"; {a.osint_red_flags} OSINT red flags"
    return Finding("URM-04", "propunere_rts", text + ".", tuple(f for _, fs in indicators for f in fs),
                   data={"indicators": [t for t, _ in indicators]})


__all__ = ["prohibited_features", "str_indicators"]
