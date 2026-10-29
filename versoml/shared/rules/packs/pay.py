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


@rule("PAY-12", title="An authorized push payment (APP) scam does not fall under art. 173 automatically",
      basis="Bitdefender consumer guide (docs/context/11 §2.5, PAY-12)", confidence=S, pack="PAY", source=SRC,
      questions=(Q_T1, Q_ESCROC, Q_ANSWER), exceptions=("PAY_APP_SCAM",), aliases=("DSP-13",),
      tests=("TC-31", "DT-04"))
def pay_12_app_scam(x: RuleContextExt, env: Env) -> Finding | None:
    """The customer authorized the payment after being tricked, so the refund regime for unauthorized
    payments does not apply automatically. Classification comes before any calculation. The case goes to the
    support route (DSP-51)."""
    if x.dispute_type != DisputeType.APP:
        return None
    return Finding(
        "PAY-12", "PAY_APP_SCAM",
        "The customer authorized the payment under manipulation. The next-business-day refund for unauthorized payments does "
        "not apply automatically (Law 209/2019, art. 173). The case goes to the support route: an urgent recall, "
        "a recommendation to file a police report, and a reasoned answer within 15 business days.",
        fields=("dispute_type", "client_admits_approving_in_app", "screen_showed_amount_and_payee"))


@rule("PAY-01", title="Notice within 13 months of the debit",
      basis="Law 209/2019, art. 169; opinion of AG Rantos in C-70/25 (CURIA press release 31/26)", confidence=P,
      pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT, Q_ANSWER), params=("undue_delay_days",),
      exceptions=("PAY_LATE_NOTIFICATION",), aliases=("DSP-01",), tests=("TC-29", "DT-05"))
def pay_01_notification_window(x: RuleContextExt, env: Env) -> Finding | None:
    """An unauthorized payment dispute is first checked against the 13 months from the debit. The limit does
    not apply if the bank did not provide the transaction information. The notes give no threshold for
    “without undue delay”. If the parameter is set and exceeded, the case goes to a human. It is not a reason
    to reject."""
    if not is_unauthorised(x):
        return None
    debit_on, notified_on = local_date(x.executed_at), local_date(x.notified_at)
    limit = add_months(debit_on, 13)
    months = months_between(debit_on, notified_on)
    deadline = Deadline(rule_id="PAY-01", name="Unauthorized payment notice limit (13 months)",
                        due_at=end_of_day(limit), basis="Law 209/2019, art. 169", business_days=False)
    fields = ("executed_at", "notified_at")
    if notified_on <= limit:
        undue = env.p("undue_delay_days")
        elapsed = (notified_on - debit_on).days
        review = undue is not None and elapsed > undue
        text = (f"The payment was debited on {fmt_d(debit_on)}. The customer reported it on {fmt_d(notified_on)}, "
                f"within the 13-month limit of {fmt_d(limit)} (Law 209/2019, art. 169).")
        if review:
            text += (f" The report came {elapsed} days after the debit, above the [U] threshold of {undue} days "
                     "for “without undue delay”. A human reviews it. The refund is not delayed.")
        return Finding("PAY-01", "in_termen", text, fields, data={"limit": limit, "undue_delay_review": review},
                       deadlines=(deadline,))
    if not x.tx_info_provided:
        return Finding(
            "PAY-01", "limita_nu_se_aplica",
            f"The report came {months} months after the debit, but the bank did not provide the transaction "
            "information. The 13-month limit does not apply (Law 209/2019, art. 169).",
            (*fields, "tx_info_provided"), data={"limit": limit, "undue_delay_review": False}, deadlines=(deadline,))
    return Finding(
        "PAY-01", "PAY_LATE_NOTIFICATION",
        f"The customer reported the payment on {fmt_d(notified_on)}, after the 13-month limit ({fmt_d(limit)}). "
        "The bank provided the transaction information, so it has no duty to correct the payment "
        "(Law 209/2019, art. 169). A human approves the reasoned answer.",
        (*fields, "tx_info_provided"), data={"limit": limit, "undue_delay_review": False}, deadlines=(deadline,))


