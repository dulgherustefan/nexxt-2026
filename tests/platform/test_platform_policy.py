"""Politici Cedar: matricea permis/refuz, zidul, rambursarea, paritatea cu evaluatorul de rezervă."""

from __future__ import annotations

import asyncio
import itertools

import cedarpy
import pytest

from versoml.contracts import Zone
from versoml.shared.policy import (
    KNOWN_ACTIONS,
    POLICY_FILE,
    PRINCIPALS,
    PolicyDenied,
    allowed_tools,
    authorize,
    cedar_schema,
    decide,
    engine_status,
    guarded,
    parse_principal,
    recent_decisions,
    set_engine,
    subscribe,
)
from versoml.shared.policy import engine as engine_module
from versoml.shared.policy import fallback
from versoml.shared.policy.entities import zone_value

JUDGES = ["Judecator/Receptor", "Judecator/Clasificator", "Judecator/Colector", "Judecator/Procuror",
          "Judecator/Avocat", "Judecator/Recuperare", "Judecator/Redactor"]
INVESTIGATORS = ["Investigator/OSINT", "Investigator/Graf", "Investigator/AvocatNevinovatiei", "Investigator/RTS"]
CLIENT_ACTIONS = ["bank-core.get_transaction", "bank-core.beneficiary_seen_before", "bank-core.get_prior_disputes",
                  "sca-logs.get_auth_events", "device.get_session", "device.get_device_history",
                  "domain-intel.rdap_lookup", "domain-intel.ct_first_seen", "domain-intel.lookalike_score",
                  "domain-intel.openphish_check", "domain-intel.fetch_page", "letters.check_letter", "diode.send_facts"]
AML_ACTIONS = ["aml.graph.neighborhood", "aml.osint.web_search", "aml.osint.news_search", "aml.osint.anaf_company",
               "aml.osint.sanctions_screen", "aml.osint.rdap_domain", "aml.osint.ct_certificates",
               "aml.osint.dns_records", "aml.osint.lookalike_score", "aml.osint.fetch_page",
               "aml.osint.openphish_check", "aml.osint.phone_intel", "aml.osint.validate_iban"]
MCP_CLIENT = ["mcp.rules.catalog", "mcp.rules.deadline", "mcp.ledger.verify", "mcp.cases.read", "mcp.cases.create",
              "mcp.cases.propose", "mcp.rules.evaluate", "mcp.wall.read", "letters.check_letter",
              "domain-intel.lookalike_score"]
MCP_AML = ["mcp.rules.catalog", "mcp.rules.deadline", "mcp.ledger.verify", "aml.leads.read", "aml.leads.decide",
           "aml.osint.web_search", "aml.osint.anaf_company", "aml.sanctions.screen"]
ALL_PRINCIPALS = list(PRINCIPALS)
NO_CEDILLA = ("\u015f", "\u015e", "\u0163", "\u0162")


def allowed(principal, action, zone, context=None) -> bool:
    return decide(principal, action, zone, context).allowed


# ------------------------------------------------------------ matricea din contractul cu orchestrarea

@pytest.mark.parametrize("principal, action", list(itertools.product(JUDGES, CLIENT_ACTIONS)))
def test_judges_may_use_client_tools(principal, action):
    assert allowed(principal, action, Zone.CLIENT)


@pytest.mark.parametrize("principal, action", list(itertools.product(INVESTIGATORS, AML_ACTIONS)))
def test_investigators_may_use_aml_tools(principal, action):
    assert allowed(principal, action, Zone.AML)


@pytest.mark.parametrize("principal, action", list(itertools.product(JUDGES, AML_ACTIONS + ["aml.leads.read"])))
def test_judges_never_reach_aml_tools(principal, action):
    assert not allowed(principal, action, Zone.AML)
    assert not allowed(principal, action, Zone.CLIENT)


@pytest.mark.parametrize("principal, action", list(itertools.product(INVESTIGATORS, CLIENT_ACTIONS + ["refund.issue"])))
def test_investigators_never_reach_client_tools(principal, action):
    assert not allowed(principal, action, Zone.CLIENT, {"approved_by_human": True})
    assert not allowed(principal, action, Zone.AML, {"approved_by_human": True})


