"""Pachetul AML: Legea 129/2019 art. 6–8 (docs/context/11 §2.2). Rulează doar în zona AML (`evaluate_aml`).

Ceasurile în ore care cad într-o zi nelucrătoare se mută la aceeași oră din următoarea zi lucrătoare
(AML-05). Ancora suspendării ONPCSB e momentul comunicat de Oficiu (de verificat în textul art. 8); când
lipsește, ceasurile sunt estimate de la sfârșitul celor 24 de ore și sunt marcate „estimat”.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from versoml.contracts import Confidence, Deadline, Question, Zone

from ..calendar_ro import BusinessCalendar, add_business_days, end_of_day, roll_same_hour, to_local
from ..context import AmlRuleContext
from ..facts import Env, fmt_dt, fmt_money, to_eur
from ..registry import Finding, rule
from .urm import str_indicators

P = Confidence.P
SRC = "docs/context/11 §2.2"
Q_RTS, Q_LEAD = Question.RTS, Question.PISTA_AML
HOLD_HOURS = 24                  # art. 8 alin. (3) [P]
SUSPENSION_MAX_HOURS = 48        # art. 8 alin. (4) [P]
EXTENSION_MAX_HOURS = 72         # art. 8 alin. (6) [P]
CORRECTION_BUSINESS_DAYS = 2     # art. 8 alin. (13) [P]
THRESHOLD_EUR = 10_000.0         # art. 7 alin. (1)–(3) [P]
REMITTANCE_EUR = 2_000.0         # art. 7 alin. (5) [P]
REPORT_BUSINESS_DAYS = 3         # art. 7 alin. (7) [P]


def str_grounds(a: AmlRuleContext, env: Env) -> bool:
    """Există temei pentru STR: suspiciunea confirmată de analist, o cerere ONPCSB sau indicii obiective."""
    return a.suspicion_confirmed or a.onpcsb_request or bool(str_indicators(a, env))


@rule("AML-05", title="Termenele în ore care cad în zile nelucrătoare se mută la aceeași oră",
      basis="Legea 129/2019 art. 8 alin. (10)", confidence=P, pack="AML", source=SRC, zone=Zone.AML,
      kind="calculator", tests=("TC-14", "TC-15"))
def hours_deadline(start: datetime, hours: int, cal: BusinessCalendar | None = None) -> datetime:
    """`start` + `hours`, mutat la aceeași oră din prima zi lucrătoare dacă pică într-o zi nelucrătoare."""
    return roll_same_hour(to_local(start) + timedelta(hours=hours), cal)


def str_hold_until(registered_at: datetime, cal: BusinessCalendar | None = None) -> datetime:
    """Art. 8 alin. (3) + (10): tranzacția nu se execută 24 de ore de la înregistrarea STR."""
    return hours_deadline(registered_at, HOLD_HOURS, cal)


def onpcsb_window_end(start: datetime, hours: int, max_hours: int, cal: BusinessCalendar | None = None) -> datetime:
    """Suspendare (≤48h) sau prelungire unică (≤72h); peste maxim → `ValueError` (AML_INVALID_DURATION)."""
    if not 0 < hours <= max_hours:
        raise ValueError(f"{hours}h depășește maximul legal de {max_hours}h")
    return hours_deadline(start, hours, cal)


def str_correction_deadline(returned_at: datetime, cal: BusinessCalendar | None = None) -> datetime:
    """Art. 8 alin. (13)–(14): STR-ul returnat se corectează în 2 zile lucrătoare."""
    return end_of_day(add_business_days(to_local(returned_at).date(), CORRECTION_BUSINESS_DAYS, cal))


def threshold_report_deadline(tx_at: datetime, cal: BusinessCalendar | None = None) -> datetime:
    """Art. 7 alin. (7): rapoartele de prag în cel mult 3 zile lucrătoare de la tranzacție."""
    return end_of_day(add_business_days(to_local(tx_at).date(), REPORT_BUSINESS_DAYS, cal))


@rule("AML-01", title="STR la ONPCSB când există motive rezonabile de suspiciune", basis="Legea 129/2019 art. 6 "
      "alin. (1) și (3)", confidence=P, pack="AML", source=SRC, zone=Zone.AML, questions=(Q_RTS,),
      exceptions=("AML_STR_REQUIRED",), tests=("TC-14",))
def aml_01_str_required(a: AmlRuleContext, env: Env) -> Finding | None:
    """STR-ul se depune exclusiv la ONPCSB când entitatea știe, suspectează sau are motive rezonabile să
    suspecteze, ori când ONPCSB cere tratarea unei tranzacții ca suspectă. Agentul pregătește ciorna și
    dosarul; trimiterea o decide responsabilul AML."""
    if not (a.suspicion_confirmed or a.onpcsb_request):
        return None
    why = "analistul are motive rezonabile de suspiciune" if a.suspicion_confirmed else \
        "ONPCSB a cerut tratarea tranzacției ca suspectă"
    return Finding("AML-01", "AML_STR_REQUIRED",
                   f"STR-ul se depune exclusiv la ONPCSB: {why}. Agentul pregătește ciorna și dosarul de probe; "
                   "trimiterea o decide responsabilul AML (art. 6).", ("suspicion_confirmed", "onpcsb_request"))


@rule("AML-02", title="STR „de îndată” și înainte de executarea tranzacției legate", basis="Legea 129/2019 art. 8 "
      "alin. (1)–(2)", confidence=P, pack="AML", source=SRC, zone=Zone.AML, questions=(Q_RTS,),
      exceptions=("AML_TX_HOLD",), tests=("TC-14",))
def aml_02_before_execution(a: AmlRuleContext, env: Env) -> Finding | None:
    """Tranzacția legată de suspiciune intră în așteptare la crearea ciornei de STR și nu se execută înainte ca
    STR-ul să fie trimis (ONPCSB confirmă prin număr de înregistrare)."""
    if a.transaction_executed or not str_grounds(a, env):
        return None
    return Finding("AML-02", "AML_TX_HOLD",
                   "Tranzacția legată nu s-a executat: rămâne în așteptare, iar STR-ul se trimite de îndată, înainte "
                   "de executare (art. 8 alin. (1)–(2)).", ("transaction_executed",))


@rule("AML-03", title="Tranzacția nu se execută 24 de ore de la înregistrarea STR", basis="Legea 129/2019 art. 8 "
      "alin. (3) și (10)", confidence=P, pack="AML", source=SRC, zone=Zone.AML, questions=(Q_RTS,),
      params=("bank_closure_days",), exceptions=("AML_TX_HOLD",), tests=("TC-14",))
def aml_03_hold_24h(a: AmlRuleContext, env: Env) -> Finding | None:
    """După înregistrarea STR, tranzacția nu se execută 24 de ore; apoi se poate executa dacă ONPCSB nu a
    dispus suspendarea. Termenul care pică într-o zi nelucrătoare se mută (AML-05)."""
    if a.str_registered_at is not None:
        until = str_hold_until(a.str_registered_at, env.cal)
        return Finding("AML-03", "AML_TX_HOLD",
                       f"STR înregistrat la {fmt_dt(a.str_registered_at)}: tranzacția legată nu se execută până la "
                       f"{fmt_dt(until)} (24 de ore, mutate la prima zi lucrătoare).", ("str_registered_at",),
                       data={"until": until},
                       deadlines=(Deadline(rule_id="AML-03", name="Tranzacția legată nu se execută (24h de la STR)",
                                           due_at=until, basis="Legea 129/2019 art. 8 alin. (3), (10)",
                                           business_days=False),))
    if a.transaction_executed or not str_grounds(a, env):
        return None
    until = str_hold_until(a.now, env.cal)
    return Finding("AML-03", "AML_TX_HOLD",
                   f"Dacă STR-ul se înregistrează acum, tranzacția legată nu se execută până la {fmt_dt(until)} "
                   "(estimat).", ("transaction_executed",), data={"until": until, "estimated": True},
                   deadlines=(Deadline(rule_id="AML-03", name="Tranzacția legată nu se execută (24h de la STR, estimat)",
                                       due_at=until, basis="Legea 129/2019 art. 8 alin. (3), (10)",
                                       business_days=False),))


@rule("AML-04", title="Suspendare ONPCSB de cel mult 48h; o singură prelungire de cel mult 72h",
      basis="Legea 129/2019 art. 8 alin. (4), (6), (9)", confidence=P, pack="AML", source=SRC, zone=Zone.AML,
      questions=(Q_RTS,), exceptions=("AML_SUSPENSION_ACTIVE", "AML_INVALID_DURATION"), tests=("TC-15", "EX-12"))
def aml_04_suspension(a: AmlRuleContext, env: Env) -> Finding | None:
    """ONPCSB poate suspenda cel mult 48 de ore și poate cere, o singură dată, prelungirea cu cel mult 72 de ore.
    Dacă prelungirea nu e comunicată până la expirare, tranzacția se poate executa. O durată peste maxim sau o a
    doua prelungire merg la Compliance: motorul nu inventează un termen."""
    deadlines: list[Deadline] = []
    errors: list[str] = []
    basis = "Legea 129/2019 art. 8 alin. (4), (6), (10)"
    if a.extensions_requested > 1:
        errors.append(f"{a.extensions_requested} prelungiri cerute (legea permite una)")
    if a.suspension_start is not None and a.suspension_hours is not None:
        try:
            end = onpcsb_window_end(a.suspension_start, a.suspension_hours, SUSPENSION_MAX_HOURS, env.cal)
            deadlines.append(Deadline(rule_id="AML-04", name=f"Suspendare ONPCSB ({a.suspension_hours}h)", due_at=end,
                                      basis=basis, business_days=False))
        except ValueError:
            errors.append(f"suspendare de {a.suspension_hours}h (maximul legal: 48h)")
    if a.extension_start is not None and a.extension_hours is not None:
        try:
            end = onpcsb_window_end(a.extension_start, a.extension_hours, EXTENSION_MAX_HOURS, env.cal)
            deadlines.append(Deadline(rule_id="AML-04", name=f"Prelungire ONPCSB ({a.extension_hours}h)", due_at=end,
                                      basis=basis, business_days=False))
        except ValueError:
            errors.append(f"prelungire de {a.extension_hours}h (maximul legal: 72h)")
    fields = ("suspension_hours", "extension_hours", "extensions_requested")
    if errors:
        return Finding("AML-04", "AML_INVALID_DURATION",
                       "Durată ONPCSB invalidă: " + "; ".join(errors) + ". Cazul merge la Compliance; motorul nu "
                       "inventează un termen.", fields, deadlines=tuple(deadlines))
    if deadlines:
        last = max(d.due_at for d in deadlines)
        return Finding("AML-04", "AML_SUSPENSION_ACTIVE",
                       f"Tranzacția rămâne suspendată până la {fmt_dt(last)}.", fields, data={"until": last},
                       deadlines=tuple(deadlines))
    if a.transaction_executed or not str_grounds(a, env) or a.str_registered_at is not None:
        return None
    hold_end = str_hold_until(a.now, env.cal)
    susp_end = hours_deadline(hold_end, SUSPENSION_MAX_HOURS, env.cal)
    ext_end = hours_deadline(susp_end, EXTENSION_MAX_HOURS, env.cal)
    return Finding("AML-04", "ceasuri_estimate",
                   f"Dacă ONPCSB suspendă după cele 24 de ore: cel mult până la {fmt_dt(susp_end)}; cu prelungirea "
                   f"unică de 72h, cel mult până la {fmt_dt(ext_end)} (estimat; ancora se verifică în art. 8).",
                   ("transaction_executed",),
                   deadlines=(Deadline(rule_id="AML-04", name="Suspendare ONPCSB de cel mult 48h (estimat)",
                                       due_at=susp_end, basis=basis, business_days=False),
                              Deadline(rule_id="AML-04", name="Prelungire ONPCSB de cel mult 72h (estimat)",
                                       due_at=ext_end, basis=basis, business_days=False)))


@rule("AML-06", title="STR returnat: corectare în 2 zile lucrătoare; cele 24h repornesc",
      basis="Legea 129/2019 art. 8 alin. (12)–(14)", confidence=P, pack="AML", source=SRC, zone=Zone.AML,
      questions=(Q_RTS,), exceptions=("AML_STR_RETURNED",), tests=("TC-16",))
def aml_06_returned(a: AmlRuleContext, env: Env) -> Finding | None:
    """Raportul neconform se returnează și se corectează în 2 zile lucrătoare; cele 24 de ore repornesc la
    confirmarea STR-ului corectat, iar tranzacția rămâne neexecutată."""
    if a.str_returned_at is None:
        return None
    due = str_correction_deadline(a.str_returned_at, env.cal)
    deadlines = [Deadline(rule_id="AML-06", name="Corectarea STR-ului returnat (2 zile lucrătoare)", due_at=due,
                          basis="Legea 129/2019 art. 8 alin. (13)", business_days=True)]
    text = f"STR-ul a fost returnat la {fmt_dt(a.str_returned_at)}: se corectează până la {fmt_dt(due)}."
    data: dict = {"correction_due": due}
    if a.str_corrected_registered_at is not None:
        until = str_hold_until(a.str_corrected_registered_at, env.cal)
        text += f" STR-ul corectat a fost confirmat: cele 24 de ore repornesc, până la {fmt_dt(until)}."
        data["until"] = until
        deadlines.append(Deadline(rule_id="AML-06", name="Tranzacția legată nu se execută (24h de la STR-ul corectat)",
                                  due_at=until, basis="Legea 129/2019 art. 8 alin. (14)", business_days=False))
    return Finding("AML-06", "AML_STR_RETURNED", text, ("str_returned_at", "str_corrected_registered_at"),
                   data=data, deadlines=tuple(deadlines))


def threshold_reports(a: AmlRuleContext, env: Env) -> list[tuple[str, str]]:
    """(cod, explicație) pentru rapoartele de prag datorate (art. 7)."""
    rate = env.p("eur_ron_rate")
    out: list[tuple[str, str]] = []
    if a.cash_linked is not None and (eur := to_eur(a.cash_linked, rate)) is not None and eur >= THRESHOLD_EUR:
        out.append(("AML_RTN_DUE", f"numerar de {fmt_money(a.cash_linked.value, a.cash_linked.currency)} "
                                   f"(≈ {fmt_money(eur, 'EUR')}), peste pragul de 10.000 EUR"))
    if (a.external_transfers_linked is not None
            and (eur := to_eur(a.external_transfers_linked, rate)) is not None and eur >= THRESHOLD_EUR):
        out.append(("AML_RTE_DUE", f"transferuri externe de {fmt_money(a.external_transfers_linked.value, a.external_transfers_linked.currency)}, "
                                   "peste pragul de 10.000 EUR"))
    if a.remittances_linked is not None and (eur := to_eur(a.remittances_linked, rate)) is not None \
            and eur >= REMITTANCE_EUR:
        out.append(("AML_RTE_DUE", f"remiteri de bani de {fmt_money(a.remittances_linked.value, a.remittances_linked.currency)}, "
                                   "peste pragul de 2.000 EUR"))
    return out


@rule("AML-07", title="RTN: numerar de cel puțin 10.000 EUR, inclusiv operațiuni legate",
      basis="Legea 129/2019 art. 7 alin. (1)–(2)", confidence=P, pack="AML", source=SRC, zone=Zone.AML,
      questions=(Q_LEAD,), params=("eur_ron_rate",), exceptions=("AML_RTN_DUE",), tests=("TC-13",))
def aml_07_cash_report(a: AmlRuleContext, env: Env) -> Finding | None:
    """Tranzacțiile în numerar, în lei sau valută, de cel puțin echivalentul a 10.000 EUR (inclusiv operațiuni
    legate) se raportează. Cursul și fereastra „operațiunilor legate” sunt parametri [U]."""
    rows = [t for c, t in threshold_reports(a, env) if c == "AML_RTN_DUE"]
    if not rows:
        return None
    return Finding("AML-07", "AML_RTN_DUE", f"Raport de numerar (RTN) datorat: {rows[0]}.", ("cash_linked",))


@rule("AML-08", title="RTE: transferuri externe de cel puțin 10.000 EUR; remiteri de cel puțin 2.000 EUR",
      basis="Legea 129/2019 art. 7 alin. (3) și (5)", confidence=P, pack="AML", source=SRC, zone=Zone.AML,
      questions=(Q_LEAD,), params=("eur_ron_rate",), exceptions=("AML_RTE_DUE",), tests=("TC-13",))
def aml_08_external_report(a: AmlRuleContext, env: Env) -> Finding | None:
    """Transferurile externe în și din conturi de cel puțin 10.000 EUR și remiterile de cel puțin 2.000 EUR
    (inclusiv operațiuni legate) se raportează."""
    rows = [t for c, t in threshold_reports(a, env) if c == "AML_RTE_DUE"]
    if not rows:
        return None
    return Finding("AML-08", "AML_RTE_DUE", "Raport de transferuri externe (RTE) datorat: " + "; ".join(rows) + ".",
                   ("external_transfers_linked", "remittances_linked"))


@rule("AML-09", title="Rapoartele de prag în cel mult 3 zile lucrătoare", basis="Legea 129/2019 art. 7 alin. (7)",
      confidence=P, pack="AML", source=SRC, zone=Zone.AML, questions=(Q_LEAD,), params=("bank_closure_days",),
      exceptions=("AML_REPORT_OVERDUE",), tests=("TC-13",))
def aml_09_report_deadline(a: AmlRuleContext, env: Env) -> Finding | None:
    """Rapoartele de prag se trimit în cel mult 3 zile lucrătoare de la tranzacție, pe formularele ONPCSB."""
    if not threshold_reports(a, env) or a.threshold_tx_at is None:
        return None
    due = threshold_report_deadline(a.threshold_tx_at, env.cal)
    overdue = to_local(a.now) > due
    return Finding("AML-09", "AML_REPORT_OVERDUE" if overdue else "termen_raport",
                   f"Raportul de prag se trimite până la {fmt_dt(due)} (3 zile lucrătoare de la tranzacție)"
                   + (": termenul a trecut." if overdue else "."), ("threshold_tx_at",), data={"due": due},
                   deadlines=(Deadline(rule_id="AML-09", name="Raport de prag la ONPCSB (3 zile lucrătoare)", due_at=due,
                                       basis="Legea 129/2019 art. 7 alin. (7)", business_days=True),))


__all__ = ["hours_deadline", "onpcsb_window_end", "str_correction_deadline", "str_grounds", "str_hold_until",
           "threshold_report_deadline", "threshold_reports"]
