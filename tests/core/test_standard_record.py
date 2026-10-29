"""How the agent reads the SCA log and turns the rule context into the standard record."""

from __future__ import annotations

from tests.rules.rules_testkit import make_ctx, ts
from versoml.contracts import Channel, DisputeType, Money, Scenario
from versoml.zone_client.agents import _claimed_amount, sca_from_events, standard_record


def test_a_declined_or_none_authentication_is_not_sca():
    declined = [{"purpose": "payment", "result": "declined", "method": "app_push", "eci": "5"}]
    assert sca_from_events(declined)["sca_performed"] is False
    assert sca_from_events([{"purpose": "payment", "result": "approved", "method": "none"}])["sca_performed"] is False
    assert sca_from_events([{"purpose": "token_provisioning", "result": "approved", "method": "sms_otp"}])["sca_performed"] is False
    ok = sca_from_events([*declined, {"purpose": "payment", "result": "approved", "method": "app_push", "eci": "5",
                                      "cavv": "AAAB", "screen_showed_amount_and_payee": 1}])
    assert ok["sca_performed"] is True and ok["eci"] == "05" and ok["cavv_present"] is True
    assert ok["screen_showed_amount_and_payee"] is True and ok["sca_step"] == "payment"
    # the courier scam: SCA only to enrol the fraudster's device, then a payment with none
    enrolled = sca_from_events([{"purpose": "device_enrollment", "result": "approved", "method": "sms_otp"},
                                {"purpose": "payment", "result": "approved", "method": "none"}])
    assert enrolled["sca_performed"] is True and enrolled["sca_method"] == "sms_otp"
    assert enrolled["sca_step"] == "device_enrollment" and enrolled["screen_showed_amount_and_payee"] is False


def test_claimed_amount_only_compares_the_same_currency():
    payment = Money(value=3200, currency="RON")
    assert _claimed_amount([Money(value=2.99, currency="RON"), Money(value=3200, currency="RON")], payment) == 3200
    assert _claimed_amount([Money(value=650, currency="EUR")], payment) is None


def test_card_record_reads_eci_against_the_scheme_and_lists_issues():
    ctx = make_ctx(channel=Channel.CARD, card_scheme="mastercard", eci="05", scenario=Scenario.CARD_ECOM_FARA_3DS,
                   sca_performed=False, claimed_amount=990.0, beneficiary_iban=None)
    r = standard_record(ctx, {"contacted_by": "sms", "hosts": ["shop.example"], "phones_e164": ["+40712345678"]},
                        pos_entry_mode="ecommerce")
    assert r.payment_type == "card" and r.card_scheme == "mastercard" and r.three_ds is None
    assert r.fraud_type == "card_details_theft" and r.fraud_type_label == "Card details theft"
    assert r.authentication == "no_sca" and r.contact_channel == "sms" and r.phones == ["+40 7•• ••• 678"]
    assert any("ECI 05 isn't a Mastercard code" in i for i in r.issues)
    assert any("RON 990.00" in i for i in r.issues)  # the customer's amount differs from the bank's record

    visa = standard_record(make_ctx(channel=Channel.CARD, card_scheme="visa", eci="05"), {})
    assert visa.three_ds == "authenticated" and not any("ECI" in i for i in visa.issues)


def test_transfer_record_checks_the_iban_and_uses_bucharest_time():
    ctx = make_ctx(dispute_type=DisputeType.APP, beneficiary_iban="RO48AAAA1B31007593840000",
                   executed_at=ts(2026, 7, 1, 9), notified_at=ts(2026, 7, 3, 10))
    r = standard_record(ctx, {})
    assert r.fraud_type == "manipulation_of_payer" and r.payment_type == "credit_transfer"
    assert r.payee_iban == "RO48 AAAA •••• 0000" and r.payee_iban_valid is False
    assert any("check digits" in i for i in r.issues)
    assert r.executed_at.isoformat().endswith("+03:00") and r.days_to_report == 2
