"""Lumea AML a Băncii Demo: conturi interne (inclusiv cărăuși), contrapartide externe, tipologii de spălare,
alerte de monitorizare și etichetele de adevăr (doar pentru evaluare).

Tipologiile urmează:
- AMLworld (Altman et al., NeurIPS 2023): fan-out, fan-in, ciclu, gather-scatter, scatter-gather, bipartit,
  stivă, aleator;
- SAML-D (Oztas et al., 2023): smurfing (structurare sub praguri), fan-out stratificat, tranzit rapid / retragere
  numerar, schimbare de comportament (cont vechi recrutat);
- PaySim: TRANSFER -> CASH_OUT.
Cărăușii trimit banii spre exchange-ul sintetic („CryptoX Exchange — sintetic") sau îi retrag numerar în câteva ore.

Exemple negative grele (normale, dar care seamănă): mici comercianți cu fan-in, firme cu fan-out salarial,
studenți care primesc bani de la familie și scot numerar, pensionari cu numerar, traderi cripto legitimi.

Fluxurile nu au nume de persoane; conturile persoanelor fizice au doar un pseudonim (`holder_ref`).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.calendar_ro import iso, parse_ts
from versoml.data.world import (HISTORY_DAYS, WORLD_NOW, IdGen, active_device, at, client_tx_to_flows, log_uniform,
                             make_auth, make_customer, make_history, make_session, money, new_fake, person_name,
                             poisson, rand_time, tx_record, weighted_choice)

POPULATIONS = {"student": 90, "pensioner": 50, "freelancer": 40, "micro_merchant": 70, "sme": 25,
               "crypto_trader": 20}
PATTERN_PLAN = [("fan_in", 10), ("fan_out", 5), ("cycle", 4), ("gather_scatter", 3), ("scatter_gather", 3),
                ("bipartite", 3), ("stack", 2), ("random", 3), ("smurfing", 4), ("layered_fan_out", 2),
                ("rapid_pass_through", 8), ("behavioural_change", 6)]
FAMILY = {"fan_in": "AMLworld", "fan_out": "AMLworld", "cycle": "AMLworld", "gather_scatter": "AMLworld",
          "scatter_gather": "AMLworld", "bipartite": "AMLworld", "stack": "AMLworld", "random": "AMLworld",
          "smurfing": "SAML-D", "layered_fan_out": "SAML-D", "rapid_pass_through": "PaySim/SAML-D",
          "behavioural_change": "SAML-D", "demo_ring": "VersoML demo"}
HARD_NEGATIVE_SEGMENTS = {"student", "pensioner", "micro_merchant", "sme", "crypto_trader"}


# ---------------------------------------------------------------- cărăușii fixați ai scenariilor


def _fixed_mule(key: str, seed: int, days_open: int, prefix: str) -> dict:
    rng = ids.sub_rng(key, seed)
    fake = new_fake(key, seed)
    first, last, _ = person_name(fake, rng)
    iban = ids.make_iban(ids.OWN_BANK, prefix + f"{rng.randint(0, 10**12 - 1):012d}")
    return {"iban": iban, "name": f"{first} {last}", "opened_at": iso(WORLD_NOW - timedelta(days=days_open)),
            "holder_ref": ids.pseudonym("TIT", iban), "bank_bic": ids.bank_bic(ids.OWN_BANK)}


def demo_mule(seed: int = 7) -> dict:
    """Contul-cărăuș intern (Banca Demo) în care plătesc demo_t1 și demo_t1_victima2."""
    return _fixed_mule("demo-mule", seed, 41, "1777")


def inel_mule(seed: int = 7) -> dict:
    """Contul-cărăuș intern al scenariului inel_carausi (trei victime, același IBAN)."""
    return _fixed_mule("inel-mule", seed, 23, "1778")


# ---------------------------------------------------------------- constructorul


class AmlBuilder:
    def __init__(self, *, seed: int, now: datetime, cbs: list[dict], catalogs: dict, idg: IdGen):
        self.seed, self.now, self.cat, self.idg = seed, now, catalogs, idg
        self.rng = ids.sub_rng("aml", seed)
        self.fake = new_fake("aml-persons", seed)
        self.start = now - timedelta(days=HISTORY_DAYS)
        self.fidg = IdGen("A")
        self.accounts: dict[str, dict] = {}
        self.flows: list[dict] = []
        self.patterns: list[dict] = []
        self.segments: dict[str, str] = {}
        self.mules: set[str] = set()
        self.cbs = cbs
        self.retail = [cb for cb in cbs if cb["profile"]["segment"] in ("salariat", "liber_profesionist")]
        self.victimized: set[str] = set()
        self.extra_client_tx: dict[str, list[dict]] = defaultdict(list)
        self.extra_sessions: dict[str, list[dict]] = defaultdict(list)
        self.extra_auth: dict[str, list[dict]] = defaultdict(list)
        self.extra_prior: list[dict] = []
        self.reported_client_tx: dict[str, str] = {}
        self.names_in_use = {cb["customer"]["full_name"] for cb in cbs}
        self.merchant_pool = [(m, m["weight"]) for m in catalogs["merchants"] if m["weight"] > 0]
        self.cat_companies_extra: list[dict] = []
        self.layer2_ibans: set[str] = set()
        self.n_life = 0
        self.hidg = IdGen("H")
        self.pattern_victims: list[str] = []
        self.pattern_client_tx: list[str] = []
        self._flow_mark = 0
        self.ext_friend_pool = [self.external_person() for _ in range(60)]

    # -------- conturi
    def _name(self) -> str:
        for _ in range(20):
            f, l, _ = person_name(self.fake, self.rng)
            n = f"{f} {l}"
            if n not in self.names_in_use:
                self.names_in_use.add(n)
                return n
        return n

    def internal_account(self, segment: str, opened: datetime, *, holder_type: str = "persoana_fizica",
                         account_type: str = "cont_curent_pf", name: str | None = None, cui: str | None = None) -> dict:
        iban = ids.generate_iban(self.rng, ids.OWN_BANK)
        acc = {"iban": iban, "kind": "internal", "bank_code": ids.OWN_BANK, "holder_type": holder_type,
               "account_type": account_type, "opened_at": iso(opened), "status": "activ",
               "holder_ref": ids.pseudonym("TIT", iban), "holder_name": name if holder_type == "persoana_juridica" else None,
               "cui": cui, "synthetic": True, "_name": name or self._name()}
        self.accounts[iban] = acc
        self.segments[iban] = segment
        return acc

    def external_person(self, bank: str | None = None) -> dict:
        iban = ids.generate_iban(self.rng, bank or self.rng.choice(ids.OTHER_BANKS))
        acc = {"iban": iban, "kind": "external", "bank_code": ids.iban_bank_code(iban), "holder_type": "necunoscut",
               "account_type": "necunoscut", "opened_at": None, "status": None, "holder_ref": None,
               "holder_name": None, "cui": None, "synthetic": True, "_name": self._name()}
        self.accounts[iban] = acc
        self.segments.setdefault(iban, "external")
        return acc

    def company_account(self, name: str, internal: bool, segment: str) -> dict:
        cui = ids.generate_invalid_cui(self.rng, 8)
        opened = self.now - timedelta(days=self.rng.randint(200, 3000))
        if internal:
            acc = self.internal_account(segment, opened, holder_type="persoana_juridica", account_type="cont_curent_pj",
                                        name=name, cui=cui)
        else:
            acc = self.external_person()
            acc.update(holder_type="persoana_juridica", holder_name=name, cui=cui, _name=name)
        self.cat_companies_extra.append({"cui": cui, "name": name, "onrc": ids.generate_onrc(self.rng, opened.year),
                                         "registered_at": opened.date().isoformat(), "status": "activă",
                                         "caen": self.rng.choice(["4791", "9602", "4520", "5610", "7490", "4321"]),
                                         "city": "București", "iban": acc["iban"], "role": segment,
                                         "cui_checksum_valid": False, "synthetic": True})
        return acc

    # -------- fluxuri
    def flow(self, ts: datetime, frm: str, to: str, amount: float, channel: str = "transfer",
             reference: str = "Transfer", reported: str | None = None) -> dict:
        f = {"flow_id": self.fidg("FL", 7), "ts": iso(ts), "from_iban": frm, "to_iban": to, "amount": money(amount),
             "currency": "RON", "channel": channel, "reference": reference, "reported_fraud": int(reported is not None),
             "report_source": reported, "case_id": None, "feed": "core_feed", "synthetic": True, "_dt": ts}
        self.flows.append(f)
        return f

    def client_payment(self, cb: dict, ts: datetime, to_iban: str, to_name: str, amount: float, desc: str, *,
                       instant: bool = False, report: str | None = None, optional: bool = True) -> dict:
        """Plată făcută de un client al zonei client: apare în istoricul lui și, prin oglindă, în zona AML."""
        dev = active_device(cb)
        prof = cb["profile"]
        ip = prof["home_ip"] if self.rng.random() < 0.6 else prof["mobile_ip"]
        ses = make_session(self.idg, cb, dev, ip, ts - timedelta(minutes=self.rng.randint(1, 6)),
                           ts + timedelta(minutes=self.rng.randint(1, 3)))
        t = tx_record(self.idg, cb, "debit", "transfer", "transfer_instant" if instant else "transfer", amount, ts, desc,
                      counterparty_name=to_name, counterparty_iban=to_iban, device_id=dev["device_id"],
                      session_id=ses["session_id"], ip=ip, end_to_end_id=f"E2E{ids.hex_id(self.rng, 12).upper()}",
                      _optional=optional)
        ref = cb["customer"]["customer_ref"]
        self.extra_client_tx[ref].append(t)
        self.extra_sessions[ref].append(ses)
        self.extra_auth[ref].append(make_auth(self.idg, cb, ts=ts - timedelta(seconds=self.rng.randint(8, 50)),
                                              method="app_push", purpose="payment", device=dev, tx_id=t["tx_id"],
                                              session_id=ses["session_id"], shown=True, shown_amount=t["amount"],
                                              shown_payee=to_name, ip=ip))
        if report:
            self.reported_client_tx[t["tx_id"]] = report
        return t

    def spend(self, iban: str, start: datetime, end: datetime, rate: float, *, lo: float = 10, hi: float = 250,
              atm_per_month: float = 1.5, atm_amounts=(100, 200, 300, 500)) -> None:
        day = start.date()
        while day <= end.date():
            for _ in range(poisson(self.rng, rate)):
                m = weighted_choice(self.rng, self.merchant_pool)
                ts = rand_time(self.rng, day, 7, 22)
                if start <= ts < end:
                    amt = min(log_uniform(self.rng, max(lo, m["amount_lo"]), max(lo + 1, min(hi, m["amount_hi"]))), hi)
                    self.flow(ts, iban, m["settlement_iban"], amt, "card", "Plată card")
            if self.rng.random() < atm_per_month / 30:
                ts = rand_time(self.rng, day, 8, 21)
                if start <= ts < end:
                    self.flow(ts, iban, art.CASH_NODE, self.rng.choice(atm_amounts), "atm", "Retragere numerar")
            day += timedelta(days=1)

    def months(self) -> list[tuple[int, int]]:
        out, d = [], self.start.date()
        while d <= self.now.date():
            if (d.year, d.month) not in out:
                out.append((d.year, d.month))
            d += timedelta(days=1)
        return out

    def clamp(self, ts: datetime, not_before: datetime | None = None) -> datetime:
        latest = self.now - timedelta(minutes=self.rng.randint(5, 90))
        if ts > latest:
            ts = latest
        if not_before and ts <= not_before:
            ts = not_before + timedelta(minutes=self.rng.randint(3, 20))
        return ts

    # ---------------------------------------------------------------- populații normale

    def populations(self) -> None:
        r, now, start = self.rng, self.now, self.start
        tax = self.cat["tax"]
        # studenți: viață normală + bani de la familie (uneori retrași numerar în aceeași zi)
        for _ in range(POPULATIONS["student"]):
            internal_parent = bool(self.retail) and r.random() < 0.5
            fam = None if internal_parent else self.external_person()
            family = None if internal_parent else {"name": fam["_name"], "iban": fam["iban"]}
            acc = self.life("student", "student", profile={"no_allowance": internal_parent}, family=family)
            iban, opened = acc["iban"], parse_ts(acc["opened_at"])
            allowances: list[tuple[datetime, float]] = []
            parent = r.choice(self.retail) if internal_parent else None
            if internal_parent:
                for (y, m) in self.months():
                    ts = at(datetime(y, m, r.randint(1, 5)).date(), r.randint(8, 20), r.randint(0, 59))
                    if start <= ts < now and ts > opened:
                        amt = r.randrange(400, 1800, 50)
                        self.client_payment(parent, ts, iban, acc["_name"], amt, f"Transfer către {acc['_name']}",
                                            instant=r.random() < 0.4, optional=False)
                        allowances.append((ts, amt))
            else:
                allowances = [(f["_dt"], f["amount"]) for f in self.flows
                              if f["to_iban"] == iban and f["from_iban"] == fam["iban"]]
            if r.random() < 0.4:   # retragere de numerar în aceeași zi (tranzit rapid legitim)
                for ts, amt in allowances:
                    self.flow(self.clamp(ts + timedelta(hours=r.uniform(1, 8)), ts), iban, art.CASH_NODE,
                              round(amt * r.uniform(0.5, 0.8), -1), "atm", "Retragere numerar")
            for (y, m) in self.months():   # transferuri mici de la colegi (fan-in legitim)
                for _ in range(poisson(r, 2.0)):
                    ts = rand_time(r, datetime(y, m, r.randint(1, 28)).date(), 9, 23)
                    if start <= ts < now and ts > opened:
                        self.flow(ts, r.choice(self.ext_friend_pool)["iban"], iban, log_uniform(r, 15, 200),
                                  "transfer_instant", "Transfer")
            if r.random() < 0.3:   # taxă de școlarizare plătită din bani primiți de la familie
                ts = now - timedelta(days=r.uniform(3, 28))
                amt = r.randrange(2000, 6000, 100)
                if internal_parent:
                    self.client_payment(parent, ts, iban, acc["_name"], amt, f"Transfer către {acc['_name']}",
                                        optional=False)
                else:
                    self.flow(ts, fam["iban"], iban, amt, "transfer", "Transfer")
                uni = self.cat["big_ticket"][3]
                self.flow(self.clamp(ts + timedelta(hours=r.uniform(2, 72)), ts), iban, uni["iban"],
                          amt * r.uniform(0.9, 1.0), "transfer", "Taxă școlarizare")
        # pensionari și liber-profesioniști: aceeași viață ca la clienții zonei client
        for _ in range(POPULATIONS["pensioner"]):
            self.life("pensionar", "pensioner")
        for _ in range(POPULATIONS["freelancer"]):
            self.life("liber_profesionist", "freelancer")
        # mici comercianți (fan-in legitim)
        for i in range(POPULATIONS["micro_merchant"]):
            nm = f"{self.rng.choice(['ATELIER', 'SERVICE', 'MAGAZIN', 'CABINET', 'STUDIO', 'CROITORIE', 'MESERIAȘ'])} " \
                 f"{self.rng.choice(['DEMO', 'EXEMPLU', 'FICTIV'])} {i + 1:02d} " \
                 f"{self.rng.choice(['SRL', 'PFA', 'II'])}"
            acc = self.company_account(nm, True, "micro_merchant")
            iban = acc["iban"]
            buyers = [self.external_person() for _ in range(r.randint(10, 30))]
            suppliers = r.sample(self.cat["suppliers"], r.randint(2, 5))
            day = start.date()
            revenue = 0.0
            while day <= now.date():
                for _ in range(poisson(r, r.uniform(0.6, 1.6))):
                    ts = rand_time(r, day, 8, 20)
                    if not (start <= ts < now):
                        continue
                    a = log_uniform(r, 20, 600)
                    revenue += a
                    rep = ("recall_camt056" if r.random() < 0.5 else "dispute_intern") if r.random() < 0.006 else None
                    if r.random() < 0.4 and self.retail:
                        cb = r.choice(self.retail)
                        self.client_payment(cb, ts, iban, nm, a, f"Plată {nm}", instant=r.random() < 0.5, report=rep)
                    else:
                        b = r.choice(buyers) if r.random() < 0.6 else self.external_person()
                        self.flow(ts, b["iban"], iban, a, r.choice(["transfer", "transfer_instant"]), "Plată servicii",
                                  reported=rep)
                if day.weekday() == 4 and revenue > 800:
                    for s in r.sample(suppliers, min(len(suppliers), r.randint(1, 2))):
                        amt = min(revenue * r.uniform(0.25, 0.45), 8000)
                        ts = rand_time(r, day, 9, 16)
                        if start <= ts < now:
                            self.flow(ts, iban, s["iban"], amt, "transfer", "Plată furnizor")
                            revenue -= amt
                    if r.random() < 0.6:
                        ts = rand_time(r, day, 16, 19)
                        if start <= ts < now:
                            a = min(revenue * 0.3, 2000)
                            if a > 100:
                                self.flow(ts, iban, art.CASH_NODE, round(a, -1), "atm", "Retragere numerar")
                                revenue -= a
                if day.day == 10:
                    ts = rand_time(r, day, 9, 12)
                    if start <= ts < now:
                        self.flow(ts, iban, tax["iban"], r.uniform(200, 1500), "transfer", "Impozit")
                day += timedelta(days=1)
        # IMM-uri cu plăți salariale (fan-out legitim), inclusiv angajatorii interni din catalog
        smes = [e for e in self.cat["employers"] if e["internal"]]
        for e in smes:
            self.accounts.setdefault(e["iban"], {"iban": e["iban"], "kind": "internal", "bank_code": ids.OWN_BANK,
                                                 "holder_type": "persoana_juridica", "account_type": "cont_curent_pj",
                                                 "opened_at": iso(now - timedelta(days=r.randint(800, 4000))),
                                                 "status": "activ", "holder_ref": ids.pseudonym("TIT", e["iban"]),
                                                 "holder_name": e["name"], "cui": e["cui"], "synthetic": True,
                                                 "_name": e["name"]})
            self.segments[e["iban"]] = "sme"
        for i in range(POPULATIONS["sme"]):
            nm = f"{self.rng.choice(['ALBASTRU', 'VERDE', 'ROȘU', 'GALBEN', 'ARGINT', 'CRISTAL', 'GRANIT'])} " \
                 f"{self.rng.choice(['SERV', 'TECH', 'CONSTRUCT', 'TRANS', 'COM'])} DEMO {i + 1:02d} SRL"
            smes.append({"iban": self.company_account(nm, True, "sme")["iban"], "name": nm})
        for e in smes:
            iban = e["iban"]
            employees = [self.external_person() for _ in range(r.randint(5, 22))]
            clients = r.sample(self.cat["clients"], r.randint(3, 8))
            for (y, m) in self.months():
                pay = at(datetime(y, m, 10).date(), 9, r.randint(0, 59))
                if start <= pay < now:
                    for emp in employees:
                        self.flow(pay + timedelta(seconds=r.randint(0, 900)), iban, emp["iban"],
                                  r.randrange(2800, 7500, 10), "salary", "Salariu")
                    self.flow(pay + timedelta(days=15), iban, tax["iban"], r.uniform(3000, 20000), "transfer", "Contribuții")
                for _ in range(r.randint(4, 14)):
                    ts = rand_time(r, datetime(y, m, r.randint(1, 28)).date(), 9, 17)
                    if start <= ts < now:
                        self.flow(ts, r.choice(clients)["iban"], iban, log_uniform(r, 2000, 40000), "transfer", "Plată factură")
                for _ in range(r.randint(2, 6)):
                    ts = rand_time(r, datetime(y, m, r.randint(1, 28)).date(), 9, 17)
                    if start <= ts < now:
                        self.flow(ts, iban, r.choice(self.cat["suppliers"])["iban"], log_uniform(r, 1500, 25000),
                                  "transfer", "Plată furnizor")
        # traderi cripto legitimi: salariu, cumpără și vând des pe exchange
        for _ in range(POPULATIONS["crypto_trader"]):
            acc = self.life("salariat", "crypto_trader", profile={"crypto": True})
            iban = acc["iban"]
            for (y, m) in self.months():
                for _ in range(r.randint(3, 10)):
                    ts = rand_time(r, datetime(y, m, r.randint(1, 28)).date(), 8, 23)
                    if start <= ts < now:
                        self.flow(ts, iban, art.CRYPTO_EXCHANGE_IBAN, log_uniform(r, 200, 5000), "transfer_instant",
                                  "Alimentare cont")
                for _ in range(r.randint(1, 4)):
                    ts = rand_time(r, datetime(y, m, r.randint(1, 28)).date(), 8, 23)
                    if start <= ts < now:
                        self.flow(ts, art.CRYPTO_EXCHANGE_IBAN, iban, log_uniform(r, 300, 6000), "transfer_instant",
                                  "Retragere exchange")

    def life(self, segment: str, label: str, *, opened: datetime | None = None, profile: dict | None = None,
             family: dict | None = None) -> dict:
        """Cont intern de persoană fizică cu viață normală, generată cu același `make_history` ca la clienții
        zonei client (aceleași obiceiuri și aceeași distribuție de vechime). Doar fluxurile ajung în zona AML."""
        self.n_life += 1
        ref = f"AML-{self.n_life:05d}"
        cb = make_customer(self.rng, self.fake, ref, ref, now=self.now, catalogs=self.cat, segment=segment,
                           overrides={"profile": profile or {}})
        if opened is not None:
            cb["accounts"][0]["opened_at"] = iso(opened)
        cb["profile"]["friends"] = [{"name": f["_name"], "iban": f["iban"], "internal_ref": None}
                                    for f in self.rng.sample(self.ext_friend_pool, self.rng.randint(1, 3))]
        if family is not None:
            cb["profile"]["family"] = family
        h = make_history(self.rng, cb, start=self.start, end=self.now, catalogs=self.cat, idg=self.hidg)
        for f in client_tx_to_flows(sorted(h["transactions"], key=lambda t: (t["_dt"], t["tx_id"])), self.fidg):
            f.pop("_client_tx_id", None)
            f["_dt"] = parse_ts(f["ts"])
            self.flows.append(f)
        iban = cb["accounts"][0]["iban"]
        acc = {"iban": iban, "kind": "internal", "bank_code": ids.OWN_BANK, "holder_type": "persoana_fizica",
               "account_type": "cont_curent_pf", "opened_at": cb["accounts"][0]["opened_at"], "status": "activ",
               "holder_ref": ids.pseudonym("TIT", iban), "holder_name": None, "cui": None, "synthetic": True,
               "_name": cb["customer"]["full_name"]}
        self.names_in_use.add(acc["_name"])
        self.accounts[iban] = acc
        self.segments[iban] = label
        return acc

    # ---------------------------------------------------------------- cărăuși și tipologii

    def mule_style(self) -> str:
        return "recruited" if self.rng.random() < 0.55 else "fresh"

    def new_mule(self, style: str | None = None, internal: bool = True) -> dict:
        """Cărăuș nou: "recruited" = cont vechi cu viață normală (schimbare de comportament);
        "fresh" = cont deschis de curând, cu activitate redusă (profil tipic de cărăuș recrutat online)."""
        r, now = self.rng, self.now
        style = style or self.mule_style()
        if not internal:
            acc = self.external_person()
            self.mules.add(acc["iban"])
            self.segments[acc["iban"]] = "mule"
            return acc
        if style == "recruited":
            seg = weighted_choice(r, [("salariat", 0.7), ("liber_profesionist", 0.1), ("student", 0.2)])
            acc = self.life(seg, "mule")
        else:
            fam = r.choice(self.ext_friend_pool)
            acc = self.life("student", "mule", opened=now - timedelta(days=r.randint(8, 70)),
                            family={"name": fam["_name"], "iban": fam["iban"]},
                            profile={"pos_rate": r.uniform(0.1, 0.45), "ecom_rate": 0.03, "atm_per_month": 1.0,
                                     "p2p_per_month": 1, "utilities": [], "rent": False, "big_events": False,
                                     "forwarder": False, "income": r.randrange(300, 1200, 50)})
        self.mules.add(acc["iban"])
        return acc

    def daytime(self, ts: datetime) -> datetime:
        """Mută un moment în profilul zilnic obișnuit (majoritatea plăților între 08 și 23)."""
        h = self.rng.randint(0, 6) if self.rng.random() < 0.08 else self.rng.randint(8, 22)
        return ts.replace(hour=h, minute=self.rng.randint(0, 59))

    def victim_payment(self, mule: dict, ts: datetime, amount: float, *, internal_prob: float = 0.15) -> str:
        r = self.rng
        ts = self.clamp(self.daytime(ts))
        candidates = [cb for cb in self.retail if cb["customer"]["customer_ref"] not in self.victimized]
        if r.random() < internal_prob and candidates:
            cb = r.choice(candidates)
            ref = cb["customer"]["customer_ref"]
            self.victimized.add(ref)
            report = "dispute_intern" if r.random() < 0.6 else None
            t = self.client_payment(cb, ts, mule["iban"], mule["_name"], amount, f"Transfer către {mule['_name']}",
                                    instant=r.random() < 0.4, report=report, optional=False)
            self.pattern_client_tx.append(t["tx_id"])
            self.pattern_victims.append(cb["accounts"][0]["iban"])
            if report:
                opened = ts + timedelta(hours=r.randint(4, 60))
                self.extra_prior.append({
                    "dispute_id": self.idg("PD", 5), "customer_ref": ref,
                    "case_id": f"CT-2026-{ids.stable_int(ref, t['tx_id']) % 10**6:06d}", "tx_ref": t["tx_id"],
                    "opened_at": iso(min(opened, self.now - timedelta(hours=1))), "closed_at": None,
                    "channel": t["channel"], "dispute_type": "app", "scenario": "cont_sigur" if t["channel"] == "transfer_instant" else "vishing_securitate",
                    "amount": t["amount"], "counterparty": mule["_name"], "outcome": "in_analiza",
                    "reason": "plată autorizată sub manipulare", "synthetic": True})
            return cb["accounts"][0]["iban"]
        v = self.external_person()
        rep = "recall_camt056" if r.random() < 0.2 else None
        self.flow(ts, v["iban"], mule["iban"], amount, r.choice(["transfer", "transfer_instant"]), "Transfer", reported=rep)
        self.pattern_victims.append(v["iban"])
        return v["iban"]

    def cash_out(self, mule: dict, amount: float, t_in: datetime, *, dest: str | None = None,
                 fast: bool | None = None, share: float | None = None) -> datetime:
        r = self.rng
        if fast is None:
            speed = weighted_choice(r, [("fast", 0.65), ("medium", 0.2), ("slow", 0.15)])
        else:
            speed = "fast" if fast else "slow"
        dwell_h = {"fast": min(math.exp(r.gauss(math.log(3.0), 0.7)), 20), "medium": r.uniform(6, 30),
                   "slow": r.uniform(24, 96)}[speed]
        share = share or r.uniform(0.7, 0.98)
        dest = dest or weighted_choice(r, [("crypto", 0.4), ("cash", 0.25), ("mixed", 0.15), ("external", 0.2)])
        t = self.clamp(t_in + timedelta(hours=dwell_h), t_in)
        total = amount * share
        if dest == "external":
            onward = self.external_person()
            self.flow(t, mule["iban"], onward["iban"], total, r.choice(["transfer", "transfer_instant"]), "Transfer")
            return t
        if dest in ("crypto", "mixed"):
            part = total if dest == "crypto" else total * 0.7
            self.flow(t, mule["iban"], art.CRYPTO_EXCHANGE_IBAN, part, "transfer_instant", "Alimentare cont")
            total -= part
        if total > 50:
            n = max(1, min(4, math.ceil(total / 4000)))
            for k in range(n):
                tk = self.clamp(t + timedelta(minutes=10 + 25 * k), t_in)
                self.flow(tk, mule["iban"], art.CASH_NODE, round(total / n, -1), "atm", "Retragere numerar")
        return t

    def layer2(self, internal_prob: float) -> dict:
        """Cărăuș de nivel 2: cont vechi, cu istoric normal, care primește doar de la alți cărăuși."""
        internal = self.rng.random() < internal_prob
        m = self.new_mule("recruited" if self.rng.random() < 0.75 else "fresh", internal=internal)
        m["_layer2"] = True
        self.layer2_ibans.add(m["iban"])
        return m

    def pass_on(self, mule: dict, amount: float, t_in: datetime) -> datetime:
        """Ieșirea unui cărăuș: discretă (spre alt cont, în zile) pentru nivelul 2, rapidă pentru restul."""
        if mule.get("_layer2") and self.rng.random() < 0.7:
            return self.cash_out(mule, amount, t_in, dest="external", fast=self.rng.random() < 0.3,
                                 share=self.rng.uniform(0.75, 0.95))
        return self.cash_out(mule, amount, t_in)

    def forward(self, src: dict, dst: dict, amount: float, t: datetime) -> datetime:
        self.flow(t, src["iban"], dst["iban"], amount, self.rng.choice(["transfer", "transfer_instant"]), "Transfer")
        return t

    def _t0(self, lo_days: float = 3, hi_days: float = 26) -> datetime:
        return self.now - timedelta(days=self.rng.uniform(lo_days, hi_days), hours=self.rng.randint(0, 12))

    def _begin(self) -> None:
        self.pattern_victims: list[str] = []
        self.pattern_client_tx: list[str] = []
        self._flow_mark = len(self.flows)

    def _end(self, typology: str, mules: list[dict], t0: datetime) -> dict:
        new_flows = self.flows[self._flow_mark:]
        p = {"pattern_id": f"PAT-{len(self.patterns) + 1:03d}", "typology": typology, "family": FAMILY[typology],
             "mules": [m["iban"] for m in mules], "victims": list(self.pattern_victims),
             "flow_ids": [f["flow_id"] for f in new_flows], "client_tx_ids": list(self.pattern_client_tx),
             "start": iso(t0), "end": iso(max((f["_dt"] for f in new_flows), default=t0)),
             "amount_in": money(sum(f["amount"] for f in new_flows if f["to_iban"] in {m["iban"] for m in mules}
                                    and f["from_iban"] not in {m["iban"] for m in mules})),
             "synthetic": True}
        self.patterns.append(p)
        return p

    def pattern(self, typology: str) -> None:
        r = self.rng
        self._begin()
        t0 = self._t0()
        style = self.mule_style()
        if typology == "fan_in":
            m = self.new_mule(style)
            times = sorted(t0 + timedelta(hours=r.uniform(0, 72)) for _ in range(r.randint(4, 9)))
            fast = r.random() < 0.8
            for ts in times:
                amt = log_uniform(r, 400, 6000)
                self.victim_payment(m, ts, amt)
                self.cash_out(m, amt, ts, fast=fast)
            mules = [m]
        elif typology == "fan_out":
            s = self.new_mule(style)
            recv = [self.layer2(0.5) for _ in range(r.randint(4, 7))]
            total = 0.0
            for _ in range(r.randint(1, 2)):
                a = log_uniform(r, 4000, 12000)
                total += a
                self.victim_payment(s, t0 + timedelta(hours=r.uniform(0, 6)), a)
            t1 = t0 + timedelta(hours=r.uniform(6.5, 12))
            for rc in recv:
                a = total * 0.95 / len(recv) * r.uniform(0.85, 1.15)
                tt = self.clamp(t1 + timedelta(hours=r.uniform(0, 10)), t0)
                self.forward(s, rc, a, tt)
                if rc["kind"] == "internal":
                    self.pass_on(rc, a, tt)
            mules = [s] + recv
        elif typology == "cycle":
            k = r.randint(3, 5)
            ring = [self.new_mule(None, internal=(i < 2 or r.random() < 0.5)) for i in range(k)]
            amt = log_uniform(r, 3000, 10000)
            self.victim_payment(ring[0], t0, amt)
            t = t0
            for _loop in range(2 if r.random() < 0.4 else 1):
                for i in range(k):
                    t = self.clamp(t + timedelta(hours=r.uniform(2, 30)), t)
                    amt *= r.uniform(0.96, 0.99)
                    self.forward(ring[i], ring[(i + 1) % k], amt, t)
            self.cash_out(ring[0], amt, t)
            mules = ring
        elif typology == "gather_scatter":
            hub = self.new_mule(style)
            total, t_last = 0.0, t0
            for _ in range(r.randint(4, 6)):
                tt = t0 + timedelta(hours=r.uniform(0, 48))
                a = log_uniform(r, 800, 5000)
                total += a
                self.victim_payment(hub, tt, a)
                t_last = max(t_last, tt)
            dests = [self.layer2(0.5) for _ in range(r.randint(3, 5))]
            for d in dests:
                a = total * 0.93 / len(dests)
                tt = self.clamp(t_last + timedelta(hours=r.uniform(1, 24)), t_last)
                self.forward(hub, d, a, tt)
                if d["kind"] == "internal":
                    self.pass_on(d, a, tt)
            mules = [hub] + dests
        elif typology == "scatter_gather":
            s = self.new_mule(style)
            mids = [self.layer2(0.6) for _ in range(r.randint(3, 5))]
            sink = self.new_mule()
            total = 0.0
            for _ in range(r.randint(1, 2)):
                a = log_uniform(r, 3000, 10000)
                total += a
                self.victim_payment(s, t0 + timedelta(hours=r.uniform(0, 5)), a)
            t1 = t0 + timedelta(hours=r.uniform(5.5, 10))
            t_last = t1
            for mid in mids:
                a = total * 0.96 / len(mids)
                tt = self.clamp(t1 + timedelta(hours=r.uniform(0, 8)), t0)
                self.forward(s, mid, a, tt)
                t2 = self.clamp(tt + timedelta(hours=r.uniform(2, 24)), tt)
                self.forward(mid, sink, a * r.uniform(0.95, 0.99), t2)
                t_last = max(t_last, t2)
            self.cash_out(sink, total * 0.9, t_last, dest="crypto")
            mules = [s] + mids + [sink]
        elif typology == "bipartite":
            A = [self.new_mule(None, internal=r.random() < 0.6) for _ in range(r.randint(3, 4))]
            B = [self.layer2(0.6) for _ in range(r.randint(3, 4))]
            for a in A:
                tot = 0.0
                for _ in range(r.randint(1, 3)):
                    x = log_uniform(r, 800, 5000)
                    tot += x
                    self.victim_payment(a, t0 + timedelta(hours=r.uniform(0, 24)), x)
                targets = [b for b in B if r.random() < 0.7] or [r.choice(B)]
                for b in targets:
                    tt = self.clamp(t0 + timedelta(hours=r.uniform(26, 60)), t0)
                    self.forward(a, b, tot * 0.95 / len(targets), tt)
            for b in B:
                if b["kind"] == "internal":
                    inflow = sum(f["amount"] for f in self.flows[self._flow_mark:] if f["to_iban"] == b["iban"])
                    if inflow:
                        last = max(f["_dt"] for f in self.flows[self._flow_mark:] if f["to_iban"] == b["iban"])
                        self.pass_on(b, inflow, last)
            mules = A + B
        elif typology == "stack":
            L = [[(self.new_mule(None, internal=r.random() < 0.6) if li == 0 else self.layer2(0.6))
                  for _ in range(r.randint(2, 3))] for li in range(3)]
            amounts: dict[str, float] = {}
            for a in L[0]:
                x = log_uniform(r, 3000, 9000)
                amounts[a["iban"]] = x
                self.victim_payment(a, t0 + timedelta(hours=r.uniform(0, 12)), x)
            t = t0 + timedelta(hours=13)
            for li in range(2):
                nxt: dict[str, float] = defaultdict(float)
                for a in L[li]:
                    for b in L[li + 1]:
                        x = amounts.get(a["iban"], 0) * 0.96 / len(L[li + 1])
                        tt = self.clamp(t + timedelta(hours=r.uniform(0, 12)), t0)
                        self.forward(a, b, x, tt)
                        nxt[b["iban"]] += x
                amounts = nxt
                t = t + timedelta(hours=r.uniform(12, 30))
            for b in L[2]:
                if b["kind"] == "internal" and amounts.get(b["iban"]):
                    self.pass_on(b, amounts[b["iban"]], self.clamp(t, t0))
            mules = [m for layer in L for m in layer]
        elif typology == "random":
            M = [self.new_mule(None, internal=r.random() < 0.65) for _ in range(r.randint(4, 6))]
            bal: dict[str, float] = defaultdict(float)
            for m in r.sample(M, 2):
                x = log_uniform(r, 2000, 8000)
                bal[m["iban"]] += x
                self.victim_payment(m, t0 + timedelta(hours=r.uniform(0, 12)), x)
            t = t0 + timedelta(hours=13)
            for _ in range(r.randint(8, 15)):
                src = max(M, key=lambda m: bal[m["iban"]] + r.random())
                dst = r.choice([m for m in M if m is not src])
                x = bal[src["iban"]] * r.uniform(0.4, 0.9)
                if x < 100:
                    continue
                t = self.clamp(t + timedelta(hours=r.uniform(1, 18)), t0)
                self.forward(src, dst, x, t)
                bal[src["iban"]] -= x
                bal[dst["iban"]] += x
            for m in M:
                if m["kind"] == "internal" and bal[m["iban"]] > 500:
                    self.cash_out(m, bal[m["iban"]], t)
            mules = M
        elif typology == "smurfing":
            m = self.new_mule(style)
            thr = r.choice([1000, 5000, 10000])
            total, t_last = 0.0, t0
            for _ in range(r.randint(5, 12)):
                tt = t0 + timedelta(hours=r.uniform(0, 7 * 24))
                x = r.uniform(0.9, 0.999) * thr
                total += x
                if r.random() < 0.5:
                    self.flow(tt, art.CASH_NODE, m["iban"], x, "cash_deposit", "Depunere numerar")
                else:
                    self.victim_payment(m, tt, x, internal_prob=0.05)
                t_last = max(t_last, tt)
            out = self.external_person() if r.random() < 0.5 else None
            tt = self.clamp(t_last + timedelta(hours=r.uniform(12, 60)), t_last)
            if out:
                self.flow(tt, m["iban"], out["iban"], total * r.uniform(0.85, 0.95), "transfer", "Transfer")
            else:
                self.flow(tt, m["iban"], art.CRYPTO_EXCHANGE_IBAN, total * r.uniform(0.85, 0.95), "transfer_instant",
                          "Alimentare cont")
            mules = [m]
        elif typology == "layered_fan_out":
            s = self.new_mule(style)
            total = log_uniform(r, 9000, 20000)
            self.victim_payment(s, t0, total, internal_prob=0.1)
            l1 = [self.layer2(0.6) for _ in range(3)]
            mules = [s] + l1
            for a in l1:
                x = total * 0.95 / 3
                t1 = self.clamp(t0 + timedelta(hours=r.uniform(1, 8)), t0)
                self.forward(s, a, x, t1)
                for _ in range(2):
                    b = self.layer2(0.5)
                    mules.append(b)
                    t2 = self.clamp(t1 + timedelta(hours=r.uniform(1, 12)), t1)
                    self.forward(a, b, x * 0.47, t2)
                    if b["kind"] == "internal":
                        self.pass_on(b, x * 0.47, t2)
        elif typology == "rapid_pass_through":
            m = self.new_mule()
            for _ in range(r.randint(1, 2)):
                ts = t0 + timedelta(hours=r.uniform(0, 30))
                x = log_uniform(r, 2000, 9000)
                self.victim_payment(m, ts, x)
                self.cash_out(m, x, ts, dest="cash", fast=True, share=r.uniform(0.9, 0.98))
            mules = [m]
        elif typology == "behavioural_change":
            m = self.new_mule("recruited")
            t0 = self._t0(2, 14)
            for _ in range(r.randint(3, 6)):
                ts = t0 + timedelta(hours=r.uniform(0, 96))
                x = log_uniform(r, 600, 5000)
                self.victim_payment(m, ts, x)
                self.cash_out(m, x, ts, dest=r.choice(["crypto", "crypto", "mixed"]))
            mules = [m]
        else:  # pragma: no cover
            raise ValueError(typology)
        self._end(typology, mules, t0)

    def demo_ring(self) -> dict:
        """Cărăușul demo: 3 victime externe în ultimele 7 zile, >85% spre CryptoX în sub 6 ore."""
        dm = demo_mule(self.seed)
        now, r = self.now, ids.sub_rng("demo-ring", self.seed)
        opened = parse_ts(dm["opened_at"])
        acc = {"iban": dm["iban"], "kind": "internal", "bank_code": ids.OWN_BANK, "holder_type": "persoana_fizica",
               "account_type": "cont_curent_pf", "opened_at": dm["opened_at"], "status": "activ",
               "holder_ref": dm["holder_ref"], "holder_name": None, "cui": None, "synthetic": True, "_name": dm["name"]}
        self.accounts[dm["iban"]] = acc
        self.segments[dm["iban"]] = "mule"
        self.mules.add(dm["iban"])
        self._begin()
        # încălzire: două transferuri mici și câteva plăți cu cardul, ca un cont nou obișnuit
        self.flow(opened + timedelta(days=2, hours=3), self.ext_friend_pool[0]["iban"], dm["iban"], 250, "transfer", "Transfer")
        self.flow(opened + timedelta(days=5, hours=6), self.ext_friend_pool[1]["iban"], dm["iban"], 180, "transfer", "Transfer")
        for k in range(6):
            m = self.cat["merchants"][k % 6]
            self.flow(opened + timedelta(days=3 + 5 * k, hours=12), dm["iban"], m["settlement_iban"],
                      round(r.uniform(15, 70), 2), "card", "Plată card")
        plan = [("XBNK", 6, 15, 10, 2850.0, 2.1, "recall_camt056"), ("YBNK", 3, 11, 42, 4100.0, 4.4, None),
                ("XBNK", 1, 19, 5, 3600.0, 1.6, None)]
        for bank, days_ago, hh, mm, amount, dwell_h, rep in plan:
            v = self.external_person(bank)
            day = (now - timedelta(days=days_ago)).date()
            ts = at(day, hh, mm, r.randint(0, 59))
            self.flow(ts, v["iban"], dm["iban"], amount, "transfer_instant", "Transfer", reported=rep)
            self.pattern_victims.append(v["iban"])
            self.flow(ts + timedelta(hours=dwell_h), dm["iban"], art.CRYPTO_EXCHANGE_IBAN,
                      round(amount * r.uniform(0.91, 0.94), 2), "transfer_instant", "Alimentare cont")
        p = self._end_named("demo_ring", [acc], now - timedelta(days=7))
        p["typologies"] = ["fan_in", "rapid_pass_through"]
        return dm

    def _end_named(self, typology: str, mules: list[dict], t0: datetime) -> dict:
        return self._end(typology, mules, t0)

    def contaminate(self) -> None:
        """Cărăușii trăiesc printre oameni obișnuiți: plătesc chirie, cumpără de la mici comercianți, dau bani
        familiei. Conturile normale ajung astfel și „în aval" de un cărăuș, ca în realitate."""
        r = self.rng
        normals = [iban for iban, seg in self.segments.items()
                   if seg in ("student", "pensioner", "freelancer", "micro_merchant", "crypto_trader")
                   and self.accounts.get(iban, {}).get("kind") == "internal"]
        retail = [cb for cb in self.retail]
        for iban in sorted(self.mules):
            acc = self.accounts.get(iban)
            if not acc or acc["kind"] != "internal" or r.random() > 0.6:
                continue
            for _ in range(r.randint(1, 3)):
                ts = self.clamp(self.now - timedelta(days=r.uniform(0.5, 27)))
                amt = log_uniform(r, 50, 1500)
                if r.random() < 0.35 and retail:
                    cb = r.choice(retail)
                    t = tx_record(self.idg, cb, "credit", "p2p_in", r.choice(["transfer", "transfer_instant"]), amt, ts,
                                  f"Transfer primit de la {acc['_name']}", counterparty_name=acc["_name"],
                                  counterparty_iban=iban, disputable=False, _optional=False)
                    self.extra_client_tx[cb["customer"]["customer_ref"]].append(t)
                elif normals:
                    self.flow(ts, iban, r.choice(normals), amt, "transfer", "Transfer")

    def run(self) -> dict:
        self.populations()
        for typology, n in PATTERN_PLAN:
            for _ in range(n):
                self.pattern(typology)
        self.contaminate()
        dm = self.demo_ring()
        for p in self.patterns:
            p.setdefault("typologies", [p["typology"]])
        # conturile persoanelor externe nu primesc nume în baza AML
        extra = []
        for iban, a in self.accounts.items():
            a = dict(a)
            extra.append(a)
        return {"accounts": extra, "flows": self.flows, "patterns": self.patterns, "segments": self.segments,
                "extra_client_tx": self.extra_client_tx, "extra_sessions": self.extra_sessions,
                "extra_auth": self.extra_auth, "extra_prior_disputes": self.extra_prior,
                "reported_client_tx": self.reported_client_tx, "demo_mule": dm,
                "companies": self.cat_companies_extra, "layer2": sorted(self.layer2_ibans)}


