"""Antrenarea tuturor modelelor: `python -m versoml.ml.train` (sub 2 minute pe un laptop).

Scrie artefactele în `get_settings().models_dir` (var/models) și metricile în `models_dir/metrics.json`:
M1 (acuratețe, macro-F1, ECE pe un set ținut deoparte), M2 (AUC, PR-AUC, Brier), M5 (baseline-uri: doar reguli,
GBDT fără graf, GBDT cu graf), plus verificări de sănătate pentru M6 (legarea cazurilor din demo) și M7
(rata de schimbare contrafactuală pe cazul demo, cu oracolul tabelului de rezultate).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from versoml.data.calendar_ro import TZ
from versoml.ml.common import models_dir as _models_dir, write_json

CF_FIELDS = ["screen_showed_amount_and_payee", "device_known", "seconds_after_click", "sca_method", "amount",
             "dispute_type", "prior_disputes_12m", "client_fraud_score", "hold_signal", "notified_at"]


def _referrals(seed: int) -> list[dict]:
    from versoml.data.golden import variant_params
    from versoml.data.scenarios import SCENARIOS, build_case, build_scenario, to_dispute_facts

    bundles = [build_scenario(s, seed) for s in SCENARIOS]
    bundles += [build_case(p, seed) for p in variant_params(seed) if p.builder == "inel_carausi"]
    return [to_dispute_facts(b).model_dump(mode="json") for b in bundles if b.rule_context_hints["channel"] != "card"]


def m6_sanity(seed: int = 7) -> dict:
    from versoml.data.scenarios import SCENARIOS
    from versoml.ml.m6_entity_resolution import link_cases

    clusters = link_cases(_referrals(seed))
    demo = {SCENARIOS["demo_t1"].case_id, SCENARIOS["demo_t1_victima2"].case_id}
    inel = {c for c in ("CT-2026-900010", "CT-2026-910019", "CT-2026-910020")}
    return {"clusters": [{"case_ids": c["case_ids"], "reasons": sorted({l["reason"] for l in c["links"]})} for c in clusters],
            "demo_t1_linked_to_victima2": any(demo <= set(c["case_ids"]) for c in clusters),
            "inel_3_victims_linked": any(inel <= set(c["case_ids"]) for c in clusters)}


def m7_sanity(seed: int = 7) -> dict:
    from versoml.data.oracle import expected_outcome
    from versoml.data.scenarios import build_scenario
    from versoml.ml.m7_counterfactual import counterfactual

    ctx = build_scenario("demo_t1", seed).rule_context_hints
    variants = {"amount": [{"value": 6400.0, "currency": "RON"}], "notified_at": ["2027-12-01T10:00:00+02:00"]}
    res = counterfactual(lambda c: {"decision": expected_outcome(c)["rambursare_t1"]}, ctx, CF_FIELDS, variants=variants)
    return {"case": "demo_t1", "decide": "oracle.expected_outcome (the table shared with the rules engine)",
            "change_rate": res["change_rate"], "fragile_fields": res["fragile_fields"], "n_variants": res["n_variants"]}


def train_all(seed: int = 7, *, models_dir: str | Path | None = None) -> dict:
    """Antrenează M1, M2, M5, verifică M6/M7 și scrie `metrics.json`. Întoarce metricile."""
    from versoml.data.world import generate_world
    from versoml.ml.m1_classifier import train_m1
    from versoml.ml.m2_client_fraud import train_m2
    from versoml.ml.m5_mule import train_m5

    out = _models_dir(models_dir)
    t0 = time.time()
    timings: dict[str, float] = {}
    t = time.time()
    world = generate_world(seed)
    timings["world"] = round(time.time() - t, 2)
    t = time.time()
    m1 = train_m1(seed, models_dir=out)
    timings["m1"] = round(time.time() - t, 2)
    t = time.time()
    m2 = train_m2(seed, models_dir=out)
    timings["m2"] = round(time.time() - t, 2)
    t = time.time()
    m5 = train_m5(world, seed=seed, models_dir=out)
    timings["m5"] = round(time.time() - t, 2)
    t = time.time()
    m6 = m6_sanity(seed)
    m7 = m7_sanity(seed)
    timings["m6_m7"] = round(time.time() - t, 2)
    metrics = {"seed": seed, "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
               "seconds_total": round(time.time() - t0, 2), "seconds": timings,
               "m1_classifier": m1, "m2_client_fraud": m2, "m5_mule": m5, "m6_entity_resolution": m6,
               "m7_counterfactual": m7, "synthetic": True,
               "note": "Every metric is on synthetic data; on real data they will be lower."}
    write_json(metrics, out / "metrics.json")
    return metrics


def _summary(m: dict) -> dict:
    return {
        "seconds_total": m["seconds_total"],
        "m1": {h: {k: m["m1_classifier"][h][k] for k in ("accuracy", "macro_f1", "ece")} for h in ("channel", "dispute_type", "scenario")},
        "m1_text_only": m["m1_classifier"].get("accuracy_text_only"),
        "m2": {k: m["m2_client_fraud"]["held_out"][k] for k in ("auc", "pr_auc", "f1")},
        "m5": {k: {x: m["m5_mule"][k][x] for x in ("auc", "pr_auc", "f1", "threshold")} for k in ("rules_only", "gbdt_no_graph", "gbdt_graph")},
        "m6": {k: v for k, v in m["m6_entity_resolution"].items() if k != "clusters"},
        "m7": m["m7_counterfactual"],
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Train M1, M2 and M5 and write var/models/metrics.json.")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    print(json.dumps(_summary(train_all(args.seed)), ensure_ascii=False, indent=2))
