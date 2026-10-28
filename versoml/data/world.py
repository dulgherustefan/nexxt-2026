"""Simulatorul Băncii Demo: clienți, conturi, carduri, dispozitive, sesiuni, SCA, tranzacții (zona client)
și, prin `aml_world`, fluxurile conturilor interne, cărăușii și tipologiile de spălare (zona AML).

Totul e sintetic, determinist (seed implicit 7) și ancorat la `WORLD_NOW` (28.10.2026, 10:00, ora României).
Istoricul acoperă `HISTORY_DAYS` zile înainte de `WORLD_NOW`.

Funcțiile `make_customer`, `make_history`, `finalize_balances` și `client_tx_to_flows` sunt refolosite de
`scenarios.py`, ca scenariile să aibă clienți cu același tip de istoric ca restul lumii.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any

from faker import Faker

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.calendar_ro import TZ, iso
from versoml.data.text import MONTHS, fmt_ron, normalize_ro, strip_diacritics

WORLD_NOW = datetime(2026, 10, 28, 10, 0, 0, tzinfo=TZ)
HISTORY_DAYS = 120
FLOW_VERSION = "2026-04"          # versiunea fluxului de aprobare din aplicație (docs/context/14 §2.5)

# ---------------------------------------------------------------- cataloage statice

CITIES = [("București", 30), ("Cluj-Napoca", 7), ("Iași", 6), ("Timișoara", 6), ("Constanța", 5),
          ("Craiova", 4), ("Brașov", 4), ("Galați", 3), ("Ploiești", 3), ("Oradea", 3), ("Brăila", 2),
          ("Arad", 2), ("Pitești", 2), ("Sibiu", 3), ("Bacău", 2), ("Târgu Mureș", 2), ("Baia Mare", 1),
          ("Buzău", 1), ("Botoșani", 1), ("Suceava", 2), ("Satu Mare", 1), ("Focșani", 1), ("Deva", 1)]

DEVICE_MODELS = [("Samsung Galaxy A54", "Android 14"), ("Samsung Galaxy S23", "Android 15"),
                 ("iPhone 13", "iOS 18.6"), ("iPhone 15", "iOS 19.1"), ("Xiaomi Redmi Note 13", "Android 14"),
                 ("Google Pixel 8", "Android 16"), ("Motorola Moto G84", "Android 14"),
                 ("iPhone 12", "iOS 18.6"), ("Samsung Galaxy A35", "Android 15"), ("OnePlus Nord 4", "Android 15")]
ATTACKER_DEVICES = [("Samsung Galaxy A15", "Android 14"), ("Xiaomi Redmi 13C", "Android 14"),
                    ("Emulator Android x86", "Android 13")]

# nume, MCC, tip achiziție, canal, sumă min, sumă max, țară, pondere, domeniu
MERCHANT_CATALOG: list[tuple] = [
    ("North Demo Supermarket", "5411", "goods", "pos", 25, 380, "RO", 10, None),
    ("Mega Example Market", "5411", "goods", "pos", 30, 520, "RO", 8, None),
    ("24h Mini Market Demo", "5411", "goods", "pos", 8, 90, "RO", 7, None),
    ("Demo Fuel A1", "5541", "goods", "pos", 120, 420, "RO", 5, None),
    ("Example Pharmacy", "5912", "goods", "pos", 15, 260, "RO", 4, None),
    ("Example Bistro", "5812", "services", "pos", 35, 240, "RO", 4, None),
    ("Demo Pizzeria", "5812", "services", "pos", 40, 180, "RO", 3, None),
    ("Example Coffee House", "5814", "services", "pos", 9, 45, "RO", 5, None),
    ("Demo Fashion Store", "5691", "goods", "both", 80, 650, "RO", 2, "modademo.example"),
    ("Demo DIY Store", "5200", "goods", "pos", 40, 900, "RO", 2, None),
    ("Example Bookshop", "5942", "goods", "both", 25, 160, "RO", 1, "librariafictiva.example"),
    ("Example Cinema", "7832", "services", "both", 28, 90, "RO", 1, "cinemaexemplu.example"),
    ("Demo City Transit", "4111", "services", "both", 3, 80, "RO", 4, "transporturban.example"),
    ("Example Taxi", "4121", "services", "both", 15, 95, "RO", 2, "taxiexemplu.example"),
    ("TelcoDemo Subscription", "4814", "services", "ecommerce", 35, 120, "RO", 2, "telcodemo.example"),
    ("StreamDemo (synthetic)", "4899", "services", "ecommerce", 29, 69, "IE", 2, "streamdemo.example"),
    ("ElectroDemo Online (synthetic)", "5732", "goods", "ecommerce", 150, 4200, "RO", 2, "electrodemo.example"),
    ("DemoMarket Online", "5999", "goods", "ecommerce", 30, 1600, "RO", 3, "piatademo.example"),
    ("Demo Food Delivery", "5814", "services", "ecommerce", 35, 160, "RO", 3, "mancaredemo.example"),
    ("Demo Travel Agency", "4722", "services", "ecommerce", 400, 3800, "RO", 1, "demotravel.example"),
    ("Example Electro SRL (fictitious)", "5732", "goods", "ecommerce", 300, 3000, "DE", 1, "exempluelectro.example"),
    ("GADGETWORLD SHOP (synthetic)", "5732", "goods", "ecommerce", 60, 900, "US", 1, "gadgetworld-shop.example"),
    ("GlobalApps Store (synthetic)", "5818", "services", "ecommerce", 5, 60, "US", 1, "globalapps.example"),
    ("Demo Fitness Club", "7997", "services", "pos", 90, 220, "RO", 1, None),
    ("Example Florist", "5992", "goods", "pos", 40, 300, "RO", 1, None),
]
EEA = {"RO", "DE", "IE", "FR", "IT", "NL", "AT", "ES"}

# angajatori: nume, pondere, intern (cont la Demo Bank)
EMPLOYER_CATALOG = [
    ("ALFA DEMO SRL", 12, False), ("BETA EXAMPLE SRL", 8, False), ("GAMMA SAMPLE SA", 6, False),
    ("DELTA SOFT DEMO SRL", 5, True), ("OMEGA LOGISTICS DEMO SRL", 4, False), ("SIGMA RETAIL EXAMPLE SA", 7, False),
    ("NOVA CONSTRUCT SAMPLE SRL", 3, False), ("HORIZON MEDICAL DEMO SRL", 3, True),
    ("EXAMPLE CITY HALL (synthetic)", 4, False), ("DEMO SCHOOL NO. 1", 2, False),
    ("EXAMPLE HOSPITAL (synthetic)", 4, False), ("TECHNO SERVICE DEMO SRL", 2, True),
    ("AGRO WEST SAMPLE SRL", 2, True), ("CREATIVE MEDIA DEMO SRL", 2, True), ("RAPID TRANSPORT EXAMPLE SRL", 2, False),
]
UTILITY_CATALOG = [("Demo Energy SA", 90, 320), ("Example Water SA", 40, 140), ("Sample Gas SA", 60, 450),
                   ("Internet Demo SRL", 45, 85), ("Demo Homeowners Association", 150, 420)]
PENSION_PAYER = "Pension Fund (synthetic)"
TAX_OFFICE = "Demo Treasury (synthetic)"
SEGMENTS = [("salariat", 0.62), ("pensionar", 0.16), ("student", 0.10), ("liber_profesionist", 0.12)]


# ---------------------------------------------------------------- utilitare


def weighted_choice(rng: random.Random, items: list[tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    x = rng.random() * total
    for item, w in items:
        x -= w
        if x <= 0:
            return item
    return items[-1][0]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def log_uniform(rng: random.Random, lo: float, hi: float) -> float:
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def at(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=TZ)


def rand_time(rng: random.Random, day: date, lo_h: int = 7, hi_h: int = 22) -> datetime:
    h = rng.randint(lo_h, hi_h)
    return at(day, h, rng.randint(0, 59), rng.randint(0, 59))


def money(x: float) -> float:
    return round(float(x), 2)


class IdGen:
    """Identificatori secvențiali, deterministici, cu prefix pe sursă (ex. TX-000001, TX-SC01-000001)."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.counters: dict[str, int] = defaultdict(int)

    def __call__(self, kind: str, width: int = 6) -> str:
        self.counters[kind] += 1
        return f"{kind}-{self.prefix}{self.counters[kind]:0{width}d}"


