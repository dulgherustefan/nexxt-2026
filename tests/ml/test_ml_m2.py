"""M2: semnalul de fraudă a clientului (doar semnal pentru om): LightGBM + LR + IsolationForest, stivuite."""

from __future__ import annotations

import pytest

from versoml.data.features import M2_FEATURES
from versoml.data.repos import ClientRepo
from versoml.data.scenarios import build_scenario
from versoml.ml.m2_client_fraud import (LABEL_NOISE, TRAIN_DAYS, client_fraud_signal, features_from_repo,
                                        simulate_disputes)


def test_metrics_temporal_split_and_members(trained):
    m = trained["metrics"]["m2_client_fraud"]
    t = m["temporal_split"]
    assert m["model_version"].startswith("m2-stack-") and m["label_noise"] == LABEL_NOISE
    assert t["ensemble"]["auc"] >= 0.80
    assert t["ensemble"]["auc"] >= max(t["lgbm"]["auc"], t["lr"]["auc"]) - 0.01
    assert t["ensemble"]["auc_clean_labels"] > t["ensemble"]["auc"]          # the noise is in the labels
    assert t["iforest_alone"]["auc"] < t["ensemble"]["auc"]                  # anomaly alone is a weak signal
    assert m["held_out"] == t["ensemble"]


def test_simulator_has_noise_drift_and_a_clean_temporal_split():
    df = simulate_disputes(n=3000, seed=11)
    flipped = (df["label"] != df["label_clean"]).mean()
    assert 0.03 <= flipped <= 0.07
    tr, te = df[df["day"] < TRAIN_DAYS], df[df["day"] >= TRAIN_DAYS]
    assert tr["day"].max() < te["day"].min() and len(te) > 0.15 * len(df)
    # drift: more "stolen phone" friendly fraud later (device unknown among fraud cases)
    fr = df[df["label_clean"] == 1]
    early, late = fr[fr["day"] < 120], fr[fr["day"] >= 240]
    assert (late["device_known"] == 0).mean() > (early["device_known"] == 0).mean()


def test_signal_separates_scenarios(trained):
    hi = client_fraud_signal(build_scenario("frauda_client").records["m2_features"], models_dir=trained["dir"])
    assert hi["score"] >= 0.7 and hi["signal_only"] is True
    for sid in ("demo_t1", "phishing_link", "card_ecom_fara_3ds", "sim_swap"):
        lo = client_fraud_signal(build_scenario(sid).records["m2_features"], models_dir=trained["dir"])
        assert lo["score"] <= 0.3, sid
    assert len(hi["top_features"]) == 5
    assert all(isinstance(n, str) and n in M2_FEATURES and isinstance(v, float) for n, v in hi["top_features"])
    assert set(hi["members"]) == {"lgbm", "lr", "anomaly"} and len(hi["lr_top_features"]) == 5


def test_missing_features_are_tolerated(trained):
    r = client_fraud_signal({"prior_disputes_12m": 5}, models_dir=trained["dir"])
    assert 0.0 <= r["score"] <= 1.0


def test_orchestrator_keys_are_mapped(trained):
    # the judge graph sends beneficiary_new / channel; they map to beneficiary_seen_before / channel_card
    a = client_fraud_signal({"beneficiary_new": True, "channel": "transfer", "device_known": 0}, models_dir=trained["dir"])
    b = client_fraud_signal({"beneficiary_seen_before": 0.0, "channel_card": 0.0, "device_known": 0}, models_dir=trained["dir"])
    assert a["score"] == pytest.approx(b["score"])


def test_inference_is_fast(trained):
    import time

    f = build_scenario("phishing_link").records["m2_features"]
    client_fraud_signal(f, models_dir=trained["dir"])
    t = time.perf_counter()
    for _ in range(10):
        client_fraud_signal(f, models_dir=trained["dir"])
    assert (time.perf_counter() - t) / 10 < 0.05


def test_features_from_repo_match_records(aml_db):
    client_db = aml_db.parent / "client_zone.db"
    repo = ClientRepo(client_db)
    b = build_scenario("frauda_client")
    f = features_from_repo(repo, "CUST-SC-07", b.complaint.transaction_refs[0], b.complaint.received_at)
    exp = b.records["m2_features"]
    for k in ("prior_disputes_12m", "device_known", "merchant_familiarity", "channel_card", "sca_strong"):
        assert f[k] == pytest.approx(exp[k]), k
