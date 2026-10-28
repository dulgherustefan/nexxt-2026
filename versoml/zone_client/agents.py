"""The dispute judge's agents (client zone).

Each graph node receives the case state, emits AG-UI events, writes evidence to the ledger through Cedar-checked
tools and returns only its own updates. The LLM extracts, argues and drafts; the rules engine decides; a person
approves anything unfavorable or over the cap.

Node IDs, event types, verdict and status codes stay as they are (the console matches on them); everything a
person reads is plain English (US spelling, money as "RON 3,200.00", dates as "29 Oct 2026, 23:59").
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
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
from versoml.zone_client.fmt import fmt_date, fmt_datetime, fmt_deadline, money, to_local
from versoml.zone_client.runtime import ClientRuntime, get_runtime

log = logging.getLogger("versoml.client.agents")

BANK = P.BANK_NAME

AG = {
    "receptor": "Intake",
    "clasificator": "Classifier",
    "ceasornicar": "Deadline clock",
    "colector_tranzactie": "Transaction collector",
    "colector_sca": "SCA collector",
    "colector_dispozitiv": "Device collector",
    "colector_domeniu": "Domain collector",
    "motor_reguli": "Rules engine",
    "outbox_aml": "Diode",
    "rambursare": "Refund",
    "procuror": "Prosecutor",
    "avocat": "Defender",
    "cantaritor": "Weigher",
    "recuperare": "Recovery",
    "redactor": "Letter writer",
    "filtru_zid": "Letter check",
    "sigiliu": "Seal",
}

PIPELINE_NODES = [
    {"id": "receptor", "label": "Intake", "model": "haiku", "lane": "intrare",
     "hint": "Isolated LLM with no tools: pulls typed fields out of untrusted text"},
    {"id": "clasificator", "label": "Classifier", "model": "ml", "lane": "intrare",
     "hint": "M1: TF-IDF and calibrated logistic regression"},
    {"id": "ceasornicar", "label": "Deadline clock", "model": "no LLM", "lane": "intrare",
     "hint": "Next business day, 15/35 business days, 13 months, Romanian bank holidays"},
    {"id": "colector_tranzactie", "label": "Transaction", "model": "no LLM", "lane": "probe",
     "hint": "bank-core: the payment, the payee, the history"},
    {"id": "colector_sca", "label": "SCA", "model": "no LLM", "lane": "probe",
     "hint": "sca-logs: the method and what the screen showed"},
    {"id": "colector_dispozitiv", "label": "Device", "model": "no LLM", "lane": "probe",
     "hint": "device: new device, seconds after the click, SIM swap"},
    {"id": "colector_domeniu", "label": "Fake domain", "model": "no LLM", "lane": "probe",
     "hint": "domain-intel: RDAP, CT, lookalike score (M3), page similarity (M4)"},
    {"id": "motor_reguli", "label": "Rules engine", "model": "no LLM", "lane": "decizie",
     "hint": "PAY, DSP, CMP, DP, REC: a rule ID behind every decision"},
    {"id": "outbox_aml", "label": "Diode to AML", "model": "no LLM", "lane": "zid",
     "hint": "DisputeFacts only, HMAC-signed, strict schema"},
    {"id": "rambursare", "label": "Refund", "model": "no LLM", "lane": "decizie",
     "hint": "only the rules engine can issue the instruction"},
    {"id": "procuror", "label": "Prosecutor", "model": "opus", "lane": "recuperare",
     "hint": "the case for gross negligence, with citations"},
    {"id": "avocat", "label": "Defender", "model": "sonnet", "lane": "recuperare",
     "hint": "the customer's case, with citations, on a different model"},
    {"id": "cantaritor", "label": "Weigher", "model": "no LLM", "lane": "recuperare",
     "hint": "fixed rubric; a person signs"},
    {"id": "recuperare", "label": "Recovery", "model": "sonnet", "lane": "recuperare",
     "hint": "camt.056 FRAD, chargeback, DNSC report: drafts only"},
    {"id": "redactor", "label": "Letter", "model": "sonnet", "lane": "iesire",
     "hint": "answers every point, with deadlines and where to complain"},
    {"id": "filtru_zid", "label": "Letter check", "model": "no LLM", "lane": "zid",
     "hint": "forbidden terms, canary tokens, personal data"},
    {"id": "sigiliu", "label": "Seal", "model": "no LLM", "lane": "iesire",
     "hint": "Merkle root, Ed25519 signature, QR code"},
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

# ---------------------------------------------------------------- what the codes mean, for people

CHANNEL_LABELS = {"card": "card", "transfer": "transfer", "transfer_instant": "instant transfer"}
DISPUTE_LABELS = {"neautorizata": "unauthorized payment", "app": "authorized push payment (APP)",
                  "disputa_comerciant": "merchant dispute", "eroare_procesare": "processing error"}
PAYMENT_KINDS = {"card": "card payment", "transfer": "transfer", "transfer_instant": "instant transfer"}
SCENARIO_LABELS = {
    "phishing_link": "phishing link", "card_ecom_fara_3ds": "online card payment without 3-D Secure",
    "card_visa_secure": "card payment approved with Visa Secure", "vishing_securitate": "fake bank security call",
    "cont_sigur": "'safe account' scam", "sim_swap": "SIM swap", "frauda_client": "customer disputing their own payment",
    "reclamatie_tardiva": "late claim", "plata_dubla": "double charge", "inel_carausi": "money mule ring",
    "injectie_document": "complaint with hidden instructions", "marfa_nelivrata": "goods not delivered",
}
VERDICT_LABELS = {
    "RAMBURSEAZA": "refund now",
    "RAMBURSEAZA_CU_APROBARE": "refund once a person approves",
    "EXCEPTIE_FRAUDA_CLIENT": "fraud exception, no refund for now",
    "RESPINGE_TARDIV": "reject, reported too late",
    "NU_SE_APLICA_T1": "the next-business-day refund rule does not apply",
    "CHARGEBACK": "chargeback",
    "RECHEMARE": "recall the transfer",
    "RECUPERARE_PROPUSA": "propose recovery from the customer",
    "NU_RECOMANDAM_RECUPERARE": "do not recover from the customer",
    "INFORMATII_SUPLIMENTARE": "ask for more information",
    "INCHIDE": "close the case",
}
SOURCE_LABELS = {"app": "the app", "email": "email", "branch": "a branch", "call_center": "the call center",
                 "web_form": "the web form"}
CONTACT_LABELS = {"sms": "SMS", "apel": "phone call", "email": "email", "mesagerie": "messaging app",
                  "site": "website", "necunoscut": "unknown"}


def label(table: dict[str, str], code: Any) -> str:
    value = getattr(code, "value", code)
    return table.get(str(value), str(value).replace("_", " ")) if value else "unknown"


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


# ---------------------------------------------------------------- why a refund waits for a signature

# outcome code of a rule hit -> the reason a person has to sign the refund (in hit order, no repeats)
ESCALATION_REASONS: dict[str, str] = {
    "DSP_AUTH_AMBIGUOUS": "the dispute could fit more than one fraud pattern",
    "semnale_autentificare": "the authentication signals need a check",
    "DSP_AMOUNT_REVIEW": "the amount is above the automatic refund limit",
    "semnale_de_risc": "the customer has risk signals",
    # the other causes the engine escalates on
    "DSP_SECURITY_SIGNAL": "the complaint text contains instructions or an amount that does not match our records",
    "suma_de_confirmat": "the amount in the customer's document needs checking against our records",
    "PAY_FRAUD_NOTICE_MISSING": "a fraud hold came in but the authority has not been told in writing",
    "DSP_CE3_MET": "earlier undisputed card payments match this one (Visa CE3.0)",
}
GENERIC_ESCALATION = "the amount is over the cap or there are risk signals"


def escalation_reasons(hits: list[dict] | None) -> list[str]:
    """The reasons behind a sign-off, from the rule hits: in hit order, each reason once."""
    reasons: list[str] = []
    for hit in hits or []:
        outcome = hit.get("outcome") if isinstance(hit, dict) else getattr(hit, "outcome", None)
        reason = ESCALATION_REASONS.get(str(outcome or ""))
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def join_and(items: list[str]) -> str:
    """["a"] -> "a"; ["a", "b"] -> "a and b"; ["a", "b", "c"] -> "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def refund_approval_prompt(amount: float, deadline: Any, hits: list[dict] | None, currency: str = "RON") -> str:
    """The question the operator answers for RAMBURSEAZA_CU_APROBARE, with the real reasons for the sign-off."""
    reasons = escalation_reasons(hits) or [GENERIC_ESCALATION]
    when = fmt_deadline(deadline)
    by = f"by {when}" if when else "by the refund deadline"
    return f"Refund {money(amount, currency)} {by}? Sign-off is needed because {join_and(reasons)}."


# ---------------------------------------------------------------- helpers


def normalize_ro(text: str) -> str:
    """s/t with a cedilla (U+015F, U+0163) -> ș/ț with a comma (Romanian text can still come in)."""
    return (text or "").translate(str.maketrans({"\u015f": "ș", "\u0163": "ț", "\u015e": "Ș", "\u0162": "Ț"}))


_RO_WORDS = re.compile(r"\b(?:și|si|nu|că|să|pe|din|mi|banii|contul|plata|vă|rog|pentru|este|care|am)\b", re.I)
_EN_WORDS = re.compile(r"\b(?:the|and|my|i|was|to|of|it|that|this|for|is|me|didn't|don't|i'm)\b", re.I)


def guess_language(text: str) -> str:
    """'ro' or 'en', from common words and Romanian diacritics (good enough for a label on the extraction)."""
    text = text or ""
    ro = len(_RO_WORDS.findall(text)) + len(re.findall(r"[ăâîșț\u015f\u0163]", text.lower()))
    return "ro" if ro > len(_EN_WORDS.findall(text)) else "en"


def g(d: dict | None, *keys: str, default: Any = None) -> Any:
    """The first key present among the variants (the data schemas can name fields differently)."""
    if not d:
        return default
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


SCA_METHOD = {"app_push": "SCA in the banking app", "sms_otp": "SCA by SMS code", "none": "No SCA"}


