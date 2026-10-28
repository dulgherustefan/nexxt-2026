"""One plain sentence per decision, built from the rule IDs and the facts. Deterministic, no LLM.

"Refund now: the customer says it wasn't them and the bank can't show they approved this payment (PAY-03)". The
sentence explains the decision the rules engine already made; it never changes it.
"""

from __future__ import annotations


from versoml.zone_client.fmt import fmt_date, fmt_datetime, money

# the rule the sentence names, in order of preference, per verdict
PRIMARY_RULE = {
    "RAMBURSEAZA": ("PAY-03",),
    "RAMBURSEAZA_CU_APROBARE": ("DSP-59", "URM-03", "DSP-50", "DSP-57", "DSP-30", "PAY-03"),
    "EXCEPTIE_FRAUDA_CLIENT": ("PAY-03",),
    "RESPINGE_TARDIV": ("PAY-01",),
    "NU_SE_APLICA_T1": ("PAY-12", "DSP-16", "PAY-03"),
    "INFORMATII_SUPLIMENTARE": ("DSP-53", "DSP-32", "CMP-01"),
    "CHARGEBACK": ("DSP-52",),
    "RECHEMARE": ("REC-03", "REC-01", "REC-04"),
    "RECUPERARE_PROPUSA": ("PAY-06",),
    "NU_RECOMANDAM_RECUPERARE": ("PAY-04", "PAY-06", "REC-05", "DSP-52", "DSP-53", "PAY-02", "PAY-03"),
}
APPROVAL_WHY = {
    "DSP-59": "the amount is above the automatic refund limit",
    "URM-03": "the customer has risk signals",
    "DSP-50": "the authentication signals need a check",
    "DSP-57": "the complaint text needs a check against the bank's records",
    "DSP-30": "earlier undisputed card payments match this one",
    "PAY-03": "a fraud hold came in without a written notice to the authority",
}


def _primary(verdict: str, rule_ids: list[str]) -> str:
    for rid in PRIMARY_RULE.get(verdict, ()):
        if rid in rule_ids:
            return rid
    return rule_ids[0] if rule_ids else ""


def _unauthorized_clause(ctx: dict, extracted: dict) -> str:
    says = "the customer says it wasn't them" if extracted.get("claims_unauthorized") is not False \
        else "the customer disputes the payment"
    if ctx.get("screen_showed_amount_and_payee") is True:
        proof = "the law still requires the refund even though the screen showed the amount and the payee"
    elif ctx.get("sca_performed") is False:
        proof = "the bank can't show any strong authentication for it"
    else:
        proof = "the bank can't show they approved this payment"
    return f"{says} and {proof}"


