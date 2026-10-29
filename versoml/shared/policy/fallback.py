"""Evaluator Python echivalent cu `policies.cedar`, folosit DOAR dacă cedarpy nu merge.

Semantica e cea din Cedar: orice `forbid` potrivit → refuz; altfel orice `permit` potrivit → permis;
altfel refuz implicit. Testul de paritate compară cele două evaluatoare pe toată matricea.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from versoml.shared.policy.entities import ROOT_GROUP, PrincipalRef, action_groups


@dataclass(frozen=True)
class Request:
    principal: PrincipalRef
    action: str
    zone: str
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def groups(self) -> frozenset[str]:
        groups = action_groups(self.action)
        return groups | {ROOT_GROUP} if groups else groups

    def is_(self, type_: str, id_: str) -> bool:
        return self.principal.type == type_ and self.principal.id == id_

    def role(self, role: str) -> bool:
        return role in self.principal.roles


def _ctx_true(r: Request, key: str) -> bool:
    return r.context.get(key) is True


Rule = tuple[str, Literal["permit", "forbid"], Callable[[Request], bool]]

RULES: tuple[Rule, ...] = (
    # zona client
    ("client-agents-tools", "permit",
     lambda r: r.role("client_agent") and "client_tools" in r.groups and r.zone == "client"),
    ("operator-client-tools", "permit",
     lambda r: r.is_("Human", "Operator") and "client_tools" in r.groups and r.zone == "client"),
    ("motor-system-tools", "permit",
     lambda r: r.is_("System", "MotorReguli")
     and r.action in ("ledger.read_client", "diode.send_facts", "letters.check_letter") and r.zone == "client"),
    ("motor-refund", "permit",
     lambda r: r.is_("System", "MotorReguli") and r.action == "refund.issue" and r.zone == "client"
     and (_ctx_true(r, "within_auto_cap") or _ctx_true(r, "approved_by_human"))),
    ("mcp-client-tools", "permit",
     lambda r: r.is_("Mcp", "client") and "mcp_client_tools" in r.groups and r.zone == "client"),
    ("operator-signoff", "permit",
     lambda r: r.is_("Human", "Operator") and r.action in ("cases.approve", "rules.set_params") and r.zone == "client"),
    # zona AML
    ("aml-agents-tools", "permit",
     lambda r: r.role("aml_agent") and "aml_tools" in r.groups and r.zone == "aml"),
    ("analyst-aml-tools", "permit",
     lambda r: r.is_("Human", "AnalistAML") and "analyst_tools" in r.groups and r.zone == "aml"),
    ("analyst-hold", "permit",
     lambda r: r.is_("Human", "AnalistAML") and r.action == "diode.send_hold" and r.zone == "aml"),
    ("mcp-aml-tools", "permit",
     lambda r: r.is_("Mcp", "aml") and "mcp_aml_tools" in r.groups and r.zone == "aml"),
    # zidul
    ("wall-client-not-in-aml", "forbid", lambda r: r.zone == "aml" and r.principal.zone == "client"),
    ("wall-aml-not-in-client", "forbid", lambda r: r.zone == "client" and r.principal.zone == "aml"),
    ("wall-client-no-aml-actions", "forbid", lambda r: "aml_zone" in r.groups and r.principal.zone == "client"),
    ("wall-aml-no-client-actions", "forbid", lambda r: "client_zone" in r.groups and r.principal.zone == "aml"),
    ("refund-only-motor", "forbid", lambda r: r.action == "refund.issue" and not r.is_("System", "MotorReguli")),
    ("no-llm-moves-money", "forbid", lambda r: r.role("llm_agent") and "client_effects" in r.groups),
    ("hold-only-analyst", "forbid", lambda r: r.action == "diode.send_hold" and not r.is_("Human", "AnalistAML")),
    ("facts-only-from-client", "forbid", lambda r: r.action == "diode.send_facts" and r.principal.zone != "client"),
    ("mcp-no-effects", "forbid",
     lambda r: r.principal.type == "Mcp" and ("client_effects" in r.groups or "diode" in r.groups)),
    ("only-a-person-signs", "forbid", lambda r: "signoff" in r.groups and r.principal.type != "Human"),
)


def evaluate(request: Request) -> tuple[bool, list[str]]:
    """(permis, ID-urile politicilor determinante), ca la Cedar."""
    forbids = [rid for rid, effect, cond in RULES if effect == "forbid" and cond(request)]
    if forbids:
        return False, forbids
    permits = [rid for rid, effect, cond in RULES if effect == "permit" and cond(request)]
    return bool(permits), permits