@rule("PAY-03", title="Refund by the end of the next business day",
      basis="Law 209/2019, art. 173–174; CJEU ruling C-70/25 (PSD2 art. 73(1))", confidence=P, pack="PAY",
      source=SRC, questions=(Q_T1,), params=("refund_end_of_day", "bank_closure_days", "refund_anchor_mode",
                                              "competent_authority"),
      exceptions=("PAY_REFUND_DUE", "PAY_FRAUD_SUSPECTED", "PAY_FRAUD_NOTICE_MISSING"), aliases=("DSP-05",),
      tests=("TC-27", "TC-40", "DT-01", "DT-12"))
def pay_03_refund_due(x: RuleContextExt, env: Env) -> Finding | None:
    """For an unauthorized payment, the bank refunds immediately, and no later than the end of the business
    day after it noted the payment or was notified of it. The account returns to its previous state, with a
    value date no later than the debit date. The only exception: reasonable grounds to suspect fraud by the
    payer, sent in writing to the competent authority. Gross negligence is not an exception (PAY-15)."""
    if x.credit_fraud:
        return None
    if x.dispute_type != DisputeType.NEAUTORIZATA:
        kind = "a merchant dispute" if x.dispute_type == DisputeType.DISPUTA_COMERCIANT else (
            "a processing error" if x.dispute_type == DisputeType.EROARE_PROCESARE else "an authorized payment")
        return Finding("PAY-03", "nu_se_aplica",
                       f"Law 209/2019, art. 173 covers only unauthorized payments. This is {kind}, so it follows "
                       "another route (chargeback, correction or support).", fields=("dispute_type",))
    if not refund_track(x):
        return None
    anchor, source = refund_anchor(x, env.p("refund_anchor_mode"))
    due = refund_due(x, env)
    deadline = Deadline(rule_id="PAY-03", name="Refund by the end of the next business day", due_at=due,
                        basis="Law 209/2019, art. 173; CJEU ruling C-70/25", business_days=True)
    anchor_fields = ("bank_noted_at",) if source == "constatare" else ("notified_at",)
    authority = env.p("competent_authority") or "the competent national authority (BNR or ANPC, to be confirmed)"
    data = {"due": due, "anchor": anchor, "anchor_source": source}
    if refund_withheld(x):
        return Finding(
            "PAY-03", "PAY_FRAUD_SUSPECTED",
            "The bank withholds the refund. A human confirmed reasonable grounds to suspect fraud by the payer, "
            f"and the bank sent the grounds in writing to {authority}. This is the only exception that "
            "Law 209/2019, art. 173 and CJEU C-70/25 allow. A human investigation follows (four-eyes).",
            ("hold_signal", "hold_authority_notified"), data=data, deadlines=(deadline,))
    if x.hold_signal:
        return Finding(
            "PAY-03", "PAY_FRAUD_NOTICE_MISSING",
            "The bank suspects fraud by the payer, but it has not sent the grounds in writing to the authority. "
            f"Either the notice to {authority} goes out by {fmt_dt(due)}, or the bank refunds by the deadline.",
            ("hold_signal", "hold_authority_notified", *anchor_fields), data=data, deadlines=(deadline,))
    what = "the bank noted the fraud" if source == "constatare" else "the customer reported it"
    return Finding(
        "PAY-03", "PAY_REFUND_DUE",
        f"Refund due by {fmt_dt(due)}, the end of the business day after {what} on {fmt_dt(anchor)} "
        "(Law 209/2019, art. 173; CJEU C-70/25). The account returns to its state before the payment, with a "
        "value date no later than the debit date.",
        anchor_fields, data=data, deadlines=(deadline,))


@rule("PAY-15", title="Gross negligence does not allow refusing or delaying the refund",
      basis="CJEU ruling C-70/25 Tukowiecka, 15 Oct 2026 (CURIA press release 147/26); Law 209/2019, art. 173",
      confidence=P, pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT),
      exceptions=("PAY_REFUSAL_ON_GN_BLOCKED", "PAY_RECOVERY_REVIEW"), aliases=("DSP-04",),
      tests=("TC-39", "TC-30", "DT-02", "EX-25"))
