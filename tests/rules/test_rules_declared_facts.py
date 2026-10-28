"""DSP-53 on a free-form complaint the intake could not match: the case rests on the customer's statements, nothing is
refunded or refused on them, a person identifies the payment and the bank asks for the missing details."""

from __future__ import annotations

from rules_testkit import DEFAULTS, decision, eod, make_ctx, outcome, t1, ts
from versoml.contracts import DisputeType, Money, Question, Verdict
from versoml.shared.rules import evaluate, get_params
from versoml.shared.rules.registry import get_rule


def declared(**kw):
    base = dict(executed_at=ts(2026, 10, 27, 18), notified_at=ts(2026, 10, 28, 10), amount=Money(value=3200.0),
                transaction_identified=False, customer_identified=True)
    base.update(kw)
    return make_ctx(**base)


def test_unmatched_payment_asks_for_information_and_keeps_the_refund_clock():
    out = evaluate(declared(), DEFAULTS)
    d = t1(out)
    assert d.decision == Verdict.INFORMATII_SUPLIMENTARE and d.requires_human and d.decided_by == "rules+human"
    assert d.rule_ids[0] == "DSP-53" and "PAY-03" in d.rule_ids
    assert d.deadline == eod(2026, 10, 29)                      # the refund clock still runs from the report
    assert d.missing_evidence == ["the payment details (date, amount and payee)"]
    assert outcome(out, "DSP-53") == "DSP_EVIDENCE_MISSING"


def test_unknown_customer_adds_the_identification_gap():
    out = evaluate(declared(customer_identified=False), DEFAULTS)
    assert t1(out).missing_evidence == [
        "the customer's identification (the phone number or IBAN registered with the bank)",
        "the payment details (date, amount and payee)"]
    answer = decision(out, Question.RASPUNS_RECLAMATIE)
    assert answer.decision == Verdict.INFORMATII_SUPLIMENTARE and answer.requires_human
    assert "DSP-53" in answer.rule_ids and "CMP-01" in answer.rule_ids and answer.deadline is not None
    assert "the payment details (date, amount and payee)" in answer.missing_evidence


def test_no_recovery_and_no_rule_runs_on_the_statements():
    # a declared date 14 months back, an amount over the cap: neither a late rejection nor a cap review
    out = evaluate(declared(executed_at=ts(2025, 8, 1), amount=Money(value=9000.0)), DEFAULTS)
    assert t1(out).decision == Verdict.INFORMATII_SUPLIMENTARE
    fired = {h.rule_id for h in out.hits}
    assert "PAY-01" not in fired and "DSP-59" not in fired and "URM-03" not in fired
    assert decision(out, Question.RECUPERARE_ESCROC).decision == Verdict.NU_RECOMANDAM_RECUPERARE
    assert decision(out, Question.RECUPERARE_CLIENT).decision == Verdict.NU_RECOMANDAM_RECUPERARE


def test_app_declared_has_no_refund_deadline():
    d = t1(evaluate(declared(dispute_type=DisputeType.APP), DEFAULTS))
    assert d.decision == Verdict.INFORMATII_SUPLIMENTARE and d.deadline is None and "PAY-03" not in d.rule_ids


def test_identified_payment_is_unchanged():
    assert t1(evaluate(make_ctx(amount=Money(value=3200.0)), DEFAULTS)).decision == Verdict.RAMBURSEAZA


def test_match_thresholds_are_u_parameters_of_dsp_53():
    params = get_params()
    assert params["match_auto_min_points"] == 50 and params["match_auto_min_margin"] == 20
    assert {"match_auto_min_points", "match_auto_min_margin", "match_candidate_min_points"} <= set(get_rule("DSP-53").params)