def new_fake(*key: object) -> Faker:
    fake = Faker("ro_RO")
    fake.seed_instance(ids.stable_int(*key, bits=32))
    return fake


def person_name(fake: Faker, rng: random.Random, sex: str | None = None) -> tuple[str, str, str]:
    sex = sex or rng.choice("MF")
    first = normalize_ro(fake.first_name_male() if sex == "M" else fake.first_name_female())
    last = normalize_ro(fake.last_name())
    return first, last, sex


# ---------------------------------------------------------------- lumea


@dataclass
class World:
    """Lumea sintetică. Toate listele conțin dict-uri JSON-serializabile (momente ISO 8601 cu offset)."""

    seed: int
    now: datetime
    customers: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    devices: list[dict] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)
    auth_events: list[dict] = field(default_factory=list)
    card_transactions: list[dict] = field(default_factory=list)
    transfers: list[dict] = field(default_factory=list)
    merchants: list[dict] = field(default_factory=list)
    companies: list[dict] = field(default_factory=list)
    domains: list[dict] = field(default_factory=list)
    phones: list[dict] = field(default_factory=list)
    sim_events: list[dict] = field(default_factory=list)
    prior_disputes: list[dict] = field(default_factory=list)
    complaints: list[dict] = field(default_factory=list)
    payees: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)
    # zona AML
    aml_accounts: list[dict] = field(default_factory=list)
    flows: list[dict] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    labels: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def transactions(self) -> list[dict]:
        return sorted(self.card_transactions + self.transfers, key=lambda t: (t["ts"], t["tx_id"]))

    def mules(self) -> list[str]:
        return [lab["id"] for lab in self.labels if lab["entity"] == "account" and lab["label"] == "mule"]


# ---------------------------------------------------------------- cataloage deterministe pe seed


@lru_cache(maxsize=8)
def static_catalogs(seed: int = 7) -> dict:
    """Comercianți, angajatori, utilități, registrul sintetic de firme, domenii și telefoane.

    Depinde doar de seed, ca scenariile să poată folosi aceiași comercianți fără să genereze toată lumea.
    """
    rng = ids.sub_rng("catalogs", seed)
    companies: list[dict] = []

    def company(name: str, role: str, bank: str | None, caen: str, year: int | None = None,
                status: str = "activă", cui: str | None = None, iban: str | None = None) -> dict:
        yr = year or rng.randint(1998, 2024)
        c = {"cui": cui or ids.generate_invalid_cui(rng, rng.choice([7, 8])), "name": name,
             "onrc": ids.generate_onrc(rng, yr), "registered_at": f"{yr}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
             "status": status, "caen": caen, "city": weighted_choice(rng, CITIES),
             "iban": iban or (ids.generate_iban(rng, bank) if bank else None), "role": role,
             "cui_checksum_valid": False, "synthetic": True}
        companies.append(c)
        return c

    merchants = []
    for i, (name, mcc, ptype, channel, lo, hi, country, weight, domain) in enumerate(MERCHANT_CATALOG, 1):
        bank = ids.OWN_BANK if (country == "RO" and rng.random() < 0.35) else rng.choice(ids.OTHER_BANKS)
        if country != "RO":
            bank = rng.choice(ids.OTHER_BANKS)
        c = company(name if "SRL" in name or "SA" in name else f"{name.upper()} SRL", "comerciant", bank,
                    {"5411": "4711", "5541": "4730", "5912": "4773", "5812": "5610", "5814": "5630"}.get(mcc, "4791"))
        merchants.append({
            "merchant_id": f"M-SYN-{i:04d}", "name": name, "mcc": mcc, "purchase_type": ptype, "channel": channel,
            "amount_lo": lo, "amount_hi": hi, "country": country, "eea": country in EEA, "weight": weight,
            "domain": domain, "cui": c["cui"], "settlement_iban": c["iban"], "city": c["city"], "synthetic": True})
    atm_own = {"merchant_id": "M-SYN-ATM1", "name": "Demo Bank ATM", "mcc": "6011", "purchase_type": "atm_cash",
               "channel": "atm", "amount_lo": 50, "amount_hi": 2000, "country": "RO", "eea": True, "weight": 0,
               "domain": None, "cui": None, "settlement_iban": art.CASH_NODE, "city": "București", "synthetic": True}
    atm_other = dict(atm_own, merchant_id="M-SYN-ATM2", name="Other bank ATM")
    merchants += [atm_own, atm_other]

    employers = []
    for name, weight, internal in EMPLOYER_CATALOG:
        bank = ids.OWN_BANK if internal else rng.choice(ids.OTHER_BANKS)
        c = company(name, "angajator", bank, rng.choice(["6201", "4941", "8610", "8411", "4120", "7311", "0111"]))
        employers.append({"name": name, "cui": c["cui"], "iban": c["iban"], "weight": weight, "internal": internal})
    utilities = []
    for name, lo, hi in UTILITY_CATALOG:
        c = company(name, "utilitate", rng.choice(ids.OTHER_BANKS), "3514")
        utilities.append({"name": name, "cui": c["cui"], "iban": c["iban"], "lo": lo, "hi": hi})
    pension = company(PENSION_PAYER, "instituție publică", "ZBNK", "8430")
    tax = company(TAX_OFFICE, "instituție publică", "ZBNK", "8411")
    shell = company(art.SHELL_COMPANY_NAME, "firmă_fantomă", "XBNK", "5320", year=2026, cui=art.SHELL_COMPANY_CUI)
    shell["onrc"] = art.SHELL_COMPANY_ONRC
    shell["registered_at"] = "2026-09-30"
    exchange = company(art.CRYPTO_EXCHANGE_NAME, "exchange", None, "6619", year=2021, cui=art.CRYPTO_EXCHANGE_CUI,
                       iban=art.CRYPTO_EXCHANGE_IBAN)
    # furnizori pentru micii comercianți și firme-client pentru liber-profesioniști și IMM-uri
    suppliers = [company(f"{w} {s} SRL", "furnizor", rng.choice(ids.OTHER_BANKS), "4690")
                 for w, s in [("WHOLESALE", "DEMO"), ("DISTRIB", "EXAMPLE"), ("GOODS", "SAMPLE"), ("PROD", "DEMO"),
                              ("EQUIPMENT", "EXAMPLE"), ("PACKAGING", "DEMO"), ("LOGISTICS", "SAMPLE"),
                              ("BUTCHERY", "EXAMPLE"), ("BAKERY", "DEMO"), ("TEXTILES", "SAMPLE")]]
    clients = [company(f"{w} {s}", "client corporativ", rng.choice(ids.OTHER_BANKS), "7022")
               for w, s in [("VECTOR", "CONSULTING DEMO SRL"), ("PRISMA", "IT EXAMPLE SRL"),
                            ("ATLAS", "IMPEX SAMPLE SRL"), ("ZENITH", "PROJECT DEMO SRL"),
                            ("ARCADIA", "SERVICES EXAMPLE SRL"), ("FOCUS", "MARKETING SAMPLE SRL"),
                            ("PLATFORM", "FREELANCE (synthetic) LTD"), ("CARPATHIA", "INDUSTRIAL DEMO SA"),
                            ("DANUBE", "TRADING EXAMPLE SRL"), ("MERIDIAN", "LOGISTICS SAMPLE SRL"),
                            ("SOLARIS", "ENERGY DEMO SRL"), ("HORIZON", "EVENTS EXAMPLE SRL")]]
    big_ticket = [company(n, "furnizor", rng.choice(ids.OTHER_BANKS), c)
                  for n, c in [("AUTO DEMO SRL", "4511"), ("RENOVATION EXAMPLE SRL", "4120"),
                               ("FURNITURE SAMPLE SRL", "4759"), ("DEMO UNIVERSITY (synthetic)", "8542"),
                               ("EXAMPLE DENTAL CLINIC SRL", "8623"), ("HOME APPLIANCES DEMO SRL", "4754")]]
    domains = _domains(rng)
    phones = [
        {"phone": art.SCAM_PHONE_SECURITATE, "kind": "scam_vishing", "label": "the \"security department\"",
         "scenario": "vishing_securitate", "first_seen": "2026-10-19", "synthetic": True},
        {"phone": art.SCAM_PHONE_CONT_SIGUR, "kind": "scam_cont_sigur", "label": "the \"safe account\"",
         "scenario": "cont_sigur", "first_seen": "2026-10-24", "synthetic": True},
        {"phone": art.BANK_OFFICIAL_PHONE, "kind": "bank_official", "label": "Demo Bank helpline",
         "scenario": None, "first_seen": "2019-01-01", "synthetic": True},
    ]
    return {"merchants": merchants, "employers": employers, "utilities": utilities, "companies": companies,
            "pension": pension, "tax": tax, "shell": shell, "exchange": exchange, "suppliers": suppliers,
            "clients": clients, "big_ticket": big_ticket, "domains": domains, "phones": phones}


