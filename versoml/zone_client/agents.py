"""Agenții Judecătorului (zona client).

Fiecare nod din graf primește starea cazului, emite evenimente AG-UI, scrie probe în registru prin
tool-uri verificate de Cedar și întoarce doar actualizările lui. LLM-ul extrage, argumentează și
redactează; motorul de reguli decide; omul semnează ce e defavorabil sau peste plafon.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from langgraph.types import interrupt

from versoml.contracts import (
    AttackRef, BeneficiaryRef, Channel, Classification, ClaimPoint, Complaint, Decision, DisputeFacts,
    DisputeType, ExtractedClaim, Labels, Money, Question, RuleContext, Scenario, Sink, Trust, Verdict, Zone,
)
from versoml.shared.events import Emitter, now
from versoml.shared.llm import Role
from versoml.zone_client import prompts as P
from versoml.zone_client.runtime import ClientRuntime, get_runtime

log = logging.getLogger("versoml.client.agents")

AG = {
    "receptor": "Judecătorul/Receptor",
    "clasificator": "Judecătorul/Clasificator",
    "ceasornicar": "Judecătorul/Ceasornicar",
    "colector_tranzactie": "Judecătorul/Colector tranzacție",
    "colector_sca": "Judecătorul/Colector SCA",
    "colector_dispozitiv": "Judecătorul/Colector dispozitiv",
    "colector_domeniu": "Judecătorul/Colector domeniu",
    "motor_reguli": "Motorul de reguli",
    "outbox_aml": "Zidul/Diodă",
    "rambursare": "Judecătorul/Rambursare",
    "procuror": "Judecătorul/Procuror",
    "avocat": "Judecătorul/Avocat",
    "cantaritor": "Judecătorul/Cântăritor",
    "recuperare": "Judecătorul/Recuperare",
    "redactor": "Judecătorul/Redactor",
    "filtru_zid": "Zidul/Filtru scrisori",
    "sigiliu": "Registrul de probe",
}

PIPELINE_NODES = [
    {"id": "receptor", "label": "Receptor", "model": "haiku", "lane": "intrare",
     "hint": "LLM izolat, fără tool-uri: extrage câmpuri din textul neîncrezut"},
    {"id": "clasificator", "label": "Clasificator", "model": "ml", "lane": "intrare",
     "hint": "M1: TF-IDF + regresie logistică calibrată"},
    {"id": "ceasornicar", "label": "Ceasornicar", "model": "fără LLM", "lane": "intrare",
     "hint": "T+1, 15/35 zile lucrătoare, 13 luni, calendar RO"},
    {"id": "colector_tranzactie", "label": "Tranzacție", "model": "fără LLM", "lane": "probe",
     "hint": "bank-core: tranzacția, beneficiarul, istoricul"},
    {"id": "colector_sca", "label": "Autentificare SCA", "model": "fără LLM", "lane": "probe",
     "hint": "sca-logs: metoda și ce a afișat ecranul"},
    {"id": "colector_dispozitiv", "label": "Dispozitiv", "model": "fără LLM", "lane": "probe",
     "hint": "device: dispozitiv nou, secunde după click, SIM swap"},
    {"id": "colector_domeniu", "label": "Domeniu fals", "model": "fără LLM", "lane": "probe",
     "hint": "domain-intel: RDAP, CT, sosie M3, asemănare M4"},
    {"id": "motor_reguli", "label": "Motor de reguli", "model": "fără LLM", "lane": "decizie",
     "hint": "PAY, DSP, CMP, DP, REC: ID de regulă în fiecare decizie"},
    {"id": "outbox_aml", "label": "Diodă → AML", "model": "fără LLM", "lane": "zid",
     "hint": "doar DisputeFacts, semnat HMAC, schemă strictă"},
    {"id": "rambursare", "label": "Rambursare T+1", "model": "fără LLM", "lane": "decizie",
     "hint": "doar motorul de reguli poate emite instrucțiunea"},
    {"id": "procuror", "label": "Procuror", "model": "opus", "lane": "recuperare",
     "hint": "argumente pentru neglijență gravă, cu citări"},
    {"id": "avocat", "label": "Avocat", "model": "sonnet", "lane": "recuperare",
     "hint": "argumente pentru client, cu citări, alt model"},
    {"id": "cantaritor", "label": "Cântăritor", "model": "fără LLM", "lane": "recuperare",
     "hint": "rubrică deterministă; omul semnează"},
    {"id": "recuperare", "label": "Recuperare", "model": "sonnet", "lane": "recuperare",
     "hint": "camt.056 FRAD, chargeback, raport DNSC: ciorne"},
    {"id": "redactor", "label": "Scrisoare", "model": "sonnet", "lane": "iesire",
     "hint": "răspunde la fiecare punct, cu termene și căi de atac"},
    {"id": "filtru_zid", "label": "Filtru zid", "model": "fără LLM", "lane": "zid",
     "hint": "termeni interziși, canary, date personale"},
    {"id": "sigiliu", "label": "Sigiliu", "model": "fără LLM", "lane": "iesire",
     "hint": "Merkle + Ed25519 + QR"},
]
PIPELINE_EDGES = [
    ("receptor", "clasificator"), ("clasificator", "ceasornicar"),
    ("ceasornicar", "colector_tranzactie"), ("ceasornicar", "colector_sca"),
    ("ceasornicar", "colector_dispozitiv"), ("ceasornicar", "colector_domeniu"),
    ("colector_tranzactie", "motor_reguli"), ("colector_sca", "motor_reguli"),
    ("colector_dispozitiv", "motor_reguli"), ("colector_domeniu", "motor_reguli"),
    ("motor_reguli", "outbox_aml"), ("outbox_aml", "rambursare"),
    ("rambursare", "procuror"), ("rambursare", "avocat"),
    ("procuror", "cantaritor"), ("avocat", "cantaritor"), ("rambursare", "recuperare"),
    ("cantaritor", "redactor"), ("recuperare", "redactor"),
    ("redactor", "filtru_zid"), ("filtru_zid", "sigiliu"),
]


# ---------------------------------------------------------------- utilitare


def normalize_ro(text: str) -> str:
    """ş/ţ cu sedilă → ș/ț cu virgulă."""
    return (text or "").translate(str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"}))


def g(d: dict | None, *keys: str, default: Any = None) -> Any:
    """Prima cheie prezentă dintre variante (schemele de date pot numi câmpurile diferit)."""
    if not d:
        return default
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def money_ro(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " lei"


# Tipare pe textul fără diacritice: instrucțiuni adresate sistemului, ascunse sau deghizate în „note interne”
INJECTION_PATTERNS = [
    r"ignora\w*\s+(toate\s+)?(regulile|instructiunile|cele de mai sus|verificarile)",
    r"aproba\s+(imediat\s+|acum\s+)?(rambursarea|plata|cererea)",
    r"\bsystem\s*prompt\b", r"\bignore\s+(all\s+)?(previous|prior)\b", r"\byou\s+are\s+now\b",
    r"\besti\s+acum\s+", r"nu\s+mai\s+aplica\s+regul", r"<\s*/?\s*(system|instructions?)\s*>",
    r"<!--", r"\[\s*instructiune", r"instructiune\s+(oficiala|interna|pentru\s+(asistent|sistem|model|ai))",
    r"\basistent(ul|ule|ului)?\b[^.]{0,60}\b(nu|trimite|aproba|ignora|rambursea|marcheaza|scrie)",
    r"\b(trimite|transfera|vireaza|returneaza)\s+(imediat\s+)?banii\s+(acum|imediat|fara)",
    r"\bnu\s+mentiona\b", r"\b(note|nota)\s+pentru\s+(sistem|asistent|model|ai)\b",
    "[​‌‍⁠]",
]


def _fold(text: str) -> str:
    """Litere mici, fără diacritice, aceeași lungime (ca citatul să vină din textul original)."""
    import unicodedata

    return "".join((unicodedata.normalize("NFKD", ch)[:1] if ch.isalpha() else ch) for ch in (text or "")).lower()


def detect_injection(text: str) -> str | None:
    folded = _fold(text)
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, folded)
        if match:
            start = max(match.start() - 30, 0)
            return text[start: match.end() + 40].strip()
    return None


URL_RE = re.compile(r"https?://[^\s\"'<>)]+|\b(?:[a-z0-9-]+\.)+(?:example|test|ro|com|net|info|xyz|top|online|site)\b(?:/[^\s\"'<>)]*)?", re.I)
PHONE_RE = re.compile(r"(?:\+40|0040|\b0)\s?7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}\b|<TELEFON_\d+>")
AMOUNT_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:lei|ron)\b", re.I)


def fallback_extract(text: str) -> P.ReceptorOut:
    """Extragerea deterministă, când nu avem LLM (regex + cuvinte-cheie)."""
    low = text.lower()
    amounts = []
    for raw in AMOUNT_RE.findall(text):
        try:
            amounts.append(float(raw.replace(".", "").replace(" ", "").replace(",", ".")))
        except ValueError:
            pass
    contacted = "necunoscut"
    for key, label in (("sms", "sms"), ("mesaj", "sms"), ("sunat", "apel"), ("apel", "apel"),
                       ("telefon", "apel"), ("e-mail", "email"), ("email", "email"), ("whatsapp", "mesagerie")):
        if key in low:
            contacted = label
            break
    impersonated = next((e for e in ("curier", "banca", "poliția", "politia", "anaf", "olx") if e in low), None)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]
    asks = [s for s in sentences if re.search(r"\b(vă rog|va rog|cer|solicit|doresc|vreau|de ce|cum)\b", s, re.I)]
    points = [P.ReceptorPoint(text=s[:140], quote=s[:200]) for s in (asks or sentences[:2])][:4]
    injection = detect_injection(text)
    low_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", low)]

    def said(verbs: tuple[str, ...], context: tuple[str, ...]) -> bool:
        """Clientul spune asta într-o propoziție: un verb la persoana I + contextul potrivit."""
        return any(any(v in s for v in verbs) and any(k in s for k in context) for s in low_sentences)

    approving = said(("am confirmat", "am aprobat", "am apăsat", "am apasat", "am acceptat", "am autorizat"),
                     ("aplicați", "aplicati", "aplicaț", "notificare", "plata", "plată", "aprobare", "ce apare"))
    sharing = said(("am introdus", "am dat", "am completat", "i-am dat", "i-am spus", "am comunicat", "am trimis"),
                   ("card", "cod", "parol", "otp", "cvv", "pin", "datele"))
    return P.ReceptorOut(
        claims_unauthorized=bool(re.search(r"nu (eu )?am (făcut|facut|autorizat|efectuat)", low)),
        client_admits_sharing_credentials=sharing,
        client_admits_approving_in_app=approving,
        noticed_when=None, contacted_by=contacted, impersonated_entity=impersonated,
        mentioned_urls=list(dict.fromkeys(m.rstrip(".,;") for m in URL_RE.findall(text)))[:5],
        mentioned_phones=list(dict.fromkeys(PHONE_RE.findall(text)))[:5],
        mentioned_amounts=amounts[:5], requested_remedy="restituirea sumei" if "bani" in low or "sum" in low else None,
        points=points, injection_suspected=injection is not None, injection_quote=injection,
    )


class Ctx:
    """Contextul unui nod: runtime, emitter și scrierea de probe prin tool-uri verificate."""

    def __init__(self, state: dict):
        self.rt: ClientRuntime = get_runtime()
        self.case_id: str = state["case_id"]
        self.run_id: str = state.get("run_id", "run")
        self.em = Emitter(self.rt.bus, self.case_id, self.run_id, self.case_id)

    def track(self, step: str, status: str, summary: str | None = None, extra: dict | None = None) -> None:
        doc = self.rt.cases.get(self.case_id) or {}
        pipeline = doc.get("pipeline_status", {})
        entry = pipeline.get(step, {})
        entry["status"] = status
        if status == "running":
            entry["started_at"] = now().isoformat()
        if status in ("done", "blocked", "skipped", "waiting"):
            entry["finished_at"] = now().isoformat()
        if summary:
            entry["summary"] = summary
        if extra:
            entry.update(extra)
        pipeline[step] = entry
        self.rt.cases.update(self.case_id, {"pipeline_status": pipeline})

    async def start(self, step: str, message: str) -> None:
        self.track(step, "running")
        await self.em.step(step, AG[step], message)

    async def finish(self, step: str, message: str, data: dict | None = None, status: str = "done") -> None:
        self.track(step, status, message)
        await self.em.done(step, AG[step], message, {**(data or {}), "status": status})

    def save(self, patch: dict) -> None:
        self.rt.cases.update(self.case_id, patch)

    async def fact(self, step: str, kind: str, source_tool: str, args: dict, content: dict, summary: str,
                   labels: Labels | None = None) -> str:
        fact = self.rt.ledger.append(self.case_id, kind, source_tool, args, content, summary, labels)
        await self.em.custom("fact", summary, {"fact_id": fact.fact_id, "kind": kind, "source_tool": source_tool,
                                               "sha256": fact.sha256, "labels": fact.labels.model_dump(mode="json")},
                             step=step, agent=AG.get(step))
        return fact.fact_id

    async def call(self, step: str, who: str, action: str, fn: Callable[[], Any], args: dict) -> Any:
        """Un apel de tool: întâi politica Cedar, apoi tool-ul. Refuzul se vede în trace."""
        decision = self.rt.authorize(who, action, Zone.CLIENT)
        if not decision.allowed:
            await self.em.custom("policy_denied", f"Cedar a refuzat {action} pentru {decision.principal}",
                                 decision.model_dump(mode="json"), step=step, agent=AG.get(step))
            raise PermissionError(decision.reason)
        await self.em.tool(step, AG[step], action, args)
        result = fn()
        if asyncio.iscoroutine(result):
            result = await result
        preview = result if isinstance(result, (dict, list)) else {"value": str(result)}
        if hasattr(result, "model_dump"):
            preview = result.model_dump(mode="json")
        await self.em.tool(step, AG[step], action, args, {"ok": True, "preview": _shorten(preview)})
        return result


def _shorten(value: Any, limit: int = 600) -> Any:
    text = str(value)
    return value if len(text) <= limit else text[:limit] + "…"


def _osint_dump(result: Any) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return dict(result) if isinstance(result, dict) else {"value": str(result)}


# ---------------------------------------------------------------- 1. Receptor


async def receptor(state: dict) -> dict:
    c = Ctx(state)
    await c.start("receptor", "Primesc reclamația, o normalizez și o pseudonimizez înainte de orice LLM")
    complaint = Complaint.model_validate(state["complaint"])
    body = normalize_ro(complaint.text)
    attachments = [f"[Atașament: {a.kind}]\n{normalize_ro(a.content)}" for a in complaint.attachments]
    full = "\n\n".join([body, *attachments])

    known: dict[str, str] = {}
    try:
        customer = c.rt.repo.get_customer(complaint.customer_ref) or {}
        for key, value in customer.items():
            if isinstance(value, str) and value and any(k in key.lower() for k in ("name", "nume")):
                known[value] = "CLIENT"
    except Exception as exc:  # noqa: BLE001 - fără clientul din bancă, pseudonimizăm doar tiparele
        log.warning("nu am găsit clientul %s: %s", complaint.customer_ref, exc)

    pseudo_text, vault = c.rt.privacy.pseudonymize(full, c.case_id, known)
    redactions = sum(1 for _ in re.finditer(r"<[A-Z]+_\d+>", pseudo_text))
    await c.fact("receptor", "complaint.received", f"intake.{complaint.source}", {"source": complaint.source},
                 {"sha256_original": hashlib.sha256(full.encode()).hexdigest(), "chars": len(full),
                  "attachments": len(complaint.attachments), "redactions": redactions},
                 f"Reclamația a intrat pe canalul „{complaint.source}”; {redactions} date personale pseudonimizate",
                 Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.LLM]))

    deterministic_injection = detect_injection(full)
    out, info = await c.rt.llm.structured(
        role=Role.HAIKU, agent=AG["receptor"], system=P.RECEPTOR_SYSTEM,
        user=f"<reclamatie>\n{pseudo_text}\n</reclamatie>", schema=P.ReceptorOut,
        fallback=lambda: fallback_extract(pseudo_text), max_tokens=2500,
    )
    restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
    injection_quote = out.injection_quote or deterministic_injection
    extracted = ExtractedClaim(
        claims_unauthorized=out.claims_unauthorized,
        client_admits_sharing_credentials=out.client_admits_sharing_credentials,
        client_admits_approving_in_app=out.client_admits_approving_in_app,
        contacted_by=out.contacted_by, impersonated_entity=out.impersonated_entity,
        mentioned_urls=[restore(u) for u in out.mentioned_urls],
        mentioned_phones=[restore(p) for p in out.mentioned_phones],
        mentioned_amounts=out.mentioned_amounts, requested_remedy=out.requested_remedy,
        points=[ClaimPoint(text=p.text, quote=p.quote) for p in out.points],
        injection_suspected=bool(out.injection_suspected or deterministic_injection),
    )
    fid = await c.fact("receptor", "complaint.extracted", f"llm.{info.mode}.{info.model or 'determinist'}",
                       {"agent": AG["receptor"]}, extracted.model_dump(mode="json"),
                       f"Câmpuri extrase de LLM-ul izolat: {len(extracted.points)} puncte, contact prin "
                       f"{extracted.contacted_by or 'necunoscut'}",
                       Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
    fact_map = {"client_admits_sharing_credentials": fid, "client_admits_approving_in_app": fid}
    if extracted.injection_suspected:
        inj = await c.fact("receptor", "security.injection", "detector.injectie",
                           {"deterministic": bool(deterministic_injection)}, {"quote": injection_quote},
                           "Reclamația conține instrucțiuni către sistem; au fost tratate ca date și ignorate",
                           Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
        await c.em.custom("injection_detected", "Injecție detectată în reclamație: ignorată, semnalată omului",
                          {"fact_id": inj, "quote": injection_quote}, step="receptor", agent=AG["receptor"])
    c.save({"extracted": extracted.model_dump(mode="json"), "llm_mode": info.mode})
    await c.finish("receptor", f"Extragere gata ({info.mode}, {info.model or 'determinist'})",
                   {"llm": info.as_dict(), "injection": extracted.injection_suspected})
    return {"pseudo": {"text": pseudo_text, "vault": vault}, "extracted": extracted.model_dump(mode="json"),
            "fact_map": fact_map}


# ---------------------------------------------------------------- 2. Clasificator (M1)


async def clasificator(state: dict) -> dict:
    c = Ctx(state)
    await c.start("clasificator", "Clasific contestația din text (M1, probabilitate calibrată)")
    complaint = state["complaint"]
    text = state["pseudo"]["text"]
    try:
        from versoml.ml.m1_classifier import classify_complaint

        cls = classify_complaint(text, {"channel_hint": complaint.get("channel_hint")})
        if isinstance(cls, dict):
            cls = Classification.model_validate(cls)
    except Exception as exc:  # noqa: BLE001 - fără model antrenat folosim indiciile
        log.warning("M1 indisponibil: %s", exc)
        hint = complaint.get("channel_hint") or "transfer"
        cls = Classification(channel=Channel(hint), dispute_type=DisputeType.NEAUTORIZATA, probability=0.5,
                             ambiguous=True, model_version="rezerva", method="rules")
    fid = await c.fact("clasificator", "ml.m1_classification", "ml.m1_classifier", {"model": cls.model_version},
                       cls.model_dump(mode="json"),
                       f"M1: {cls.dispute_type.value}, canal {cls.channel.value}, p={cls.probability:.2f}"
                       + (" (ambiguu)" if cls.ambiguous else ""),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    c.save({"classification": cls.model_dump(mode="json")})
    await c.finish("clasificator", f"{cls.dispute_type.value} / {cls.scenario.value if cls.scenario else '—'} "
                                   f"(p={cls.probability:.2f})", {"classification": cls.model_dump(mode="json")})
    return {"classification": cls.model_dump(mode="json"), "fact_map": {"classification": fid}}


# ---------------------------------------------------------------- 3. Ceasornicar


async def ceasornicar(state: dict) -> dict:
    c = Ctx(state)
    await c.start("ceasornicar", "Pornesc ceasurile legale din momentul notificării")
    from versoml.shared.rules.calendar_ro import add_business_days, end_of_next_business_day

    received = parse_dt(state["complaint"]["received_at"]) or now()
    t1 = end_of_next_business_day(received)
    answer = add_business_days(received, 15)
    clock = {"notified_at": received.isoformat(), "t1_deadline": t1.isoformat(),
             "answer_deadline": answer.isoformat()}
    fid = await c.fact("ceasornicar", "clock.started", "rules.calendar_ro", {"notified_at": received.isoformat()},
                       clock, f"Termen T+1: {t1.strftime('%d.%m.%Y %H:%M')}; răspuns în 15 zile lucrătoare",
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT, Sink.LETTER]))
    c.save({"clock": clock, "deadline": t1.isoformat()})
    await c.em.custom("clock", "Ceasul T+1 a pornit", clock, step="ceasornicar", agent=AG["ceasornicar"])
    await c.finish("ceasornicar", f"T+1 până la {t1.strftime('%d.%m.%Y, %H:%M')}")
    return {"clock": clock, "fact_map": {"notified_at": fid}}


# ---------------------------------------------------------------- 4. Colectori (în paralel)


def _main_tx_id(state: dict) -> str | None:
    refs = state["complaint"].get("transaction_refs") or []
    return refs[0] if refs else None


async def colector_tranzactie(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_tranzactie", "Citesc tranzacția și beneficiarul din bank-core")
    tx_id = _main_tx_id(state)
    customer_ref = state["complaint"]["customer_ref"]
    records: dict = {}
    fact_map: dict = {}
    tx = await c.call("colector_tranzactie", "colector", "bank-core.get_transaction",
                      lambda: c.rt.repo.get_transaction(tx_id) if tx_id else None, {"tx_id": tx_id})
    if tx:
        records["transaction"] = tx
        amount = float(g(tx, "amount", "value", default=0))
        bene = g(tx, "beneficiary_iban", "counterparty_iban", "to_iban", default=None)
        fid = await c.fact("colector_tranzactie", "bank.transaction", "bank-core.get_transaction", {"tx_id": tx_id},
                           tx, f"Tranzacția {tx_id}: {money_ro(amount)}, {g(tx, 'channel', 'type', default='')}"
                               + (f", către {bene[:4]}…{bene[-4:]}" if bene else ""),
                           Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT, Sink.AML]))
        fact_map.update({"amount": fid, "executed_at": fid, "channel": fid, "merchant_mcc": fid, "eci": fid})
        if bene:
            seen = await c.call("colector_tranzactie", "colector", "bank-core.beneficiary_seen_before",
                                lambda: c.rt.repo.beneficiary_seen_before(customer_ref, bene), {"iban": "…"})
            records["beneficiary_new"] = not bool(seen)
            fid = await c.fact("colector_tranzactie", "bank.beneficiary_history", "bank-core.beneficiary_seen_before",
                               {"customer": customer_ref}, {"beneficiary_new": not bool(seen)},
                               "Beneficiar nou pentru client" if not seen else "Beneficiar folosit anterior de client")
            fact_map["beneficiary_new"] = fid
        dups = []
        if g(tx, "channel", "type", default="") == "card":
            dups = await c.call("colector_tranzactie", "colector", "bank-core.get_transaction",
                                lambda: c.rt.repo.find_duplicates(tx_id), {"tx_id": tx_id, "op": "find_duplicates"}) or []
        if dups:
            records["duplicate_of"] = g(dups[0], "id", "tx_id")
            fact_map["duplicate_of"] = await c.fact(
                "colector_tranzactie", "bank.duplicate", "bank-core.find_duplicates", {"tx_id": tx_id},
                {"duplicates": dups}, f"Tranzacție identică găsită: {records['duplicate_of']}")
    prior = await c.call("colector_tranzactie", "colector", "bank-core.get_prior_disputes",
                         lambda: c.rt.repo.get_prior_disputes(customer_ref, 12), {"months": 12})
    records["prior_disputes_12m"] = len(prior or [])
    fact_map["prior_disputes_12m"] = await c.fact(
        "colector_tranzactie", "bank.prior_disputes", "bank-core.get_prior_disputes", {"months": 12},
        {"count": len(prior or [])}, f"{len(prior or [])} contestații anterioare în ultimele 12 luni")
    await c.finish("colector_tranzactie", "Tranzacția și istoricul sunt în registru")
    return {"records": records, "fact_map": fact_map}


async def colector_sca(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_sca", "Citesc autentificările SCA: metoda și ce a văzut clientul pe ecran")
    tx_id = _main_tx_id(state)
    events = await c.call("colector_sca", "colector", "sca-logs.get_auth_events",
                          lambda: c.rt.repo.get_auth_events(tx_id) if tx_id else [], {"tx_id": tx_id}) or []
    records: dict = {"auth_events": events}
    fact_map: dict = {}
    payment_auth = next((e for e in events if g(e, "purpose", default="payment") == "payment"), None)
    enrollment = next((e for e in events if g(e, "purpose") == "device_enrollment"), None)
    shown = None
    if payment_auth:
        shown = bool(g(payment_auth, "screen_showed_amount_and_payee", "dynamic_linking", default=False))
    elif enrollment:
        shown = False  # plata a plecat de pe un dispozitiv înrolat; SCA-ul nu a afișat suma
    method = g(payment_auth or enrollment or {}, "method", default="none")
    records.update({"sca_performed": bool(events), "sca_method": method, "screen_showed_amount_and_payee": shown,
                    "eci": g(payment_auth or {}, "eci"), "cavv_present": g(payment_auth or {}, "cavv_present", "cavv")})
    for event in events[:4]:
        purpose = g(event, "purpose", default="payment")
        fid = await c.fact(
            "colector_sca", "sca.auth_event", "sca-logs.get_auth_events", {"tx_id": tx_id}, event,
            f"SCA {g(event, 'method', default='?')} pentru {'înrolarea unui dispozitiv nou' if purpose == 'device_enrollment' else 'plată'}: "
            + ("ecranul a afișat suma și beneficiarul" if g(event, "screen_showed_amount_and_payee") else "fără sumă și beneficiar pe ecran"))
        fact_map.setdefault("sca_performed", fid)
        fact_map.setdefault("sca_method", fid)
        fact_map.setdefault("screen_showed_amount_and_payee", fid)
        if g(event, "eci"):
            fact_map["eci"] = fid
            fact_map["cavv_present"] = fid
    if not events:
        fact_map["sca_performed"] = await c.fact("colector_sca", "sca.none", "sca-logs.get_auth_events",
                                                 {"tx_id": tx_id}, {"events": 0}, "Nicio autentificare SCA în jurnal")
    await c.finish("colector_sca", f"{len(events)} evenimente SCA; ecranul "
                                   + ("a afișat" if shown else "nu a afișat") + " suma și beneficiarul")
    return {"records": records, "fact_map": fact_map}


async def colector_dispozitiv(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_dispozitiv", "Verific dispozitivul, sesiunea și schimbările de SIM")
    customer_ref = state["complaint"]["customer_ref"]
    tx_id = _main_tx_id(state)
    tx = await c.call("colector_dispozitiv", "colector", "bank-core.get_transaction",
                      lambda: c.rt.repo.get_transaction(tx_id) if tx_id else None, {"tx_id": tx_id})
    records: dict = {}
    fact_map: dict = {}
    session_id = g(tx or {}, "session_id")
    session = None
    if session_id:
        session = await c.call("colector_dispozitiv", "colector", "device.get_session",
                               lambda: c.rt.repo.get_session(session_id), {"session_id": session_id})
    history = await c.call("colector_dispozitiv", "colector", "device.get_device_history",
                           lambda: c.rt.repo.get_device_history(customer_ref), {"customer": customer_ref}) or []
    device_id = g(session or {}, "device_id", "device_fingerprint")
    if session:
        executed_at = parse_dt(g(tx or {}, "executed_at", "ts", "timestamp")) or now()
        # cunoscut = înrolat cu cel puțin o zi înainte de plată (un telefon înrolat acum câteva minute e „nou”)
        known_ids = {g(d, "device_id", "fingerprint", "device_fingerprint") for d in history
                     if g(d, "trusted", "known", default=True)
                     and (parse_dt(g(d, "enrolled_at", "first_seen", "first_seen_at")) or executed_at)
                     < executed_at - timedelta(days=1)}
        device_known = bool(g(session, "device_known")) if g(session, "device_known") is not None else device_id in known_ids
        click = parse_dt(g(session, "link_clicked_at", "click_at", "clicked_at"))
        executed = parse_dt(g(tx or {}, "executed_at", "ts", "timestamp"))
        seconds = g(session, "seconds_after_click")
        if seconds is None and click and executed:
            seconds = int((executed - click).total_seconds())
        records.update({"device_known": device_known, "seconds_after_click": seconds, "session": session})
        fid = await c.fact("colector_dispozitiv", "device.session", "device.get_session", {"session_id": session_id},
                           session, ("Dispozitiv cunoscut" if device_known else "Dispozitiv NOU, nevăzut până acum")
                           + (f"; plata la {seconds} s după click pe link" if seconds is not None else ""))
        fact_map.update({"device_known": fid, "seconds_after_click": fid})
    executed = parse_dt(g(tx or {}, "executed_at", "ts", "timestamp")) or now()
    sims = await c.call("colector_dispozitiv", "colector", "device.get_device_history",
                        lambda: c.rt.repo.sim_swap_events(customer_ref, executed, 48),
                        {"customer": customer_ref, "op": "sim_swap_events", "hours": 48}) or []
    if sims:
        swap_at = parse_dt(g(sims[0], "ts", "at", "swapped_at")) or executed
        hours = round((executed - swap_at).total_seconds() / 3600, 2)
        records["sim_swap_hours_before"] = hours
        fact_map["sim_swap_hours_before"] = await c.fact(
            "colector_dispozitiv", "telecom.sim_swap", "device.sim_swap_events", {"hours": 48}, {"events": sims},
            f"Schimbare de SIM cu {hours} ore înainte de plată")
    await c.finish("colector_dispozitiv", "Dispozitivul și sesiunea sunt în registru")
    return {"records": records, "fact_map": fact_map}


async def colector_domeniu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_domeniu", "Analizez domeniul fals: vârstă, certificat, asemănare cu banca")
    extracted = state.get("extracted") or {}
    texts = [state["complaint"].get("text", "")] + [a.get("content", "") for a in state["complaint"].get("attachments", [])]
    try:
        from versoml.osint.investigate import extract_artifacts

        artifacts = extract_artifacts("\n".join(texts))
    except Exception:  # noqa: BLE001
        artifacts = {"domains": [], "urls": []}
    urls = list(dict.fromkeys([*extracted.get("mentioned_urls", []), *artifacts.get("urls", [])]))
    domains = list(dict.fromkeys([*artifacts.get("domains", [])]))
    for url in urls:
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        if host and host not in domains:
            domains.append(host)
    phones = list(dict.fromkeys([*extracted.get("mentioned_phones", []), *artifacts.get("phones", [])]))
    records: dict = {"attack": {"domains": domains[:3], "urls": urls[:3], "phones": phones[:3]}}
    fact_map: dict = {}
    intel: dict = {}
    if not domains:
        await c.finish("colector_domeniu", "Niciun domeniu în reclamație", status="skipped")
        return {"records": records, "fact_map": fact_map}

    try:
        from versoml.osint import domain as osd
        from versoml.osint import lookalike as osl
        from versoml.osint import threatintel as ost
    except ImportError as exc:  # fără modulul OSINT, colectorul nu oprește cazul
        log.warning("OSINT indisponibil: %s", exc)
        await c.finish("colector_domeniu", "Modulul domain-intel nu e disponibil", status="skipped")
        return {"records": records, "fact_map": fact_map}

    domain = domains[0]
    url = urls[0] if urls else f"https://{domain}/"

    async def run(action: str, fn: Callable[[], Any], args: dict) -> Any:
        try:
            return await c.call("colector_domeniu", "colector", action, fn, args)
        except Exception as exc:  # noqa: BLE001 - un tool căzut nu oprește colectorul
            log.warning("%s a eșuat: %s", action, exc)
            return None

    rdap, ct, look, phish, page = await asyncio.gather(
        run("domain-intel.rdap_lookup", lambda: osd.rdap_domain(domain), {"domain": domain}),
        run("domain-intel.ct_first_seen", lambda: osd.ct_certificates(domain), {"domain": domain}),
        run("domain-intel.lookalike_score", lambda: osl.lookalike_score(domain), {"domain": domain}),
        run("domain-intel.openphish_check", lambda: ost.openphish_check(url), {"url": url}),
        run("domain-intel.fetch_page", lambda: _fetch_page(url), {"url": url}),
    )
    for name, result, kind in (("rdap", rdap, "domain.rdap"), ("ct", ct, "domain.ct"),
                               ("lookalike", look, "domain.lookalike"), ("openphish", phish, "domain.openphish"),
                               ("page", page, "domain.page")):
        if result is None:
            continue
        data = _osint_dump(result)
        intel[name] = data
        fid = await c.fact("colector_domeniu", kind, f"domain-intel.{name}", {"domain": domain},
                           data, data.get("summary") or f"{name} pentru {domain}",
                           Labels(conf="public", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.AML, Sink.LLM]))
        fact_map[f"domain_{name}"] = fid
    # M4: fetch_page calculează deja asemănarea cu pagina Banca Demo (HTML-ul brut, neîncrezut, nu circulă)
    similarity = ((intel.get("page") or {}).get("data") or {}).get("similarity")
    if similarity is not None:
        score = similarity.get("score") if isinstance(similarity, dict) else similarity
        data = similarity if isinstance(similarity, dict) else {"score": similarity}
        intel["similarity"] = data
        fact_map["domain_similarity"] = await c.fact(
            "colector_domeniu", "domain.similarity", "domain-intel.page_similarity", {"reference": "bancademo_login"},
            data, f"M4: pagina seamănă {float(score):.0%} cu pagina de autentificare Banca Demo"
            if isinstance(score, (int, float)) else "M4: asemănarea paginii cu pagina băncii")
    age_hours = _age_hours(intel.get("rdap"))
    score = (intel.get("lookalike") or {}).get("data", {}).get("score")
    records["attack"].update({"domain": domain, "url": url, "domain_age_hours": age_hours, "lookalike_score": score})
    await c.finish("colector_domeniu", f"{domain}: " + (f"creat acum {age_hours:.0f} h; " if age_hours is not None else "")
                   + (f"scor de sosie {score:.2f}" if isinstance(score, (int, float)) else "scor indisponibil"),
                   {"intel": {k: (v.get("summary") if isinstance(v, dict) else None) for k, v in intel.items()}})
    return {"records": records, "fact_map": fact_map, "domain_intel": intel}


async def _fetch_page(url: str):
    from versoml.osint.crawl import fetch_page

    return await fetch_page(url)


def _age_hours(rdap: dict | None) -> float | None:
    if not rdap:
        return None
    data = rdap.get("data") or {}
    for key in ("age_hours", "domain_age_hours"):
        if isinstance(data.get(key), (int, float)):
            return float(data[key])
    if isinstance(data.get("age_days"), (int, float)):
        return float(data["age_days"]) * 24
    created = parse_dt(data.get("created") or data.get("registration") or data.get("created_at"))
    return round((now() - created).total_seconds() / 3600, 1) if created else None


# ---------------------------------------------------------------- 5. Motorul de reguli


def reconcile_type(cls: dict, records: dict, extracted: dict) -> tuple[DisputeType, bool, str]:
    """Clasificarea finală: textul (M1) împăcat cu faptele din sistemele băncii."""
    ml_type = DisputeType(cls.get("dispute_type", "neautorizata"))
    approved_in_app = bool(records.get("screen_showed_amount_and_payee")) and bool(records.get("device_known"))
    if records.get("duplicate_of"):
        return DisputeType.EROARE_PROCESARE, False, "tranzacție dublă găsită în bank-core"
    if ml_type in (DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        return ml_type, bool(cls.get("ambiguous")), "textul descrie o problemă cu comerciantul"
    fact_type = DisputeType.APP if approved_in_app and records.get("channel") != "card" else DisputeType.NEAUTORIZATA
    if records.get("device_known") is False:
        fact_type = DisputeType.NEAUTORIZATA
    ambiguous = bool(cls.get("ambiguous")) or fact_type != ml_type
    reason = ("faptele confirmă textul" if fact_type == ml_type else
              f"textul sugerează {ml_type.value}, faptele arată {fact_type.value}: decid faptele, semnalez omului")
    return fact_type, ambiguous, reason


async def motor_reguli(state: dict) -> dict:
    c = Ctx(state)
    await c.start("motor_reguli", "Construiesc contextul de reguli doar din fapte și evaluez regulile")
    from versoml.shared.rules import RuleContextExt, evaluate

    records = dict(state.get("records") or {})
    tx = records.get("transaction") or {}
    channel_raw = g(tx, "channel", "type", default=(state.get("classification") or {}).get("channel", "transfer"))
    if channel_raw in ("transfer_instant", "instant"):
        channel = Channel.TRANSFER_INSTANT
    elif channel_raw == "card":
        channel = Channel.CARD
    else:
        channel = Channel.TRANSFER
    records["channel"] = channel.value
    dispute_type, ambiguous, reason = reconcile_type(state.get("classification") or {}, records, state.get("extracted") or {})
    cls = state.get("classification") or {}
    scenario = cls.get("scenario")
    hint = (state.get("scenario_hint") or "")
    if hint and hint in Scenario._value2member_map_:
        scenario = hint

    signal = None
    try:
        from versoml.ml.m2_client_fraud import client_fraud_signal

        signal = client_fraud_signal({
            "prior_disputes_12m": records.get("prior_disputes_12m", 0),
            "device_known": records.get("device_known"),
            "beneficiary_new": records.get("beneficiary_new"),
            "amount": float(g(tx, "amount", "value", default=0)),
            "seconds_after_click": records.get("seconds_after_click"),
            "channel": channel.value,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("M2 indisponibil: %s", exc)
    fact_map = dict(state.get("fact_map") or {})
    if signal:
        fact_map["client_fraud_score"] = await c.fact(
            "motor_reguli", "ml.m2_client_fraud", "ml.m2_client_fraud", {}, signal,
            f"M2 (semnal pentru om, nu decizie): scor {float(signal.get('score', 0)):.2f}")

    doc = c.rt.cases.get(c.case_id) or {}
    hold = doc.get("hold") or {}
    executed = parse_dt(g(tx, "executed_at", "ts", "timestamp")) or now()
    notified = parse_dt(state["complaint"]["received_at"]) or now()
    extracted = state.get("extracted") or {}
    claimed = extracted.get("mentioned_amounts") or []
    refs = set(state["complaint"].get("transaction_refs") or [])
    other_dispute = any(d.get("case_id") not in (None, c.case_id) and d.get("status") not in ("EROARE",)
                        and refs & set((d.get("complaint") or {}).get("transaction_refs") or []) for d in c.rt.cases.all())
    ctx = RuleContextExt(
        existing_dispute_for_txn=other_dispute,
        classification_ambiguous=ambiguous,
        beneficiary_iban=g(tx, "beneficiary_iban", "counterparty_iban", "to_iban"),
        complaint_received_at=notified,
        card_scheme="visa" if channel == Channel.CARD else None,
        processing_date=executed.date(),
        injection_suspected=bool(extracted.get("injection_suspected")),
        # suma invocată = cea din text mai apropiată de jurnal (textul pomenește și taxa-momeală de 2,99 lei)
        claimed_amount=float(min(claimed, key=lambda v: abs(float(v) - float(g(tx, "amount", "value", default=0)))))
        if claimed else None,
        case_id=c.case_id, now=now(), channel=channel, dispute_type=dispute_type,
        scenario=Scenario(scenario) if scenario in Scenario._value2member_map_ else None,
        amount=Money(value=float(g(tx, "amount", "value", default=0)), currency=g(tx, "currency", default="RON")),
        executed_at=executed, notified_at=notified,
        sca_performed=records.get("sca_performed"), sca_method=records.get("sca_method"),
        eci=records.get("eci") or g(tx, "eci"), cavv_present=records.get("cavv_present"),
        screen_showed_amount_and_payee=records.get("screen_showed_amount_and_payee"),
        device_known=records.get("device_known"), seconds_after_click=records.get("seconds_after_click"),
        sim_swap_hours_before=records.get("sim_swap_hours_before"), beneficiary_new=records.get("beneficiary_new"),
        merchant_mcc=g(tx, "mcc", "merchant_mcc"), duplicate_of=records.get("duplicate_of"),
        prior_disputes_12m=int(records.get("prior_disputes_12m") or 0),
        client_fraud_score=float(signal["score"]) if signal and signal.get("score") is not None else None,
        client_admits_sharing_credentials=(state.get("extracted") or {}).get("client_admits_sharing_credentials"),
        client_admits_approving_in_app=(state.get("extracted") or {}).get("client_admits_approving_in_app"),
        hold_signal=bool(hold.get("hold")), hold_authority_notified=bool(hold.get("authority_notified")),
        fact_ids={k: v for k, v in fact_map.items() if isinstance(v, str)},
    )
    await c.em.custom("classification_final", f"Clasificare finală: {dispute_type.value} ({reason})",
                      {"dispute_type": dispute_type.value, "ambiguous": ambiguous}, step="motor_reguli",
                      agent=AG["motor_reguli"])
    outcome = evaluate(ctx)
    for hit in outcome.hits:
        await c.em.custom("rule_hit", f"{hit.rule_id}: {hit.outcome}", hit.model_dump(mode="json"),
                          step="motor_reguli", agent=AG["motor_reguli"])
    decisions = list(outcome.decisions)
    if ambiguous:
        for d in decisions:
            if d.question == Question.RAMBURSARE_T1 and d.decision == Verdict.RAMBURSEAZA:
                d.decision = Verdict.RAMBURSEAZA_CU_APROBARE
                d.requires_human = True
                d.decided_by = "rules+human"
                d.unknowns.append("clasificarea textului contrazice faptele: confirmă un om")
    for d in decisions:
        await c.em.custom("decision", f"{d.question.value}: {d.decision.value}", d.model_dump(mode="json"),
                          step="motor_reguli", agent=AG["motor_reguli"])
    fid = await c.fact("motor_reguli", "rules.outcome", "rules.engine", {"engine": outcome.engine_version},
                       {"decisions": [d.model_dump(mode="json") for d in decisions],
                        "rule_ids": sorted({h.rule_id for h in outcome.hits})},
                       f"Motorul de reguli: {len(outcome.hits)} reguli atinse, {len(decisions)} decizii")
    t1 = next((d for d in decisions if d.question == Question.RAMBURSARE_T1), None)
    c.save({"rule_context": ctx.model_dump(mode="json"), "rules": outcome.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "verdict": t1.decision.value if t1 else None, "channel": channel.value,
            "scenario": ctx.scenario.value if ctx.scenario else scenario,
            "amount": ctx.amount.model_dump(), "dispute_type": dispute_type.value})
    await c.finish("motor_reguli", f"Rambursare: {t1.decision.value if t1 else '—'}; reguli "
                   + ", ".join(sorted({h.rule_id for h in outcome.hits})[:6]))
    return {"rule_context": ctx.model_dump(mode="json"), "rules": outcome.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in decisions], "fact_map": {"rules_outcome": fid},
            "records": {"channel": channel.value}}


# ---------------------------------------------------------------- 6. Dioda spre AML


async def outbox_aml(state: dict) -> dict:
    c = Ctx(state)
    await c.start("outbox_aml", "Trimit spre AML doar fapte despre atac și beneficiar, fără identitatea victimei")
    ctx = state["rule_context"]
    records = state.get("records") or {}
    tx = records.get("transaction") or {}
    attack = records.get("attack") or {}
    bene_iban = g(tx, "beneficiary_iban", "counterparty_iban", "to_iban")
    if ctx["dispute_type"] not in ("neautorizata", "app") or not (bene_iban or attack.get("domain")):
        await c.finish("outbox_aml", "Nu e caz de fraudă cu beneficiar: nimic de trimis", status="skipped")
        return {}
    victim_ref = "VCT-" + hashlib.sha256(f"versoml|{state['complaint']['customer_ref']}".encode()).hexdigest()[:6]
    facts = DisputeFacts(
        case_id=c.case_id, victim_ref=victim_ref, channel=Channel(ctx["channel"]),
        dispute_type=DisputeType(ctx["dispute_type"]),
        scenario=Scenario(ctx["scenario"]) if ctx.get("scenario") else None,
        amount=Money.model_validate(ctx["amount"]), executed_at=parse_dt(ctx["executed_at"]) or now(),
        beneficiary=BeneficiaryRef(iban=bene_iban, name=g(tx, "beneficiary_name", "counterparty_name"),
                                   cui=g(tx, "beneficiary_cui"), bank_bic=g(tx, "beneficiary_bic")),
        attack=AttackRef(domain=attack.get("domain"), url=attack.get("url"),
                         phone=(attack.get("phones") or [None])[0], domain_age_hours=attack.get("domain_age_hours"),
                         lookalike_score=attack.get("lookalike_score")),
        fact_ids=[v for k, v in (state.get("fact_map") or {}).items() if k in ("amount", "domain_rdap", "domain_lookalike")],
    )
    decision = c.rt.authorize("colector", "diode.send_facts", Zone.CLIENT)
    status = "neautorizat"
    if decision.allowed:
        try:
            result = await _send_facts(c.rt, facts)
            status = "trimis" if result.get("ok") else "în outbox (zona AML nu răspunde; se retrimite)"
        except Exception as exc:  # noqa: BLE001 - schema refuzată: nu trimitem nimic
            log.warning("dioda: %s", exc)
            status = f"refuzat de diodă ({type(exc).__name__})"
    fid = await c.fact("outbox_aml", "wall.diode_sent", "diode.send_facts", {"case_id": c.case_id},
                       {"status": status, "fields": sorted(facts.model_dump(exclude_none=True).keys())},
                       f"Dioda: DisputeFacts {status}; victima apare doar ca {victim_ref}",
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    await c.em.custom("diode", f"DisputeFacts {status}", {"status": status, "victim_ref": victim_ref, "fact_id": fid},
                      step="outbox_aml", agent=AG["outbox_aml"])
    c.save({"aml_referral": {"status": status, "victim_ref": victim_ref}})
    await c.finish("outbox_aml", f"Dioda: {status}")
    return {}


async def _send_facts(rt: ClientRuntime, facts: DisputeFacts) -> dict:
    # trimiterea HTTP e sincronă: o mutăm pe un fir, ca graful să nu blocheze bucla de evenimente
    result = await asyncio.to_thread(rt.diode.send_facts, facts)
    return result if isinstance(result, dict) else {"ok": True}


# ---------------------------------------------------------------- 7. Rambursarea (motorul de reguli + om)


def _decision(state: dict, question: Question) -> dict | None:
    return next((d for d in state.get("decisions", []) if d.get("question") == question.value), None)


async def rambursare(state: dict) -> dict:
    c = Ctx(state)
    d = _decision(state, Question.RAMBURSARE_T1)
    if state.get("refund", {}).get("done"):
        return {}
    verdict = d["decision"] if d else None
    amount = float((state["rule_context"].get("amount") or {}).get("value", 0))
    customer_ref = state["complaint"]["customer_ref"]
    # la reluarea după semnătura umană, nodul rulează din nou până la interrupt(): nu reemitem nimic
    pending = (c.rt.cases.get(c.case_id) or {}).get("interrupt") or {}
    resuming = bool(pending.get("pending") or pending.get("resuming"))
    if not resuming:
        await c.start("rambursare", f"Aplic decizia de rambursare: {verdict}")

    if verdict in (Verdict.RAMBURSEAZA_CU_APROBARE.value, Verdict.EXCEPTIE_FRAUDA_CLIENT.value,
                   Verdict.RESPINGE_TARDIV.value) or (d and d.get("requires_human") and verdict != Verdict.NU_SE_APLICA_T1.value):
        prompt = {
            Verdict.RAMBURSEAZA_CU_APROBARE.value: f"Regulile cer rambursarea a {money_ro(amount)} până la termenul T+1, "
                                                   "dar peste plafon sau cu semnale de risc. Aprobi instrucțiunea?",
            Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "Zona AML a emis HOLD aprobat de un analist, iar autoritatea e notificată. "
                                                 "Confirmi excepția C-70/25 (fără rambursare acum)?",
            Verdict.RESPINGE_TARDIV.value: "Notificarea a venit după 13 luni (art. 169). O decizie defavorabilă cere "
                                          "semnătură umană (GDPR art. 22). Confirmi respingerea?",
        }.get(verdict, "Decizia cere semnătură umană.")
        payload = {"kind": "aprobare_rambursare" if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value else "semnatura_decizie",
                   "verdict": verdict, "prompt": prompt, "options": ["approve", "reject"], "amount": amount,
                   "deadline": d.get("deadline") if d else None, "rule_ids": d.get("rule_ids", []) if d else []}
        if not resuming:
            c.track("rambursare", "waiting", "Așteaptă semnătura operatorului")
            c.save({"interrupt": {"pending": True, **payload}, "status": "ASTEAPTA_APROBARE"})
            await c.em.custom("interrupt", prompt, payload, step="rambursare", agent=AG["rambursare"])
        answer = interrupt(payload)
        c.save({"interrupt": {**payload, "pending": False, "resuming": False, "answer": answer}})
        approved = (answer or {}).get("action") == "approve"
        approver = (answer or {}).get("approver") or "OPERATOR-01"
        await c.fact("rambursare", "human.signature", "consola.operator", {"approver": approver},
                     {"action": (answer or {}).get("action"), "note": (answer or {}).get("note")},
                     f"{approver} a {'aprobat' if approved else 'respins'} decizia {verdict}")
        if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value and approved:
            return await _issue_refund(c, state, amount, customer_ref, approved_by=approver)
        status = {Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "EXCEPTIE", Verdict.RESPINGE_TARDIV.value: "RESPINS"}.get(
            verdict, "IN_ANALIZA")
        if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value and not approved:
            status = "IN_ANALIZA"
        if verdict in (Verdict.EXCEPTIE_FRAUDA_CLIENT.value, Verdict.RESPINGE_TARDIV.value) and not approved:
            # omul nu a confirmat decizia defavorabilă: rambursăm în termen
            return await _issue_refund(c, state, amount, customer_ref, approved_by=approver)
        c.save({"status": status})
        await c.finish("rambursare", f"Decizie semnată de {approver}: {status}")
        return {"refund": {"done": False, "status": status}}

    if verdict == Verdict.RAMBURSEAZA.value:
        return await _issue_refund(c, state, amount, customer_ref, approved_by=None)

    status = "TRASEU_APP" if state["rule_context"]["dispute_type"] == "app" else "IN_ANALIZA"
    c.save({"status": status})
    await c.finish("rambursare", "Nu se aplică rambursarea T+1: traseul de recuperare și sprijin", status="skipped")
    return {"refund": {"done": False, "status": status}}


async def _issue_refund(c: Ctx, state: dict, amount: float, customer_ref: str, approved_by: str | None) -> dict:
    context = {"within_auto_cap": approved_by is None, "approved_by_human": approved_by is not None}
    decision = c.rt.authorize("motor", "refund.issue", Zone.CLIENT, context)
    if not decision.allowed:
        await c.em.custom("policy_denied", "Cedar a refuzat instrucțiunea de rambursare", decision.model_dump(mode="json"),
                          step="rambursare", agent=AG["rambursare"])
        await c.finish("rambursare", "Instrucțiunea a fost refuzată de politică", status="blocked")
        return {"refund": {"done": False, "status": "BLOCAT"}}
    # o plată se rambursează o singură dată, oricâte contestații ar avea (protecție operațională, nu regulă juridică)
    refs = set(state["complaint"].get("transaction_refs") or [])
    prior = next((d for d in c.rt.cases.all() if d.get("case_id") not in (None, c.case_id) and d.get("status") == "RAMBURSAT"
                  and refs & set((d.get("complaint") or {}).get("transaction_refs") or [])), None)
    if prior:
        await c.fact("rambursare", "refund.duplicate", "refund.issue", {"tx": sorted(refs)},
                     {"already_refunded_in": prior["case_id"]},
                     f"Plata a fost deja rambursată în cazul {prior['case_id']}: nu o rambursăm a doua oară")
        c.save({"status": "RAMBURSAT", "refund_of": prior["case_id"]})
        await c.finish("rambursare", f"Deja rambursată în {prior['case_id']}: nicio plată dublă")
        return {"refund": {"done": True, "status": "RAMBURSAT", "duplicate_of": prior["case_id"]}}
    key = f"refund-{c.case_id}"
    result = c.rt.repo.post_refund(c.case_id, customer_ref, amount, key)
    await c.fact("rambursare", "refund.instruction", "refund.issue", {"idempotency_key": key},
                 {"amount": amount, "result": result, "approved_by": approved_by, "decided_by": "MotorReguli"},
                 f"Instrucțiune de rambursare {money_ro(amount)} emisă de motorul de reguli"
                 + (f", aprobată de {approved_by}" if approved_by else " (sub plafon, fără semnale)"))
    # notificarea „Ți-am returnat…” o scrie core banking-ul (post_refund), ca orice altă tranzacție
    c.save({"status": "RAMBURSAT", "refunded_at": now().isoformat()})
    await c.em.custom("refund", f"Rambursat {money_ro(amount)}", {"amount": amount, "approved_by": approved_by},
                      step="rambursare", agent=AG["rambursare"])
    await c.finish("rambursare", f"Rambursat {money_ro(amount)} înainte de termenul T+1")
    return {"refund": {"done": True, "status": "RAMBURSAT", "amount": amount}}


# ---------------------------------------------------------------- 8. Dezbaterea (doar pe recuperare)


def _facts_brief(c: Ctx, limit: int = 30) -> tuple[str, set[str]]:
    facts = c.rt.ledger.facts(c.case_id)
    ids = {f.fact_id for f in facts}
    lines = [f"- {f.fact_id} [{f.kind}]: {f.summary}" for f in facts if f.kind not in ("complaint.received",)][:limit]
    brief, _ = c.rt.privacy.pseudonymize("\n".join(lines), c.case_id)  # nimic brut spre model
    return brief, ids


def _verify(lines: list[P.ArgLine], valid: set[str]) -> tuple[list[dict], int]:
    kept, rejected = [], 0
    for line in lines:
        cites = [x for x in line.cites if x in valid]
        if cites:
            kept.append({"text": line.text, "cites": cites})
        else:
            rejected += 1
    return kept, rejected


def _fallback_argument(side: str, ctx: dict, fm: dict) -> P.Argument:
    cite = lambda k: [fm[k]] if fm.get(k) else []  # noqa: E731
    if side == "procuror":
        claims = []
        if ctx.get("screen_showed_amount_and_payee"):
            claims.append(P.ArgLine(text="Ecranul de autentificare a afișat suma și beneficiarul, iar clientul a confirmat.",
                                    cites=cite("screen_showed_amount_and_payee")))
        if ctx.get("client_admits_sharing_credentials"):
            claims.append(P.ArgLine(text="Clientul recunoaște că a introdus datele cardului și codul pe pagina falsă.",
                                    cites=cite("client_admits_sharing_credentials")))
        if not claims:
            claims.append(P.ArgLine(text="Plata a cerut autentificare SCA reușită pe numele clientului.",
                                    cites=cite("sca_performed")))
        return P.Argument(claims=claims, missing_evidence=["înregistrarea completă a sesiunii"],
                          strongest_point=claims[0].text)
    claims = []
    if ctx.get("device_known") is False:
        claims.append(P.ArgLine(text="Plata a plecat de pe un dispozitiv nou, înrolat de escroc, nu de pe telefonul clientului.",
                                cites=cite("device_known")))
    if ctx.get("screen_showed_amount_and_payee") is False:
        claims.append(P.ArgLine(text="Codul SMS nu a afișat suma și beneficiarul, deci clientul nu putea ști ce aprobă.",
                                cites=cite("screen_showed_amount_and_payee")))
    if fm.get("domain_lookalike"):
        claims.append(P.ArgLine(text="Pagina falsă imita foarte bine banca, pe un domeniu creat cu câteva ore înainte.",
                                cites=[fm["domain_lookalike"]] + cite("domain_rdap")))
    if ctx.get("seconds_after_click") is not None:
        claims.append(P.ArgLine(text=f"Plata a venit la {ctx['seconds_after_click']} de secunde după click: atac automatizat, rapid.",
                                cites=cite("seconds_after_click")))
    if not claims:
        claims.append(P.ArgLine(text="Folosirea instrumentului de plată nu dovedește singură neglijența gravă (art. 171).",
                                cites=cite("sca_performed") or cite("amount")))
    return P.Argument(claims=claims, missing_evidence=[], strongest_point=claims[0].text)


def rubric(ctx: dict, fm: dict) -> tuple[list[dict], int]:
    """Rubrica deterministă a Cântăritorului: indicatori obiectivi cu ponderi publice."""
    items = [
        ("Ecranul a afișat suma și beneficiarul", ctx.get("screen_showed_amount_and_payee") is True, 3, "screen_showed_amount_and_payee"),
        ("Clientul recunoaște că a dat datele sau codul", ctx.get("client_admits_sharing_credentials") is True, 2, "client_admits_sharing_credentials"),
        ("Clientul recunoaște că a aprobat în aplicație", ctx.get("client_admits_approving_in_app") is True, 2, "client_admits_approving_in_app"),
        ("Plata de pe dispozitiv nou (pro client)", ctx.get("device_known") is False, -2, "device_known"),
        ("Atac rapid: plata sub 5 minute de la click (pro client)", (ctx.get("seconds_after_click") or 10**6) < 300, -1, "seconds_after_click"),
        ("SIM swap înainte de plată (pro client)", ctx.get("sim_swap_hours_before") is not None, -3, "sim_swap_hours_before"),
    ]
    rows = [{"indicator": name, "value": bool(value), "weight": weight, "cites": [fm[key]] if fm.get(key) else []}
            for name, value, weight, key in items]
    score = sum(r["weight"] for r in rows if r["value"])
    return rows, score


async def dezbatere(state: dict) -> dict:
    c = Ctx(state)
    ctx = state["rule_context"]
    fm = ctx.get("fact_ids") or {}
    if ctx["dispute_type"] != "neautorizata" or not state.get("refund", {}).get("done") and \
            (_decision(state, Question.RAMBURSARE_T1) or {}).get("decision") not in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE"):
        for step in ("procuror", "avocat", "cantaritor"):
            c.track(step, "skipped", "Fără dezbatere: nu e traseu de recuperare de la client")
        return {"debate": {"ran": False}}
    brief, valid = _facts_brief(c)
    question = ("Probe din registru:\n" + brief +
                "\n\nÎntrebarea: există probe pentru un dosar de recuperare de la client (neglijență gravă)?")
    await c.start("procuror", "Procurorul argumentează pentru recuperare (Opus), cu citări")
    await c.start("avocat", "Avocatul argumentează pentru client (alt model), cu citări")

    async def statement(side: str) -> tuple[P.Argument, Any]:
        system = P.PROCUROR_SYSTEM if side == "procuror" else P.AVOCAT_SYSTEM
        role = Role.OPUS if side == "procuror" else Role.SONNET
        return await c.rt.llm.structured(role=role, agent=AG[side], system=system, user=question, schema=P.Argument,
                                         effort="medium", max_tokens=3000,
                                         fallback=lambda: _fallback_argument(side, ctx, fm))

    (pro, pro_info), (con, con_info) = await asyncio.gather(statement("procuror"), statement("avocat"))

    async def rebut(side: str, other: P.Argument) -> tuple[P.Argument, Any]:
        system = (P.PROCUROR_SYSTEM if side == "procuror" else P.AVOCAT_SYSTEM) + "\n" + P.REBUTTAL_HINT
        role = Role.OPUS if side == "procuror" else Role.SONNET
        other_text = "\n".join(f"- {l.text} {l.cites}" for l in other.claims)
        return await c.rt.llm.structured(role=role, agent=AG[side], system=system,
                                         user=question + "\n\nDeclarația celeilalte părți:\n" + other_text,
                                         schema=P.Argument, effort="low", max_tokens=2000,
                                         fallback=lambda: P.Argument(claims=[], missing_evidence=[], strongest_point=""))

    (pro_r, _), (con_r, _) = await asyncio.gather(rebut("procuror", con), rebut("avocat", pro))
    pro_lines, pro_bad = _verify(pro.claims + pro_r.claims, valid)
    con_lines, con_bad = _verify(con.claims + con_r.claims, valid)
    await c.finish("procuror", f"{len(pro_lines)} afirmații cu surse ({pro_bad} respinse fără sursă)",
                   {"lines": pro_lines, "llm": pro_info.as_dict()})
    await c.finish("avocat", f"{len(con_lines)} afirmații cu surse ({con_bad} respinse fără sursă)",
                   {"lines": con_lines, "llm": con_info.as_dict()})

    await c.start("cantaritor", "Cântăresc indicatorii cu rubrica deterministă")
    rows, score = rubric(ctx, fm)
    rules_rec = (_decision(state, Question.RECUPERARE_CLIENT) or {}).get("decision") or (
        "RECUPERARE_PROPUSA" if score >= 3 else "NU_RECOMANDAM_RECUPERARE")
    rubric_rec = "RECUPERARE_PROPUSA" if score >= 3 else "NU_RECOMANDAM_RECUPERARE"
    agree = rubric_rec == rules_rec
    debate = {"ran": True, "prosecutor": pro_lines, "defender": con_lines, "rubric": rows, "score": score,
              "recommendation": rules_rec, "rubric_recommendation": rubric_rec, "agree_with_rules": agree,
              "rejected_without_citation": pro_bad + con_bad,
              "missing_evidence": list(dict.fromkeys(pro.missing_evidence + con.missing_evidence))[:6],
              "models": {"procuror": pro_info.model, "avocat": con_info.model}}
    await c.fact("cantaritor", "debate.rubric", "debate.cantaritor", {"score": score},
                 {"rubric": rows, "recommendation": rules_rec, "agree_with_rules": agree},
                 f"Rubrica: scor {score}; recomandare {rules_rec}" + ("" if agree else " (dezacord cu regulile: decide omul)"))
    c.save({"debate": debate})
    await c.finish("cantaritor", f"Recomandare: {rules_rec.replace('_', ' ').lower()} (scor {score})")
    return {"debate": debate}


# ---------------------------------------------------------------- 9. Recuperarea de la escroc


def camt056(case_id: str, tx: dict, amount: float, currency: str) -> str:
    """Cerere de anulare ISO 20022 camt.056.001.08 cu motivul FRAD (ciornă, nu se trimite automat)."""
    ts = now().strftime("%Y-%m-%dT%H:%M:%S")
    e2e = g(tx, "end_to_end_id", "e2e_id", "id", default=case_id)
    bic = g(tx, "beneficiary_bic", default="NOTPROVIDED")
    settle = (parse_dt(g(tx, "executed_at", "ts")) or now()).strftime("%Y-%m-%d")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.056.001.08">
  <FIToFIPmtCxlReq>
    <Assgnmt>
      <Id>VERSOML-{case_id}</Id>
      <Assgnr><Agt><FinInstnId><BICFI>BDEMROBU</BICFI></FinInstnId></Agt></Assgnr>
      <Assgne><Agt><FinInstnId><BICFI>{bic}</BICFI></FinInstnId></Agt></Assgne>
      <CreDtTm>{ts}</CreDtTm>
    </Assgnmt>
    <Undrlyg>
      <TxInf>
        <CxlId>CXL-{case_id}</CxlId>
        <OrgnlEndToEndId>{e2e}</OrgnlEndToEndId>
        <OrgnlIntrBkSttlmAmt Ccy="{currency}">{amount:.2f}</OrgnlIntrBkSttlmAmt>
        <OrgnlIntrBkSttlmDt>{settle}</OrgnlIntrBkSttlmDt>
        <CxlRsnInf><Rsn><Cd>FRAD</Cd></Rsn><AddtlInf>Plata contestata de platitor ca frauda</AddtlInf></CxlRsnInf>
      </TxInf>
    </Undrlyg>
  </FIToFIPmtCxlReq>
</Document>"""


