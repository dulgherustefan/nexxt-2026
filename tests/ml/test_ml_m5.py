"""M5: conturi-cărăuș (stivă GBDT pe graf + PPR + IsolationForest + reguli), comunități, tipologii."""

from __future__ import annotations

from datetime import timedelta

import networkx as nx
import pytest

from versoml.contracts import AccountScore
from versoml.data import artifacts as art
from versoml.data.aml_world import demo_mule
from versoml.data.calendar_ro import parse_ts
from versoml.data.repos import AmlRepo
from versoml.data.world import WORLD_NOW, generate_world
from versoml.ml import m5_mule as M
from versoml.ml.m5_mule import communities, detect_typologies, score_accounts


@pytest.fixture(scope="module")
def world():
    return generate_world(7)


def test_baselines_are_reported_honestly(trained):
    m = trained["metrics"]["m5_mule"]
    for k in ("rules_only", "gbdt_no_graph", "gbdt_graph"):
        assert {"auc", "pr_auc", "f1", "threshold"} <= set(m[k])
    assert m["gbdt_graph"]["auc"] >= 0.85
    assert m["gbdt_graph"]["auc"] >= m["rules_only"]["auc"]
    assert m["gbdt_graph"]["pr_auc"] >= m["gbdt_no_graph"]["pr_auc"] - 0.02
    assert "StratifiedGroupKFold" in m["cv"]
    t = m["temporal_split"]
    for k in ("rules_only", "gbdt_no_graph", "gbdt_graph", "ensemble", "ppr_alone", "iforest_alone"):
        assert "auc" in t[k], k
    assert t["ensemble"]["auc"] >= 0.9 and t["ensemble"]["auc"] > t["rules_only"]["auc"]
    assert t["ensemble"]["auc"] >= t["gbdt_graph"]["auc"] - 0.01        # the stack does not lose to its GBDT
    assert len(m["meta_coef"]) == len(m["meta_inputs"]) == 4


def test_temporal_split_has_no_leakage(trained):
    t = trained["metrics"]["m5_mule"]["temporal_split"]
    test_start = parse_ts(t["test_window"][0])
    assert parse_ts(t["max_train_flow_ts"]) <= test_start - timedelta(days=t["label_delay_days"])
    assert all(parse_ts(a) <= test_start - timedelta(days=t["label_delay_days"]) for a in t["train_snapshots_as_of"])
    assert t["test_mules"] > 50 and t["n_train"] > t["n_test"]


def test_window_labels_follow_pattern_flows(world):
    labels_now = M.window_labels(world, as_of=world.now)
    labels_old = M.window_labels(world, as_of=world.now - timedelta(days=67))
    assert demo_mule(7)["iban"] in labels_now and demo_mule(7)["iban"] not in labels_old
    assert labels_now and labels_old and set(labels_now) != set(labels_old)
    # patterns list only their own flows (not the normal life of the mule accounts)
    flows = {f["flow_id"]: f for f in world.flows}
    p = world.patterns[0]
    assert all(flows[fid]["from_iban"] in p["mules"] or flows[fid]["to_iban"] in p["mules"]
               for fid in p["flow_ids"] if fid in flows)


def test_training_frame_uses_only_past_flows(world):
    as_of = world.now - timedelta(days=37)
    f = M.training_frame(world, as_of=as_of)
    assert f["max_flow_ts"] <= as_of and len(f["nodes"]) == len(f["y"]) == len(f["ppr"])
    assert f["y"].sum() > 20


def test_ppr_spreads_from_reported_accounts_only():
    g = nx.DiGraph()
    g.add_edge("V", "A", amount=1000)
    g.add_edge("A", "B", amount=900)
    g.add_edge("C", "D", amount=500)
    kinds = {n: "internal" for n in "VABCD"}
    feats = {"A": {"victim_reports": 1}, "B": {}, "C": {}, "D": {}, "V": {}}
    ppr = M.ppr_from_seeds(g, kinds, feats)
    assert ppr["A"] > ppr["B"] > 0 and ppr["C"] == ppr["D"] == 0.0 and ppr["V"] == 0.0


def _graph(aml_db):
    return AmlRepo(aml_db, clock=lambda: WORLD_NOW + timedelta(hours=1)).neighborhood([demo_mule(7)["iban"]], hops=2, days=30)


def test_demo_mule_scores_high(trained, aml_db):
    g = _graph(aml_db)
    scores = score_accounts(g, models_dir=trained["dir"])
    assert scores and all(isinstance(s, AccountScore) for s in scores)
    top = {s.account: s for s in scores}[demo_mule(7)["iban"]]
    assert top.score >= 0.7 and top.label == "carausi_probabil"
    assert len(top.top_features) == 5 and all(isinstance(v, float) for _, v in top.top_features)
    assert top.community is not None
    assert all(s.account != art.CRYPTO_EXCHANGE_IBAN for s in scores)
    others = [s for s in scores if s.account != top.account]
    assert others and max(s.score for s in others) < top.score


def test_scoring_is_fast(trained, aml_db):
    import time

    g = _graph(aml_db)
    score_accounts(g, models_dir=trained["dir"])
    t = time.perf_counter()
    for _ in range(5):
        score_accounts(g, models_dir=trained["dir"])
    assert (time.perf_counter() - t) / 5 < 0.1


def test_communities_deterministic(aml_db):
    g = _graph(aml_db)
    c1, c2 = communities(g), communities(g)
    assert c1 == c2 and set(c1) == {n["id"] for n in g["nodes"]}


def test_typologies_on_demo_mule(aml_db):
    dm = demo_mule(7)["iban"]
    found = {t["typology"] for t in detect_typologies(_graph(aml_db)) if t["center"] == dm}
    assert {"fan_in", "rapid_pass_through", "crypto_cash_out"} <= found


def test_typology_rules_on_toy_graph():
    t0 = WORLD_NOW - timedelta(days=2)
    nodes = [{"id": x, "kind": "internal", "features": {"degree_total": 3}} for x in ("A", "B", "C", "S", "M1", "M2", "M3", "T")]
    e = lambda i, s, t, a, h: {"id": i, "source": s, "target": t, "amount": a, "ts": (t0 + timedelta(hours=h)).isoformat()}  # noqa: E731
    edges = [e("c1", "A", "B", 1000, 0), e("c2", "B", "C", 980, 2), e("c3", "C", "A", 960, 4),
             e("s1", "S", "M1", 500, 1), e("s2", "S", "M2", 500, 1), e("s3", "S", "M3", 500, 1),
             e("g1", "M1", "T", 490, 3), e("g2", "M2", "T", 490, 3), e("g3", "M3", "T", 490, 3)]
    typ = {t["typology"] for t in detect_typologies({"nodes": nodes, "edges": edges})}
    assert {"cycle", "scatter_gather", "fan_out", "fan_in"} <= typ