def _domains(rng: random.Random) -> list[dict]:
    def d(domain, kind, registered_at, scenario=None, target=None):
        return {"domain": domain, "kind": kind, "registered_at": registered_at, "registrar": "Demo Registrar (synthetic)",
                "ip": ids.test_ip(rng, "attacker" if kind == "scam" else "home"), "target_brand": target,
                "scenario": scenario, "synthetic": True}
    return [
        d(art.LEGIT_BRAND_DOMAIN, "legit_brand", "2004-03-11T09:00:00+02:00"),
        d(art.LEGIT_COURIER_DOMAIN, "legit_courier", "2011-06-02T10:00:00+03:00"),
        d(art.SCAM_DOMAIN_DEMO, "scam", "2026-10-28T06:12:00+02:00", "demo_t1", art.LEGIT_BRAND_DOMAIN),
        d(art.SCAM_DOMAIN_CARD, "scam", "2026-10-21T22:40:00+03:00", "card_visa_secure", art.LEGIT_BRAND_DOMAIN),
        d(art.SCAM_DOMAIN_INEL, "scam", "2026-10-22T08:05:00+03:00", "inel_carausi", art.LEGIT_COURIER_DOMAIN),
        d(art.SCAM_DOMAIN_VISHING, "scam", "2026-10-26T19:30:00+02:00", "vishing_securitate", art.LEGIT_BRAND_DOMAIN),
    ]


# ---------------------------------------------------------------- clienți