async def recuperare(state: dict) -> dict:
    c = Ctx(state)
    await c.start("recuperare", "Pregătesc recuperarea: rechemare, chargeback și raportul DNSC (ciorne)")
    ctx = state["rule_context"]
    records = state.get("records") or {}
    tx = records.get("transaction") or {}
    rules = state.get("rules") or {}
    escroc = _decision(state, Question.RECUPERARE_ESCROC) or {}
    amount = float((ctx.get("amount") or {}).get("value", 0))
    currency = (ctx.get("amount") or {}).get("currency", "RON")
    recovery: dict = {"decision": escroc.get("decision"), "rule_ids": escroc.get("rule_ids", [])}

    hit = next((h for h in rules.get("hits", []) if "chargeback" in (h.get("title", "") + h.get("outcome", "")).lower()
                or h.get("rule_id") == "DSP-52"), None)
    if ctx["channel"] == "card":
        reason = (hit or {}).get("params", {}).get("reason_code") or (
            "10.4" if ctx.get("eci") in ("07", "7") else "12.6.1" if ctx.get("duplicate_of") else None)
        eligible = escroc.get("decision") == "CHARGEBACK"
        recovery["chargeback"] = {"eligible": eligible, "reason_code": reason,
                                  "explanation": (hit or {}).get("explanation") or (
                                      "Chargeback posibil." if eligible else
                                      "Plata a fost autentificată cu Visa Secure (ECI 05 + CAVV): codul 10.4 nu e valid, "
                                      "pierderea rămâne la bancă; urmează recuperarea pe alte căi.")}
    else:
        bene = g(tx, "beneficiary_iban", "counterparty_iban", "to_iban") or ""
        internal = "BDEM" in bene[:8].upper()
        recovery["recall"] = {
            "kind": "interna" if internal else ("camt.056" if currency == "EUR" else "rechemare_ron"),
            "xml": None if internal else camt056(c.case_id, tx, amount, currency),
            "note": ("Beneficiarul are cont la Banca Demo: cerere internă de restituire către Operațiuni."
                     if internal else "Ciornă de rechemare; procedura RON între bănci se confirmă cu mentorii [U]."),
            "deadline": next((dl["due_at"] for dl in rules.get("deadlines", []) if "rechem" in dl.get("name", "").lower()), None),
        }
    attack = records.get("attack") or {}
    if attack.get("domain") or attack.get("phones"):
        public = {"domeniu": attack.get("domain"), "url": attack.get("url"), "telefoane": attack.get("phones"),
                  "varsta_domeniu_ore": attack.get("domain_age_hours"), "scor_sosie": attack.get("lookalike_score"),
                  "canal": (state.get("extracted") or {}).get("contacted_by")}
        # telefonul escrocului e public, dar garda nu-l poate deosebi de al unui client: la model ajunge ca etichetă
        masked, vault = c.rt.privacy.pseudonymize(_json(public), c.case_id)
        draft, info = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["recuperare"], system=P.DNSC_SYSTEM,
            user="Indicatori publici ai atacului (JSON):\n" + masked, schema=P.DnscDraft, effort="low",
            max_tokens=1500,
            fallback=lambda: P.DnscDraft(
                title=f"Phishing: {attack.get('domain') or 'apel fraudulos'}",
                body=(f"Raportăm o campanie de phishing care imită Banca Demo. Domeniu: {attack.get('domain')}. "
                      f"URL: {attack.get('url')}. Domeniul pare înregistrat de "
                      f"{attack.get('domain_age_hours') or '?'} ore. Vă rugăm să analizați blocarea."),
                indicators=[x for x in [attack.get("domain"), attack.get("url"), *(attack.get("phones") or [])] if x]))
        restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
        recovery["dnsc_report"] = {"title": restore(draft.title), "text": restore(draft.body),
                                   "indicators": [restore(x) for x in draft.indicators],
                                   "channel": "pnrisc.dnsc.ro / 1911", "status": "ciornă: trimite un om"}
    await c.fact("recuperare", "recovery.drafts", "recall.draft", {"decision": escroc.get("decision")},
                 {k: v for k, v in recovery.items() if k != "decision"},
                 "Ciorne de recuperare pregătite: " + ", ".join(k for k in ("recall", "chargeback", "dnsc_report") if k in recovery))
    c.save({"recovery": recovery})
    await c.finish("recuperare", "Ciornele de recuperare așteaptă trimiterea de către un om")
    return {"recovery": recovery}


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str, indent=1)


