"""Fixture-uri pentru testele platformei. Toate datele sunt sintetice; nimic nu scrie în var/ real."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from versoml.config import Settings
from versoml.contracts import DisputeFacts, HoldSignal, Zone
from versoml.shared.ledger import Ledger
from versoml.shared.policy import clear_decisions, set_engine
from versoml.wall import CanaryRegistry, Diode, InProcessTransport, journal


@pytest.fixture(autouse=True)
def _clean_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Jurnale goale și niciun fișier scris în var/ real (registrul implicit de canary e mutat în tmp)."""
    from versoml.wall import canary, letter_filter

    monkeypatch.setattr(canary, "default_path", lambda: tmp_path / "default_wall" / "canary_hashes.json")
    monkeypatch.setattr(letter_filter, "_default_registry", None)
    clear_decisions()
    journal.clear()
    set_engine("auto")
    yield
    set_engine("auto")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(versoml_var_dir=tmp_path / "var", versoml_diode_secret=None, versoml_aml_url=None, versoml_client_url=None)


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(Zone.CLIENT, tmp_path / "client_zone.db", tmp_path / "keys")


@pytest.fixture
def aml_ledger(tmp_path: Path) -> Ledger:
    return Ledger(Zone.AML, tmp_path / "aml_zone.db", tmp_path / "keys")


@pytest.fixture
def registry(tmp_path: Path) -> CanaryRegistry:
    return CanaryRegistry(tmp_path / "wall" / "canary_hashes.json")


@pytest.fixture
def diodes(settings: Settings) -> tuple[Diode, Diode, InProcessTransport, InProcessTransport]:
    """(client, aml, transport client→aml, transport aml→client) cu același secret generat."""
    client = Diode(settings=settings)
    aml = Diode(settings=settings)
    to_aml = InProcessTransport(receiver=aml)
    to_client = InProcessTransport(receiver=client)
    client.transport = to_aml
    aml.transport = to_client
    return client, aml, to_aml, to_client


@pytest.fixture
def facts() -> DisputeFacts:
    return DisputeFacts(
        case_id="CT-2026-000123",
        victim_ref="VCT-8f21",
        channel="transfer",
        dispute_type="neautorizata",
        scenario="phishing_link",
        amount={"value": 3200.0, "currency": "RON"},
        executed_at=datetime(2026, 10, 28, 12, 2, 11, tzinfo=timezone.utc),
        beneficiary={"iban": "RO49AAAA1B31007593840000", "name": "SC EXEMPLU SRL", "cui": "RO00000000",
                     "bank_bic": "AAAARO22"},
        attack={"domain": "livrare-bancademo.example", "domain_age_hours": 6, "lookalike_score": 0.93},
        fact_ids=["EV-004", "EV-007", "EV-011"],
    )


@pytest.fixture
def hold() -> HoldSignal:
    return HoldSignal(case_id="CT-2026-000123", hold=True, approved_by="ANALIST-07",
                      approved_at=datetime(2026, 10, 28, 13, 10, tzinfo=timezone.utc), authority_notified=True)
