"""The labelled eval set, the offline retrieval metrics (committed query vectors) and the grounding check."""

from __future__ import annotations

import json

import pytest

from versoml.knowledge import corpus
from versoml.knowledge.build import eval_questions
from versoml.knowledge.evaluate import retrieval_eval, score_ranking


def test_eval_set_is_labelled_and_bilingual():
    rows = eval_questions()
    assert len(rows) >= 60
    langs = [r["lang"] for r in rows]
    assert abs(langs.count("ro") - langs.count("en")) <= 4
    assert len({r["id"] for r in rows}) == len(rows)
    ids = {c.id for c in corpus.build_static_corpus()}
    for row in rows:
        assert row["expected_rule_ids"] or row["expected_ids"], row["id"]
        for rid in row["expected_rule_ids"]:
            assert f"rule:{rid}" in ids, (row["id"], rid)
        for cid in row["expected_ids"]:
            ok = any(i.startswith(cid[:-1]) for i in ids) if cid.endswith("*") else cid in ids
            assert ok, (row["id"], cid)
    assert sum(r["ask"] for r in rows) >= 15


def test_metrics_math():
    row = {"expected_rule_ids": ["PAY-03"], "expected_ids": ["ctx:a#b*"]}
    s = score_ranking(row, ["x", "rule:PAY-03", "ctx:a#b-2"])
    assert s["recall@1"] == 0.0 and s["recall@3"] == 1.0 and s["hit@1"] == 0.0
    assert s["mrr@10"] == pytest.approx(0.5) and 0 < s["ndcg@10"] < 1


@pytest.fixture(scope="module")
def report(client_kb, tmp_path_factory):
    path = tmp_path_factory.mktemp("eval") / "kb.json"
    return retrieval_eval(client_kb, path=path)


def test_offline_eval_measures_all_methods(report):
    assert report["dense_query_vectors_missing"] == 0  # committed vectors: offline still measures dense
    m = report["methods"]
    assert set(m) == {"bm25", "dense", "hybrid", "hybrid_offline"}
    hybrid, dense, bm25 = m["hybrid"], m["dense"], m["bm25"]
    assert hybrid["recall@5"] >= bm25["recall@5"]
    assert hybrid["recall@5"] >= dense["recall@5"] - 0.02  # level with dense (one item at most)
    assert hybrid["recall@3"] >= dense["recall@3"]
    assert hybrid["recall@5"] >= 0.85 and hybrid["mrr@10"] >= 0.75
    assert m["hybrid_offline"]["recall@5"] >= 0.65  # the degraded path still finds most answers
    assert json.loads(open(report["path"], encoding="utf-8").read())["queries"] == report["queries"]


def test_grounding_check_offline(report):
    g = report["grounding"]
    assert g["questions"] >= 15
    assert g["grounded_rate"] == 1.0 and g["markers_valid_rate"] == 1.0 and g["answered_rate"] == 1.0
    assert g["citation_precision"] >= 0.4


def test_cli_search_offline(monkeypatch, client_kb):
    from typer.testing import CliRunner

    from versoml.knowledge import cli, kb

    monkeypatch.setitem(kb._kbs, "client", client_kb)
    result = CliRunner().invoke(cli.kb_app, ["search", "PAY-03 refund", "--k", "3"])
    assert result.exit_code == 0, result.output
    assert "rule:PAY-03" in result.output
