"""Pachetul PAY: Legea 209/2019 (PSD2) și CJUE C-70/25. ID-urile și marcajele vin din docs/context/11 §2.5.

Regulile DSP-01…DSP-13 din docs/context/14 §3 aplică aceleași articole în fluxul de dispute; aici sunt
aliasuri (coloana „În 11” din tabelul docs/context/14 §3).
"""

from __future__ import annotations

from datetime import date, timedelta

from versoml.contracts import Confidence, Deadline, DisputeType, Question

from ..calendar_ro import BusinessCalendar, add_months, end_of_day, local_date, months_between, to_local
from ..context import GuardResult, RuleContextExt
from ..facts import (
    GN_LABELS, Env, eur_cap_in, fmt_d, fmt_dt, fmt_money, gn_indicator_fields, gross_negligence_case,
    is_unauthorised, refund_anchor, refund_due, refund_track, refund_withheld, sca_evidence_present,
)
from ..registry import Finding, rule

P, S = Confidence.P, Confidence.S
SRC = "docs/context/11 §2.5"
Q_T1, Q_CLIENT, Q_ESCROC, Q_ANSWER = (Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT,
                                      Question.RECUPERARE_ESCROC, Question.RASPUNS_RECLAMATIE)


@rule("PAY-12", title="Plata autorizată sub manipulare (APP) nu intră automat la art. 173",
      basis="ghid de consum Bitdefender (docs/context/11 §2.5, PAY-12)", confidence=S, pack="PAY", source=SRC,
      questions=(Q_T1, Q_ESCROC, Q_ANSWER), exceptions=("PAY_APP_SCAM",), aliases=("DSP-13",),
      tests=("TC-31", "DT-04"))
def pay_12_app_scam(x: RuleContextExt, env: Env) -> Finding | None:
    """Clientul a autorizat plata, păcălit: regimul de rambursare pentru operațiuni neautorizate nu se aplică
    automat. Clasificarea precede orice calcul; cazul merge pe traseul de sprijin (DSP-51)."""
    if x.dispute_type != DisputeType.APP:
        return None
    return Finding(
        "PAY-12", "PAY_APP_SCAM",
        "Clientul a autorizat plata, sub manipulare: rambursarea T+1 pentru operațiuni neautorizate nu se aplică "
        "automat (art. 173). Cazul merge pe traseul de sprijin: rechemare urgentă, recomandarea plângerii la poliție "
        "și răspuns motivat în 15 zile lucrătoare.",
        fields=("dispute_type", "client_admits_approving_in_app", "screen_showed_amount_and_payee"))


@rule("PAY-01", title="Notificarea în cel mult 13 luni de la debitare",
      basis="Legea 209/2019 art. 169; opinia AG Rantos în C-70/25 (comunicatul CURIA 31/26)", confidence=P,
      pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT, Q_ANSWER), params=("undue_delay_days",),
      exceptions=("PAY_LATE_NOTIFICATION",), aliases=("DSP-01",), tests=("TC-29", "DT-05"))
