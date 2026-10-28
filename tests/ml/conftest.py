"""Fixture-uri pentru testele ML: antrenăm o dată, într-un director temporar (fără rețea, fără LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from versoml.config import Settings


@pytest.fixture(scope="session")
def trained(tmp_path_factory):
    from versoml.ml.train import train_all

    models = tmp_path_factory.mktemp("models")
    metrics = train_all(seed=7, models_dir=models)
    return {"dir": Path(models), "metrics": metrics}


@pytest.fixture(scope="session")
def aml_db(tmp_path_factory):
    from versoml.data.seed import seed_all

    var = tmp_path_factory.mktemp("var_ml")
    settings = Settings(versoml_var_dir=var)
    seed_all(settings, seed=7)
    return Path(settings.aml_db)