def test_demo_denials_have_a_clear_english_reason():
    for principal, action in (("Judecator/Redactor", "aml.osint.web_search"),
                              ("Judecator/Procuror", "aml.graph.neighborhood")):
        decision = authorize(principal, action, Zone.AML)
        assert not decision.allowed
        assert {"wall-client-not-in-aml", "wall-client-no-aml-actions"} <= set(decision.policy_ids)
        assert decision.principal == f'Agent::"{principal}"' and decision.resource == 'Zone::"aml"'
        assert "AML zone" in decision.reason and "tipping-off" in decision.reason and decision.reason.startswith("Denied")
        assert not any(c in decision.reason for c in NO_CEDILLA)
        assert decision.at is not None


# ------------------------------------------------------------ rambursarea

@pytest.mark.parametrize("context, expected", [
    ({"within_auto_cap": True}, True),
    ({"approved_by_human": True}, True),
    ({"within_auto_cap": False, "approved_by_human": True}, True),
    (None, False),
    ({}, False),
    ({"within_auto_cap": False, "approved_by_human": False}, False),
    ({"within_auto_cap": "true"}, False),
    ({"approved_by_human": 1}, False),
])
def test_only_motor_reguli_refunds_and_only_with_cap_or_human(context, expected):
    decision = authorize("MotorReguli", "refund.issue", Zone.CLIENT, context)
    assert decision.allowed is expected
    if not expected:
        assert "approved_by_human" in decision.reason


@pytest.mark.parametrize("principal", [p for p in ALL_PRINCIPALS if p != "MotorReguli"])
def test_nobody_else_can_refund(principal):
    for zone in Zone:
        decision = decide(principal, "refund.issue", zone, {"within_auto_cap": True, "approved_by_human": True})
        assert not decision.allowed
    assert "refund-only-motor" in decide(principal, "refund.issue", Zone.CLIENT, {"approved_by_human": True}).policy_ids


def test_motor_reguli_cannot_refund_in_aml_zone():
    assert not allowed("MotorReguli", "refund.issue", Zone.AML, {"approved_by_human": True})


# ------------------------------------------------------------ semnătura umană

SIGNOFF = ["cases.approve", "mcp.cases.approve", "rules.set_params"]


@pytest.mark.parametrize("principal", [p for p in ALL_PRINCIPALS if p != "Operator"] + ["Necunoscut/X"])
def test_only_a_person_signs_or_changes_the_rules(principal):
    for action, zone in itertools.product(SIGNOFF, Zone):
        decision = decide(principal, action, zone, {"approved_by_human": True})
        assert not decision.allowed, (principal, action, zone)
    ref = parse_principal(principal)
    if ref.type in ("Mcp", "Agent", "System"):
        decision = decide(principal, "cases.approve", Zone.CLIENT)
        assert "only-a-person-signs" in decision.policy_ids


def test_an_operator_signs_in_the_client_zone_only():
    assert allowed("Operator", "cases.approve", Zone.CLIENT) and allowed("Operator", "rules.set_params", Zone.CLIENT)
    assert not allowed("Operator", "cases.approve", Zone.AML)
    assert not allowed("Operator", "mcp.cases.approve", Zone.CLIENT)  # the MCP form is nobody's


def test_an_mcp_client_proposes_but_never_approves():
    approve = authorize("Mcp/client", "mcp.cases.approve", Zone.CLIENT, {"via": "mcp"})
    assert not approve.allowed and approve.policy_ids == ["only-a-person-signs"]
    assert "MCP client" in approve.reason and "propose" in approve.reason
    assert allowed("Mcp/client", "mcp.cases.propose", Zone.CLIENT)
    assert not allowed("Mcp/aml", "mcp.cases.propose", Zone.CLIENT)
    for agent in JUDGES:
        assert not allowed(agent, "cases.approve", Zone.CLIENT, {"approved_by_human": True})


# ------------------------------------------------------------ dioda

@pytest.mark.parametrize("principal", ALL_PRINCIPALS)
def test_only_the_aml_analyst_sends_hold(principal):
    expected = principal == "AnalistAML"
    assert allowed(principal, "diode.send_hold", Zone.AML) is expected
    assert not allowed(principal, "diode.send_hold", Zone.CLIENT)


@pytest.mark.parametrize("principal", ALL_PRINCIPALS)
def test_only_client_zone_principals_send_facts(principal):
    expected = principal in JUDGES or principal in ("MotorReguli", "Operator")
    assert allowed(principal, "diode.send_facts", Zone.CLIENT) is expected
    assert not allowed(principal, "diode.send_facts", Zone.AML)


