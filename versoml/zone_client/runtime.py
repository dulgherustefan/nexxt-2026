"""Everything the client zone process uses. The client zone has no path to the AML database."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from versoml.config import Settings, get_settings
from versoml.contracts import PolicyDecision, Zone
from versoml.shared.events import EventBus
from versoml.shared.llm import LLMClient, get_llm
from versoml.shared.store import JsonStore

log = logging.getLogger("versoml.client")

PRINCIPALS = {
    "receptor": "Judecator/Receptor",
    "clasificator": "Judecator/Clasificator",
    "colector": "Judecator/Colector",
    "procuror": "Judecator/Procuror",
    "avocat": "Judecator/Avocat",
    "recuperare": "Judecator/Recuperare",
    "redactor": "Judecator/Redactor",
    "motor": "MotorReguli",
}


@dataclass
class ClientRuntime:
    settings: Settings = field(default_factory=get_settings)
    denials: list[dict] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)

    @cached_property
    def bus(self) -> EventBus:
        return EventBus(Zone.CLIENT, self.settings.var_dir / "events" / "client")

    @cached_property
    def llm(self) -> LLMClient:
        return get_llm()

    @cached_property
    def cases(self) -> JsonStore:
        return JsonStore(self.settings.client_db, "versoml_cases",
                         ("customer_ref", "status", "scenario", "verdict"))

    @cached_property
    def notifications(self) -> JsonStore:
        return JsonStore(self.settings.client_db, "versoml_bank_notifications", ("customer_ref",))

    @cached_property
    def repo(self):
        from versoml.data.repos import ClientRepo

        return ClientRepo(self.settings.client_db)

    @cached_property
    def ledger(self):
        from versoml.shared.ledger import Ledger

        return Ledger(Zone.CLIENT, self.settings.client_db, self.settings.keys_dir)

    @cached_property
    def privacy(self):
        from versoml.shared.privacy import PrivacyProxy

        return PrivacyProxy(db_path=self.settings.client_db)

    @cached_property
    def diode(self):
        from versoml.wall.diode import Diode

        return Diode(settings=self.settings, outbox_db=self.settings.client_db,
                     known_case=lambda case_id: self.cases.get(case_id) is not None)

    def aml_url(self) -> str:
        return self.settings.aml_url

    def client_url(self) -> str:
        return self.settings.client_url

    def authorize(self, who: str, action: str, zone: Zone = Zone.CLIENT, context: dict | None = None) -> PolicyDecision:
        """The Cedar checkpoint for every tool. Denials are kept for the website."""
        from versoml.shared.policy import authorize

        principal = PRINCIPALS.get(who, who)
        decision = authorize(principal, action, zone, context or {})
        if not decision.allowed:
            self.denials.append(decision.model_dump(mode="json"))
            self.denials = self.denials[-200:]
        return decision

    def record_block(self, case_id: str, reasons: list[str], terms: list[str]) -> None:
        from versoml.shared.events import now

        self.blocks.append({"at": now().isoformat(), "case_id": case_id, "reasons": reasons, "terms": terms})
        self.blocks = self.blocks[-200:]

    def notify(self, customer_ref: str, text: str, kind: str = "info", data: dict[str, Any] | None = None) -> None:
        from versoml.shared.events import now
        import uuid

        nid = f"N-{uuid.uuid4().hex[:10]}"
        self.notifications.put(nid, {"id": nid, "customer_ref": customer_ref, "ts": now().isoformat(),
                                     "text": text, "kind": kind, "data": data or {}})


_runtime: ClientRuntime | None = None


def get_runtime() -> ClientRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ClientRuntime()
    return _runtime
