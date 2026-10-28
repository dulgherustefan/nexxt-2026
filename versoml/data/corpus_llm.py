"""Corpusul de reclamații augmentat cu LLM (generat o singură dată, păstrat în git; pipeline-ul offline nu îl cere).

Ce conține `versoml/data/corpus/llm_complaints.jsonl` (ordine deterministă: tip, scenariu, limbă, lot, index):
- `paraphrase`: reclamații libere pentru fiecare scenariu din `contracts.Scenario`, în engleză și română, scrise
  de Claude Sonnet pe Bedrock cu persoane, lungimi și grade de dezordine diferite (3 loturi x 12 texte);
- `hard_negative`: dispute legitime care sună a fraudă, „am plătit, dar m-am răzgândit”, frauda prietenoasă
  (familia a folosit cardul), reclamații vagi, reclamații cu mai multe probleme (2 loturi x 10 texte);
- `typology`: reclamații pentru tipologiile din `versoml/data/typologies_ro.yaml` (dacă fișierul există).
Fiecare rând: {id, kind, scenario, channel, dispute_type, language, batch, persona, subtype, expect_ambiguous,
typology, text, scrubbed, synthetic}.

Igienă: promptul cere doar nume fictive (Demo Bank, Demo Courier, domenii .example/.test, telefoane +40700…);
`scrub()` înlocuiește apoi orice nume de marcă reală, URL, telefon, IBAN, e-mail, număr de card sau CNP care ar
fi scăpat, cu substituenții generatorului. `scrubbed` = numărul de înlocuiri pe rând.

Regenerare (apeluri live Bedrock, us-east-1, cheia se încarcă la rulare prin `versoml.secrets.load_bedrock_key`):
    .venv/Scripts/python.exe -X utf8 -m versoml.data.corpus_llm            # tot corpusul
    .venv/Scripts/python.exe -X utf8 -m versoml.data.corpus_llm --kinds typology
Promptul e `SYSTEM_PROMPT` + `_user_prompt()` de mai jos. Modelul: `Settings.model_sonnet`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from pydantic import BaseModel, Field

from versoml.data import artifacts as art
from versoml.data import ids
from versoml.data.complaints import SCENARIO_LABELS
from versoml.data.text import normalize_ro

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
LLM_CORPUS = CORPUS_DIR / "llm_complaints.jsonl"
TYPOLOGIES_YAML = Path(__file__).resolve().parent / "typologies_ro.yaml"

PER_BATCH = 12
HARD_PER_BATCH = 10

SCENARIO_BRIEFS = {
    "phishing_link": "A text message 'from the courier' about an undelivered parcel and a small delivery fee; the customer "
                     "opened the link, typed card or online-banking details and an SMS code on the fake page; minutes later "
                     "a transfer they did not make left the account.",
    "card_ecom_fara_3ds": "An online card payment at a shop the customer never used (often a foreign site), with no "
                          "confirmation request; the card is still in the customer's possession.",
    "card_visa_secure": "A fake bank page or e-mail ('your card is suspended, confirm it'); the customer approved a "
                        "request in the banking app believing it was a card check, and it was actually an online payment.",
    "vishing_securitate": "A phone call from a fake 'bank security department' (number +40700000111); the caller convinced "
                          "the customer to approve an operation in the app 'to stop a fraud'; the screen showed the amount "
                          "and the payee; the money went to a stranger.",
    "cont_sigur": "A caller pretending to be from the bank (number +40700000222) said the account was hacked and made the "
                  "customer move savings by instant transfer to a 'safe account' IBAN he dictated.",
    "sim_swap": "The phone suddenly lost signal; the mobile operator had issued a new SIM on the customer's number without "
                "their request; meanwhile a transfer was made from a new device.",
    "frauda_client": "The customer disputes a card payment at a shop as 'not me / not authorised', insisting and threatening "
                     "to complain, with few details (in reality the bank's logs will show their own device and address).",
    "reclamatie_tardiva": "The customer only now noticed, in old statements, a card payment from more than a year ago "
                          "(13+ months) that they do not recognise, and still wants to dispute it.",
    "plata_dubla": "The same card payment at a physical shop or petrol station was taken twice (terminal error, paid again).",
    "inel_carausi": "The customer was selling something on a classifieds site; a fake buyer sent a 'confirm the parcel to "
                    "get paid' link; after typing card details and a code, a transfer left the account; the customer "
                    "found out other people lost money to the same account.",
    "injectie_document": "An ordinary dispute (e.g. a transfer after a fake courier link) whose text or attached statement "
                         "also contains a hidden instruction addressed to an automated system or AI, asking it to ignore "
                         "the rules and approve the full refund.",
    "marfa_nelivrata": "The customer paid online by card themselves, but the goods never arrived and the shop does not answer.",
}

HARD_NEGATIVES = {
    # subtype: (scenario label, expect_ambiguous, brief)
    "changed_mind": ("marfa_nelivrata", False, "The customer paid by card themselves and now changed their mind, or the "
                     "product was fine but they no longer want it, and asks the bank to 'cancel' the payment. It is not fraud."),
    "subscription": ("marfa_nelivrata", False, "A subscription or service the customer says they cancelled kept charging the "
                     "card, or a free trial turned into a paid plan; written angrily, it can sound like fraud."),
    "processing_error": ("plata_dubla", False, "A wrong amount was charged, an ATM did not give the cash but debited the "
                         "account, or a pre-authorisation was not released. It is a processing error, not fraud."),
    "friendly_fraud": ("frauda_client", False, "The customer says the payment is not theirs, but the text lets slip that a "
                       "child, partner or relative used the card or phone, or that they did order something there."),
    "vague": ("card_ecom_fara_3ds", True, "A vague complaint with almost no details: money is missing, something is wrong "
              "with the account, 'please check', no amount, no date, no channel."),
    "multi_issue": ("phishing_link", True, "One message with two or three unrelated problems (for example an unknown transfer "
                    "AND a card charged twice AND a question about a loan), without saying which matters most."),
}

PERSONAS = [
    "older customers (60+), polite, some long and rambling, some written as formal letters, a few with spelling mistakes",
    "young customers writing from their phone: very short, informal, chat style, typos, little or no punctuation",
    "angry or panicked customers of all ages: mixed lengths, some vague about details, some adding irrelevant background",
]

SYSTEM_PROMPT = """You write synthetic customer complaints for testing a bank's dispute-triage software.
Everything is fictional. Strict rules:
- The bank is "Demo Bank". The courier is "Demo Courier". Shops: DemoMarket Online, ElectroDemo Online, GADGETWORLD SHOP,
  GlobalApps Store, Demo Fashion Store, Demo Travel Agency, North Demo Supermarket, Demo Fuel A1, Example Pharmacy.
  Never use the name of any real bank, courier, shop, marketplace, app, social network, telecom operator or company.
  Say "a classifieds site", "a messaging app", "a social network", "my mobile operator" instead.