def wrap_data(tag: str, text: str) -> str:
    """Untrusted text between an opening and a closing tag that carry the same random ID, so the text cannot close
    the block itself. The ID is 16 hex characters: the LLM client strips those from replay keys."""
    rid = secrets.token_hex(8)
    return f'<{tag} id="{rid}">\n{text}\n</{tag} id="{rid}">'


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


# Patterns on the folded text (lower case, no diacritics): instructions aimed at the system, hidden or dressed
# up as "internal notes". Romanian and English. A customer asking for their money back never matches.
INJECTION_PATTERNS = [
    # Romanian
    r"ignora\w*\s+(toate\s+)?(regulile|instructiunile|cele de mai sus|verificarile)",
    r"aproba\s+(imediat\s+|acum\s+)?(rambursarea|plata|cererea)",
    r"\besti\s+acum\s+", r"nu\s+mai\s+aplica\s+regul",
    r"\[\s*instructiune", r"instructiune\s+(oficiala|interna|pentru\s+(asistent|sistem|model|ai))",
    r"\basistent(ul|ule|ului)?\b[^.]{0,60}\b(nu|trimite|aproba|ignora|rambursea|marcheaza|scrie)",
    r"\b(trimite|transfera|vireaza|returneaza)\s+(imediat\s+)?banii\s+(acum|imediat|fara)",
    r"\bnu\s+mentiona\b", r"\b(note|nota)\s+pentru\s+(sistem|asistent|model|ai)\b",
    # English
    r"\bsystem\s*prompt\b", r"\bignore\s+(all\s+)?(previous|prior)\b",
    r"\byou\s+are\s+now\s+(an?|the|in|acting|operating|playing|free|unrestricted|allowed|authori[sz]ed|permitted)\b",
    r"\b(ignore|disregard|forget|override|bypass)\s+(\w+\s+){0,3}?(rules|instructions|guidelines|prompts?|checks"
    r"|verifications|polic(y|ies))\b",
    r"\b(ignore|disregard|forget)\s+(everything|all|anything)\s+(above|before|previous\w*|prior|else)\b",
    r"\b(updated|hidden|secret|system|revised)\s+instructions?\s*:", r"\b(jailbreak|developer\s+mode)\b",
    r"\binstructions?\s+(for|to)\s+(the\s+)?(ai|assistant|system|model|bot|llm|automated)\b",
    r"\bnotes?\s+(for|to)\s+(the\s+)?(automated\s+|automatic\s+|ai\s+)?(system|assistant|model|ai|bot|llm)\b",
    r"\b(set|change|switch|update)\s+(the\s+)?(decision|verdict|status|outcome)\s*[=:]",
    r"\b(decision|verdict)\s*=\s*\w+",
    r"\b(do\s+not|don'?t|never|no\s+need\s+to)\s+(escalate|involve\s+a\s+human|loop\s+in)\b",
    r"\bwithout\s+(a\s+|any\s+)?human\s+(review|check|approval|sign-?off|oversight)\b",
    r"\bthis\s+is\s+an?\s+(official|internal|direct|system|priority|authori[sz]ed)\s+(instruction|order|command"
    r"|directive|override)\b",
    r"\[\s*(internal|system|official|admin|priority|hidden|secret)?\s*(instruction|directive|command)",
    r"(^|[\n.!?:;]\s*|[(\[]\s*)(dear\s+|hey\s+|hi\s+)?(ai\s+|virtual\s+|automated\s+)?assistant\s*[,:]",
    r"\bdear\s+(ai|model|bot|system|llm)\b", r"\bas\s+an?\s+(ai|language\s+model|llm)\b",
    r"\bif\s+(an?\s+|the\s+)?(ai|bot|model|llm|automated\s+system|assistant)\s+(is\s+)?read(s|ing)?\b",
    r"\b(approve|refund|pay\s+out|close|process)\s+(\S+\s+){0,6}?without\s+(any\s+)?(further\s+|more\s+"
    r"|additional\s+|other\s+)?(checks|verification|review|escalation)\b",
    r"\bskip\s+(all\s+|any\s+)?(the\s+)?(usual\s+|normal\s+|standard\s+|fraud\s+|security\s+)?(checks|verifications?"
    r"|review|rules)\b",
    r"\bact\s+as\s+(an?\s+|the\s+)?(\w+\s+)?(approver|administrator|admin|supervisor|system|assistant)\b",
    # either language: markup and invisible characters
    r"<\s*/?\s*(system|instructions?)\s*>", r"<!--", "[​‌‍⁠]",
]
# On the original text: the engine's verdict codes. A customer has no reason to write them in capitals.
CASED_INJECTION_PATTERNS = [r"\b(RAMBURSEAZA(_CU_APROBARE)?|NU_SE_APLICA_T1|EXCEPTIE_FRAUDA_CLIENT|RESPINGE_TARDIV)\b"]


def _fold(text: str) -> str:
    """Lower case, no diacritics, same length (so the quote comes from the original text)."""
    import unicodedata

    return "".join((unicodedata.normalize("NFKD", ch)[:1] if ch.isalpha() else ch) for ch in (text or "")).lower()


def detect_injection(text: str) -> str | None:
    folded = _fold(text)
    found = [m for m in (re.search(p, folded) for p in INJECTION_PATTERNS) if m]
    found += [m for m in (re.search(p, text or "") for p in CASED_INJECTION_PATTERNS) if m]
    if not found:
        return None
    match = min(found, key=lambda m: m.start())
    start = max(match.start() - 30, 0)
    return text[start: match.end() + 40].strip()


URL_RE = re.compile(r"https?://[^\s\"'<>)]+|\b(?:[a-z0-9-]+\.)+(?:example|test|ro|com|net|info|xyz|top|online|site)\b(?:/[^\s\"'<>)]*)?", re.I)
PHONE_RE = re.compile(r"(?:\+40|0040|\b0)\s?7\d{2}[\s.-]?\d{3}[\s.-]?\d{3}\b|<TELEFON_\d+>")
_NUM = r"\d{1,3}(?:[., ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
# "RON 3,200.00", "3,200 RON", "3.200,00 lei", "3200 de lei"
AMOUNT_RE = re.compile(rf"\b(?:ron|lei)\s*({_NUM})(?!\d)|(?<![\d.,])({_NUM})\s*(?:de\s+)?(?:ron|lei)\b", re.I)
ATTACHMENT_MARK = re.compile(r"\[(?:Attachment|Atașament|Atasament):", re.I)


def parse_amount(raw: str) -> float | None:
    """'3,200.00', '3.200,00', '3 200', '2,99' or '2.99': the last separator with one or two digits after it is
    the decimal point; groups of three are thousands."""
    s = (raw or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        head, _, tail = s.rpartition(sep)
        s = s.replace(sep, "") if len(tail) == 3 else head.replace(sep, "") + "." + tail
    try:
        return float(s)
    except ValueError:
        return None


CONTACT_PATTERNS: list[tuple[str, str]] = [
    (r"\bsms\b|\btext\s+message|\btext(?:ed)?\b|\ba\s+text\b", "sms"),
    (r"\bwhatsapp\b|\bmessenger\b|\btelegram\b|\bsignal\s+app\b", "mesagerie"),
    (r"mesaj|\bmessage\b", "sms"),
    (r"sunat|\bapel|telefon|\b(?:called|rang|phoned)\s+me\b|\bphone\s+call\b|\b(?:got|had|received)\s+a\s+call\b"
     r"|\ba\s+call\s+from\b|\bon\s+the\s+phone\b|\bcaller\b|\bcall_transcript\b", "apel"),
    (r"\be-?mail\b", "email"),
    (r"\bchat\b", "mesagerie"),
]
IMPERSONATED: list[tuple[str, str]] = [
    (r"curier|\bcourier\b|\bdelivery\s+(?:company|firm|service)\b", "courier"),
    (r"\bbanca\b", "bank"),
    (r"poliția|politia|\bpolice\b", "police"),
    (r"\banaf\b|\btax\s+office\b", "ANAF"),
    (r"\bolx\b", "OLX"),
    (r"\b(?:from|of)\s+(?:the|my|your)\s+bank\b|\bbank'?s\s+(?:security|fraud)\b|\b(?:security|fraud)\s+"
     r"(?:department|team)\b|\bbank\s+employee\b", "bank"),
]
ASK_RE = re.compile(r"\b(?:vă rog|va rog|cer|solicit|doresc|vreau|de ce|cum|please|pls|i\s+want|i\s+would\s+like"
                    r"|i'?d\s+like|i\s+need|i'?m\s+asking|i\s+ask|i\s+request|i\s+demand|can\s+you|could\s+you|why"
                    r"|how|what\s+can|help\s+me)\b", re.I)
# a first-person verb and the right context, in the same sentence
SHARE_VERBS = ("am introdus", "am dat", "am completat", "i-am dat", "i-am spus", "am comunicat", "am trimis")
SHARE_CONTEXT = ("card", "cod", "parol", "otp", "cvv", "pin", "datele")
SHARE_EN = (r"\bi\s+(?:also\s+|then\s+|just\s+|even\s+)?(?:entered|typed|put\s+in|keyed\s+in|filled\s+in|gave|told"
            r"|read\s+out|sent|shared|provided|submitted)\b",
            r"\b(?:card|codes?|password|passcode|otp|cvv|cvc|pin|details|login|one-time)\b")
APPROVE_VERBS = ("am confirmat", "am aprobat", "am apăsat", "am apasat", "am acceptat", "am autorizat")
APPROVE_CONTEXT = ("aplicați", "aplicati", "aplicaț", "notificare", "plata", "plată", "aprobare", "ce apare")
APPROVE_EN = (r"\bi\s+(?:also\s+|then\s+|just\s+)?(?:approved|confirmed|pressed|tapped|accepted|authori[sz]ed|ok'?e?d"
              r"|okayed|hit)\b",
              r"\b(?:app|application|notification|push|pop-?up|prompt|approve|confirm(?:ation)?|payment|screen)\b")
UNAUTHORISED_RE = re.compile(r"nu (eu )?am (făcut|facut|autorizat|efectuat)|\b(?:did\s*n[o']?t|didn't|never)\s+"
                             r"(?:make|do|authori[sz]e|approve|send|order|buy)\b|\bwasn'?t\s+me\b")
REMEDY_RE = re.compile(r"bani|sum|\bmoney\b|\brefund|\breimburs|\bback\b")


def fallback_extract(text: str) -> P.ReceptorOut:
    """The deterministic extraction, for when there is no LLM (regular expressions and keywords).

    What the customer says (points, admissions, the claim) comes from the complaint itself; links, numbers and
    the contact channel also come from the attachments.
    """
    body = ATTACHMENT_MARK.split(text or "", maxsplit=1)[0]
    low = (text or "").lower()
    body_low = body.lower()
    amounts = []
    for pre, post in AMOUNT_RE.findall(text or ""):
        value = parse_amount(pre or post)
        if value is not None:
            amounts.append(value)
    contacted = next((code for pattern, code in CONTACT_PATTERNS if re.search(pattern, low)), "necunoscut")
    impersonated = next((who for pattern, who in IMPERSONATED if re.search(pattern, low)), None)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) > 25]
    asks = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) >= 15 and ASK_RE.search(s)]
    points = [P.ReceptorPoint(text=s[:140], quote=s[:200]) for s in (asks or sentences[:2])][:4]
    injection = detect_injection(text or "")
    low_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body_low)]

    def said(verbs: tuple[str, ...], context: tuple[str, ...], english: tuple[str, str]) -> bool:
        """The customer says it in one sentence: a first-person verb and the right context."""
        return any((any(v in s for v in verbs) and any(k in s for k in context))
                   or (re.search(english[0], s) and re.search(english[1], s)) for s in low_sentences)

    return P.ReceptorOut(
        claims_unauthorized=bool(UNAUTHORISED_RE.search(body_low)),
        client_admits_sharing_credentials=said(SHARE_VERBS, SHARE_CONTEXT, SHARE_EN),
        client_admits_approving_in_app=said(APPROVE_VERBS, APPROVE_CONTEXT, APPROVE_EN),
        noticed_when=None, contacted_by=contacted, impersonated_entity=impersonated,
        mentioned_urls=list(dict.fromkeys(m.rstrip(".,;") for m in URL_RE.findall(text or "")))[:5],
        mentioned_phones=list(dict.fromkeys(PHONE_RE.findall(text or "")))[:5],
        mentioned_amounts=amounts[:5], requested_remedy="refund of the amount" if REMEDY_RE.search(body_low) else None,
        points=points, injection_suspected=injection is not None, injection_quote=injection,
    )


