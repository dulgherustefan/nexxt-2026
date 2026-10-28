"""Tot ce folosește procesul zonei AML. Zona AML nu citește baza zonei client."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from versoml.config import Settings, get_settings
from versoml.contracts import PolicyDecision, Zone
from versoml.shared.events import EventBus
from versoml.shared.llm import LLMClient, get_llm
from versoml.shared.store import JsonStore

PRINCIPALS = {
    "osint": "Investigator/OSINT",
    "graf": "Investigator/Graf",
    "nevinovatie": "Investigator/AvocatNevinovatiei",
    "rts": "Investigator/RTS",
    "analist": "AnalistAML",
}


@dataclass
class AmlRuntime:
    settings: Settings = field(default_factory=get_settings)
    denials: list[dict] = field(default_factory=list)

    @cached_property
    def bus(self) -> EventBus:
        return EventBus(Zone.AML, self.settings.var_dir / "events" / "aml")

    @cached_property
    def llm(self) -> LLMClient:
        return get_llm()

    @cached_property
    def leads(self) -> JsonStore:
        return JsonStore(self.settings.aml_db, "versoml_leads", ("status", "recommendation"))

    @cached_property
    def referrals(self) -> JsonStore:
        return JsonStore(self.settings.aml_db, "versoml_referrals", ("lead_id",))

    @cached_property
    def repo(self):
        from versoml.data.repos import AmlRepo

        return AmlRepo(self.settings.aml_db)

    @cached_property
    def ledger(self):
        from versoml.shared.ledger import Ledger

        return Ledger(Zone.AML, self.settings.aml_db, self.settings.keys_dir)

    @cached_property
    def privacy(self):
        from versoml.shared.privacy import PrivacyProxy

        return PrivacyProxy(db_path=self.settings.aml_db)

    @cached_property
    def diode(self):
        from versoml.wall.diode import Diode

        return Diode(settings=self.settings, outbox_db=self.settings.aml_db)

    @cached_property
    def canaries(self):
        from versoml.wall.canary import CanaryRegistry

        return CanaryRegistry()

    def client_url(self) -> str:
        return self.settings.client_url

    def aml_url(self) -> str:
        return self.settings.aml_url

    def authorize(self, who: str, action: str, context: dict | None = None) -> PolicyDecision:
        from versoml.shared.policy import authorize

        decision = authorize(PRINCIPALS.get(who, who), action, Zone.AML, context or {})
        if not decision.allowed:
            self.denials.append(decision.model_dump(mode="json"))
            self.denials = self.denials[-200:]
        return decision


_runtime: AmlRuntime | None = None


def get_runtime() -> AmlRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AmlRuntime()
    return _runtime
