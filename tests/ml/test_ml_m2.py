"""M2: semnalul de fraudă a clientului (doar semnal pentru om)."""

from __future__ import annotations

import pytest

from versoml.data.features import M2_FEATURES
from versoml.data.repos import ClientRepo
from versoml.data.scenarios import build_scenario
from versoml.ml.m2_client_fraud import client_fraud_signal, features_from_repo


def test_metrics(trained):
    m = trained["metrics"]["m2_client_fraud"]
    assert m["held_out"]["auc"] >= 0.85 and m["model_version"].startswith("m2-")


def test_signal_separates_scenarios(trained):
    hi = client_fraud_signal(build_scenario("frauda_client").records["m2_features"], models_dir=trained["dir"])
    assert hi["score"] >= 0.7 and hi["signal_only"] is True
    for sid in ("demo_t1", "phishing_link", "card_ecom_fara_3ds", "sim_swap"):
        lo = client_fraud_signal(build_scenario(sid).records["m2_features"], models_dir=trained["dir"])
        assert lo["score"] <= 0.3, sid
    assert len(hi["top_features"]) == 5
    assert all(isinstance(n, str) and n in M2_FEATURES and isinstance(v, float) for n, v in hi["top_features"])


def test_missing_features_are_tolerated(trained):
    r = client_fraud_signal({"prior_disputes_12m": 5}, models_dir=trained["dir"])
    assert 0.0 <= r["score"] <= 1.0


def test_features_from_repo_match_records(aml_db):
    client_db = aml_db.parent / "client_zone.db"
    repo = ClientRepo(client_db)
    b = build_scenario("frauda_client")
    f = features_from_repo(repo, "CUST-SC-07", b.complaint.transaction_refs[0], b.complaint.received_at)
    exp = b.records["m2_features"]
    for k in ("prior_disputes_12m", "device_known", "merchant_familiarity", "channel_card", "sca_strong"):
        assert f[k] == pytest.approx(exp[k]), k
