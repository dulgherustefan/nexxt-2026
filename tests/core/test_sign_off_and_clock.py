"""The human gate and the clock: what the bank's records outweigh, what a log leaves unknown, why a person signed,
where the money goes back, and which cases are close to or past their deadline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from tests.rules.rules_testkit import make_ctx, ts
from versoml.contracts import DisputeType, Money
from versoml.shared.rules import params as rule_params
from versoml.zone_client import agents as A
from versoml.zone_client.service import MANUAL_QUEUE, ClientService, deadline_escalation

MERCHANT = {"dispute_type": "disputa_comerciant", "ambiguous": False}


class _Cases:
    def __init__(self, docs: list[dict]):
        self.docs = {d["case_id"]: d for d in docs}

    def all(self) -> list[dict]:
        return list(self.docs.values())

    def get(self, case_id: str) -> dict | None:
        return self.docs.get(case_id)

    def update(self, case_id: str, patch: dict) -> None:
        self.docs[case_id].update(patch)


@pytest.fixture(autouse=True)
def default_params(tmp_path, monkeypatch):
    """The rules' default parameters, whatever var/rules_params.json says."""
    monkeypatch.setattr(rule_params, "params_path", lambda: tmp_path / "rules_params.json")


# ---------------------------------------------------------------- the text against the bank's records


def test_a_merchant_label_never_outweighs_the_signs_of_an_unauthorised_payment():
    kind, ambiguous, _ = A.reconcile_type(MERCHANT, {"sca_performed": True, "device_known": True}, {})
    assert (kind, ambiguous) == (DisputeType.DISPUTA_COMERCIANT, False)
    for records, extracted in (({"sca_performed": False}, {}), ({"device_known": False}, {}),
                               ({"sca_performed": True}, {"claims_unauthorized": True})):
        kind, ambiguous, reason = A.reconcile_type(MERCHANT, records, extracted)
        assert kind == DisputeType.NEAUTORIZATA and ambiguous, records
        assert reason.startswith("the text suggests merchant dispute but") and "a person confirms" in reason
    # a duplicate in bank-core is a processing error, whatever the text says
    duplicate = A.reconcile_type({"dispute_type": "neautorizata"}, {"duplicate_of": "TX-1"}, {"claims_unauthorized": True})
    assert duplicate[0] == DisputeType.EROARE_PROCESARE


def test_an_sca_attempt_without_a_result_is_unknown_and_goes_to_a_person():
    sca = A.sca_from_events([{"purpose": "payment", "method": "app_push", "screen_showed_amount_and_payee": True}])
    assert sca["sca_performed"] is None and sca["sca_unreadable"] is True
    ok = A.sca_from_events([{"purpose": "payment", "method": "app_push"},
                            {"purpose": "payment", "method": "app_push", "result": "approved"}])
    assert ok["sca_performed"] is True and ok["sca_unreadable"] is False
    kind, ambiguous, reason = A.reconcile_type({"dispute_type": "neautorizata"}, {"sca_unreadable": True}, {})
    assert kind == DisputeType.NEAUTORIZATA and ambiguous and "no result in the log" in reason


def test_a_device_without_history_is_unknown_not_trusted():
    paid = ts(2026, 10, 28, 12)
    mine = {"device_id": "D1", "trusted": True, "enrolled_at": (paid - timedelta(days=30)).isoformat()}
    assert A.device_known_from([mine], "D1", paid) is True
    assert A.device_known_from([], "D1", paid) is None                  # nothing on file to compare with
    assert A.device_known_from([mine], None, paid) is None
    assert A.device_known_from([mine], "D2", paid) is False             # not one of the customer's devices
    assert A.device_known_from([{**mine, "trusted": None}], "D1", paid) is None
    assert A.device_known_from([{**mine, "enrolled_at": None}], "D1", paid) is None
    assert A.device_known_from([{**mine, "trusted": False}], "D1", paid) is False
    assert A.device_known_from([{**mine, "enrolled_at": (paid - timedelta(minutes=5)).isoformat()}], "D1", paid) is False
    # an unknown device never makes the payment "approved in the app"
    kind, ambiguous, _ = A.reconcile_type({"dispute_type": "app"}, {"screen_showed_amount_and_payee": True,
                                                                    "device_known": None, "device_unreadable": True}, {})
    assert kind == DisputeType.NEAUTORIZATA and ambiguous


# ---------------------------------------------------------------- signatures


def test_every_signature_carries_a_reason():
    assert A.signature_reason("approve", None, None, "Refund?") == {
        "reason_code": "FACTS_CONFIRMED", "reason_text": "Refund?", "reason_from_note": False}
    assert A.signature_reason("reject", "fraud_suspected", "  Same IBAN as two other cases  ", "Refund?") == {
        "reason_code": "FRAUD_SUSPECTED", "reason_text": "Same IBAN as two other cases", "reason_from_note": True}
    assert "error" in A.signature_reason("approve", "FRAUD_SUSPECTED", None, "Refund?")      # does not fit approve
    assert "error" in A.signature_reason("reject", "OTHER", " ", "Refund?")                 # OTHER needs a text
    assert "error" in A.signature_reason("reject", None, "x" * 1001, "Refund?")