# ------------------------------------------------------------ MCP

def test_mcp_client_has_exactly_its_list():
    assert sorted(allowed_tools("Mcp/client", Zone.CLIENT)) == sorted(MCP_CLIENT)
    assert allowed_tools("Mcp/client", Zone.AML) == []


def test_mcp_client_is_denied_every_aml_action_and_the_aml_zone():
    aml_like = [a for a in KNOWN_ACTIONS if a.startswith("aml.")] + ["aml.leads.new_thing", "aml.osint.new_thing"]
    for action in aml_like:
        for zone in Zone:
            assert not allowed("Mcp/client", action, zone)
    for action in KNOWN_ACTIONS:
        assert not allowed("Mcp/client", action, Zone.AML)
    assert not allowed("Mcp/client", "bank-core.get_transaction", Zone.CLIENT)
    assert not allowed("Mcp/client", "diode.send_facts", Zone.CLIENT)


def test_mcp_aml_has_exactly_its_list():
    assert sorted(allowed_tools("Mcp/aml", Zone.AML)) == sorted(MCP_AML)
    assert allowed_tools("Mcp/aml", Zone.CLIENT) == []
    assert not allowed("Mcp/aml", "letters.check_letter", Zone.CLIENT)


# ------------------------------------------------------------ default deny și normalizare

@pytest.mark.parametrize("principal, action, zone", [
    ("Hacker", "bank-core.get_transaction", Zone.CLIENT),
    ("Judecator/Necunoscut", "bank-core.get_transaction", Zone.CLIENT),
    ('Agent::"Investigator/Fals"', "aml.osint.web_search", Zone.AML),
    ("Judecator/Colector", "bank-core.delete_customer", Zone.CLIENT),
    ("Judecator/Colector", "client_tools", Zone.CLIENT),
    ("Judecator/Colector", "any_tool", Zone.CLIENT),
    ("Judecator/Colector", "bank-core.get_transaction\nrefund.issue", Zone.CLIENT),
    ("Judecator/Colector", "bank-core.get_transaction", "moon"),
    ("Operator", "aml.osint.web_search", Zone.AML),
    ("AnalistAML", "aml.osint.web_search", Zone.AML),
])
def test_default_deny(principal, action, zone):
    decision = authorize(principal, action, zone)
    assert not decision.allowed and decision.policy_ids and decision.reason.startswith("Denied")


def test_wildcard_read_tools_follow_their_zone():
    assert allowed("Judecator/Colector", "domain-intel.whois_history", Zone.CLIENT)
    assert allowed("Investigator/OSINT", "aml.osint.reverse_image", Zone.AML)
    assert not allowed("Judecator/Colector", "aml.osint.reverse_image", Zone.CLIENT)


@pytest.mark.parametrize("raw, canonical", [
    ("Judecator/Redactor", "Judecator/Redactor"),
    ("Judecătorul/Redactor", "Judecator/Redactor"),
    ('Agent::"Judecator/Redactor"', "Judecator/Redactor"),
    ("Investigatorul/Avocatul nevinovăției", "Investigator/AvocatNevinovatiei"),
    ("Mcp/client", "Mcp/client"),
    ('Mcp::"client"', "Mcp/client"),
    ("mcp::aml", "Mcp/aml"),
    ('System::"MotorReguli"', "MotorReguli"),
    ("AnalistAML", "AnalistAML"),
])
def test_principal_aliases(raw, canonical):
    ref = parse_principal(raw)
    assert ref.known and ref.name == canonical


def test_zone_parsing():
    assert zone_value("AML") == "aml" and zone_value(Zone.CLIENT) == "client"
    assert decide("Judecator/Colector", "sca-logs.get_auth_events", "client").allowed
    assert decide("Judecator/Colector", "sca-logs.get_auth_events", " CLIENT ").allowed


# ------------------------------------------------------------ Cedar vs evaluatorul de rezervă

def test_policies_validate_against_schema():
    result = cedarpy.validate_policies(POLICY_FILE.read_text(encoding="utf-8"), cedar_schema())
    assert result.validation_passed, [str(e) for e in result.errors]


def test_cedar_is_the_active_engine():
    status = engine_status()
    assert status["engine"] == "cedar" and status["ok"]


