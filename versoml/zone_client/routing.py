"""The router: which evidence collectors a case needs, and why, in one plain sentence each.

Pure: the router node gathers the inputs (the match, the payment, the merchant, the complaint's links) and this module
decides. Every collector gets an entry, run or skipped, so the console can show the whole plan.
"""

from __future__ import annotations

from typing import Any

COLLECTORS = ["colector_tranzactie", "colector_sca", "colector_dispozitiv", "colector_domeniu", "colector_campanie"]
CARD_PRESENT_KINDS = ("card_pos", "card_atm")


def _card_present(tx: dict) -> bool:
    kind = str(tx.get("kind") or "")
    if kind in CARD_PRESENT_KINDS:
        return True
    return str(tx.get("channel") or "") == "card" and not tx.get("session_id") and kind != "card_ecom" \
        and str(tx.get("pos_entry_mode") or "").lower() not in ("", "ecom", "ecommerce", "e-commerce")


def plan(*, tx: dict | None, customer_ref: str | None, attack_domains: list[str], merchant_domain: str | None,
         indicators: dict[str, list[str]], narrative_chars: int) -> list[dict[str, Any]]:
    """[{node, run, reason}] for the five collectors, in a fixed order."""
    out: list[dict[str, Any]] = []
    tx_id = (tx or {}).get("tx_id") or (tx or {}).get("id")

    def add(node: str, run: bool, reason: str) -> None:
        out.append({"node": node, "run": run, "reason": reason})

    if tx:
        add("colector_tranzactie", True, f"Transaction check runs: payment {tx_id} was found in the ledger")
    elif customer_ref:
        add("colector_tranzactie", True, "Transaction check runs for the customer's dispute history only: no payment "
                                         "was identified")
    else:
        add("colector_tranzactie", False, "Transaction check skipped: neither the customer nor the payment was "
                                          "identified")

    if tx:
        add("colector_sca", True, "SCA check runs: the payment has an authentication log to read")
    else:
        add("colector_sca", False, "SCA check skipped: there is no identified payment to read the log for")

    if not tx:
        add("colector_dispozitiv", False, "Device check skipped: there is no identified payment")
    elif _card_present(tx):
        add("colector_dispozitiv", False, "Device check skipped: a card payment at a shop or ATM has no online session "
                                          "or device to check")
    else:
        add("colector_dispozitiv", True, "Device check runs: the payment was made online, so the device, the session "
                                         "and any SIM swap matter")

    if attack_domains:
        add("colector_domeniu", True, f"Domain check runs: the complaint mentions a link ({attack_domains[0]})")
    elif merchant_domain:
        add("colector_domeniu", True, f"Domain check runs: the card payment went to an online shop ({merchant_domain})")
    else:
        add("colector_domeniu", False, "Domain check skipped: the complaint has no link and the payment has no "
                                       "merchant website")

    kinds = [k for k in ("ibans", "domains", "phones") if indicators.get(k)]
    if kinds:
        names = {"ibans": "the payee account", "domains": "the link", "phones": "the phone number"}
        listed = [names[k] for k in kinds]
        what = listed[0] if len(listed) == 1 else ", ".join(listed[:-1]) + " and " + listed[-1]
        add("colector_campanie", True, f"Campaign check runs: {what} can be compared with other cases")
    elif narrative_chars >= 40:
        add("colector_campanie", True, "Campaign check runs: the complaint's story is compared with other cases")
    else:
        add("colector_campanie", False, "Campaign check skipped: the complaint has nothing to compare with other cases")
    return out