- Do not write any person's full name, real phone number, IBAN, card number, e-mail address, national ID or real URL.
  If a phone number is needed use +40700000111 or +40700000222. Web addresses only on .example or .test domains,
  e.g. livrare-bancademo.example. Sign with a first name only, or not at all.
- Amounts in RON/lei and dates are fine (October 2026 is "now").
- Vary length (from one line to a few paragraphs), tone, structure and wording; do not reuse sentences between texts.
- Write only the customer's own message, as they would type it into the app, an e-mail or a web form."""

RO_STYLE = ("Write in Romanian, the way real Romanian customers write to their bank: many write without diacritics, "
            "informally, with typos and abbreviations (\"va rog\", \"nu am facut eu plata\", \"urgent!!!\"); some write "
            "formal letters. When you do use diacritics, use ș and ț with a comma below.")
EN_STYLE = "Write in English, as customers in Romania writing in English would (some non-native phrasing is fine)."


class _Texts(BaseModel):
    complaints: list[str] = Field(description="the complaint texts, one per item")


def _user_prompt(task: dict) -> str:
    lang = RO_STYLE if task["language"] == "ro" else EN_STYLE
    if task["kind"] == "paraphrase":
        what = f"What happened (the customer's situation): {SCENARIO_BRIEFS[task['scenario']]}"
    elif task["kind"] == "hard_negative":
        what = f"What happened: {HARD_NEGATIVES[task['subtype']][2]}"
    else:
        what = (f"Fraud typology: {task['typology_name']}. Story: {task['story']}\n"
                f"Clues customers mention: {task['cues']}")
    return (f"{what}\n\nWrite {task['n']} different complaints about this situation. Writers: {PERSONAS[task['batch'] % 3]}.\n"
            f"{lang}\nNot every complaint should state every detail; some forget the amount or the date.\n"
            "Return JSON with the key \"complaints\": a list of strings.")