def pay_01_notification_window(x: RuleContextExt, env: Env) -> Finding | None:
    """Cererea „neautorizată” se verifică întâi pe 13 luni de la debitare. Limita nu se aplică dacă banca
    nu a furnizat informațiile despre tranzacție. „Fără întârziere nejustificată” nu are prag în note:
    dacă parametrul e setat și e depășit, cazul merge la om (nu e motiv de respingere)."""
    if not is_unauthorised(x):
        return None
    debit_on, notified_on = local_date(x.executed_at), local_date(x.notified_at)
    limit = add_months(debit_on, 13)
    months = months_between(debit_on, notified_on)
    deadline = Deadline(rule_id="PAY-01", name="Limita de notificare a plății neautorizate (13 luni)",
                        due_at=end_of_day(limit), basis="Legea 209/2019 art. 169", business_days=False)
    fields = ("executed_at", "notified_at")
    if notified_on <= limit:
        undue = env.p("undue_delay_days")
        elapsed = (notified_on - debit_on).days
        review = undue is not None and elapsed > undue
        text = (f"Plata a fost debitată la {fmt_d(debit_on)}, iar clientul a notificat banca la {fmt_d(notified_on)}, "
                f"în termenul de 13 luni (limita: {fmt_d(limit)}, art. 169).")
        if review:
            text += (f" Au trecut {elapsed} zile, peste pragul [U] de {undue} zile pentru „fără întârziere "
                     "nejustificată”: un om verifică, fără să amâne rambursarea.")
        return Finding("PAY-01", "in_termen", text, fields, data={"limit": limit, "undue_delay_review": review},
                       deadlines=(deadline,))
    if not x.tx_info_provided:
        return Finding(
            "PAY-01", "limita_nu_se_aplica",
            f"Au trecut {months} luni de la debitare, dar banca nu a furnizat informațiile despre tranzacție: "
            "limita de 13 luni nu se aplică (art. 169).",
            (*fields, "tx_info_provided"), data={"limit": limit, "undue_delay_review": False}, deadlines=(deadline,))
    return Finding(
        "PAY-01", "PAY_LATE_NOTIFICATION",
        f"Notificarea a venit la {fmt_d(notified_on)}, după limita de 13 luni de la debitare ({fmt_d(limit)}), iar "
        "banca a furnizat informațiile despre tranzacție: nu există obligația de corecție (art. 169). Răspunsul "
        "motivat îl aprobă un om.",
        (*fields, "tx_info_provided"), data={"limit": limit, "undue_delay_review": False}, deadlines=(deadline,))


@rule("PAY-03", title="Rambursare cel târziu la sfârșitul zilei lucrătoare următoare (T+1)",
      basis="Legea 209/2019 art. 173–174; CJUE C-70/25 (PSD2 art. 73 alin. (1))", confidence=P, pack="PAY",
      source=SRC, questions=(Q_T1,), params=("refund_end_of_day", "bank_closure_days", "refund_anchor_mode",
                                              "competent_authority"),
      exceptions=("PAY_REFUND_DUE", "PAY_FRAUD_SUSPECTED", "PAY_FRAUD_NOTICE_MISSING"), aliases=("DSP-05",),
      tests=("TC-27", "TC-40", "DT-01", "DT-12"))
def pay_03_refund_due(x: RuleContextExt, env: Env) -> Finding | None:
    """La o plată neautorizată, banca rambursează imediat, cel târziu la sfârșitul zilei lucrătoare care urmează
    constatării sau notificării; contul revine la starea anterioară, cu data valutei cel târziu data debitării.
    Singura excepție: motive rezonabile de suspiciune de fraudă a plătitorului, comunicate în scris autorității
    competente. Neglijența gravă nu e excepție (PAY-15)."""
    if x.credit_fraud:
        return None
    if x.dispute_type != DisputeType.NEAUTORIZATA:
        kind = "disputa cu comerciantul" if x.dispute_type == DisputeType.DISPUTA_COMERCIANT else (
            "eroarea de procesare" if x.dispute_type == DisputeType.EROARE_PROCESARE else "plata autorizată")
        return Finding("PAY-03", "nu_se_aplica",
                       f"Art. 173 privește doar operațiunile neautorizate; {kind} urmează alt traseu "
                       "(chargeback, corecție sau sprijin).", fields=("dispute_type",))
    if not refund_track(x):
        return None
    anchor, source = refund_anchor(x, env.p("refund_anchor_mode"))
    due = refund_due(x, env)
    deadline = Deadline(rule_id="PAY-03", name="Rambursare T+1 (sfârșitul zilei lucrătoare următoare)", due_at=due,
                        basis="Legea 209/2019 art. 173; CJUE C-70/25", business_days=True)
    anchor_fields = ("bank_noted_at",) if source == "constatare" else ("notified_at",)
    authority = env.p("competent_authority") or "autoritatea națională competentă (BNR sau ANPC, de confirmat)"
    data = {"due": due, "anchor": anchor, "anchor_source": source}
    if refund_withheld(x):
        return Finding(
            "PAY-03", "PAY_FRAUD_SUSPECTED",
            "Rambursarea se reține: există motive rezonabile de suspiciune de fraudă a plătitorului, confirmate de "
            f"un om și comunicate în scris către {authority}. E singura excepție admisă de art. 173 și de C-70/25; "
            "urmează investigația umană (four-eyes).",
            ("hold_signal", "hold_authority_notified"), data=data, deadlines=(deadline,))
    if x.hold_signal:
        return Finding(
            "PAY-03", "PAY_FRAUD_NOTICE_MISSING",
            "Există o suspiciune de fraudă a plătitorului, dar motivele nu au fost comunicate în scris autorității: "
            f"fie comunicarea către {authority} pleacă până la {fmt_dt(due)}, fie banca rambursează la termen.",
            ("hold_signal", "hold_authority_notified", *anchor_fields), data=data, deadlines=(deadline,))
    what = "constatării de către bancă" if source == "constatare" else "notificării"
    return Finding(
        "PAY-03", "PAY_REFUND_DUE",
        f"Rambursarea e datorată până la {fmt_dt(due)}: sfârșitul zilei lucrătoare care urmează {what} din "
        f"{fmt_dt(anchor)} (art. 173, C-70/25). Contul revine la starea dinaintea plății, cu data valutei cel târziu "
        "data debitării.",
        anchor_fields, data=data, deadlines=(deadline,))