# ---------------------------------------------------------------- 10. Scrisoarea + filtrul zidului


ADR_BLOCK = ("Dacă nu sunteți de acord cu răspunsul nostru, vă puteți adresa Autorității Naționale pentru Protecția "
             "Consumatorilor (ANPC), Agenției Naționale de Administrare Fiscală (ANAF), Băncii Naționale a României "
             "(BNR) sau Centrului de Soluționare Alternativă a Litigiilor în Domeniul Bancar (CSALB), precum și "
             "instanței competente.")


def _fallback_letter(state: dict) -> P.LetterOut:
    ctx = state["rule_context"]
    t1 = _decision(state, Question.RAMBURSARE_T1) or {}
    ans = _decision(state, Question.RASPUNS_RECLAMATIE) or {}
    amount = money_ro(float((ctx.get("amount") or {}).get("value", 0)))
    fm = ctx.get("fact_ids") or {}
    verdict = t1.get("decision")
    if verdict in ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE"):
        main = (f"Am analizat contestația dumneavoastră și vă returnăm suma de {amount}, conform Legii 209/2019 "
                "(art. 173) și hotărârii Curții de Justiție a Uniunii Europene în cauza C-70/25. Rambursarea se face "
                "cel târziu până la sfârșitul zilei lucrătoare următoare notificării.")
    elif verdict == "NU_SE_APLICA_T1":
        main = (f"Am analizat contestația privind plata de {amount}. Din jurnalele noastre reiese că plata a fost "
                "autorizată din aplicația dumneavoastră, așa că nu intră sub regula de rambursare a plăților "
                "neautorizate. Am inițiat deja demersurile de recuperare a sumei de la banca beneficiarului.")
    elif verdict == "RESPINGE_TARDIV":
        main = ("Notificarea a fost transmisă după termenul de 13 luni de la data plății prevăzut de art. 169 din "
                "Legea 209/2019, motiv pentru care nu putem aproba rambursarea.")
    else:
        main = "Am analizat contestația dumneavoastră și vă comunicăm rezultatul mai jos."
    paragraphs = [
        P.LetterParagraph(text="Stimată doamnă / Stimate domn <CLIENT_1>,", cites=[]),
        P.LetterParagraph(text=main, cites=[x for x in [fm.get("amount"), fm.get("notified_at")] if x]),
    ]
    points = []
    for point in (state.get("extracted") or {}).get("points", [])[:4]:
        paragraphs.append(P.LetterParagraph(text=f"Referitor la solicitarea „{point['text']}”: am inclus-o în analiza "
                                                 "de mai sus, iar răspunsul nostru este cel comunicat.", cites=[]))
        points.append(point["text"])
    paragraphs.append(P.LetterParagraph(
        text=("Dacă nu sunteți de acord cu răspunsul, ne puteți scrie din nou sau vă puteți adresa Autorității "
              "Naționale pentru Protecția Consumatorilor (ANPC), Agenției Naționale de Administrare Fiscală (ANAF), "
              "Băncii Naționale a României (BNR), Centrului de Soluționare Alternativă a Litigiilor în Domeniul "
              "Bancar (CSALB) ori instanței competente."
              + (f" Termenul nostru de răspuns la reclamație este {ans.get('deadline', '')[:10]}." if ans.get("deadline") else "")),
        cites=[]))
    paragraphs.append(P.LetterParagraph(text="Cu stimă,\nEchipa Contestații, Banca Demo", cites=[]))
    return P.LetterOut(subject="Răspuns la contestația dumneavoastră", paragraphs=paragraphs, points_answered=points)


