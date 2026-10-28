"""M7: robustețe contrafactuală (docs/05 §8): „ce se schimbă dacă un fapt ar fi altfel?".

Generic: primește funcția de decizie (ex. motorul de reguli), contextul (dict) și câmpurile de încercat.
Pentru fiecare câmp, întoarce sau elimină valoarea, rulează din nou decizia și raportează dacă s-a schimbat.
Rezultatul: rata de schimbare și faptele fragile (cele de care depinde decizia). Butonul „schimbă un fapt" din UI.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable

REMOVE = object()   # varianta „câmpul lipsește"

# variante utile pentru câmpurile din RuleContext; restul primesc variante generice după tip
RULE_CONTEXT_VARIANTS: dict[str, list[Any]] = {
    "eci": ["05", "07", REMOVE],
    "sca_method": ["app_push", "sms_otp", "none"],
    "dispute_type": ["neautorizata", "app"],
    "channel": ["card", "transfer", "transfer_instant"],
    "prior_disputes_12m": [0, 4],
    "client_fraud_score": [0.05, 0.9, REMOVE],
    "seconds_after_click": [90, 3600, REMOVE],
    "sim_swap_hours_before": [1.0, REMOVE],
}


def _variants(field: str, value: Any, overrides: dict[str, list[Any]] | None) -> list[Any]:
    if overrides and field in overrides:
        cands = list(overrides[field])
    elif field in RULE_CONTEXT_VARIANTS:
        cands = list(RULE_CONTEXT_VARIANTS[field])
    elif isinstance(value, bool):
        cands = [not value, REMOVE]
    elif value is None:
        cands = [True, False]
    elif isinstance(value, (int, float)):
        cands = [0 if value else 1, value * 2 if value else 5, REMOVE]
    elif isinstance(value, dict) and "value" in value:
        cands = [{**value, "value": round(float(value["value"]) * 2, 2)}, {**value, "value": round(float(value["value"]) / 2, 2)}]
    else:
        cands = [REMOVE]
    return [c for c in cands if c is REMOVE or c != value]


def _key(out: Any) -> Any:
    """Forma comparabilă a unei decizii (RulesOutcome, Decision, dict, enum, str)."""
    if hasattr(out, "model_dump"):
        out = out.model_dump(mode="json")
    if isinstance(out, dict) and "decisions" in out:
        return tuple(sorted((str(d.get("question")), str(d.get("decision")), bool(d.get("requires_human")))
                            for d in out["decisions"]))
    if isinstance(out, dict) and "decision" in out:
        return (str(out.get("question")), str(out.get("decision")), bool(out.get("requires_human")))
    if hasattr(out, "value"):
        return out.value
    if isinstance(out, (dict, list)):
        return json.dumps(out, sort_keys=True, default=str)
    return out


def _summary(k: Any) -> Any:
    if isinstance(k, tuple) and k and isinstance(k[0], tuple):
        return [{"question": q, "decision": d, "requires_human": h} for q, d, h in k]
    if isinstance(k, tuple) and len(k) == 3:
        return {"question": k[0], "decision": k[1], "requires_human": k[2]}
    return k


def counterfactual(decide: Callable[[dict], Any], ctx: dict, fields: list[str], *,
                   variants: dict[str, list[Any]] | None = None) -> dict:
    """Rata de schimbare a deciziei când se schimbă câte un fapt + faptele fragile.

    `decide(ctx)` poate întoarce orice (RulesOutcome, dict, Verdict, str). Variantele care fac `decide` să
    arunce o excepție (ex. un câmp obligatoriu eliminat) se raportează cu `error` și nu intră în rată.
    """
    base = _key(decide(copy.deepcopy(ctx)))
    results = []
    for field in fields:
        original = ctx.get(field, None)
        for val in _variants(field, original, variants):
            c2 = copy.deepcopy(ctx)
            if val is REMOVE:
                c2.pop(field, None)
            else:
                c2[field] = val
            entry: dict[str, Any] = {"field": field, "original": original,
                                     "variant": "<eliminat>" if val is REMOVE else val}
            try:
                k = _key(decide(c2))
                entry.update(decision=_summary(k), changed=k != base, error=None)
            except Exception as e:  # noqa: BLE001 - raportăm, nu oprim analiza
                entry.update(decision=None, changed=None, error=f"{type(e).__name__}: {e}")
            results.append(entry)
    valid = [r for r in results if r["changed"] is not None]
    changed = [r for r in valid if r["changed"]]
    return {"base": _summary(base), "results": results, "n_variants": len(valid),
            "change_rate": round(len(changed) / len(valid), 4) if valid else 0.0,
            "fragile_fields": sorted({r["field"] for r in changed}), "fields": list(fields)}
