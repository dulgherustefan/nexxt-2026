"""Motorul de reguli VersoML (docs/06 §4.4): reguli cu ID, calendarul RO, ceasurile legale și parametrii [U].

Principiul: LLM-ul extrage și redactează; regulile decid. Fiecare decizie are ID-urile regulilor, temeiul,
marcajul de încredere și citări spre fact_id-urile din registrul de probe.
"""

from .calendar_ro import add_banking_days, add_business_days, end_of_next_business_day, is_business_day
from .context import AmlRuleContext, AmlRulesOutcome, GuardResult, RuleContextExt
from .engine import ENGINE_VERSION, catalog, evaluate, evaluate_aml, explain, get_params, set_params
from .packs.cmp import check_adr_block, check_complaint_letter, check_points_answered
from .packs.dsp import Ce3Txn, ce3_check, chargeback_recoverable, validate_reversal
from .packs.pay import validate_refund_refusal
from .params import ParamsError, param_specs, reset_params

__all__ = [
    "ENGINE_VERSION", "AmlRuleContext", "AmlRulesOutcome", "Ce3Txn", "GuardResult", "ParamsError",
    "RuleContextExt", "add_banking_days", "add_business_days", "catalog", "ce3_check", "chargeback_recoverable",
    "check_adr_block", "check_complaint_letter", "check_points_answered", "end_of_next_business_day", "evaluate",
    "evaluate_aml", "explain", "get_params", "is_business_day", "param_specs", "reset_params", "set_params",
    "validate_refund_refusal", "validate_reversal",
]