def test_the_service_checks_the_reason_before_it_resumes_the_case():
    doc = {"case_id": "CT-1", "status": "ASTEAPTA_APROBARE", "run_id": "RUN-1",
           "interrupt": {"pending": True, "kind": "semnatura_decizie", "verdict": "RESPINGE_TARDIV",
                         "prompt": "Confirm the rejection?"}}
    cases = _Cases([doc])
    svc = ClientService(SimpleNamespace(cases=cases))
    resumed = []
    svc._drive = lambda case_id, run_id, payload: payload
    svc._spawn = resumed.append
    bad = asyncio.run(svc.approve("CT-1", "reject", None, "OPERATOR-01", reason_code="OTHER"))
    assert bad["ok"] is False and "OTHER" in bad["detail"]
    assert not resumed and not cases.docs["CT-1"]["interrupt"].get("resuming")
    assert asyncio.run(svc.approve("CT-1", "approve", "Reported 14 months on", "OPERATOR-01"))["ok"]
    [command] = resumed
    assert command.resume["reason_code"] == "FACTS_CONFIRMED" and command.resume["reason_text"] == "Reported 14 months on"


def test_a_route_decision_tells_the_person_what_each_answer_does():
    text = A.route_prompt({"dispute_type": "app"}, "2026-10-29T21:59:59+00:00")
    assert "does not apply" in text and "GDPR art. 22" in text and text.endswith("refunded by 29 Oct, 23:59.")


def test_not_confirming_an_unfavourable_decision_makes_it_a_refund_on_that_signature():
    decisions = [{"question": "rambursare_t1", "decision": "NU_SE_APLICA_T1", "rationale": []},
                 {"question": "raspuns_reclamatie", "decision": "NU_SE_APLICA_T1"},
                 {"question": "recuperare_escroc", "decision": "RECHEMARE"}]
    out = A._overridden({"decisions": decisions}, "NU_SE_APLICA_T1", "OPERATOR-01")
    assert [d["decision"] for d in out] == ["RAMBURSEAZA_CU_APROBARE", "RAMBURSEAZA_CU_APROBARE", "RECHEMARE"]
    assert out[0]["decided_by"] == "human" and "OPERATOR-01 did not confirm" in out[0]["rationale"][-1]["text"]
    assert decisions[0]["decision"] == "NU_SE_APLICA_T1"                # the engine's own decision is untouched


# ---------------------------------------------------------------- the money


def test_the_refund_is_in_full_unless_the_bank_keeps_the_customers_share():
    ctx = make_ctx(amount=Money(value=3200.0), sca_performed=True).model_dump(mode="json")
    assert A.refund_plan(ctx) == {"debited": 3200.0, "currency": "RON", "refund": 3200.0, "payer_liability": 150.0,
                                  "cap": 150.0, "retained": False, "basis": "Law 209/2019, art. 179(1)"}
    rule_params.set_params({"retain_payer_liability": True})
    kept = A.refund_plan(ctx)
    assert kept["refund"] == 3050.0 and kept["retained"] is True
    # art. 177(d): no SCA, so the customer bears nothing
    no_sca = A.refund_plan(make_ctx(sca_performed=False).model_dump(mode="json"))
    assert no_sca["payer_liability"] == 0.0 and no_sca["refund"] == 1000.0 and no_sca["basis"].endswith("art. 177")
    # in the currency debited; without a EUR rate for it nothing is kept
    eur = A.refund_plan(make_ctx(amount=Money(value=20.0, currency="EUR"), sca_performed=True).model_dump(mode="json"))
    assert (eur["currency"], eur["payer_liability"], eur["refund"]) == ("EUR", 20.0, 0.0)
    usd = A.refund_plan(make_ctx(amount=Money(value=90.0, currency="USD"), sca_performed=True).model_dump(mode="json"))
    assert (usd["payer_liability"], usd["refund"], usd["retained"]) == (None, 90.0, False)


def test_the_rubric_counts_a_payment_zero_seconds_after_the_click():
    rows, score = A.rubric({"seconds_after_click": 0}, {})
    assert next(r for r in rows if "5 minutes" in r["indicator"])["value"] is True and score == -1
    rows, score = A.rubric({}, {})
    assert next(r for r in rows if "5 minutes" in r["indicator"])["value"] is False and score == 0


# ---------------------------------------------------------------- the moment the customer told the bank


