"""Why a refund needs a human sign-off: the reasons come from the rule hits, not from a fixed sentence."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from versoml.zone_client.agents import escalation_reasons, refund_approval_prompt
from versoml.zone_client.fmt import fmt_date, fmt_datetime, fmt_deadline, money

AMBIGUOUS = "the dispute could fit more than one fraud pattern"
AUTH = "the authentication signals need a check"
CAP = "the amount is above the automatic refund limit"
RISK = "the customer has risk signals"

DEADLINE = "2026-10-29T21:59:59+00:00"   # 23:59:59 in Bucharest (EET, after the October clock change)


def hit(rule_id: str, outcome: str) -> dict:
    return {"rule_id": rule_id, "outcome": outcome, "title": "", "basis": "", "explanation": ""}


@pytest.mark.parametrize("outcome, reason", [
    ("DSP_AUTH_AMBIGUOUS", AMBIGUOUS),
    ("semnale_autentificare", AUTH),
    ("DSP_AMOUNT_REVIEW", CAP),
    ("semnale_de_risc", RISK),
])
def test_each_outcome_maps_to_its_reason(outcome, reason):
    assert escalation_reasons([hit("X-01", outcome)]) == [reason]


def test_reasons_follow_hit_order():
    hits = [hit("URM-03", "semnale_de_risc"), hit("DSP-50", "DSP_AUTH_AMBIGUOUS"), hit("DSP-59", "DSP_AMOUNT_REVIEW")]
    assert escalation_reasons(hits) == [RISK, AMBIGUOUS, CAP]


def test_duplicates_are_dropped():
    hits = [hit("DSP-59", "DSP_AMOUNT_REVIEW"), hit("URM-03", "semnale_de_risc"), hit("DSP-59", "DSP_AMOUNT_REVIEW")]
    assert escalation_reasons(hits) == [CAP, RISK]


def test_outcomes_that_do_not_escalate_are_ignored():
    hits = [hit("DSP-59", "sub_plafon"), hit("URM-03", "fara_semnale"), hit("PAY-03", "PAY_REFUND_DUE"),
            {"rule_id": "CMP-03"}, {}]
    assert escalation_reasons(hits) == []


def test_no_hits_means_no_reasons():
    assert escalation_reasons([]) == []
    assert escalation_reasons(None) == []


def test_escalation_reasons_does_not_mutate_its_input():
    hits = [hit("DSP-59", "DSP_AMOUNT_REVIEW")]
    before = [dict(h) for h in hits]
    escalation_reasons(hits)
    assert hits == before


def test_prompt_names_the_real_reasons():
    hits = [hit("DSP-50", "DSP_AUTH_AMBIGUOUS"), hit("URM-03", "semnale_de_risc")]
    assert refund_approval_prompt(3200.0, DEADLINE, hits) == (
        "Refund RON 3,200.00 by 29 Oct, 23:59? Sign-off is needed because the dispute could fit more than one "
        "fraud pattern and the customer has risk signals.")


def test_prompt_with_one_reason():
    prompt = refund_approval_prompt(6400.0, DEADLINE, [hit("DSP-59", "DSP_AMOUNT_REVIEW")])
    assert prompt == ("Refund RON 6,400.00 by 29 Oct, 23:59? Sign-off is needed because the amount is above the "
                      "automatic refund limit.")
    assert "risk signals" not in prompt


def test_prompt_with_three_reasons_lists_them_naturally():
    hits = [hit("DSP-50", "semnale_autentificare"), hit("DSP-59", "DSP_AMOUNT_REVIEW"), hit("URM-03", "semnale_de_risc")]
    assert refund_approval_prompt(5000.01, DEADLINE, hits).endswith(
        "because the authentication signals need a check, the amount is above the automatic refund limit and the "
        "customer has risk signals.")


def test_prompt_falls_back_to_the_generic_wording_without_reasons():
    prompt = refund_approval_prompt(3200.0, DEADLINE, [hit("DSP-59", "sub_plafon")])
    assert prompt.startswith("Refund RON 3,200.00 by 29 Oct, 23:59? Sign-off is needed because")
    assert "over the cap" in prompt and "risk signals" in prompt


def test_prompt_without_a_deadline():
    prompt = refund_approval_prompt(3200.0, None, [hit("DSP-59", "DSP_AMOUNT_REVIEW")])
    assert prompt.startswith("Refund RON 3,200.00 by the refund deadline?")


def test_money_and_dates_are_english():
    assert money(3200) == "RON 3,200.00"
    assert money(1234567.891, "EUR") == "EUR 1,234,567.89"
    assert money(0.5) == "RON 0.50"
    assert fmt_datetime(DEADLINE) == "29 Oct 2026, 23:59"
    assert fmt_datetime(datetime(2026, 7, 1, 9, 5, tzinfo=timezone.utc)) == "1 Jul 2026, 12:05"   # EEST, UTC+3
    assert fmt_date(date(2026, 10, 29)) == "29 Oct 2026"
    assert fmt_date("2026-10-28T23:30:00+00:00") == "29 Oct 2026"   # already the 29th in Bucharest
    assert fmt_deadline(DEADLINE) == "29 Oct, 23:59"
    assert fmt_datetime(None) == "" and fmt_date("not a date") == ""
