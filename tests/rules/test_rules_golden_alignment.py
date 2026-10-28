"""Alinierea cu setul de aur: scenariile din `versoml.data` trec prin motor și dau rezultatul oracolului.

Se sare peste test dacă modulul de date lipsește sau nu poate construi scenariile (e scris în paralel).
Verificările sunt cele din versoml/eval/run.py: verdictul, semnătura umană, termenul T+1, ruta de recuperare.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from versoml.contracts import RuleContext
from versoml.shared.rules import evaluate

scenarios = pytest.importorskip("versoml.data.scenarios")


def recovery_of(out) -> str | None:
    for q in ("recuperare_escroc", "recuperare_client"):
        d = next((x for x in out.decisions if x.question.value == q), None)
        if d and d.decision.value in ("RECHEMARE", "CHARGEBACK", "RECUPERARE_PROPUSA"):
            return d.decision.value
    d = next((x for x in out.decisions if x.question.value == "recuperare_client"), None)
    return d.decision.value if d else None


@pytest.mark.parametrize("scenario_id", sorted(getattr(scenarios, "SCENARIOS", {})))
def test_scenariul_din_setul_de_aur(scenario_id):
    try:
        bundle = scenarios.build_scenario(scenario_id)
        ctx = RuleContext.model_validate(bundle.rule_context_hints)
        expected = dict(bundle.expected)
    except Exception as exc:  # noqa: BLE001  (modulul de date e în lucru)
        pytest.skip(f"scenariul nu se poate construi: {exc}")
    out = evaluate(ctx)
    refund = out.decisions[0]
    assert refund.decision.value == expected["rambursare_t1"], refund.rule_ids
    assert refund.requires_human == expected["requires_human"]
    if expected.get("t1_deadline"):
        assert refund.deadline is not None
        assert abs((refund.deadline - datetime.fromisoformat(expected["t1_deadline"])).total_seconds()) < 2
    if expected.get("recovery") is not None:
        assert recovery_of(out) == expected["recovery"]
    if expected.get("chargeback_reason"):
        cb = next(h for h in out.hits if h.rule_id == "DSP-52")
        assert cb.params["reason_code"] == expected["chargeback_reason"]
