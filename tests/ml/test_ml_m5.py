"""M5: conturi-cărăuș, comunități, tipologii."""

from __future__ import annotations

from datetime import timedelta

from versoml.contracts import AccountScore
from versoml.data import artifacts as art
from versoml.data.aml_world import demo_mule
from versoml.data.repos import AmlRepo
from versoml.data.world import WORLD_NOW
from versoml.ml.m5_mule import communities, detect_typologies, score_accounts


def test_baselines_are_reported_honestly(trained):
    m = trained["metrics"]["m5_mule"]
    for k in ("rules_only", "gbdt_no_graph", "gbdt_graph"):
        assert {"auc", "pr_auc", "f1", "threshold"} <= set(m[k])
    assert m["gbdt_graph"]["auc"] >= 0.85
    assert m["gbdt_graph"]["auc"] >= m["rules_only"]["auc"]
    assert m["gbdt_graph"]["pr_auc"] >= m["gbdt_no_graph"]["pr_auc"] - 0.02
    assert "StratifiedGroupKFold" in m["cv"]


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