CONTEXTS = [None, {"within_auto_cap": True}, {"approved_by_human": True}, {"within_auto_cap": False}]
EXTRA_ACTIONS = ["domain-intel.new_probe", "aml.osint.new_probe", "aml.leads.other", "bank-core.unknown", "x.y"]


def test_parity_cedar_and_python_on_the_full_matrix():
    mismatches = []
    for principal, action, zone, ctx in itertools.product(ALL_PRINCIPALS + ["Necunoscut/X"],
                                                          list(KNOWN_ACTIONS) + EXTRA_ACTIONS, list(Zone), CONTEXTS):
        cedar = decide(principal, action, zone, ctx)
        ref = parse_principal(principal)
        py_allowed, py_ids = fallback.evaluate(fallback.Request(ref, action, zone.value,
                                                                engine_module._sanitize(ctx or {})))
        if (cedar.allowed, sorted(cedar.policy_ids)) != (py_allowed, sorted(py_ids) or ["default-deny"]):
            mismatches.append((principal, action, zone.value, ctx, cedar.policy_ids, py_ids))
    assert mismatches == []


def test_forced_python_engine_says_so_loudly():
    set_engine("python")
    decision = authorize("Judecator/Redactor", "aml.osint.web_search", Zone.AML)
    assert not decision.allowed and decision.reason.startswith("[WARNING")
    assert engine_status()["engine"] == "python"


def test_cedar_failure_falls_back_with_a_loud_reason(monkeypatch):
    def broken():
        raise RuntimeError("cedarpy stricat")

    monkeypatch.setattr(engine_module, "_cedar", broken)
    denied = authorize("Judecator/Redactor", "aml.osint.web_search", Zone.AML)
    permitted = authorize("MotorReguli", "refund.issue", Zone.CLIENT, {"within_auto_cap": True})
    assert not denied.allowed and permitted.allowed
    assert "cedarpy is unavailable" in denied.reason and "cedarpy is unavailable" in permitted.reason


# ------------------------------------------------------------ guarded, jurnal, abonați

def test_guarded_sync_and_async():
    @guarded("Judecator/Colector", "sca-logs.get_auth_events", Zone.CLIENT)
    def read(tx: str) -> str:
        return f"ok {tx}"

    @guarded("Judecator/Redactor", "aml.osint.web_search", Zone.AML)
    async def leak() -> str:
        return "n-ar trebui"

    @guarded("MotorReguli", "refund.issue", Zone.CLIENT, context=lambda amount, cap: {"within_auto_cap": amount <= cap})
    def refund(amount: float, cap: float) -> str:
        return "rambursat"

    assert read("TX-1") == "ok TX-1"
    with pytest.raises(PolicyDenied) as err:
        asyncio.run(leak())
    assert not err.value.decision.allowed and "wall-client-not-in-aml" in err.value.decision.policy_ids
    assert refund(100, 500) == "rambursat"
    with pytest.raises(PolicyDenied):
        refund(900, 500)
    assert read.__versoml_policy__ == {"principal": "Judecator/Colector", "action": "sca-logs.get_auth_events",
                                    "zone": "client"}


def test_recent_decisions_ring_buffer_and_subscribers():
    seen, denied = [], []
    unsubscribe = subscribe(seen.append)
    unsubscribe_denied = subscribe(denied.append, denied_only=True)
    subscribe_broken = subscribe(lambda d: 1 / 0)  # un abonat stricat nu oprește controlul
    authorize("Judecator/Colector", "sca-logs.get_auth_events", Zone.CLIENT)
    authorize("Judecator/Redactor", "aml.osint.web_search", Zone.AML)
    authorize("Mcp/client", "aml.leads.read", Zone.CLIENT)
    assert len(seen) == 3 and len(denied) == 2
    latest = recent_decisions(2)
    assert [d.action for d in latest] == ["aml.leads.read", "aml.osint.web_search"]
    assert all(not d.allowed for d in recent_decisions(10, denied_only=True))
    unsubscribe()
    unsubscribe_denied()
    subscribe_broken()
    authorize("Judecator/Colector", "device.get_session", Zone.CLIENT)
    assert len(seen) == 3
    for _ in range(1100):
        decide("Judecator/Colector", "device.get_session", Zone.CLIENT)
    assert len(recent_decisions(5000)) == 4  # `decide` nu jurnalizează; `authorize` da
