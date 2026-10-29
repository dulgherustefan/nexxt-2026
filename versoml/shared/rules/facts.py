"""Funcții pure folosite de reguli: mediul de evaluare, citările, formatarea și faptele derivate.

Nimic de aici nu decide: funcțiile doar calculează (ora locală, ancora T+1, conversii) sau formatează.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from versoml.contracts import Channel, DisputeType, Money, Scenario

from .calendar_ro import BusinessCalendar, add_months, end_of_next_business_day, local_date, to_local
from .context import RuleContextExt

# Câmpurile de clasificare pot fi citate și prin faptul clasificării (cheia „classification” din fact_ids).
_FACT_FALLBACK = {
    "dispute_type": ("classification",),
    "channel": ("classification", "transaction"),
    "scenario": ("classification",),
    "classification_ambiguous": ("classification",),
    "amount": ("transaction",),
    "executed_at": ("transaction",),
}

GN_FIELDS = ("screen_showed_amount_and_payee", "client_admits_approving_in_app", "client_admits_sharing_credentials")
GN_LABELS = {
    "screen_showed_amount_and_payee": "the authentication screen showed the amount and beneficiary",
    "client_admits_approving_in_app": "the customer says they approved the payment in the app",
    "client_admits_sharing_credentials": "the customer says they shared their credentials or OTP code",
    "sca_performed": "strong customer authentication (SCA) succeeded",
}


@dataclass(frozen=True)
class Env:
    """Mediul unei evaluări: parametrii validați, calendarul și ora sfârșitului zilei."""

    params: Mapping[str, Any]
    cal: BusinessCalendar
    eod: time
    flags: Mapping[str, Any]

    def p(self, name: str) -> Any:
        return self.params[name]


def make_env(params: Mapping[str, Any], flags: Mapping[str, Any] | None = None) -> Env:
    closures = frozenset(date.fromisoformat(d) for d in params.get("bank_closure_days") or [])
    eod = time.fromisoformat(params.get("refund_end_of_day") or "23:59:59")
    return Env(params=dict(params), cal=BusinessCalendar(closures=closures), eod=eod, flags=dict(flags or {}))


# ---------------------------------------------------------------- citări


def cite(x: RuleContextExt, fields: Iterable[str]) -> list[str]:
    """fact_id-urile pentru câmpurile folosite; doar valori care există în `ctx.fact_ids`."""
    out: list[str] = []
    for f in fields:
        keys = (f, *_FACT_FALLBACK.get(f, ()))
        fid = next((x.fact_ids[k] for k in keys if x.fact_ids.get(k)), None)
        if fid and fid not in out:
            out.append(fid)
    return out


# ---------------------------------------------------------------- formatare (engleză)

# Lunile scrise explicit: `%b` din strftime depinde de locale-ul procesului.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_d(d: date | datetime) -> str:
    """Data locală, ex. „29 Oct 2026” (ziua fără zero în față)."""
    day = local_date(d)
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def fmt_dt(dt: datetime) -> str:
    """The moment in Romanian time, 24h, e.g. "29 Oct 2026, 23:59"."""
    local = to_local(dt)
    return f"{fmt_d(local)}, {local:%H:%M}"


def fmt_num(value: float, decimals: int = 2) -> str:
    """Virgulă la mii, punct la zecimale, ex. „3,200.00”."""
    return f"{value:,.{decimals}f}"


def fmt_money(value: float, currency: str) -> str:
    """Codul monedei întâi, ex. „RON 3,200.00”."""
    return f"{currency} {fmt_num(value)}"


# ---------------------------------------------------------------- conversii


def to_ron(money: Money, eur_ron_rate: float) -> float | None:
    cur = money.currency.upper()
    if cur == "RON":
        return money.value
    if cur == "EUR":
        return money.value * eur_ron_rate
    return None


def to_eur(money: Money, eur_ron_rate: float) -> float | None:
    cur = money.currency.upper()
    if cur == "EUR":
        return money.value
    if cur == "RON":
        return money.value / eur_ron_rate
    return None


def eur_cap_in(currency: str, eur: float, eur_ron_rate: float) -> float | None:
    """Un plafon în euro, exprimat în moneda tranzacției (doar EUR și RON)."""
    cur = currency.upper()
    if cur == "EUR":
        return eur
    if cur == "RON":
        return round(eur * eur_ron_rate, 2)
    return None


# ---------------------------------------------------------------- fapte derivate


def is_unauthorised(x: RuleContextExt) -> bool:
    return x.dispute_type == DisputeType.NEAUTORIZATA and not x.credit_fraud


def notified_in_time(x: RuleContextExt) -> bool:
    """Art. 169: notificarea în 13 luni sau banca nu a furnizat informațiile (limita nu se aplică)."""
    in_time = local_date(x.notified_at) <= add_months(local_date(x.executed_at), 13)
    return in_time or not x.tx_info_provided


def refund_anchor(x: RuleContextExt, mode: str = "cea_mai_devreme") -> tuple[datetime, str]:
    """DSP-58: T+1 curge de la cea mai devreme dintre constatarea băncii și notificarea clientului."""
    notified = to_local(x.notified_at)
    if mode == "cea_mai_devreme" and x.bank_noted_at is not None and to_local(x.bank_noted_at) < notified:
        return to_local(x.bank_noted_at), "constatare"
    return notified, "notificare"


def refund_due(x: RuleContextExt, env: Env) -> datetime:
    anchor, _ = refund_anchor(x, env.p("refund_anchor_mode"))
    return end_of_next_business_day(anchor, env.cal, env.eod)


def refund_track(x: RuleContextExt) -> bool:
    """Plată neautorizată, notificată în termen: pista A (rambursarea) e deschisă."""
    return is_unauthorised(x) and notified_in_time(x)


def refund_withheld(x: RuleContextExt) -> bool:
    """Singura excepție (art. 173, C-70/25): suspiciune de fraudă a clientului, comunicată autorității."""
    return x.hold_signal and x.hold_authority_notified


def gn_indicator_fields(x: RuleContextExt) -> list[str]:
    fields = [f for f in GN_FIELDS if getattr(x, f) is True]
    if x.sca_performed is True:
        fields.append("sca_performed")
    return fields


def gross_negligence_case(x: RuleContextExt) -> bool:
    """Indiciile de neglijență gravă: ecranul a arătat suma și beneficiarul ȘI clientul a aprobat sau a divulgat."""
    return x.screen_showed_amount_and_payee is True and (
        x.client_admits_approving_in_app is True or x.client_admits_sharing_credentials is True)


def sca_evidence_present(x: RuleContextExt) -> bool:
    """Există jurnalul de autentificare (inclusiv „SCA nu s-a aplicat”) sau ce a afișat ecranul."""
    return x.sca_performed is not None or x.screen_showed_amount_and_payee is not None


CARD_PRESENT_ENTRY = ("chip", "contactless", "magstripe", "atm")


def card_present(x: RuleContextExt) -> bool | None:
    if x.card_present is not None:
        return x.card_present
    if x.pos_entry_mode in CARD_PRESENT_ENTRY:
        return True           # citit la POS sau la ATM
    if x.eci is not None or x.cavv_present is not None or x.pos_entry_mode == "ecommerce":
        return False          # ECI/CAVV există doar la plățile la distanță (e-commerce)
    return None


def card_scheme(x: RuleContextExt, env: Env) -> str:
    return x.card_scheme or env.p("default_card_scheme")


def processing_date(x: RuleContextExt) -> tuple[date, bool]:
    """Data procesării (ancora Visa); lipsă → data executării, mai devreme deci conservatoare."""
    if x.processing_date is not None:
        return x.processing_date, True
    return local_date(x.executed_at), False


def is_card(x: RuleContextExt) -> bool:
    return x.channel == Channel.CARD


def is_direct_debit(x: RuleContextExt) -> bool:
    return x.channel == Channel.DIRECT_DEBIT


# Problema cu comerciantul -> condiția Visa (Core Rules, ch. 11, grupa 13)
MERCHANT_ISSUE_CONDITIONS = {"recurring_cancelled": "13.2", "not_as_described": "13.3",
                             "credit_not_processed": "13.6", "cancelled": "13.7"}


def visa_condition(x: RuleContextExt) -> str | None:
    """Condiția Visa a disputei: cea dată explicit sau cea care decurge din tipul cererii."""
    if x.visa_condition:
        return x.visa_condition.strip()
    if x.dispute_type == DisputeType.NEAUTORIZATA:
        cp = card_present(x)
        if cp is False:
            return "10.4"
        # card prezent la POS: 10.3; 10.1/10.2 cer datele cipului și ale terminalului, pe care le alege un om
        return "10.3" if cp is True and x.pos_entry_mode != "atm" and x.purchase_type != "atm_cash" else None
    if x.dispute_type == DisputeType.EROARE_PROCESARE:
        if x.duplicate_of:
            return "12.6.1"
        if x.purchase_type == "atm_cash":
            return "13.9"
        return None
    if x.dispute_type == DisputeType.DISPUTA_COMERCIANT:
        if x.merchant_issue:
            return MERCHANT_ISSUE_CONDITIONS[x.merchant_issue]
        return "13.1" if x.scenario == Scenario.MARFA_NELIVRATA else None
    return None


def iban_bank_code(iban: str | None) -> str | None:
    if not iban:
        return None
    compact = iban.replace(" ", "").upper()
    if compact.startswith("RO") and len(compact) >= 8:
        return compact[4:8]
    return None


def risk_signals(x: RuleContextExt, env: Env) -> list[tuple[str, tuple[str, ...]]]:
    """Semnalele de risc ale clientului (URM-03): doar trimit cazul la om, nu decid nimic."""
    out: list[tuple[str, tuple[str, ...]]] = []
    thr = env.p("client_fraud_signal_threshold")
    if x.client_fraud_score is not None and x.client_fraud_score >= thr:
        out.append((f"the M2 customer fraud score is {fmt_num(x.client_fraud_score)}, above the threshold of "
                    f"{fmt_num(thr)} (a signal for a human only)", ("client_fraud_score",)))
    n_thr = env.p("prior_disputes_signal_threshold")
    if x.prior_disputes_12m >= n_thr:
        out.append((f"{x.prior_disputes_12m} disputes in the last 12 months (threshold: {n_thr})",
                    ("prior_disputes_12m",)))
    return out
