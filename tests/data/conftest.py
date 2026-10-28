"""Fixture-uri pentru testele datelor: lumea generată și bazele scrise într-un director temporar."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from versoml.config import Settings
from versoml.data.world import WORLD_NOW, generate_world


@pytest.fixture(scope="session")
def world():
    return generate_world(7)


@pytest.fixture(scope="session")
def seeded(tmp_path_factory):
    from versoml.data.seed import seed_all

    var = tmp_path_factory.mktemp("var_seed")
    settings = Settings(versoml_var_dir=var)
    result = seed_all(settings, seed=7)
    return {"settings": settings, "result": result, "client_db": Path(settings.client_db), "aml_db": Path(settings.aml_db)}


@pytest.fixture()
def dbs(seeded, tmp_path):
    """Copii proaspete ale bazelor, pentru testele care scriu."""
    c, a = tmp_path / "client_zone.db", tmp_path / "aml_zone.db"
    shutil.copy(seeded["client_db"], c)
    shutil.copy(seeded["aml_db"], a)
    return c, a


@pytest.fixture()
def clock():
    """Ceasul demo-ului: 28.10.2026, 14:50 (după plățile demo)."""
    return lambda: WORLD_NOW + timedelta(hours=4, minutes=50)