async def redactor(state: dict) -> dict:
    c = Ctx(state)
    await c.start("redactor", "Redactez răspunsul către client, la fiecare punct, cu termene și căi de atac")
    ctx = state["rule_context"]
    decisions = [d for d in state.get("decisions", []) if d.get("question") in
                 ("rambursare_t1", "raspuns_reclamatie", "recuperare_escroc")]
    brief = {
        "decizii": [{"intrebare": d["question"], "decizie": d["decision"], "termen": d.get("deadline"),
                     "explicatii": [r.get("text") for r in d.get("rationale", [])][:3]} for d in decisions],
        "suma": ctx.get("amount"), "puncte": [p["text"] for p in (state.get("extracted") or {}).get("points", [])],
        "status": (c.rt.cases.get(c.case_id) or {}).get("status"),
        "probe_disponibile": sorted({v for v in (ctx.get("fact_ids") or {}).values()})[:20],
    }
    message_id = f"letter-{c.case_id}"
    out, info = await c.rt.llm.structured(
        role=Role.SONNET, agent=AG["redactor"], system=P.LETTER_SYSTEM,
        user="Datele pentru scrisoare (JSON):\n" + _json(brief), schema=P.LetterOut, effort="low", max_tokens=3000,
        fallback=lambda: _fallback_letter(state))
    valid = {f.fact_id for f in c.rt.ledger.facts(c.case_id)}
    cites = sorted({x for p in out.paragraphs for x in p.cites if x in valid})
    pseudo_body = "\n\n".join(p.text for p in out.paragraphs)
    # verificările CMP din motorul de reguli: fiecare punct primește răspuns (CMP-01), blocul de sesizare (CMP-03)
    from versoml.shared.rules import check_complaint_letter

    points = [p["text"] for p in (state.get("extracted") or {}).get("points", [])]
    cmp_hits = check_complaint_letter(pseudo_body, points, out.points_answered)
    if any(h.outcome == "CMP_ADR_BLOCK_MISSING" for h in cmp_hits):
        pseudo_body += "\n\n" + ADR_BLOCK
        cmp_hits = check_complaint_letter(pseudo_body, points, out.points_answered)
        await c.em.custom("rule_hit", "CMP-03: blocul ANPC / ANAF / BNR / CSALB lipsea și a fost adăugat",
                          {"rule_id": "CMP-03", "outcome": "bloc_adaugat"}, step="redactor", agent=AG["redactor"])
    cmp_checks = [{"rule_id": h.rule_id, "outcome": h.outcome, "explanation": h.explanation} for h in cmp_hits]
    await c.finish("redactor", f"Scrisoare redactată ({info.mode}); {len(out.points_answered)} puncte acoperite",
                   {"llm": info.as_dict(), "cmp": cmp_checks})

    await c.start("filtru_zid", "Trec scrisoarea prin filtrul zidului: termeni interziși, canary, date personale")
    from versoml.wall.letter_filter import check_letter

    result = check_letter(pseudo_body)
    if not result.passed and not result.canaries_found and result.blocked_terms:
        # auto-corectare: o singură rescriere, cu motivele filtrului; dacă și ea cade, decide un om
        await c.em.custom("wall_block", "Filtrul a oprit prima variantă; Redactorul o rescrie fără formulările interzise",
                          result.model_dump(mode="json"), step="filtru_zid", agent=AG["filtru_zid"])
        feedback = ("\n\nVersiunea anterioară a fost oprită de filtrul zidului pentru formulările: "
                    + ", ".join(result.blocked_terms) + ". Rescrie scrisoarea fără ele și fără orice referire la "
                    "monitorizare, semnalări sau suspiciuni.")
        retry, _ = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["redactor"], system=P.LETTER_SYSTEM,
            user="Datele pentru scrisoare (JSON):\n" + _json(brief) + feedback, schema=P.LetterOut, effort="low",
            max_tokens=3000, fallback=lambda: _fallback_letter(state))
        candidate = "\n\n".join(p.text for p in retry.paragraphs)
        if not any(h.outcome == "bloc_prezent" for h in check_complaint_letter(candidate, points, retry.points_answered)):
            candidate += "\n\n" + ADR_BLOCK
        second = check_letter(candidate)
        if second.passed:
            out, pseudo_body, result = retry, candidate, second
            cites = sorted({x for p in out.paragraphs for x in p.cites if x in valid})
    vault = (state.get("pseudo") or {}).get("vault") or {}
    body = c.rt.privacy.restore(pseudo_body, vault)
    body = re.sub(r"<CLIENT_\d+>", "client", body)
    status = "draft" if result.passed else "blocked"
    letter = {"case_id": c.case_id, "subject": out.subject, "body": body, "cites": cites,
              "points_answered": out.points_answered, "filter": result.model_dump(mode="json"), "status": status,
              "cmp_checks": cmp_checks}
    if not result.passed:
        c.rt.record_block(c.case_id, result.reasons, result.blocked_terms)
        await c.em.custom("wall_block", "Zidul a blocat scrisoarea: " + "; ".join(result.reasons[:2]),
                          result.model_dump(mode="json"), step="filtru_zid", agent=AG["filtru_zid"])
    await c.fact("filtru_zid", "letter.checked", "letters.check_letter", {"chars": len(body)},
                 {"passed": result.passed, "blocked_terms": result.blocked_terms, "canaries": result.canaries_found,
                  "sha256_letter": hashlib.sha256(body.encode()).hexdigest()},
                 "Scrisoarea a trecut filtrul zidului" if result.passed else "Scrisoarea a fost BLOCATĂ de zid")
    c.save({"letter": letter})
    await c.finish("filtru_zid", "Scrisoare curată: 0 termeni interziși, 0 canary" if result.passed
                   else "Blocată și trimisă la un om", status="done" if result.passed else "blocked")
    return {"letter": letter}


# ---------------------------------------------------------------- 11. Sigiliul registrului


async def sigiliu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("sigiliu", "Sigilez dosarul: rădăcină Merkle semnată Ed25519 și cod QR")
    seal = c.rt.ledger.seal(c.case_id)
    summary = {k: seal.get(k) for k in ("root", "count", "sealed_at", "signature")}
    await c.em.custom("ledger_seal", f"Dosar sigilat: {seal.get('count')} probe, rădăcina {str(seal.get('root'))[:16]}…",
                      summary, step="sigiliu", agent=AG["sigiliu"])
    doc = c.rt.cases.get(c.case_id) or {}
    c.save({"ledger": {"count": seal.get("count"), "root": seal.get("root"), "sealed": True},
            "finished_at": now().isoformat(), "status": doc.get("status") or "INCHIS"})
    await c.finish("sigiliu", f"Sigilat: {seal.get('count')} probe")
    return {"sealed": True}


def new_run_id() -> str:
    return "RUN-" + uuid.uuid4().hex[:8]
