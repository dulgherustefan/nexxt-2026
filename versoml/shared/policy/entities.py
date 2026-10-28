"""Principalii, acțiunile (tool-urile) și entitățile Cedar ale VersoML.

Șirurile de principal acceptate sunt cele din contractul cu orchestrarea: „Judecator/Redactor",
„MotorReguli", „AnalistAML", „Mcp/client" etc. (și forma Cedar `Agent::"Judecator/Redactor"`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from versoml.contracts import Zone
from versoml.shared.privacy.text import fold

# ---------------------------------------------------------------- principali

PRINCIPALS: dict[str, dict[str, Any]] = {
    # zona client: agenții Judecătorului
    "Judecator/Receptor": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Clasificator": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Colector": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Procuror": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Avocat": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Recuperare": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "Judecator/Redactor": {"type": "Agent", "zone": "client", "kind": "agent", "roles": ["client_agent", "llm_agent"]},
    "MotorReguli": {"type": "System", "zone": "client", "kind": "system", "roles": []},
    "Operator": {"type": "Human", "zone": "client", "kind": "human", "roles": []},
    "Mcp/client": {"type": "Mcp", "id": "client", "zone": "client", "kind": "mcp", "roles": []},
    # zona AML: agenții Investigatorului
    "Investigator/OSINT": {"type": "Agent", "zone": "aml", "kind": "agent", "roles": ["aml_agent", "llm_agent"]},
    "Investigator/Graf": {"type": "Agent", "zone": "aml", "kind": "agent", "roles": ["aml_agent", "llm_agent"]},
    "Investigator/AvocatNevinovatiei": {"type": "Agent", "zone": "aml", "kind": "agent", "roles": ["aml_agent", "llm_agent"]},
    "Investigator/RTS": {"type": "Agent", "zone": "aml", "kind": "agent", "roles": ["aml_agent", "llm_agent"]},
    "AnalistAML": {"type": "Human", "zone": "aml", "kind": "human", "roles": []},
    "Mcp/aml": {"type": "Mcp", "id": "aml", "zone": "aml", "kind": "mcp", "roles": []},
}
ROLES = ("client_agent", "aml_agent", "llm_agent")
UNKNOWN_TYPE = "Necunoscut"

# ---------------------------------------------------------------- acțiuni (tool-uri)

CLIENT_TOOLS = (
    "bank-core.get_transaction", "bank-core.get_customer_ref", "bank-core.get_balance",
    "bank-core.beneficiary_seen_before", "bank-core.get_prior_disputes",
    "sca-logs.get_auth_events", "sca-logs.get_screen_shown",
    "device.get_session", "device.get_device_history",
    "domain-intel.rdap_lookup", "domain-intel.ct_first_seen", "domain-intel.lookalike_score",
    "domain-intel.openphish_check", "domain-intel.fetch_page", "domain-intel.sandbox_screenshot",
    "recall.draft_camt056", "recall.draft_ron_recall", "recall.chargeback_eligibility", "recall.draft_dnsc_report",
    "letters.draft_letter", "letters.check_letter",
    "ledger.read_client",
    "diode.send_facts",
)
CLIENT_EFFECTS = ("refund.issue",)
AML_TOOLS = (
    "aml.graph.neighborhood", "aml.graph.link_cases", "aml.graph.communities", "aml.graph.mule_score",
    "aml.graph.typologies",
    "aml.osint.web_search", "aml.osint.news_search", "aml.osint.anaf_company", "aml.osint.sanctions_screen",
    "aml.osint.rdap_domain", "aml.osint.ct_certificates", "aml.osint.dns_records", "aml.osint.lookalike_score",
    "aml.osint.fetch_page", "aml.osint.openphish_check", "aml.osint.phone_intel", "aml.osint.validate_iban",
    "aml.osint.wayback_first_seen", "aml.osint.ip_geo",
    "aml.sanctions.screen", "aml.str.draft", "ledger.read_aml",
)
ANALYST_TOOLS = ("aml.leads.read", "aml.leads.decide", "ledger.read_aml")
MCP_CLIENT_TOOLS = (
    "mcp.rules.catalog", "mcp.rules.deadline", "mcp.ledger.verify", "mcp.cases.read", "mcp.cases.create",
    "mcp.cases.approve", "mcp.rules.evaluate", "mcp.wall.read", "letters.check_letter", "domain-intel.lookalike_score",
)
MCP_AML_TOOLS = (
    "mcp.rules.catalog", "mcp.rules.deadline", "mcp.ledger.verify", "aml.leads.read", "aml.leads.decide",
    "aml.osint.web_search", "aml.osint.anaf_company", "aml.sanctions.screen",
)
DIODE_ACTIONS = ("diode.send_facts", "diode.send_hold")

# „domain-intel.*", „aml.graph.*", „aml.osint.*": tool-uri noi de citire intră automat în grupul zonei
WILDCARDS = {"domain-intel.": "client_tools", "aml.graph.": "aml_tools", "aml.osint.": "aml_tools"}
# Ce acțiuni aparțin unei zone (folosit de forbid-urile zidului, inclusiv pentru tool-uri necunoscute)
CLIENT_ZONE_PREFIXES = ("bank-core.", "sca-logs.", "device.", "domain-intel.", "recall.", "letters.", "refund.")
CLIENT_ZONE_EXACT = frozenset({"ledger.read_client", "diode.send_facts"})
AML_ZONE_PREFIXES = ("aml.",)
AML_ZONE_EXACT = frozenset({"ledger.read_aml", "diode.send_hold"})

GROUPS = ("client_tools", "client_effects", "aml_tools", "analyst_tools", "mcp_client_tools", "mcp_aml_tools",
          "diode", "client_zone", "aml_zone")
ROOT_GROUP = "any_tool"

_GROUP_MEMBERS = {
    "client_tools": frozenset(CLIENT_TOOLS),
    "client_effects": frozenset(CLIENT_EFFECTS),
    "aml_tools": frozenset(AML_TOOLS),
    "analyst_tools": frozenset(ANALYST_TOOLS),
    "mcp_client_tools": frozenset(MCP_CLIENT_TOOLS),
    "mcp_aml_tools": frozenset(MCP_AML_TOOLS),
    "diode": frozenset(DIODE_ACTIONS),
}
KNOWN_ACTIONS = tuple(sorted(set().union(*_GROUP_MEMBERS.values())))

_ACTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,127}$")


def action_groups(action: str) -> frozenset[str]:
    """Grupurile (părinții Cedar) unei acțiuni, inclusiv pentru tool-uri noi după prefix."""
    groups = {g for g, members in _GROUP_MEMBERS.items() if action in members}
    for prefix, group in WILDCARDS.items():
        if action.startswith(prefix):
            groups.add(group)
    if action in CLIENT_ZONE_EXACT or action.startswith(CLIENT_ZONE_PREFIXES):
        groups.add("client_zone")
    if action in AML_ZONE_EXACT or action.startswith(AML_ZONE_PREFIXES):
        groups.add("aml_zone")
    return frozenset(groups)


def valid_action_name(action: str) -> bool:
    return bool(_ACTION_RE.match(action or ""))


# ---------------------------------------------------------------- normalizarea principalilor

@dataclass(frozen=True)
class PrincipalRef:
    name: str                  # forma canonică („Judecator/Redactor") sau textul primit, dacă e necunoscut
    type: str                  # Agent | System | Human | Mcp | Necunoscut
    id: str
    zone: str                  # client | aml | unknown
    kind: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    known: bool = True

    @property
    def uid(self) -> str:
        return f'{self.type}::{json.dumps(self.id, ensure_ascii=False)}'

    def entity(self) -> dict[str, Any]:
        return {
            "uid": {"type": self.type, "id": self.id},
            "attrs": {"zone": self.zone, "kind": self.kind},
            "parents": [{"type": "Role", "id": r} for r in self.roles],
        }


def _squash(text: str) -> str:
    out = re.sub(r"[\s_]+", "", fold(text))
    for long, short in (("judecatorul", "judecator"), ("investigatorul", "investigator"),
                        ("avocatulnevinovatiei", "avocatnevinovatiei"), ("avocatul", "avocat"),
                        ("redactorul", "redactor"), ("receptorul", "receptor"), ("clasificatorul", "clasificator"),
                        ("colectorul", "colector"), ("procurorul", "procuror"), ("motorulreguli", "motorreguli"),
                        ("motoruldereguli", "motorreguli"), ("analistulaml", "analistaml")):
        out = out.replace(long, short)
    return out


@lru_cache(maxsize=1)
def _lookup() -> dict[str, str]:
    table: dict[str, str] = {}
    for name, info in PRINCIPALS.items():
        pid = info.get("id", name)
        table[_squash(name)] = name
        table[_squash(f"{info['type']}::{pid}")] = name
        table[_squash(f"{info['type']}/{pid}")] = name
    return table


_CEDAR_UID = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*::\s*"?(.*?)"?\s*$')


def parse_principal(principal: str) -> PrincipalRef:
    """Transformă șirul primit în principalul canonic. Necunoscut → zona „unknown” (refuz implicit)."""
    raw = str(principal or "").strip()
    candidates = [raw]
    m = _CEDAR_UID.match(raw)
    if m:
        candidates += [f"{m.group(1)}::{m.group(2)}", m.group(2)]
    for cand in candidates:
        name = _lookup().get(_squash(cand))
        if name:
            info = PRINCIPALS[name]
            return PrincipalRef(name=name, type=info["type"], id=info.get("id", name), zone=info["zone"],
                                kind=info["kind"], roles=tuple(info["roles"]), known=True)
    return PrincipalRef(name=raw or "(empty)", type=UNKNOWN_TYPE, id=raw or "(empty)", zone="unknown",
                        kind="unknown", roles=(), known=False)


def zone_value(zone: Zone | str) -> str:
    """„client”/„aml” din Zone sau text (fără diferență de majuscule)."""
    return zone.value if isinstance(zone, Zone) else Zone(str(zone).strip().lower()).value


# ---------------------------------------------------------------- entitățile Cedar

def _action_entity(action: str) -> dict[str, Any]:
    return {"uid": {"type": "Action", "id": action}, "attrs": {},
            "parents": [{"type": "Action", "id": g} for g in sorted(action_groups(action))]}


@lru_cache(maxsize=1)
def base_entities() -> tuple[dict[str, Any], ...]:
    """Entitățile fixe: roluri, zone, principali cunoscuți, grupuri și tool-uri cunoscute."""
    ents: list[dict[str, Any]] = [{"uid": {"type": "Role", "id": r}, "attrs": {}, "parents": []} for r in ROLES]
    ents += [{"uid": {"type": "Zone", "id": z.value}, "attrs": {}, "parents": []} for z in Zone]
    ents += [parse_principal(name).entity() for name in PRINCIPALS]
    ents.append({"uid": {"type": "Action", "id": ROOT_GROUP}, "attrs": {}, "parents": []})
    ents += [{"uid": {"type": "Action", "id": g}, "attrs": {}, "parents": [{"type": "Action", "id": ROOT_GROUP}]}
             for g in GROUPS]
    ents += [_action_entity(a) for a in KNOWN_ACTIONS]
    return tuple(ents)


def request_entities(principal: PrincipalRef, action: str) -> list[dict[str, Any]]:
    """Entitățile de adăugat pentru o cerere (principal sau tool necunoscut)."""
    extra = []
    if not principal.known:
        extra.append(principal.entity())
    if action not in KNOWN_ACTIONS:
        extra.append(_action_entity(action))
    return extra


def cedar_schema() -> str:
    """Schema Cedar a entităților și acțiunilor cunoscute (pentru validarea politicilor)."""
    types = "Agent, System, Human, Mcp, " + UNKNOWN_TYPE
    lines = [
        "entity Role;",
        "entity Zone;",
        *(f"entity {t} in [Role] {{ zone: String, kind: String }};" for t in ("Agent", "System", "Human", "Mcp")),
        f"entity {UNKNOWN_TYPE} {{ zone: String, kind: String }};",
        f'action "{ROOT_GROUP}";',
        *(f'action "{g}" in ["{ROOT_GROUP}"];' for g in GROUPS),
    ]
    context = "{ approved_by_human?: Bool, within_auto_cap?: Bool }"
    for action in KNOWN_ACTIONS:
        parents = ", ".join(f'"{g}"' for g in sorted(action_groups(action)))
        lines.append(f'action "{action}" in [{parents}] appliesTo {{ principal: [{types}], resource: [Zone], '
                     f"context: {context} }};")
    return "\n".join(lines)
