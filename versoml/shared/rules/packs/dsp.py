"""Pachetul DSP: dispute card, scheme Visa/Mastercard și procesul emitentului (docs/context/14).

Valorile [P] din Visa Core Rules (18.04.2026) sunt constante aici, cu sursa lângă ele. Valorile [U] și
termenele Mastercard (în conflict între surse) sunt parametri. Ordinea regulilor contează doar pentru lista
de hit-uri: DSP-52 (flagul de recuperabilitate) apare înaintea celorlalte reguli de schemă.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from versoml.contracts import Confidence, Deadline, DisputeType, Question

from ..calendar_ro import end_of_day, local_date, to_local
from ..context import GuardResult, RuleContextExt
from ..facts import (
    Env, card_present, card_scheme, fmt_d, fmt_dt, fmt_money, fmt_num, is_card, is_unauthorised, processing_date,
    refund_anchor, refund_due, refund_track, refund_withheld, risk_signals, to_ron, visa_condition,
)
from ..registry import Finding, rule

P, S, U = Confidence.P, Confidence.S, Confidence.U
SRC = "docs/context/14"
Q_T1, Q_CLIENT, Q_ESCROC, Q_ANSWER = (Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT,
                                      Question.RECUPERARE_ESCROC, Question.RASPUNS_RECLAMATIE)

# ---------------------------------------------------------------- constante Visa (Core Rules 18.04.2026) [P]

VISA_CONDITIONS: dict[str, str] = {          # docs/context/14 §5.1, denumirile din Core Rules
    "10.1": "EMV Liability Shift Counterfeit", "10.2": "EMV Liability Shift Non-Counterfeit",
    "10.3": "Other Fraud – Card-Present", "10.4": "Other Fraud – Card-Absent",
    "10.5": "Visa Fraud Monitoring Program",
    "11.1": "Card Recovery Bulletin", "11.2": "Declined Authorization", "11.3": "No Authorization/Late Presentment",
    "12.2": "Incorrect Transaction Code", "12.3": "Incorrect Currency", "12.4": "Incorrect Account Number",
    "12.5": "Incorrect Amount", "12.6": "Duplicate Processing/Paid by Other Means", "12.7": "Invalid Data",
    "13.1": "Merchandise/Services Not Received", "13.2": "Cancelled Recurring", "13.3": "Not as Described/Defective",
    "13.4": "Counterfeit Merchandise", "13.5": "Misrepresentation", "13.6": "Credit Not Processed",
    "13.7": "Cancelled Merchandise/Services", "13.8": "Original Credit Transaction Not Accepted",
    "13.9": "Non-Receipt of Cash at an ATM",
}
# Subcodurile 12.6.x nu sunt în docs/context: cerute de produs, marcate [U] (de verificat în Core Rules).
VISA_SUBCONDITIONS: dict[str, tuple[str, str]] = {"12.6.1": ("12.6", "Duplicate Processing"),
                                                   "12.6.2": ("12.6", "Paid by Other Means")}
VISA_104_OPEN_DAYS = 120          # Table 11-29 [P]
VISA_131_OPEN_DAYS = 120          # Table 11-92 [P]
VISA_131_CAP_DAYS = 540           # Table 11-92 [P]
VISA_131_WAIT_DAYS = 15           # Table 11-92 [P]; ancora [U]
VISA_104_DISPUTE_CAP = 35         # Table 11-28 [P]; ce se numără [U]
VISA_FRAUD_RPT_TXN_DAYS = 60      # §1.9.4.3 [P]
VISA_FRAUD_RPT_NOTICE_DAYS = 30   # §1.9.4.3 [P]; lectura [U]
CE3_V2026_FROM = date(2026, 10, 24)   # CE3.0 cu mai mulți comercianți; device ID + fingerprint = un element
MC_CODES = {DisputeType.NEAUTORIZATA: "4837", DisputeType.DISPUTA_COMERCIANT: "4853",
            DisputeType.EROARE_PROCESARE: "4834"}   # DSP-40 [S]

# Etapele Visa: (zile, ancora, marcaj). Table 11-1 (alocare, 10–11) și 11-2 (colaborare, 12–13).
VISA_STAGES: dict[str, dict[str, tuple[int, str, Confidence]]] = {
    "alocare": {
        "prearbitraj_acquirer": (30, "data procesării disputei", P),
        "raspuns_emitent_prearbitraj": (30, "pre-arbitrajul (unitate neprecizată)", U),
        "arbitraj_acquirer": (10, "răspunsul la pre-arbitraj", P),
    },
    "colaborare": {
        "raspuns_disputa_acquirer": (30, "disputa (unitate neprecizată)", U),
        "prearbitraj_emitent": (30, "Dispute Response (unitate neprecizată)", U),
        "raspuns_acquirer_prearbitraj": (30, "pre-arbitrajul (unitate neprecizată)", U),
        "arbitraj_emitent": (10, "răspunsul acquirer-ului (unitate neprecizată)", U),
    },
}


def is_valid_condition(code: str) -> bool:
    return code in VISA_CONDITIONS or code in VISA_SUBCONDITIONS


def condition_name(code: str) -> str:
    if code in VISA_SUBCONDITIONS:
        return VISA_SUBCONDITIONS[code][1]
    return VISA_CONDITIONS.get(code, "?")


def _eci(x: RuleContextExt) -> str | None:
    return x.eci.strip().zfill(2) if x.eci else None


def classification_ambiguous(x: RuleContextExt, env: Env) -> bool:
    return bool(x.classification_ambiguous or env.flags.get("classification_ambiguous"))


# ---------------------------------------------------------------- calculatoare de schemă


@rule("DSP-22", title="Ziua procesării evenimentului anterior nu se numără", basis="Visa Core Rules §11.2.1",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator", tests=("DT-01", "DT-09", "DT-13"))
def visa_due(anchor: date, days: int) -> date:
    """Termenul Visa: ancora + n zile calendaristice (ziua ancorei nu se numără)."""
    return anchor + timedelta(days=days)


@rule("DSP-23", title="Fără acțiune la termen, ciclul se închide; alertă înainte de termen",
      basis="Visa Core Rules §11.2.1", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      params=("scheme_alert_lead_days",), exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-14",))
def scheme_deadline_status(due: date, as_of: datetime | date, lead_days: int) -> tuple[str, int]:
    """Starea unui termen de schemă: (cod, zile rămase). Ratarea termenului = pierdere automată."""
    left = (due - local_date(as_of)).days
    if left < 0:
        return "termen_expirat", left
    if left <= lead_days:
        return "DSP_SCHEME_DEADLINE_AT_RISK", left
    return "in_termen", left


@rule("DSP-33", title="Categoriile 10–11: pre-arbitraj acquirer, răspuns emitent, arbitraj",
      basis="Visa Core Rules Table 11-1", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-13", "DT-14"))
def visa_allocation_stage_due(stage: str, anchor: date) -> tuple[date, Confidence]:
    """Termenul unei etape din fluxul de alocare (fraudă, autorizare). O unitate e neprecizată [U]."""
    days, _, conf = VISA_STAGES["alocare"][stage]
    return visa_due(anchor, days), conf


@rule("DSP-34", title="Categoriile 12–13: Dispute Response, pre-arbitraj emitent, răspuns, arbitraj",
      basis="Visa Core Rules Table 11-2", confidence=P, pack="DSP", source=f"{SRC} §5.2", kind="calculator",
      exceptions=("DSP_SCHEME_DEADLINE_AT_RISK",), tests=("DT-09",))
def visa_collaboration_stage_due(stage: str, anchor: date) -> tuple[date, Confidence]:
    """Termenul unei etape din fluxul de colaborare (erori de procesare, dispute de consum); unități [U]."""
    days, _, conf = VISA_STAGES["colaborare"][stage]
    return visa_due(anchor, days), conf


def visa_fraud_report_due(txn_on: date, notified_on: date, mode: str | None) -> tuple[date, bool]:
    """DSP-25: (termen, lecturi concordante). 60 de zile de la tranzacție / 30 de la notificare, dacă vine
    mai târziu; lectura e [U]. Fără mod setat: dacă lecturile diferă, data mai devreme."""
    d60 = txn_on + timedelta(days=VISA_FRAUD_RPT_TXN_DAYS)
    d30 = notified_on + timedelta(days=VISA_FRAUD_RPT_NOTICE_DAYS)
    by_max = max(d60, d30)
    by_after = d30 if notified_on > d60 else d60
    if mode == "max":
        return by_max, True
    if mode == "after_day_60":
        return by_after, True
    return (by_max, True) if by_max == by_after else (min(by_max, by_after), False)


@dataclass(frozen=True)
class DisputeWindow:
    condition: str
    due: date
    earliest: date | None
    verified: bool
    anchor_known: bool
    expired: bool


def visa_dispute_window(x: RuleContextExt, env: Env) -> DisputeWindow | None:
    """Termenul emitentului pentru condiția Visa a cazului (DSP-24, §5.4)."""
    cond = visa_condition(x)
    if cond is None or not is_valid_condition(cond):
        return None
    proc, known = processing_date(x)
    earliest = None
    if cond == "10.4":
        due, verified = visa_due(proc, VISA_104_OPEN_DAYS), True
    elif cond == "13.1":
        base = max(proc, x.expected_delivery_date) if x.expected_delivery_date else proc
        due, verified = min(visa_due(base, VISA_131_OPEN_DAYS), visa_due(proc, VISA_131_CAP_DAYS)), True
        if x.expected_delivery_date is None:
            anchor = proc if env.p("visa_131_wait_anchor") == "processing_date" else local_date(x.executed_at)
            earliest = visa_due(anchor, VISA_131_WAIT_DAYS)
    else:
        due, verified = visa_due(proc, env.p("visa_other_open_days")), False
    return DisputeWindow(cond, due, earliest, verified, known, local_date(x.now) > due)


def chargeback_recoverable(x: RuleContextExt, env: Env) -> tuple[str, list[str], str | None]:
    """Flagul DSP-52 (docs/context/14 §6.1): (DA / NU / INCERT, regulile care au decis, codul de motiv).
    Ordinea testelor e fixă; fiecare NU sau INCERT citează regula care a decis."""
    if x.existing_dispute_for_txn:
        return "NU", ["DSP-21"], None
    if x.purchase_type == "crypto_nft" and x.cardholder_participated:
        return "NU", ["DSP-29"], None
    if x.dispute_type == DisputeType.APP:
        return "NU", ["PAY-12"], None
    if x.preauth_release_late:
        return "NU", ["PAY-09"], None
    if card_scheme(x, env) == "mastercard":
        return "INCERT", ["DSP-42", "DSP-43"], MC_CODES.get(x.dispute_type)
    cond = visa_condition(x)
    if cond is not None and not is_valid_condition(cond):
        return "INCERT", ["DSP-20"], cond
    if is_unauthorised(x):
        if card_present(x) is not False:
            return "INCERT", ["DSP-52"], None
        window = visa_dispute_window(x, env)
        if window and window.expired:
            return "NU", ["DSP-24"], "10.4"
        if x.prior_disputes_120d is not None and x.prior_disputes_120d > VISA_104_DISPUTE_CAP:
            return "NU", ["DSP-26"], "10.4"
        if x.prior_disputes_120d is None and x.prior_disputes_12m > VISA_104_DISPUTE_CAP:
            return "INCERT", ["DSP-26"], "10.4"
        if _eci(x) == "05" and x.cavv_present is True and x.visa_secure_auth_confirmation is not False:
            return "NU", ["DSP-27"], "10.4"
        if x.wallet_token and x.tavv_present and x.cvm_approved:
            return "NU", ["DSP-28"], "10.4"
        if x.ce3_met:
            return "NU", ["DSP-30"], "10.4"
        if _eci(x) == "06":
            return "INCERT", ["DSP-31"], "10.4"
        return "DA", [], "10.4"
    if cond is None:
        return "INCERT", ["DSP-20"], None
    window = visa_dispute_window(x, env)
    if window and window.expired:
        return "NU", ["DSP-24"], cond
    blocking = []
    if window and not window.verified:
        blocking.append("DSP-24")
    if cond.startswith("13.") and cond != "13.9" and x.merchant_contact_proof is not True:
        blocking.append("DSP-53")
    return ("INCERT" if blocking else "DA"), blocking, cond


# ---------------------------------------------------------------- pista A: rambursarea (proces)


@rule("DSP-58", title="T+1 curge de la cea mai devreme dintre constatarea băncii și notificarea clientului",
      basis="Legea 209/2019 art. 173 („după constatare sau notificare”); inferență din note", confidence=U,
      pack="DSP", source=f"{SRC} §7.4", questions=(Q_T1,), params=("refund_anchor_mode",), tests=("DT-19",))
def dsp_58_refund_anchor(x: RuleContextExt, env: Env) -> Finding | None:
    """Ancora T+1 e cea mai devreme dintre confirmarea echipei de fraudă (nu o alertă) și notificarea
    clientului. Lectura e o inferență [U], deci modul ancorei e parametru."""
    if x.bank_noted_at is None or not refund_track(x):
        return None
    anchor, source = refund_anchor(x, env.p("refund_anchor_mode"))
    if source == "constatare":
        text = (f"Ancora T+1 este constatarea fraudei de către bancă ({fmt_dt(anchor)}), înaintea notificării "
                f"clientului ({fmt_dt(x.notified_at)}).")
    else:
        text = f"Ancora T+1 este notificarea clientului ({fmt_dt(anchor)})."
    return Finding("DSP-58", f"ancora_{source}", text, ("bank_noted_at", "notified_at"),
                   data={"anchor": anchor, "source": source})


@rule("DSP-03", title="Ceasul T+1: alertă înainte de termen și depășire",
      basis="Legea 209/2019 art. 173–174; CJUE C-70/25", confidence=P, pack="DSP", source=f"{SRC} §3",
      questions=(Q_T1,), params=("refund_sla_alert_hours", "refund_end_of_day"),
      exceptions=("DSP_REFUND_SLA_AT_RISK", "DSP_REFUND_SLA_BREACHED"), tests=("DT-07", "DT-19"))
def dsp_03_refund_sla(x: RuleContextExt, env: Env) -> Finding | None:
    """Termenul T+1 se urmărește pe ancora DSP-58. Depășit la intake (ex. scrisoare pe hârtie înregistrată
    târziu): rambursarea se face imediat, cu escaladare. Pragul de alertă în ore e parametru [U]."""
    if not refund_track(x) or refund_withheld(x):
        return None
    due, now = refund_due(x, env), to_local(x.now)
    if now > due:
        return Finding("DSP-03", "DSP_REFUND_SLA_BREACHED",
                       f"Termenul T+1 ({fmt_dt(due)}) trecuse deja la analiză ({fmt_dt(now)}): rambursarea se face "
                       "imediat, cu escaladare.", ("notified_at",), data={"due": due})
    hours = (due - now).total_seconds() / 3600
    if hours <= env.p("refund_sla_alert_hours"):
        return Finding("DSP-03", "DSP_REFUND_SLA_AT_RISK",
                       f"Mai sunt {fmt_num(hours, 1)} ore până la termenul T+1 ({fmt_dt(due)}): cazul are prioritate.",
                       ("notified_at",), data={"due": due})
    return None


@rule("DSP-50", title="Cine a făcut pasul SCA: semnalele de autentificare și ambiguitatea merg la om",
      basis="Legea 209/2019 art. 171–172; inferență din note", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      questions=(Q_T1,), exceptions=("DSP_AUTH_AMBIGUOUS",), tests=("DT-02", "DT-03"))
def dsp_50_auth_signals(x: RuleContextExt, env: Env) -> Finding | None:
    """Se înregistrează cine a făcut pasul SCA și cum. Dispozitivele noi, schimbarea SIM-ului și plata imediat
    după click susțin că plata nu e a clientului; o clasificare ambiguă merge la om, cu scadența T+1, fără
    eticheta „autorizat” și fără refuz automat."""
    if x.dispute_type not in (DisputeType.NEAUTORIZATA, DisputeType.APP) or x.credit_fraud:
        return None
    signals: list[tuple[str, tuple[str, ...]]] = []
    if x.device_known is False:
        signals.append(("plata a pornit de pe un dispozitiv nou, nevăzut până atunci", ("device_known",)))
    if x.seconds_after_click is not None:
        signals.append((f"plata a pornit la {x.seconds_after_click} secunde după click pe link",
                        ("seconds_after_click",)))
    if x.sim_swap_hours_before is not None:
        signals.append((f"cartela SIM a fost schimbată cu {fmt_num(x.sim_swap_hours_before, 1)} ore înainte de plată",
                        ("sim_swap_hours_before",)))
    if x.beneficiary_new is True:
        signals.append(("beneficiarul e nou pentru client", ("beneficiary_new",)))
    fields = tuple(f for _, fs in signals for f in fs)
    listed = "; ".join(t for t, _ in signals)
    if classification_ambiguous(x, env):
        text = ("Clasificarea autorizat / neautorizat e ambiguă: decide un om înainte de termenul T+1, cu ciorne "
                "pentru ambele ramuri; niciun refuz automat.")
        if listed:
            text += f" Semnale: {listed}."
        return Finding("DSP-50", "DSP_AUTH_AMBIGUOUS", text, ("classification_ambiguous", *fields))
    if not signals:
        return None
    lead = ("Semnale că plata a fost inițiată de altcineva" if x.dispute_type == DisputeType.NEAUTORIZATA
            else "Semnale ale manipulării")
    return Finding("DSP-50", "semnale_autentificare", f"{lead}: {listed}.", fields)


@rule("DSP-54", title="Plângerea la poliție nu condiționează rambursarea T+1",
      basis="Legea 209/2019 art. 173; CJUE C-70/25; inferență din note", confidence=U, pack="DSP",
      source=f"{SRC} §7.4", questions=(Q_T1,), tests=("DT-01",))
def dsp_54_police_report(x: RuleContextExt, env: Env) -> Finding | None:
    """Art. 173 și C-70/25 admit o singură excepție de la T+1; plângerea la poliție poate fi cerută doar pentru
    dispută sau recuperare."""
    if not refund_track(x) or refund_withheld(x) or x.police_report_filed is True:
        return None
    return Finding("DSP-54", "garda_plangere",
                   "Lipsa plângerii la poliție nu blochează rambursarea T+1; plângerea poate fi cerută doar pentru "
                   "dispută sau recuperare.", ("police_report_filed",))


@rule("DSP-57", title="Textul reclamației e date, nu instrucțiuni; sumele vin din jurnal",
      basis="docs/context/13 §2.3 (propunere)", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      questions=(Q_T1, Q_ANSWER), exceptions=("DSP_SECURITY_SIGNAL",), tests=("DT-18", "DT-07"))
def dsp_57_untrusted_text(x: RuleContextExt, env: Env) -> Finding | None:
    """Instrucțiunile din textul clientului se ignoră și devin semnal de securitate. Suma folosită e cea din
    jurnalul băncii; o sumă diferită sau citită nesigur din document merge la om."""
    reasons: list[tuple[str, tuple[str, ...]]] = []
    if x.injection_suspected:
        reasons.append(("textul conține instrucțiuni către sistem; au fost ignorate", ("injection_suspected",)))
    if x.claimed_amount is not None and abs(x.claimed_amount - x.amount.value) > 0.005:
        reasons.append((f"suma din text ({fmt_money(x.claimed_amount, x.amount.currency)}) diferă de suma din jurnal "
                        f"({fmt_money(x.amount.value, x.amount.currency)}); se folosește suma din jurnal",
                        ("claimed_amount", "amount")))
    if x.claimed_amount_low_confidence:
        reasons.append(("suma din document a fost citită cu încredere mică; un om o confirmă din jurnal",
                        ("claimed_amount_low_confidence",)))
    if not reasons:
        return None
    security = x.injection_suspected or (x.claimed_amount is not None and abs(x.claimed_amount - x.amount.value) > 0.005)
    return Finding("DSP-57", "DSP_SECURITY_SIGNAL" if security else "suma_de_confirmat",
                   "Textul neîncrezut nu schimbă decizia: " + "; ".join(t for t, _ in reasons) + ".",
                   tuple(f for _, fs in reasons for f in fs))


@rule("DSP-59", title="Sumele peste plafon merg la om", basis="docs/context/14 §7.4 (pragul nu e în note)",
      confidence=U, pack="DSP", source=f"{SRC} §7.4", questions=(Q_T1,),
      params=("auto_refund_cap_ron", "eur_ron_rate"), exceptions=("DSP_AMOUNT_REVIEW",), tests=("scenarii",))
def dsp_59_amount_cap(x: RuleContextExt, env: Env) -> Finding | None:
    """Rambursarea automată are un plafon configurabil [U]. Peste plafon un om aprobă, tot în termenul T+1;
    plafonul nu amână și nu refuză nimic."""
    if not refund_track(x) or refund_withheld(x):
        return None
    cap, rate = env.p("auto_refund_cap_ron"), env.p("eur_ron_rate")
    ron = to_ron(x.amount, rate)
    amount = fmt_money(x.amount.value, x.amount.currency)
    if ron is None:
        return Finding("DSP-59", "DSP_AMOUNT_REVIEW",
                       f"Moneda {x.amount.currency} nu se poate compara cu plafonul în RON: un om aprobă rambursarea, "
                       "tot în termenul T+1.", ("amount",), data={"amount_ron": None})
    if ron <= cap:
        return Finding("DSP-59", "sub_plafon",
                       f"Suma de {amount} e sub plafonul de rambursare automată ({fmt_money(cap, 'RON')}, parametru [U]).",
                       ("amount",), data={"amount_ron": ron})
    return Finding("DSP-59", "DSP_AMOUNT_REVIEW",
                   f"Suma de {amount} depășește plafonul de rambursare automată ({fmt_money(cap, 'RON')}, parametru "
                   "[U]): un om aprobă, tot în termenul T+1.", ("amount",), data={"amount_ron": ron})


@rule("DSP-16", title="Credit sau card de credit pe numele victimei = reclamație de credit",
      basis="OUG 50/2010 art. 42", confidence=S, pack="DSP", source=f"{SRC} §3", questions=(Q_T1, Q_ANSWER),
      exceptions=("DSP_ROUTE_CREDIT_FRAUD",), tests=("DT-17",))
def dsp_16_credit_fraud(x: RuleContextExt, env: Env) -> Finding | None:
    """Un credit sau un card de credit emis pe numele clientului, necerut de el, e reclamație de credit (termen
    de 30 de zile, CMP-04), cu cererea de suspendare a raportării la Biroul de Credit. Nu se respinge ca
    „nu e dispută card”."""
    if not x.credit_fraud:
        return None
    return Finding("DSP-16", "DSP_ROUTE_CREDIT_FRAUD",
                   "Creditul sau cardul de credit a fost emis pe numele clientului fără cererea lui: e reclamație de "
                   "credit (30 de zile, CMP-04), cu cererea de suspendare a raportării la Biroul de Credit.",
                   ("credit_fraud",))


@rule("DSP-51", title="APP: traseu de sprijin, nu coada de dispute card", basis="inferență din note",
      confidence=U, pack="DSP", source=f"{SRC} §7.4", questions=(Q_ESCROC, Q_ANSWER),
      exceptions=("PAY_APP_SCAM",), tests=("DT-04",))
def dsp_51_support_route(x: RuleContextExt, env: Env) -> Finding | None:
    """Înșelătoria autorizată (APP) merge pe traseul de sprijin: investigație, recomandarea plângerii la poliție,
    eventual reeșalonare și Biroul de Credit, scrisoare explicativă."""
    if x.dispute_type != DisputeType.APP:
        return None
    return Finding("DSP-51", "traseu_sprijin",
                   "Traseu de sprijin pentru înșelătoria autorizată: investigație, recomandarea plângerii la poliție, "
                   "scrisoare explicativă; nu coada de dispute card.", ("dispute_type",))


# ---------------------------------------------------------------- pista C: chargeback


@rule("DSP-52", title="Flagul „recuperabil prin chargeback”", basis="regulile Visa (docs/context/14 §6.1); inferență",
      confidence=U, pack="DSP", source=f"{SRC} §6.1", questions=(Q_ESCROC,), params=("default_card_scheme",),
      tests=("DT-01", "DT-02", "DT-06", "DT-08", "DT-11", "DT-16"))
def dsp_52_chargeback_flag(x: RuleContextExt, env: Env) -> Finding | None:
    """Flagul se calculează la intake, din ECI, CAVV, token, canal, comerciant și istoric, în ordinea fixă din
    §6.1: DA, NU sau INCERT, cu regulile care au decis. Nu schimbă rambursarea (DSP-37)."""
    if not is_card(x) or x.credit_fraud:
        return None
    value, blocking, code = chargeback_recoverable(x, env)
    scheme = card_scheme(x, env)
    label = (f"Visa {code}" if scheme == "visa" else f"Mastercard {code}") if code else "condiția de stabilit"
    if value == "DA":
        text = f"Recuperabil prin chargeback: DA ({label})."
    elif value == "NU":
        text = f"Recuperabil prin chargeback: NU (regula {', '.join(blocking)})."
    else:
        text = f"Recuperabil prin chargeback: INCERT ({label}; {', '.join(blocking)}): omul alege ruta de schemă."
    fields = ("eci", "cavv_present", "dispute_type", "duplicate_of")
    return Finding("DSP-52", f"recuperabil_{value}", text, fields,
                   data={"value": value, "blocking_rules": blocking, "reason_code": code, "scheme": scheme,
                         "hit_params": {"recuperabil": value, "reason_code": code, "blocking_rules": blocking,
                                        "scheme": scheme}})


@rule("DSP-20", title="Condiția vine din lista închisă Visa", basis="Visa Core Rules cap. 11", confidence=P,
      pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_UNKNOWN_CONDITION",),
      tests=("DT-10",))
def dsp_20_condition(x: RuleContextExt, env: Env) -> Finding | None:
    """Condiția de dispută vine din lista închisă (§5.1), cu denumirile din Core Rules; altă valoare merge la om.
    Subcodurile 12.6.1 și 12.6.2 nu sunt în docs/context [U]."""
    if not is_card(x) or card_scheme(x, env) != "visa":
        return None
    cond = visa_condition(x)
    if cond is None:
        return None
    if not is_valid_condition(cond):
        return Finding("DSP-20", "DSP_UNKNOWN_CONDITION",
                       f"Condiția propusă „{cond}” nu există în lista închisă Visa (Core Rules, cap. 11): decide un om.",
                       ("visa_condition",), data={"condition": cond})
    note = " (subcod [U], de verificat în Core Rules)" if cond in VISA_SUBCONDITIONS else ""
    return Finding("DSP-20", "conditie_valida", f"Condiția Visa {cond}: {condition_name(cond)}{note}.",
                   ("visa_condition", "dispute_type", "duplicate_of"), data={"condition": cond})


@rule("DSP-21", title="Fiecare tranzacție se contestă separat și o singură dată", basis="Visa Core Rules §11.2.1",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_DUPLICATE_DISPUTE",),
      tests=("DT-16",))
def dsp_21_single_dispute(x: RuleContextExt, env: Env) -> Finding | None:
    """N tranzacții înseamnă N dispute; o dispută existentă pe tranzacție o blochează pe a doua (excepție: 10.5)."""
    if not is_card(x) or not x.existing_dispute_for_txn:
        return None
    return Finding("DSP-21", "DSP_DUPLICATE_DISPUTE",
                   "Există deja o dispută pe această tranzacție: o tranzacție se contestă o singură dată.",
                   ("existing_dispute_for_txn",))


@rule("DSP-24", title="Termenul de dispută al emitentului depinde de condiție",
      basis="Visa Core Rules Tables 11-29 și 11-92", confidence=P, pack="DSP", source=f"{SRC} §5.4",
      questions=(Q_ESCROC,), params=("visa_other_open_days", "visa_131_wait_anchor"),
      exceptions=("PAY_CHARGEBACK_WINDOW", "DSP_DEADLINE_UNVERIFIED"), tests=("DT-01", "DT-05", "DT-09", "DT-10"))
def dsp_24_dispute_window(x: RuleContextExt, env: Env) -> Finding | None:
    """10.4: 120 de zile de la procesare. 13.1: 120 de zile de la procesare sau de la ultima livrare așteptată,
    cel mult 540, după o așteptare de 15 zile când nu există dată de livrare (ancora [U]). Celelalte condiții:
    „120 de zile pentru majoritatea” [U], deci `DSP_DEADLINE_UNVERIFIED` și decide omul."""
    if not is_card(x) or card_scheme(x, env) != "visa" or x.dispute_type == DisputeType.APP:
        return None
    w = visa_dispute_window(x, env)
    if w is None:
        return None
    basis = "Visa Core Rules Table 11-29" if w.condition == "10.4" else (
        "Visa Core Rules Table 11-92" if w.condition == "13.1" else "Visa Core Rules cap. 11 [U]")
    deadlines = [Deadline(rule_id="DSP-24", name=f"Termen de dispută Visa {w.condition} (emitent)",
                          due_at=end_of_day(w.due), basis=basis, business_days=False)]
    fields = ["processing_date" if w.anchor_known else "executed_at"]
    if x.expected_delivery_date:
        fields.append("expected_delivery_date")
    anchor = "" if w.anchor_known else " (data procesării lipsește: ancora e data plății, conservator)"
    if w.earliest:
        deadlines.append(Deadline(rule_id="DSP-24", name=f"Cel mai devreme pentru disputa Visa {w.condition} "
                                  "(după așteptarea de 15 zile)", due_at=end_of_day(w.earliest), basis=basis,
                                  business_days=False))
    data = {"condition": w.condition, "due": w.due, "earliest": w.earliest}
    if w.expired:
        return Finding("DSP-24", "PAY_CHARGEBACK_WINDOW",
                       f"Termenul de dispută Visa {w.condition} a expirat la {fmt_d(w.due)}{anchor}: chargeback-ul "
                       "nu mai e posibil.", tuple(fields), data=data, deadlines=tuple(deadlines))
    if not w.verified:
        return Finding("DSP-24", "DSP_DEADLINE_UNVERIFIED",
                       f"Termenul pentru condiția {w.condition} nu e citit în Core Rules: se folosesc "
                       f"{env.p('visa_other_open_days')} de zile [U], până la {fmt_d(w.due)}{anchor}; omul confirmă "
                       "termenul.", tuple(fields), data=data, deadlines=tuple(deadlines))
    text = f"Disputa Visa {w.condition} se poate deschide până la {fmt_d(w.due)}{anchor}."
    if w.earliest:
        text += f" Fără dată de livrare, cel mai devreme din {fmt_d(w.earliest)} (așteptare de 15 zile, ancora [U])."
    return Finding("DSP-24", "in_termen", text, tuple(fields), data=data, deadlines=tuple(deadlines))


@rule("DSP-25", title="Frauda se raportează la Visa, chiar și când disputa nu e posibilă",
      basis="Visa Core Rules Table 11-27; §1.9.4.3", confidence=P, pack="DSP", source=f"{SRC} §5.2",
      questions=(Q_ESCROC,), params=("fraud_report_deadline_mode",), exceptions=("DSP_FRAUD_REPORT_DUE",),
      tests=("DT-01", "DT-02"))
def dsp_25_fraud_report(x: RuleContextExt, env: Env) -> Finding | None:
    """Frauda se raportează prin VisaNet la detectare, oricare ar fi starea tranzacției: 60 de zile de la
    tranzacție sau 30 de la notificarea titularului, dacă vine mai târziu (lectura e parametru [U])."""
    if not (is_card(x) and card_scheme(x, env) == "visa" and refund_track(x)) or refund_withheld(x):
        return None
    due, agree = visa_fraud_report_due(local_date(x.executed_at), local_date(x.notified_at),
                                       env.p("fraud_report_deadline_mode"))
    text = f"Frauda se raportează la Visa până la {fmt_d(due)}, chiar dacă disputa nu e posibilă."
    if not agree:
        text += " Lecturile termenului diferă: s-a ales data mai devreme, iar omul confirmă (DSP_RULE_UNVERIFIED)."
    return Finding("DSP-25", "DSP_FRAUD_REPORT_DUE", text, ("executed_at", "notified_at"), data={"due": due},
                   deadlines=(Deadline(rule_id="DSP-25", name="Raportul de fraudă la Visa", due_at=end_of_day(due),
                                       basis="Visa Core Rules §1.9.4.3", business_days=False),))


def _visa_fraud_claim(x: RuleContextExt, env: Env) -> bool:
    return is_card(x) and card_scheme(x, env) == "visa" and is_unauthorised(x)


@rule("DSP-26", title="10.4 e invalidă peste 35 de dispute în ultimele 120 de zile",
      basis="Visa Core Rules Table 11-28", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      params=("dispute_count_scope",), exceptions=("DSP_DISPUTE_LIMIT_EXCEEDED",), tests=("DT-06",))
def dsp_26_dispute_cap(x: RuleContextExt, env: Env) -> Finding | None:
    """Peste 35 de dispute deschise de emitent pe cont în 120 de zile, 10.4 nu e validă. Ce se numără e [U]
    (parametrul `dispute_count_scope`). Obligația legală de rambursare rămâne."""
    if not _visa_fraud_claim(x, env):
        return None
    scope = env.p("dispute_count_scope")
    n = x.prior_disputes_120d
    if n is None:
        if x.prior_disputes_12m > VISA_104_DISPUTE_CAP:
            return Finding("DSP-26", "DSP_RULE_UNVERIFIED",
                           f"{x.prior_disputes_12m} contestații în 12 luni, dar lipsește numărul pe 120 de zile: omul "
                           "verifică limita de 35.", ("prior_disputes_12m",))
        return None
    if n > VISA_104_DISPUTE_CAP:
        return Finding("DSP-26", "DSP_DISPUTE_LIMIT_EXCEEDED",
                       f"Contul are {n} dispute în ultimele 120 de zile (domeniu: {scope} [U]), peste limita de 35: "
                       "condiția 10.4 nu e validă. Rambursarea legală rămâne; contul se semnalează echipei de fraudă.",
                       ("prior_disputes_120d",), data={"count": n})
    return Finding("DSP-26", "sub_limita", f"{n} dispute în ultimele 120 de zile: sub limita de 35 pentru 10.4.",
                   ("prior_disputes_120d",), data={"count": n})


@rule("DSP-27", title="10.4 e invalidă la e-commerce autentificat Visa Secure (ECI 05 + CAVV)",
      basis="Visa Core Rules Table 11-28", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      exceptions=("DSP_NOT_CHARGEABLE",), tests=("DT-02", "DT-03"))
def dsp_27_visa_secure(x: RuleContextExt, env: Env) -> Finding | None:
    """E-commerce cu ECI 5, confirmarea autentificării prin Visa Secure (EMV 3DS) și CAVV în autorizare:
    10.4 nu e validă (liability shift). Rambursarea T+1 rămâne datorată."""
    if not _visa_fraud_claim(x, env):
        return None
    if _eci(x) == "05" and x.cavv_present is True and x.visa_secure_auth_confirmation is not False:
        return Finding("DSP-27", "DSP_NOT_CHARGEABLE",
                       "Plata e-commerce a fost autentificată cu Visa Secure (ECI 05, CAVV în autorizare): condiția "
                       "10.4 nu e validă, deci pierderea rămâne la bancă dacă recuperarea de la client nu reușește. "
                       "Rambursarea T+1 rămâne datorată.", ("eci", "cavv_present"))
    return None


@rule("DSP-28", title="10.4 e invalidă la tranzacția tokenizată autentificată", basis="Visa Core Rules Table 11-28",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_NOT_CHARGEABLE",))
def dsp_28_token(x: RuleContextExt, env: Env) -> Finding | None:
    """Token cu TAVV și metodă de verificare aprobată: 10.4 nu e validă."""
    if _visa_fraud_claim(x, env) and x.wallet_token and x.tavv_present and x.cvm_approved:
        return Finding("DSP-28", "DSP_NOT_CHARGEABLE",
                       "Tranzacția tokenizată a fost autentificată (TAVV și metodă de verificare aprobată): condiția "
                       "10.4 nu e validă.", ("wallet_token", "tavv_present", "cvm_approved"))
    return None


@rule("DSP-29", title="10.4 e invalidă la cripto sau NFT cumpărat de titular", basis="Visa Core Rules Table 11-28",
      confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC, Q_T1), exceptions=("PAY_APP_SCAM",),
      tests=("DT-04",))
def dsp_29_crypto(x: RuleContextExt, env: Env) -> Finding | None:
    """Titularul a participat la cumpărarea de cripto sau NFT și spune ulterior că a fost înșelat: 10.4 nu e
    validă, iar cazul e APP (DSP-13, DSP-51). Maparea MCC → cripto nu e în note [U]."""
    if is_card(x) and x.purchase_type == "crypto_nft" and x.cardholder_participated is True:
        return Finding("DSP-29", "PAY_APP_SCAM",
                       "Titularul a cumpărat el cripto sau NFT și spune ulterior că a fost înșelat: condiția 10.4 nu e "
                       "validă; cazul merge pe traseul de sprijin.", ("purchase_type", "cardholder_participated"))
    return None


@rule("DSP-30", title="CE3.0: două tranzacții anterioare necontestate cu aceleași elemente",
      basis="Visa Core Rules Table 11-28; ghidul Visa pp. 22–23, 78–79", confidence=P, pack="DSP",
      source=f"{SRC} §5.2", questions=(Q_ESCROC, Q_T1), exceptions=("DSP_CE3_MET", "DSP_CE3_NOT_MET"),
      tests=("DT-12", "DT-13"))
def dsp_30_ce3(x: RuleContextExt, env: Env) -> Finding | None:
    """Rezultatul `ce3_check` pe datele băncii. CE3.0 îndeplinit: 10.4 nu e validă, iar cazul devine semnal
    candidat de fraudă a clientului (DSP-05): reținere propusă și notificare către autoritate, cu four-eyes."""
    if not is_card(x) or x.ce3_met is None:
        return None
    if x.ce3_met:
        return Finding("DSP-30", "DSP_CE3_MET",
                       "Dovezile CE3.0 sunt îndeplinite (două tranzacții anterioare necontestate, cu aceleași "
                       "elemente): 10.4 nu e validă, iar cazul e un semnal candidat de fraudă a clientului: un om "
                       "decide reținerea și notificarea autorității (four-eyes).", ("ce3_met",))
    return Finding("DSP-30", "DSP_CE3_NOT_MET", "Condițiile CE3.0 nu sunt îndeplinite.", ("ce3_met",))


@rule("DSP-31", title="ECI 06 („attempted”): condiții necitite integral", basis="Visa Core Rules Table 11-28",
      confidence=U, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",),
      tests=("DT-08",))
def dsp_31_eci06(x: RuleContextExt, env: Env) -> Finding | None:
    """ECI 6 poate face 10.4 invalidă, în condiții necitite integral: rezultatul e INCERT și decide omul."""
    if _visa_fraud_claim(x, env) and _eci(x) == "06":
        return Finding("DSP-31", "DSP_RULE_UNVERIFIED",
                       "ECI 06 („attempted”): regula pentru 10.4 nu e citită integral, deci recuperabilitatea e INCERT "
                       "și decide omul; rambursarea nu se schimbă.", ("eci",))
    return None


@rule("DSP-32", title="Certificarea în numele titularului doar pe canal autentificat",
      basis="Visa Core Rules §11.7.1, §11.10.1", confidence=P, pack="DSP", source=f"{SRC} §5.2",
      questions=(Q_ESCROC, Q_ANSWER), exceptions=("DSP_CARDHOLDER_PROOF_MISSING",), tests=("DT-01", "DT-07"))
def dsp_32_cardholder_certification(x: RuleContextExt, env: Env) -> Finding | None:
    """Emitentul certifică în numele titularului (categoriile 10 și 13) doar dacă cererea a venit pe un canal
    echivalent semnăturii; altfel cere o scrisoare semnată, cu cardul, comercianții și sumele."""
    if not is_card(x) or x.dispute_type not in (DisputeType.NEAUTORIZATA, DisputeType.DISPUTA_COMERCIANT):
        return None
    if x.intake_authenticated is True:
        return Finding("DSP-32", "certificare_permisa",
                       "Cererea a venit pe un canal autentificat: emitentul poate certifica în numele titularului.",
                       ("intake_authenticated",))
    if x.intake_authenticated is False and x.signed_letter is not True:
        return Finding("DSP-32", "DSP_CARDHOLDER_PROOF_MISSING",
                       "Cererea nu a venit pe un canal autentificat și nu e semnată: înainte de dispută se cere o "
                       "scrisoare semnată, cu cardul (mascat), comercianții și sumele.",
                       ("intake_authenticated", "signed_letter"))
    return None


@rule("DSP-37", title="Emitentul nu procesează dispute invalide și face due diligence la fiecare dispută",
      basis="Visa Core Rules §11.1.2", confidence=P, pack="DSP", source=f"{SRC} §5.2", questions=(Q_ESCROC,),
      tests=("frauda_client",))
def dsp_37_due_diligence(x: RuleContextExt, env: Env) -> Finding | None:
    """Invaliditatea se verifică înainte de orice ciornă de dispută. Cu semnale de fraudă a clientului, disputa
    de fraudă nu se propune până nu le lămurește un om; protecțiile legale ale clientului rămân."""
    if not (is_card(x) and is_unauthorised(x)):
        return None
    signals = risk_signals(x, env)
    reasons = [t for t, _ in signals]
    fields = [f for _, fs in signals for f in fs]
    if x.hold_signal:
        reasons.append("există o suspiciune de fraudă a clientului confirmată de un om")
        fields.append("hold_signal")
    if x.ce3_met:
        reasons.append("dovezile CE3.0 sunt îndeplinite")
        fields.append("ce3_met")
    if not reasons:
        return None
    return Finding("DSP-37", "due_diligence",
                   "Disputa de fraudă nu se propune până nu lămurește un om semnalele: " + "; ".join(reasons) + ".",
                   tuple(fields))


@rule("DSP-40", title="Codurile Mastercard (4837 fraudă, 4853 dispută, 4834 eroare)",
      basis="specificații Valitor/Rapyd; agregatori", confidence=S, pack="DSP", source=f"{SRC} §5.3",
      questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",), tests=("DT-11",))
def dsp_40_mastercard_codes(x: RuleContextExt, env: Env) -> Finding | None:
    """Codurile Mastercard vin din surse secundare: 4837 No Cardholder Authorization, 4853 Cardholder Dispute,
    4834 Point-of-Interaction Error. Codul e doar candidat."""
    if not is_card(x) or card_scheme(x, env) != "mastercard":
        return None
    code = MC_CODES.get(x.dispute_type)
    if code is None:
        return None
    return Finding("DSP-40", "cod_candidat", f"Cod Mastercard candidat: {code} (sursă secundară).",
                   ("dispute_type",), data={"reason_code": code})


@rule("DSP-42", title="Termenele Mastercard sunt în conflict între surse", basis="agregatori (Chargeback Gurus, "
      "ChargebackStop, Chargeflow)", confidence=U, pack="DSP", source=f"{SRC} §5.3", questions=(Q_ESCROC,),
      params=("mc_chargeback_open_days",), exceptions=("DSP_RULE_UNVERIFIED",), tests=("DT-11",))
def dsp_42_mastercard_deadlines(x: RuleContextExt, env: Env) -> Finding | None:
    """Termenele Mastercard stau în configurare, fără blocare automată; ruta o alege omul."""
    if not is_card(x) or card_scheme(x, env) != "mastercard" or x.dispute_type == DisputeType.APP:
        return None
    days = env.p("mc_chargeback_open_days")
    proc, _ = processing_date(x)
    due = visa_due(proc, days)
    return Finding("DSP-42", "DSP_RULE_UNVERIFIED",
                   f"Termenele Mastercard sunt în conflict între surse (chargeback ~{days} de zile, până la "
                   f"{fmt_d(due)} [S]): fără blocare automată, decide omul.", ("executed_at",),
                   deadlines=(Deadline(rule_id="DSP-42", name="Termen chargeback Mastercard (estimat, [S])",
                                       due_at=end_of_day(due), basis="agregatori, surse în conflict",
                                       business_days=False),))


@rule("DSP-43", title="Precondițiile 4837 și plafonul pe cont nu sunt verificate", basis="gol în note",
      confidence=U, pack="DSP", source=f"{SRC} §5.3", questions=(Q_ESCROC,), exceptions=("DSP_RULE_UNVERIFIED",),
      tests=("DT-11",))
def dsp_43_mastercard_4837(x: RuleContextExt, env: Env) -> Finding | None:
    """Ruta Mastercard de fraudă merge la om: precondițiile 4837 nu sunt în note."""
    if is_card(x) and card_scheme(x, env) == "mastercard" and is_unauthorised(x):
        return Finding("DSP-43", "DSP_RULE_UNVERIFIED",
                       "Precondițiile codului 4837 (ex. raportarea în baza de fraudă) nu sunt verificate: ruta "
                       "Mastercard de fraudă o alege omul.", ("dispute_type",))
    return None


@rule("DSP-53", title="Checklist de dovezi; fiecare gol devine o cerere către client",
      basis="formularul BCR (proxy) [P la BCR]; practica Raiffeisen [U]", confidence=U, pack="DSP",
      source=f"{SRC} §7.4", questions=(Q_ESCROC, Q_ANSWER), exceptions=("DSP_EVIDENCE_MISSING",), tests=("DT-09",))
def dsp_53_evidence(x: RuleContextExt, env: Env) -> Finding | None:
    """Pentru disputele de consum (13.x) e nevoie de dovada contactării comerciantului, a anulării sau a
    returului; lipsa ei devine o cerere către client înaintea disputei."""
    if not is_card(x):
        return None
    cond = visa_condition(x)
    if not cond or not cond.startswith("13.") or cond == "13.9" or x.merchant_contact_proof is True:
        return None
    return Finding("DSP-53", "DSP_EVIDENCE_MISSING",
                   "Lipsește dovada contactării comerciantului (sau a anulării ori a returului): se cere clientului "
                   "înainte de dispută.", ("merchant_contact_proof",), data={"missing": ["dovada contactării comerciantului"]})


# ---------------------------------------------------------------- gărzi și calculatoare de proces


_REVERSAL_ALLOWED = {"comerciant_a_rambursat": "comerciantul a rambursat deja aceeași tranzacție",
                     "disputa_13x_pierduta": "disputa de consum (13.x) a fost pierdută, conform clauzei contractuale [U]"}


@rule("DSP-55", title="Reversarea creditului provizoriu doar în cazurile permise",
      basis="clauza BCR (proxy) [P]; CJUE C-70/25; opinia AG", confidence=U, pack="DSP", source=f"{SRC} §7.4",
      kind="garda", questions=(Q_CLIENT,), exceptions=("DSP_REVERSAL_BLOCKED",), tests=("DT-15",))
def validate_reversal(reason: str) -> GuardResult:
    """Reversarea se propune doar dacă (a) comerciantul a rambursat deja sau (b) o dispută de consum 13.x e
    pierdută. După o rambursare din art. 173, neglijența gravă nu justifică reversarea: se merge pe pista B."""
    key = reason.strip().lower()
    if key in _REVERSAL_ALLOWED:
        return GuardResult(allowed=True, rule_id="DSP-55", code="propune_reversare",
                           explanation=f"Reversarea se poate propune: {_REVERSAL_ALLOWED[key]}.",
                           next_actions=["propune reversarea, cu aprobare umană", "notifică clientul înainte"])
    return GuardResult(allowed=False, rule_id="DSP-55", code="DSP_REVERSAL_BLOCKED",
                       explanation="Reversarea creditului e blocată: după o rambursare din art. 173, neglijența gravă "
                                   "sau alt motiv nu justifică reversarea unilaterală.",
                       next_actions=["redactează cererea de restituire pe pista de recuperare (PAY-06)",
                                     "dacă clientul refuză, banca merge în instanță (opinia AG)"])


class Ce3Txn(BaseModel):
    """O tranzacție pentru CE3.0 (date sintetice): elementele care se compară."""

    txn_id: str
    processed_on: date
    merchant_id: str | None = None
    device_id: str | None = None
    fingerprint: str | None = None
    ip: str | None = None
    login_id: str | None = None
    shipping_address: str | None = None      # adresa completă sau hash-ul ei
    reported_fraud: bool = False
    disputed: bool = False


class Ce3Result(BaseModel):
    met: bool
    code: str
    qualifying: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _ce3_elements(a: Ce3Txn, b: Ce3Txn, v2026: bool) -> set[str]:
    out: set[str] = set()
    device = bool(a.device_id and a.device_id == b.device_id and len(a.device_id) >= 15)
    fingerprint = bool(a.fingerprint and a.fingerprint == b.fingerprint and len(a.fingerprint) >= 20)
    if v2026:
        if device or fingerprint:
            out.add("device")            # din 24.10.2026: device ID și fingerprint = un singur element
    else:
        if device:
            out.add("device")
        if fingerprint:
            out.add("fingerprint")
    if a.ip and a.ip == b.ip:
        out.add("ip")
    if a.login_id and a.login_id == b.login_id:
        out.add("login")
    if a.shipping_address and a.shipping_address == b.shipping_address:
        out.add("adresa")
    return out


def ce3_check(disputed: Ce3Txn, priors: list[Ce3Txn], dispute_on: date, as_of: date | None = None) -> Ce3Result:
    """DSP-30: CE3.0 e îndeplinit cu două tranzacții anterioare pe aceeași credențială, neraportate ca fraudă,
    procesate cu peste 120 de zile înainte de dispută și în cele 365 de zile dinaintea tranzacției contestate,
    fiecare cu cel puțin două elemente potrivite, dintre care unul IP sau dispozitiv. Din 24.10.2026 contează și
    alți comercianți, iar device ID și fingerprint sunt un singur element. Versiunea regulii se alege după
    `as_of` (momentul evaluării, ex. pre-arbitrajul; implicit data disputei): data de referință e [U]."""
    v2026 = (as_of or dispute_on) >= CE3_V2026_FROM
    qualifying: list[str] = []
    reasons: list[str] = []
    for t in priors:
        if t.reported_fraud:
            reasons.append(f"{t.txn_id}: raportată de bancă drept fraudă")
            continue
        if t.disputed:
            reasons.append(f"{t.txn_id}: contestată")
            continue
        if (dispute_on - t.processed_on).days <= 120:
            reasons.append(f"{t.txn_id}: procesată cu cel mult 120 de zile înainte de dispută")
            continue
        age = (disputed.processed_on - t.processed_on).days
        if age < 0 or age > 365:
            reasons.append(f"{t.txn_id}: în afara celor 365 de zile dinaintea tranzacției contestate")
            continue
        if not v2026 and t.merchant_id != disputed.merchant_id:
            reasons.append(f"{t.txn_id}: alt comerciant (înainte de 24.10.2026 trebuia același)")
            continue
        elements = _ce3_elements(disputed, t, v2026)
        if len(elements) >= 2 and elements & {"device", "fingerprint", "ip"}:
            qualifying.append(t.txn_id)
        else:
            reasons.append(f"{t.txn_id}: elemente potrivite {sorted(elements) or '—'} (trebuie două, unul IP sau "
                           "dispozitiv)")
    met = len(qualifying) >= 2
    return Ce3Result(met=met, code="DSP_CE3_MET" if met else "DSP_CE3_NOT_MET", qualifying=qualifying,
                     reasons=reasons)


__all__ = ["Ce3Result", "Ce3Txn", "DisputeWindow", "MC_CODES", "VISA_CONDITIONS", "VISA_STAGES",
           "VISA_SUBCONDITIONS", "ce3_check", "chargeback_recoverable", "classification_ambiguous",
           "condition_name", "is_valid_condition", "scheme_deadline_status", "validate_reversal",
           "visa_allocation_stage_due", "visa_collaboration_stage_due", "visa_dispute_window", "visa_due",
           "visa_fraud_report_due"]
