"""Constructori de cazuri sintetice pentru testele motorului de reguli (toate datele sunt fictive)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from versoml.contracts import Channel, Decision, Deadline, DisputeType, Money, Question, RuleHit, RulesOutcome
from versoml.shared.rules import RuleContextExt
from versoml.shared.rules.params import defaults

TZ = ZoneInfo("Europe/Bucharest")
DEFAULTS = defaults()

# câmp → fact_id, ca la orchestrator (citările trebuie să vină doar de aici)
FACT_FIELDS = (
    "amount", "executed_at", "notified_at", "channel", "dispute_type", "sca_performed", "sca_method", "eci",
    "cavv_present", "screen_showed_amount_and_payee", "device_known", "seconds_after_click",
    "sim_swap_hours_before", "beneficiary_new", "merchant_mcc", "duplicate_of", "prior_disputes_12m",
    "client_fraud_score", "client_admits_sharing_credentials", "client_admits_approving_in_app", "hold_signal",
    "hold_authority_notified", "bank_noted_at", "beneficiary_iban", "processing_date", "prior_disputes_120d",
    "merchant_contact_proof", "intake_authenticated", "loss_reported_at", "staff_involvement",
    "sca_required_by_issuer", "complaint_received_at", "classification",
)
FACT_IDS = {f: f"EV-{i + 1:03d}" for i, f in enumerate(FACT_FIELDS)}


def ts(y: int, m: int, d: int, hh: int = 10, mm: int = 0, ss: int = 0) -> datetime:
    """Un moment în ora României."""
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ)


def eod(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 23, 59, 59, tzinfo=TZ)


def make_ctx(**kw: Any) -> RuleContextExt:
    """Un caz neautorizat, transfer de 1.000 RON, notificat la o oră după plată; `now` = notificarea."""
    base: dict[str, Any] = {
        "case_id": "CT-2026-TEST", "channel": Channel.TRANSFER, "dispute_type": DisputeType.NEAUTORIZATA,
        "amount": Money(value=1000.0, currency="RON"), "executed_at": ts(2026, 10, 27, 9),
        "notified_at": ts(2026, 10, 27, 10), "fact_ids": dict(FACT_IDS),
    }
    base.update(kw)
    if "now" not in base:
        base["now"] = base["notified_at"]
    return RuleContextExt(**base)


def decision(out: RulesOutcome, question: Question | str) -> Decision:
    q = question.value if isinstance(question, Question) else question
    return next(d for d in out.decisions if d.question.value == q)


def hit(out: RulesOutcome, rule_id: str) -> RuleHit | None:
    return next((h for h in out.hits if h.rule_id == rule_id), None)


def outcome(out: RulesOutcome, rule_id: str) -> str | None:
    h = hit(out, rule_id)
    return h.outcome if h else None


def deadline(out: RulesOutcome, rule_id: str, contains: str = "") -> Deadline:
    return next(d for d in out.deadlines if d.rule_id == rule_id and contains in d.name)


def t1(out: RulesOutcome) -> Decision:
    return decision(out, Question.RAMBURSARE_T1)