def test_the_first_report_of_an_unauthorised_payment_anchors_the_notice():
    received = ts(2026, 10, 28, 15)
    others = [
        {"case_id": "CT-A", "customer_ref": "C1", "received_at": ts(2026, 10, 28, 9).isoformat(),
         "dispute_type": "neautorizata"},
        {"case_id": "CT-B", "customer_ref": "C1", "received_at": ts(2026, 10, 27, 9).isoformat(),
         "dispute_type": "disputa_comerciant"},                         # not a report of an unauthorized payment
        {"case_id": "CT-C", "customer_ref": "C2", "received_at": ts(2026, 10, 20, 9).isoformat(),
         "dispute_type": "neautorizata"},                               # another customer
        {"case_id": "CT-D", "customer_ref": "C1", "received_at": ts(2026, 10, 26, 9).isoformat(), "status": "EROARE",
         "extracted": {"claims_unauthorized": True}},
    ]
    c = SimpleNamespace(case_id="CT-NEW", rt=SimpleNamespace(cases=_Cases(others)))
    assert A.customer_notice(c, {"match": {"customer_ref": "C1"}, "complaint": {}}, received) == (ts(2026, 10, 28, 9), "CT-A")
    assert A.customer_notice(c, {"match": {"customer_ref": None}, "complaint": {}}, received) == (received, None)


def test_the_replay_scope_follows_the_complaint():
    one = {"complaint": {"customer_ref": "C1", "text": "I did not make this payment.", "attachments": []}}
    assert A.replay_scope(one) == A.replay_scope({"complaint": dict(one["complaint"])})
    assert A.replay_scope(one) != A.replay_scope({"complaint": {**one["complaint"], "customer_ref": "C2"}})
    assert len(A.replay_scope(one)) == 16


# ---------------------------------------------------------------- the clock


def test_a_failed_run_goes_to_the_manual_queue_with_the_clock_running():
    class RawPIIError(ValueError):
        pass

    cases = _Cases([{"case_id": "CT-2", "status": "IN_ANALIZA", "received_at": "2026-10-28T10:00:00+02:00"}])
    facts, errors = [], []
    ledger = SimpleNamespace(append=lambda *args: facts.append(args), seal=lambda case_id: None)
    svc = ClientService(SimpleNamespace(cases=cases, ledger=ledger))

    async def run_error(message: str) -> None:
        errors.append(message)

    asyncio.run(svc._to_manual_queue("CT-2", SimpleNamespace(run_error=run_error),
                                     RawPIIError("Raw personal data in the request to the LLM: TELEFON ×1.")))
    doc = cases.docs["CT-2"]
    assert doc["status"] == MANUAL_QUEUE and doc["finished_at"]
    assert doc["deadline"] == "2026-10-29T23:59:59+02:00"               # end of the next business day, from the report
    assert "unmasked" in doc["manual_queue"]["reason"] and doc["manual_queue"]["deadline"] == doc["deadline"]
    assert [f[1] for f in facts] == ["case.manual_queue"]
    assert "manual queue" in errors[0] and "29 Oct 2026, 23:59" in errors[0]


def test_the_clock_flags_cases_close_to_or_past_the_deadline():
    due = "2026-10-29T23:59:59+02:00"
    doc = {"case_id": "CT-3", "status": "ASTEAPTA_APROBARE", "deadline": due, "received_at": "2026-10-28T10:00:00+02:00"}

    def before(hours: float) -> datetime:
        return datetime.fromisoformat(due) - timedelta(hours=hours)

    assert deadline_escalation(doc, before(10)) is None
    soon = deadline_escalation(doc, before(2))
    assert soon["level"] == "at_risk" and soon["what"] == "refund" and "2.0 hours away" in soon["message"]
    late = deadline_escalation(doc, before(-1))
    assert late["level"] == "breached" and late["seconds_left"] == -3600 and "escalate now" in late["message"]
    for status in ("REFUZAT", MANUAL_QUEUE, "IN_ANALIZA"):
        assert deadline_escalation({**doc, "status": status}, before(-1))["level"] == "breached"
    for status in ("RAMBURSAT", "RESPINS", "EXCEPTIE", "INCHIS"):
        assert deadline_escalation({**doc, "status": status}, before(-1)) is None
    # no next-business-day refund: the written answer's deadline is the one that counts
    route = {**doc, "status": "TRASEU_APP", "verdict": "NU_SE_APLICA_T1",
             "clock": {"answer_deadline": "2026-11-18T23:59:59+02:00"}}
    assert deadline_escalation(route, before(-1)) is None
    assert deadline_escalation(route, datetime(2026, 11, 17, 9, tzinfo=UTC))["what"] == "written answer"
    # a case that never ran: the deadline comes from the report
    never = {"case_id": "CT-4", "status": "NOU", "received_at": "2026-10-28T10:00:00+02:00"}
    assert deadline_escalation(never, before(-1))["deadline"] == due