def generate_aml_world(*, seed: int, now: datetime, cbs: list[dict], catalogs: dict, idg: IdGen) -> dict:
    return AmlBuilder(seed=seed, now=now, cbs=cbs, catalogs=catalogs, idg=idg).run()


# ---------------------------------------------------------------- conturi, etichete, alerte


def build_aml_accounts(cbs: list[dict], extra: list[dict], catalogs: dict, flows: list[dict], *,
                       now: datetime) -> list[dict]:
    """Toate nodurile zonei AML. Persoanele fizice au doar pseudonim; firmele au denumire și CUI."""
    out: dict[str, dict] = {}
    for cb in cbs:
        for a in cb["accounts"]:
            out[a["iban"]] = {"iban": a["iban"], "kind": "internal", "bank_code": ids.OWN_BANK,
                              "holder_type": "persoana_fizica",
                              "account_type": "cont_curent_pf" if a["type"] == "curent" else "cont_economii",
                              "opened_at": a["opened_at"], "status": "activ",
                              "holder_ref": ids.pseudonym("TIT", cb["customer"]["customer_ref"]),
                              "holder_name": None, "cui": None, "synthetic": True}
    for a in extra:
        a = {k: v for k, v in a.items() if not k.startswith("_")}
        out.setdefault(a["iban"], a)
    for c in catalogs["companies"]:
        if not c.get("iban") or c["iban"] in out:
            continue
        kind = "exchange" if c["role"] == "exchange" else ("internal" if ids.iban_bank_code(c["iban"]) == ids.OWN_BANK else "external")
        out[c["iban"]] = {"iban": c["iban"], "kind": kind, "bank_code": ids.iban_bank_code(c["iban"]),
                          "holder_type": "persoana_juridica", "account_type": "cont_curent_pj" if kind == "internal" else "necunoscut",
                          "opened_at": iso(now - timedelta(days=1500)) if kind == "internal" else None,
                          "status": "activ" if kind == "internal" else None,
                          "holder_ref": ids.pseudonym("TIT", c["iban"]) if kind == "internal" else None,
                          "holder_name": c["name"], "cui": c["cui"], "synthetic": True}
    out[art.CASH_NODE] = {"iban": art.CASH_NODE, "kind": "cash", "bank_code": None, "holder_type": "numerar",
                          "account_type": "numerar", "opened_at": None, "status": None, "holder_ref": None,
                          "holder_name": "Numerar (ATM / ghișeu)", "cui": None, "synthetic": True}
    if art.CRYPTO_EXCHANGE_IBAN in out:
        out[art.CRYPTO_EXCHANGE_IBAN]["kind"] = "exchange"
    for f in flows:
        for node in (f["from_iban"], f["to_iban"]):
            if node not in out:
                out[node] = {"iban": node, "kind": "internal" if ids.iban_bank_code(node) == ids.OWN_BANK else "external",
                             "bank_code": ids.iban_bank_code(node), "holder_type": "necunoscut",
                             "account_type": "necunoscut", "opened_at": None, "status": None, "holder_ref": None,
                             "holder_name": None, "cui": None, "synthetic": True}
    return [out[k] for k in sorted(out)]


