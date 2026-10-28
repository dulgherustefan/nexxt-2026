"""Setul freeform_60: reclamații scrise liber (română și engleză), FĂRĂ `transaction_refs`.

Testează potrivirea text -> client -> tranzacție (matcher-ul zonei client) pe lumea seed-uită. Fiecare linie:
{"gid", "text", "language", "customer_ref" (sau null), "expected": {"customer_ref", "tx_id", "needs_human"},
 "scenario", "notes", "category", "received_at", "evidence", "candidates"}.

Categorii (generate din `generate_world(seed)`, deci tranzacțiile există în var/client_zone.db după seed):
- `clear` (36): suma, data și/sau beneficiarul din text potrivesc EXACT o plată ieșită a clientului (verificat aici,
  pe toate plățile clientului din ultimele 90 de zile); 10 dintre ele vin fără `customer_ref`, cu numele și
  telefonul (sau e-mailul) în text, unice în lume;
- `ambiguous` (12): beneficiarul și un interval de zile potrivesc DOUĂ plăți; `candidates` le listează;
- `no_match` (4): clientul există, dar nicio plată nu se potrivește cu ce scrie;
- `unknown_customer` (8): niciun client cu numele/telefonul/referința din text.
`needs_human` e adevărat exact când `expected.tx_id` e null.

Momentul primirii e `WORLD_NOW` (28.10.2026, 10:00, ora României); „ieri” / „yesterday” se raportează la el.
Regenerare: `python -m versoml.data.golden` (scrie și setul de aur).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from versoml.data import ids
from versoml.data.calendar_ro import TZ, iso, parse_ts
from versoml.data.complaints import add_typos
from versoml.data.text import LUNI, MONTHS, fold, fmt_number_ro, normalize_ro, strip_diacritics

N_CLEAR, N_CLEAR_NO_REF, N_AMBIGUOUS, N_NO_MATCH, N_UNKNOWN = 36, 10, 12, 4, 8
N_MULE_VICTIMS = 5          # dintre cazurile clare: plăți reale spre cărăușii lumii („cont sigur”)
WINDOW_DAYS = 90            # plățile din care matcher-ul ar trebui să aleagă
RECENT_DAYS = 55            # cazurile folosesc plăți din ultimele 55 de zile

# povești pe tipul plății: (scenariu, șabloane EN, șabloane RO); {amount} {payee} {date}
STORIES = {
    "card_ecom": [
        ("card_ecom_fara_3ds",
         ["I don't recognise a card payment of {amount} at {payee} {date}. I never shopped there and the card is with me.",
          "hi, there's an online payment {amount} to {payee} {date} that wasnt me!! please block it",
          "Dear Sir or Madam, my statement shows {amount} paid to {payee} {date}. I did not authorise this payment."],
         ["Bună ziua, am o plată de {amount} la {payee} {date} pe care nu o recunosc. Cardul e la mine.",
          "buna, imi apare o plata online {amount} la {payee} {date}, nu am facut-o eu!! va rog blocati",
          "Stimate domn/doamnă, în extras apare suma de {amount} plătită către {payee} {date}. Nu am autorizat plata."]),
        ("marfa_nelivrata",
         ["I paid {payee} {amount} {date} for an order that never arrived and they don't answer my emails.",
          "ordered from {payee} {date}, paid {amount}, still nothing delivered. I want my money back"],
         ["Am comandat de la {payee} {date} și am plătit {amount}, coletul nu a mai venit și nu răspund la telefon.",
          "am platit {amount} la {payee} {date} pt o comanda care nu a ajuns niciodata, ce pot face?"]),
    ],
    "card_pos": [
        ("plata_dubla",
         ["At {payee} I was charged {amount} {date} although the payment failed at the till and I paid again.",
          "the terminal at {payee} gave an error {date} but {amount} was still taken from my card"],
         ["La {payee} mi s-au luat {amount} {date} deși plata nu a trecut la casă și am plătit din nou.",
          "la {payee} {date} terminalul a dat eroare dar tot mi-a luat {amount} de pe card"]),
    ],
    "transfer": [
        ("phishing_link",
         ["I got an SMS about a parcel with a link, I opened it and then {amount} went to {payee} {date}. I did not send it.",
          "Someone emptied my account: a transfer of {amount} to {payee} {date}, after I typed my details on a courier page."],
         ["Am primit un SMS de la curier cu un link, am intrat și apoi au plecat {amount} către {payee} {date}. Nu eu am făcut transferul!",
          "mi s-au luat {amount} prin transfer catre {payee} {date} dupa ce am completat datele pe o pagina de curier"]),
    ],
    "mule": [
        ("cont_sigur",
         ["A man from the bank called and told me to move my money to a safe account. I sent {amount} to {payee} {date}.",
          "I was scammed by phone, they said my account was hacked and I transferred {amount} to {payee} {date}."],
         ["M-a sunat cineva de la bancă și mi-a spus să mut banii într-un cont sigur. Am trimis {amount} lui {payee} {date}.",
          "am fost inselat la telefon, mi-au zis ca mi s-a spart contul si am transferat {amount} catre {payee} {date}"]),
    ],
}
AMBIGUOUS_EN = ["{payee} took money from my card sometime between {d1} and {d2}, I don't know exactly how much. I did not buy anything.",
                "There is a payment to {payee} between {d1} and {d2} that I don't recognise, I can't remember the amount."]
AMBIGUOUS_RO = ["{payee} mi-a luat bani de pe card undeva între {d1} și {d2}, nu știu suma exactă. Nu am cumpărat nimic.",
                "Am o plată către {payee} între {d1} și {d2} pe care nu o recunosc, nu mai știu suma."]
SIGN_EN = ["My name is {name}, phone {phone}.", "{name}, {email}", "This is {name} (tel. {phone})."]
SIGN_RO = ["Mă numesc {name}, telefon {phone}.", "{name}, {email}", "Sunt {name}, nr. de telefon {phone}."]
UNKNOWN_PAYEES = ["Fast Gadgets Demo Shop", "Example Outlet Online", "Demo Crypto Wallet Service", "Travel Deals Example"]


def _kind(t: dict, mules: set[str]) -> str | None:
    if t["kind"] in ("card_ecom", "card_pos"):
        return t["kind"]
    if t["kind"] == "transfer" and t.get("counterparty_iban"):
        if t["counterparty_iban"] in mules:
            return "mule"
        if t.get("counterparty_name") and "own accounts" not in t["description"]:
            return "transfer"
    return None


def _amount_text(v: float, lang: str, rng: random.Random) -> str:
    if lang == "ro":
        return rng.choice([f"{fmt_number_ro(v)} lei", f"{v:.2f} RON", f"{fmt_number_ro(v)} RON", f"{v:.2f} lei"])
    return rng.choice([f"RON {v:,.2f}", f"{v:.2f} RON", f"{v:.2f} lei", f"RON {v:.2f}"])


def _date_text(d: date, lang: str, rng: random.Random, today: date) -> str:
    if d == today - timedelta(days=1) and rng.random() < 0.7:
        return "ieri" if lang == "ro" else "yesterday"
    if lang == "ro":
        return rng.choice([f"pe {d.day} {LUNI[d.month - 1]}", f"pe {d.day:02d}.{d.month:02d}", f"în data de {d:%d.%m.%Y}"])
    return rng.choice([f"on {d.day} {MONTHS[d.month - 1]}", f"on {MONTHS[d.month - 1][:3]} {d.day}", f"on {d:%d/%m}"])


def _range_text(d: date, lang: str) -> str:
    return f"{d.day} {LUNI[d.month - 1]}" if lang == "ro" else f"{d.day} {MONTHS[d.month - 1]}"


def _national(phone: str) -> str:
    """+40700123456 -> '0700 123 456' (cum scriu clienții numărul)."""
    n = "0" + phone[3:]
    return f"{n[:4]} {n[4:7]} {n[7:]}"


def _messy(text: str, lang: str, rng: random.Random) -> str:
    if lang == "ro" and rng.random() < 0.5:
        text = strip_diacritics(text)
    if rng.random() < 0.35:
        text = add_typos(text, rng, rng.choice([0.03, 0.06]))
    if rng.random() < 0.15:
        text = text.lower()
    return normalize_ro(text)


def _local_date(t: dict) -> date:
    return parse_ts(t["ts"]).astimezone(TZ).date()


def _matches(debits: list[dict], *, amount: float | None = None, day: date | None = None,
             payee: str | None = None, lo: date | None = None, hi: date | None = None) -> list[dict]:
    out = []
    for t in debits:
        if amount is not None and abs(t["amount"] - amount) > 0.005:
            continue
        d = _local_date(t)
        if day is not None and d != day:
            continue
        if lo is not None and not (lo <= d <= hi):
            continue
        if payee is not None and fold(payee) not in fold(t.get("counterparty_name") or ""):
            continue
        out.append(t)
    return out


def build_freeform(world, seed: int = 7) -> list[dict]:
    rng = ids.sub_rng("freeform-60", seed)
    now = world.now
    today = now.astimezone(TZ).date()
    mules = set(world.mules())
    customers = {c["customer_ref"]: c for c in world.customers}
    name_count: dict[str, int] = {}
    phone_count: dict[str, int] = {}
    for c in world.customers:
        name_count[fold(c["full_name"])] = name_count.get(fold(c["full_name"]), 0) + 1
        phone_count[c["phone"]] = phone_count.get(c["phone"], 0) + 1
    lo_window = now - timedelta(days=WINDOW_DAYS)
    debits: dict[str, list[dict]] = {}
    for t in world.card_transactions + world.transfers:
        if t["direction"] == "debit" and t["customer_ref"] in customers and lo_window <= parse_ts(t["ts"]) <= now:
            debits.setdefault(t["customer_ref"], []).append(t)
    for v in debits.values():
        v.sort(key=lambda t: (t["ts"], t["tx_id"]))
    refs = sorted(debits)
    rng.shuffle(refs)
    used_customers: set[str] = set()
    lines: list[dict] = []

    def line(category: str, text: str, lang: str, given_ref: str | None, exp_ref: str | None, tx: dict | None,
             scenario: str, notes: str, evidence: dict, candidates: list[str]) -> None:
        lines.append({"gid": "", "text": text, "language": lang, "customer_ref": given_ref,
                      "expected": {"customer_ref": exp_ref, "tx_id": tx["tx_id"] if tx else None,
                                   "needs_human": tx is None},
                      "scenario": scenario, "notes": notes, "category": category, "received_at": iso(now),
                      "evidence": evidence, "candidates": candidates, "synthetic": True})

    def sign(c: dict, lang: str) -> str:
        tpl = rng.choice(SIGN_RO if lang == "ro" else SIGN_EN)
        return tpl.format(name=c["full_name"], phone=_national(c["phone"]), email=c["email"])

    # ------------------------------------------------ clear: o singură plată potrivită
    def recent_of(ref: str, kind: str) -> list[dict]:
        return [t for t in debits[ref] if (now - parse_ts(t["ts"])).days <= RECENT_DAYS and _kind(t, mules) == kind]

    kinds_cycle = ["card_ecom", "card_pos", "transfer", "card_ecom", "transfer", "card_pos"]
    # întâi victimele reale ale cărăușilor din lume (plăți „cont sigur”), apoi restul, cu clientul dat sau nu
    plan = [(ref, "mule") for ref in refs if recent_of(ref, "mule")][:N_MULE_VICTIMS]
    plan += [(ref, None) for ref in refs]
    n_clear = n_no_ref = 0
    for ref, want in plan:
        if n_clear >= N_CLEAR:
            break
        if ref in used_customers:
            continue
        c = customers[ref]
        no_ref = want is None and n_no_ref < N_CLEAR_NO_REF
        if no_ref and (name_count[fold(c["full_name"])] > 1 or phone_count[c["phone"]] > 1):
            continue
        want = want or kinds_cycle[n_clear % len(kinds_cycle)]
        recent = recent_of(ref, want)
        if not recent:
            continue
        tx = rng.choice(recent)
        lang = "ro" if n_clear % 2 == 0 else "en"
        payee = tx["counterparty_name"]
        d = _local_date(tx)
        # dovezile din text: sumă + dată + beneficiar, uneori doar două dintre ele; trebuie să rămână unice
        options = [dict(amount=tx["amount"], day=d, payee=payee), dict(amount=tx["amount"], payee=payee),
                   dict(amount=tx["amount"], day=d)]
        if len(_matches(debits[ref], **options[0])) != 1:
            continue
        ev = options[0]
        if rng.random() >= 0.6:
            ev = next((o for o in rng.sample(options[1:], 2) if len(_matches(debits[ref], **o)) == 1), ev)
        scenario, en, ro = rng.choice(STORIES[want])
        tpl = rng.choice(ro if lang == "ro" else en)
        generic = ({"card_ecom": "un magazin online", "card_pos": "un magazin"}.get(want, "cineva") if lang == "ro"
                   else {"card_ecom": "an online shop", "card_pos": "a shop"}.get(want, "someone"))
        text = tpl.format(amount=_amount_text(tx["amount"], lang, rng), payee=payee if "payee" in ev else generic,
                          date=_date_text(d, lang, rng, today) if "day" in ev else "")
        text = " ".join(text.split()).replace(" .", ".")
        if no_ref:
            text = text.rstrip() + ("" if text.rstrip()[-1:] in ".!?" else ".") + " " + sign(c, lang)
        text = _messy(text, lang, rng)
        evidence = {"amount": ev["amount"], "date": ev.get("day").isoformat() if ev.get("day") else None,
                    "payee": ev.get("payee"), "identity": "name+contact" if no_ref else "customer_ref"}
        line("clear", text, lang, None if no_ref else ref, ref, tx, scenario,
             f"exactly one outgoing payment matches ({', '.join(k for k in ('amount', 'day', 'payee') if k in ev)})"
             + ("; the customer is identified by name and phone or e-mail" if no_ref else ""), evidence, [tx["tx_id"]])
        used_customers.add(ref)
        n_clear += 1
        n_no_ref += no_ref

    # ------------------------------------------------ ambiguous: două plăți la același beneficiar
    n_amb = 0
    for ref in refs:
        if n_amb >= N_AMBIGUOUS:
            break
        if ref in used_customers:
            continue
        by_payee: dict[str, list[dict]] = {}
        for t in debits[ref]:
            if _kind(t, mules) in ("card_ecom", "card_pos", "transfer") and (now - parse_ts(t["ts"])).days <= RECENT_DAYS:
                by_payee.setdefault(t["counterparty_name"], []).append(t)
        pairs = []
        for payee, ts in sorted(by_payee.items()):
            for a, b in zip(ts, ts[1:]):
                if 0 < (_local_date(b) - _local_date(a)).days <= 10:
                    lo, hi = _local_date(a) - timedelta(days=1), _local_date(b) + timedelta(days=1)
                    if hi <= today and len(_matches(debits[ref], payee=payee, lo=lo, hi=hi)) == 2:
                        pairs.append((payee, a, b, lo, hi))
        if not pairs:
            continue
        payee, a, b, lo, hi = rng.choice(pairs)
        lang = "en" if n_amb % 2 == 0 else "ro"
        tpl = rng.choice(AMBIGUOUS_RO if lang == "ro" else AMBIGUOUS_EN)
        text = _messy(tpl.format(payee=payee, d1=_range_text(lo, lang), d2=_range_text(hi, lang)), lang, rng)
        scenario = "card_ecom_fara_3ds" if a["channel"] == "card" else "phishing_link"
        line("ambiguous", text, lang, ref, ref, None, scenario,
             "two outgoing payments to the same payee fall in the period the customer gives; a person (or the "
             "customer) must say which one", {"amount": None, "date_from": lo.isoformat(), "date_to": hi.isoformat(),
                                              "payee": payee, "identity": "customer_ref"},
             [a["tx_id"], b["tx_id"]])
        used_customers.add(ref)
        n_amb += 1

    # ------------------------------------------------ no_match: clientul există, plata nu
    n_nm = 0
    for ref in refs:
        if n_nm >= N_NO_MATCH:
            break
        if ref in used_customers:
            continue
        lang = "ro" if n_nm % 2 == 0 else "en"
        amount = round(rng.uniform(150, 2500), 2)
        payee = UNKNOWN_PAYEES[n_nm % len(UNKNOWN_PAYEES)]
        d = today - timedelta(days=rng.randint(2, 20))
        if _matches(debits[ref], amount=amount) or _matches(debits[ref], payee=payee):
            continue
        _, en, ro = STORIES["card_ecom"][0]
        text = _messy(rng.choice(ro if lang == "ro" else en).format(
            amount=_amount_text(amount, lang, rng), payee=payee, date=_date_text(d, lang, rng, today)), lang, rng)
        line("no_match", text, lang, ref, ref, None, "card_ecom_fara_3ds",
             "the customer exists, but no outgoing payment has this amount or payee", {
                 "amount": amount, "date": d.isoformat(), "payee": payee, "identity": "customer_ref"}, [])
        used_customers.add(ref)
        n_nm += 1

    # ------------------------------------------------ unknown_customer: nimeni cu numele, telefonul sau referința
    from versoml.data.world import new_fake, person_name

    fake = new_fake("freeform-unknown", seed)
    phones = {c["phone"] for c in world.customers}
    n_unk = 0
    while n_unk < N_UNKNOWN:
        first, last, _ = person_name(fake, rng)
        name = f"{first} {last}"
        phone = ids.fictive_phone(rng.randint(100000, 999999))
        if fold(name) in name_count or phone in phones:
            continue
        lang = "en" if n_unk % 2 == 0 else "ro"
        kind = ["card_ecom", "transfer", "mule", "card_pos"][n_unk % 4]
        scenario, en, ro = STORIES[kind][0]
        amount = round(rng.uniform(80, 4000), 2)
        d = today - timedelta(days=rng.randint(1, 25))
        text = rng.choice(ro if lang == "ro" else en).format(
            amount=_amount_text(amount, lang, rng), payee=rng.choice(UNKNOWN_PAYEES), date=_date_text(d, lang, rng, today))
        given = None
        if n_unk >= N_UNKNOWN - 2:
            given = f"CUST-{9000 + n_unk}"          # referință care nu există în lume
        else:
            tpl = rng.choice(SIGN_RO if lang == "ro" else SIGN_EN)
            text = text.rstrip() + ("" if text.rstrip()[-1:] in ".!?" else ".") + " " + tpl.format(name=name, phone=_national(phone),
                                     email=strip_diacritics(f"{first}.{last}".lower()).replace(" ", "") + "@mail.example")
        text = _messy(text, lang, rng)
        line("unknown_customer", text, lang, given, None, None, scenario,
             "no customer with this name, phone, e-mail or reference exists", {
                 "amount": amount, "date": d.isoformat(), "payee": None,
                 "identity": "customer_ref (nonexistent)" if given else "name+contact (nonexistent)"}, [])
        n_unk += 1

    for i, ln in enumerate(lines, 1):
        ln["gid"] = f"FF{i:02d}"
    return lines