def make_customer(rng: random.Random, fake: Faker, ref: str, alias: str, *, now: datetime, catalogs: dict,
                  segment: str | None = None, overrides: dict | None = None) -> dict:
    """Un client cu cont curent, card, dispozitive și profil de comportament (pentru `make_history`)."""
    overrides = overrides or {}
    segment = segment or weighted_choice(rng, SEGMENTS)
    first, last, sex = person_name(fake, rng, overrides.get("sex"))
    first, last = overrides.get("first_name", first), overrides.get("last_name", last)
    age = {"salariat": rng.randint(23, 62), "pensionar": rng.randint(63, 84), "student": rng.randint(19, 25),
           "liber_profesionist": rng.randint(26, 58)}[segment]
    birth = now.date() - timedelta(days=age * 365 + rng.randint(0, 364))
    cnp = ids.generate_cnp(birth, sex, rng.choice(ids.TEST_COUNTIES), rng.randint(1, 999))
    city = weighted_choice(rng, CITIES)
    adult_since = birth + timedelta(days=18 * 366)
    since_days = rng.randint(25, 100) if rng.random() < 0.1 else rng.randint(120, 5200)   # 10% clienți noi
    since = max(now.date() - timedelta(days=since_days), adult_since)
    since_dt = at(since, 10)
    phone = overrides.get("phone") or ids.fictive_phone(100000 + ids.stable_int(ref, "phone") % 899999)
    email = strip_diacritics(f"{first}.{last}".lower()).replace(" ", "").replace("'", "") + f"{rng.randint(1, 99)}@mail.example"
    customer = {
        "customer_ref": ref, "alias": alias, "first_name": first, "last_name": last, "full_name": f"{first} {last}",
        "cnp": cnp, "birth_date": birth.isoformat(), "sex": sex, "phone": phone, "email": email, "city": city,
        "address": f"{city}, {normalize_ro(fake.street_name())} nr. {rng.randint(1, 120)}",
        "segment": segment, "customer_since": since.isoformat(), "kyc_level": "standard", "synthetic": True,
    }
    acc_digits = "1" + f"{rng.randint(0, 999):03d}" + f"{ids.stable_int(ref, 'acct') % 10**12:012d}"
    iban = ids.make_iban(ids.OWN_BANK, acc_digits)
    accounts = [{"iban": iban, "customer_ref": ref, "type": "curent", "currency": "RON", "opened_at": iso(since_dt),
                 "opening_balance": 0.0, "balance": 0.0, "status": "activ", "primary": True, "synthetic": True}]
    if rng.random() < 0.3:
        sav = ids.make_iban(ids.OWN_BANK, "2" + acc_digits[1:])
        accounts.append({"iban": sav, "customer_ref": ref, "type": "economii", "currency": "RON",
                         "opened_at": iso(since_dt + timedelta(days=rng.randint(10, 400))),
                         "opening_balance": money(rng.uniform(500, 40000)), "balance": 0.0, "status": "activ",
                         "primary": False, "synthetic": True})
        accounts[-1]["balance"] = accounts[-1]["opening_balance"]
    scheme = "visa" if rng.random() < 0.7 else "mastercard"
    last4 = f"{rng.randint(0, 9999):04d}"
    issued = max(since, now.date() - timedelta(days=rng.randint(30, 1400)))
    cards = [{"card_id": f"CARD-{ids.stable_int(ref, 'card') % 10**8:08d}", "customer_ref": ref, "account_iban": iban,
              "pan_masked": f"************{last4}", "last4": last4, "scheme": scheme, "product": "debit",
              "status": "activ", "issued_at": issued.isoformat(),
              "expires": f"{(issued.month):02d}/{(issued.year + 4) % 100:02d}",
              "token": f"tok_card_{ids.hex_id(rng, 8)}", "synthetic": True}]
    home_ip, mobile_ip = ids.test_ip(rng, "home"), ids.test_ip(rng, "mobile")
    devices = []
    main_enrolled = since_dt + timedelta(days=rng.randint(0, max(1, (now - since_dt).days - 25)))
    main_enrolled = min(main_enrolled, now - timedelta(days=21))
    if rng.random() < 0.35:
        old_model = rng.choice(DEVICE_MODELS)
        old_at = main_enrolled - timedelta(days=rng.randint(200, 900))
        devices.append(_device(rng, ref, old_model, max(old_at, since_dt), home_ip, status="revocat",
                               via=rng.choice(["branch", "sms_otp"]), last_seen=main_enrolled))
    model = rng.choice(DEVICE_MODELS)
    devices.append(_device(rng, ref, model, main_enrolled, home_ip, status="activ",
                           via=rng.choice(["sms_otp", "app_push", "branch", "video_id"]), last_seen=now - timedelta(hours=rng.randint(1, 48))))
    income = {"salariat": rng.randrange(3200, 14000, 50), "pensionar": rng.randrange(1800, 4600, 50),
              "student": rng.randrange(600, 2000, 50), "liber_profesionist": rng.randrange(4000, 15000, 100)}[segment]
    employer = weighted_choice(rng, [(e, e["weight"]) for e in catalogs["employers"]]) if segment == "salariat" else None
    shop_merchants = [m for m in catalogs["merchants"] if m["weight"] > 0]
    favorites = rng.sample([m["merchant_id"] for m in shop_merchants if m["channel"] in ("pos", "both")], 5)
    profile = {
        "segment": segment, "income": income, "employer": employer, "home_ip": home_ip, "mobile_ip": mobile_ip,
        "pay_day": rng.choice([5, 10, 10, 15, 15, 25]), "favorites": favorites,
        "pos_rate": {"salariat": 0.55, "pensionar": 0.3, "student": 0.45, "liber_profesionist": 0.5}[segment],
        "ecom_rate": {"salariat": 0.08, "pensionar": 0.015, "student": 0.1, "liber_profesionist": 0.12}[segment],
        "atm_per_month": {"salariat": 2, "pensionar": 3.2, "student": 1.5, "liber_profesionist": 1.2}[segment],
        "p2p_per_month": rng.choice([0, 1, 1, 2, 2, 3, 4]), "utilities": rng.sample(range(len(catalogs["utilities"])), rng.randint(2, 4)),
        "rent": rng.random() < (0.25 if segment in ("salariat", "liber_profesionist") else 0.05),
        "crypto": rng.random() < 0.10, "night_owl": rng.random() < 0.08,
        # își mută salariul în contul propriu de la altă bancă, în aceeași zi (tranzit rapid legitim)
        "forwarder": segment == "salariat" and rng.random() < 0.18,
        # evenimente mari și legitime: bani primiți de la familie / o vânzare, cheltuiți în câteva zile
        "big_events": rng.random() < 0.35,
        "friends": [],
    }
    profile.update(overrides.get("profile", {}))
    return {"customer": customer, "accounts": accounts, "cards": cards, "devices": devices, "profile": profile}


def _device(rng: random.Random, ref: str, model: tuple[str, str], enrolled: datetime, ip: str, *, status: str,
            via: str, last_seen: datetime, session_id: str | None = None, trusted: bool = True) -> dict:
    return {"device_id": f"dev-SYN-{ids.hex_id(rng, 16)}", "customer_ref": ref, "fingerprint": ids.hex_id(rng, 32),
            "model": model[0], "os": model[1], "app_version": f"7.{rng.randint(2, 9)}.{rng.randint(0, 20)}",
            "enrolled_at": iso(enrolled), "enrolled_via": via, "enrollment_session_id": session_id,
            "last_seen_at": iso(last_seen), "status": status, "first_ip": ip, "trusted": trusted, "synthetic": True}


def active_device(cb: dict) -> dict:
    return [d for d in cb["devices"] if d["status"] == "activ"][-1]


# ---------------------------------------------------------------- istoric


def tx_record(idg: IdGen, cb: dict, direction: str, kind: str, channel: str, amount: float, ts: datetime,
              description: str, **extra: Any) -> dict:
    acc = cb["accounts"][0]
    t = {"tx_id": extra.pop("tx_id", None) or idg("TX"), "customer_ref": cb["customer"]["customer_ref"],
         "account_iban": acc["iban"], "direction": direction, "kind": kind, "channel": channel,
         "amount": money(amount), "currency": "RON", "ts": iso(ts), "booked_at": iso(ts),
         "description": description, "counterparty_name": None, "counterparty_iban": None, "merchant_id": None,
         "mcc": None, "card_id": None, "pos_entry_mode": None, "eci": None, "cavv_present": None,
         "merchant_country": None, "device_id": None, "session_id": None, "ip": None, "status": "booked",
         "end_to_end_id": None, "disputable": direction == "debit", "case_tag": None,
         "synthetic": True, "_dt": ts, "_optional": True}
    t.update(extra)
    return t


def make_session(idg: IdGen, cb: dict, device: dict, ip: str, started: datetime, ended: datetime, *,
                 clicked_url: str | None = None, clicked_at: datetime | None = None, channel: str = "app",
                 session_id: str | None = None) -> dict:
    return {"session_id": session_id or idg("SES"), "customer_ref": cb["customer"]["customer_ref"],
            "device_id": device["device_id"], "ip": ip, "channel": channel, "started_at": iso(started),
            "ended_at": iso(ended), "user_agent": f"DemoBank/{device['app_version']} ({device['os']}; {device['model']})",
            "clicked_url": clicked_url, "clicked_at": iso(clicked_at), "referrer": None,
            "geo": "RO", "synthetic": True}