def sentence(decision: dict, ctx: dict, extracted: dict | None = None, hits: list[dict] | None = None) -> dict:
    """{rule_id, decision, sentence} for one decision."""
    extracted = extracted or {}
    verdict = str(decision.get("decision") or "")
    question = str(decision.get("question") or "")
    rule_ids = list(decision.get("rule_ids") or [])
    rid = _primary(verdict, rule_ids)
    if verdict == "RAMBURSEAZA_CU_APROBARE":
        rid = next((r for r in PRIMARY_RULE[verdict] if r in rule_ids and _fired(hits, r)), "PAY-03"
                   if "PAY-03" in rule_ids else rid)
    amount = ctx.get("amount") or {}
    value = money(float(amount.get("value") or 0), amount.get("currency") or "RON")
    deadline = fmt_datetime(decision.get("deadline"))
    by = f" by {deadline}" if deadline else ""
    if question == "raspuns_reclamatie":
        if verdict == "INFORMATII_SUPLIMENTARE":
            text = ("Ask the customer for the missing details: " +
                    ", ".join(decision.get("missing_evidence") or ["the evidence the case still needs"])
                    + (f"; the written answer is due by {fmt_date(decision.get('deadline'))}" if deadline else ""))
        else:
            text = (f"Reply in writing{(' by ' + fmt_date(decision.get('deadline'))) if deadline else ''}, answering "
                    "every point and naming where the customer can complain")
        rid = rid if rid in ("DSP-53", "DSP-32") and verdict == "INFORMATII_SUPLIMENTARE" else (
            "CMP-01" if "CMP-01" in rule_ids else rid)
    elif question == "rambursare_t1":
        if verdict == "RAMBURSEAZA":
            text = f"Refund now: {_unauthorized_clause(ctx, extracted)}"
        elif verdict == "RAMBURSEAZA_CU_APROBARE":
            why = [APPROVAL_WHY[r] for r in ("DSP-59", "URM-03", "DSP-50", "DSP-57", "DSP-30", "PAY-03") if r in rule_ids
                   and _fired(hits, r)]
            text = (f"Refund once a person approves{by}, because "
                    + (" and ".join(why[:2]) if why else "the case needs a second look")
                    + f": {_unauthorized_clause(ctx, extracted)}")
        elif verdict == "EXCEPTIE_FRAUDA_CLIENT":
            text = "Hold the refund: an analyst confirmed a fraud suspicion and the authority was told in writing"
        elif verdict == "RESPINGE_TARDIV":
            text = "Reject the refund: the customer reported the payment more than 13 months after it was made"
        elif verdict == "NU_SE_APLICA_T1":
            kind = ctx.get("dispute_type")
            text = {"app": "No next-business-day refund: the customer approved the payment in the app, so the bank "
                           "tries to recover it instead",
                    "disputa_comerciant": "No next-business-day refund: this is a dispute with the merchant, so it "
                                          "goes through the card scheme",
                    "eroare_procesare": "No next-business-day refund: the merchant charged twice, so the duplicate is "
                                        "corrected"}.get(kind, "No next-business-day refund: the payment follows another "
                                                               "route")
        elif verdict == "INFORMATII_SUPLIMENTARE":
            text = ("Ask for more information: the payment could not be found in the bank's records, so a person "
                    "identifies it first" + (f" before {deadline}" if deadline else ""))
        else:
            text = f"Decision {verdict.replace('_', ' ').lower()}"
    elif question == "recuperare_client":
        text = ("Propose recovery from the customer: the screen showed the amount and the payee and the customer "
                "approved it or shared the codes; a person decides" if verdict == "RECUPERARE_PROPUSA" else
                "Do not recover the money from the customer: there is no proof of gross negligence")
        if verdict != "RECUPERARE_PROPUSA" and rid == "PAY-04":
            text = "Do not recover the money from the customer: the law sets the customer's liability at zero"
        if verdict != "RECUPERARE_PROPUSA" and "PAY-06" in rule_ids and not ctx.get("transaction_identified", True):
            text = "Do not recover the money from the customer: there is no refund to recover"
    elif question == "recuperare_escroc":
        if verdict == "RECHEMARE":
            text = ("Recall the transfer: the money went to an account at this bank, so it is blocked and returned "
                    "internally" if rid == "REC-03" else
                    f"Recall the transfer: ask the bank that received the {value} to return it")
        elif verdict == "CHARGEBACK":
            text = "Start a chargeback: the card payment had no strong authentication, so the card scheme can reverse it"
        elif rid == "DSP-53":
            text = "No recall or chargeback yet: the payment is not identified in the bank's records"
        elif rid == "REC-05":
            text = "No recall: the transfer is too old for a fraud recall"
        elif rid == "DSP-52":
            text = "No chargeback: the card payment was authenticated, so the card scheme does not reverse it"
        else:
            text = "No recovery from the scammer for now: a person decides the next step"
    else:
        text = f"Decision {verdict.replace('_', ' ').lower()}"
    return {"rule_id": rid, "question": question, "decision": verdict, "sentence": f"{text} ({rid})." if rid else f"{text}."}


def _fired(hits: list[dict] | None, rule_id: str) -> bool:
    """A rule that escalates only counts when its finding was the escalating one (DSP-59 under the cap does not)."""
    if hits is None:
        return True
    escalating = {"DSP-59": ("DSP_AMOUNT_REVIEW",), "URM-03": ("semnale_de_risc",),
                  "DSP-50": ("DSP_AUTH_AMBIGUOUS", "semnale_autentificare"), "DSP-57": ("DSP_SECURITY_SIGNAL",
                                                                                      "suma_de_confirmat"),
                  "DSP-30": ("DSP_CE3_MET",), "PAY-03": ("PAY_FRAUD_NOTICE_MISSING",)}
    wanted = escalating.get(rule_id)
    return any(h.get("rule_id") == rule_id and (not wanted or h.get("outcome") in wanted) for h in hits)


def decision_reasons(decisions: list[dict] | None, ctx: dict | None, extracted: dict | None = None,
                     hits: list[dict] | None = None) -> list[dict]:
    return [sentence(d, ctx or {}, extracted, hits) for d in decisions or []]


def scenario_phrase(scenario: str | None, dispute_type: str | None = None, match: dict | None = None) -> str | None:
    """The situation in a few plain words, for the case list."""
    phrases = {
        "phishing_link": "Paid after a fake link", "demo_t1": "Paid after a fake courier text",
        "card_ecom_fara_3ds": "Online card payment without 3-D Secure",
        "card_visa_secure": "Card payment approved with Visa Secure", "vishing_securitate": "Fake bank security call",
        "cont_sigur": "Told to move money to a 'safe account'", "sim_swap": "SIM swapped before the payment",
        "frauda_client": "Disputing an own payment", "reclamatie_tardiva": "Reported after 13 months",
        "plata_dubla": "Charged twice", "inel_carausi": "Several victims, one payee account",
        "injectie_document": "Complaint with hidden instructions", "marfa_nelivrata": "Goods not delivered",
    }
    if scenario and scenario in phrases:
        return phrases[scenario]
    if match is not None and not match.get("tx_id"):
        return "Payment not identified yet"
    return {"neautorizata": "Unauthorized payment", "app": "Approved under a scam", "disputa_comerciant":
            "Dispute with the merchant", "eroare_procesare": "Processing error"}.get(str(dispute_type or ""))