def pay_15_gross_negligence_guard(x: RuleContextExt, env: Env) -> Finding | None:
    """Alleged gross negligence (details entered on a fake site, a shared OTP, approval in the app, a
    successful SCA) does not let the bank refuse or delay the next-business-day refund. The refund and the final loss
    allocation are separate. Recovery comes afterwards, and the bank carries the burden of proof (PAY-06)."""
    if not refund_track(x) or refund_withheld(x):
        return None
    indicators = gn_indicator_fields(x)
    if indicators:
        listed = "; ".join(GN_LABELS[f] for f in indicators)
        text = (f"Signs that could be cited as gross negligence do not change the refund: {listed}. "
                "CJEU C-70/25 requires the refund by the deadline. These signs matter only for the recovery track "
                "after the refund (PAY-06).")
    else:
        text = ("No evidence of gross negligence. Even with it, the bank could not refuse or delay the refund "
                "(CJEU C-70/25).")
    return Finding("PAY-15", "garda_c70_25", text, tuple(indicators), data={"indicators": indicators})


@rule("PAY-02", title="The bank carries the burden of proof; use of the payment instrument is not enough on its own",
      basis="Law 209/2019, art. 171–172", confidence=P, pack="PAY", source=SRC, questions=(Q_T1, Q_CLIENT),
      exceptions=("PAY_SCA_EVIDENCE_MISSING",), aliases=("DSP-02",), tests=("TC-30", "EX-19", "DT-04"))
def pay_02_burden_of_proof(x: RuleContextExt, env: Env) -> Finding | None:
    """If the customer denies authorizing the payment, the bank proves the authentication, recording and
    booking, and that nothing malfunctioned. Use of the instrument or a successful SCA is not proof on its
    own. Without logs, nothing is attributed to the customer, and recovery is blocked."""
    if not is_unauthorised(x):
        return None
    if not sca_evidence_present(x):
        return Finding(
            "PAY-02", "PAY_SCA_EVIDENCE_MISSING",
            "The authentication log is missing (method, factors, what the screen showed). Nothing can be "
            "attributed to the customer, and recovery from the customer is blocked (Law 209/2019, art. 171–172).",
            fields=("sca_performed",))
    if x.sca_performed is False:
        return Finding("PAY-02", "fara_sca",
                       "The bank did not apply strong customer authentication (SCA) to this payment. The payment "
                       "cannot be attributed to the customer (Law 209/2019, art. 171–172 and art. 177(d)).",
                       fields=("sca_performed", "sca_method"))
    method = f" ({x.sca_method})" if x.sca_method else ""
    what = "A successful authentication" if x.sca_performed else "The authentication log"
    return Finding("PAY-02", "garda_proba",
                   f"{what}{method} does not prove on its own that the payer authorized the payment or was "
                   "negligent. The bank carries the burden of proof (Law 209/2019, art. 171–172).",
                   fields=("sca_performed", "sca_method", "screen_showed_amount_and_payee"))


@rule("PAY-08", title="Remote SCA requires dynamic linking to the amount and beneficiary",
      basis="Law 209/2019, art. 220", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      exceptions=("PAY_SCA_EVIDENCE_MISSING",), aliases=("DSP-10",), tests=("DT-03",))
def pay_08_dynamic_linking(x: RuleContextExt, env: Env) -> Finding | None:
    """A remote electronic payment with SCA requires dynamic linking to the amount and beneficiary. If the
    screen did not show the amount and beneficiary of the disputed payment, the authentication does not
    prove this payment."""
    if not is_unauthorised(x) or x.screen_showed_amount_and_payee is None:
        return None
    fields = ("screen_showed_amount_and_payee", "sca_method")
    if x.screen_showed_amount_and_payee is False and x.sca_performed is not False:
        return Finding("PAY-08", "PAY_SCA_EVIDENCE_MISSING",
                       "The authentication screen did not show the amount and beneficiary of the disputed payment "
                       "(no dynamic linking). The authentication does not prove this payment "
                       "(Law 209/2019, art. 220).", fields)
    if x.screen_showed_amount_and_payee is True:
        return Finding("PAY-08", "legare_dinamica",
                       "The authentication screen showed the amount and beneficiary (dynamic linking, "
                       "Law 209/2019, art. 220). This matters only for the recovery track.", fields)
    return None