def make_auth(idg: IdGen, cb: dict, *, ts: datetime, method: str, purpose: str, device: dict | None,
              tx_id: str | None = None, session_id: str | None = None, shown: bool = False,
              shown_amount: float | None = None, shown_payee: str | None = None, otp_text: str | None = None,
              eci: str | None = None, cavv: str | None = None, ip: str | None = None, result: str = "approved",
              auth_id: str | None = None) -> dict:
    return {"auth_id": auth_id or idg("AUTH"), "customer_ref": cb["customer"]["customer_ref"], "tx_id": tx_id,
            "session_id": session_id, "device_id": device["device_id"] if device else None, "ts": iso(ts),
            "method": method, "purpose": purpose, "result": result,
            "screen_showed_amount_and_payee": bool(shown), "shown_amount": shown_amount if shown else None,
            "shown_payee": shown_payee if shown else None, "otp_text": otp_text,
            "phone": cb["customer"]["phone"] if method == "sms_otp" else None,
            "eci": eci, "cavv": cavv, "cavv_present": (cavv is not None) if eci else None,
            "three_ds_version": "2.2.0" if eci == "05" else None, "flow_version": FLOW_VERSION, "ip": ip,
            "synthetic": True}


def fake_cavv(rng: random.Random) -> str:
    return "AAAB" + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(23)) + "="


