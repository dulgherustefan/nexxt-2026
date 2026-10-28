"""Rezultatul așteptat al unui caz, după tabelul comun cu motorul de reguli (folosit doar pentru setul de aur).

Nu e motorul de reguli: e lectura de referință a tabelului de rezultate, ca testele să aibă un adevăr fix.
Pragurile marcate PARAM sunt valorile implicite ale parametrilor [U]; cazurile din setul de aur sunt alese
departe de praguri (în afară de cazurile-limită etichetate), ca un motor cu alte praguri rezonabile să dea
același rezultat.

| scenariu | rambursare_t1 | requires_human | recuperare |
|---|---|---|---|
| neautorizată fără semnale de risc | RAMBURSEAZA dacă suma <= plafon, altfel RAMBURSEAZA_CU_APROBARE | nu / da | transfer: RECHEMARE; card ECI 05+CAVV: RECUPERARE_PROPUSA; alt card: CHARGEBACK 10.4 |
| neautorizată cu semnal de fraudă a clientului | RAMBURSEAZA_CU_APROBARE; cu HoldSignal + autoritate notificată: EXCEPTIE_FRAUDA_CLIENT | da | null |
| notificată după 13 luni | RESPINGE_TARDIV | da (GDPR art. 22) | null |
| APP (autorizată sub manipulare) | NU_SE_APLICA_T1 | da | RECHEMARE |
| eroare de procesare (plată dublă) | NU_SE_APLICA_T1 | nu | CHARGEBACK 12.6.1 |
| dispută cu comerciantul (nelivrat) | NU_SE_APLICA_T1 | nu | CHARGEBACK 13.1 |
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from versoml.data.calendar_ro import end_of_next_business_day, parse_ts, within_13_months

CAP_RON = 5000.0                 # PARAM [U]: plafonul de rambursare automată (docs/05 §3, DSP-59)
RISK_SCORE_THRESHOLD = 0.7       # PARAM [U]: scor M2 de la care e semnal pentru om
RISK_PRIOR_DISPUTES = 3          # PARAM [U]: contestații în 12 luni de la care e semnal pentru om
EUR_RON = 5.0                    # PARAM [U]: cursul pentru plafonul în lei (ca `eur_ron_rate` din reguli)


def _get(ctx: Any, key: str, default: Any = None) -> Any:
    if isinstance(ctx, dict):
        return ctx.get(key, default)
    v = getattr(ctx, key, default)
    return v.value if hasattr(v, "value") else v


def risk_signal(ctx: Any) -> bool:
    score = _get(ctx, "client_fraud_score")
    return bool(_get(ctx, "hold_signal")) or (_get(ctx, "prior_disputes_12m") or 0) >= RISK_PRIOR_DISPUTES or (
        score is not None and score >= RISK_SCORE_THRESHOLD)


def expected_outcome(ctx: Any) -> dict:
    """{rambursare_t1, requires_human, recovery, chargeback_reason, t1_deadline} pentru un RuleContext."""
    channel = _get(ctx, "channel")
    dispute_type = _get(ctx, "dispute_type")
    amount = _get(ctx, "amount")
    amount = amount["value"] if isinstance(amount, dict) else getattr(amount, "value", amount)
    executed = parse_ts(_get(ctx, "executed_at"))
    notified = parse_ts(_get(ctx, "notified_at"))
    deadline = end_of_next_business_day(notified).isoformat()

    def out(verdict: str, human: bool, recovery: str | None, reason: str | None, t1: str | None) -> dict:
        return {"rambursare_t1": verdict, "requires_human": human, "recovery": recovery,
                "chargeback_reason": reason, "t1_deadline": t1}

    if dispute_type == "app":
        return out("NU_SE_APLICA_T1", True, "RECHEMARE", None, None)
    if dispute_type == "eroare_procesare":
        return out("NU_SE_APLICA_T1", False, "CHARGEBACK", "12.6.1", None)
    if dispute_type == "disputa_comerciant":
        return out("NU_SE_APLICA_T1", False, "CHARGEBACK", "13.1", None)
    # neautorizată
    if not within_13_months(executed, notified):
        return out("RESPINGE_TARDIV", True, None, None, None)
    if _get(ctx, "hold_signal") and _get(ctx, "hold_authority_notified"):
        return out("EXCEPTIE_FRAUDA_CLIENT", True, None, None, deadline)
    if risk_signal(ctx):
        return out("RAMBURSEAZA_CU_APROBARE", True, None, None, deadline)
    money = _get(ctx, "amount")
    currency = (money.get("currency") if isinstance(money, dict) else getattr(money, "currency", "RON")) or "RON"
    amount_ron = float(amount) * (EUR_RON if currency == "EUR" else 1.0)
    verdict = "RAMBURSEAZA" if amount_ron <= CAP_RON else "RAMBURSEAZA_CU_APROBARE"
    if channel in ("transfer", "transfer_instant"):
        recovery, reason = "RECHEMARE", None
    elif _get(ctx, "eci") == "05" and _get(ctx, "cavv_present"):
        # chargeback imposibil; recuperarea de la client se propune omului doar cu indicii de neglijență gravă
        gross = _get(ctx, "screen_showed_amount_and_payee") is True and (
            _get(ctx, "client_admits_approving_in_app") is True or _get(ctx, "client_admits_sharing_credentials") is True)
        recovery, reason = ("RECUPERARE_PROPUSA" if gross else "NU_RECOMANDAM_RECUPERARE"), None
    else:
        recovery, reason = "CHARGEBACK", "10.4"
    return out(verdict, verdict != "RAMBURSEAZA", recovery, reason, deadline)


def t1_deadline(notified_at: datetime | str) -> str:
    return end_of_next_business_day(parse_ts(notified_at)).isoformat()