def art177_reasons(x: RuleContextExt) -> list[tuple[str, str, tuple[str, ...]]]:
    """Cazurile din art. 177 care se pot stabili din date: (b), (c), (d)."""
    out: list[tuple[str, str, tuple[str, ...]]] = []
    if x.staff_involvement:
        out.append(("b", "the loss was caused by the bank's staff or agents", ("staff_involvement",)))
    if x.loss_reported_at is not None and to_local(x.loss_reported_at) <= to_local(x.executed_at):
        out.append(("c", f"the payment happened after the loss or theft was reported ({fmt_dt(x.loss_reported_at)})",
                    ("loss_reported_at", "executed_at")))
    if x.sca_required_by_issuer is False or x.sca_performed is False:
        field = "sca_required_by_issuer" if x.sca_required_by_issuer is False else "sca_performed"
        out.append(("d", "the bank did not require strong customer authentication (SCA)", (field,)))
    return out


@rule("PAY-04", title="Zero liability for a payer who did not act fraudulently (art. 177 cases)",
      basis="Law 209/2019, art. 177", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      exceptions=("DSP_STAFF_INVOLVEMENT",), aliases=("DSP-07",), tests=("TC-27", "DT-01", "DT-16", "DT-17"))
def pay_04_zero_liability(x: RuleContextExt, env: Env) -> Finding | None:
    """A payer who did not act fraudulently bears no loss if: (a) the loss could not be detected before the
    payment; (b) the bank's staff, agents or outsourcers caused it; (c) the payment came after the loss or
    theft was reported; (d) the bank did not require SCA; (e) there was no permanent way to report. The data
    settles (b), (c) and (d). A human assesses (a) and (e)."""
    if not is_unauthorised(x):
        return None
    reasons = art177_reasons(x)
    if not reasons:
        return None
    fields = tuple(f for _, _, fs in reasons for f in fs)
    listed = "; ".join(f"({letter}) {text}" for letter, text, _ in reasons)
    staff = any(letter == "b" for letter, _, _ in reasons)
    text = f"The customer's liability is zero (Law 209/2019, art. 177): {listed}."
    if staff:
        text += " Compliance also reviews the staff involvement."
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


@rule("PAY-05", title="At most EUR 30 for a lost, stolen or misappropriated instrument, without fraud",
      basis="Law 209/2019, art. 179(1)", confidence=P, pack="PAY", source=SRC, questions=(Q_CLIENT,),
      params=("eur_ron_rate",), aliases=("DSP-08",), tests=("TC-28", "DT-16"))
def pay_05_capped_liability(x: RuleContextExt, env: Env) -> Finding | None:
    """A payer who did not act fraudulently and did not intentionally breach the duties in art. 166 bears at
    most EUR 30 (or the RON equivalent). This applies only to the final allocation, after the refund. A human
    decides whether to retain it. The EUR/RON rate is a [U] parameter."""
    if not is_unauthorised(x) or art177_reasons(x):
        return None
    cap = eur_cap_in(x.amount.currency, 30.0, env.p("eur_ron_rate"))
    if cap is None:
        return Finding("PAY-05", "curs_necunoscut",
                       f"The EUR 30 cap cannot be converted to {x.amount.currency}. A human decides.",
                       ("amount",), data={"liability": None})
    liability = payer_liability(x.amount.value, payer_fraud=False, art177_case=False,
                                intent_or_gross_negligence_proven=False, lost_stolen_misappropriated=True, cap=cap)
    rate = "" if x.amount.currency.upper() == "EUR" else f", at the [U] rate of {env.p('eur_ron_rate')} RON per EUR"
    # the bank either keeps the share back from the refund or waives it (the [U] parameter retain_payer_liability)
    kept = bool(env.p("retain_payer_liability"))
    return Finding(
        "PAY-05", "raspundere_max_30_eur",
        f"Without proven gross negligence, the customer's liability is at most EUR 30 "
        f"({fmt_money(liability, x.amount.currency)}{rate}) under Law 209/2019, art. 179(1). "
        + ("The refund keeps it back." if kept else
           "The bank waives it in the refund; a human can still claim it at the final loss allocation."),
        ("amount",),
        data={"liability": liability, "cap": cap, "retained": kept,
              "hit_params": {"raspundere": liability, "plafon": cap, "moneda": x.amount.currency}})


@rule("PAY-06", title="Full loss only for proven fraud or gross negligence, after the refund",
      basis="Law 209/2019, art. 179(2)–(3); CJEU ruling C-70/25", confidence=P, pack="PAY", source=SRC,
      questions=(Q_CLIENT,), exceptions=("PAY_RECOVERY_REVIEW",), aliases=("DSP-06",),
      tests=("DT-02", "TC-39", "DT-15"))