def make_history(rng: random.Random, cb: dict, *, start: datetime, end: datetime, catalogs: dict,
                 idg: IdGen) -> dict:
    """Istoric de comportament normal: venituri, plăți cu cardul, ATM, utilități, transferuri P2P, chirie.

    Transferurile primite de la prieteni interni se adaugă la nivelul lumii (`generate_world`), ca să apară
    la ambii clienți. Întoarce dict cu transactions, sessions, auth_events, payees.
    """
    prof, cust = cb["profile"], cb["customer"]
    dev = active_device(cb)
    card = cb["cards"][0]
    merchants = catalogs["merchants"]
    by_id = {m["merchant_id"]: m for m in merchants}
    pos_pool = [(m, m["weight"]) for m in merchants if m["channel"] in ("pos", "both") and m["weight"] > 0]
    ecom_pool = [(m, m["weight"]) for m in merchants if m["channel"] in ("ecommerce", "both") and m["weight"] > 0]
    txs: list[dict] = []
    sessions: list[dict] = []
    auths: list[dict] = []
    payees: dict[str, dict] = {}
    seg = prof["segment"]
    start = max(start, datetime.fromisoformat(cb["accounts"][0]["opened_at"]))

    def transfer_out(ts: datetime, iban: str, name: str, amount: float, desc: str, *, instant: bool = False,
                     kind: str = "transfer") -> dict:
        ip = prof["home_ip"] if rng.random() < 0.6 else prof["mobile_ip"]
        ses = make_session(idg, cb, dev, ip, ts - timedelta(minutes=rng.randint(1, 6)), ts + timedelta(minutes=rng.randint(1, 4)))
        sessions.append(ses)
        t = tx_record(idg, cb, "debit", kind, "transfer_instant" if instant else "transfer", amount, ts, desc,
                      counterparty_name=name, counterparty_iban=iban, device_id=dev["device_id"],
                      session_id=ses["session_id"], ip=ip, end_to_end_id=f"E2E{ids.hex_id(rng, 12).upper()}")
        auths.append(make_auth(idg, cb, ts=ts - timedelta(seconds=rng.randint(8, 50)), method="app_push",
                               purpose="payment", device=dev, tx_id=t["tx_id"], session_id=ses["session_id"],
                               shown=True, shown_amount=t["amount"], shown_payee=name, ip=ip))
        p = payees.get(iban)
        if p is None:
            payees[iban] = {"customer_ref": cust["customer_ref"], "iban": iban, "name": name, "created_at": iso(ts),
                            "last_used_at": iso(ts), "uses": 1, "synthetic": True}
        else:
            p["last_used_at"], p["uses"] = iso(ts), p["uses"] + 1
        txs.append(t)
        return t

    # ---------------- venituri lunare
    day = start.date()
    months: list[tuple[int, int]] = []
    while day <= end.date():
        if (day.year, day.month) not in months:
            months.append((day.year, day.month))
        day += timedelta(days=1)
    for (y, m) in months:
        pay = date(y, m, min(prof["pay_day"], 28))
        while pay.weekday() >= 5:
            pay -= timedelta(days=1)
        ts = at(pay, rng.randint(6, 11), rng.randint(0, 59))
        if not (start <= ts < end):
            continue
        month = MONTHS[m - 1]
        if seg == "salariat" and prof.get("employer"):
            e = prof["employer"]
            amt = prof["income"] * rng.uniform(0.97, 1.03)
            txs.append(tx_record(idg, cb, "credit", "salary", "transfer", amt, ts, f"Salary {month} {y} - {e['name']}",
                                 counterparty_name=e["name"], counterparty_iban=e["iban"], disputable=False))
            if prof.get("forwarder"):
                own = prof.setdefault("own_external", ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS)))
                tf = ts + timedelta(hours=rng.uniform(0.5, 6))
                if tf < end:
                    transfer_out(tf, own, cust["full_name"], amt * rng.uniform(0.6, 0.9), "Transfer between own accounts",
                                 instant=rng.random() < 0.5)
                    txs[-1]["_optional"] = False
        elif seg == "pensionar":
            p = catalogs["pension"]
            txs.append(tx_record(idg, cb, "credit", "pension", "transfer", prof["income"], ts,
                                 f"Pension {month} {y}", counterparty_name=p["name"], counterparty_iban=p["iban"],
                                 disputable=False))
        elif seg == "student" and not prof.get("no_allowance"):
            fam = prof.get("family") or {"name": "Family (external)", "iban": ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS))}
            prof["family"] = fam
            txs.append(tx_record(idg, cb, "credit", "p2p_in", "transfer", prof["income"] * rng.uniform(0.9, 1.1), ts,
                                 f"Transfer from {fam['name']}", counterparty_name=fam["name"],
                                 counterparty_iban=fam["iban"], disputable=False))
        elif seg == "liber_profesionist":
            for _ in range(rng.randint(1, 3)):
                cl = rng.choice(catalogs["clients"])
                d2 = date(y, m, rng.randint(1, 28))
                ts2 = at(d2, rng.randint(9, 16), rng.randint(0, 59))
                if start <= ts2 < end:
                    txs.append(tx_record(idg, cb, "credit", "invoice", "transfer",
                                         prof["income"] / 2 * rng.uniform(0.5, 1.6), ts2,
                                         f"Invoice payment - {cl['name']}", counterparty_name=cl["name"],
                                         counterparty_iban=cl["iban"], disputable=False))
        # utilities (direct debit, no session)
        for ui in prof["utilities"]:
            u = catalogs["utilities"][ui]
            du = date(y, m, 18 + ui)
            tsu = at(du, 3, rng.randint(0, 59))
            if start <= tsu < end:
                txs.append(tx_record(idg, cb, "debit", "utility", "transfer", rng.uniform(u["lo"], u["hi"]), tsu,
                                     f"Direct debit {u['name']}", counterparty_name=u["name"],
                                     counterparty_iban=u["iban"], _optional=False))
        if prof["rent"]:
            landlord = prof.setdefault("landlord", {"name": "Landlord (external)",
                                                    "iban": ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS)),
                                                    "amount": rng.randrange(1200, 3200, 50)})
            dr = date(y, m, 2)
            tsr = rand_time(rng, dr, 9, 20)
            if start <= tsr < end:
                transfer_out(tsr, landlord["iban"], landlord["name"], landlord["amount"], f"Rent {month}")
                txs[-1]["_optional"] = False

    # ---------------- evenimente mari, legitime (intrare mare urmată de o plată mare)
    if prof.get("big_events") and (end - start).days > 10:
        for _ in range(rng.randint(1, 2)):
            ts = start + timedelta(seconds=rng.uniform(0, (end - start).total_seconds() - 6 * 86400))
            ts = rand_time(rng, ts.date(), 9, 19)
            src = rng.choice([f for f in prof["friends"] if not f.get("internal_ref")] or
                             [{"name": "Family (external)", "iban": ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS))}])
            amt = log_uniform(rng, 1500, 9000)
            txs.append(tx_record(idg, cb, "credit", "p2p_in", rng.choice(["transfer", "transfer_instant"]), amt, ts,
                                 f"Transfer from {src['name']}", counterparty_name=src["name"],
                                 counterparty_iban=src["iban"], disputable=False))
            co = rng.choice(catalogs["big_ticket"])
            t2 = ts + timedelta(hours=rng.uniform(4, 120))
            if t2 < end:
                transfer_out(t2, co["iban"], co["name"], amt * rng.uniform(0.7, 1.0), f"Payment to {co['name']}",
                             instant=rng.random() < 0.3)
                txs[-1]["_optional"] = False

    # ---------------- zilnic: card, ATM, P2P
    day = start.date()
    while day <= end.date():
        lo_h, hi_h = (0, 23) if prof["night_owl"] else (7, 22)
        for _ in range(poisson(rng, prof["pos_rate"])):
            m = by_id[rng.choice(prof["favorites"])] if rng.random() < 0.7 else weighted_choice(rng, pos_pool)
            ts = rand_time(rng, day, lo_h, hi_h)
            if not (start <= ts < end):
                continue
            amt = log_uniform(rng, m["amount_lo"], m["amount_hi"])
            txs.append(tx_record(idg, cb, "debit", "card_pos", "card", amt, ts, f"POS {m['name']}",
                                 counterparty_name=m["name"], counterparty_iban=m["settlement_iban"],
                                 merchant_id=m["merchant_id"], mcc=m["mcc"], card_id=card["card_id"],
                                 pos_entry_mode=rng.choice(["contactless", "contactless", "chip"]),
                                 merchant_country=m["country"]))
        for _ in range(poisson(rng, prof["ecom_rate"])):
            m = weighted_choice(rng, ecom_pool)
            ts = rand_time(rng, day, 0 if prof["night_owl"] else 8, 23)
            if not (start <= ts < end):
                continue
            amt = log_uniform(rng, m["amount_lo"], min(m["amount_hi"], 1800 if seg != "salariat" else m["amount_hi"]))
            three_ds = m["eea"] or rng.random() < 0.2
            eci, cavv = ("05", fake_cavv(rng)) if three_ds else ("07", None)
            t = tx_record(idg, cb, "debit", "card_ecom", "card", amt, ts, f"Online payment {m['name']}",
                          counterparty_name=m["name"], counterparty_iban=m["settlement_iban"],
                          merchant_id=m["merchant_id"], mcc=m["mcc"], card_id=card["card_id"],
                          pos_entry_mode="ecommerce", eci=eci, cavv_present=cavv is not None,
                          merchant_country=m["country"], ip=prof["home_ip"])
            txs.append(t)
            if three_ds:
                auths.append(make_auth(idg, cb, ts=ts - timedelta(seconds=rng.randint(10, 70)), method="app_push",
                                       purpose="payment", device=dev, tx_id=t["tx_id"], shown=True,
                                       shown_amount=t["amount"], shown_payee=m["name"], eci="05", cavv=cavv,
                                       ip=prof["home_ip"]))
        if rng.random() < prof["atm_per_month"] / 30:
            ts = rand_time(rng, day, 8, 21)
            if start <= ts < end:
                atm = by_id["M-SYN-ATM1"] if rng.random() < 0.7 else by_id["M-SYN-ATM2"]
                amt = rng.choice([100, 200, 200, 300, 400, 500, 500, 1000])
                where = "Demo Bank" if atm["merchant_id"] == "M-SYN-ATM1" else "other bank"
                txs.append(tx_record(idg, cb, "debit", "card_atm", "card", amt, ts, f"ATM withdrawal, {where}",
                                     counterparty_name=atm["name"], counterparty_iban=art.CASH_NODE,
                                     merchant_id=atm["merchant_id"], mcc="6011", card_id=card["card_id"],
                                     pos_entry_mode="atm", merchant_country="RO"))
        if rng.random() < 0.4 / 30:   # bani primiți de la un prieten de la altă bancă
            ext = [f for f in prof["friends"] if not f.get("internal_ref")]
            if ext:
                fr = rng.choice(ext)
                ts = rand_time(rng, day, 9, 22)
                if start <= ts < end:
                    txs.append(tx_record(idg, cb, "credit", "p2p_in", "transfer", log_uniform(rng, 40, 700), ts,
                                         f"Transfer from {fr['name']}", counterparty_name=fr["name"],
                                         counterparty_iban=fr["iban"], disputable=False))
        if rng.random() < 0.15 / 30:  # retur de la un comerciant (credit pe card)
            m = weighted_choice(rng, ecom_pool)
            ts = rand_time(rng, day, 9, 20)
            if start <= ts < end:
                txs.append(tx_record(idg, cb, "credit", "card_refund", "card", log_uniform(rng, 20, 400), ts,
                                     f"Refund from {m['name']}", counterparty_name=m["name"], counterparty_iban=m["settlement_iban"],
                                     merchant_id=m["merchant_id"], mcc=m["mcc"], card_id=card["card_id"], disputable=False))
        if prof["friends"] and rng.random() < prof["p2p_per_month"] / 30:
            fr = rng.choice(prof["friends"])
            ts = rand_time(rng, day, 9, 22)
            if start <= ts < end:
                t = transfer_out(ts, fr["iban"], fr["name"], log_uniform(rng, 40, 900), f"Transfer to {fr['name']}",
                                 instant=rng.random() < 0.35, kind="transfer")
                t["_friend"] = fr
        if prof.get("crypto") and rng.random() < 2.5 / 30:
            ts = rand_time(rng, day, 9, 23)
            if start <= ts < end:
                transfer_out(ts, art.CRYPTO_EXCHANGE_IBAN, art.CRYPTO_EXCHANGE_NAME, log_uniform(rng, 100, 3000),
                             "CryptoX account top-up", instant=True)
        day += timedelta(days=1)
    return {"transactions": txs, "sessions": sessions, "auth_events": auths, "payees": list(payees.values())}


