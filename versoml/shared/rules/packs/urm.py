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
SRC = "docs/05 §3–5 (absent din catalogul docs/context)"


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


@rule("URM-01", title="Fără profilare pe trăsături personale: doar fapte obiective, decizie umană",
      basis="AI Act art. 5 alin. (1) lit. d); Ghidurile Comisiei C(2025) 884 (docs/05 §3)", confidence=S, pack="URM",
      source=SRC, zone=Zone.AML, questions=(Question.PISTA_AML, Question.RTS),
      params=("aml_prohibited_features",), exceptions=("URM_PROFILING_FEATURE",), tests=("URM-T1",))
def urm_01_objective_facts(a: AmlRuleContext, env: Env) -> Finding | None:
    """Evaluarea unui cont-cărăuș pe fapte obiective și verificabile, cu decizie umană, e permisă; un scor de
    „predispoziție” din date demografice nu e. Trăsăturile interzise (listă [U]) scot scorul din decizie."""
    if not a.features_used:
        return None
    bad = prohibited_features(a.features_used, env.p("aml_prohibited_features"))
    if bad:
        return Finding("URM-01", "URM_PROFILING_FEATURE",
                       f"Scorul folosește trăsături personale ({', '.join(bad)}): nu poate susține o propunere "
                       "(AI Act art. 5 alin. (1) lit. d)); se recalculează doar din fapte obiective.",
                       ("features_used",), data={"features": bad})
    return Finding("URM-01", "fapte_obiective",
                   "Scorul folosește doar fapte obiective despre conturi și tranzacții, fără trăsături personale.",
                   ("features_used",))


@rule("URM-02", title="Interdicția de tipping-off: spre client pleacă doar semnalul HOLD",
      basis="Legea 129/2019 art. 38 alin. (2); sancțiunea: art. 47 alin. (1) (docs/05 §3)", confidence=S, pack="URM",
      source=SRC, zone=Zone.AML, questions=(Question.PISTA_AML, Question.RTS, Question.RASPUNS_RECLAMATIE),
      exceptions=("AML_TIPPING_OFF_BAN",), tests=("URM-T2",))
def urm_02_tipping_off(a: AmlRuleContext, env: Env) -> Finding:
    """Clientul sau terții nu află nimic despre analiza AML sau despre un RTS. Spre zona client pleacă doar
    semnalul HOLD (da/nu), aprobat de un om; scrisorile trec prin filtrul zidului. Art. 47 alin. (1)
    pedepsește încălcarea cu închisoare de la 6 luni la 3 ani sau amendă."""
    return Finding("URM-02", "AML_TIPPING_OFF_BAN",
                   "Nicio informație despre analiză sau despre un raport nu ajunge la client sau la terți: spre zona "
                   "client pleacă doar semnalul HOLD (da/nu), aprobat de un om (art. 38 alin. (2); pedeapsa la "
                   "art. 47 alin. (1): închisoare de la 6 luni la 3 ani sau amendă).")


@rule("URM-03", title="Rambursare automată doar fără semnale de risc ale clientului",
      basis="propunere VersoML (docs/05 §3 și §5: „sub plafon și fără semnale”); semnalele sunt candidate pentru "
            "excepția PAY-03, nu motive de refuz", confidence=U, pack="URM", source=SRC,
      questions=(Question.RAMBURSARE_T1, Question.RECUPERARE_ESCROC),
      params=("client_fraud_signal_threshold", "prior_disputes_signal_threshold"), tests=("frauda_client",))
def urm_03_risk_signals(x: RuleContextExt, env: Env) -> Finding | None:
    """Scorul M2 peste prag sau prea multe contestații în 12 luni trimit rambursarea la om, tot în termenul T+1.
    Semnalele nu rețin și nu refuză: doar suspiciunea confirmată și comunicată autorității face asta (PAY-03)."""
    if not refund_track(x) or refund_withheld(x):
        return None
    signals = risk_signals(x, env)
    if signals:
        return Finding("URM-03", "semnale_de_risc",
                       "Semnale de risc, deci decide un om, tot în termenul T+1: "
                       + "; ".join(t for t, _ in signals) + ".",
                       tuple(f for _, fs in signals for f in fs), data={"signals": [t for t, _ in signals]})
    parts = [f"{x.prior_disputes_12m} contestații în 12 luni"]
    if x.client_fraud_score is not None:
        parts.insert(0, f"scorul M2 {fmt_num(x.client_fraud_score)}")
    return Finding("URM-03", "fara_semnale", "Fără semnale de risc ale clientului (" + ", ".join(parts) + ").",
                   ("client_fraud_score", "prior_disputes_12m"))


def str_indicators(a: AmlRuleContext, env: Env) -> list[tuple[str, tuple[str, ...]]]:
    """Indiciile obiective care fac o propunere de RTS (URM-04); scorul iese dacă folosește trăsături interzise."""
    out: list[tuple[str, tuple[str, ...]]] = []
    score_ok = not prohibited_features(a.features_used, env.p("aml_prohibited_features"))
    thr = env.p("aml_mule_score_threshold")
    if score_ok and a.top_mule_score is not None and a.top_mule_score >= thr:
        out.append((f"scorul M5 de cont-cărăuș este {fmt_num(a.top_mule_score)} (pragul [U]: {fmt_num(thr)})",
                    ("top_mule_score",)))
    if a.victims >= env.p("aml_min_linked_victims") and a.typologies:
        out.append((f"{a.victims} victime legate de același cont, cu tipologiile: {', '.join(a.typologies)}",
                    ("victims", "typologies")))
    return out


@rule("URM-04", title="Propunere de RTS din indicii obiective; decide analistul",
      basis="propunere VersoML (docs/05 §5 și §7.2); Legea 129/2019 art. 6 pentru obligația de raportare",
      confidence=U, pack="URM", source=SRC, zone=Zone.AML, questions=(Question.RTS,),
      params=("aml_mule_score_threshold", "aml_min_linked_victims", "aml_prohibited_features"), tests=("URM-T4",))
def urm_04_str_indicators(a: AmlRuleContext, env: Env) -> Finding | None:
    """Scorul de cont-cărăuș peste prag sau mai multe victime legate de același cont, cu o tipologie, fac o
    propunere de RTS pentru analist. Pragurile sunt [U]; analistul decide dacă suspiciunea există."""
    indicators = str_indicators(a, env)
    if not indicators:
        return None
    text = "Indicii obiective pentru un RTS, de confirmat de analist: " + "; ".join(t for t, _ in indicators)
    if a.osint_red_flags:
        text += f"; {a.osint_red_flags} semnale roșii OSINT"
    return Finding("URM-04", "propunere_rts", text + ".", tuple(f for _, fs in indicators for f in fs),
                   data={"indicators": [t for t, _ in indicators]})


__all__ = ["prohibited_features", "str_indicators"]
