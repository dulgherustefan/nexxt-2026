"""Proprietăți (hypothesis) pe care le arătăm juriului.

1. Invariantul C-70/25: la o plată neautorizată notificată în 13 luni, fără HOLD confirmat și comunicat,
   indiciile de neglijență gravă (ecranul cu suma, aprobarea în aplicație, OTP divulgat, SCA reușită,
   dispozitivul cunoscut) NU schimbă niciodată rambursarea: nici verdictul, nici termenul, nici suma.
2. Fiecare decizie are cel puțin o regulă cunoscută, iar fiecare citare e un fact_id din `ctx.fact_ids`.
3. Determinism, semnătura umană pe deciziile defavorabile, ș/ț cu virgulă.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from rules_testkit import DEFAULTS, FACT_IDS, TZ
from versoml.contracts import Channel, DisputeType, Money, Question, Scenario, Verdict
from versoml.shared.rules import RuleContextExt, end_of_next_business_day, evaluate
from versoml.shared.rules.calendar_ro import add_months, local_date
from versoml.shared.rules.packs.dp import explanation_complete, is_unfavourable
from versoml.shared.rules.registry import known_ids

REFUNDS = {Verdict.RAMBURSEAZA, Verdict.RAMBURSEAZA_CU_APROBARE}
CEDILLA = set("şţŞŢ")
RO_LETTERS = set("ăâîșțĂÂÎȘȚ")
PROPER_NOUNS = ("Plăți Instant",)          # numele schemei Transfond rămâne ca atare în textul englez


def without_proper_nouns(text: str) -> str:
    for name in PROPER_NOUNS:
        text = text.replace(name, "")
    return text
opt_bool = st.none() | st.booleans()
moments = st.datetimes(min_value=datetime(2025, 6, 1), max_value=datetime(2027, 6, 30), timezones=st.just(TZ))
gn = st.fixed_dictionaries({
    "screen_showed_amount_and_payee": opt_bool, "client_admits_approving_in_app": opt_bool,
    "client_admits_sharing_credentials": opt_bool, "sca_performed": opt_bool, "device_known": opt_bool,
})


@st.composite
def contexts(draw, dispute_type=None, max_delay_days=600, hold=None, min_delay_days=0) -> RuleContextExt:
    executed = draw(moments)
    notified = executed + draw(st.timedeltas(min_value=timedelta(days=min_delay_days),
                                             max_value=timedelta(days=max_delay_days)))
    now = notified + draw(st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=12)))
    keys = draw(st.sets(st.sampled_from(sorted(FACT_IDS))))
    hold_signal = draw(st.booleans()) if hold is None else hold
    return RuleContextExt(
        case_id="CT-SYN-PROP", now=now, executed_at=executed, notified_at=notified,
        channel=draw(st.sampled_from(list(Channel))),
        dispute_type=dispute_type or draw(st.sampled_from(list(DisputeType))),
        scenario=draw(st.none() | st.sampled_from(list(Scenario))),
        amount=Money(value=round(draw(st.floats(min_value=1, max_value=60000, allow_nan=False)), 2),
                     currency=draw(st.sampled_from(["RON", "EUR"]))),
        sca_performed=draw(opt_bool), sca_method=draw(st.none() | st.sampled_from(["app_push", "sms_otp", "biometric"])),
        eci=draw(st.none() | st.sampled_from(["05", "06", "07"])), cavv_present=draw(opt_bool),
        screen_showed_amount_and_payee=draw(opt_bool), device_known=draw(opt_bool),
        seconds_after_click=draw(st.none() | st.integers(min_value=0, max_value=7200)),
        sim_swap_hours_before=draw(st.none() | st.floats(min_value=0, max_value=48, allow_nan=False)),
        beneficiary_new=draw(opt_bool), duplicate_of=draw(st.none() | st.just("TX-SYN-1")),
        prior_disputes_12m=draw(st.integers(min_value=0, max_value=40)),
        client_fraud_score=draw(st.none() | st.floats(min_value=0, max_value=1, allow_nan=False)),
        client_admits_sharing_credentials=draw(opt_bool), client_admits_approving_in_app=draw(opt_bool),
        hold_signal=hold_signal, hold_authority_notified=draw(st.booleans()),
        classification_ambiguous=draw(st.booleans()), card_present=draw(opt_bool),
        fact_ids={k: FACT_IDS[k] for k in keys},
    )


def in_13_months(ctx: RuleContextExt) -> bool:
    return local_date(ctx.notified_at) <= add_months(local_date(ctx.executed_at), 13)


@settings(max_examples=250, deadline=None)
@given(contexts(dispute_type=DisputeType.NEAUTORIZATA, max_delay_days=390), gn, gn)
def test_invariant_c70_25_neglijenta_nu_schimba_rambursarea(ctx, gn_a, gn_b):
    assume(in_13_months(ctx) and not (ctx.hold_signal and ctx.hold_authority_notified))
    a = evaluate(ctx.model_copy(update=gn_a), DEFAULTS).decisions[0]
    b = evaluate(ctx.model_copy(update=gn_b), DEFAULTS).decisions[0]
    assert a.decision in REFUNDS and b.decision in REFUNDS
    assert (a.decision, a.requires_human, a.deadline, a.amount) == (b.decision, b.requires_human, b.deadline, b.amount)
    assert a.deadline == end_of_next_business_day(ctx.notified_at)
    assert a.amount == ctx.amount                                     # rambursare integrală


@settings(max_examples=150, deadline=None)
@given(contexts(dispute_type=DisputeType.NEAUTORIZATA, max_delay_days=390, hold=True), gn)
def test_invariant_singura_exceptie_e_hold_plus_autoritate(ctx, gn_a):
    assume(in_13_months(ctx))
    d = evaluate(ctx.model_copy(update=gn_a), DEFAULTS).decisions[0]
    if ctx.hold_authority_notified:
        assert d.decision == Verdict.EXCEPTIE_FRAUDA_CLIENT and d.requires_human
    else:
        assert d.decision == Verdict.RAMBURSEAZA_CU_APROBARE and d.requires_human


@settings(max_examples=300, deadline=None)
@given(contexts())
def test_invariant_decizii_cu_reguli_si_citari_doar_din_registru(ctx):
    out = evaluate(ctx, DEFAULTS)
    valid = set(ctx.fact_ids.values())
    known = known_ids()
    assert [d.question for d in out.decisions] == [Question.RAMBURSARE_T1, Question.RECUPERARE_CLIENT,
                                                   Question.RECUPERARE_ESCROC, Question.RASPUNS_RECLAMATIE]
    for d in out.decisions:
        assert d.rule_ids and set(d.rule_ids) <= known, d.rule_ids
        assert explanation_complete(d)
        for line in d.rationale:
            assert set(line.cites) <= valid
        assert set(d.supporting_evidence) <= valid and set(d.contradicting_evidence) <= valid
        assert d.decided_by == ("rules+human" if d.requires_human else "rules")
        if is_unfavourable(d, ctx):
            assert d.requires_human and "DP-02" in d.rule_ids
    for h in out.hits:
        assert set(h.inputs) <= valid and h.version and h.basis and h.rule_id in known
    assert out.engine_version and out.case_id == ctx.case_id


@settings(max_examples=100, deadline=None)
@given(contexts())
def test_invariant_determinism_si_diacritice(ctx):
    a, b = evaluate(ctx, DEFAULTS), evaluate(ctx, DEFAULTS)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
    text = json.dumps(a.model_dump(mode="json"), ensure_ascii=False)
    assert not (CEDILLA & set(text))
    assert not (RO_LETTERS & set(without_proper_nouns(text)))           # textele pentru UI sunt în engleză


@settings(max_examples=150, deadline=None)
@given(contexts(dispute_type=DisputeType.NEAUTORIZATA, min_delay_days=400, max_delay_days=900))
def test_invariant_dupa_13_luni_respingerea_o_semneaza_un_om(ctx):
    assert not in_13_months(ctx)
    d = evaluate(ctx, DEFAULTS).decisions[0]
    assert d.decision == Verdict.RESPINGE_TARDIV and d.requires_human and "PAY-01" in d.rule_ids


@settings(max_examples=150, deadline=None)
@given(contexts(dispute_type=DisputeType.APP))
def test_invariant_app_nu_primeste_t1_si_merge_la_om(ctx):
    d = evaluate(ctx, DEFAULTS).decisions[0]
    assert d.decision == Verdict.NU_SE_APLICA_T1 and d.requires_human and "PAY-12" in d.rule_ids