def finalize_balances(cb: dict, txs: list[dict], *, rng: random.Random, target_balance: float | None = None) -> list[dict]:
    """Sortează tranzacțiile contului principal, elimină cheltuielile opționale care ar intra în descoperit
    și fixează soldul de deschidere (sau soldul final țintă, la clienții demo). Întoarce tranzacțiile păstrate."""
    acc = cb["accounts"][0]
    txs.sort(key=lambda t: (t["_dt"], t["tx_id"]))
    dropped: set[str] = set()
    opening = money(rng.uniform(600, 9000)) if target_balance is None else 0.0
    for _ in range(200):
        kept = [t for t in txs if t["tx_id"] not in dropped]
        net = sum(t["amount"] if t["direction"] == "credit" else -t["amount"] for t in kept)
        if target_balance is not None:
            opening = money(target_balance - net)
        run, worst = opening, None
        for t in kept:
            run += t["amount"] if t["direction"] == "credit" else -t["amount"]
            if run < -0.005 and worst is None:
                worst = t
        if worst is None and opening >= 0:
            break
        # eliminăm cea mai mare cheltuială opțională de până la momentul problemei
        upto = [t for t in kept if t["direction"] == "debit" and t.get("_optional", True)
                and (worst is None or (t["_dt"], t["tx_id"]) <= (worst["_dt"], worst["tx_id"]))]
        if not upto:
            if target_balance is None:
                opening += 1000.0
                continue
            break
        dropped.add(max(upto, key=lambda t: t["amount"])["tx_id"])
    kept = [t for t in txs if t["tx_id"] not in dropped]
    run = opening
    for t in kept:
        run = money(run + (t["amount"] if t["direction"] == "credit" else -t["amount"]))
        t["balance_after"] = run
    acc["opening_balance"] = money(opening)
    acc["balance"] = money(run)
    return kept


def strip_private(rows: list[dict]) -> list[dict]:
    for r in rows:
        for k in [k for k in r if k.startswith("_")]:
            del r[k]
    return rows


# ---------------------------------------------------------------- oglinda în zona AML


def client_tx_to_flows(txs: list[dict], idg: IdGen) -> list[dict]:
    """Fiecare tranzacție a unui cont intern devine un flux în zona AML (fluxul de la core banking).

    Fluxurile nu poartă nume de persoane, doar IBAN-uri și o referință neutră.
    """
    flows = []
    for t in txs:
        if t["kind"] in ("refund",) or not t.get("counterparty_iban"):
            continue
        own, other = t["account_iban"], t["counterparty_iban"]
        frm, to = (own, other) if t["direction"] == "debit" else (other, own)
        if t["channel"] == "card":
            channel = "atm" if t["kind"] == "card_atm" else "card"
        elif t["kind"] in ("salary", "pension"):
            channel = t["kind"]
        elif t["kind"] == "utility":
            channel = "direct_debit"
        else:
            channel = t["channel"]
        reference = {"card": "Card payment", "atm": "Cash withdrawal", "salary": "Salary", "pension": "Pension",
                     "direct_debit": "Direct debit"}.get(channel, "Transfer")
        flows.append({"flow_id": idg("FL", 7), "ts": t["ts"], "from_iban": frm, "to_iban": to, "amount": t["amount"],
                      "currency": "RON", "channel": channel, "reference": reference, "reported_fraud": 0,
                      "report_source": None, "case_id": None, "feed": "core_feed", "synthetic": True,
                      "_client_tx_id": t["tx_id"]})
    return flows


# ---------------------------------------------------------------- istoric de dispute (zona client)

DISPUTE_TEMPLATES = [
    ("card", "neautorizata", "card_ecom_fara_3ds", "does not recognize the online payment", "rambursat"),
    ("card", "disputa_comerciant", "marfa_nelivrata", "goods not delivered", "chargeback_castigat"),
    ("card", "eroare_procesare", "plata_dubla", "charged twice", "corectat"),
    ("transfer", "neautorizata", "phishing_link", "transfer after a fake link", "rambursat"),
    ("card", "neautorizata", "frauda_client", "does not recognize the transaction", "respins_dovezi_livrare"),
]


def make_prior_disputes(rng: random.Random, idg: IdGen, cb: dict, *, now: datetime, n: int,
                        merchants: list[dict], serial: bool = False) -> list[dict]:
    out = []
    for _ in range(n):
        if serial:
            ch, dt, sc, reason, outcome = rng.choice([DISPUTE_TEMPLATES[0], DISPUTE_TEMPLATES[1], DISPUTE_TEMPLATES[4]])
        else:
            ch, dt, sc, reason, outcome = weighted_choice(rng, [(DISPUTE_TEMPLATES[0], 4), (DISPUTE_TEMPLATES[1], 3),
                                                                 (DISPUTE_TEMPLATES[2], 2), (DISPUTE_TEMPLATES[3], 1)])
        opened = now - timedelta(days=rng.randint(15, 355), hours=rng.randint(0, 23))
        m = rng.choice([x for x in merchants if x["channel"] in ("ecommerce", "both")])
        out.append({"dispute_id": idg("PD", 5), "customer_ref": cb["customer"]["customer_ref"],
                    "case_id": f"CT-2025-{ids.stable_int(cb['customer']['customer_ref'], opened.isoformat()) % 10**6:06d}",
                    "tx_ref": f"TX-ARH-{ids.hex_id(rng, 8).upper()}", "opened_at": iso(opened),
                    "closed_at": iso(opened + timedelta(days=rng.randint(2, 40))), "channel": ch, "dispute_type": dt,
                    "scenario": sc, "amount": money(log_uniform(rng, 60, 2500)), "counterparty": m["name"],
                    "outcome": outcome, "reason": reason, "synthetic": True})
    return out


# ---------------------------------------------------------------- generatorul