@rule("PAY-15", title="Neglijența gravă nu permite refuzul sau amânarea rambursării",
      basis="CJUE C-70/25 Tukowiecka, 15.10.2026 (comunicatul CURIA 147/26); Legea 209/2019 art. 173",
      confidence=P, pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT),
      exceptions=("PAY_REFUSAL_ON_GN_BLOCKED", "PAY_RECOVERY_REVIEW"), aliases=("DSP-04",),
      tests=("TC-39", "TC-30", "DT-02", "EX-25"))
def pay_15_gross_negligence_guard(x: RuleContextExt, env: Env) -> Finding | None:
    """Neglijența gravă presupusă (date introduse pe un site fals, OTP divulgat, aprobare în aplicație, SCA
    reușită) nu dă dreptul băncii să refuze sau să amâne rambursarea T+1. Rambursarea și alocarea finală a
    pierderii sunt separate; recuperarea vine după, cu sarcina probei pe bancă (PAY-06)."""
    if not refund_track(x) or refund_withheld(x):
        return None
    indicators = gn_indicator_fields(x)
    if indicators:
        listed = "; ".join(GN_LABELS[f] for f in indicators)
        text = (f"Indiciile invocabile ca neglijență gravă ({listed}) nu schimbă rambursarea: C-70/25 cere "
                "rambursarea la termen. Ele contează doar pe pista de recuperare de după rambursare (PAY-06).")
    else:
        text = ("Nicio probă de neglijență gravă; oricum, neglijența gravă nu ar permite refuzul sau amânarea "
                "rambursării (C-70/25).")
    return Finding("PAY-15", "garda_c70_25", text, tuple(indicators), data={"indicators": indicators})


@rule("PAY-02", title="Sarcina probei e la bancă; folosirea instrumentului nu e neapărat suficientă",
      basis="Legea 209/2019 art. 171–172", confidence=P, pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT),
      exceptions=("PAY_SCA_EVIDENCE_MISSING",), aliases=("DSP-02",), tests=("TC-30", "EX-19", "DT-04"))