class Ctx:
    """A node's context: the runtime, the emitter and evidence written through checked tools."""

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
        """One tool call: the Cedar policy first, then the tool. A denial shows up in the trace."""
        decision = self.rt.authorize(who, action, Zone.CLIENT)
        if not decision.allowed:
            await self.em.custom("policy_denied", f"Cedar denied {action} for {decision.principal}",
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


# ---------------------------------------------------------------- 1. Intake


async def receptor(state: dict) -> dict:
    c = Ctx(state)
    await c.start("receptor", "Reading the complaint and pseudonymizing it before any LLM sees it")
    complaint = Complaint.model_validate(state["complaint"])
    body = normalize_ro(complaint.text)
    attachments = [f"[Attachment: {a.kind}]\n{normalize_ro(a.content)}" for a in complaint.attachments]
    full = "\n\n".join([body, *attachments])

    known: dict[str, str] = {}
    try:
        customer = c.rt.repo.get_customer(complaint.customer_ref) or {}
        for key, value in customer.items():
            if isinstance(value, str) and value and any(k in key.lower() for k in ("name", "nume")):
                known[value] = "CLIENT"
    except Exception as exc:  # noqa: BLE001 - without the bank's customer record we only mask the patterns
        log.warning("customer %s not found: %s", complaint.customer_ref, exc)

    pseudo_text, vault = c.rt.privacy.pseudonymize(full, c.case_id, known)
    redactions = sum(1 for _ in re.finditer(r"<[A-Z]+_\d+>", pseudo_text))
    await c.fact("receptor", "complaint.received", f"intake.{complaint.source}", {"source": complaint.source},
                 {"sha256_original": hashlib.sha256(full.encode()).hexdigest(), "chars": len(full),
                  "attachments": len(complaint.attachments), "redactions": redactions},
                 f"Complaint received through {label(SOURCE_LABELS, complaint.source)}; "
                 f"{plural(redactions, 'personal detail')} pseudonymized",
                 Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.LLM]))

    deterministic_injection = detect_injection(full)
    out, info = await c.rt.llm.structured(
        role=Role.HAIKU, agent=AG["receptor"], system=P.RECEPTOR_SYSTEM,
        user=wrap_data("complaint", pseudo_text), schema=P.ReceptorOut,
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
        language=guess_language(body),
    )
    model = {"determinist": "deterministic"}.get(info.model or "", info.model) or "deterministic"
    fid = await c.fact("receptor", "complaint.extracted", f"llm.{info.mode}.{model}",
                       {"agent": AG["receptor"]}, extracted.model_dump(mode="json"),
                       f"The isolated LLM found {plural(len(extracted.points), 'point')} to answer; first contact: "
                       f"{label(CONTACT_LABELS, extracted.contacted_by or 'necunoscut')}",
                       Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
    fact_map = {"client_admits_sharing_credentials": fid, "client_admits_approving_in_app": fid}
    if extracted.injection_suspected:
        inj = await c.fact("receptor", "security.injection", "detector.injection",
                           {"deterministic": bool(deterministic_injection)}, {"quote": injection_quote},
                           "The complaint contains instructions aimed at the system; they were treated as data and "
                           "ignored",
                           Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
        await c.em.custom("injection_detected", "Instructions found in the complaint: ignored and flagged for a person",
                          {"fact_id": inj, "quote": injection_quote}, step="receptor", agent=AG["receptor"])
    c.save({"extracted": extracted.model_dump(mode="json"), "llm_mode": info.mode})
    await c.finish("receptor", f"Extraction done ({info.mode}, {model})",
                   {"llm": info.as_dict(), "injection": extracted.injection_suspected})
    return {"pseudo": {"text": pseudo_text, "vault": vault}, "extracted": extracted.model_dump(mode="json"),
            "fact_map": fact_map}


# ---------------------------------------------------------------- 2. Classifier (M1)


async def clasificator(state: dict) -> dict:
    c = Ctx(state)
    await c.start("clasificator", "Classifying the claim from its text (M1, calibrated probability)")
    complaint = state["complaint"]
    text = state["pseudo"]["text"]
    try:
        from versoml.ml.m1_classifier import classify_complaint

        cls = classify_complaint(text, {"channel_hint": complaint.get("channel_hint")})
        if isinstance(cls, dict):
            cls = Classification.model_validate(cls)
    except Exception as exc:  # noqa: BLE001 - without a trained model we use the hints
        log.warning("M1 unavailable: %s", exc)
        hint = complaint.get("channel_hint") or "transfer"
        cls = Classification(channel=Channel(hint), dispute_type=DisputeType.NEAUTORIZATA, probability=0.5,
                             ambiguous=True, model_version="fallback", method="rules")
    fid = await c.fact("clasificator", "ml.m1_classification", "ml.m1_classifier", {"model": cls.model_version},
                       cls.model_dump(mode="json"),
                       f"M1: {label(DISPUTE_LABELS, cls.dispute_type)}, {label(CHANNEL_LABELS, cls.channel)}, "
                       f"p={cls.probability:.2f}" + (" (ambiguous)" if cls.ambiguous else ""),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    c.save({"classification": cls.model_dump(mode="json")})
    scenario = label(SCENARIO_LABELS, cls.scenario) if cls.scenario else "no scenario"
    await c.finish("clasificator", f"{scenario.capitalize()}, {label(DISPUTE_LABELS, cls.dispute_type)} "
                                   f"(p={cls.probability:.2f})", {"classification": cls.model_dump(mode="json")})
    return {"classification": cls.model_dump(mode="json"), "fact_map": {"classification": fid}}


# ---------------------------------------------------------------- 3. Deadline clock


async def ceasornicar(state: dict) -> dict:
    c = Ctx(state)
    await c.start("ceasornicar", "Starting the legal clocks from the moment the customer told us")
    from versoml.shared.rules.calendar_ro import add_business_days, end_of_next_business_day

    received = parse_dt(state["complaint"]["received_at"]) or now()
    t1 = end_of_next_business_day(received)
    answer = add_business_days(received, 15)
    clock = {"notified_at": received.isoformat(), "t1_deadline": t1.isoformat(),
             "answer_deadline": answer.isoformat()}
    fid = await c.fact("ceasornicar", "clock.started", "rules.calendar_ro", {"notified_at": received.isoformat()},
                       clock, f"Refund deadline: {fmt_datetime(t1)} (end of the next business day). Written reply "
                              f"due by {fmt_date(answer)} (15 business days)",
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT, Sink.LETTER]))
    c.save({"clock": clock, "deadline": t1.isoformat()})
    await c.em.custom("clock", "The refund clock is running", clock, step="ceasornicar", agent=AG["ceasornicar"])
    await c.finish("ceasornicar", f"Refund due by {fmt_datetime(t1)}")
    return {"clock": clock, "fact_map": {"notified_at": fid}}


# ---------------------------------------------------------------- 4. Collectors (in parallel)


def _main_tx_id(state: dict) -> str | None:
    refs = state["complaint"].get("transaction_refs") or []
    return refs[0] if refs else None


async def colector_tranzactie(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_tranzactie", "Reading the payment and the payee from bank-core")
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
        channel = g(tx, "channel", "type", default="")
        fid = await c.fact("colector_tranzactie", "bank.transaction", "bank-core.get_transaction", {"tx_id": tx_id},
                           tx, f"Payment {tx_id}: {money(amount, g(tx, 'currency', default='RON'))}"
                               + (f", {label(CHANNEL_LABELS, channel)}" if channel else "")
                               + (f", to {merchant}" if (merchant := g(tx, "merchant_name", "counterparty_name", default=None)) and channel == "card"
                                  else f", to {bene[:4]}…{bene[-4:]}" if bene else ""),
                           Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT, Sink.AML]))
        fact_map.update({"amount": fid, "executed_at": fid, "channel": fid, "merchant_mcc": fid, "eci": fid})
        if bene:
            seen = await c.call("colector_tranzactie", "colector", "bank-core.beneficiary_seen_before",
                                lambda: c.rt.repo.beneficiary_seen_before(customer_ref, bene), {"iban": "…"})
            records["beneficiary_new"] = not bool(seen)
            fid = await c.fact("colector_tranzactie", "bank.beneficiary_history", "bank-core.beneficiary_seen_before",
                               {"customer": customer_ref}, {"beneficiary_new": not bool(seen)},
                               "New payee for this customer" if not seen else "The customer has paid this payee before")
            fact_map["beneficiary_new"] = fid
        dups = []
        if g(tx, "channel", "type", default="") == "card":
            dups = await c.call("colector_tranzactie", "colector", "bank-core.get_transaction",
                                lambda: c.rt.repo.find_duplicates(tx_id), {"tx_id": tx_id, "op": "find_duplicates"}) or []
        if dups:
            records["duplicate_of"] = g(dups[0], "id", "tx_id")
            fact_map["duplicate_of"] = await c.fact(
                "colector_tranzactie", "bank.duplicate", "bank-core.find_duplicates", {"tx_id": tx_id},
                {"duplicates": dups}, f"Identical payment found: {records['duplicate_of']}")
    # live complaints count too; the case under analysis never counts as its own earlier claim
    prior = await c.call("colector_tranzactie", "colector", "bank-core.get_prior_disputes",
                         lambda: c.rt.repo.get_prior_disputes(customer_ref, 12, exclude_case_id=c.case_id),
                         {"months": 12})
    records["prior_disputes_12m"] = len(prior or [])
    fact_map["prior_disputes_12m"] = await c.fact(
        "colector_tranzactie", "bank.prior_disputes", "bank-core.get_prior_disputes", {"months": 12},
        {"count": len(prior or [])}, f"{plural(len(prior or []), 'earlier claim')} in the last 12 months")
    await c.finish("colector_tranzactie", "The payment and its history are in the ledger")
    return {"records": records, "fact_map": fact_map}