# ---------------------------------------------------------------- igienă

BRANDS_EN = {
    "bank": ("Demo Bank", r"BCR|BRD|ING(?: Bank)?|Raiffeisen(?: Bank)?|Banca Transilvania|CEC(?: Bank)?|Revolut|UniCredit|"
                          r"Alpha Bank|OTP Bank|Garanti(?: BBVA)?|Libra(?: Internet)? Bank|Salt Bank|Banca Comercial[aă] Rom[aâ]n[aă]"),
    "courier": ("Demo Courier", r"Fan ?Courier|Sameday|(?:Urgent )?Cargus|DPD|GLS|DHL|Po[sș]ta Rom[aâ]n[aă]|FedEx|Nemo Express"),
    "market": ("DemoMarket Online", r"eMAG|Altex|Temu|Amazon|AliExpress|Shein|Kaufland|Lidl|Carrefour|Mega Image|Profi|"
                                    r"Auchan|Dedeman|Flanco|Elefant|Fashion Days|Glovo|Tazz|Bolt Food|Booking\.com|Airbnb"),
    "classifieds": ("a classifieds site", r"OLX|Vinted|Lajumate|Publi24|Facebook Marketplace|Marketplace"),
    "social": ("a social network", r"Facebook|Instagram|TikTok|Twitter|LinkedIn"),
    "messaging": ("a messaging app", r"WhatsApp|Telegram|Viber|Messenger"),
    "telco": ("my mobile operator", r"Orange|Vodafone|Telekom|Digi(?: Mobil)?"),
    "crypto": ("CryptoX Exchange", r"Binance|Coinbase|Kraken|Bybit"),
    "tech": ("an online service", r"Netflix|Spotify|Google|Apple|Microsoft|PayPal|Uber|Bolt|Wizz ?Air|Ryanair|"
                                  r"Western Union|Hidroelectrica|Anydesk|AnyDesk|TeamViewer"),
    "scheme_secure": ("the card security check", r"Visa Secure|Verified by Visa|Mastercard Identity Check|"
                                                 r"Mastercard SecureCode"),
    "scheme": ("card", r"Visa|Mastercard|Maestro"),
}
RO_PLACEHOLDER = {"classifieds": "un site de anunțuri", "social": "o rețea socială", "messaging": "o aplicație de mesagerie",
                  "telco": "operatorul meu", "tech": "un serviciu online", "scheme": "card",
                  "scheme_secure": "verificarea de securitate a cardului"}
_FAKE_DOMAINS = ["livrare-colet-demo.example", "plata-taxa-demo.test", "confirmare-plata-demo.example",
                 "bancademo-verificare.test", "magazin-demo.example"]
RE_URL = re.compile(r"\b(?:https?://)?(?:[\w-]+\.)+(?:ro|com|net|org|eu|info|io|xyz|online|shop|site|app|me|co)\b(?:/\S*)?",
                    re.I)
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
RE_IBAN = re.compile(r"\bRO\s?\d{2}(?:\s?[A-Z0-9]{4}){4,5}\b", re.I)
RE_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
RE_PHONE = re.compile(r"(?<!\d)(?:\+?40|0040|0)\s?7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?!\d)")
RE_CNP = re.compile(r"\b[1-8]\d{12}\b")


