"""Fixture-uri pentru testele ML: antrenăm o dată, într-un director temporar (fără rețea, fără LLM)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from versoml.config import Settings


@pytest.fixture(scope="session")
def trained(tmp_path_factory):
    from versoml.ml.train import train_all

    models = tmp_path_factory.mktemp("models")
    # quick: aceleași modele servite; experimentele de evaluare cinstită ale M1 se testează separat (m1_honest)
    metrics = train_all(seed=7, models_dir=models, quick=True)
    return {"dir": Path(models), "metrics": metrics}


@pytest.fixture(scope="session")
def m1_honest():
    """Evaluarea cinstită a M1 pe un corpus redus (aceleași împărțiri ca la antrenarea completă)."""
    from versoml.ml.m1_classifier import build_corpus, honest_evaluation, lookup_embeddings

    rows = build_corpus(7, n_templates=16, n_typology=4)
    E, has_e = lookup_embeddings(rows)
    return {"rows": rows, "has_e": has_e, "eval": honest_evaluation(rows, E, has_e, seed=7)}


@pytest.fixture(scope="session")
def aml_db(tmp_path_factory):
    from versoml.data.seed import seed_all

    var = tmp_path_factory.mktemp("var_ml")
    settings = Settings(versoml_var_dir=var)
    seed_all(settings, seed=7)
    return Path(settings.aml_db)


@pytest.fixture()
def rng():
    return np.random.default_rng(7)