async def colector_sca(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_sca", "Reading the SCA log: the method and what the customer saw on screen")
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
        shown = False  # the payment left from an enrolled device; the SCA step never showed the amount
    method = g(payment_auth or enrollment or {}, "method", default="none")
    records.update({"sca_performed": bool(events), "sca_method": method, "screen_showed_amount_and_payee": shown,
                    "eci": g(payment_auth or {}, "eci"), "cavv_present": g(payment_auth or {}, "cavv_present", "cavv")})
    for event in events[:4]:
        purpose = g(event, "purpose", default="payment")
        fid = await c.fact(
            "colector_sca", "sca.auth_event", "sca-logs.get_auth_events", {"tx_id": tx_id}, event,
            f"{SCA_METHOD.get(g(event, 'method', default=''), 'SCA')} for "
            f"{'enrolling a new device' if purpose == 'device_enrollment' else 'the payment'}: "
            + ("the screen showed the amount and the payee" if g(event, "screen_showed_amount_and_payee")
               else "no amount or payee on the screen"))
        fact_map.setdefault("sca_performed", fid)
        fact_map.setdefault("sca_method", fid)
        fact_map.setdefault("screen_showed_amount_and_payee", fid)
        if g(event, "eci"):
            fact_map["eci"] = fid
            fact_map["cavv_present"] = fid
    if not events:
        fact_map["sca_performed"] = await c.fact("colector_sca", "sca.none", "sca-logs.get_auth_events",
                                                 {"tx_id": tx_id}, {"events": 0}, "No SCA authentication in the log")
    await c.finish("colector_sca", f"{plural(len(events), 'SCA event')}; the screen "
                                   + ("showed" if shown else "did not show") + " the amount and the payee")
    return {"records": records, "fact_map": fact_map}


async def colector_dispozitiv(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_dispozitiv", "Checking the device, the session and any SIM swap")
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
        # known = enrolled at least a day before the payment (a phone enrolled minutes ago counts as new)
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
                           session, ("Known device" if device_known else "NEW device, never seen before")
                           + (f"; the payment went out {seconds} s after the link was clicked" if seconds is not None else ""))
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
            f"SIM swap {hours:g} {'hour' if hours == 1 else 'hours'} before the payment")
    await c.finish("colector_dispozitiv", "The device and the session are in the ledger")
    return {"records": records, "fact_map": fact_map}


def _age(hours: float) -> str:
    if hours < 48:
        return plural(round(hours), "hour")
    if hours < 24 * 60:
        return plural(round(hours / 24), "day")
    if hours < 24 * 730:
        return plural(round(hours / (24 * 30.4)), "month")
    return plural(round(hours / (24 * 365)), "year")


INTEL_SOURCES = {"rdap": "RDAP", "ct": "Certificate Transparency", "lookalike": "The lookalike check",
                 "openphish": "OpenPhish", "page": "The page fetch"}


def _intel_summary(name: str, domain: str, dump: dict) -> str:
    """One English sentence per domain-intel result, written from its data (the tools' own summaries aren't)."""
    data = dump.get("data") or {}
    if dump.get("ok") is False:
        return f"{INTEL_SOURCES.get(name, name)} gave no answer for {domain}"
    if name == "rdap":
        if data.get("registered") is False:
            return f"{domain} is not in the domain registry"
        if data.get("created_before_2001"):
            return f"{domain} was registered before 2001 (registrar: {data.get('registrar') or 'unknown'})"
        hours = data.get("age_hours")
        if not isinstance(hours, (int, float)):
            return f"RDAP shows no registration date for {domain}"
        created = fmt_datetime(data.get("created"))
        return (f"{domain} was registered {_age(hours)} ago" + (f" ({created})" if created else "")
                + f" through {data.get('registrar') or 'an unknown registrar'}"
                + ("; the owner's details are hidden" if data.get("privacy_protected") else ""))
    if name == "ct":
        count = int(data.get("count") or 0)
        if not count:
            return f"No certificates for {domain} in Certificate Transparency"
        hours = data.get("cert_age_hours")
        issuer = data.get("first_issuer") or "an unknown issuer"
        return (f"First certificate for {domain} logged "
                + (f"{_age(hours)} ago" if isinstance(hours, (int, float)) else "at an unknown time")
                + f", issued by {issuer}" + (" (a free CA)" if data.get("free_ca") else "")
                + f"; {plural(count, 'certificate')} in total")
    if name == "lookalike":
        score, brand = data.get("score"), data.get("closest_brand") or "the bank's domain"
        if data.get("legit"):
            return f"{domain} is the protected domain {brand} (or a subdomain), not a lookalike"
        keywords = (data.get("features") or {}).get("keywords") or []
        text = f"Lookalike score {float(score):.2f} against {brand}" if isinstance(score, (int, float)) \
            else f"No lookalike score for {domain}"
        return text + (f"; risky words: {', '.join(map(str, keywords))}" if keywords else "")
    if name == "openphish":
        if data.get("listed"):
            return f"OpenPhish lists {domain} ({plural(len(data.get('matches') or []), 'entry', 'entries')} in the feed)"
        return f"{domain} is not in the OpenPhish feed (that alone does not prove it is safe)"
    if name == "page":
        status = data.get("status")
        return f"Page at {data.get('final_url') or data.get('url') or domain} fetched" \
               + (f" (HTTP {status})" if status else "")
    return f"{name} for {domain}"


async def colector_domeniu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_domeniu", "Checking the fake domain: age, certificate, likeness to the bank")
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
        await c.finish("colector_domeniu", "No domain in the complaint", status="skipped")
        return {"records": records, "fact_map": fact_map}

    try:
        from versoml.osint import domain as osd
        from versoml.osint import lookalike as osl
        from versoml.osint import threatintel as ost
    except ImportError as exc:  # without the OSINT module the collector doesn't stop the case
        log.warning("OSINT unavailable: %s", exc)
        await c.finish("colector_domeniu", "The domain-intel module is not available", status="skipped")
        return {"records": records, "fact_map": fact_map}

    domain = domains[0]
    url = urls[0] if urls else f"https://{domain}/"

    async def run(action: str, fn: Callable[[], Any], args: dict) -> Any:
        try:
            return await c.call("colector_domeniu", "colector", action, fn, args)
        except Exception as exc:  # noqa: BLE001 - one failed tool doesn't stop the collector
            log.warning("%s failed: %s", action, exc)
            return None

    rdap, ct, look, phish, page = await asyncio.gather(
        run("domain-intel.rdap_lookup", lambda: osd.rdap_domain(domain), {"domain": domain}),
        run("domain-intel.ct_first_seen", lambda: osd.ct_certificates(domain), {"domain": domain}),
        run("domain-intel.lookalike_score", lambda: osl.lookalike_score(domain), {"domain": domain}),
        run("domain-intel.openphish_check", lambda: ost.openphish_check(url), {"url": url}),
        run("domain-intel.fetch_page", lambda: _fetch_page(url), {"url": url}),
    )
    summaries: dict[str, str] = {}
    for name, result, kind in (("rdap", rdap, "domain.rdap"), ("ct", ct, "domain.ct"),
                               ("lookalike", look, "domain.lookalike"), ("openphish", phish, "domain.openphish"),
                               ("page", page, "domain.page")):
        if result is None:
            continue
        data = _osint_dump(result)
        intel[name] = data
        summaries[name] = _intel_summary(name, domain, data)
        fid = await c.fact("colector_domeniu", kind, f"domain-intel.{name}", {"domain": domain}, data, summaries[name],
                           Labels(conf="public", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.AML, Sink.LLM]))
        fact_map[f"domain_{name}"] = fid
    # M4: fetch_page already scores the likeness to the Demo Bank page (the raw, untrusted HTML goes nowhere)
    similarity = ((intel.get("page") or {}).get("data") or {}).get("similarity")
    if similarity is not None:
        score = similarity.get("score") if isinstance(similarity, dict) else similarity
        data = similarity if isinstance(similarity, dict) else {"score": similarity}
        intel["similarity"] = data
        summaries["similarity"] = (f"M4: the page is {float(score):.0%} similar to the {BANK} login page"
                                   if isinstance(score, (int, float)) else "M4: how closely the page copies the bank's")
        fact_map["domain_similarity"] = await c.fact(
            "colector_domeniu", "domain.similarity", "domain-intel.page_similarity", {"reference": "bancademo_login"},
            data, summaries["similarity"])
    age_hours = _age_hours(intel.get("rdap"))
    score = (intel.get("lookalike") or {}).get("data", {}).get("score")
    records["attack"].update({"domain": domain, "url": url, "domain_age_hours": age_hours, "lookalike_score": score})
    await c.finish("colector_domeniu", f"{domain}: " + (f"registered {age_hours:.0f} h ago; " if age_hours is not None else "")
                   + (f"lookalike score {score:.2f}" if isinstance(score, (int, float)) else "no lookalike score"),
                   {"intel": summaries})
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


