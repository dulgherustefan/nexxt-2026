"""Fixture-uri pentru testele motorului de reguli: parametrii nu ating niciodată var/rules_params.json."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def isolated_params(tmp_path, monkeypatch):
    """Fiecare test are fișierul lui de parametri, gol la început; calendarul implicit nu are zile închise."""
    from versoml.shared.rules import calendar_ro, params

    path = tmp_path / "rules_params.json"
    monkeypatch.setattr(params, "params_path", lambda: path)
    calendar_ro.set_bank_closure_days([])
    yield path
    calendar_ro.set_bank_closure_days([])
