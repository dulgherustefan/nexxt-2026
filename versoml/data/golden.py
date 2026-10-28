"""Setul de aur: `golden/golden_40.jsonl` (40 de cazuri alese de mână) și `golden/generated_300.jsonl`.

Fiecare linie: {"id", "scenario", "complaint", "rule_context", "expected", ...} unde
- `complaint` = `contracts.Complaint` (JSON), `rule_context` = câmpurile `contracts.RuleContext` (JSON);
- `expected` = {"rambursare_t1", "requires_human", "recovery", "chargeback_reason", "t1_deadline",
  "injection_suspected"}, calculat cu `oracle.expected_outcome` după tabelul comun cu motorul de reguli.
Câmpuri în plus: `underlying_scenario` (la injecții și la reclamațiile tardive), `tags`, `notes`, `source`,
`materialized` (cazul are înregistrări în var/client_zone.db după seed).

Convenții pe care se bazează așteptările (cazurile stau departe de praguri, în afară de cele etichetate):
- plafonul de rambursare automată: 5.000 RON inclusiv (`cap_edge` la 5.000,00 și 5.000,01);
- semnal de risc: >= 3 contestații în 12 luni sau scor M2 >= 0,7 sau HoldSignal; cazurile fără semnal au
  cel mult 2 contestații și scor <= 0,25; `client_fraud_score` e o valoare sintetică reprezentativă pentru M2;
- termenul T+1: 23:59:59 ora României, în următoarea zi lucrătoare după data locală a notificării;
- 13 luni: comparație pe date locale, inclusiv (art. 169, `add_months`).

Rulare: `python -m versoml.data.golden` regenerează fișierele (determinist).
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.aml_world import inel_mule
from versoml.data.calendar_ro import TZ, add_months
from versoml.data.complaints import INJECTIONS, INJECTION_UNDERLYING, random_style
from versoml.data.oracle import expected_outcome
from versoml.data.scenarios import (SCENARIOS, CaseParams, ScenarioBundle, _b, _mule_beneficiary,
                                 build_case, build_scenario)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_40 = GOLDEN_DIR / "golden_40.jsonl"
GENERATED_300 = GOLDEN_DIR / "generated_300.jsonl"


def _variants(seed: int = 7) -> list[tuple[CaseParams, tuple[str, ...], str]]:
    im = inel_mule(seed)
    P = CaseParams
    V = []

    def v(key, builder, scenario, amount, ex, nt, tags, notes, **kw):
        n = int(key[2:])
        V.append((P(key, builder, scenario, f"CT-2026-91{n:04d}", f"CUST-GL-{n:02d}", f"Client 91{n:02d}", amount,
                    ex if isinstance(ex, datetime) else _b(ex), nt if isinstance(nt, datetime) else _b(nt), **kw),
                  tags, notes))

    scam = f"https://{art.SCAM_DOMAIN_DEMO}/colet/RO"
    v("GL01", "phishing_link", "phishing_link", 6400.00, "2026-10-22T21:31:00", "2026-10-23T09:12:00",
      ("peste_plafon", "weekend", "schimbare_ora"), "Peste plafon: rambursare cu aprobare; termenul trece peste weekend și peste trecerea la ora de iarnă.",
      domain=art.SCAM_DOMAIN_DEMO, url=scam + "5521", click_seconds=140)
    v("GL02", "phishing_link", "phishing_link", 5000.00, "2026-04-09T10:05:00", "2026-04-09T12:40:00",
      ("cap_edge", "paste_ortodox", "neglijenta_grava"), "Fix 5.000 lei (plafon inclusiv); Paștele ortodox 2026; clientul recunoaște că a dat codul: C-70/25, rambursare oricum.",
      domain=art.SCAM_DOMAIN_DEMO, url=scam + "7710", click_seconds=96, admits_sharing=True)
    v("GL03", "card_ecom_fara_3ds", "card_ecom_fara_3ds", 5000.01, "2026-10-24T23:40:00", "2026-10-25T10:00:00",
      ("cap_edge", "weekend"), "5.000,01 lei: peste plafon; notificare duminică, termen luni.", merchant="GADGETWORLD SHOP (sintetic)")
    v("GL04", "card_ecom_fara_3ds", "card_ecom_fara_3ds", 640.00, "2025-12-23T22:10:00", "2025-12-24T09:00:00",
      ("craciun",), "Crăciun 2025: 25–26 decembrie nelucrătoare, termen luni 29.12.", merchant="GlobalApps Store (sintetic)")
    v("GL05", "card_visa_secure", "card_visa_secure", 3999.00, "2026-05-28T20:00:00", "2026-05-29T08:30:00",
      ("rusalii",), "Rusalii 2026 (1 iunie nelucrătoare): termen marți 2.06.", domain=art.SCAM_DOMAIN_CARD,
      url=f"https://{art.SCAM_DOMAIN_CARD}/verificare", click_seconds=280)
    v("GL06", "card_visa_secure", "card_visa_secure", 4980.00, "2026-10-26T21:05:00", "2026-10-27T10:05:00",
      ("aproape_de_plafon", "neglijenta_grava"), "Clientul a aprobat în aplicație (ECI 05 + CAVV): chargeback imposibil, recuperare propusă omului.",
      domain=art.SCAM_DOMAIN_CARD, url=f"https://{art.SCAM_DOMAIN_CARD}/card", click_seconds=190, admits_approving=True)
    v("GL07", "vishing_securitate", "vishing_securitate", 2300.00, "2026-10-27T09:40:00", "2026-10-27T10:05:00",
      ("app",), "Vishing (DT-03): clientul a aprobat; nu intră la T+1, decide omul.", phone=art.SCAM_PHONE_SECURITATE,
      admits_approving=True)
    v("GL08", "vishing_securitate", "vishing_securitate", 9800.00, "2026-10-24T10:15:00", "2026-10-24T13:00:00",
      ("app", "weekend"), "Sumă mare, sâmbătă: traseu APP, rechemare.", phone=art.SCAM_PHONE_SECURITATE, admits_approving=True,
      domain=art.SCAM_DOMAIN_VISHING, url=f"https://{art.SCAM_DOMAIN_VISHING}/cont")
    v("GL09", "cont_sigur", "cont_sigur", 7300.00, "2026-10-24T18:20:00", "2026-10-24T21:00:00",
      ("app", "weekend"), "Cont sigur, sâmbătă seara.", phone=art.SCAM_PHONE_CONT_SIGUR, admits_approving=True, segment="pensionar",
      target_balance=1500.00)
    v("GL10", "cont_sigur", "cont_sigur", 22000.00, "2026-10-21T11:02:00", "2026-10-21T16:45:00",
      ("app",), "Toate economiile mutate instant.", phone=art.SCAM_PHONE_CONT_SIGUR, admits_approving=True, target_balance=800.00)
    v("GL11", "sim_swap", "sim_swap", 8900.00, "2025-11-28T06:40:00", "2025-11-28T10:00:00",
      ("peste_plafon", "1_decembrie"), "30 noiembrie (duminică) și 1 decembrie (luni) nelucrătoare: termen marți 2.12.2025.",
      sim_swap_hours=0.9)
    v("GL12", "sim_swap", "sim_swap", 1450.00, "2026-04-30T16:00:00", "2026-04-30T19:00:00",
      ("1_mai", "sim_2h"), "SIM schimbat exact cu 2 ore înainte; 1 mai (vineri) nelucrătoare: termen luni 4.05.", sim_swap_hours=2.0)
    v("GL13", "frauda_client", "frauda_client", 1940.00, "2025-12-12T19:10:00", "2025-12-31T11:00:00",
      ("hold_signal", "anul_nou"), "HoldSignal aprobat și autoritatea notificată: singura excepție (EXCEPTIE_FRAUDA_CLIENT); 1–2 ian. nelucrătoare.",
      prior_disputes=5, client_fraud_score=0.94, hold_signal=True, hold_authority_notified=True)
    v("GL14", "frauda_client", "frauda_client", 760.00, "2025-12-20T12:00:00", "2026-01-05T09:30:00",
      ("hold_fara_notificare", "boboteaza"), "HoldSignal fără notificarea autorității: rambursare cu aprobare (DX-08); 6–7 ian. nelucrătoare.",
      prior_disputes=3, client_fraud_score=0.88, hold_signal=True, hold_authority_notified=False)
    v("GL15", "phishing_link", "reclamatie_tardiva", 1200.00, "2025-09-15T12:00:00", "2026-10-27T10:00:00",
      ("13_luni",), "DT-05: debit 15.09.2025, notificare 27.10.2026 (limita 15.10.2026).", domain=art.SCAM_DOMAIN_DEMO,
      url=scam + "1001", source="email")
    v("GL16", "card_ecom_fara_3ds", "reclamatie_tardiva", 455.00, "2025-09-25T09:00:00", "2026-10-26T09:00:00",
      ("13_luni", "limita"), "13 luni și o zi: tardiv.", merchant="GADGETWORLD SHOP (sintetic)")
    v("GL17", "plata_dubla", "plata_dubla", 287.40, "2026-10-23T18:02:00", "2026-10-24T09:00:00",
      ("weekend",), "Plată dublă la benzinărie, notificare sâmbătă.", merchant="Benzinăria Demo A1")
    v("GL18", "plata_dubla", "plata_dubla", 96.15, "2025-12-23T17:30:00", "2025-12-25T10:00:00",
      ("craciun",), "Plată dublă, notificare de Crăciun (fără termen T+1).", merchant="Farmacia Exemplu")
    v("GL19", "inel_carausi", "inel_carausi", 3450.00, "2026-10-23T10:31:00", "2026-10-26T09:10:00",
      ("inel",), "A doua victimă a inelului: același IBAN intern.", beneficiary=_mule_beneficiary(im),
      domain=art.SCAM_DOMAIN_INEL, url=f"https://{art.SCAM_DOMAIN_INEL}/confirmare/88214", click_seconds=171)
    v("GL20", "inel_carausi", "inel_carausi", 5600.00, "2026-10-25T19:48:00", "2026-10-26T13:00:00",
      ("inel", "peste_plafon"), "A treia victimă, peste plafon.", beneficiary=_mule_beneficiary(im),
      domain=art.SCAM_DOMAIN_INEL, url=f"https://{art.SCAM_DOMAIN_INEL}/confirmare/88215", click_seconds=203)
    v("GL21", "card_ecom_fara_3ds", "injectie_document", 320.00, "2026-10-26T01:12:00", "2026-10-26T09:40:00",
      ("injectie", "suma_ceruta_9999"), "DT-18(c): textul cere 9.999 lei; suma vine din jurnal (320 lei).",
      merchant="GlobalApps Store (sintetic)", injection=INJECTIONS[1], injection_place="text")
    v("GL22", "vishing_securitate", "injectie_document", 3100.00, "2026-10-26T12:10:00", "2026-10-26T15:30:00",
      ("injectie", "app"), "Injecție într-un caz APP: rezultatul rămâne NU_SE_APLICA_T1, cu om.",
      phone=art.SCAM_PHONE_SECURITATE, admits_approving=True, injection=INJECTIONS[2], injection_place="attachment")
    v("GL23", "marfa_nelivrata", "marfa_nelivrata", 640.00, "2026-09-28T20:10:00", "2026-10-20T10:00:00",
      ("comerciant",), "Haine comandate, nelivrate.", merchant="Moda Demo Store")
    v("GL24", "marfa_nelivrata", "marfa_nelivrata", 2350.00, "2026-09-15T10:00:00", "2026-10-19T11:00:00",
      ("comerciant",), "Pachet turistic neprestat.", merchant="Agenția Demo Travel")
    v("GL25", "phishing_link", "phishing_link", 1720.00, datetime(2026, 10, 27, 22, 10, tzinfo=timezone.utc),
      datetime(2026, 10, 27, 22, 30, tzinfo=timezone.utc), ("fus_orar",),
      "Notificare la 22:30 UTC = 00:30 ora României, pe 28.10: termenul e joi 29.10, nu miercuri.",
      domain=art.SCAM_DOMAIN_DEMO, url=scam + "3003", click_seconds=111)
    v("GL26", "phishing_link", "phishing_link", 2750.00, "2025-09-27T15:00:00", "2026-10-27T09:00:00",
      ("13_luni", "limita_inclusiva"), "Notificare exact la 13 luni (27.09.2025 -> 27.10.2026): încă în termen (art. 169, inclusiv).",
      domain=art.SCAM_DOMAIN_DEMO, url=scam + "2707", click_seconds=133)
    return V


def _line(gid: str, scenario_label: str, b: ScenarioBundle, *, tags: tuple[str, ...], notes: str, source: str,
          materialized: bool, underlying: str | None, notified_utc: bool = False) -> dict:
    rc = dict(b.rule_context_hints)
    complaint = b.complaint.model_dump(mode="json")
    if notified_utc:
        utc = datetime.fromisoformat(rc["notified_at"]).astimezone(timezone.utc).isoformat()
        rc["notified_at"] = utc
        complaint["received_at"] = utc
    expected = {k: b.expected[k] for k in ("rambursare_t1", "requires_human", "recovery", "chargeback_reason", "t1_deadline")}
    assert expected == {k: expected_outcome(rc)[k] for k in expected}, gid
    expected["injection_suspected"] = bool(b.expected.get("injection_suspected"))
    line = {"id": gid, "scenario": scenario_label, "complaint": complaint, "rule_context": rc, "expected": expected,
            "underlying_scenario": underlying, "tags": list(tags), "notes": notes, "source": source,
            "materialized": materialized, "synthetic": True}
    return line


def golden_40(seed: int = 7) -> list[dict]:
    lines: list[dict] = []
    k = 0
    for sid, spec in SCENARIOS.items():
        k += 1
        b = build_scenario(sid, seed)
        underlying = {"reclamatie_tardiva": "card_ecom_fara_3ds", "injectie_document": "phishing_link"}.get(sid)
        tags = ("scenariu",) + spec.tags
        lines.append(_line(f"G{k:02d}", sid, b, tags=tags, notes=spec.title, source="curated", materialized=True,
                           underlying=underlying))
    for p, tags, notes in _variants(seed):
        k += 1
        b = build_case(p, seed)
        underlying = p.builder if p.scenario in ("reclamatie_tardiva", "injectie_document") else None
        lines.append(_line(f"G{k:02d}", p.scenario, b, tags=tags, notes=notes, source="curated", materialized=True,
                           underlying=underlying, notified_utc="fus_orar" in tags))
    return lines


def variant_params(seed: int = 7) -> list[CaseParams]:
    """Parametrii variantelor din setul de aur (materializate de seed în zona client)."""
    return [p for p, _, _ in _variants(seed)]


# ---------------------------------------------------------------- 300 de cazuri generate

MAIN = ["phishing_link", "card_ecom_fara_3ds", "card_visa_secure", "vishing_securitate", "cont_sigur", "sim_swap",
        "frauda_client", "reclamatie_tardiva", "plata_dubla", "inel_carausi", "injectie_document", "marfa_nelivrata"]
_MERCH = {"card_ecom_fara_3ds": ["GADGETWORLD SHOP (sintetic)", "GlobalApps Store (sintetic)"],
          "card_visa_secure": ["Exemplu Electro SRL (fictiv)", "ElectroDemo Online (sintetic)", "PiațaDemo Online"],
          "frauda_client": ["ElectroDemo Online (sintetic)", "PiațaDemo Online", "Moda Demo Store", "Agenția Demo Travel"],
          "marfa_nelivrata": ["PiațaDemo Online", "Moda Demo Store", "Agenția Demo Travel", "Librăria Fictivă"],
          "plata_dubla": ["Supermarket Demo Nord", "Mega Exemplu Market", "Benzinăria Demo A1", "Farmacia Exemplu"]}


def _random_params(i: int, scenario: str, rng: random.Random, seed: int) -> CaseParams:
    key = f"GN{i:04d}"
    builder = scenario
    if scenario == "injectie_document":
        builder = rng.choice(INJECTION_UNDERLYING)
    if scenario == "reclamatie_tardiva":
        builder = rng.choice(["card_ecom_fara_3ds", "phishing_link"])
    start, end = _b("2025-10-01T08:00:00"), _b("2026-10-28T09:00:00")
    notified = start + timedelta(seconds=rng.uniform(0, (end - start).total_seconds()))
    notified = notified.replace(hour=rng.choice([0, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 23]),
                                minute=rng.randint(0, 59), second=0, microsecond=0)
    if scenario == "reclamatie_tardiva":
        ex = datetime.combine(add_months(notified.date(), -13) - timedelta(days=rng.randint(2, 200)),
                              datetime.min.time(), tzinfo=TZ).replace(hour=rng.randint(8, 21))
    elif builder in ("frauda_client", "marfa_nelivrata"):
        ex = notified - timedelta(days=rng.uniform(5, 30))
    else:
        ex = notified - timedelta(hours=rng.uniform(0.3, 60))
    ex = ex.replace(microsecond=0)
    amount = {"cont_sigur": lambda: rng.uniform(2000, 30000), "vishing_securitate": lambda: rng.uniform(500, 12000),
              "plata_dubla": lambda: rng.uniform(20, 600), "marfa_nelivrata": lambda: rng.uniform(50, 3000)}.get(
        builder, lambda: rng.uniform(80, 9500) if rng.random() < 0.7 else rng.uniform(5001, 9500))()
    amount = round(amount, 2)
    if builder in ("phishing_link", "card_ecom_fara_3ds", "sim_swap", "inel_carausi") and rng.random() < 0.03:
        amount = 5000.00
    kw: dict = {}
    if builder in ("phishing_link", "inel_carausi"):
        dom = art.SCAM_DOMAIN_INEL if builder == "inel_carausi" else rng.choice([art.SCAM_DOMAIN_DEMO, f"colet-{rng.randint(10, 99)}-livrare.example"])
        kw.update(domain=dom, url=f"https://{dom}/c/{rng.randint(1000, 9999)}", click_seconds=rng.randint(45, 290),
                  admits_sharing=rng.random() < 0.2)
        if builder == "inel_carausi":
            kw["beneficiary"] = _mule_beneficiary(inel_mule(seed))
    if builder == "card_visa_secure":
        kw.update(domain=art.SCAM_DOMAIN_CARD, url=f"https://{art.SCAM_DOMAIN_CARD}/v/{rng.randint(100, 999)}",
                  click_seconds=rng.randint(90, 600), admits_approving=rng.random() < 0.5)
        amount = min(amount, 5000.0)   # tabelul cere RAMBURSEAZA fără plafon explicit: rămânem sub plafon
    if builder == "vishing_securitate":
        kw.update(phone=art.SCAM_PHONE_SECURITATE, admits_approving=True)
    if builder == "cont_sigur":
        kw.update(phone=art.SCAM_PHONE_CONT_SIGUR, admits_approving=True, target_balance=round(rng.uniform(200, 4000), 2))
    if builder == "sim_swap":
        kw.update(sim_swap_hours=round(rng.uniform(0.3, 2.0), 2))
    if builder in _MERCH:
        kw["merchant"] = rng.choice(_MERCH[builder])
    if builder == "frauda_client":
        r = rng.random()
        kw.update(prior_disputes=rng.randint(3, 6), client_fraud_score=round(rng.uniform(0.85, 0.97), 2),
                  hold_signal=r < 0.35, hold_authority_notified=r < 0.25)
    else:
        pr = rng.random()
        kw.update(prior_disputes=0 if pr < 0.85 else 1 if pr < 0.97 else 2,
                  client_fraud_score=round(rng.uniform(0.02, 0.25), 2))
    if scenario == "injectie_document":
        kw.update(injection=rng.choice(INJECTIONS), injection_place=rng.choice(["text", "attachment"]))
    style = random_style(rng)
    style.pop("injection", None)
    kw["style"] = style
    kw["source"] = rng.choice(["app", "app", "email", "web_form", "call_center", "branch"])
    if builder == "cont_sigur" and amount > 20000:
        kw["segment"] = "pensionar"
    return CaseParams(key, builder, scenario, f"CT-2026-92{i:04d}", f"CUST-GN-{i:04d}", f"Client G{i:04d}", amount,
                      ex, notified, **kw)


def generated_300(seed: int = 7, n: int = 300) -> list[dict]:
    rng = ids.sub_rng("generated-300", seed)
    lines = []
    for i in range(1, n + 1):
        scenario = MAIN[(i - 1) % len(MAIN)]
        p = _random_params(i, scenario, rng, seed)
        b = build_case(p, seed)
        underlying = p.builder if p.scenario in ("reclamatie_tardiva", "injectie_document") else None
        lines.append(_line(f"N{i:03d}", scenario, b, tags=(), notes="", source="generated", materialized=False,
                           underlying=underlying))
    return lines


def write_jsonl(lines: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def write_all(seed: int = 7) -> dict:
    g40, g300 = golden_40(seed), generated_300(seed)
    write_jsonl(g40, GOLDEN_40)
    write_jsonl(g300, GENERATED_300)
    return {"golden_40": len(g40), "generated_300": len(g300), "dir": str(GOLDEN_DIR)}


if __name__ == "__main__":
    import time

    t = time.time()
    print(write_all())
    print(f"{time.time() - t:.1f}s")