def pay_02_burden_of_proof(x: RuleContextExt, env: Env) -> Finding | None:
    """Dacă clientul neagă autorizarea, banca dovedește autentificarea, înregistrarea, contabilizarea și lipsa
    unei defecțiuni. Folosirea instrumentului sau o SCA reușită nu sunt, singure, probă. Fără jurnale nimic
    nu se impută clientului, iar recuperarea e blocată."""
    if not is_unauthorised(x):
        return None
    if not sca_evidence_present(x):
        return Finding(
            "PAY-02", "PAY_SCA_EVIDENCE_MISSING",
            "Lipsește jurnalul de autentificare (metoda, factorii, ce a afișat ecranul): nimic nu se impută "
            "clientului, iar recuperarea de la client e blocată (art. 171–172).", fields=("sca_performed",))
    if x.sca_performed is False:
        return Finding("PAY-02", "fara_sca",
                       "Banca nu a aplicat autentificarea strictă (SCA) la această plată: plata nu poate fi imputată "
                       "clientului (art. 171–172, art. 177 lit. d)).", fields=("sca_performed", "sca_method"))
    method = f" ({x.sca_method})" if x.sca_method else ""
    what, alone = ("Autentificarea reușită", "singură") if x.sca_performed else ("Jurnalul de autentificare", "singur")
    return Finding("PAY-02", "garda_proba",
                   f"{what}{method} nu e, {alone}, probă că plătitorul a autorizat plata sau a fost neglijent: "
                   "sarcina probei e a băncii (art. 171–172).",
                   fields=("sca_performed", "sca_method", "screen_showed_amount_and_payee"))


@rule("PAY-08", title="SCA la distanță cere legarea dinamică de sumă și beneficiar",
      basis="Legea 209/2019 art. 220", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      exceptions=("PAY_SCA_EVIDENCE_MISSING",), aliases=("DSP-10",), tests=("DT-03",))
def pay_08_dynamic_linking(x: RuleContextExt, env: Env) -> Finding | None:
    """O plată electronică la distanță cu SCA cere legarea dinamică de sumă și beneficiar. Dacă ecranul nu a
    afișat suma și beneficiarul plății contestate, autentificarea nu e probă pentru această plată."""
    if not is_unauthorised(x) or x.screen_showed_amount_and_payee is None:
        return None
    fields = ("screen_showed_amount_and_payee", "sca_method")
    if x.screen_showed_amount_and_payee is False and x.sca_performed is not False:
        return Finding("PAY-08", "PAY_SCA_EVIDENCE_MISSING",
                       "Ecranul de autentificare nu a afișat suma și beneficiarul plății contestate (fără legare "
                       "dinamică): autentificarea nu e probă pentru această plată (art. 220).", fields)
    if x.screen_showed_amount_and_payee is True:
        return Finding("PAY-08", "legare_dinamica",
                       "Ecranul de autentificare a afișat suma și beneficiarul (legare dinamică, art. 220); contează "
                       "doar pe pista de recuperare.", fields)
    return None


def art177_reasons(x: RuleContextExt) -> list[tuple[str, str, tuple[str, ...]]]:
    """Cazurile din art. 177 care se pot stabili din date: (b), (c), (d)."""
    out: list[tuple[str, str, tuple[str, ...]]] = []
    if x.staff_involvement:
        out.append(("b", "pierderea e cauzată de personalul sau agenții băncii", ("staff_involvement",)))
    if x.loss_reported_at is not None and to_local(x.loss_reported_at) <= to_local(x.executed_at):
        out.append(("c", f"plata a avut loc după notificarea pierderii sau furtului ({fmt_dt(x.loss_reported_at)})",
                    ("loss_reported_at", "executed_at")))
    if x.sca_required_by_issuer is False or x.sca_performed is False:
        field = "sca_required_by_issuer" if x.sca_required_by_issuer is False else "sca_performed"
        out.append(("d", "banca nu a solicitat autentificarea strictă (SCA)", (field,)))
    return out


@rule("PAY-04", title="Răspundere 0 pentru plătitorul care nu a fraudat (cazurile art. 177)",
      basis="Legea 209/2019 art. 177", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      exceptions=("DSP_STAFF_INVOLVEMENT",), aliases=("DSP-07",), tests=("TC-27", "DT-01", "DT-16", "DT-17"))