def pay_06_recovery_review(x: RuleContextExt, env: Env) -> Finding | None:
    """The payer bears the full loss only for fraud, or for breaching the duties in art. 166 intentionally or
    with gross negligence, taking into account the nature of the security data and the circumstances. This
    applies only on the recovery track after the refund, with documented evidence (PAY-02) and a human
    decision. It is never a reason to refuse or delay the refund."""
    if not refund_track(x) or refund_withheld(x) or art177_reasons(x):
        return None
    if not (gross_negligence_case(x) and sca_evidence_present(x)):
        return None
    admits = [GN_LABELS[f] for f in ("client_admits_approving_in_app", "client_admits_sharing_credentials")
              if getattr(x, f) is True]
    return Finding(
        "PAY-06", "PAY_RECOVERY_REVIEW",
        f"Signs of gross negligence: {GN_LABELS['screen_showed_amount_and_payee']}, and {' and '.join(admits)}. "
        "A recovery file opens after the refund. The bank carries the burden of proof, and a human decides "
        "(Law 209/2019, art. 179(2)–(3)).",
        ("screen_showed_amount_and_payee", "client_admits_approving_in_app", "client_admits_sharing_credentials"),
        data={"liability": x.amount.value,
              "hit_params": {"raspundere": x.amount.value, "moneda": x.amount.currency}})


@rule("PAY-07", title="A beneficiary or its PSP that does not accept SCA compensates the bank",
      basis="Law 209/2019, art. 178", confidence=P, pack="PAY", source=SRC, questions=(Q_ESCROC,),
      exceptions=("PAY_RECOVERY_FROM_PAYEE_PSP", "DSP_RULE_UNVERIFIED"), aliases=("DSP-09",), tests=("DT-20",))
def pay_07_payee_no_sca(x: RuleContextExt, env: Env) -> Finding | None:
    """If the beneficiary or its PSP does not accept SCA, it repays the loss caused to the payer's bank. The
    notes do not cover the recovery mechanism [U], so this is only a flag. The refund deadline does not change."""
    if x.sca_not_applied_reason != "payee_no_sca":
        return None
    return Finding("PAY-07", "PAY_RECOVERY_FROM_PAYEE_PSP",
                   "The merchant or its PSP did not accept SCA. The bank can recover its loss from them "
                   "(Law 209/2019, art. 178). The mechanism is not verified (DSP_RULE_UNVERIFIED). The refund "
                   "deadline stays the same.",
                   ("sca_not_applied_reason",))


@rule("PAY-09", title="Pre-authorization: block funds only with consent and release them without delay",
      basis="Law 209/2019, art. 180–181", confidence=P, pack="PAY", source=SRC, questions=(Q_ESCROC, Q_ANSWER),
      exceptions=("PAY_PREAUTH_RELEASE_LATE",), aliases=("DSP-11",), tests=("DT-10",))
def pay_09_preauth(x: RuleContextExt, env: Env) -> Finding | None:
    """Funds are blocked only with consent for the exact amount, and released without delay. A blocked
    amount that was not released is not a chargeback. It goes to operations."""
    if not x.preauth_release_late:
        return None
    return Finding("PAY-09", "PAY_PREAUTH_RELEASE_LATE",
                   "The pre-authorized amount was not released in time (Law 209/2019, art. 180–181). The "
                   "operations team corrects it. This is not a chargeback case.", ("preauth_release_late",))


def direct_debit_refund_due(debit_on: date, requested_on: date, cal: BusinessCalendar | None = None) -> date | None:
    """PAY-10: termenul de răspuns la o cerere de rambursare a unui debit direct. `None` = fereastra de 8 săptămâni
    s-a închis (`PAY_DD_WINDOW_EXPIRED`)."""
    from ..calendar_ro import add_business_days

    if requested_on > debit_on + timedelta(weeks=8):
        return None
    return add_business_days(requested_on, 10, cal)


@rule("PAY-10", title="Direct debit: request within 8 weeks, answer within 10 business days",
      basis="Law 209/2019, art. 182–185", confidence=P, pack="PAY", source=SRC, questions=(Q_T1, Q_ESCROC),
      exceptions=("PAY_DD_REFUND", "PAY_DD_WINDOW_EXPIRED"), aliases=("DSP-12",), tests=("TC-32", "DD-01"))
