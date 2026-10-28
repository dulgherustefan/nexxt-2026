"""Parametrii [U] (validare, persistare în var/rules_params.json), catalogul, aliasurile și `explain`."""

from __future__ import annotations

import json

import pytest

from rules_testkit import eod, make_ctx, t1, ts
from versoml.contracts import Confidence, Money, Verdict
from versoml.shared.rules import (
    ENGINE_VERSION, ParamsError, catalog, evaluate, explain, get_params, param_specs, reset_params, set_params,
)
from versoml.shared.rules.registry import PACK_ORDER, aliases, all_rules, get_rule

CEDILLA = set("şţŞŢ")


def test_parametrii_impliciti_fara_fisier(isolated_params):
    params = get_params()
    assert not isolated_params.exists()
    assert params["auto_refund_cap_ron"] == 5000 and params["client_fraud_signal_threshold"] == 0.7
    assert params["prior_disputes_signal_threshold"] == 3 and params["eur_ron_rate"] == 5.0
    assert params["bank_closure_days"] == [] and params["require_human_for_unfavourable"] is True


def test_set_params_persista_si_schimba_evaluarea(isolated_params):
    ctx = make_ctx(amount=Money(value=3200.0))
    assert t1(evaluate(ctx)).decision == Verdict.RAMBURSEAZA
    out = set_params({"auto_refund_cap_ron": 2000})
    assert out["auto_refund_cap_ron"] == 2000
    assert json.loads(isolated_params.read_text(encoding="utf-8")) == {"auto_refund_cap_ron": 2000.0}
    assert t1(evaluate(ctx)).decision == Verdict.RAMBURSEAZA_CU_APROBARE          # params=None → fișierul
    assert t1(evaluate(ctx, {})).decision == Verdict.RAMBURSEAZA                  # dicționar → doar implicitele
    assert reset_params()["auto_refund_cap_ron"] == 5000 and not isolated_params.exists()