def generate_world(seed: int = 7, n_customers: int = 400) -> World:
    """Generează lumea Băncii Demo (zona client + zona AML), deterministă pentru un seed dat."""
    from versoml.data import aml_world, complaints as complaint_gen

    now = WORLD_NOW
    start = now - timedelta(days=HISTORY_DAYS)
    rng = ids.sub_rng("world", seed)
    fake = new_fake("world-customers", seed)
    cat = static_catalogs(seed)
    idg = IdGen("")
    world = World(seed=seed, now=now)
    world.merchants = [dict(m) for m in cat["merchants"]]
    world.companies = [dict(c) for c in cat["companies"]]
    world.domains = [dict(d) for d in cat["domains"]]
    world.phones = [dict(p) for p in cat["phones"]]

    # ---------------- clienți
    cbs = []
    for i in range(1, n_customers + 1):
        ref = f"CUST-{i:04d}"
        cbs.append(make_customer(rng, fake, ref, f"Customer {i:04d}", now=now, catalogs=cat))
    ext_fake = new_fake("world-external-persons", seed)
    for cb in cbs:
        nf = rng.randint(1, 4)
        for _ in range(nf):
            if rng.random() < 0.45:
                other = rng.choice(cbs)
                if other is cb:
                    continue
                cb["profile"]["friends"].append({"name": other["customer"]["full_name"], "iban": other["accounts"][0]["iban"],
                                                 "internal_ref": other["customer"]["customer_ref"]})
            else:
                f, l, _ = person_name(ext_fake, rng)
                cb["profile"]["friends"].append({"name": f"{f} {l}", "iban": ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS)),
                                                 "internal_ref": None})
        if cb["profile"]["segment"] == "student":
            f, l, _ = person_name(ext_fake, rng)
            cb["profile"]["family"] = {"name": f"{f} {cb['customer']['last_name']}",
                                       "iban": ids.generate_iban(rng, rng.choice(ids.OTHER_BANKS))}

    # ---------------- istoric
    hist: dict[str, dict] = {}
    for cb in cbs:
        hist[cb["customer"]["customer_ref"]] = make_history(rng, cb, start=start, end=now, catalogs=cat, idg=idg)
    by_ref = {cb["customer"]["customer_ref"]: cb for cb in cbs}
    # transferurile între clienți interni apar și la destinatar
    for ref, h in hist.items():
        for t in list(h["transactions"]):
            fr = t.pop("_friend", None)
            if fr and fr.get("internal_ref") and fr["internal_ref"] in by_ref:
                dest = by_ref[fr["internal_ref"]]
                src = by_ref[ref]["customer"]
                hist[fr["internal_ref"]]["transactions"].append(tx_record(
                    idg, dest, "credit", "p2p_in", t["channel"], t["amount"], t["_dt"],
                    f"Transfer from {src['full_name']}", counterparty_name=src["full_name"],
                    counterparty_iban=t["account_iban"], disputable=False, end_to_end_id=t["end_to_end_id"]))

    # ---------------- lumea AML (populații suplimentare, cărăuși, victime interne)
    aml = aml_world.generate_aml_world(seed=seed, now=now, cbs=cbs, catalogs=cat, idg=idg)
    for ref, extra in aml["extra_client_tx"].items():
        hist[ref]["transactions"].extend(extra)
    for ref, extra in aml["extra_sessions"].items():
        hist[ref]["sessions"].extend(extra)
    for ref, extra in aml["extra_auth"].items():
        hist[ref]["auth_events"].extend(extra)

    # ---------------- solduri, dispute anterioare, SIM, notificări
    prior: list[dict] = []
    for cb in cbs:
        ref = cb["customer"]["customer_ref"]
        kept = finalize_balances(cb, hist[ref]["transactions"], rng=rng)
        hist[ref]["transactions"] = kept
        kept_ids = {t["tx_id"] for t in kept}
        hist[ref]["auth_events"] = [a for a in hist[ref]["auth_events"] if a["tx_id"] is None or a["tx_id"] in kept_ids]
        r = rng.random()
        n_prior = 0 if r < 0.84 else 1 if r < 0.95 else 2 if r < 0.985 else rng.randint(3, 5)
        prior += make_prior_disputes(rng, idg, cb, now=now, n=n_prior, merchants=cat["merchants"], serial=n_prior >= 3)
        if rng.random() < 0.03:   # înlocuire legitimă de SIM (telefon nou), fără fraudă
            world.sim_events.append({"event_id": idg("SIM", 5), "customer_ref": ref, "phone": cb["customer"]["phone"],
                                     "ts": iso(now - timedelta(days=rng.randint(5, 100), hours=rng.randint(0, 12))),
                                     "kind": "sim_swap", "operator": "Demo Mobile Operator",
                                     "channel": rng.choice(["store", "online"]), "synthetic": True})
    prior += aml["extra_prior_disputes"]
    world.prior_disputes = prior

    # reclamațiile istorice (închise) aferente disputelor anterioare
    world.complaints = complaint_gen.historical_complaints(prior, by_ref, seed=seed)

    for cb in cbs:
        ref = cb["customer"]["customer_ref"]
        world.customers.append(cb["customer"])
        world.accounts += cb["accounts"]
        world.cards += cb["cards"]
        world.devices += cb["devices"]
        h = hist[ref]
        world.sessions += h["sessions"]
        world.auth_events += h["auth_events"]
        world.payees += h["payees"]
        for t in h["transactions"]:
            (world.card_transactions if t["channel"] == "card" else world.transfers).append(t)
        for t in h["transactions"][-200:]:
            if t["_dt"] >= now - timedelta(days=10):
                verb = "You paid" if t["direction"] == "debit" else "You received"
                world.notifications.append({"notification_id": idg("NTF", 6), "customer_ref": ref, "ts": t["ts"],
                                            "kind": "tranzactie", "text": f"{verb} {fmt_ron(t['amount'])}: {t['description']}",
                                            "read": True, "synthetic": True})

    # ---------------- fluxuri AML: oglinda tranzacțiilor clienților + populațiile suplimentare
    fl_idg = IdGen("")
    mirrored = client_tx_to_flows(sorted(world.card_transactions + world.transfers, key=lambda t: (t["_dt"], t["tx_id"])), fl_idg)
    report_by_tx = aml["reported_client_tx"]
    tx_to_flow: dict[str, str] = {}
    for f in mirrored:
        tx_to_flow[f["_client_tx_id"]] = f["flow_id"]
        rep = report_by_tx.get(f["_client_tx_id"])
        if rep:
            f["reported_fraud"], f["report_source"] = 1, rep
    extra_flows = aml["flows"]
    for p in aml["patterns"]:
        p["flow_ids"] = p["flow_ids"] + [tx_to_flow[t] for t in p.pop("client_tx_ids", []) if t in tx_to_flow]
    world.flows = sorted(strip_private(mirrored + extra_flows), key=lambda f: (f["ts"], f["flow_id"]))
    world.companies += aml["companies"]
    world.aml_accounts = aml_world.build_aml_accounts(cbs, aml["accounts"], cat, world.flows, now=now)
    world.patterns = aml["patterns"]
    world.labels = aml_world.build_labels(world.aml_accounts, aml["patterns"], aml["segments"], layer2=aml["layer2"])
    world.alerts = aml_world.compute_alerts(world.aml_accounts, world.flows, now=now)

    for rows in (world.card_transactions, world.transfers):
        strip_private(rows)
    world.card_transactions.sort(key=lambda t: (t["ts"], t["tx_id"]))
    world.transfers.sort(key=lambda t: (t["ts"], t["tx_id"]))
    world.meta = {"seed": seed, "now": iso(now), "history_days": HISTORY_DAYS, "n_customers": n_customers,
                  "generator": "versoml.data.world", "version": "1", "synthetic": True,
                  "demo_mule_iban": aml["demo_mule"]["iban"]}
    return world