def pay_10_direct_debit(x: RuleContextExt, env: Env) -> Finding | None:
    """A payer can ask for the refund of an authorized direct debit within 8 weeks of the debit, and the bank
    answers within 10 business days. The route is the refund through the direct debit scheme, not a recall of a
    credit transfer. For a debit in euro under the SEPA core scheme the refund needs no reason; in other currencies
    the conditions of art. 182 apply and a human checks them. A debit with no mandate is an unauthorized payment
    (art. 173) and keeps the next-business-day refund; a debit authorized under manipulation follows the APP route,
    where a human weighs the same 8-week right."""
    if x.channel.value != "direct_debit" or x.credit_fraud or x.dispute_type not in (
            DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        return None
    debit_on, requested_on = local_date(x.executed_at), local_date(x.notified_at)
    due = direct_debit_refund_due(debit_on, requested_on, env.cal)
    closes = debit_on + timedelta(weeks=8)
    fields = ("executed_at", "notified_at", "channel")
    if due is None:
        return Finding("PAY-10", "PAY_DD_WINDOW_EXPIRED",
                       f"The refund request came on {fmt_d(requested_on)}, after the 8-week window for the direct "
                       f"debit closed on {fmt_d(closes)} (Law 209/2019, art. 182–185). A human answers the complaint; "
                       "a debit with no valid mandate can still be an unauthorized payment.", fields,
                       data={"due": None, "closes": closes})
    sepa = x.amount.currency.upper() == "EUR"
    condition = ("No reason is needed (SEPA core direct debit in euro)." if sepa else
                 "A human checks the conditions of art. 182 (the mandate did not state the exact amount, and the "
                 "amount exceeded what the payer could reasonably expect), unless the contract gives an unconditional "
                 "right.")
    return Finding("PAY-10", "PAY_DD_REFUND",
                   f"The direct debit refund was requested within 8 weeks of the debit (by {fmt_d(closes)}). The bank "
                   f"refunds or answers with reasons by {fmt_d(due)}, 10 business days from the request "
                   f"(Law 209/2019, art. 182–185). {condition} The amount is claimed from the payee's bank through "
                   "the direct debit scheme, not by a credit transfer recall.", fields,
                   data={"due": end_of_day(due), "closes": closes, "unconditional": sepa},
                   deadlines=(Deadline(rule_id="PAY-10", name="Direct debit refund answer (10 business days)",
                                       due_at=end_of_day(due), basis="Law 209/2019, art. 182–185",
                                       business_days=True),))


def refund_can_be_withheld(payer_fraud_suspected: bool, grounds_sent_to_authority: bool) -> bool:
    """Art. 173 + C-70/25: the only exception to the next-business-day refund. Gross negligence is NOT a parameter here."""
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
                           explanation="Withholding is allowed: the bank suspects customer fraud and notified "
                                       "the authority.")
    if key in ("tardiv", "late") and ctx.dispute_type == DisputeType.NEAUTORIZATA and not notified_in_time(ctx):
        return GuardResult(allowed=True, rule_id="PAY-01", code="PAY_LATE_NOTIFICATION",
                           explanation="The customer reported the payment after 13 months (Law 209/2019, "
                                       "art. 169). A human approves the reasoned answer.")
    if key in ("frauda_client", "payer_fraud"):
        return GuardResult(
            allowed=False, rule_id="PAY-03", code="PAY_FRAUD_NOTICE_MISSING",
            explanation="A fraud suspicion withholds the refund only if the bank sent the grounds in writing to the "
                        "competent authority. Otherwise the bank refunds by the deadline.",
            next_actions=["Send the written notice to the authority before the refund deadline, or refund"])
    label = "gross negligence" if key in _REFUSAL_GN else f"the reason “{reason}”"
    return GuardResult(
        allowed=False, rule_id="PAY-15", code="PAY_REFUSAL_ON_GN_BLOCKED",
        explanation=f"Refusing or delaying the refund for {label} is blocked. Under CJEU C-70/25, only a "
                    "suspicion of customer fraud reported to the authority allows withholding.",
        next_actions=["Refund by the refund deadline", "Open the recovery file (track B) with evidence (PAY-06)"])


__all__ = ["art177_reasons", "direct_debit_refund_due", "payer_liability", "refund_can_be_withheld",
           "validate_refund_refusal", "eur_cap_in"]
