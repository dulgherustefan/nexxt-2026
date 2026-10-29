"""Intrările și ieșirile motorului care nu sunt (încă) în `versoml/contracts.py`.

- `RuleContextExt` extinde `RuleContext` cu faptele de care au nevoie regulile DSP, CMP și REC
  (ex. IBAN-ul beneficiarului, data procesării, ancora constatării). Toate au valori implicite neutre:
  un `RuleContext` simplu dă exact rezultatul de bază. Câmpurile sunt raportate platformei, ca să intre
  în contract.
- `AmlRuleContext` și `AmlRulesOutcome` sunt pentru zona AML (`evaluate_aml`): doar fapte obiective
  despre conturi și tranzacții, fără date despre victimă.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from versoml.contracts import Decision, Deadline, Money, RuleContext, RuleHit


class RuleContextExt(RuleContext):
    """`RuleContext` plus faptele opționale folosite de regulile de dispută, reclamații și rechemare."""

    # clasificare (Classification.ambiguous)                                         DSP-50
    classification_ambiguous: bool = False
    # ceasuri                                                                         DSP-58, CMP-01, PAY-01
    bank_noted_at: datetime | None = None            # confirmarea echipei de fraudă (nu o alertă)
    complaint_received_at: datetime | None = None    # implicit: notified_at
    tx_info_provided: bool = True                    # art. 169: limita cade dacă banca nu a informat
    final_answer_sent_at: datetime | None = None
    holding_reply_sent_at: datetime | None = None    # CMP-02
    delay_reason_external: bool | None = None        # CMP-02: motiv independent de bancă
    # transfer                                                                        REC-01..REC-05
    beneficiary_iban: str | None = None
    # card și schemă                                                                  DSP-20..DSP-53
    card_scheme: Literal["visa", "mastercard"] | None = None
    card_present: bool | None = None
    processing_date: date | None = None
    visa_condition: str | None = None                # condiția propusă de clasificator (ex. "13.1")
    prior_disputes_120d: int | None = None
    visa_secure_auth_confirmation: bool | None = None
    wallet_token: bool | None = None
    tavv_present: bool | None = None
    cvm_approved: bool | None = None
    purchase_type: Literal["goods", "services", "crypto_nft", "atm_cash"] | None = None
    cardholder_participated: bool | None = None
    ce3_met: bool | None = None                      # rezultatul `ce3_check` (DSP-30)
    expected_delivery_date: date | None = None
    merchant_contact_proof: bool | None = None
    intake_authenticated: bool | None = None
    signed_letter: bool | None = None
    existing_dispute_for_txn: bool = False
    preauth_release_late: bool = False
    # răspundere                                                                      PAY-04, PAY-07
    loss_reported_at: datetime | None = None
    staff_involvement: bool = False
    sca_required_by_issuer: bool | None = None
    sca_not_applied_reason: str | None = None        # ex. "payee_no_sca"
    police_report_filed: bool | None = None
    credit_fraud: bool = False                       # credit sau card de credit pe numele victimei (DSP-16)
    # identificarea (reclamație liberă)                                               DSP-53
    # False = plata (sau clientul) nu a fost găsită în evidențele băncii: contextul are doar declarațiile clientului
    customer_identified: bool = True
    transaction_identified: bool = True
    # textul neîncrezut                                                               DSP-57, DP-02
    injection_suspected: bool = False
    claimed_amount: float | None = None              # suma din text: doar comparată, niciodată folosită
    claimed_amount_low_confidence: bool = False
    customer_claims_unauthorised: bool | None = None  # clientul spune că nu a făcut plata (extragerea)
    llm_mode: str | None = None                      # cum s-a citit reclamația: live, replay sau offline (regex)


def extend(ctx: RuleContext, **flags: Any) -> RuleContextExt:
    """Contextul extins; un `RuleContext` simplu primește valorile implicite neutre."""
    base = ctx if isinstance(ctx, RuleContextExt) else RuleContextExt.model_validate(ctx.model_dump())
    return base.model_copy(update=flags) if flags else base


class GuardResult(BaseModel):
    """Rezultatul unei gărzi (ex. o cerere de refuz sau de reversare)."""

    allowed: bool
    rule_id: str
    code: str
    explanation: str
    next_actions: list[str] = Field(default_factory=list)


class AmlRuleContext(BaseModel):
    """Intrarea regulilor AML: fapte obiective despre pistă, conturi și ceasurile ONPCSB."""

    model_config = ConfigDict(extra="forbid")

    lead_id: str
    now: datetime
    # indicii obiective (din graf, M5, OSINT), fără date demografice                  URM-04
    cases: int = 0
    victims: int = 0
    top_mule_score: float | None = None
    typologies: list[str] = Field(default_factory=list)
    osint_red_flags: int = 0
    amount_total: float | None = None
    features_used: list[str] = Field(default_factory=list)   # trăsăturile scorului (URM-01)
    # suspiciunea confirmată de analist și ceasurile art. 8                          AML-01..AML-06
    suspicion_confirmed: bool = False
    onpcsb_request: bool = False
    transaction_executed: bool = True
    str_registered_at: datetime | None = None
    str_returned_at: datetime | None = None
    str_corrected_registered_at: datetime | None = None
    suspension_start: datetime | None = None
    suspension_hours: int | None = None
    extension_start: datetime | None = None
    extension_hours: int | None = None
    extensions_requested: int = 0
    # rapoarte de prag (art. 7)                                                       AML-07..AML-09
    cash_linked: Money | None = None
    external_transfers_linked: Money | None = None
    remittances_linked: Money | None = None
    threshold_tx_at: datetime | None = None
    fact_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("typologies", "features_used", mode="before")
    @classmethod
    def _drop_empty(cls, value: Any) -> list[str]:
        return [str(v) for v in (value or []) if v]


class AmlRulesOutcome(BaseModel):
    lead_id: str
    decisions: list[Decision] = Field(default_factory=list)
    hits: list[RuleHit] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    tx_hold_until: datetime | None = None
    constraints: list[str] = Field(default_factory=list)
    params_used: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "1"