def pay_04_zero_liability(x: RuleContextExt, env: Env) -> Finding | None:
    """Plătitorul care nu a fraudat nu suportă nicio pierdere dacă: (a) pierderea nu putea fi detectată înainte
    de plată; (b) e cauzată de personalul, agenții sau externalizații băncii; (c) plata vine după notificarea
    pierderii sau furtului; (d) banca nu cere SCA; (e) lipsesc mijloacele de notificare permanentă. Din date se
    stabilesc (b), (c) și (d); (a) și (e) le apreciază omul."""
    if not is_unauthorised(x):
        return None
    reasons = art177_reasons(x)
    if not reasons:
        return None
    fields = tuple(f for _, _, fs in reasons for f in fs)
    listed = "; ".join(f"lit. {letter}) {text}" for letter, text, _ in reasons)
    staff = any(letter == "b" for letter, _, _ in reasons)
    text = f"Răspunderea clientului este 0 (art. 177): {listed}."
    if staff:
        text += " Implicarea unui angajat merge și la conformitate."
    letters = [r[0] for r in reasons]
    return Finding("PAY-04", "DSP_STAFF_INVOLVEMENT" if staff else "raspundere_0", text, fields,
                   data={"liability": 0.0, "letters": letters,
                         "hit_params": {"raspundere": 0.0, "moneda": x.amount.currency, "art_177_litere": letters}})


def payer_liability(loss: float, *, payer_fraud: bool, art177_case: bool, intent_or_gross_negligence_proven: bool,
                    lost_stolen_misappropriated: bool, cap: float) -> float:
    """Alocarea FINALĂ a pierderii, pe pista de recuperare de după rambursare (docs/context/11 §3).

    `cap` = 30 EUR exprimat în moneda pierderii (art. 179 alin. (1)).
    """
    if payer_fraud:
        return loss                    # art. 179 alin. (2)
    if art177_case:
        return 0.0                     # art. 177
    if intent_or_gross_negligence_proven:
        return loss                    # art. 179 alin. (2); proba e a băncii (art. 172)
    return min(loss, cap) if lost_stolen_misappropriated else 0.0   # art. 179 alin. (1)


@rule("PAY-05", title="Cel mult 30 EUR pentru instrument pierdut, furat sau însușit, fără fraudă",
      basis="Legea 209/2019 art. 179 alin. (1)", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      params=("eur_ron_rate",), aliases=("DSP-08",), tests=("TC-28", "DT-16"))
def pay_05_capped_liability(x: RuleContextExt, env: Env) -> Finding | None:
    """Plătitorul care nu a fraudat și nu și-a încălcat intenționat obligațiile din art. 166 suportă cel mult
    30 EUR (sau echivalentul în lei). Se aplică doar la alocarea finală, după rambursare; reținerea o decide
    omul. Cursul EUR/RON e parametru [U]."""
    if not is_unauthorised(x) or art177_reasons(x):
        return None
    cap = eur_cap_in(x.amount.currency, 30.0, env.p("eur_ron_rate"))
    if cap is None:
        return Finding("PAY-05", "curs_necunoscut",
                       f"Moneda {x.amount.currency}: plafonul de 30 EUR nu se poate converti; decide un om.",
                       ("amount",), data={"liability": None})
    liability = payer_liability(x.amount.value, payer_fraud=False, art177_case=False,
                                intent_or_gross_negligence_proven=False, lost_stolen_misappropriated=True, cap=cap)
    rate = "" if x.amount.currency.upper() == "EUR" else f", la cursul [U] de {env.p('eur_ron_rate')} lei/EUR"
    return Finding(
        "PAY-05", "raspundere_max_30_eur",
        f"Fără neglijență gravă dovedită, răspunderea clientului este de cel mult 30 EUR "
        f"({fmt_money(liability, x.amount.currency)}{rate}), conform art. 179 alin. (1); reținerea o decide omul, "
        "la alocarea finală.", ("amount",),
        data={"liability": liability, "cap": cap,
              "hit_params": {"raspundere": liability, "plafon": cap, "moneda": x.amount.currency}})