def build_labels(aml_accounts: list[dict], patterns: list[dict], segments: dict[str, str],
                 retail_segments: dict[str, str] | None = None, layer2: list[str] | None = None) -> list[dict]:
    """Etichete de adevăr (doar pentru antrenare și evaluare; nu se arată agenților)."""
    by_acc: dict[str, list[dict]] = defaultdict(list)
    for p in patterns:
        for m in p["mules"]:
            by_acc[m].append(p)
    labels = []
    l2 = set(layer2 or [])
    for a in aml_accounts:
        iban = a["iban"]
        pats = by_acc.get(iban, [])
        seg = segments.get(iban) or (retail_segments or {}).get(iban) or (
            "retail" if a["kind"] == "internal" and a["holder_type"] == "persoana_fizica" else
            "business" if a["holder_type"] == "persoana_juridica" else a["kind"])
        labels.append({"entity": "account", "id": iban, "label": "mule" if pats else "normal", "segment": seg,
                       "is_internal": a["kind"] == "internal", "hard_negative": (not pats) and seg in HARD_NEGATIVE_SEGMENTS,
                       "role": ("nivel2" if iban in l2 else "nivel1") if pats else None,
                       "patterns": [p["pattern_id"] for p in pats],
                       "typologies": sorted({t for p in pats for t in p.get("typologies", [p["typology"]])}),
                       "synthetic": True})
    return labels