# ---------------------------------------------------------------- 5. The rules engine


def reconcile_type(cls: dict, records: dict, extracted: dict) -> tuple[DisputeType, bool, str]:
    """The final classification: the text (M1) reconciled with the facts in the bank's systems."""
    ml_type = DisputeType(cls.get("dispute_type", "neautorizata"))
    approved_in_app = bool(records.get("screen_showed_amount_and_payee")) and bool(records.get("device_known"))
    if records.get("duplicate_of"):
        return DisputeType.EROARE_PROCESARE, False, "duplicate payment found in bank-core"
    if ml_type in (DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        return ml_type, bool(cls.get("ambiguous")), "the text describes a problem with the merchant"
    fact_type = DisputeType.APP if approved_in_app and records.get("channel") != "card" else DisputeType.NEAUTORIZATA
    if records.get("device_known") is False:
        fact_type = DisputeType.NEAUTORIZATA
    ambiguous = bool(cls.get("ambiguous")) or fact_type != ml_type
    reason = ("the facts match the text" if fact_type == ml_type else
              f"the text suggests {label(DISPUTE_LABELS, ml_type)} but the facts show "
              f"{label(DISPUTE_LABELS, fact_type)}: the facts decide, and a person is told")
    return fact_type, ambiguous, reason


async def motor_reguli(state: dict) -> dict:
    c = Ctx(state)
    await c.start("motor_reguli", "Building the rule context from facts only, then running the rules")
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
        log.warning("M2 unavailable: %s", exc)
    fact_map = dict(state.get("fact_map") or {})
    if signal:
        fact_map["client_fraud_score"] = await c.fact(
            "motor_reguli", "ml.m2_client_fraud", "ml.m2_client_fraud", {}, signal,
            f"M2 (a signal for a person, not a decision): score {float(signal.get('score', 0)):.2f}")

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
        # the claimed amount = the one in the text closest to the log (the text also mentions the RON 2.99 bait fee)
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
    await c.em.custom("classification_final", f"Final classification: {label(DISPUTE_LABELS, dispute_type)} ({reason})",
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
                d.unknowns.append("the text classification contradicts the facts: a person confirms")
    for d in decisions:
        await c.em.custom("decision", f"{d.question.value}: {d.decision.value}", d.model_dump(mode="json"),
                          step="motor_reguli", agent=AG["motor_reguli"])
    fid = await c.fact("motor_reguli", "rules.outcome", "rules.engine", {"engine": outcome.engine_version},
                       {"decisions": [d.model_dump(mode="json") for d in decisions],
                        "rule_ids": sorted({h.rule_id for h in outcome.hits})},
                       f"Rules engine: {plural(len(outcome.hits), 'rule')} fired, "
                       f"{plural(len(decisions), 'decision')}")
    t1 = next((d for d in decisions if d.question == Question.RAMBURSARE_T1), None)
    c.save({"rule_context": ctx.model_dump(mode="json"), "rules": outcome.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "verdict": t1.decision.value if t1 else None, "channel": channel.value,
            "scenario": ctx.scenario.value if ctx.scenario else scenario,
            "amount": ctx.amount.model_dump(), "dispute_type": dispute_type.value})
    await c.finish("motor_reguli", f"Refund: {label(VERDICT_LABELS, t1.decision) if t1 else 'no decision'}; rules "
                   + ", ".join(sorted({h.rule_id for h in outcome.hits})[:6]))
    return {"rule_context": ctx.model_dump(mode="json"), "rules": outcome.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in decisions], "fact_map": {"rules_outcome": fid},
            "records": {"channel": channel.value}}


# ---------------------------------------------------------------- 6. The diode to AML


async def outbox_aml(state: dict) -> dict:
    c = Ctx(state)
    await c.start("outbox_aml", "Sending AML only facts about the attack and the payee, never the victim's identity")
    ctx = state["rule_context"]
    records = state.get("records") or {}
    tx = records.get("transaction") or {}
    attack = records.get("attack") or {}
    bene_iban = g(tx, "beneficiary_iban", "counterparty_iban", "to_iban")
    if ctx["dispute_type"] not in ("neautorizata", "app") or not (bene_iban or attack.get("domain")):
        await c.finish("outbox_aml", "Not a fraud case with a payee: nothing to send", status="skipped")
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
    status = "not authorized"
    if decision.allowed:
        try:
            result = await _send_facts(c.rt, facts)
            status = "sent" if result.get("ok") else "queued in the outbox (the AML zone is not answering, so it will retry)"
        except Exception as exc:  # noqa: BLE001 - schema refused: nothing is sent
            log.warning("diode: %s", exc)
            status = f"rejected by the diode ({type(exc).__name__})"
    fid = await c.fact("outbox_aml", "wall.diode_sent", "diode.send_facts", {"case_id": c.case_id},
                       {"status": status, "fields": sorted(facts.model_dump(exclude_none=True).keys())},
                       (f"Payment facts sent to the fraud intelligence team; the customer appears only as {victim_ref}"
                        if status == "sent" else f"Payment facts for the fraud intelligence team: {status}"),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    await c.em.custom("diode", f"DisputeFacts {status}", {"status": status, "victim_ref": victim_ref, "fact_id": fid},
                      step="outbox_aml", agent=AG["outbox_aml"])
    c.save({"aml_referral": {"status": status, "victim_ref": victim_ref}})
    await c.finish("outbox_aml", f"Diode: {status}")
    return {}


async def _send_facts(rt: ClientRuntime, facts: DisputeFacts) -> dict:
    # the HTTP send is blocking: run it on a thread so the graph doesn't block the event loop
    result = await asyncio.to_thread(rt.diode.send_facts, facts)
    return result if isinstance(result, dict) else {"ok": True}


# ---------------------------------------------------------------- 7. The refund (rules engine + a person)


def _decision(state: dict, question: Question) -> dict | None:
    return next((d for d in state.get("decisions", []) if d.get("question") == question.value), None)


async def rambursare(state: dict) -> dict:
    c = Ctx(state)
    d = _decision(state, Question.RAMBURSARE_T1)
    if state.get("refund", {}).get("done"):
        return {}
    verdict = d["decision"] if d else None
    amount = float((state["rule_context"].get("amount") or {}).get("value", 0))
    currency = (state["rule_context"].get("amount") or {}).get("currency") or "RON"
    customer_ref = state["complaint"]["customer_ref"]
    # when the graph resumes after the signature, the node runs again up to interrupt(): emit nothing twice
    pending = (c.rt.cases.get(c.case_id) or {}).get("interrupt") or {}
    resuming = bool(pending.get("pending") or pending.get("resuming"))
    if not resuming:
        await c.start("rambursare", f"Applying the refund decision: {label(VERDICT_LABELS, verdict)}"
                      + (f" ({verdict})" if verdict else ""))

    if verdict in (Verdict.RAMBURSEAZA_CU_APROBARE.value, Verdict.EXCEPTIE_FRAUDA_CLIENT.value,
                   Verdict.RESPINGE_TARDIV.value) or (d and d.get("requires_human") and verdict != Verdict.NU_SE_APLICA_T1.value):
        prompt = {
            Verdict.RAMBURSEAZA_CU_APROBARE.value: refund_approval_prompt(
                amount, d.get("deadline") if d else None, (state.get("rules") or {}).get("hits"), currency),
            Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "The AML zone sent a HOLD approved by an analyst, and the authority "
                                                 "has been notified. Confirm the C-70/25 exception (no refund for now)?",
            Verdict.RESPINGE_TARDIV.value: "The customer told us more than 13 months after the payment (art. 169). "
                                          "An unfavorable decision needs a person's approval (GDPR art. 22). "
                                          "Confirm the rejection?",
        }.get(verdict, "This decision needs a person's signature.")
        payload = {"kind": "aprobare_rambursare" if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value else "semnatura_decizie",
                   "verdict": verdict, "prompt": prompt, "options": ["approve", "reject"], "amount": amount,
                   "deadline": d.get("deadline") if d else None, "rule_ids": d.get("rule_ids", []) if d else []}
        if not resuming:
            c.track("rambursare", "waiting", "Needs approval")
            c.save({"interrupt": {"pending": True, **payload}, "status": "ASTEAPTA_APROBARE"})
            await c.em.custom("interrupt", prompt, payload, step="rambursare", agent=AG["rambursare"])
        answer = interrupt(payload)
        c.save({"interrupt": {**payload, "pending": False, "resuming": False, "answer": answer}})
        approved = (answer or {}).get("action") == "approve"
        approver = (answer or {}).get("approver") or "OPERATOR-01"
        await c.fact("rambursare", "human.signature", "console.operator", {"approver": approver},
                     {"action": (answer or {}).get("action"), "note": (answer or {}).get("note")},
                     f"{approver} {'approved' if approved else 'rejected'} the {verdict} decision")
        if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value and approved:
            return await _issue_refund(c, state, amount, customer_ref, approved_by=approver)
        status = {Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "EXCEPTIE", Verdict.RESPINGE_TARDIV.value: "RESPINS"}.get(
            verdict, "IN_ANALIZA")
        if verdict == Verdict.RAMBURSEAZA_CU_APROBARE.value and not approved:
            status = "IN_ANALIZA"
        if verdict in (Verdict.EXCEPTIE_FRAUDA_CLIENT.value, Verdict.RESPINGE_TARDIV.value) and not approved:
            # the person did not confirm the unfavorable decision: refund within the deadline
            return await _issue_refund(c, state, amount, customer_ref, approved_by=approver)
        c.save({"status": status})
        await c.finish("rambursare", f"Decision signed by {approver}: {status}")
        return {"refund": {"done": False, "status": status}}

    if verdict == Verdict.RAMBURSEAZA.value:
        return await _issue_refund(c, state, amount, customer_ref, approved_by=None)

    status = "TRASEU_APP" if state["rule_context"]["dispute_type"] == "app" else "IN_ANALIZA"
    c.save({"status": status})
    await c.finish("rambursare", "The next-business-day refund does not apply: recovery and support route", status="skipped")
    return {"refund": {"done": False, "status": status}}


async def _issue_refund(c: Ctx, state: dict, amount: float, customer_ref: str, approved_by: str | None) -> dict:
    context = {"within_auto_cap": approved_by is None, "approved_by_human": approved_by is not None}
    decision = c.rt.authorize("motor", "refund.issue", Zone.CLIENT, context)
    currency = (state["rule_context"].get("amount") or {}).get("currency") or "RON"
    if not decision.allowed:
        await c.em.custom("policy_denied", "Cedar denied the refund instruction", decision.model_dump(mode="json"),
                          step="rambursare", agent=AG["rambursare"])
        await c.finish("rambursare", "The policy blocked the refund instruction", status="blocked")
        return {"refund": {"done": False, "status": "BLOCAT"}}
    # a payment is refunded once, however many disputes it gets (an operational guard, not a legal rule)
    refs = set(state["complaint"].get("transaction_refs") or [])
    prior = next((d for d in c.rt.cases.all() if d.get("case_id") not in (None, c.case_id) and d.get("status") == "RAMBURSAT"
                  and refs & set((d.get("complaint") or {}).get("transaction_refs") or [])), None)
    if prior:
        await c.fact("rambursare", "refund.duplicate", "refund.issue", {"tx": sorted(refs)},
                     {"already_refunded_in": prior["case_id"]},
                     f"This payment was already refunded in case {prior['case_id']}: no second refund")
        c.save({"status": "RAMBURSAT", "refund_of": prior["case_id"]})
        await c.finish("rambursare", f"Already refunded in {prior['case_id']}: no double payment")
        return {"refund": {"done": True, "status": "RAMBURSAT", "duplicate_of": prior["case_id"]}}
    key = f"refund-{c.case_id}"
    result = c.rt.repo.post_refund(c.case_id, customer_ref, amount, key)
    await c.fact("rambursare", "refund.instruction", "refund.issue", {"idempotency_key": key},
                 {"amount": amount, "result": result, "approved_by": approved_by, "decided_by": "MotorReguli"},
                 f"Refund instruction for {money(amount, currency)} issued by the rules engine"
                 + (f", approved by {approved_by}" if approved_by else " (under the cap, no signals)"))
    # the "We've refunded you…" notification is written by core banking (post_refund), like any other transaction
    c.save({"status": "RAMBURSAT", "refunded_at": now().isoformat()})
    await c.em.custom("refund", f"Refunded {money(amount, currency)}", {"amount": amount, "approved_by": approved_by},
                      step="rambursare", agent=AG["rambursare"])
    await c.finish("rambursare", f"Refunded {money(amount, currency)} before the refund deadline")
    return {"refund": {"done": True, "status": "RAMBURSAT", "amount": amount}}


# ---------------------------------------------------------------- 8. The debate (recovery route only)


def _facts_brief(c: Ctx, limit: int = 30) -> tuple[str, set[str]]:
    facts = c.rt.ledger.facts(c.case_id)
    ids = {f.fact_id for f in facts}
    lines = [f"- {f.fact_id} [{f.kind}]: {f.summary}" for f in facts if f.kind not in ("complaint.received",)][:limit]
    brief, _ = c.rt.privacy.pseudonymize("\n".join(lines), c.case_id)  # nothing raw goes to the model
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


def _numbered(prefix: str, lines: list[tuple[str, list[str]]], start: int = 1) -> list[P.ArgLine]:
    """Argument lines as the prompts ask for them: "P1. The claim [EV-004]." (the IDs also go in `cites`)."""
    out = []
    for i, (text, cites) in enumerate(lines, start):
        ids = " ".join(f"[{c}]" for c in cites)
        out.append(P.ArgLine(text=f"{prefix}{i}. {text}" + (f" {ids}." if ids else "."), cites=cites))
    return out


def _fallback_argument(side: str, ctx: dict, fm: dict) -> P.Argument:
    cite = lambda k: [fm[k]] if fm.get(k) else []  # noqa: E731
    if side == "procuror":
        lines = []
        if ctx.get("screen_showed_amount_and_payee"):
            lines.append(("The authentication screen showed the amount and the payee, and the customer confirmed",
                          cite("screen_showed_amount_and_payee")))
        if ctx.get("client_admits_sharing_credentials"):
            lines.append(("The customer says they entered their card details and the code on the fake page",
                          cite("client_admits_sharing_credentials")))
        if not lines:
            lines.append(("The payment needed a successful SCA step in the customer's name", cite("sca_performed")))
        claims = _numbered("P", lines)
        return P.Argument(claims=claims, missing_evidence=["the full session recording"],
                          strongest_point=claims[0].text)
    lines = []
    if ctx.get("device_known") is False:
        lines.append(("The payment came from a new device that someone else enrolled, not from the customer's phone",
                      cite("device_known")))
    if ctx.get("screen_showed_amount_and_payee") is False:
        lines.append(("The SMS code did not show the amount or the payee, so the customer could not see what they "
                      "were approving", cite("screen_showed_amount_and_payee")))
    if fm.get("domain_lookalike"):
        lines.append(("The fake page copied the bank's page on a recently registered domain",
                      [fm["domain_lookalike"]] + cite("domain_rdap")))
    if ctx.get("seconds_after_click") is not None:
        lines.append((f"The payment went out {ctx['seconds_after_click']} seconds after the link was clicked",
                      cite("seconds_after_click")))
    if not lines:
        lines.append(("Under Article 171 of Law 209/2019, use of the payment instrument does not on its own prove "
                      "gross negligence", cite("sca_performed") or cite("amount")))
    claims = _numbered("D", lines)
    return P.Argument(claims=claims, missing_evidence=[], strongest_point=claims[0].text)


def rubric(ctx: dict, fm: dict) -> tuple[list[dict], int]:
    """The weigher's fixed rubric: objective indicators with public weights."""
    items = [
        ("The screen showed the amount and the payee", ctx.get("screen_showed_amount_and_payee") is True, 3,
         "screen_showed_amount_and_payee"),
        ("The customer says they gave away card details or a code", ctx.get("client_admits_sharing_credentials") is True,
         2, "client_admits_sharing_credentials"),
        ("The customer says they approved it in the app", ctx.get("client_admits_approving_in_app") is True, 2,
         "client_admits_approving_in_app"),
        ("Payment from a new device (favors the customer)", ctx.get("device_known") is False, -2, "device_known"),
        ("Payment within 5 minutes of the click (favors the customer)",
         (ctx.get("seconds_after_click") or 10**6) < 300, -1, "seconds_after_click"),
        ("SIM swap before the payment (favors the customer)", ctx.get("sim_swap_hours_before") is not None, -3,
         "sim_swap_hours_before"),
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
            c.track(step, "skipped", "No debate: there is no case for recovering the money from the customer")
        return {"debate": {"ran": False}}
    brief, valid = _facts_brief(c)
    question = (wrap_data("evidence", brief) +
                "\n\nQuestion: is there evidence for a case to recover the money from the customer for gross "
                "negligence?")
    await c.start("procuror", "The prosecutor argues for recovery (Opus), citing the evidence")
    await c.start("avocat", "The defender argues for the customer (a different model), citing the evidence")

    async def statement(side: str) -> tuple[P.Argument, Any]:
        system = P.PROCUROR_SYSTEM if side == "procuror" else P.AVOCAT_SYSTEM
        role = Role.OPUS if side == "procuror" else Role.SONNET
        return await c.rt.llm.structured(role=role, agent=AG[side], system=system, user=question, schema=P.Argument,
                                         effort="medium", max_tokens=3000,
                                         fallback=lambda: _fallback_argument(side, ctx, fm))

    (pro, pro_info), (con, con_info) = await asyncio.gather(statement("procuror"), statement("avocat"))

    async def rebut(side: str, own: P.Argument, other: P.Argument) -> tuple[P.Argument, Any]:
        system = (P.PROCUROR_SYSTEM if side == "procuror" else P.AVOCAT_SYSTEM) + "\n" + P.REBUTTAL_HINT
        role = Role.OPUS if side == "procuror" else Role.SONNET
        other_text = "\n".join(f"{l.text} cites={l.cites}" for l in other.claims) or "No points."
        first = f"{'P' if side == 'procuror' else 'D'}{len(own.claims) + 1}"
        return await c.rt.llm.structured(role=role, agent=AG[side], system=system,
                                         user=question + "\n\n" + wrap_data("other_side", other_text)
                                         + f"\n\nNumber your replies from {first}.",
                                         schema=P.Argument, effort="low", max_tokens=2000,
                                         fallback=lambda: P.Argument(claims=[], missing_evidence=[], strongest_point=""))

    (pro_r, _), (con_r, _) = await asyncio.gather(rebut("procuror", pro, con), rebut("avocat", con, pro))
    pro_lines, pro_bad = _verify(pro.claims + pro_r.claims, valid)
    con_lines, con_bad = _verify(con.claims + con_r.claims, valid)
    await c.finish("procuror", f"{plural(len(pro_lines), 'claim')} with sources ({pro_bad} dropped for having none)",
                   {"lines": pro_lines, "llm": pro_info.as_dict()})
    await c.finish("avocat", f"{plural(len(con_lines), 'claim')} with sources ({con_bad} dropped for having none)",
                   {"lines": con_lines, "llm": con_info.as_dict()})

    await c.start("cantaritor", "Weighing the indicators with the fixed rubric")
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
    await c.fact("cantaritor", "debate.rubric", "debate.weigher", {"score": score},
                 {"rubric": rows, "recommendation": rules_rec, "agree_with_rules": agree},
                 f"Rubric score {score}; recommendation: {label(VERDICT_LABELS, rules_rec)}"
                 + ("" if agree else " (disagrees with the rules: a person decides)"))
    c.save({"debate": debate})
    await c.finish("cantaritor", f"Recommendation: {label(VERDICT_LABELS, rules_rec)} (score {score})")
    return {"debate": debate}


# ---------------------------------------------------------------- 9. Recovering the money from the scammer


def camt056(case_id: str, tx: dict, amount: float, currency: str) -> str:
    """An ISO 20022 camt.056.001.08 cancellation request with reason FRAD (a draft, never sent automatically)."""
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
        <CxlRsnInf><Rsn><Cd>FRAD</Cd></Rsn><AddtlInf>Payment disputed by the payer as fraud</AddtlInf></CxlRsnInf>
      </TxInf>
    </Undrlyg>
  </FIToFIPmtCxlReq>
</Document>"""


def _fallback_dnsc(attack: dict) -> P.DnscDraft:
    domain, url, phones = attack.get("domain"), attack.get("url"), [p for p in attack.get("phones") or [] if p]
    lines = [f"We are reporting a phishing campaign that imitates {BANK}."]
    if domain:
        lines.append(f"Domain: {domain}.")
    if url:
        lines.append(f"URL: {url}.")
    if phones:
        lines.append(f"Phone {'number' if len(phones) == 1 else 'numbers'} used by the scammer: {', '.join(phones)}.")
    age = attack.get("domain_age_hours")
    if isinstance(age, (int, float)):
        lines.append(f"The domain was registered about {plural(round(age), 'hour')} before the attack.")
    lines.append("We ask you to block the domain and take the page down." if domain
                 else "We ask you to block the number.")
    return P.DnscDraft(title=f"Phishing: {domain or 'fraudulent phone call'}", body=" ".join(lines),
                       indicators=[x for x in [domain, url, *phones] if x])


async def recuperare(state: dict) -> dict:
    c = Ctx(state)
    await c.start("recuperare", "Preparing the recovery drafts: recall, chargeback and the DNSC report")
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
                                      "A chargeback is possible." if eligible else
                                      "The payment was authenticated with Visa Secure (ECI 05 and CAVV), so Visa "
                                      "10.4 does not apply and the loss stays with the bank. Recovery goes through "
                                      "other routes.")}
    else:
        bene = g(tx, "beneficiary_iban", "counterparty_iban", "to_iban") or ""
        internal = "BDEM" in bene[:8].upper()
        recovery["recall"] = {
            "kind": "interna" if internal else ("camt.056" if currency == "EUR" else "rechemare_ron"),
            "xml": None if internal else camt056(c.case_id, tx, amount, currency),
            "note": (f"The payee also banks with {BANK}: an internal return request goes to Operations."
                     if internal else "Recall draft. The interbank procedure for RON payments is still to be "
                                      "confirmed [U]."),
            "deadline": next((dl["due_at"] for dl in rules.get("deadlines", [])
                              if any(k in dl.get("name", "").lower() for k in ("rechem", "recall"))), None),
        }
    attack = records.get("attack") or {}
    if attack.get("domain") or attack.get("phones"):
        public = {"domain": attack.get("domain"), "url": attack.get("url"), "phones": attack.get("phones"),
                  "domain_age_hours": attack.get("domain_age_hours"), "lookalike_score": attack.get("lookalike_score"),
                  "contact_channel": (state.get("extracted") or {}).get("contacted_by")}
        # the scammer's number is public, but the guard can't tell it from a customer's: the model sees a label
        masked, vault = c.rt.privacy.pseudonymize(_json(public), c.case_id)
        draft, info = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["recuperare"], system=P.DNSC_SYSTEM,
            user=wrap_data("attack_indicators", masked), schema=P.DnscDraft, effort="low",
            max_tokens=1500, fallback=lambda: _fallback_dnsc(attack))
        restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
        recovery["dnsc_report"] = {"title": restore(draft.title), "text": restore(draft.body),
                                   "indicators": [restore(x) for x in draft.indicators],
                                   "channel": "pnrisc.dnsc.ro / 1911", "status": "draft: a person sends it"}
    names = {"recall": "recall", "chargeback": "chargeback", "dnsc_report": "DNSC report"}
    await c.fact("recuperare", "recovery.drafts", "recall.draft", {"decision": escroc.get("decision")},
                 {k: v for k, v in recovery.items() if k != "decision"},
                 "Recovery drafts ready: " + (", ".join(v for k, v in names.items() if k in recovery) or "none"))
    c.save({"recovery": recovery})
    await c.finish("recuperare", "The recovery drafts are waiting for a person to send them")
    return {"recovery": recovery}


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str, indent=1)


# ---------------------------------------------------------------- 10. The letter and the wall check


HELPLINE = P.HELPLINE

ADR_BLOCK = P.ADR_TEXT

SAFETY_TIP = "Never share the codes we send you by text message, even with someone who says they work for the bank."
SAFETY_TIPS = {"app": "If someone calls saying they work for the bank and asks you to move money or approve a "
                       "payment, hang up and call us on the number on the back of your card."}

REFUND_VERDICTS = ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")
_ABOUT_MONEY = re.compile(r"\bmoney\b|\brefund|\bback\b|\breturn|\breimburs|\bbani|\bsum", re.I)
_WHY_NOT_STOPPED = (re.compile(r"\b(?:why|how\s+come|de\s+ce)\b", re.I), re.compile(r"\bblock|\bstop|\bbloc|\bopri", re.I))


def _point_answer(point: str, verdict: str | None) -> str | None:
    """The fallback letter's answer to one point of the complaint, or None when the letter already answers it."""
    if _WHY_NOT_STOPPED[0].search(point) and _WHY_NOT_STOPPED[1].search(point):
        return ("You asked why we did not stop the payment. It went through the usual authentication steps, so it "
                "was processed like any other payment."
                + (" The law still requires us to refund you." if verdict in REFUND_VERDICTS else ""))
    if _ABOUT_MONEY.search(point) and verdict in (*REFUND_VERDICTS, "RESPINGE_TARDIV", "NU_SE_APLICA_T1"):
        return None   # the outcome paragraph is the answer
    return f"You also wrote: \u201c{point}\u201d We have taken this into account in our answer."


def _payment_words(state: dict) -> tuple[str, str]:
    """("card payment", " to SHOP SRL") for the letter; a transfer's payee is not named."""
    ctx = state["rule_context"]
    tx = (state.get("records") or {}).get("transaction") or {}
    kind = PAYMENT_KINDS.get(str(ctx.get("channel") or ""), "payment")
    merchant = g(tx, "merchant_name", "counterparty_name") if ctx.get("channel") == "card" else None
    return kind, (f" to {merchant}" if merchant else "")


def _fallback_letter(state: dict) -> P.LetterOut:
    """The letter without an LLM: the same facts, in the shape the letter prompt asks for."""
    ctx = state["rule_context"]
    t1 = _decision(state, Question.RAMBURSARE_T1) or {}
    ans = _decision(state, Question.RASPUNS_RECLAMATIE) or {}
    escroc = (_decision(state, Question.RECUPERARE_ESCROC) or {}).get("decision")
    value = ctx.get("amount") or {}
    amount = money(float(value.get("value", 0)), value.get("currency") or "RON")
    fm = ctx.get("fact_ids") or {}
    verdict = t1.get("decision")
    kind, to_whom = _payment_words(state)
    paid, told = to_local(ctx.get("executed_at")), to_local(ctx.get("notified_at"))
    paid_on, told_on = fmt_date(paid), fmt_date(told)
    on_paid = f" on {paid_on}" if paid_on else ""
    when_paid = " earlier that day" if paid_on and paid_on == told_on else on_paid
    you_told = f"On {told_on} you told us" if told_on else "You told us"
    by, answer_by = fmt_datetime(t1.get("deadline")), fmt_date(ans.get("deadline"))
    refunded = bool((state.get("refund") or {}).get("done"))
    quick = bool(paid and told and (told - paid) <= timedelta(days=2))
    law = ""
    if verdict in REFUND_VERDICTS:
        subject = f"Refund of {amount} for a {kind}{to_whom}"
        opening = (f"{you_told} that you did not make the {kind} of {amount}{to_whom}{when_paid}. "
                   + ("We have refunded the full amount to your account." if refunded else
                      f"We will refund the full amount to your account by {by}." if by else
                      "We will refund the full amount to your account.")
                   + (" Thank you for telling us so quickly." if quick else " Thank you for telling us about it."))
        law = ("Under Article 173 of Law 209/2019, we must refund a payment you did not authorize by the end of the "
               "next business day after you report it.")
        after = {"RECHEMARE": "We are also asking the bank that received the money to return it. You do not need to "
                              "do anything for this.",
                 "CHARGEBACK": "We are also asking the merchant's bank to return the money through Visa. You do not "
                               "need to do anything for this."}.get(escroc, "You do not need to do anything else.")
    elif verdict == "NU_SE_APLICA_T1":
        subject = f"Your claim about the {amount} {kind}"
        how = {"app": "was approved in your banking app",
               "disputa_comerciant": "was a card payment you authorized",
               "eroare_procesare": "was charged twice by the merchant"}.get(ctx.get("dispute_type"), "was authorized")
        opening = (f"{you_told} about the {kind} of {amount}{to_whom} made{when_paid or ' recently'}. "
                   f"Our records show that the payment {how}.")
        law = ("This means Article 173 of Law 209/2019, which makes us refund a payment you did not authorize by the "
               "end of the next business day, does not apply to it.")
        later = f" by {answer_by}" if answer_by else ""
        after = {"RECHEMARE": f"We have asked the bank that received the money to return it, and we will write to you "
                              f"with their answer{later}.",
                 "CHARGEBACK": f"We have started a chargeback with the merchant's bank, and we will write to you with "
                               f"the outcome{later}."}.get(
            escroc, f"We are trying to recover the money from the bank that received it, and we will write to you{later}.")
    elif verdict == "RESPINGE_TARDIV":
        subject = f"Your claim about the {amount} {kind}" + (f" of {paid_on}" if paid_on else "")
        opening = f"{you_told} that you did not make the {kind} of {amount}{to_whom}{on_paid}."
        law = ("Article 169 of Law 209/2019 allows 13 months from the payment date to report a payment you did not "
               "authorize. You told us after that period, so we cannot refund this payment.")
        after = ("If you have documents showing that you contacted us earlier, send them to us and we will look at "
                 "your claim again.")
    else:
        subject = f"Your claim about the {amount} {kind}"
        opening = f"We have received your claim about the {kind} of {amount}{to_whom}{on_paid}."
        after = ("We need more time to finish our review, and we will send you our answer"
                 + (f" by {answer_by}." if answer_by else " as soon as it is ready."))
    paragraphs = [
        P.LetterParagraph(text="Dear <CLIENT_1>,", cites=[]),
        P.LetterParagraph(text=opening, cites=[x for x in [fm.get("amount"), fm.get("notified_at")] if x]),
    ]
    if law:
        paragraphs.append(P.LetterParagraph(text=law, cites=[x for x in [fm.get("rules_outcome")] if x]))
    points = []
    for point in (state.get("extracted") or {}).get("points", [])[:4]:
        answer = _point_answer(point["text"], verdict)
        if answer:
            paragraphs.append(P.LetterParagraph(text=answer, cites=[]))
        points.append(point["text"])
    paragraphs.append(P.LetterParagraph(text=f"{after} {SAFETY_TIPS.get(ctx.get('dispute_type'), SAFETY_TIP)}",
                                        cites=[]))
    paragraphs.append(P.LetterParagraph(
        text=f"{ADR_BLOCK} If you have questions, call us on {HELPLINE} or reply to this email, quoting case "
             f"{state.get('case_id') or ctx.get('case_id')}.", cites=[]))
    paragraphs.append(P.LetterParagraph(text=f"Kind regards,\nDisputes team, {BANK}", cites=[]))
    return P.LetterOut(subject=subject, paragraphs=paragraphs, points_answered=points)


VERDICT_MEANINGS = {
    "RAMBURSEAZA": "refund the full amount by the deadline",
    "RAMBURSEAZA_CU_APROBARE": "refund the full amount by the deadline, once a bank employee approves it",
    "EXCEPTIE_FRAUDA_CLIENT": "no refund for now: tell the customer the review needs more time and give the answer date",
    "RESPINGE_TARDIV": "no refund: the customer reported the payment more than 13 months after it was made",
    "NU_SE_APLICA_T1": "the next-business-day refund rule does not apply: the bank tries to recover the money instead",
    "CHARGEBACK": "the bank asks the merchant's bank to return the money (chargeback)",
    "RECHEMARE": "the bank asks the bank that received the transfer to return it (recall)",
    "INFORMATII_SUPLIMENTARE": "the bank needs more information from the customer",
    "INCHIDE": "the claim is closed",
}


def _local_iso(value: Any) -> str | None:
    """Bucharest time as ISO (the LLM client strips ISO timestamps from replay keys, so recordings still match)."""
    dt = to_local(value)
    return dt.isoformat(timespec="seconds") if dt else None


def _letter_brief(state: dict, c: Ctx) -> dict:
    ctx = state["rule_context"]
    value = ctx.get("amount") or {}
    kind, to_whom = _payment_words(state)
    decisions = [d for d in state.get("decisions", []) if d.get("question") in
                 ("rambursare_t1", "raspuns_reclamatie", "recuperare_escroc")]
    return {
        "case_id": c.case_id,
        "payment": {"amount": money(float(value.get("value", 0)), value.get("currency") or "RON"), "type": kind,
                    "merchant": to_whom[4:] or None, "made_at": _local_iso(ctx.get("executed_at")),
                    "reported_at": _local_iso(ctx.get("notified_at"))},
        "refund_sent": bool((state.get("refund") or {}).get("done")),
        "decisions": [{"question": d["question"], "decision": d["decision"],
                       "meaning": VERDICT_MEANINGS.get(d["decision"], label(VERDICT_LABELS, d["decision"])),
                       "deadline": _local_iso(d.get("deadline")),
                       "reasons": [r.get("text") for r in d.get("rationale", [])][:3]} for d in decisions],
        "points": [p["text"] for p in (state.get("extracted") or {}).get("points", [])],
        "evidence_ids": sorted({v for v in (ctx.get("fact_ids") or {}).values()})[:20],
    }


def _customer_name(c: Ctx, state: dict) -> str | None:
    """The name for the greeting, from the bank's record (the complaint may not mention it)."""
    try:
        customer = c.rt.repo.get_customer(state["complaint"]["customer_ref"]) or {}
    except Exception:  # noqa: BLE001 - without the record the letter says "Dear customer,"
        return None
    name = " ".join(str(customer[k]) for k in ("first_name", "last_name") if customer.get(k))
    return name or None


async def redactor(state: dict) -> dict:
    c = Ctx(state)
    await c.start("redactor", "Drafting the reply: every point answered, with deadlines and where to complain")
    brief = wrap_data("letter_data", _json(_letter_brief(state, c)))
    out, info = await c.rt.llm.structured(
        role=Role.SONNET, agent=AG["redactor"], system=P.LETTER_SYSTEM,
        user=brief, schema=P.LetterOut, effort="low", max_tokens=3000,
        fallback=lambda: _fallback_letter(state))
    valid = {f.fact_id for f in c.rt.ledger.facts(c.case_id)}
    cites = sorted({x for p in out.paragraphs for x in p.cites if x in valid})
    pseudo_body = "\n\n".join(p.text for p in out.paragraphs)
    # the CMP checks from the rules engine: every point gets an answer (CMP-01), the complaints block (CMP-03)
    from versoml.shared.rules import check_complaint_letter

    points = [p["text"] for p in (state.get("extracted") or {}).get("points", [])]
    cmp_hits = check_complaint_letter(pseudo_body, points, out.points_answered)
    if any(h.outcome == "CMP_ADR_BLOCK_MISSING" for h in cmp_hits):
        pseudo_body += "\n\n" + ADR_BLOCK
        cmp_hits = check_complaint_letter(pseudo_body, points, out.points_answered)
        await c.em.custom("rule_hit", "CMP-03: the ANPC / ANAF / BNR / CSALB paragraph was missing, so it was added",
                          {"rule_id": "CMP-03", "outcome": "bloc_adaugat"}, step="redactor", agent=AG["redactor"])
    cmp_checks = [{"rule_id": h.rule_id, "outcome": h.outcome, "explanation": h.explanation} for h in cmp_hits]
    await c.finish("redactor", f"Letter drafted ({info.mode}); {plural(len(out.points_answered), 'point')} answered",
                   {"llm": info.as_dict(), "cmp": cmp_checks})

    await c.start("filtru_zid", "Checking the letter: forbidden terms, canary tokens, personal data")
    from versoml.wall.letter_filter import check_letter

    result = check_letter(pseudo_body)
    if not result.passed and not result.canaries_found and result.blocked_terms:
        # self-correction: one rewrite, with the filter's reasons; if that fails too, a person decides
        await c.em.custom("wall_block", "The check stopped the first draft; the letter writer is redoing it without "
                                        "the forbidden terms",
                          result.model_dump(mode="json"), step="filtru_zid", agent=AG["filtru_zid"])
        feedback = ("\n\nThe letter check stopped the previous draft because of these terms: "
                    + ", ".join(result.blocked_terms) + ". Write the letter again without them. Talk only about the "
                    "customer's payment, the decision, the next step and where to complain.")
        retry, _ = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["redactor"], system=P.LETTER_SYSTEM,
            user=brief + feedback, schema=P.LetterOut, effort="low",
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
    body = re.sub(r"<CLIENT_\d+>", _customer_name(c, state) or "customer", body)
    status = "draft" if result.passed else "blocked"
    letter = {"case_id": c.case_id, "subject": out.subject, "body": body, "cites": cites,
              "points_answered": out.points_answered, "filter": result.model_dump(mode="json"), "status": status,
              "cmp_checks": cmp_checks}
    if not result.passed:
        c.rt.record_block(c.case_id, result.reasons, result.blocked_terms)
        await c.em.custom("wall_block", "The wall blocked the letter: " + "; ".join(result.reasons[:2]),
                          result.model_dump(mode="json"), step="filtru_zid", agent=AG["filtru_zid"])
    await c.fact("filtru_zid", "letter.checked", "letters.check_letter", {"chars": len(body)},
                 {"passed": result.passed, "blocked_terms": result.blocked_terms, "canaries": result.canaries_found,
                  "sha256_letter": hashlib.sha256(body.encode()).hexdigest()},
                 "The letter passed the wall check" if result.passed else "The wall BLOCKED the letter")
    c.save({"letter": letter})
    await c.finish("filtru_zid", "Clean letter: no forbidden terms, no canary tokens" if result.passed
                   else "Blocked and sent to a person", status="done" if result.passed else "blocked")
    return {"letter": letter}


# ---------------------------------------------------------------- 11. The ledger seal


async def sigiliu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("sigiliu", "Sealing the case file: an Ed25519-signed Merkle root and a QR code")
    seal = c.rt.ledger.seal(c.case_id)
    summary = {k: seal.get(k) for k in ("root", "count", "sealed_at", "signature")}
    count = int(seal.get("count") or 0)
    await c.em.custom("ledger_seal", f"Case file sealed: {plural(count, 'evidence item')}, root "
                                     f"{str(seal.get('root'))[:16]}…",
                      summary, step="sigiliu", agent=AG["sigiliu"])
    doc = c.rt.cases.get(c.case_id) or {}
    c.save({"ledger": {"count": seal.get("count"), "root": seal.get("root"), "sealed": True},
            "finished_at": now().isoformat(), "status": doc.get("status") or "INCHIS"})
    await c.finish("sigiliu", f"Sealed: {plural(count, 'evidence item')}")
    return {"sealed": True}


def new_run_id() -> str:
    return "RUN-" + uuid.uuid4().hex[:8]