@rule("PAY-06", title="Pierderea integrală doar pentru fraudă sau neglijență gravă dovedite, după rambursare",
      basis="Legea 209/2019 art. 179 alin. (2)–(3); CJUE C-70/25", confidence=P, pack="PAY", source=SRC,
      questions=(Q_CLIENT,), exceptions=("PAY_RECOVERY_REVIEW",), aliases=("DSP-06",),
      tests=("DT-02", "TC-39", "DT-15"))
def pay_06_recovery_review(x: RuleContextExt, env: Env) -> Finding | None:
    """Plătitorul suportă toată pierderea doar pentru fraudă sau încălcarea intenționată ori din neglijență gravă
    a obligațiilor din art. 166, ținând cont de natura datelor de securitate și de circumstanțe. Se aplică doar pe
    pista de recuperare de după rambursare, cu probe documentate (PAY-02) și decizie umană; niciodată ca motiv de
    refuz sau de amânare a rambursării."""
    if not refund_track(x) or refund_withheld(x) or art177_reasons(x):
        return None
    if not (gross_negligence_case(x) and sca_evidence_present(x)):
        return None
    admits = [GN_LABELS[f] for f in ("client_admits_approving_in_app", "client_admits_sharing_credentials")
              if getattr(x, f) is True]
    return Finding(
        "PAY-06", "PAY_RECOVERY_REVIEW",
        f"Indicii de neglijență gravă: {GN_LABELS['screen_showed_amount_and_payee']}, iar {' și '.join(admits)}. "
        "Se deschide dosarul de recuperare, după rambursare: proba e a băncii, iar decizia e a omului "
        "(art. 179 alin. (2)–(3)).",
        ("screen_showed_amount_and_payee", "client_admits_approving_in_app", "client_admits_sharing_credentials"),
        data={"liability": x.amount.value,
              "hit_params": {"raspundere": x.amount.value, "moneda": x.amount.currency}})


@rule("PAY-07", title="Beneficiarul sau PSP-ul lui care nu acceptă SCA despăgubește banca",
      basis="Legea 209/2019 art. 178", confidence=P, pack="PAY", source=SRC, questions=(Q_ESCROC,),
      exceptions=("PAY_RECOVERY_FROM_PAYEE_PSP", "DSP_RULE_UNVERIFIED"), aliases=("DSP-09",), tests=("DT-20",))
def pay_07_payee_no_sca(x: RuleContextExt, env: Env) -> Finding | None:
    """Dacă beneficiarul sau PSP-ul lui nu acceptă SCA, rambursează prejudiciul cauzat băncii plătitorului.
    Mecanismul de recuperare nu e în note [U], deci e doar un flag; T+1 rămâne neschimbat."""
    if x.sca_not_applied_reason != "payee_no_sca":
        return None
    return Finding("PAY-07", "PAY_RECOVERY_FROM_PAYEE_PSP",
                   "Comerciantul sau PSP-ul lui nu a acceptat SCA: banca își poate recupera prejudiciul de la ei "
                   "(art. 178). Mecanismul nu e verificat (DSP_RULE_UNVERIFIED); termenul T+1 rămâne același.",
                   ("sca_not_applied_reason",))


@rule("PAY-09", title="Pre-autorizare: blocare doar cu acord și deblocare fără întârziere",
      basis="Legea 209/2019 art. 180–181", confidence=P, pack="PAY", source=SRC, questions=(Q_ESCROC, Q_ANSWER),
      exceptions=("PAY_PREAUTH_RELEASE_LATE",), aliases=("DSP-11",), tests=("DT-10",))
def pay_09_preauth(x: RuleContextExt, env: Env) -> Finding | None:
    """Fondurile se blochează doar cu acordul pentru suma exactă și se deblochează fără întârziere. O sumă
    blocată nedeblocată nu e chargeback: merge la operațiuni."""
    if not x.preauth_release_late:
        return None
    return Finding("PAY-09", "PAY_PREAUTH_RELEASE_LATE",
                   "Suma pre-autorizată nu a fost deblocată la timp (art. 180–181): corecția o face echipa de "
                   "operațiuni; nu e caz de chargeback.", ("preauth_release_late",))


