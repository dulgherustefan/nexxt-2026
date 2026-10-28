"""Panoul zidului: cele șase straturi, atacurile de demo, jurnalul și igiena surselor platformei."""

from __future__ import annotations

from pathlib import Path

import pytest

from versoml.config import ROOT, Settings
from versoml.wall import Diode, journal, simulate_attack, wall_layers

PLATFORM_DIRS = [ROOT / "versoml" / "shared" / "ledger", ROOT / "versoml" / "shared" / "privacy",
                 ROOT / "versoml" / "shared" / "policy", ROOT / "versoml" / "wall", ROOT / "tests" / "platform"]


def test_layers_in_zone_process(tmp_path, registry):
    client = Settings(versoml_var_dir=tmp_path / "v", versoml_zone="client")
    layers = {layer["id"]: layer for layer in wall_layers(client, registry=registry,
                                                          noninterference={"passed": True, "runs": 25, "leaks": 0})}
    assert [layers[i]["status"] for i in range(1, 7)] == ["ok"] * 6
    assert all(layer["name"] and layer["detail"] for layer in layers.values())


def test_layers_flag_dev_mode_and_missing_noninterference(tmp_path, registry):
    dev = Settings(versoml_var_dir=tmp_path / "v", versoml_zone="all")
    layers = {layer["id"]: layer["status"] for layer in wall_layers(dev, registry=registry)}
    assert layers[1] == "alert" and layers[6] == "alert" and layers[3] == "ok"


@pytest.mark.parametrize("kind, layer", [("read_aml_tool", 3), ("letter_tipping_off", 5), ("prompt_injection", 3),
                                         ("diode_text_field", 2)])
def test_demo_attacks_are_blocked(kind, layer, settings, registry):
    result = simulate_attack(kind, diode=Diode(settings=settings), registry=registry, case_id="CT-2026-000123")
    assert result["blocked"] and result["layer"] == layer and result["detail"]


def test_attack_payloads_and_unknown_kind(settings, registry):
    custom = simulate_attack("read_aml_tool", {"principal": "Judecator/Procuror", "action": "aml.graph.neighborhood"})
    assert custom["blocked"] and custom["evidence"]["principal"] == 'Agent::"Judecator/Procuror"'
    passed = simulate_attack("letter_tipping_off", {"text": "Suma a fost rambursată."}, registry=registry)
    assert not passed["blocked"]
    with pytest.raises(ValueError):
        simulate_attack("ddos")


def test_journal_subscription():
    seen = []
    unsubscribe = journal.subscribe(seen.append)
    journal.record(5, "letter_block", case_id="CT-2026-000123", reasons=["Termen interzis «RTS»."], terms=["RTS"])
    unsubscribe()
    journal.record(5, "letter_block", case_id="CT-2026-000124")
    assert len(seen) == 1 and journal.blocks(10)[0]["case_id"] == "CT-2026-000124"


def _sources() -> list[Path]:
    return [p for d in PLATFORM_DIRS for p in d.rglob("*") if p.suffix in (".py", ".cedar") and p.is_file()]


def test_sources_use_comma_below_never_cedilla():
    offenders = [str(p) for p in _sources()
                 if any(c in p.read_text(encoding="utf-8") for c in ("\u015f", "\u015e", "\u0163", "\u0162"))]
    assert offenders == []


def test_platform_never_touches_the_key_file():
    assert [str(p) for p in _sources() if "API_KEY" in p.read_text(encoding="utf-8") and p.name != Path(__file__).name] == []


def test_package_level_imports():
    from versoml.shared.ledger import Ledger, verify_dossier
    from versoml.shared.policy import authorize, guarded, recent_decisions
    from versoml.shared.privacy import PrivacyProxy, assert_llm_safe, check_sink
    from versoml.wall import CanaryRegistry, Diode as WallDiode, check_letter, run_noninterference, scan_paths

    assert all(callable(x) for x in (Ledger, verify_dossier, authorize, guarded, recent_decisions, PrivacyProxy,
                                     assert_llm_safe, check_sink, CanaryRegistry, WallDiode, check_letter,
                                     run_noninterference, scan_paths))