def test_valoarea_egala_cu_implicita_nu_se_salveaza(isolated_params):
    set_params({"eur_ron_rate": 5.0})
    assert json.loads(isolated_params.read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize("updates, code", [
    ({"plafon_inventat": 1}, "PARAM_UNKNOWN"),
    ({"auto_refund_cap_ron": "mult"}, "PARAM_TYPE"),
    ({"auto_refund_cap_ron": True}, "PARAM_TYPE"),
    ({"client_fraud_signal_threshold": 1.5}, "PARAM_RANGE"),
    ({"prior_disputes_signal_threshold": 2.5}, "PARAM_TYPE"),
    ({"refund_anchor_mode": "oricand"}, "PARAM_CHOICE"),
    ({"bank_closure_days": ["31.12.2026"]}, "PARAM_TYPE"),
    ({"refund_end_of_day": "24:00"}, "PARAM_TYPE"),
    ({"auto_refund_cap_ron": None}, "PARAM_NULL"),
])
def test_validarea_parametrilor(updates, code, isolated_params):
    with pytest.raises(ParamsError) as exc:
        set_params(updates)
    assert exc.value.errors[0]["code"] == code
    assert isinstance(exc.value, ValueError)                    # API-ul prinde ValueError → 400
    assert not isolated_params.exists()


def test_parametrii_nullabili_si_listele():
    assert set_params({"undue_delay_days": 30})["undue_delay_days"] == 30
    assert set_params({"undue_delay_days": None})["undue_delay_days"] is None
    assert set_params({"bank_closure_days": ["2026-12-31", "2026-12-31"]})["bank_closure_days"] == ["2026-12-31"]


def test_zilele_inchise_ale_bancii_schimba_termenul_t1():
    ctx = make_ctx(executed_at=ts(2026, 10, 28, 9), notified_at=ts(2026, 10, 28, 10))
    assert t1(evaluate(ctx)).deadline == eod(2026, 10, 29)
    set_params({"bank_closure_days": ["2026-10-29"]})
    assert t1(evaluate(ctx)).deadline == eod(2026, 10, 30)


def test_fisierul_corupt_nu_strica_parametrii(isolated_params):
    isolated_params.write_text("{nu e json", encoding="utf-8")
    assert get_params()["auto_refund_cap_ron"] == 5000
    isolated_params.write_text(json.dumps({"auto_refund_cap_ron": -5, "require_human_for_unfavourable": False}),
                               encoding="utf-8")
    params = get_params()
    assert params["auto_refund_cap_ron"] == 5000 and params["require_human_for_unfavourable"] is True


def test_undue_delay_trimite_la_om_fara_sa_respinga():
    ctx = make_ctx(executed_at=ts(2026, 6, 1), notified_at=ts(2026, 10, 27, 10))
    out = evaluate(ctx, {"undue_delay_days": 60})
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE and t1(out).deadline == eod(2026, 10, 28)


def test_flagurile_pe_caz_din_params_nu_sunt_parametri():
    out = evaluate(make_ctx(), {"_classification_ambiguous": True, "_alt_flag_ignorat": 1})
    assert t1(out).decision == Verdict.RAMBURSEAZA_CU_APROBARE
    with pytest.raises(ParamsError):
        evaluate(make_ctx(), {"cheie_necunoscuta": 1})


# ---------------------------------------------------------------- catalog și registru


def test_catalogul_are_campurile_contractului():
    rows = catalog()
    assert rows and len({r["rule_id"] for r in rows}) == len(rows)
    for r in rows:
        assert {"rule_id", "title", "basis", "confidence", "pack", "params"} <= set(r)
        assert r["confidence"] in {c.value for c in Confidence}
        assert r["pack"] in PACK_ORDER and r["title"] and r["basis"] and r["source"]
        assert r["extension"] == (r["pack"] in ("REC", "URM"))
        assert not (CEDILLA & set(json.dumps(r, ensure_ascii=False)))


def test_id_urile_din_docs_context_sunt_refolosite():
    ids = {r["rule_id"] for r in catalog()}
    for rid in ("PAY-01", "PAY-02", "PAY-03", "PAY-04", "PAY-05", "PAY-06", "PAY-12", "PAY-15",
                "DSP-24", "DSP-27", "DSP-52", "DSP-58", "DSP-59", "CMP-01", "CMP-02", "CMP-03",
                "DP-02", "DP-03", "AML-01", "AML-03", "AML-04"):
        assert rid in ids
    assert {r["rule_id"] for r in catalog() if r["pack"] == "REC"} == {"REC-01", "REC-02", "REC-03", "REC-04", "REC-05"}


def test_aliasurile_dsp_trimit_la_regulile_pay_si_cmp():
    table = aliases()
    assert table["DSP-01"] == "PAY-01" and table["DSP-04"] == "PAY-15" and table["DSP-05"] == "PAY-03"
    assert table["DSP-14"] == "CMP-01" and table["DSP-15"] == "CMP-03"
    assert get_rule("DSP-13").rule_id == "PAY-12"


def test_parametrii_declarati_exista_si_trimit_la_reguli_existente():
    specs = param_specs()
    for spec in all_rules():
        assert spec.description, spec.rule_id
        for name in spec.params:
            assert name in specs, (spec.rule_id, name)
    ids = {s.rule_id for s in all_rules()}
    for name, spec in specs.items():
        assert spec.rules and set(spec.rules) <= ids, name
        assert spec.description and not (CEDILLA & set(spec.description))


def test_valorile_U_sunt_parametri_nu_constante():
    specs = param_specs()
    for name in ("auto_refund_cap_ron", "client_fraud_signal_threshold", "prior_disputes_signal_threshold",
                 "eur_ron_rate", "refund_end_of_day", "bank_closure_days", "recall_window_months",
                 "ron_recall_answer_banking_days", "fraud_report_deadline_mode"):
        assert specs[name].confidence == Confidence.U


def test_explain_pe_alias_si_pe_regula():
    entry = explain("DSP-04")
    assert entry["rule_id"] == "PAY-15" and entry["alias_of"] == "PAY-15" and "DSP-04" in entry["note"]
    pay03 = explain("PAY-03")
    assert pay03["description"] and pay03["params_detail"]["refund_end_of_day"]["confidence"] == "U"
    assert pay03["confidence"] == "P" and pay03["alias_of"] is None
    assert explain("REC-01")["extension"] is True
    with pytest.raises(KeyError):
        explain("XYZ-99")


def test_versiunea_motorului_in_rezultat():
    assert evaluate(make_ctx()).engine_version == ENGINE_VERSION
    assert all(h.version == get_rule(h.rule_id).version for h in evaluate(make_ctx()).hits)