@rule("PAY-10", title="Debitare directă: cerere în 8 săptămâni, răspuns în 10 zile lucrătoare",
      basis="Legea 209/2019 art. 182–185", confidence=P, pack="PAY", source=SRC, kind="calculator",
      exceptions=("PAY_DD_WINDOW_EXPIRED",), aliases=("DSP-12",), tests=("TC-32",))
def direct_debit_refund_due(debit_on: date, requested_on: date, cal: BusinessCalendar | None = None) -> date | None:
    """Termenul de răspuns la o cerere de rambursare pentru o debitare directă; `None` = fereastra de 8
    săptămâni s-a închis (`PAY_DD_WINDOW_EXPIRED`)."""
    from ..calendar_ro import add_business_days

    if requested_on > debit_on + timedelta(weeks=8):
        return None
    return add_business_days(requested_on, 10, cal)


def refund_can_be_withheld(payer_fraud_suspected: bool, grounds_sent_to_authority: bool) -> bool:
    """Art. 173 + C-70/25: singura excepție de la T+1. Neglijența gravă NU e parametru aici."""
    return payer_fraud_suspected and grounds_sent_to_authority


_REFUSAL_GN = {"neglijenta_grava", "refused_gross_negligence", "sca_reusita", "aprobat_in_aplicatie",
               "otp_divulgat", "date_divulgate", "instrument_folosit"}


def validate_refund_refusal(ctx: RuleContextExt, reason: str) -> GuardResult:
    """Garda PAY-15 pentru o cerere de refuz sau de amânare a rambursării (ex. din consola operatorului).

    Permis doar: excepția de fraudă (HOLD + autoritatea notificată, PAY-03) sau notificarea tardivă (PAY-01).
    Orice motiv de neglijență gravă e blocat (`PAY_REFUSAL_ON_GN_BLOCKED`).
    """
    from ..context import extend
    from ..facts import notified_in_time

    ctx = extend(ctx)
    key = reason.strip().lower()
    if key in ("frauda_client", "payer_fraud") and refund_withheld(ctx):
        return GuardResult(allowed=True, rule_id="PAY-03", code="PAY_FRAUD_SUSPECTED",
                           explanation="Reținerea e permisă: suspiciune de fraudă a clientului, comunicată autorității.")
    if key in ("tardiv", "late") and ctx.dispute_type == DisputeType.NEAUTORIZATA and not notified_in_time(ctx):
        return GuardResult(allowed=True, rule_id="PAY-01", code="PAY_LATE_NOTIFICATION",
                           explanation="Notificarea a venit după 13 luni (art. 169); răspunsul motivat îl aprobă un om.")
    if key in ("frauda_client", "payer_fraud"):
        return GuardResult(
            allowed=False, rule_id="PAY-03", code="PAY_FRAUD_NOTICE_MISSING",
            explanation="Suspiciunea de fraudă reține rambursarea doar dacă motivele au fost comunicate în scris "
                        "autorității competente; altfel se rambursează la termen.",
            next_actions=["trimite comunicarea scrisă către autoritate înainte de termenul T+1 sau rambursează"])
    label = "neglijență gravă" if key in _REFUSAL_GN else f"motivul „{reason}”"
    return GuardResult(
        allowed=False, rule_id="PAY-15", code="PAY_REFUSAL_ON_GN_BLOCKED",
        explanation=f"Refuzul sau amânarea rambursării pentru {label} e blocat: după C-70/25 doar suspiciunea de "
                    "fraudă a clientului, comunicată autorității, permite reținerea.",
        next_actions=["rambursează până la termenul T+1", "deschide dosarul de recuperare (pista B), cu probe (PAY-06)"])


__all__ = ["art177_reasons", "direct_debit_refund_due", "payer_liability", "refund_can_be_withheld",
           "validate_refund_refusal", "eur_cap_in"]