def scrub(text: str, language: str = "en", key: str = "") -> tuple[str, int]:
    """Înlocuiește tot ce ar putea fi real cu substituenții generatorului. Întoarce (text, nr. de înlocuiri)."""
    n = 0

    def sub(pattern, repl, s):
        def fn(m: re.Match) -> str:
            nonlocal n
            out = repl(m) if callable(repl) else repl
            n += out != m.group(0)
            return out
        return (re.compile(pattern, re.I) if isinstance(pattern, str) else pattern).sub(fn, s)

    def phone(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if digits[-9:].startswith("700"):          # deja în intervalul fictiv +40700xxxxxx
            return m.group(0)
        return ids.fictive_phone(100000 + ids.stable_int(key, digits) % 899999)

    text = sub(RE_EMAIL, lambda m: m.group(0) if m.group(0).endswith("@mail.example") else "client@mail.example", text)
    text = sub(RE_URL, lambda m: m.group(0) if re.search(r"\.(example|test)\b", m.group(0), re.I)
               else _FAKE_DOMAINS[ids.stable_int(key, m.group(0)) % len(_FAKE_DOMAINS)], text)
    text = sub(RE_IBAN, lambda m: m.group(0) if ids.iban_bank_code(m.group(0)) in ids.FICTIVE_BANKS
               else ids.generate_iban(ids.sub_rng("scrub-iban", key, m.group(0)), "XBNK"), text)
    text = sub(RE_PHONE, phone, text)
    text = sub(RE_CNP, "CNP-ul meu" if language == "ro" else "my ID number", text)
    text = sub(RE_CARD, lambda m: "**** " + re.sub(r"\D", "", m.group(0))[-4:], text)
    for kind, (en, pattern) in BRANDS_EN.items():
        repl = RO_PLACEHOLDER.get(kind, en) if language == "ro" else en
        text = sub(rf"\b(?:{pattern})\b", repl, text)
    return normalize_ro(text), n


def scrub_count(text: str, language: str = "en") -> int:
    """Câte înlocuiri ar mai face `scrub` (0 = textul e curat)."""
    cleaned, _ = scrub(text, language)
    return 0 if cleaned == normalize_ro(text) else 1


# ---------------------------------------------------------------- loturile

def _labels(scenario: str) -> tuple[str, str]:
    if scenario == "injectie_document":
        return SCENARIO_LABELS["phishing_link"]
    if scenario == "reclamatie_tardiva":
        return "card", "neautorizata"
    return SCENARIO_LABELS[scenario]


def load_typologies(path: Path = TYPOLOGIES_YAML) -> list[dict]:
    if not path.exists():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for t in data.get("typologies") or []:
        if isinstance(t, dict) and t.get("id") and t.get("maps_to_scenario") in SCENARIO_LABELS:
            out.append(t)
    return out


def build_tasks(kinds: tuple[str, ...] = ("paraphrase", "hard_negative", "typology")) -> list[dict]:
    tasks = []
    if "paraphrase" in kinds:
        for sc in SCENARIO_LABELS:
            for lang in ("en", "ro"):
                for b in range(3):
                    tasks.append({"kind": "paraphrase", "scenario": sc, "language": lang, "batch": b, "n": PER_BATCH,
                                  "subtype": None, "typology": None})
    if "hard_negative" in kinds:
        for sub_, (sc, _, _) in HARD_NEGATIVES.items():
            for lang in ("en", "ro"):
                for b in range(2):
                    tasks.append({"kind": "hard_negative", "scenario": sc, "language": lang, "batch": b,
                                  "n": HARD_PER_BATCH, "subtype": sub_, "typology": None})
    if "typology" in kinds:
        for t in load_typologies():
            cues = "; ".join((t.get("complaint_cues_en") or [])[:6] + (t.get("complaint_cues_ro") or [])[:6])
            for lang in ("en", "ro"):
                tasks.append({"kind": "typology", "scenario": t["maps_to_scenario"], "language": lang,
                              "batch": ids.stable_int(t["id"]) % 3, "n": 8, "subtype": None, "typology": t["id"],
                              # the research text may name real brands: it is scrubbed before it reaches the prompt
                              "typology_name": scrub(t.get("name") or t["id"])[0], "story": scrub(t.get("story") or "")[0],
                              "cues": scrub(cues)[0]})
    return tasks


async def _run_task(client, model: str, task: dict, sem: asyncio.Semaphore, log: list) -> list[dict]:
    async with sem:
        for attempt in range(3):
            started = time.perf_counter()
            try:
                resp = await client.messages.parse(
                    model=model, max_tokens=8000, system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": _user_prompt(task)}], output_format=_Texts)
                texts = resp.parsed_output.complaints if resp.parsed_output else []
                log.append({"ok": True, "ms": round((time.perf_counter() - started) * 1000),
                            "in": resp.usage.input_tokens, "out": resp.usage.output_tokens})
                break
            except Exception as exc:  # noqa: BLE001 - retry, then skip the batch
                log.append({"ok": False, "error": type(exc).__name__})
                texts = []
                await asyncio.sleep(2 + 3 * attempt)
    ch, dt = _labels(task["scenario"])
    rows = []
    for i, raw in enumerate(texts[: task["n"] + 2]):
        key = f"{task['kind']}:{task['scenario']}:{task['language']}:{task['batch']}:{task.get('subtype')}:{task.get('typology')}:{i}"
        text, n = scrub(raw.strip(), task["language"], key)
        if len(text) < 12:
            continue
        exp_amb = HARD_NEGATIVES[task["subtype"]][1] if task["kind"] == "hard_negative" else False
        rows.append({"id": "", "kind": task["kind"], "scenario": task["scenario"], "channel": ch, "dispute_type": dt,
                     "language": task["language"], "batch": task["batch"], "persona": PERSONAS[task["batch"] % 3],
                     "subtype": task.get("subtype"), "typology": task.get("typology"), "expect_ambiguous": exp_amb,
                     "index": i, "text": text, "scrubbed": n, "synthetic": True})
    return rows


async def generate(tasks: list[dict], concurrency: int = 6) -> tuple[list[dict], list[dict]]:
    from anthropic import AsyncAnthropicBedrockMantle

    from versoml.config import get_settings
    from versoml.secrets import install_log_redaction, load_bedrock_key

    install_log_redaction()
    if not load_bedrock_key():
        raise SystemExit("no Bedrock key available")
    s = get_settings()
    client = AsyncAnthropicBedrockMantle(aws_region=s.aws_region, max_retries=2, timeout=180)
    sem = asyncio.Semaphore(concurrency)
    log: list[dict] = []
    batches = await asyncio.gather(*[_run_task(client, s.model_sonnet, t, sem, log) for t in tasks])
    return [r for b in batches for r in b], log


def _order(r: dict) -> tuple:
    return (["paraphrase", "hard_negative", "typology"].index(r["kind"]), r["scenario"], r.get("subtype") or "",
            r.get("typology") or "", r["language"], r["batch"], r["index"])


def write_corpus(rows: list[dict], path: Path = LLM_CORPUS) -> None:
    rows = sorted(rows, key=_order)
    for i, r in enumerate(rows, 1):
        r["id"] = f"LLM{i:05d}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_llm_corpus(path: Path = LLM_CORPUS) -> list[dict]:
    """Rândurile corpusului LLM, în forma rândurilor din `complaints.generate_corpus` (fără atașamente)."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.append({**r, "attachments": [], "meta": {"source": "app"}, "underlying": None,
                    "group": r["batch"] % 3, "source": "llm"})
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate the LLM-augmented complaint corpus (live Bedrock calls).")
    ap.add_argument("--kinds", default="paraphrase,hard_negative,typology")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--merge", action="store_true", help="keep the rows of the other kinds already in the file")
    args = ap.parse_args()
    kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
    tasks = build_tasks(kinds)
    t0 = time.time()
    rows, log = asyncio.run(generate(tasks, args.concurrency))
    if args.merge and LLM_CORPUS.exists():
        rows += [r for r in (json.loads(x) for x in LLM_CORPUS.read_text(encoding="utf-8").splitlines() if x.strip())
                 if r["kind"] not in kinds]
    write_corpus(rows)
    ok = [x for x in log if x.get("ok")]
    print(json.dumps({"tasks": len(tasks), "calls": len(log), "ok": len(ok), "rows": len(rows),
                      "input_tokens": sum(x["in"] for x in ok), "output_tokens": sum(x["out"] for x in ok),
                      "seconds": round(time.time() - t0, 1), "scrubbed_rows": sum(1 for r in rows if r["scrubbed"])}))