TM_RULES = {
    "TM-01": "Intrări de la cel puțin 5 plătitori distincți în 7 zile, urmate de ieșiri de cel puțin 80% în 48 de ore",
    "TM-02": "Cel puțin 70% din ieșirile din 7 zile merg spre un exchange cripto",
    "TM-03": "Cel puțin 3 intrări în 7 zile cu sume chiar sub un prag rotund (1.000 / 5.000 / 10.000 lei)",
    "TM-04": "Cont deschis de mai puțin de 60 de zile, cu intrări de peste 15.000 lei în 30 de zile",
    "TM-05": "Retrageri de numerar de cel puțin 80% dintr-o intrare, în 24 de ore",
}
TM_BASIS = "regulă internă de monitorizare, sintetică; pragurile sunt PARAM [U]"


def compute_alerts(aml_accounts: list[dict], flows: list[dict], *, now: datetime) -> list[dict]:
    """Alertele sistemului clasic de monitorizare (reguli simple, multe fals pozitive)."""
    kinds = {a["iban"]: a["kind"] for a in aml_accounts}
    opened = {a["iban"]: parse_ts(a["opened_at"]) for a in aml_accounts if a.get("opened_at")}
    window = now - timedelta(days=30)
    inc: dict[str, list] = defaultdict(list)
    out: dict[str, list] = defaultdict(list)
    for f in flows:
        ts = parse_ts(f["ts"])
        if ts < window or ts > now:
            continue
        inc[f["to_iban"]].append((ts, f["from_iban"], f["amount"]))
        out[f["from_iban"]].append((ts, f["to_iban"], f["amount"], f["channel"]))
    alerts = []
    seq = 0
    for iban in sorted(k for k, v in kinds.items() if v == "internal"):
        ins, outs = sorted(inc.get(iban, [])), sorted(out.get(iban, []))
        if not ins and not outs:
            continue
        hits: list[tuple[str, datetime, str]] = []
        for i, (ts, _, _) in enumerate(ins):
            w = [x for x in ins if ts <= x[0] <= ts + timedelta(days=7)]
            senders = {x[1] for x in w}
            if len(senders) >= 5:
                amt_in = sum(x[2] for x in w)
                amt_out = sum(o[2] for o in outs if ts <= o[0] <= w[-1][0] + timedelta(hours=48))
                if amt_in and amt_out / amt_in >= 0.8:
                    hits.append(("TM-01", w[-1][0], f"{len(senders)} plătitori distincți, ieșiri {amt_out / amt_in:.0%}"))
                    break
        for ts, *_ in outs:
            w = [o for o in outs if ts <= o[0] <= ts + timedelta(days=7)]
            tot = sum(o[2] for o in w)
            cr = sum(o[2] for o in w if kinds.get(o[1]) == "exchange")
            if tot >= 3000 and cr / tot >= 0.7:
                hits.append(("TM-02", w[-1][0], f"{cr / tot:.0%} din ieșiri spre exchange cripto"))
                break
        near = [x for x in ins if any(0.9 * t <= x[2] < t for t in (1000, 5000, 10000))]
        for ts, *_ in near:
            w = [x for x in near if ts <= x[0] <= ts + timedelta(days=7)]
            if len(w) >= 3:
                hits.append(("TM-03", w[-1][0], f"{len(w)} intrări chiar sub prag"))
                break
        if iban in opened and (now - opened[iban]).days < 60 and sum(x[2] for x in ins) > 15000:
            hits.append(("TM-04", ins[-1][0], f"cont de {(now - opened[iban]).days} zile, intrări {sum(x[2] for x in ins):.0f} lei"))
        for ts, _, amt in ins:
            if amt < 2000:
                continue
            cash = sum(o[2] for o in outs if kinds.get(o[1]) == "cash" and ts <= o[0] <= ts + timedelta(hours=24))
            if cash >= 0.8 * amt:
                hits.append(("TM-05", ts, f"retrageri numerar {cash:.0f} lei după o intrare de {amt:.0f} lei"))
                break
        for rule, ts, detail in hits:
            seq += 1
            h = ids.stable_int(iban, rule) % 100
            status = "nou" if h < 45 else "in_analiza" if h < 65 else "inchis_fals_pozitiv" if h < 95 else "escaladat"
            alerts.append({"alert_id": f"AL-{seq:05d}", "iban": iban, "rule_id": rule, "title": TM_RULES[rule],
                           "basis": TM_BASIS, "ts": iso(ts), "detail": detail, "status": status, "synthetic": True})
    return alerts
