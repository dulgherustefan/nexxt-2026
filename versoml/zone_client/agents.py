"""The dispute judge's agents (client zone).

Each graph node receives the case state, emits AG-UI events, writes evidence to the ledger through Cedar-checked
tools and returns only its own updates. The LLM extracts, argues and drafts; the rules engine decides; a person
approves anything unfavorable or over the cap.

Node IDs, event types, verdict and status codes stay as they are (the console matches on them); everything a
person at the bank reads is plain English (US spelling, money as "RON 3,200.00", dates as "29 Oct 2026, 23:59").
The letter to the customer is in the customer's language: Romanian ("3.200,00 lei", "29 octombrie 2026, ora 23:59")
when the complaint is in Romanian, English otherwise.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from langgraph.types import interrupt

from versoml.contracts import (
    AttackRef, BeneficiaryRef, Channel, Classification, ClaimPoint, Complaint, Decision, DisputeFacts,
    DisputeType, ExtractedClaim, Labels, Money, Question, RuleContext, Scenario, Sink, StandardRecord, Trust, Verdict,
    Zone,
)
from versoml.shared import canonical as K
from versoml.shared.events import Emitter, now
from versoml.shared.llm import Role
from versoml.zone_client import prompts as P
from versoml.zone_client.fmt import (
    fmt_date, fmt_date_ro, fmt_datetime, fmt_datetime_ro, fmt_deadline, money, money_ro, to_local,
)
from versoml.zone_client.runtime import ClientRuntime, get_runtime

log = logging.getLogger("versoml.client.agents")

BANK = P.BANK_NAME

AG = {
    "receptor": "Intake",
    "identificare": "Identification",
    "clasificator": "Classifier",
    "ceasornicar": "Deadline clock",
    "colector_tranzactie": "Transaction collector",
    "colector_sca": "SCA collector",
    "colector_dispozitiv": "Device collector",
    "colector_domeniu": "Domain collector",
    "colector_campanie": "Campaign collector",
    "router": "Router",
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
    {"id": "identificare", "label": "Identification", "model": "no LLM", "lane": "intrare",
     "hint": "finds the customer and the disputed payment in the ledger, with a score per clue; a person picks if unsure"},
    {"id": "clasificator", "label": "Classifier", "model": "ml", "lane": "intrare",
     "hint": "M1: TF-IDF and calibrated logistic regression"},
    {"id": "ceasornicar", "label": "Deadline clock", "model": "no LLM", "lane": "intrare",
     "hint": "Next business day, 15/35 business days, 13 months, Romanian bank holidays"},
    {"id": "router", "label": "Router", "model": "no LLM", "lane": "intrare",
     "hint": "decides which collectors run, with a reason for each (LangGraph Send)"},
    {"id": "colector_tranzactie", "label": "Transaction", "model": "no LLM", "lane": "probe",
     "hint": "bank-core: the payment, the payee, the history"},
    {"id": "colector_sca", "label": "SCA", "model": "no LLM", "lane": "probe",
     "hint": "sca-logs: the method and what the screen showed"},
    {"id": "colector_dispozitiv", "label": "Device", "model": "no LLM", "lane": "probe",
     "hint": "device: new device, seconds after the click, SIM swap"},
    {"id": "colector_domeniu", "label": "Fake domain", "model": "no LLM", "lane": "probe",
     "hint": "domain-intel: RDAP, CT, lookalike score (M3), page similarity (M4)"},
    {"id": "colector_campanie", "label": "Campaign", "model": "no LLM", "lane": "probe",
     "hint": "other cases with the same payee, link or phone (M6), and similar stories"},
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
COLLECTOR_NODES = ["colector_tranzactie", "colector_sca", "colector_dispozitiv", "colector_domeniu", "colector_campanie"]
PIPELINE_EDGES = [
    ("receptor", "identificare"), ("identificare", "clasificator"), ("clasificator", "ceasornicar"),
    ("ceasornicar", "router"),
    *[("router", name) for name in COLLECTOR_NODES],
    *[(name, "motor_reguli") for name in COLLECTOR_NODES],
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
    "extragere_de_confirmat": "the complaint was read without a live model",
    "PAY_FRAUD_NOTICE_MISSING": "a fraud hold came in but the authority has not been told in writing",
    "DSP_CE3_MET": "earlier undisputed card payments match this one (Visa CE3.0)",
}
GENERIC_ESCALATION = "the amount is over the cap or there are risk signals"

# why a person signed the way they did: a code and a text, both sealed with the signature (GDPR art. 22). The
# first code of each action is the one used until the console sends a code of its own.
SIGNATURE_REASONS: dict[str, dict[str, str]] = {
    "approve": {"FACTS_CONFIRMED": "the facts in the case file support the proposed decision",
                "OTHER": "another reason, given in the text"},
    "reject": {"FACTS_DISPUTED": "the facts in the case file do not support the proposed decision",
               "FRAUD_SUSPECTED": "a suspicion of fraud by the customer, to be reported to the authority in writing",
               "EVIDENCE_MISSING": "evidence the decision needs is missing",
               "OTHER": "another reason, given in the text"},
}


def signature_reason(action: str, code: str | None, note: str | None, prompt: str | None) -> dict:
    """The reason behind an approve or a reject: a code that fits the action and a text. The text is the person's
    note; without one it is the question they answered, and `reason_from_note` says so. {"error": ...} when the
    reason cannot be accepted."""
    codes = SIGNATURE_REASONS.get(action) or {}
    code = (code or next(iter(codes), "")).strip().upper()
    if code not in codes:
        return {"error": f"Reason code {code or '(none)'} does not fit {action}: use one of {', '.join(codes)}."}
    text = (note or "").strip()
    if code == "OTHER" and not text:
        return {"error": "OTHER needs the reason written in the note."}
    if len(text) > 1000:
        return {"error": "Keep the reason under 1,000 characters."}
    return {"reason_code": code, "reason_text": text or prompt or codes[code], "reason_from_note": bool(text)}


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


def replay_scope(state: dict) -> str:
    """The case's part of every replay key: a hash of what the customer sent and who sent it. A rerun of the same
    complaint still replays; a recording made for another complaint never answers this one."""
    complaint = state.get("complaint") or {}
    blob = _json([complaint.get("customer_ref"), complaint.get("text"), complaint.get("attachments") or []])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


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
ASK_RE = re.compile(r"\b(?:vă rog|va rog|cer|solicit|doresc|vreau|de ce|please|pls|i\s+want|i\s+would\s+like"
                    r"|i'?d\s+like|i\s+need|i'?m\s+asking|i\s+ask|i\s+request|i\s+demand|can\s+you|could\s+you|why"
                    r"|what\s+can|help\s+me)\b|\b(?:how|cum)\b[^.!]*\?", re.I)
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
    body_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body)]

    def said(verbs: tuple[str, ...], context: tuple[str, ...], english: tuple[str, str]) -> str | None:
        """The sentence where the customer says it (a first-person verb and the right context), or None."""
        for s in body_sentences:
            low = s.lower()
            if (any(v in low for v in verbs) and any(k in low for k in context)) \
                    or (re.search(english[0], low) and re.search(english[1], low)):
                return s
        return None

    sharing = said(SHARE_VERBS, SHARE_CONTEXT, SHARE_EN)
    approving = said(APPROVE_VERBS, APPROVE_CONTEXT, APPROVE_EN)
    return P.ReceptorOut(
        claims_unauthorized=bool(UNAUTHORISED_RE.search(body_low)),
        client_admits_sharing_credentials=sharing is not None, sharing_quote=sharing,
        client_admits_approving_in_app=approving is not None, approving_quote=approving,
        noticed_when=None, contacted_by=contacted, impersonated_entity=impersonated,
        mentioned_urls=list(dict.fromkeys(m.rstrip(".,;") for m in URL_RE.findall(text or "")))[:5],
        mentioned_phones=list(dict.fromkeys(PHONE_RE.findall(text or "")))[:5],
        mentioned_amounts=amounts[:5], requested_remedy="refund of the amount" if REMEDY_RE.search(body_low) else None,
        points=points, injection_suspected=injection is not None, injection_quote=injection,
    )


# ---------------------------------------------------------------- what the reading may claim

ADMISSIONS = (("client_admits_sharing_credentials", "sharing_quote"),
              ("client_admits_approving_in_app", "approving_quote"))
ADMISSION_WORDS = {"client_admits_sharing_credentials": "shared their card details or codes",
                   "client_admits_approving_in_app": "approved the payment in the app"}
_PLAIN_MARKS = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u00ab": '"',
                              "\u00bb": '"', "\u2013": "-", "\u2014": "-"})


def _plain(text: str) -> str:
    """Folded for comparing a quote with the complaint: no diacritics (cedillas included), lower case, plain quote
    marks and dashes, one space between words."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", normalize_ro(text or ""))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().translate(_PLAIN_MARKS)
    return " ".join(folded.split())


def quote_in_text(quote: str | None, text: str) -> bool:
    """True when the quote is the customer's own words: it appears in the text as written, after folding case,
    diacritics, quote marks and spaces. A quote cut short with "..." counts when each piece appears, in order."""
    pieces = [p.strip(" .,;:!?\"'") for p in re.split(r"\[?\s*\.{3,}\s*\]?", _plain(quote or ""))]
    pieces = [p for p in pieces if p]
    if not pieces or sum(len(p) for p in pieces) < 4:
        return False
    hay, pos = _plain(text), 0
    for piece in pieces:
        found = hay.find(piece, pos)
        if found < 0:
            return False
        pos = found + len(piece)
    return True


def ground_extraction(out: P.ReceptorOut, text: str, *, deterministic: bool = False) -> tuple[P.ReceptorOut, dict]:
    """The reading, kept only where the complaint backs it. A point's quote and the injection quote must be the
    customer's words, and a link or phone number the reading lists must be in the text (the domain check and the
    DNSC draft use them), or they are dropped. An admission, true or false, stands only with its quote found in the
    text; otherwise it becomes None and a person confirms it. The pattern reader's "false" only means it found
    nothing, so it becomes None without a flag.

    Returns the checked reading and {dropped, to_confirm}."""
    from versoml.zone_client.numeric_check import host_of, phone_key

    dropped: list[dict] = []
    plain, digits = _plain(text), re.sub(r"\D", "", text or "")
    urls = [u for u in out.mentioned_urls if host_of(u) and host_of(u) in plain]
    phones = [p for p in out.mentioned_phones
              if p in (text or "") or (len(phone_key(p)) >= 6 and phone_key(p) in digits)]
    dropped += [{"field": "mentioned_urls", "quote": u} for u in out.mentioned_urls if u not in urls]
    dropped += [{"field": "mentioned_phones", "quote": p} for p in out.mentioned_phones if p not in phones]
    points = []
    for i, point in enumerate(out.points):
        if point.quote and not quote_in_text(point.quote, text):
            dropped.append({"field": f"points[{i}].quote", "quote": point.quote})
            point = point.model_copy(update={"quote": ""})
        points.append(point)
    update: dict[str, Any] = {"points": points, "mentioned_urls": urls, "mentioned_phones": phones}
    if out.injection_quote and not quote_in_text(out.injection_quote, text):
        dropped.append({"field": "injection_quote", "quote": out.injection_quote})
        update["injection_quote"] = None
    to_confirm: list[dict] = []
    for field, quote_field in ADMISSIONS:
        value, quote = getattr(out, field), getattr(out, quote_field)
        if value is None:
            update[quote_field] = None
            continue
        if quote and quote_in_text(quote, text):
            continue
        update[field], update[quote_field] = None, None
        if quote:
            dropped.append({"field": quote_field, "quote": quote})
        if not (deterministic and value is False):
            to_confirm.append({"field": field, "value": value, "quote": quote or None})
    return out.model_copy(update=update), {"dropped": dropped, "to_confirm": to_confirm}


def _grounding_summary(report: dict) -> str:
    parts = []
    for item in report["to_confirm"]:
        says = ("says the customer " if item["value"] else "says the customer never ") + ADMISSION_WORDS[item["field"]]
        parts.append(f"the reading {says}, but no such words are in the complaint")
    quotes = sum(1 for d in report["dropped"] if d["field"] == "injection_quote" or d["field"].startswith("points"))
    if quotes:
        parts.append(f"{plural(quotes, 'quote')} not found in the complaint {'was' if quotes == 1 else 'were'} dropped")
    mentions = sum(1 for d in report["dropped"] if d["field"] in ("mentioned_urls", "mentioned_phones"))
    if mentions:
        parts.append(f"{plural(mentions, 'link or phone number', 'links or phone numbers')} not in the complaint "
                     f"{'was' if mentions == 1 else 'were'} dropped")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + (": the admission is left blank for a person to confirm"
                                           if report["to_confirm"] else "")


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
    customer_ref = complaint.customer_ref or _pre_identify(c, complaint)
    try:
        customer = (c.rt.repo.get_customer(customer_ref) if customer_ref else None) or {}
        for key, value in customer.items():
            if isinstance(value, str) and value and any(k in key.lower() for k in ("name", "nume")):
                known[value] = "CLIENT"
    except Exception as exc:  # noqa: BLE001 - without the bank's customer record we only mask the patterns
        log.warning("customer %s not found: %s", customer_ref, exc)

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
        fallback=lambda: fallback_extract(pseudo_text), max_tokens=2500, scope=replay_scope(state),
    )
    # every quote must be the customer's words, and an admission stands only on its quote
    out, grounding = ground_extraction(out, pseudo_text, deterministic=info.mode == "offline")
    restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
    injection_quote = out.injection_quote or deterministic_injection
    amounts, phones, hosts = _standard_mentions(complaint, out, restore)
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
        language=guess_language(body), amounts=amounts, phones_e164=phones, hosts=hosts,
    )
    model = {"determinist": "deterministic"}.get(info.model or "", info.model) or "deterministic"
    fid = await c.fact("receptor", "complaint.extracted", f"llm.{info.mode}.{model}",
                       {"agent": AG["receptor"]}, extracted.model_dump(mode="json"),
                       f"The isolated LLM found {plural(len(extracted.points), 'point')} to answer; first contact: "
                       f"{label(CONTACT_LABELS, extracted.contacted_by or 'necunoscut')}",
                       Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
    fact_map = {"client_admits_sharing_credentials": fid, "client_admits_approving_in_app": fid}
    extracted_doc = {**extracted.model_dump(mode="json"), "to_confirm": [x["field"] for x in grounding["to_confirm"]]}
    if grounding["dropped"] or grounding["to_confirm"]:
        check = await c.fact("receptor", "complaint.grounding", "intake.quote_check",
                             {"dropped": len(grounding["dropped"]), "to_confirm": len(grounding["to_confirm"])},
                             grounding, _grounding_summary(grounding),
                             Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
        if grounding["to_confirm"]:
            await c.em.custom("extraction_unconfirmed", _grounding_summary(grounding),
                              {"fact_id": check, "fields": extracted_doc["to_confirm"]},
                              step="receptor", agent=AG["receptor"])
    if extracted.injection_suspected:
        inj = await c.fact("receptor", "security.injection", "detector.injection",
                           {"deterministic": bool(deterministic_injection)}, {"quote": injection_quote},
                           "The complaint contains instructions aimed at the system; they were treated as data and "
                           "ignored",
                           Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
        await c.em.custom("injection_detected", "Instructions found in the complaint: ignored and flagged for a person",
                          {"fact_id": inj, "quote": injection_quote}, step="receptor", agent=AG["receptor"])
    c.save({"extracted": extracted_doc, "llm_mode": info.mode})
    if info.mode != "live":
        await c.em.custom("llm_degraded", f"The complaint was read in {info.mode} mode, not by a live model: a person "
                                          "checks the extraction", {"mode": info.mode, "fact_id": fid},
                          step="receptor", agent=AG["receptor"])
    await c.finish("receptor", f"Extraction done ({info.mode}, {model})",
                   {"llm": info.as_dict(), "injection": extracted.injection_suspected})
    return {"pseudo": {"text": pseudo_text, "vault": vault}, "extracted": extracted_doc,
            "fact_map": {**fact_map, "llm_mode": fid}, "llm_mode": info.mode}


def _standard_mentions(complaint: Complaint, out: "P.ReceptorOut",
                       restore: Callable[[str], str]) -> tuple[list[Money], list[str], list[str]]:
    """The amounts, phone numbers and websites in the complaint, in standard form. The deterministic parser reads the
    original text, currencies included; what the LLM listed is normalized the same way and added. The customer's own
    phone number is left out: it is not an indicator."""
    from versoml.zone_client import matcher as M

    try:
        clues = M.parse_clues(complaint.text, [a.model_dump() for a in complaint.attachments],
                              received_at=complaint.received_at)
    except Exception as exc:  # noqa: BLE001 - the LLM's lists alone, normalized
        log.info("clue parsing failed: %s", type(exc).__name__)
        clues = M.Clues()
    amounts = [Money(value=round(a.value, 2), currency=a.currency) for a in clues.amounts]
    if not amounts:
        amounts = [m for v in out.mentioned_amounts if (m := K.money(v))]
    own = {K.e164(p) for p, role in clues.phones if role == "self"}
    phones = [restore(p) for p in out.mentioned_phones] + [p for p, role in clues.phones if role != "self"]
    sites = [restore(u) for u in out.mentioned_urls] + [*clues.urls, *clues.domains]
    return (amounts[:8], [x for x in dict.fromkeys(map(K.e164, phones)) if x and x not in own][:8],
            [x for x in dict.fromkeys(map(K.host, sites)) if x][:8])


def customer_alias(customer_ref: str | None) -> str:
    if not customer_ref:
        return "Unidentified customer"
    if customer_ref.startswith("CUST-DEMO-"):
        return "Demo Customer " + customer_ref[-2:]
    digits = "".join(ch for ch in customer_ref if ch.isdigit())[-4:] or "0000"
    return f"Customer {digits}"


def _pre_identify(c: "Ctx", complaint: Complaint) -> str | None:
    """Before the LLM sees a free-form complaint: the customer the text points to, so their name is masked too (a
    wrong guess only masks one name more). The identification node decides properly afterwards."""
    try:
        from versoml.zone_client import matcher as M

        clues = M.parse_clues(complaint.text, [a.model_dump() for a in complaint.attachments],
                              received_at=complaint.received_at)
        guesses = M.identify_customer(c.rt.repo, clues)
        return guesses[0].customer_ref if guesses else None
    except Exception as exc:  # noqa: BLE001 - the patterns still mask phone numbers, IBANs and signatures
        log.info("pre-identification failed: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------- 1b. Identification (free-form intake)


def _open_cases_tx(c: "Ctx") -> dict[str, str]:
    """Payments other cases in this zone are already about (a new claim is matched to another payment)."""
    out: dict[str, str] = {}
    for d in c.rt.cases.all():
        if d.get("case_id") in (None, c.case_id) or d.get("status") == "EROARE":
            continue
        for ref in case_tx_refs(d):
            out.setdefault(ref, d["case_id"])
    return out


def _match_summary(match: dict) -> str:
    if match.get("tx_id"):
        how = {"given": "given with the complaint", "picked": "picked by a person"}.get(match.get("method"), "matched")
        who = match.get("customer_match_reason") or "Customer identified"
        return f"{who}. Payment {match['tx_id']} {how}"
    if match.get("customer_ref"):
        return "Customer identified; no payment in the ledger fits the complaint"
    return "The customer could not be identified from the complaint"


async def identificare(state: dict) -> dict:
    c = Ctx(state)
    from versoml.contracts import MatchResult
    from versoml.zone_client import matcher as M

    complaint = state["complaint"]
    doc = c.rt.cases.get(c.case_id) or {}
    pending = doc.get("interrupt") or {}
    resuming = pending.get("kind") == "pick_transaction" and bool(pending.get("pending") or pending.get("resuming"))
    received = parse_dt(complaint.get("received_at")) or now()
    clues = M.parse_clues(complaint.get("text", ""), complaint.get("attachments"), received_at=received,
                          channel_hint=complaint.get("channel_hint"))
    if resuming and doc.get("match_pending"):
        match = MatchResult.model_validate(doc["match_pending"])
    else:
        await c.start("identificare", "Finding the customer and the disputed payment in the bank's records")
        decision = c.rt.authorize("colector", "bank-core.get_transaction", Zone.CLIENT)
        if not decision.allowed:
            await c.em.custom("policy_denied", "Cedar denied bank-core.get_transaction", decision.model_dump(mode="json"),
                              step="identificare", agent=AG["identificare"])
            raise PermissionError(decision.reason)
        taken = _open_cases_tx(c)
        match = await c.call("identificare", "colector", "bank-core.get_customer_ref",
                             lambda: M.match_complaint(c.rt.repo, text=complaint.get("text", ""),
                                                       attachments=complaint.get("attachments"),
                                                       customer_ref=complaint.get("customer_ref"),
                                                       transaction_refs=complaint.get("transaction_refs") or [],
                                                       channel_hint=complaint.get("channel_hint"), received_at=received,
                                                       exclude_case_id=c.case_id, taken=taken, clues=clues),
                             {"customer_ref_given": bool(complaint.get("customer_ref")),
                              "transaction_refs_given": len(complaint.get("transaction_refs") or [])})
        await c.em.custom("match", match.reason, match.model_dump(mode="json"), step="identificare",
                          agent=AG["identificare"])

    if match.needs_human and match.candidates and match.customer_ref:
        from versoml.shared.rules.calendar_ro import end_of_next_business_day

        candidates = [x.model_dump(mode="json") for x in match.candidates]
        prompt = f"Which payment is the customer disputing? {match.reason} Pick one, or choose none of these."
        # the refund clock runs from the customer's report while the person picks
        payload = {"kind": "pick_transaction", "prompt": prompt, "options": ["pick_transaction"],
                   "candidates": candidates, "customer_ref": match.customer_ref, "reason": match.reason,
                   "deadline": end_of_next_business_day(received).isoformat()}
        if not resuming:
            c.track("identificare", "waiting", "A person picks the disputed payment")
            c.save({"interrupt": {"pending": True, **payload}, "status": "ASTEAPTA_APROBARE",
                    "match_pending": match.model_dump(mode="json"), "customer_ref": match.customer_ref,
                    "customer_alias": customer_alias(match.customer_ref)})
            await c.em.custom("interrupt", prompt, payload, step="identificare", agent=AG["identificare"])
        answer = interrupt(payload) or {}
        approver = answer.get("approver") or "OPERATOR-01"
        c.save({"interrupt": {**payload, "pending": False, "resuming": False, "answer": answer}, "status": "IN_ANALIZA"})
        match = M.picked(match, answer.get("tx_id"), approver)
        await c.fact("identificare", "human.pick_transaction", "console.operator", {"approver": approver},
                     {"tx_id": answer.get("tx_id"), "note": answer.get("note"),
                      "candidates": [x.tx_id for x in match.candidates]},
                     f"{approver} picked payment {answer['tx_id']}" if answer.get("tx_id")
                     else f"{approver} found none of the candidate payments right")
        await c.em.custom("match", match.reason, match.model_dump(mode="json"), step="identificare",
                          agent=AG["identificare"])

    match_d = match.model_dump(mode="json")
    fid = await c.fact("identificare", "intake.match", "bank-core.match_complaint",
                       {"method": match.method, "candidates": len(match.candidates)}, match_d, _match_summary(match_d),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    fact_map = {"match": fid, "transaction_identified": fid, "customer_identified": fid}
    declared: dict = {}
    if not match.tx_id:
        declared = M.declared_facts(clues)
        dfid = await c.fact("identificare", "declared.statement", "intake.customer_statement", {"source": "complaint"},
                            declared, "What the customer says about the payment (their statement, not the bank's records)",
                            Labels(conf="client", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT, Sink.LETTER]))
        fact_map.update({"declared": dfid, "amount": dfid, "executed_at": dfid})
    tx_refs = [match.tx_id] if match.tx_id else []
    customer_ref = match.customer_ref or complaint.get("customer_ref")
    patch = {"match": match_d, "tx_refs": tx_refs, "declared": declared or None}
    if customer_ref and customer_ref != doc.get("customer_ref"):
        patch.update({"customer_ref": customer_ref, "customer_alias": customer_alias(customer_ref)})
    c.save(patch)
    try:
        c.rt.repo.update_complaint_identity(c.case_id, customer_ref, tx_refs)
    except Exception as exc:  # noqa: BLE001 - the case document keeps the identity anyway
        log.info("update_complaint_identity: %s", type(exc).__name__)
    message = _match_summary(match_d) + ("" if match.tx_id else ": the claim goes on with the customer's statements")
    await c.finish("identificare", message, {"match": {k: match_d[k] for k in ("customer_ref", "tx_id", "needs_human",
                                                                              "method", "confidence")}})
    return {"match": match_d, "declared": declared, "fact_map": fact_map}


# ---------------------------------------------------------------- 3b. The router (dynamic collectors)


def _attack_targets(state: dict) -> dict:
    """The links, domains and phone numbers in the complaint (the scammer's, as the customer reports them)."""
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
    return {"domains": domains, "urls": urls, "phones": phones}


def _own_phone(c: "Ctx", customer_ref: str | None) -> str | None:
    try:
        return (c.rt.repo.get_customer(customer_ref) or {}).get("phone") if customer_ref else None
    except Exception:  # noqa: BLE001
        return None


def _campaign_indicators(c: "Ctx", state: dict, tx: dict | None) -> dict:
    from versoml.data.ids import normalize_phone

    targets = _attack_targets(state)
    own = normalize_phone(_own_phone(c, _customer_ref(state)) or "")
    iban = g(tx or {}, "counterparty_iban", "beneficiary_iban", "to_iban")
    return {"ibans": [iban] if iban and str(iban).upper().startswith("RO") else [],
            "domains": targets["domains"][:3],
            "phones": [p for p in targets["phones"] if not p.startswith("<") and normalize_phone(p) != own][:3]}


async def router(state: dict) -> dict:
    c = Ctx(state)
    await c.start("router", "Deciding which evidence collectors this case needs")
    from versoml.zone_client import routing as R

    tx_id = _main_tx_id(state)
    tx = await c.call("router", "colector", "bank-core.get_transaction",
                      lambda: c.rt.repo.get_transaction(tx_id) if tx_id else None, {"tx_id": tx_id})
    merchant = None
    if tx and g(tx, "channel") == "card" and g(tx, "merchant_id"):
        merchant = c.rt.repo.get_merchant(tx["merchant_id"])
    targets = _attack_targets(state)
    steps = R.plan(tx=tx, customer_ref=_customer_ref(state), attack_domains=targets["domains"],
                   merchant_domain=(merchant or {}).get("domain"), indicators=_campaign_indicators(c, state, tx),
                   narrative_chars=len((state.get("pseudo") or {}).get("text") or ""))
    for entry in steps:
        await c.em.custom("routing", entry["reason"], entry, step="router", agent=AG["router"])
        if not entry["run"]:
            c.track(entry["node"], "skipped", entry["reason"])
    running = [e for e in steps if e["run"]]
    await c.fact("router", "routing.plan", "router.plan", {"collectors": len(steps)}, {"steps": steps},
                 f"Router: {len(running)} of {len(steps)} collectors run",
                 Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    c.save({"routing": steps})
    await c.finish("router", f"{len(running)} of {len(steps)} collectors run")
    return {"routing": steps, "records": {"merchant": merchant} if merchant else {}}


# ---------------------------------------------------------------- 4e. Campaign collector


def _other_cases(c: "Ctx") -> list[dict]:
    out = []
    for d in c.rt.cases.all():
        if d.get("case_id") in (None, c.case_id) or d.get("status") == "EROARE":
            continue
        ind = d.get("indicators")
        if ind is None:
            extracted = d.get("extracted") or {}
            iban = (d.get("rule_context") or {}).get("beneficiary_iban")
            ind = {"ibans": [iban] if iban else [], "domains": extracted.get("mentioned_urls") or [],
                   "phones": [p for p in extracted.get("mentioned_phones") or [] if not str(p).startswith("<")]}
        out.append({"case_id": d["case_id"], "indicators": ind, "narrative": (ind or {}).get("narrative") or ""})
    return out


async def colector_campanie(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_campanie", "Looking for other cases with the same payee, link or phone number")
    from versoml.zone_client import campaign as CP
    from versoml.zone_client import grounding as G

    tx_id = _main_tx_id(state)
    tx = await c.call("colector_campanie", "colector", "bank-core.get_transaction",
                      lambda: c.rt.repo.get_transaction(tx_id) if tx_id else None, {"tx_id": tx_id})
    indicators = _campaign_indicators(c, state, tx)
    narrative = ((state.get("pseudo") or {}).get("text") or "")[:1500]
    c.save({"indicators": {**indicators, "narrative": narrative}})
    others = await c.call("colector_campanie", "colector", "ledger.read_client", lambda: _other_cases(c),
                          {"op": "campaign_candidates"})
    result = CP.link(c.case_id, indicators, narrative, others or [],
                     embed=lambda texts: G.embed(texts, input_type="clustering", namespace="campaign"))
    if not result:
        await c.finish("colector_campanie", "No other case shares this payee, link or phone number")
        return {"campaign": None}
    shared = ", ".join(f"{i['kind']} {i['value_masked']}" for i in result["shared_indicators"][:3])
    n = len(result["case_ids"]) - 1
    summary = (f"Linked to {plural(n, 'other case')}" + (f": same {shared}" if shared else "")
               + (f"; story similarity {result['similarity']:.2f}" if result["similarity"] else ""))
    await c.fact("colector_campanie", "campaign.link", "ledger.read_client", {"cases": n}, result, summary,
                 Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    c.save({"campaign": result})
    await c.finish("colector_campanie", summary)
    return {"campaign": result}


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


async def add_task(c: Ctx, step: str, kind: str, title: str, due_at: Any, basis: str) -> dict:
    """A follow-up a person owns, with its deadline: a ledger fact and an entry in the case's task list (one per
    kind)."""
    due = parse_dt(due_at)
    task = {"kind": kind, "title": title, "due_at": due.isoformat() if due else None, "basis": basis,
            "status": "open", "created_at": now().isoformat()}
    fid = await c.fact(step, f"task.{kind}", "tasks.create", {"kind": kind}, task,
                       title + (f" (due {fmt_datetime(due)})" if due else ""),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    tasks = [t for t in (c.rt.cases.get(c.case_id) or {}).get("tasks") or [] if t.get("kind") != kind]
    c.save({"tasks": [*tasks, {**task, "fact_id": fid}]})
    await c.em.custom("task", title, {**task, "fact_id": fid}, step=step, agent=AG[step])
    return task


def customer_notice(c: Ctx, state: dict, received: datetime) -> tuple[datetime, str | None]:
    """The first time this customer told the bank about a payment they did not make: this complaint, or an earlier
    claim of theirs in this zone. Debits after that moment are the bank's loss (Law 209/2019, art. 177(c)).
    Returns (the moment, the earlier case or None)."""
    ref = _customer_ref(state)
    told, earlier = received, None
    if not ref:
        return told, earlier
    for d in c.rt.cases.all():
        if d.get("case_id") in (None, c.case_id) or d.get("customer_ref") != ref or d.get("status") == "EROARE":
            continue
        if d.get("dispute_type") != DisputeType.NEAUTORIZATA.value \
                and not (d.get("extracted") or {}).get("claims_unauthorized"):
            continue
        at = parse_dt(d.get("received_at"))
        if at and at < told:
            told, earlier = at, d["case_id"]
    return told, earlier


async def ceasornicar(state: dict) -> dict:
    c = Ctx(state)
    await c.start("ceasornicar", "Starting the legal clocks from the moment the customer told us")
    from versoml.shared.rules import get_params
    from versoml.shared.rules.calendar_ro import add_business_days, end_of_next_business_day

    received = parse_dt(state["complaint"]["received_at"]) or now()
    t1 = end_of_next_business_day(received)
    answer = add_business_days(received, 15)
    told, earlier = customer_notice(c, state, received)
    clock = {"notified_at": received.isoformat(), "t1_deadline": t1.isoformat(),
             "answer_deadline": answer.isoformat(), "customer_told_at": told.isoformat(), "told_in_case": earlier}
    fid = await c.fact("ceasornicar", "clock.started", "rules.calendar_ro", {"notified_at": received.isoformat()},
                       clock, f"Refund deadline: {fmt_datetime(t1)} (end of the next business day). Written reply "
                              f"due by {fmt_date(answer)} (15 business days)"
                              + (f". The customer first reported an unauthorized payment on {fmt_datetime(told)} "
                                 f"(case {earlier})" if earlier else ""),
                       Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT, Sink.LETTER]))
    c.save({"clock": clock, "deadline": t1.isoformat()})
    await c.em.custom("clock", "The refund clock is running", clock, step="ceasornicar", agent=AG["ceasornicar"])
    # the customer reports a payment they did not make: the instrument is blocked now, whatever the decision
    if (state.get("extracted") or {}).get("claims_unauthorized") \
            or (state.get("classification") or {}).get("dispute_type") == DisputeType.NEAUTORIZATA.value:
        minutes = int(get_params()["block_instrument_sla_minutes"])
        await add_task(c, "ceasornicar", "block_instrument",
                       "Block the card or the app access the customer reported, so no payment goes out after the "
                       "report", received + timedelta(minutes=minutes),
                       "Law 209/2019, art. 166(1)(b) and art. 177(c)")
    await c.finish("ceasornicar", f"Refund due by {fmt_datetime(t1)}")
    return {"clock": clock, "fact_map": {"notified_at": fid, "bank_noted_at": fid, "loss_reported_at": fid}}


# ---------------------------------------------------------------- 4. Collectors (in parallel)


def _main_tx_id(state: dict) -> str | None:
    """The disputed payment: the one the identification found (or a person picked), else the one given."""
    match = state.get("match")
    if match is not None:
        return match.get("tx_id")
    refs = state["complaint"].get("transaction_refs") or []
    return refs[0] if refs else None


def _customer_ref(state: dict) -> str | None:
    match = state.get("match")
    if match is not None and match.get("customer_ref"):
        return match["customer_ref"]
    return state["complaint"].get("customer_ref")


def case_tx_refs(doc: dict) -> set[str]:
    """The payments a stored case is about: the identified one, else the ones its complaint named."""
    if doc.get("tx_refs") is not None:
        return set(doc.get("tx_refs") or [])
    return set((doc.get("complaint") or {}).get("transaction_refs") or [])


def declared_only(state: dict) -> bool:
    """True on the declared-facts path: no payment in the bank's records was matched to the complaint."""
    return state.get("match") is not None and not (state.get("match") or {}).get("tx_id")


async def colector_tranzactie(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_tranzactie", "Reading the payment and the payee from bank-core")
    tx_id = _main_tx_id(state)
    customer_ref = _customer_ref(state)
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
        card_id = g(tx, "card_id", default=None)
        if channel == "card" and card_id and hasattr(c.rt.repo, "get_card"):
            card = await c.call("colector_tranzactie", "colector", "bank-core.get_transaction",
                                lambda: c.rt.repo.get_card(card_id), {"card_id": card_id, "op": "get_card"})
            if card and card.get("scheme"):
                records["card_scheme"] = str(card["scheme"]).lower()
                fact_map["card_scheme"] = await c.fact(
                    "colector_tranzactie", "bank.card", "bank-core.get_card", {"card_id": card_id},
                    {"scheme": records["card_scheme"], "product": card.get("product"), "last4": card.get("last4")},
                    f"Paid with a {records['card_scheme'].title()} {card.get('product') or 'card'} card ending "
                    f"{card.get('last4') or '••••'}",
                    Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
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
    if not customer_ref:
        await c.finish("colector_tranzactie", "No customer identified: no payment or history to read", status="skipped")
        return {"records": records, "fact_map": fact_map}
    prior = await c.call("colector_tranzactie", "colector", "bank-core.get_prior_disputes",
                         lambda: c.rt.repo.get_prior_disputes(customer_ref, 12, exclude_case_id=c.case_id),
                         {"months": 12})
    records["prior_disputes_12m"] = len(prior or [])
    fact_map["prior_disputes_12m"] = await c.fact(
        "colector_tranzactie", "bank.prior_disputes", "bank-core.get_prior_disputes", {"months": 12},
        {"count": len(prior or [])}, f"{plural(len(prior or []), 'earlier claim')} in the last 12 months")
    await c.finish("colector_tranzactie", "The payment and its history are in the ledger")
    return {"records": records, "fact_map": fact_map}


def sca_from_events(events: list[dict]) -> dict:
    """What the SCA log says about the payment. Only a successful authentication counts as SCA: a declined or
    expired attempt, a "none" method or a card token provisioning is not one (the same rule as the scenarios). An
    attempt with no result in the log leaves SCA unknown (None): it is never read as approved."""
    attempts = [e for e in events if g(e, "method", default="") != "none"
                and g(e, "purpose", default="payment") != "token_provisioning"]
    approved = [e for e in attempts if g(e, "result") in ("approved", "success", "authenticated")]
    unreadable = not approved and any(g(e, "result") is None for e in attempts)
    payment_ok = next((e for e in approved if g(e, "purpose", default="payment") == "payment"), None)
    payment_auth = payment_ok or next((e for e in events if g(e, "purpose", default="payment") == "payment"), None)
    enrollment = next((e for e in approved if g(e, "purpose") == "device_enrollment"), None)
    # the authentication that counts: the payment's own, else enrolling the device the payment came from
    used = payment_ok or enrollment
    shown = None
    if payment_auth:
        shown = bool(g(payment_auth, "screen_showed_amount_and_payee", "dynamic_linking", default=False))
    elif enrollment:
        shown = False  # the payment left from an enrolled device; the SCA step never showed the amount
    cavv = g(payment_auth or {}, "cavv_present", "cavv")
    return {"sca_performed": None if unreadable else bool(approved),
            "sca_method": g(used or payment_auth or {}, "method", default="none"),
            "sca_step": "payment" if payment_ok else "device_enrollment" if enrollment else None,
            "screen_showed_amount_and_payee": shown, "eci": K.eci_code(g(payment_auth or {}, "eci")),
            "cavv_present": None if cavv is None else bool(cavv), "sca_unreadable": unreadable}


async def colector_sca(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_sca", "Reading the SCA log: the method and what the customer saw on screen")
    tx_id = _main_tx_id(state)
    events = await c.call("colector_sca", "colector", "sca-logs.get_auth_events",
                          lambda: c.rt.repo.get_auth_events(tx_id) if tx_id else [], {"tx_id": tx_id}) or []
    records: dict = {"auth_events": events}
    fact_map: dict = {}
    sca = sca_from_events(events)
    shown = sca["screen_showed_amount_and_payee"]
    records.update(sca)
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
                                   + ("showed" if shown else "did not show") + " the amount and the payee"
                                   + ("; an attempt has no result in the log, so SCA is unknown"
                                      if sca["sca_unreadable"] else ""))
    return {"records": records, "fact_map": fact_map}


def device_known_from(history: list[dict], device_id: str | None, executed_at: datetime) -> bool | None:
    """Whether the payment's device is the customer's: known = trusted and enrolled at least a day before the
    payment (a phone enrolled minutes ago counts as new). A device not on a customer's list is new. Without a
    history, or a record without its trust flag or enrollment date, the answer is unknown (None), never trusted."""
    if not device_id or not history:
        return None
    entry = next((d for d in history if g(d, "device_id", "fingerprint", "device_fingerprint") == device_id), None)
    if entry is None:
        return False
    trusted = g(entry, "trusted", "known")
    enrolled = parse_dt(g(entry, "enrolled_at", "first_seen", "first_seen_at"))
    if trusted is False:
        return False
    if trusted is None or enrolled is None:
        return None
    return enrolled < executed_at - timedelta(days=1)


async def colector_dispozitiv(state: dict) -> dict:
    c = Ctx(state)
    await c.start("colector_dispozitiv", "Checking the device, the session and any SIM swap")
    customer_ref = _customer_ref(state)
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
        if g(session, "device_known") is not None:
            device_known = bool(g(session, "device_known"))
        else:
            device_known = device_known_from(history, device_id, executed_at)
        click = parse_dt(g(session, "link_clicked_at", "click_at", "clicked_at"))
        executed = parse_dt(g(tx or {}, "executed_at", "ts", "timestamp"))
        seconds = g(session, "seconds_after_click")
        if seconds is None and click and executed:
            seconds = int((executed - click).total_seconds())
        records.update({"device_known": device_known, "seconds_after_click": seconds, "session": session,
                        "device_unreadable": device_known is None})
        what = {True: "Known device", False: "NEW device, never seen before"}.get(
            device_known, "Device with no enrollment history: whether it is the customer's is unknown")
        fid = await c.fact("colector_dispozitiv", "device.session", "device.get_session", {"session_id": session_id},
                           session, what
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
    targets = _attack_targets(state)
    urls, domains, phones = targets["urls"], targets["domains"], targets["phones"]
    records: dict = {"attack": {"domains": domains[:3], "urls": urls[:3], "phones": phones[:3]}}
    fact_map: dict = {}
    intel: dict = {}
    if not domains:
        site = ((state.get("records") or {}).get("merchant") or {}).get("domain")
        if site:
            return await _merchant_site(c, site, records)
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


async def _merchant_site(c: "Ctx", site: str, records: dict) -> dict:
    """The online shop the card payment went to: its age and likeness to the bank, as information. It is not treated
    as the scammer's domain, and nothing about it goes to AML."""
    from versoml.osint import domain as osd
    from versoml.osint import lookalike as osl

    fact_map: dict = {}
    summaries: dict[str, str] = {}
    for name, action, fn in (("rdap", "domain-intel.rdap_lookup", lambda: osd.rdap_domain(site)),
                             ("lookalike", "domain-intel.lookalike_score", lambda: osl.lookalike_score(site))):
        try:
            result = await c.call("colector_domeniu", "colector", action, fn, {"domain": site})
        except Exception as exc:  # noqa: BLE001 - one failed tool doesn't stop the collector
            log.warning("%s failed: %s", action, exc)
            continue
        data = _osint_dump(result)
        summaries[name] = "Merchant site: " + _intel_summary(name, site, data)
        fact_map[f"merchant_domain_{name}"] = await c.fact(
            "colector_domeniu", f"merchant.domain_{name}", f"domain-intel.{name}", {"domain": site}, data,
            summaries[name], Labels(conf="public", trust=Trust.UNTRUSTED, sinks=[Sink.CLIENT]))
    records["merchant_site"] = site
    await c.finish("colector_domeniu", f"Merchant site {site} checked (information only)", {"intel": summaries})
    return {"records": records, "fact_map": fact_map}


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


def unauthorised_signals(records: dict, extracted: dict) -> list[str]:
    """What points to a payment the customer did not make: the bank's logs, and the customer's own words."""
    signals = []
    if records.get("sca_performed") is False:
        signals.append("the bank's log shows no strong authentication for the payment")
    if records.get("device_known") is False:
        signals.append("the payment came from a device the customer had not used before")
    if extracted.get("claims_unauthorized") is True:
        signals.append("the customer says they did not make it")
    return signals


def reconcile_type(cls: dict, records: dict, extracted: dict) -> tuple[DisputeType, bool, str]:
    """The final classification: the text (M1) reconciled with the facts in the bank's systems. A merchant or
    processing-error label from the text never outweighs the signs of an unauthorized payment, and a log the
    collectors could not read sends the case to a person."""
    ml_type = DisputeType(cls.get("dispute_type", "neautorizata"))
    approved_in_app = bool(records.get("screen_showed_amount_and_payee")) and bool(records.get("device_known"))
    if records.get("duplicate_of"):
        return DisputeType.EROARE_PROCESARE, False, "duplicate payment found in bank-core"
    if ml_type in (DisputeType.DISPUTA_COMERCIANT, DisputeType.EROARE_PROCESARE):
        signals = unauthorised_signals(records, extracted)
        if not signals:
            return ml_type, bool(cls.get("ambiguous")), "the text describes a problem with the merchant"
        reason = (f"the text suggests {label(DISPUTE_LABELS, ml_type)} but {join_and(signals)}: the facts decide, "
                  "and a person confirms")
        return DisputeType.NEAUTORIZATA, True, reason
    fact_type = DisputeType.APP if approved_in_app and records.get("channel") != "card" else DisputeType.NEAUTORIZATA
    if records.get("device_known") is False:
        fact_type = DisputeType.NEAUTORIZATA
    gaps = [what for key, what in (("sca_unreadable", "an SCA attempt has no result in the log"),
                                   ("device_unreadable", "the device has no enrollment history"))
            if records.get(key)]
    ambiguous = bool(cls.get("ambiguous")) or fact_type != ml_type or bool(gaps)
    reason = ("the facts match the text" if fact_type == ml_type else
              f"the text suggests {label(DISPUTE_LABELS, ml_type)} but the facts show "
              f"{label(DISPUTE_LABELS, fact_type)}: the facts decide, and a person is told")
    if gaps:
        reason += f"; {join_and(gaps)}, so a person checks who authorized it"
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
    elif channel_raw == "direct_debit" or g(tx, "kind") in ("direct_debit", "utility"):
        channel = Channel.DIRECT_DEBIT
    else:
        channel = Channel.TRANSFER
    # where the card was read: POS and ATM are card present (10.1-10.3, 13.9), e-commerce is not (10.4)
    entry = g(tx, "pos_entry_mode") or {"card_pos": "chip", "card_atm": "atm", "card_ecom": "ecommerce"}.get(
        g(tx, "kind") or "") if channel == Channel.CARD else None
    records["channel"] = channel.value
    dispute_type, ambiguous, reason = reconcile_type(state.get("classification") or {}, records, state.get("extracted") or {})
    cls = state.get("classification") or {}
    text_type = cls.get("dispute_type") or DisputeType.NEAUTORIZATA.value
    # the text and the bank's records disagree on what kind of claim this is: the console shows it to the person
    conflict = ({"text_type": text_type, "fact_type": dispute_type.value, "reason": reason}
                if ambiguous and text_type != dispute_type.value else None)
    scenario = cls.get("scenario")
    hint = (state.get("scenario_hint") or "")
    if hint and hint in Scenario._value2member_map_:
        scenario = hint

    declared = declared_only(state)
    signal = None
    try:
        if declared:
            raise LookupError("declared facts only: no payment to score")
        from versoml.ml.m2_client_fraud import client_fraud_signal, features_from_repo

        try:  # the same objective features the model was trained on, read from the bank's logs
            features = features_from_repo(c.rt.repo, _customer_ref(state), _main_tx_id(state),
                                          state["complaint"]["received_at"])
        except Exception as exc:  # noqa: BLE001 - fall back to what the collectors already gathered
            log.warning("M2 features from the repo failed: %s", exc)
            features = {"prior_disputes_12m": records.get("prior_disputes_12m", 0),
                        "device_known": records.get("device_known"),
                        "beneficiary_new": records.get("beneficiary_new"), "channel": channel.value}
        signal = client_fraud_signal(features)
    except LookupError:
        signal = None
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
    told = parse_dt((state.get("clock") or {}).get("customer_told_at")) or notified
    extracted = state.get("extracted") or {}
    claimed = [m for m in (K.money(x) for x in extracted.get("amounts") or extracted.get("mentioned_amounts") or []) if m]
    main = _main_tx_id(state)
    refs = {main} if main else set()
    other_dispute = any(d.get("case_id") not in (None, c.case_id) and d.get("status") not in ("EROARE",)
                        and refs & case_tx_refs(d) for d in c.rt.cases.all())
    amount = Money(value=float(g(tx, "amount", "value", default=0)), currency=g(tx, "currency", default="RON"))
    if declared:
        # the customer's statements only (DSP-53): untrusted, used to ask for the rest, never to pay or refuse
        stated = state.get("declared") or {}
        value = stated.get("amount") or {}
        amount = Money(value=float(value.get("value") or 0), currency=value.get("currency") or "RON")
        day = stated.get("date")
        try:  # noon in Bucharest that day, with the day's real offset (summer time is +03:00)
            executed = K.local_noon(date.fromisoformat(str(day)[:10])) if day else notified
        except ValueError:
            executed = notified
        claimed = []
        hinted = stated.get("channel")
        if not tx and hinted in ("card", "transfer", "transfer_instant"):
            channel = Channel(hinted)
            records["channel"] = channel.value
    ctx = RuleContextExt(
        transaction_identified=not declared, customer_identified=bool(_customer_ref(state)),
        existing_dispute_for_txn=other_dispute,
        classification_ambiguous=ambiguous,
        beneficiary_iban=g(tx, "beneficiary_iban", "counterparty_iban", "to_iban"),
        complaint_received_at=notified,
        # from the bank's card record; unknown leaves the rules' documented default (Visa)
        card_scheme=records.get("card_scheme") if channel == Channel.CARD else None,
        pos_entry_mode=entry, purchase_type="atm_cash" if entry == "atm" else None,
        processing_date=executed.date(),
        # admissions the intake could not find word for word in the text, and the checked vulnerability signals
        unconfirmed_admissions=list(extracted.get("to_confirm") or []),
        vulnerability_signals=sorted({str(v.get("kind")) for v in extracted.get("vulnerability") or []
                                      if isinstance(v, dict) and v.get("kind")}),
        injection_suspected=bool(extracted.get("injection_suspected")),
        # the claimed amount = the one in the text in the payment's currency and closest to the log (the text also
        # mentions the RON 2.99 bait fee); an amount in another currency isn't compared
        claimed_amount=_claimed_amount(claimed, amount),
        case_id=c.case_id, now=now(), channel=channel, dispute_type=dispute_type,
        scenario=Scenario(scenario) if scenario in Scenario._value2member_map_ else None,
        amount=amount, executed_at=executed, notified_at=notified,
        sca_performed=records.get("sca_performed"), sca_method=records.get("sca_method"),
        eci=K.eci_code(records.get("eci") or g(tx, "eci")), cavv_present=records.get("cavv_present"),
        screen_showed_amount_and_payee=records.get("screen_showed_amount_and_payee"),
        device_known=records.get("device_known"), seconds_after_click=records.get("seconds_after_click"),
        sim_swap_hours_before=records.get("sim_swap_hours_before"), beneficiary_new=records.get("beneficiary_new"),
        merchant_mcc=g(tx, "mcc", "merchant_mcc"), duplicate_of=records.get("duplicate_of"),
        prior_disputes_12m=int(records.get("prior_disputes_12m") or 0),
        client_fraud_score=float(signal["score"]) if signal and signal.get("score") is not None else None,
        client_admits_sharing_credentials=(state.get("extracted") or {}).get("client_admits_sharing_credentials"),
        client_admits_approving_in_app=(state.get("extracted") or {}).get("client_admits_approving_in_app"),
        customer_claims_unauthorised=extracted.get("claims_unauthorized"),
        hold_signal=bool(hold.get("hold")), hold_authority_notified=bool(hold.get("authority_notified")),
        # the moment the customer told the bank: debits after it are the bank's loss (art. 177(c)), and a debit after
        # an earlier report was known to the bank as soon as it went out (DSP-58)
        loss_reported_at=told, bank_noted_at=max(told, executed),
        llm_mode=state.get("llm_mode") or doc.get("llm_mode"),
        fact_ids={k: v for k, v in fact_map.items() if isinstance(v, str)},
    )
    await c.em.custom("classification_final", f"Final classification: {label(DISPUTE_LABELS, dispute_type)} ({reason})",
                      {"dispute_type": dispute_type.value, "ambiguous": ambiguous}, step="motor_reguli",
                      agent=AG["motor_reguli"])
    if conflict:
        conflict["fact_id"] = await c.fact(
            "motor_reguli", "classification.conflict", "rules.reconcile_type", {"text_type": text_type}, conflict,
            f"The text reads as {label(DISPUTE_LABELS, text_type)}, the bank's records as "
            f"{label(DISPUTE_LABELS, dispute_type)}: the records decide and a person confirms",
            Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
        await c.em.custom("classification_conflict", f"The text and the bank's records disagree: {reason}", conflict,
                          step="motor_reguli", agent=AG["motor_reguli"])
    c.save({"classification_conflict": conflict})
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
    standard = standard_record(ctx, extracted, pos_entry_mode=g(tx, "pos_entry_mode", default=None),
                               sca_step=records.get("sca_step"))
    await c.fact("motor_reguli", "case.standard", "canonical.v1", {"schema": standard.schema_version},
                 standard.model_dump(mode="json"), _standard_summary(standard),
                 Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    c.save({"standard": standard.model_dump(mode="json")})
    c.save({"rule_context": ctx.model_dump(mode="json"), "rules": outcome.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "verdict": t1.decision.value if t1 else None, "channel": channel.value,
            "scenario": ctx.scenario.value if ctx.scenario else scenario,
            "amount": ctx.amount.model_dump(), "dispute_type": dispute_type.value,
            "amount_source": "declared" if declared else "ledger"})
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
    if declared_only(state):
        await c.finish("outbox_aml", "Nothing sent to AML: the payment is not identified in the bank's records yet",
                       status="skipped")
        return {}
    if ctx["dispute_type"] not in ("neautorizata", "app") or not (bene_iban or attack.get("domain")):
        await c.finish("outbox_aml", "Not a fraud case with a payee: nothing to send", status="skipped")
        return {}
    victim_ref = "VCT-" + hashlib.sha256(f"versoml|{_customer_ref(state)}".encode()).hexdigest()[:6]
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


def _claimed_amount(mentions: list[Money], amount: Money) -> float | None:
    pick = K.closest_amount(mentions, amount)
    return pick.value if pick and pick.currency == amount.currency else None


CONTACT_STANDARD = {"sms": "sms", "apel": "call", "email": "email", "mesagerie": "messaging", "site": "website",
                    "necunoscut": "unknown"}
PAYMENT_TYPE = {Channel.CARD: "card", Channel.TRANSFER: "credit_transfer", Channel.TRANSFER_INSTANT: "instant_credit_transfer",
                Channel.DIRECT_DEBIT: "direct_debit"}


def standard_record(ctx: RuleContext, extracted: dict, *, pos_entry_mode: str | None = None,
                    sca_step: str | None = None) -> StandardRecord:
    """The case in published codes (ISO 4217, ISO 8601, ISO 13616, ISO 18245, E.164, EBA fraud types, the card
    scheme's ECI table), with a plain list of what the data didn't let it read."""
    issues: list[str] = []
    card = ctx.channel == Channel.CARD
    scheme = getattr(ctx, "card_scheme", None) if card else None
    scheme = scheme if scheme in ("visa", "mastercard") else None
    if card and not scheme:
        issues.append("The card's scheme isn't in the bank's records, so the rules assume Visa")
    three = K.three_ds(ctx.eci, scheme) if card else None
    if card and ctx.eci and scheme and three is None:
        issues.append(f"ECI {ctx.eci} isn't a {scheme.title()} code, so the 3-D Secure outcome can't be read from it")
    payee = getattr(ctx, "beneficiary_iban", None)
    if payee and not re.match(r"[A-Za-z]{2}[0-9]{2}", payee.replace(" ", "")):
        payee = None  # a cash withdrawal records "NUMERAR" there, not an account
    valid = (K.iban(payee) is not None) if payee else None
    if valid is False:
        issues.append("The payee's IBAN fails its check digits (ISO 13616)")
    claimed_value = getattr(ctx, "claimed_amount", None)
    claimed = Money(value=claimed_value, currency=ctx.amount.currency) if claimed_value is not None else None
    if claimed and abs(claimed.value - ctx.amount.value) > 0.005:
        issues.append(f"The customer mentions {money(claimed.value, claimed.currency)}; the bank's record says "
                      f"{money(ctx.amount.value, ctx.amount.currency)}")
    executed = K.local(ctx.executed_at) if ctx.executed_at else None
    reported = K.local(ctx.notified_at) if ctx.notified_at else None
    fraud = K.eba_fraud_type(ctx.channel, ctx.dispute_type, ctx.scenario, pos_entry_mode)
    return StandardRecord(
        case_id=ctx.case_id, payment_type=PAYMENT_TYPE[ctx.channel], amount=ctx.amount,
        executed_at=executed, reported_at=reported,
        days_to_report=(reported.date() - executed.date()).days if executed and reported else None,
        fraud_type=fraud, fraud_type_label=K.EBA_LABELS.get(fraud) if fraud else None,
        authentication="sca" if ctx.sca_performed else "no_sca" if ctx.sca_performed is False else "unknown",
        sca_method=ctx.sca_method if ctx.sca_method not in (None, "none") else None,
        sca_step=sca_step if ctx.sca_performed else None,
        card_scheme=scheme, eci=ctx.eci if card else None, three_ds=three,
        merchant_mcc=str(ctx.merchant_mcc) if ctx.merchant_mcc else None,
        payee_iban=K.mask_iban(payee) if payee else None, payee_iban_valid=valid,
        contact_channel=CONTACT_STANDARD.get(extracted.get("contacted_by") or "", None),
        claimed_amount=claimed,
        phones=[m for p in extracted.get("phones_e164") or [] if (m := K.mask_phone(p))],
        websites=list(extracted.get("hosts") or []), issues=issues,
    )


def _standard_summary(r: StandardRecord) -> str:
    parts = [r.fraud_type_label or "Not a fraud case", r.payment_type.replace("_", " "),
             money(r.amount.value, r.amount.currency) if r.amount else "no amount",
             {"sca": "SCA done", "no_sca": "no SCA", "unknown": "SCA unknown"}[r.authentication]]
    if r.three_ds:
        parts.append(f"3-D Secure {r.three_ds.replace('_', ' ')}")
    tail = f"; {plural(len(r.issues), 'data issue')}" if r.issues else ""
    return "Standard record: " + " · ".join(parts) + tail


async def rambursare(state: dict) -> dict:
    c = Ctx(state)
    d = _decision(state, Question.RAMBURSARE_T1)
    if state.get("refund", {}).get("done"):
        return {}
    verdict = d["decision"] if d else None
    amount = float((state["rule_context"].get("amount") or {}).get("value", 0))
    currency = (state["rule_context"].get("amount") or {}).get("currency") or "RON"
    customer_ref = _customer_ref(state)
    # when the graph resumes after the signature, the node runs again up to interrupt(): emit nothing twice
    pending = (c.rt.cases.get(c.case_id) or {}).get("interrupt") or {}
    resuming = pending.get("kind") != "pick_transaction" and bool(pending.get("pending") or pending.get("resuming"))
    if not resuming:
        await c.start("rambursare", f"Applying the refund decision: {label(VERDICT_LABELS, verdict)}"
                      + (f" ({verdict})" if verdict else ""))

    if verdict == Verdict.INFORMATII_SUPLIMENTARE.value:
        # declared facts only (DSP-53): nothing to refund or refuse until a person identifies the payment
        c.save({"status": "IN_ANALIZA"})
        await c.finish("rambursare", "No refund decision yet: the payment is not identified in the bank's records. "
                                     "A person follows up and the customer is asked for the details", status="skipped")
        return {"refund": {"done": False, "status": "IN_ANALIZA"}}

    # every decision that needs a person stops here for a signature, the "no next-business-day refund" route too
    if verdict in (Verdict.RAMBURSEAZA_CU_APROBARE.value, Verdict.EXCEPTIE_FRAUDA_CLIENT.value,
                   Verdict.RESPINGE_TARDIV.value) or (d and d.get("requires_human")):
        deadline = (d.get("deadline") if d else None) or (state.get("clock") or {}).get("t1_deadline")
        refund_verdict = verdict in REFUND_VERDICTS
        refund_prompt = refund_approval_prompt(amount, deadline, (state.get("rules") or {}).get("hits"), currency)
        prompt = {
            Verdict.RAMBURSEAZA.value: refund_prompt,
            Verdict.RAMBURSEAZA_CU_APROBARE.value: refund_prompt,
            Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "The AML zone sent a HOLD approved by an analyst, and the authority "
                                                 "has been notified. Confirm the C-70/25 exception (no refund for now)?",
            Verdict.RESPINGE_TARDIV.value: "The customer told us more than 13 months after the payment (art. 169). "
                                          "An unfavorable decision needs a person's approval (GDPR art. 22). "
                                          "Confirm the rejection?",
            Verdict.NU_SE_APLICA_T1.value: route_prompt(state["rule_context"], deadline),
        }.get(verdict, "This decision needs a person's signature.")
        payload = {"kind": "aprobare_rambursare" if refund_verdict else "semnatura_decizie",
                   "verdict": verdict, "prompt": prompt, "options": ["approve", "reject"], "amount": amount,
                   "deadline": deadline, "rule_ids": d.get("rule_ids", []) if d else []}
        if not resuming:
            c.track("rambursare", "waiting", "Needs approval")
            c.save({"interrupt": {"pending": True, **payload}, "status": "ASTEAPTA_APROBARE"})
            await c.em.custom("interrupt", prompt, payload, step="rambursare", agent=AG["rambursare"])
        answer = interrupt(payload) or {}
        c.save({"interrupt": {**payload, "pending": False, "resuming": False, "answer": answer}})
        approved = answer.get("action") == "approve"
        approver = answer.get("approver") or "OPERATOR-01"
        reason = _signature(answer, prompt)
        await c.fact("rambursare", "human.signature", "console.operator", {"approver": approver},
                     {"action": answer.get("action"), "note": answer.get("note"), **reason},
                     f"{approver} {'approved' if approved else 'rejected'} the {verdict} decision"
                     + (f" ({reason['reason_code']})" if reason.get("reason_code") else ""))
        c.save({"approved_by" if approved else "rejected_by": approver,
                "approved_at" if approved else "rejected_at": now().isoformat(), "signature": reason})
        if refund_verdict and approved:
            return await _issue_refund(c, state, customer_ref, approved_by=approver)
        if refund_verdict:
            # the person declined the refund: VersoML stops here and the case is theirs to handle by hand.
            # The refund deadline still applies (refund, or report suspected fraud to the authority, DSP-05).
            c.save({"status": "REFUZAT"})
            answer_due = (_decision(state, Question.RASPUNS_RECLAMATIE) or {}).get("deadline") \
                or (state.get("clock") or {}).get("answer_deadline")
            await add_task(c, "rambursare", "written_answer",
                           "Write to the customer why the refund was declined, answering every point and naming "
                           "where to complain (ANPC, ANAF, BNR, CSALB)", answer_due, "Law 209/2019, art. 224-225")
            await c.finish("rambursare", f"Refund declined by {approver}: no refund from VersoML. "
                                         "A person handles the case; the refund deadline still applies")
            return {"refund": {"done": False, "status": "REFUZAT", "declined_by": approver}}
        if not approved and not state["rule_context"].get("credit_fraud"):
            # the person did not confirm the unfavorable decision: refund within the deadline, signed by them
            decisions = _overridden(state, verdict, approver)
            c.save({"decisions": decisions, "verdict": Verdict.RAMBURSEAZA_CU_APROBARE.value,
                    "verdict_by_rules": verdict})
            refunded = await _issue_refund(c, {**state, "decisions": decisions}, customer_ref, approved_by=approver)
            return {**refunded, "decisions": decisions}
        route = "TRASEU_APP" if state["rule_context"]["dispute_type"] == "app" else "IN_ANALIZA"
        status = {Verdict.EXCEPTIE_FRAUDA_CLIENT.value: "EXCEPTIE", Verdict.RESPINGE_TARDIV.value: "RESPINS",
                  Verdict.NU_SE_APLICA_T1.value: route}.get(verdict, "IN_ANALIZA")
        c.save({"status": status})
        await c.finish("rambursare", f"Decision signed by {approver}: {status}")
        return {"refund": {"done": False, "status": status}}

    if verdict == Verdict.RAMBURSEAZA.value:
        return await _issue_refund(c, state, customer_ref, approved_by=None)

    status = "TRASEU_APP" if state["rule_context"]["dispute_type"] == "app" else "IN_ANALIZA"
    c.save({"status": status})
    await c.finish("rambursare", "The next-business-day refund does not apply: recovery and support route", status="skipped")
    return {"refund": {"done": False, "status": status}}


def route_prompt(ctx: dict, deadline: Any) -> str:
    """The question for a signed "the next-business-day refund does not apply" decision, and what each answer
    does."""
    why = {"app": "the customer approved the payment under manipulation (APP)",
           "disputa_comerciant": "this is a dispute with the merchant",
           "eroare_procesare": "this is a processing error"}.get(str(ctx.get("dispute_type")),
                                                                 "it follows another route")
    if ctx.get("credit_fraud"):
        return ("The next-business-day refund does not apply: a loan was taken out in the customer's name. An "
                "unfavorable decision needs a person's approval (GDPR art. 22). Confirm the credit fraud route?")
    when = fmt_deadline(deadline)
    return (f"The next-business-day refund does not apply: {why}. An unfavorable decision needs a person's approval "
            f"(GDPR art. 22). Confirm the recovery and support route? If you reject it, the payment is treated as "
            f"unauthorized and refunded" + (f" by {when}." if when else "."))


def _signature(answer: dict, prompt: str) -> dict:
    """The reason the service checked and sent with the answer; an answer that came without one gets the default
    for its action."""
    if answer.get("reason_code"):
        return {k: answer.get(k) for k in ("reason_code", "reason_text", "reason_from_note")}
    reason = signature_reason(str(answer.get("action") or ""), None, answer.get("note"), prompt)
    return reason if "error" not in reason else {"reason_code": None, "reason_text": prompt, "reason_from_note": False}


def _overridden(state: dict, verdict: str, approver: str) -> list[dict]:
    """The decisions once a person did not confirm an unfavorable refund decision: the refund is due, on their
    signature. The rules engine's own decision stays in the ledger (rules.outcome)."""
    line = {"text": f"{approver} did not confirm {verdict}: the payment is refunded by the deadline.", "cites": []}
    out = []
    for d in state.get("decisions") or []:
        if d.get("question") in (Question.RAMBURSARE_T1.value, Question.RASPUNS_RECLAMATIE.value) \
                and d.get("decision") == verdict:
            d = {**d, "decision": Verdict.RAMBURSEAZA_CU_APROBARE.value, "requires_human": True, "decided_by": "human",
                 "rationale": [*(d.get("rationale") or []), line]}
        out.append(d)
    return out


def refund_plan(ctx: dict) -> dict:
    """What goes back, in the currency debited: the payment's amount, less the customer's share under Law
    209/2019, art. 179(1) only when the bank keeps it (the [U] parameter `retain_payer_liability`). In the art. 177
    cases the share is zero; without a EUR rate for the currency it is unknown, and nothing is kept."""
    from versoml.shared.rules import RuleContextExt, get_params
    from versoml.shared.rules.facts import eur_cap_in
    from versoml.shared.rules.packs.pay import art177_reasons, payer_liability

    x = RuleContextExt.model_validate(ctx)
    params = get_params()
    art177 = bool(art177_reasons(x))
    cap = eur_cap_in(x.amount.currency, 30.0, params["eur_ron_rate"])
    share = None if cap is None else payer_liability(
        x.amount.value, payer_fraud=False, art177_case=art177, intent_or_gross_negligence_proven=False,
        lost_stolen_misappropriated=True, cap=cap)
    kept = bool(params["retain_payer_liability"]) and bool(share)
    return {"debited": x.amount.value, "currency": x.amount.currency,
            "refund": round(x.amount.value - (share if kept else 0), 2), "payer_liability": share, "cap": cap,
            "retained": kept, "basis": "Law 209/2019, art. 177" if art177 else "Law 209/2019, art. 179(1)"}


def _liability_words(plan: dict) -> str:
    share, currency = plan["payer_liability"], plan["currency"]
    if share is None:
        return "the customer's share under art. 179(1) can't be worked out in this currency, so nothing is kept"
    if not share:
        return "the customer bears nothing (art. 177)"
    if plan["retained"]:
        return f"the customer's share under art. 179(1), {money(share, currency)}, is kept back"
    return f"the customer's share under art. 179(1), up to {money(share, currency)}, is waived"


async def _issue_refund(c: Ctx, state: dict, customer_ref: str, approved_by: str | None) -> dict:
    context = {"within_auto_cap": approved_by is None, "approved_by_human": approved_by is not None}
    decision = c.rt.authorize("motor", "refund.issue", Zone.CLIENT, context)
    plan = refund_plan(state["rule_context"])
    amount, currency = plan["refund"], plan["currency"]
    if not decision.allowed:
        await c.em.custom("policy_denied", "Cedar denied the refund instruction", decision.model_dump(mode="json"),
                          step="rambursare", agent=AG["rambursare"])
        await c.finish("rambursare", "The policy blocked the refund instruction", status="blocked")
        return {"refund": {"done": False, "status": "BLOCAT"}}
    # a payment is refunded once, however many disputes it gets (an operational guard, not a legal rule)
    main = _main_tx_id(state)
    refs = {main} if main else set()
    prior = next((d for d in c.rt.cases.all() if d.get("case_id") not in (None, c.case_id) and d.get("status") == "RAMBURSAT"
                  and refs & case_tx_refs(d)), None)
    if prior:
        await c.fact("rambursare", "refund.duplicate", "refund.issue", {"tx": sorted(refs)},
                     {"already_refunded_in": prior["case_id"]},
                     f"This payment was already refunded in case {prior['case_id']}: no second refund")
        c.save({"status": "RAMBURSAT", "refund_of": prior["case_id"]})
        await c.finish("rambursare", f"Already refunded in {prior['case_id']}: no double payment")
        return {"refund": {"done": True, "status": "RAMBURSAT", "duplicate_of": prior["case_id"]}}
    key = f"refund-{c.case_id}"
    # back to the account the payment left, in the payment's currency (an account in another currency is an error)
    account = g((state.get("records") or {}).get("transaction") or {}, "account_iban")
    result = (c.rt.repo.post_refund(c.case_id, customer_ref, amount, key, account_iban=account, currency=currency)
              if amount > 0 else {"status": "nothing to refund: the customer's share covers the payment"})
    refund = {"amount": amount, "currency": currency, "debited": plan["debited"],
              "to_account": K.mask_iban(account) if account else None,
              **{k: plan[k] for k in ("payer_liability", "cap", "retained", "basis")}}
    await c.fact("rambursare", "refund.instruction", "refund.issue", {"idempotency_key": key},
                 {**refund, "result": result, "approved_by": approved_by, "decided_by": "MotorReguli"},
                 f"Refund instruction for {money(amount, currency)} to the account debited, issued by the rules engine"
                 + (f", approved by {approved_by}" if approved_by else " (under the cap, no signals)")
                 + f"; {_liability_words(plan)}")
    # the "We've refunded you…" notification is written by core banking (post_refund), like any other transaction
    c.save({"status": "RAMBURSAT", "refunded_at": now().isoformat(), "refund": refund})
    await c.em.custom("refund", f"Refunded {money(amount, currency)}", {**refund, "approved_by": approved_by},
                      step="rambursare", agent=AG["rambursare"])
    await c.finish("rambursare", f"Refunded {money(amount, currency)} before the refund deadline")
    return {"refund": {"done": True, "status": "RAMBURSAT", **refund}}


# ---------------------------------------------------------------- 8. The debate (recovery route only)


def _facts_brief(c: Ctx, limit: int = 30) -> tuple[str, set[str]]:
    facts = c.rt.ledger.facts(c.case_id)
    ids = {f.fact_id for f in facts}
    lines = [f"- {f.fact_id} [{f.kind}]: {f.summary}" for f in facts if f.kind not in ("complaint.received",)][:limit]
    brief, _ = c.rt.privacy.pseudonymize("\n".join(lines), c.case_id)  # nothing raw goes to the model
    return brief, ids


def _verify(lines: list[P.ArgLine], valid: set[str], kb: set[str] | None = None) -> tuple[list[dict], int]:
    """Keeps the lines that cite at least one evidence ID; knowledge-base passages ([KB-n]) ride along as legal
    support but never stand in for evidence."""
    kept, rejected = [], 0
    for line in lines:
        cites = [x for x in line.cites if x in valid]
        kb_cites = [x for x in line.cites if x in (kb or set())]
        kb_cites += [x for x in re.findall(r"\bKB-\d+\b", line.text) if x in (kb or set()) and x not in kb_cites]
        if cites:
            kept.append({"text": line.text, "cites": cites, **({"kb_cites": kb_cites} if kb_cites else {})})
        else:
            rejected += 1
    return kept, rejected


async def _record_grounding(c: "Ctx", used_in: str, hits: list[dict], step: str = "redactor") -> None:
    """The knowledge-base passages a draft relied on: a ledger fact, and the case's `grounding` list."""
    if not hits:
        return
    slim = [{k: h.get(k) for k in ("id", "kind", "title", "source", "confidence", "rule_ids", "score")} for h in hits]
    await c.fact(step, "kb.citations", "knowledge.search", {"used_in": used_in},
                 {"used_in": used_in, "hits": slim},
                 f"{plural(len(hits), 'knowledge passage')} cited in the {used_in}",
                 Labels(conf="public", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))
    doc = c.rt.cases.get(c.case_id) or {}
    grounding = [e for e in doc.get("grounding") or [] if e.get("used_in") != used_in]
    grounding += [{"used_in": used_in, "hit": h} for h in hits]
    c.save({"grounding": grounding})


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
         ctx.get("seconds_after_click") is not None and ctx["seconds_after_click"] < 300, -1, "seconds_after_click"),
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
    # the legal passages behind the recovery rules, from the knowledge base: citable for points of law, never evidence
    from versoml.zone_client import grounding as G

    recovery_rules = (_decision(state, Question.RECUPERARE_CLIENT) or {}).get("rule_ids") or ["PAY-06", "PAY-02"]
    passages = [h for h in G.for_rules(recovery_rules, k_per=1) if h.get("kind") in ("rule", "law", "guidance")][:4]
    kb_ids = {f"KB-{i}": h for i, h in enumerate(passages, 1)}
    if passages:
        lines = "\n".join(f"- {kid} ({h.get('source') or h.get('title')}): {(h.get('text') or '')[:400]}"
                          for kid, h in kb_ids.items())
        question += ("\n\n" + wrap_data("legal_passages", lines)
                     + "\nYou may cite a passage as [KB-n] for a point of law, next to the evidence IDs.")
    await c.start("procuror", "The prosecutor argues for recovery (Opus), citing the evidence")
    await c.start("avocat", "The defender argues for the customer (a different model), citing the evidence")

    async def statement(side: str) -> tuple[P.Argument, Any]:
        system = P.PROCUROR_SYSTEM if side == "procuror" else P.AVOCAT_SYSTEM
        role = Role.OPUS if side == "procuror" else Role.SONNET
        return await c.rt.llm.structured(role=role, agent=AG[side], system=system, user=question, schema=P.Argument,
                                         effort="medium", max_tokens=3000,
                                         fallback=lambda: _fallback_argument(side, ctx, fm), scope=replay_scope(state))

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
                                         fallback=lambda: P.Argument(claims=[], missing_evidence=[], strongest_point=""),
                                         scope=replay_scope(state))

    (pro_r, _), (con_r, _) = await asyncio.gather(rebut("procuror", pro, con), rebut("avocat", con, pro))
    pro_lines, pro_bad = _verify(pro.claims + pro_r.claims, valid, set(kb_ids))
    con_lines, con_bad = _verify(con.claims + con_r.claims, valid, set(kb_ids))
    cited = sorted({x for line in pro_lines + con_lines for x in line.get("kb_cites", [])})
    if cited:
        await _record_grounding(c, "debate", [kb_ids[k] for k in cited], step="cantaritor")
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
        lines.append(f"URL reported by the customer, not yet confirmed by the bank: {url}.")
    if phones:
        lines.append(f"Phone {'number' if len(phones) == 1 else 'numbers'} the customer says the scammer used, not yet "
                     f"confirmed by the bank: {', '.join(phones)}.")
    age = attack.get("domain_age_hours")
    if isinstance(age, (int, float)):
        lines.append(f"The domain was registered about {plural(round(age), 'hour')} before the attack.")
    lines.append("We ask you to block the domain and take the page down." if domain
                 else "We ask you to block the number.")
    return P.DnscDraft(title=f"Phishing: {domain or 'fraudulent phone call'}", body=" ".join(lines),
                       indicators=[x for x in [domain, url, *phones] if x])


async def recuperare(state: dict) -> dict:
    c = Ctx(state)
    if declared_only(state):
        c.track("recuperare", "skipped", "No recovery drafts: the payment is not identified in the bank's records yet")
        return {"recovery": {"decision": None, "skipped": "payment not identified"}}
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
    elif ctx["channel"] == Channel.DIRECT_DEBIT.value:
        # a direct debit goes back through the direct debit scheme (PAY-10), never as a credit transfer recall
        recovery["direct_debit_refund"] = {
            "eligible": escroc.get("decision") == "RECUPERARE_PROPUSA",
            "explanation": next((h.get("explanation") for h in rules.get("hits", []) if h.get("rule_id") == "PAY-10"),
                                "A person decides the claim against the payee's bank."),
            "deadline": next((dl["due_at"] for dl in rules.get("deadlines", []) if dl.get("rule_id") == "PAY-10"), None),
        }
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
        # the link and the numbers come from the customer's text: the report carries them as data nobody has confirmed
        unconfirmed = [x for x in [attack.get("url"), *(attack.get("phones") or [])] if x]
        public = {"domain": attack.get("domain"), "url": attack.get("url"), "phones": attack.get("phones"),
                  "domain_age_hours": attack.get("domain_age_hours"), "lookalike_score": attack.get("lookalike_score"),
                  "contact_channel": (state.get("extracted") or {}).get("contacted_by"),
                  "unconfirmed": {"values": unconfirmed, "source": "the customer's complaint, not checked by the bank"}}
        # the scammer's number is public, but the guard can't tell it from a customer's: the model sees a label
        masked, vault = c.rt.privacy.pseudonymize(_json(public), c.case_id)
        draft, info = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["recuperare"], system=P.DNSC_SYSTEM,
            user=wrap_data("attack_indicators", masked), schema=P.DnscDraft, effort="low",
            max_tokens=1500, fallback=lambda: _fallback_dnsc(attack), scope=replay_scope(state))
        restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731
        recovery["dnsc_report"] = {"title": restore(draft.title), "text": restore(draft.body),
                                   "indicators": [restore(x) for x in draft.indicators],
                                   "unconfirmed": unconfirmed,
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

REFUND_VERDICTS = ("RAMBURSEAZA", "RAMBURSEAZA_CU_APROBARE")
# the decisions that go against the customer: their letter says how to contest them (GDPR art. 22(3))
ADVERSE_VERDICTS = ("RESPINGE_TARDIV", "NU_SE_APLICA_T1")


def letter_language(state: dict) -> str:
    """"ro" when the customer wrote in Romanian, "en" otherwise, as the intake step read the complaint."""
    language = (state.get("extracted") or {}).get("language")
    if language in ("ro", "en"):
        return language
    text = (state.get("complaint") or {}).get("text")
    return guess_language(text) if text else "en"


def _formats(lang: str) -> tuple[Callable[..., str], Callable[[Any], str], Callable[[Any], str]]:
    """(money, date, date and time) in the letter's language."""
    return (money_ro, fmt_date_ro, fmt_datetime_ro) if lang == "ro" else (money, fmt_date, fmt_datetime)


def _join(items: list[str], lang: str) -> str:
    if lang != "ro" or len(items) <= 1:
        return join_and(items)
    return ", ".join(items[:-1]) + " și " + items[-1]


PAYMENT_KINDS_RO = {"card": "plata cu cardul", "transfer": "transferul", "transfer_instant": "transferul instant"}
# "efectuată" for a payment, "efectuat" for a transfer
PAYMENT_MADE_RO = {"transfer": "efectuat", "transfer_instant": "efectuat"}
# the same, after "of": "Rambursarea plății cu cardul", "Rambursarea transferului"
PAYMENT_KINDS_RO_OF = {"card": "plății cu cardul", "transfer": "transferului", "transfer_instant": "transferului instant"}

# The fallback letter's fixed sentences, by language. The Romanian ones are written for a Romanian reader, not
# translated word for word: the formal "dumneavoastră", the words Romanian banks use, diacritics with a comma below.
LETTER_WORDS: dict[str, dict[str, str]] = {
    "en": {
        "to": " to {merchant}",
        "subject.refund": "Refund of {amount} for {a_kind}{to}",
        "subject.claim": "Your claim about the {amount} {kind}",
        "subject.late": "Your claim about the {amount} {kind} of {paid}",
        "subject.info": "Your claim{about}: we need a few details",
        "about": " about the payment of {amount}",
        "refund.kept": ("We have refunded {refunded} to your account. Under Article 179 of Law 209/2019, the first "
                        "{kept} of the loss stays with you."),
        "refund.done": "We have refunded the full amount of {amount} to your account.",
        "refund.by": "We will refund the full amount of {amount} to your account by {by}.",
        "refund.soon": "We will refund the full amount of {amount} to your account.",
        "told.same_day": "On {told} you told us that you did not make the {kind}{to} that left your account earlier "
                         "that day.",
        "told.on": "On {told} you told us that you did not make the {kind}{to} on {paid}.",
        "told": "You told us that you did not make the {kind}{to}.",
        "thanks.quick": "Thank you for telling us so quickly.",
        "thanks": "Thank you for telling us about it.",
        "law.refund": ("Under Article 173 of Law 209/2019, we must refund a payment you did not authorize by the end of "
                       "the next business day after you report it."),
        "route.app": ("We cannot refund the {kind} of {amount}{to} straight away, because our records show that it "
                      "was approved in your banking app."),
        "route.disputa_comerciant": ("We cannot refund the {kind} of {amount}{to} straight away, because you "
                                     "authorized it and your claim is about what the merchant delivered."),
        "route.eroare_procesare": ("We are correcting the {kind} of {amount}{to}, because our records show that the "
                                   "merchant charged it twice."),
        "route": ("We cannot refund the {kind} of {amount}{to} straight away, because our records show that it was "
                  "authorized."),
        "route.told.same_day": "On {told} you told us about this {kind}, which left your account that day.",
        "route.told.on": "On {told} you told us about this {kind}, made on {paid}.",
        "route.told": "You told us about this {kind}.",
        "law.route": ("This means Article 173 of Law 209/2019, which makes us refund a payment you did not authorize by "
                      "the end of the next business day, does not apply to it."),
        "late": "We cannot refund the {kind} of {amount}{to}{made_on}. {told_part}",
        "late.made_on": ", made on {paid}",
        "late.told": "On {told} you told us that you did not make it.",
        "late.told_unknown": "You told us that you did not make it.",
        "law.late": ("Article 169 of Law 209/2019 allows 13 months from the payment date to report a payment you did "
                     "not authorize. You told us after that period."),
        "info": ("We cannot decide on your claim{about} yet, because we could not find this payment in our records "
                 "from the details you gave{unknown}."),
        "info.unknown": ", and we could not match your claim to an account with us",
        "info.after": ("Reply to this email with the date and the amount of the payment and who it went to{unknown}. "
                       "As soon as we find the payment, we will decide on the refund{by}"),
        "info.after.unknown": ", and the phone number or IBAN registered with us",
        "info.after.by": ", and we will send you our full answer by {answer_by}.",
        "hold": "We need more time to finish our review of your claim about the {kind} of {amount}{to}{made_on}.",
        "hold.made_on": ", made on {paid}",
        "hold.after": "We will send you our decision on the refund by {answer_by}. You do not need to send us "
                      "anything else for now.",
        "hold.after.soon": ("We will send you our decision on the refund as soon as it is ready. You do not need to "
                            "send us anything else for now."),
        "data_used": "To decide, we looked at {data}.",
        "references": "The rules we applied: {references}.",
        "after.refund.RECHEMARE": ("We are also asking the bank that received the money to return it. You do not need "
                                   "to do anything for this."),
        "after.refund.CHARGEBACK": ("We are also asking the merchant's bank to return the money through Visa. You do "
                                    "not need to do anything for this."),
        "after.refund": "You do not need to do anything else.",
        "after.route.RECHEMARE": ("We have asked the bank that received the money to return it, and we will write to "
                                  "you with their answer{later}."),
        "after.route.CHARGEBACK": ("We have started a chargeback with the merchant's bank, and we will write to you "
                                   "with the outcome{later}."),
        "after.route": ("We are trying to recover the money from the bank that received it, and we will write to "
                        "you{later}."),
        "later": " by {answer_by}",
        "tip": "Never share the codes we send you by text message, even with someone who says they work for the bank.",
        "tip.app": ("If someone calls saying they work for the bank and asks you to move money or approve a payment, "
                    "hang up and call us on the number on the back of your card."),
        "reviewed": "A member of our disputes team reviewed and approved this decision.",
        "rights": ("You can ask us for a copy of the information and documents we used for this decision by replying "
                   "to this email."),
        "rights.contest": ("You can ask us for a copy of the information and documents we used, give us your point of "
                           "view or ask for the decision to be reviewed again, by replying to this email."),
    },
    "ro": {
        "to": " către {merchant}",
        "subject.refund": "Rambursarea {kind_of} de {amount}{to}",
        "subject.claim": "Reclamația dumneavoastră privind {kind} de {amount}",
        "subject.late": "Reclamația dumneavoastră privind {kind} de {amount} din {paid}",
        "subject.info": "Reclamația dumneavoastră{about}: avem nevoie de câteva detalii",
        "about": " privind plata de {amount}",
        "refund.kept": ("V-am rambursat suma de {refunded} în contul dumneavoastră. Conform art. 179 din Legea nr. "
                        "209/2019, primii {kept} din pierdere rămân în sarcina dumneavoastră."),
        "refund.done": "V-am rambursat integral suma de {amount} în contul dumneavoastră.",
        "refund.by": "Vă vom rambursa integral suma de {amount} în contul dumneavoastră până la {by}.",
        "refund.soon": "Vă vom rambursa integral suma de {amount} în contul dumneavoastră.",
        "told.same_day": "Pe {told} ne-ați informat că nu ați autorizat {kind}{to} din aceeași zi.",
        "told.on": "Pe {told} ne-ați informat că nu ați autorizat {kind}{to} din {paid}.",
        "told": "Ne-ați informat că nu ați autorizat {kind}{to}.",
        "thanks.quick": "Vă mulțumim că ne-ați anunțat atât de repede.",
        "thanks": "Vă mulțumim că ne-ați anunțat.",
        "law.refund": ("Conform art. 173 din Legea nr. 209/2019, suntem obligați să rambursăm o plată pe care nu ați "
                       "autorizat-o cel târziu până la sfârșitul următoarei zile lucrătoare după ce ne-ați semnalat-o."),
        "route.app": ("Nu vă putem rambursa imediat {kind} în valoare de {amount}{to}, deoarece înregistrările "
                      "noastre arată că plata a fost aprobată în aplicația dumneavoastră de banking."),
        "route.disputa_comerciant": ("Nu vă putem rambursa imediat {kind} în valoare de {amount}{to}, deoarece plata "
                                     "a fost autorizată de dumneavoastră, iar reclamația privește produsul sau "
                                     "serviciul comerciantului."),
        "route.eroare_procesare": ("Corectăm {kind} în valoare de {amount}{to}, deoarece înregistrările noastre arată "
                                   "că comerciantul a încasat aceeași sumă de două ori."),
        "route": ("Nu vă putem rambursa imediat {kind} în valoare de {amount}{to}, deoarece înregistrările noastre "
                  "arată că plata a fost autorizată."),
        "route.told.same_day": "Pe {told} ne-ați informat despre această plată, efectuată în aceeași zi.",
        "route.told.on": "Pe {told} ne-ați informat despre această plată, efectuată pe {paid}.",
        "route.told": "Ne-ați informat despre această plată.",
        "law.route": ("Prin urmare, art. 173 din Legea nr. 209/2019, care ne obligă să rambursăm o plată neautorizată "
                      "până la sfârșitul următoarei zile lucrătoare, nu se aplică în acest caz."),
        "late": "Nu vă putem rambursa {kind} în valoare de {amount}{to}{made_on}. {told_part}",
        "late.made_on": ", {made} pe {paid}",
        "late.told": "Pe {told} ne-ați informat că nu ați autorizat această plată.",
        "late.told_unknown": "Ne-ați informat că nu ați autorizat această plată.",
        "law.late": ("Art. 169 din Legea nr. 209/2019 permite semnalarea unei plăți neautorizate în cel mult 13 luni "
                     "de la data plății. Ne-ați semnalat plata după expirarea acestui termen."),
        "info": ("Nu putem lua încă o decizie cu privire la reclamația dumneavoastră{about}, deoarece nu am găsit această "
                 "plată în evidențele noastre pe baza detaliilor primite{unknown}."),
        "info.unknown": " și nu am putut asocia reclamația unui cont deschis la noi",
        "info.after": ("Răspundeți la acest e-mail cu data și suma plății, precum și cu numele celui care a primit "
                       "banii{unknown}. Imediat ce găsim plata, vom decide asupra rambursării{by}"),
        "info.after.unknown": ", împreună cu numărul de telefon sau IBAN-ul înregistrat la noi",
        "info.after.by": " și vă vom trimite răspunsul complet până la {answer_by}.",
        "hold": ("Avem nevoie de mai mult timp pentru a finaliza analiza reclamației dumneavoastră privind {kind} în "
                 "valoare de {amount}{to}{made_on}."),
        "hold.made_on": ", {made} pe {paid}",
        "hold.after": ("Vă vom comunica decizia privind rambursarea până la {answer_by}. Deocamdată nu trebuie să ne "
                       "trimiteți nimic altceva."),
        "hold.after.soon": ("Vă vom comunica decizia privind rambursarea imediat ce este gata. Deocamdată nu trebuie să "
                            "ne trimiteți nimic altceva."),
        "data_used": "Pentru a lua această decizie, am analizat {data}.",
        "references": "Prevederile legale aplicate: {references}.",
        "after.refund.RECHEMARE": ("Am cerut și băncii care a primit banii să îi returneze. Nu trebuie să faceți nimic "
                                   "în acest sens."),
        "after.refund.CHARGEBACK": ("Am cerut și băncii comerciantului să returneze banii, prin procedura de "
                                    "chargeback Visa. Nu trebuie să faceți nimic în acest sens."),
        "after.refund": "Nu mai trebuie să faceți nimic altceva.",
        "after.route.RECHEMARE": ("Am cerut băncii care a primit banii să îi returneze și vă vom comunica răspunsul "
                                  "acesteia{later}."),
        "after.route.CHARGEBACK": ("Am inițiat procedura de chargeback la banca comerciantului și vă vom comunica "
                                   "rezultatul{later}."),
        "after.route": "Încercăm să recuperăm banii de la banca ce i-a primit și vă vom scrie{later}.",
        "later": " până la {answer_by}",
        "tip": ("Nu comunicați nimănui codurile pe care vi le trimitem prin SMS, nici măcar cuiva care se prezintă "
                "drept angajat al băncii."),
        "tip.app": ("Dacă vă sună cineva care se prezintă drept angajat al băncii și vă cere să mutați bani sau să "
                    "aprobați o plată, închideți și sunați-ne la numărul de pe spatele cardului."),
        "reviewed": "Un coleg din echipa de contestații a verificat și a aprobat această decizie.",
        "rights": ("Ne puteți cere o copie a informațiilor și a documentelor pe care le-am folosit pentru această "
                   "decizie, răspunzând la acest e-mail."),
        "rights.contest": ("Ne puteți cere o copie a informațiilor și a documentelor folosite, ne puteți transmite "
                           "punctul dumneavoastră de vedere sau puteți cere reanalizarea deciziei, răspunzând la acest "
                           "e-mail."),
    },
}
# the data a decision rests on (GDPR art. 15(1)(h) and CJEU C-203/22): categories, never values or scores
DATA_WORDS = {
    "en": {"complaint": "your complaint", "payment": "the record of the payment",
           "authentication": "the authentication record", "device": "the device used for the payment",
           "reported": "the date you reported it"},
    "ro": {"complaint": "reclamația dumneavoastră", "payment": "datele tranzacției",
           "authentication": "jurnalul de autentificare", "device": "dispozitivul folosit pentru plată",
           "reported": "data la care ne-ați anunțat"},
}
# the main factor behind each decision, in plain words: what the rules weighed, with no threshold or score
FACTOR_WORDS = {
    "en": {"refund": ("The main factors were that you told us you did not authorize the payment and that you reported "
                      "it within the 13 months the law allows."),
           "late": "The main factor was the time between the payment and your report, which is longer than 13 months.",
           "app": "The main factor was that the payment was confirmed in your banking app.",
           "app.screen": ("The main factors were that the payment was confirmed in your banking app and that the "
                          "screen showed the amount and the payee."),
           "disputa_comerciant": "The main factor was that you authorized the card payment yourself.",
           "eroare_procesare": "The main factor was that the merchant charged the same payment twice.",
           "route": "The main factor was that the payment was authorized."},
    "ro": {"refund": ("Am ținut cont, în principal, de faptul că ați declarat că nu ați autorizat plata și că ați "
                      "semnalat-o în termenul de 13 luni prevăzut de lege."),
           "late": "Decizia se bazează pe intervalul dintre data plății și data sesizării, care depășește 13 luni.",
           "app": "Am ținut cont, în principal, de faptul că plata a fost confirmată în aplicația de banking.",
           "app.screen": ("Am ținut cont, în principal, de faptul că plata a fost confirmată în aplicația de banking, "
                          "iar pe ecran au apărut suma și beneficiarul."),
           "disputa_comerciant": "Am ținut cont, în principal, de faptul că ați autorizat dumneavoastră plata cu cardul.",
           "eroare_procesare": ("Am ținut cont, în principal, de faptul că comerciantul a încasat aceeași plată de două "
                                "ori."),
           "route": "Am ținut cont, în principal, de faptul că plata a fost autorizată."},
}
# the one thing the customer can do or show that would change an unfavorable outcome (no internal thresholds)
COUNTERFACTUAL_WORDS = {
    "en": {"late": ("If you have documents showing that you told us about this payment earlier, within the 13 months, "
                    "send them to us and we will look at your claim again."),
           "app": ("If you did not approve the payment in the app yourself, tell us in your reply and we will look at "
                   "your claim again."),
           "disputa_comerciant": ("If the merchant does not solve the problem, send us the order confirmation and your "
                                  "messages with the merchant, and we will check whether the money can come back "
                                  "through Visa."),
           "eroare_procesare": ("If you still see both charges on your statement after the correction, tell us and we "
                                "will look at it again.")},
    "ro": {"late": ("Dacă aveți documente care arată că ne-ați semnalat plata mai devreme, în termenul de 13 luni, "
                    "trimiteți-ni-le și vom analiza din nou reclamația."),
           "app": ("Dacă nu ați aprobat dumneavoastră plata în aplicație, spuneți-ne în răspunsul la acest e-mail și "
                   "vom analiza din nou reclamația."),
           "disputa_comerciant": ("Dacă problema nu se rezolvă cu comerciantul, trimiteți-ne confirmarea comenzii și "
                                  "mesajele schimbate cu acesta, iar noi vom verifica dacă banii pot fi recuperați "
                                  "prin Visa."),
           "eroare_procesare": ("Dacă după corectare vedeți în continuare ambele plăți în extras, spuneți-ne și vom "
                                "analiza din nou situația.")},
}
# the fallback letter's answer to a point of the complaint, by the point's topic (versoml.shared.rules.packs.cmp):
# in the bank's own words, never the customer's quoted back
POINT_ANSWERS = {
    "en": {"why_not_stopped": ("You asked why we did not stop the payment. It went through the usual authentication "
                               "steps, so it was processed like any other payment."),
           "still_refund": " The law still requires us to refund you.",
           "own_card": (f"You asked us to block your card. If it is not blocked yet, call us on {HELPLINE} and we will "
                        "block it straight away."),
           "payee": ("You asked us to act on the account that received the money. We cannot share information about "
                     "other people's accounts, but we have taken what you told us into account."),
           "documents": ("You can ask us for a copy of the information we hold about this payment by replying to this "
                         "email."),
           "police": "You can also report the fraud to the police. Keep the messages and receipts linked to this payment.",
           "other": "We have read the other details in your message and taken them into account in our review."},
    "ro": {"why_not_stopped": ("Ne-ați întrebat de ce nu am oprit plata. Plata a trecut prin pașii obișnuiți de "
                               "autentificare, așa că a fost procesată ca orice altă plată."),
           "still_refund": " Legea ne obligă totuși să vă rambursăm suma.",
           "own_card": (f"Ne-ați cerut să vă blocăm cardul. Dacă nu este încă blocat, sunați-ne la {HELPLINE} și îl "
                        "blocăm imediat."),
           "payee": ("Ne-ați cerut să luăm măsuri privind contul care a primit banii. Nu putem oferi informații despre "
                     "conturile altor persoane, dar am ținut cont de ce ne-ați spus."),
           "documents": ("Ne puteți cere o copie a informațiilor pe care le deținem despre această plată, răspunzând la "
                         "acest e-mail."),
           "police": "Puteți sesiza și Poliția. Păstrați mesajele și chitanțele legate de această plată.",
           "other": "Am citit și celelalte detalii din mesajul dumneavoastră și am ținut cont de ele în analiza noastră."},
}
_RO_REFERENCE = ((r"\bLaw (\d+/\d{4})", r"Legea nr. \1"), (r"\bGEO (\d+/\d{4})", r"OUG nr. \1"),
                 (r"\bCJEU ruling (C-\d+/\d+)", r"hotărârea CJUE în cauza \1"), (r"\bGDPR\b", "RGPD"),
                 (r"\bpara\.", "alin."), (r"\bletter\b", "lit."), (r"\band\b", "și"))


def ro_reference(ref: str) -> str:
    """"Law 209/2019, art. 173" -> "Legea nr. 209/2019, art. 173"."""
    for pattern, repl in _RO_REFERENCE:
        ref = re.sub(pattern, repl, ref)
    return ref


def _payment_words(state: dict, lang: str = "en") -> tuple[str, str, str]:
    """("card payment", " to SHOP SRL", the kind after "of") for the letter; a transfer's payee is not named."""
    ctx = state["rule_context"]
    tx = (state.get("records") or {}).get("transaction") or {}
    channel = str(ctx.get("channel") or "")
    merchant = g(tx, "merchant_name", "counterparty_name") if ctx.get("channel") == "card" else None
    to_whom = LETTER_WORDS[lang]["to"].format(merchant=merchant) if merchant else ""
    if lang == "ro":
        return PAYMENT_KINDS_RO.get(channel, "plata"), to_whom, PAYMENT_KINDS_RO_OF.get(channel, "plății")
    kind = PAYMENT_KINDS.get(channel, "payment")
    return kind, to_whom, kind


def _data_used(state: dict, lang: str) -> list[str]:
    """The kinds of data the decision rests on, as the customer would name them."""
    ctx = state.get("rule_context") or {}
    words = DATA_WORDS[lang]
    used = [words["complaint"]]
    if not declared_only(state):
        used.append(words["payment"])
    if ctx.get("sca_performed") is not None or ctx.get("screen_showed_amount_and_payee") is not None:
        used.append(words["authentication"])
    if ctx.get("device_known") is not None:
        used.append(words["device"])
    if ctx.get("notified_at"):
        used.append(words["reported"])
    return used


def _main_factor(state: dict, verdict: str | None, lang: str) -> str | None:
    ctx = state.get("rule_context") or {}
    words = FACTOR_WORDS[lang]
    if verdict in REFUND_VERDICTS:
        return words["refund"]
    if verdict == Verdict.RESPINGE_TARDIV.value:
        return words["late"]
    if verdict == Verdict.NU_SE_APLICA_T1.value:
        kind = str(ctx.get("dispute_type") or "")
        if kind == "app":
            return words["app.screen" if ctx.get("screen_showed_amount_and_payee") is True else "app"]
        return words.get(kind, words["route"])
    return None


def _counterfactual(state: dict, verdict: str | None, lang: str) -> str | None:
    words = COUNTERFACTUAL_WORDS[lang]
    if verdict == Verdict.RESPINGE_TARDIV.value:
        return words["late"]
    if verdict == Verdict.NU_SE_APLICA_T1.value:
        return words.get(str((state.get("rule_context") or {}).get("dispute_type") or ""))
    return None


def _explanation(state: dict, lang: str, reviewed_by: str | None) -> dict | None:
    """What the letter says about how the decision was made (CJEU C-203/22, Dun & Bradstreet): the data used, the
    main factors, what would change an unfavorable outcome, whether a person reviewed it and the customer's rights.
    None for a fraud hold: that letter gives no reason (tipping-off)."""
    verdict = (_decision(state, Question.RAMBURSARE_T1) or {}).get("decision")
    if verdict == Verdict.EXCEPTIE_FRAUDA_CLIENT.value:
        return None
    if verdict == Verdict.INFORMATII_SUPLIMENTARE.value:
        return {"data_used": [DATA_WORDS[lang]["complaint"]], "main_factors": [], "counterfactual": None,
                "reviewed_by_person": False, "documents": False, "contest": False}
    kept = bool((state.get("refund") or {}).get("retained"))
    factor = _main_factor(state, verdict, lang)
    return {"data_used": _data_used(state, lang), "main_factors": [factor] if factor else [],
            "counterfactual": _counterfactual(state, verdict, lang), "reviewed_by_person": bool(reviewed_by),
            "documents": True, "contest": verdict in ADVERSE_VERDICTS or kept}


def _point_answer(point: str, quote: str, case: dict, lang: str) -> str | None:
    """The fallback letter's answer to one point of the complaint, or None when the letter already answers it. The
    answer is chosen by the point's topic (the same topics the CMP-01 check reads), so the customer's words are
    never quoted back to them."""
    from versoml.shared.rules.packs.cmp import point_topic

    topic = point_topic(point) or (point_topic(quote) if quote else None)
    words = POINT_ANSWERS[lang]
    verdict = case.get("verdict")
    if topic == "why_not_stopped":
        return words["why_not_stopped"] + (words["still_refund"] if verdict in REFUND_VERDICTS else "")
    if topic in ("own_card", "police"):
        return words[topic]
    if topic == "payee":
        return None if case.get("escroc") in ("RECHEMARE", "CHARGEBACK") else words["payee"]
    if topic == "documents":
        return None if (case.get("explanation") or {}).get("documents") else words["documents"]
    if topic == "refund" or (topic == "duplicate" and case.get("dispute_type") == "eroare_procesare"):
        return None   # the opening paragraph is the answer
    return words["other"]


def _fallback_letter(state: dict, references: list[str] | None = None, *,
                     reviewed_by: str | None = None) -> P.LetterOut:
    """The letter without an LLM, in the customer's language and in the shape the letter prompt asks for: the decision
    first, then why (the law, the data used and the main factor), answers to the customer's points in the bank's own
    words, the next step with what would change an unfavorable outcome, the customer's rights and where to complain.
    `references` are plain legal references from the knowledge base (none means no extra line); `reviewed_by` is the
    person who signed the decision, when one did."""
    lang = letter_language(state)
    words = LETTER_WORDS[lang]
    cash, day, moment = _formats(lang)
    ctx = state["rule_context"]
    t1 = _decision(state, Question.RAMBURSARE_T1) or {}
    ans = _decision(state, Question.RASPUNS_RECLAMATIE) or {}
    escroc = (_decision(state, Question.RECUPERARE_ESCROC) or {}).get("decision")
    value = ctx.get("amount") or {}
    amount = cash(float(value.get("value", 0)), value.get("currency") or "RON")
    fm = ctx.get("fact_ids") or {}
    verdict = t1.get("decision")
    dispute_type = str(ctx.get("dispute_type") or "")
    kind, to_whom, kind_of = _payment_words(state, lang)
    paid, told = to_local(ctx.get("executed_at")), to_local(ctx.get("notified_at"))
    paid_on, told_on = day(paid), day(told)
    same_day = bool(paid_on) and paid_on == told_on
    by, answer_by = moment(t1.get("deadline")), day(ans.get("deadline"))
    back = state.get("refund") or {}
    refunded = bool(back.get("done"))
    # the bank kept the customer's share under art. 179(1): the letter says how much went back
    kept = cash(float(back["payer_liability"]), back.get("currency") or "RON") if back.get("retained") else None
    quick = bool(paid and told and (told - paid) <= timedelta(days=2))
    explanation = _explanation(state, lang, reviewed_by)
    made = PAYMENT_MADE_RO.get(str(ctx.get("channel") or ""), "efectuată")
    fill = {"amount": amount, "kind": kind, "kind_of": kind_of, "to": to_whom, "paid": paid_on, "told": told_on,
            "by": by, "answer_by": answer_by, "made": made,
            "a_kind": ("an " if kind[:1] in "aeiou" else "a ") + kind}
    tip = words["tip.app"] if dispute_type == "app" else words["tip"]
    law = ""
    if verdict in REFUND_VERDICTS:
        refund_value = cash(float(back["amount"]), back.get("currency") or "RON") if refunded and kept else amount
        subject = words["subject.refund"].format(**{**fill, "amount": refund_value if lang == "en" else amount})
        decision = words["refund.kept" if refunded and kept else "refund.done" if refunded else
                         "refund.by" if by else "refund.soon"]
        what = words["told.same_day" if same_day else "told.on" if paid_on and told_on else "told"]
        opening = " ".join([decision.format(**fill, refunded=refund_value, kept=kept), what.format(**fill),
                            words["thanks.quick"] if quick else words["thanks"]])
        law = words["law.refund"]
        after = words.get(f"after.refund.{escroc}", words["after.refund"])
    elif verdict == Verdict.NU_SE_APLICA_T1.value:
        subject = words["subject.claim"].format(**fill)
        route = words.get(f"route.{dispute_type}", words["route"])
        what = words["route.told.same_day" if same_day else "route.told.on" if paid_on and told_on else "route.told"]
        opening = f"{route.format(**fill)} {what.format(**fill)}"
        law = words["law.route"]
        later = words["later"].format(answer_by=answer_by) if answer_by else ""
        after = words.get(f"after.route.{escroc}", words["after.route"]).format(later=later)
    elif verdict == Verdict.RESPINGE_TARDIV.value:
        subject = words["subject.late" if paid_on else "subject.claim"].format(**fill)
        told_part = words["late.told" if told_on else "late.told_unknown"].format(**fill)
        made_on = words["late.made_on"].format(**fill) if paid_on else ""
        opening = words["late"].format(**{**fill, "made_on": made_on, "told_part": told_part})
        law = words["law.late"]
        after = ""
    elif verdict == Verdict.INFORMATII_SUPLIMENTARE.value:
        # declared facts only: the payment (or the customer) was not found from the details in the complaint
        stated = (state.get("declared") or {}).get("amount") or {}
        about = (words["about"].format(amount=cash(float(stated["value"]), stated.get("currency") or "RON"))
                 if stated.get("value") else "")
        known = bool((state.get("match") or {}).get("customer_ref") or (state.get("complaint") or {}).get("customer_ref"))
        subject = words["subject.info"].format(about=about)
        opening = words["info"].format(about=about, unknown="" if known else words["info.unknown"])
        after = words["info.after"].format(
            unknown="" if known else words["info.after.unknown"],
            by=words["info.after.by"].format(answer_by=answer_by) if answer_by else ".")
    else:
        subject = words["subject.claim"].format(**fill)
        made_on = words["hold.made_on"].format(**fill) if paid_on else ""
        opening = words["hold"].format(**{**fill, "made_on": made_on})
        after = words["hold.after"].format(answer_by=answer_by) if answer_by else words["hold.after.soon"]
    rules_cite = [x for x in [fm.get("rules_outcome")] if x]
    paragraphs = [
        P.LetterParagraph(text=P.GREETING[lang], cites=[]),
        P.LetterParagraph(text=opening, cites=[x for x in [fm.get("amount"), fm.get("notified_at")] if x]),
    ]
    if law and explanation:
        why = [law, words["data_used"].format(data=_join(explanation["data_used"], lang)),
               *explanation["main_factors"]]
        paragraphs.append(P.LetterParagraph(text=" ".join(why), cites=rules_cite))
    if references and explanation:
        listed = "; ".join(ro_reference(r) for r in references) if lang == "ro" else "; ".join(references)
        paragraphs.append(P.LetterParagraph(text=words["references"].format(references=listed), cites=rules_cite))
    points, answers = [], []
    case = {"verdict": verdict, "escroc": escroc, "dispute_type": dispute_type, "explanation": explanation}
    for point in (state.get("extracted") or {}).get("points", [])[:4]:
        answer = _point_answer(point["text"], point.get("quote") or "", case, lang)
        if answer and answer not in answers:
            answers.append(answer)
            paragraphs.append(P.LetterParagraph(text=answer, cites=[]))
        points.append(point["text"])
    counterfactual = (explanation or {}).get("counterfactual")
    paragraphs.append(P.LetterParagraph(text=" ".join(x for x in (after, counterfactual, tip) if x), cites=[]))
    if explanation and explanation["documents"]:
        rights = words["rights.contest"] if explanation["contest"] else words["rights"]
        paragraphs.append(P.LetterParagraph(
            text=f"{words['reviewed']} {rights}" if explanation["reviewed_by_person"] else rights, cites=[]))
    case_id = state.get("case_id") or ctx.get("case_id")
    paragraphs.append(P.LetterParagraph(text=f"{P.ADR[lang]} {P.contact_line(case_id, lang)}", cites=[]))
    paragraphs.append(P.LetterParagraph(text=P.SIGN_OFF[lang], cites=[]))
    return P.LetterOut(subject=subject, paragraphs=paragraphs, points_answered=points)


VERDICT_MEANINGS = {
    "RAMBURSEAZA": "refund the full amount by the deadline",
    "RAMBURSEAZA_CU_APROBARE": "refund the full amount by the deadline, once a bank employee approves it",
    "EXCEPTIE_FRAUDA_CLIENT": "no refund for now: tell the customer the review needs more time and give the answer date",
    "RESPINGE_TARDIV": "no refund: the customer reported the payment more than 13 months after it was made",
    "NU_SE_APLICA_T1": "the next-business-day refund rule does not apply: the bank tries to recover the money instead",
    "CHARGEBACK": "the bank asks the merchant's bank to return the money (chargeback)",
    "RECHEMARE": "the bank asks the bank that received the transfer to return it (recall)",
    "INFORMATII_SUPLIMENTARE": "the bank needs more information from the customer: when missing_details is in the "
                               "data, the bank could not find the payment and asks the customer for those details",
    "INCHIDE": "the claim is closed",
}


def _local_iso(value: Any) -> str | None:
    """Bucharest time as ISO (the LLM client strips ISO timestamps from replay keys, so recordings still match)."""
    dt = to_local(value)
    return dt.isoformat(timespec="seconds") if dt else None


def _letter_brief(state: dict, c: Ctx, lang: str = "en", reviewed_by: str | None = None) -> dict:
    ctx = state["rule_context"]
    value = ctx.get("amount") or {}
    cash = _formats(lang)[0]
    kind, to_whom, _ = _payment_words(state, lang)
    tx = (state.get("records") or {}).get("transaction") or {}
    merchant = g(tx, "merchant_name", "counterparty_name") if to_whom else None
    decisions = [d for d in state.get("decisions", []) if d.get("question") in
                 ("rambursare_t1", "raspuns_reclamatie", "recuperare_escroc")]
    out = {
        "case_id": c.case_id,
        "language": "Romanian" if lang == "ro" else "English",
        "payment": {"amount": cash(float(value.get("value", 0)), value.get("currency") or "RON"), "type": kind,
                    "merchant": merchant, "made_at": _local_iso(ctx.get("executed_at")),
                    "reported_at": _local_iso(ctx.get("notified_at"))},
        "refund_sent": bool((state.get("refund") or {}).get("done")),
        "decisions": [{"question": d["question"], "decision": d["decision"],
                       "meaning": VERDICT_MEANINGS.get(d["decision"], label(VERDICT_LABELS, d["decision"])),
                       "deadline": _local_iso(d.get("deadline")),
                       "reasons": [r.get("text") for r in d.get("rationale", [])][:3]} for d in decisions],
        "points": [p["text"] for p in (state.get("extracted") or {}).get("points", [])],
        "evidence_ids": sorted({v for v in (ctx.get("fact_ids") or {}).values()})[:20],
    }
    explanation = _explanation(state, lang, reviewed_by)
    if explanation:
        out["explanation"] = explanation
    back = state.get("refund") or {}
    if back.get("retained"):
        # the bank kept the customer's share under art. 179(1): the letter says what went back
        currency = back.get("currency") or "RON"
        out["refund"] = {"amount": cash(float(back["amount"]), currency), "basis": "Law 209/2019, art. 179(1)",
                         "customer_share_kept": cash(float(back["payer_liability"]), currency)}
    if declared_only(state):
        # the customer's statement, not the bank's records: no amount when they gave none
        if not float(value.get("value") or 0):
            out["payment"]["amount"] = None
        out["payment"]["source"] = "the customer's statement (the payment is not identified in our records)"
        t1 = _decision(state, Question.RAMBURSARE_T1) or {}
        out["missing_details"] = list(t1.get("missing_evidence") or [])
    return out


def _customer_name(c: Ctx, state: dict) -> str | None:
    """The name for the greeting, from the bank's record (the complaint may not mention it)."""
    try:
        ref = _customer_ref(state)
        customer = (c.rt.repo.get_customer(ref) if ref else None) or {}
    except Exception:  # noqa: BLE001 - without the record the letter says "Dear customer,"
        return None
    name = " ".join(str(customer[k]) for k in ("first_name", "last_name") if customer.get(k))
    return name or None


def _greet(body: str, name: str | None, lang: str) -> str:
    """The customer's name in place of the label; without one, "Dear customer," or a plain "Bună ziua,"."""
    if name:
        return re.sub(r"<CLIENT_\d+>", name, body)
    if lang == "ro":
        return re.sub(r"<CLIENT_\d+>", "client", re.sub(r",\s*<CLIENT_\d+>", "", body))
    return re.sub(r"<CLIENT_\d+>", "customer", body)


RULE_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d{2}\b|·")


def _legal_references(state: dict) -> tuple[list[str], list[dict]]:
    """Plain legal references for the letter, from the knowledge base, for the rules behind the letter's decisions.
    None for a fraud hold: that letter gives no reason (tipping-off)."""
    from versoml.zone_client import grounding as G

    t1 = _decision(state, Question.RAMBURSARE_T1) or {}
    if t1.get("decision") == Verdict.EXCEPTIE_FRAUDA_CLIENT.value:
        return [], []
    ids: list[str] = []
    for q in (Question.RAMBURSARE_T1, Question.RASPUNS_RECLAMATIE, Question.RECUPERARE_ESCROC):
        ids += (_decision(state, q) or {}).get("rule_ids") or []
    refs: list[str] = []
    used: list[dict] = []
    for hit in G.for_rules(ids, k_per=1):
        if hit.get("kind") not in ("rule", "law"):
            continue
        # a rule's title can stand in for a missing legal basis, and it starts with the rule ID: the letter names laws
        fresh = [r for r in G.plain_reference_parts(hit) if not RULE_ID_RE.search(r)
                 and not any(r.startswith(x) or x.startswith(r) for x in refs)]
        if fresh:
            refs.extend(fresh)
            used.append(hit)
        if len(refs) >= 3:
            break
    refs = refs[:3]
    return refs, used


def _letter_rule_ids(state: dict) -> list[str]:
    """The rules behind the letter's decisions: they go in the letter's metadata, never in its text."""
    ids: list[str] = []
    for q in (Question.RAMBURSARE_T1, Question.RASPUNS_RECLAMATIE, Question.RECUPERARE_ESCROC):
        ids += [r for r in (_decision(state, q) or {}).get("rule_ids") or [] if r not in ids]
    return ids


def _numbers_allowed(c: "Ctx", state: dict):
    """The values the letter may state: the ledger facts and the rules engine's fact sheet (its decisions and
    context), plus the customer's own statement on the declared-facts path."""
    from versoml.zone_client import numeric_check as N

    kinds = ("declared.statement",) if declared_only(state) else ()
    allowed = N.allowed_from_facts(c.rt.ledger.facts(c.case_id), c.case_id, include_untrusted_kinds=kinds)
    ctx = state.get("rule_context") or {}
    currency = (ctx.get("amount") or {}).get("currency") or "RON"
    allowed.add_content({k: ctx.get(k) for k in ("amount", "executed_at", "notified_at", "complaint_received_at")},
                        currency)
    for d in state.get("decisions") or []:
        allowed.add_content({"deadline": d.get("deadline"), "amount": d.get("amount")}, currency)
    back = state.get("refund") or {}
    if back.get("done") and back.get("amount") is not None:
        allowed.add_content({k: back.get(k) for k in ("amount", "debited", "payer_liability", "currency")},
                            back.get("currency") or currency, kind="refund.instruction")
    return allowed


def _cmp_rows(hits: list) -> list[dict]:
    """The CMP checks of the letter that goes out (the last draft, after any rewrite)."""
    return [{"rule_id": h.rule_id, "outcome": h.outcome, "explanation": h.explanation} for h in hits]


async def redactor(state: dict) -> dict:
    c = Ctx(state)
    if (state.get("refund") or {}).get("status") == "REFUZAT":
        # a letter now would promise a refund nobody approved: the person handling the case writes to the customer
        await c.start("redactor", "No reply drafted: the refund was declined")
        await c.finish("redactor", "No letter: the refund was declined, so the person handling the case writes "
                                   "to the customer", status="skipped")
        c.track("filtru_zid", "skipped", "No letter to check")
        return {}
    lang = letter_language(state)
    await c.start("redactor", "Drafting the reply in " + ("Romanian" if lang == "ro" else "English")
                  + ": the decision and why, every point answered, deadlines and where to complain")
    from versoml.shared.rules import check_complaint_letter
    from versoml.wall.letter_filter import check_letter
    from versoml.zone_client import numeric_check as N

    doc = c.rt.cases.get(c.case_id) or {}
    reviewed_by = doc.get("approved_by") or doc.get("rejected_by")
    references, reference_hits = _legal_references(state)
    data = _letter_brief(state, c, lang, reviewed_by)
    if references:
        data["legal_basis"] = [ro_reference(r) for r in references] if lang == "ro" else references
    brief = wrap_data("letter_data", _json(data))
    system = P.letter_system(lang)
    fallback = lambda: _fallback_letter(state, references, reviewed_by=reviewed_by)  # noqa: E731
    out, info = await c.rt.llm.structured(
        role=Role.SONNET, agent=AG["redactor"], system=system,
        user=brief, schema=P.LetterOut, effort="low", max_tokens=3000, fallback=fallback, scope=replay_scope(state))
    valid = {f.fact_id for f in c.rt.ledger.facts(c.case_id)}
    claim_points = (state.get("extracted") or {}).get("points", [])
    points = [p["text"] for p in claim_points]
    quotes = [p.get("quote") or "" for p in claim_points]
    adr_block = P.ADR[lang]
    vault = (state.get("pseudo") or {}).get("vault") or {}
    restore = lambda s: c.rt.privacy.restore(s, vault) if s else s  # noqa: E731

    def compose(letter: P.LetterOut) -> tuple[str, list]:
        # the CMP checks from the rules engine, read from the letter itself: every point gets an answer (CMP-01),
        # the complaints block (CMP-03)
        body = "\n\n".join(p.text for p in letter.paragraphs)
        hits = check_complaint_letter(body, points, quotes)
        if any(h.outcome == "CMP_ADR_BLOCK_MISSING" for h in hits):
            body += "\n\n" + adr_block
            hits = check_complaint_letter(body, points, quotes)
        return body, hits

    allowed = _numbers_allowed(c, state)

    def numbers(letter: P.LetterOut) -> dict:
        return N.check(N.sections_of(restore(letter.subject), [restore(p.text) for p in letter.paragraphs]), allowed)

    pseudo_body, cmp_hits = compose(out)
    if "\n\n" + adr_block in pseudo_body and adr_block not in "\n\n".join(p.text for p in out.paragraphs):
        await c.em.custom("rule_hit", "CMP-03: the ANPC / ANAF / BNR / CSALB paragraph was missing, so it was added",
                          {"rule_id": "CMP-03", "outcome": "bloc_adaugat"}, step="redactor", agent=AG["redactor"])
    answered = next((h for h in cmp_hits if h.rule_id == "CMP-01"), None)
    await c.finish("redactor", f"Letter drafted ({info.mode}, {'Romanian' if lang == 'ro' else 'English'}); "
                   + ("every point answered" if answered is None or answered.outcome == "toate_punctele"
                      else "a point still needs an answer: a person adds it"),
                   {"llm": info.as_dict(), "cmp": _cmp_rows(cmp_hits), "language": lang})

    await c.start("filtru_zid", "Checking the letter: every number against the case file, forbidden terms, canary "
                                "tokens, personal data")
    num = numbers(out)
    rewritten = False
    if not num["passed"]:
        # self-correction: one rewrite with the values on file; if that fails too, a person decides
        await c.em.custom("numeric_check", "The numbers check stopped the first draft; the letter writer is redoing it "
                                           "with the values from the case file",
                          {"mismatches": num["mismatches"]}, step="filtru_zid", agent=AG["filtru_zid"])
        retry, _ = await c.rt.llm.structured(
            role=Role.SONNET, agent=AG["redactor"], system=system, user=brief + N.feedback(num["mismatches"]),
            schema=P.LetterOut, effort="low", max_tokens=3000, fallback=fallback, scope=replay_scope(state))
        rewritten = True
        second = numbers(retry)
        out, num = retry, second
        pseudo_body, cmp_hits = compose(out)
    cites = sorted({x for p in out.paragraphs for x in p.cites if x in valid})
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
            role=Role.SONNET, agent=AG["redactor"], system=system,
            user=brief + feedback, schema=P.LetterOut, effort="low",
            max_tokens=3000, fallback=fallback, scope=replay_scope(state))
        candidate, candidate_hits = compose(retry)
        second = check_letter(candidate)
        if second.passed:
            out, pseudo_body, result, cmp_hits = retry, candidate, second, candidate_hits
            cites = sorted({x for p in out.paragraphs for x in p.cites if x in valid})
            num = numbers(out)
    numeric_check = {**num, "rewritten": rewritten}
    body = _greet(restore(pseudo_body), _customer_name(c, state), lang)
    passed = result.passed and num["passed"]
    status = "draft" if passed else "blocked"
    # human_approved: a person signed the decision this letter gives. The letter itself stays a draft until a
    # person sends it (status).
    metadata = {"ai_assisted": True, "human_approved": bool(reviewed_by), "approved_by": reviewed_by,
                "language": lang, "llm_mode": info.mode, "rule_ids": _letter_rule_ids(state),
                "legal_basis": references}
    letter = {"case_id": c.case_id, "subject": restore(out.subject), "body": body, "cites": cites,
              "points_answered": out.points_answered, "filter": result.model_dump(mode="json"), "status": status,
              "cmp_checks": _cmp_rows(cmp_hits), "numeric_check": numeric_check, "language": lang,
              "metadata": metadata}
    if not result.passed:
        c.rt.record_block(c.case_id, result.reasons, result.blocked_terms)
        await c.em.custom("wall_block", "The wall blocked the letter: " + "; ".join(result.reasons[:2]),
                          result.model_dump(mode="json"), step="filtru_zid", agent=AG["filtru_zid"])
    if not num["passed"]:
        c.rt.record_block(c.case_id, ["the numbers in the letter do not match the case file"], [])
        await c.em.custom("numeric_block", "The numbers check blocked the letter: a person checks it",
                          {"mismatches": num["mismatches"]}, step="filtru_zid", agent=AG["filtru_zid"])
    await c.fact("filtru_zid", "letter.numeric_check", "letters.numeric_check", {"checked": num["checked"]},
                 numeric_check,
                 (f"Every number, phone number and link in the letter matches the case file "
                  f"({plural(num['checked'], 'value')} checked)"
                  if num["passed"] else f"{plural(len(num['mismatches']), 'value')} in the letter do not match the case "
                                        "file: sent to a person")
                 + (" after one rewrite" if rewritten else ""))
    await c.fact("filtru_zid", "letter.checked", "letters.check_letter", {"chars": len(body)},
                 {"passed": result.passed, "blocked_terms": result.blocked_terms, "canaries": result.canaries_found,
                  "sha256_letter": hashlib.sha256(body.encode()).hexdigest(), "language": lang,
                  "metadata": metadata},
                 "The letter passed the wall check" if result.passed else "The wall BLOCKED the letter")
    shown = [ro_reference(r) for r in references] if lang == "ro" else references
    used = reference_hits if any(ref in body for ref in shown) else []
    if used:
        await _record_grounding(c, "letter", used, step="redactor")
    c.save({"letter": letter, "numeric_check": numeric_check})
    await c.finish("filtru_zid", "Clean letter: the numbers match the case file, no forbidden terms, no canary tokens"
                   if passed else "Blocked and sent to a person", status="done" if passed else "blocked")
    return {"letter": letter}


# ---------------------------------------------------------------- 11. The ledger seal


async def sigiliu(state: dict) -> dict:
    c = Ctx(state)
    await c.start("sigiliu", "Sealing the case file: an Ed25519-signed Merkle root and a QR code")
    await _add_precedent(c, state)
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


def precedent_text(c: "Ctx", state: dict) -> str:
    """A pseudonymized summary of the case for the precedent index: the situation, the facts that decided it and
    the customer's story (already pseudonymized). No name, IBAN or phone number."""
    ctx = state.get("rule_context") or {}
    value = ctx.get("amount") or {}
    from versoml.zone_client.reasons import scenario_phrase

    parts = [scenario_phrase(ctx.get("scenario"), ctx.get("dispute_type"), state.get("match")) or "Payment dispute",
             f"{label(CHANNEL_LABELS, ctx.get('channel'))}, {label(DISPUTE_LABELS, ctx.get('dispute_type'))}",
             money(float(value.get("value") or 0), value.get("currency") or "RON")]
    signals = [text for key, wanted, text in (("device_known", False, "new device"), ("beneficiary_new", True, "new payee"),
                                              ("screen_showed_amount_and_payee", True, "screen showed amount and payee"))
               if ctx.get(key) is wanted]
    if ctx.get("seconds_after_click") is not None:
        signals.append(f"payment {ctx['seconds_after_click']} s after a link click")
    if ctx.get("sim_swap_hours_before") is not None:
        signals.append("SIM swap before the payment")
    if signals:
        parts.append("; ".join(signals))
    story = ((state.get("pseudo") or {}).get("text") or "")[:800]
    text, _ = c.rt.privacy.pseudonymize(". ".join(parts) + ".\n" + story, c.case_id)
    return text


PRECEDENT_TIMEOUT_S = 10


async def _add_precedent(c: "Ctx", state: dict) -> None:
    """A sealed case becomes a precedent in the client-zone knowledge base (information for later cases only)."""
    from versoml.zone_client import grounding as G

    if not G.available():
        return
    from versoml.zone_client.reasons import decision_reasons

    doc = c.rt.cases.get(c.case_id) or {}
    decisions = {d.get("question"): d.get("decision") for d in state.get("decisions") or []}
    escroc = decisions.get("recuperare_escroc")
    reported, refunded = parse_dt(doc.get("received_at")), parse_dt(doc.get("refunded_at"))
    reasons = decision_reasons(state.get("decisions"), state.get("rule_context") or {}, state.get("extracted"),
                               (state.get("rules") or {}).get("hits"))
    outcome = {"decision": decisions.get("rambursare_t1"), "status": doc.get("status"),
               "refund_days": round((refunded - reported).total_seconds() / 86400, 2) if reported and refunded else None,
               # a recall or a chargeback here is only a draft: nothing is recovered when the case is sealed
               "recovery_proposed": escroc if escroc in ("RECHEMARE", "CHARGEBACK") else None,
               "note": reasons[0]["sentence"] if reasons else None, "decisions": decisions,
               "rule_ids": sorted({r for d in state.get("decisions") or [] for r in d.get("rule_ids") or []})}
    ctx = state.get("rule_context") or {}
    meta = {"scenario": ctx.get("scenario"), "channel": ctx.get("channel"), "dispute_type": ctx.get("dispute_type"),
            "case_id": c.case_id}
    # off the event loop and with a time limit: the embedding is a network call, and the seal must not wait on it
    try:
        added = await asyncio.wait_for(
            asyncio.to_thread(G.add_precedent, c.case_id, precedent_text(c, state), outcome, meta=meta),
            timeout=PRECEDENT_TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("precedent for %s still embedding after %ss; sealing without waiting", c.case_id, PRECEDENT_TIMEOUT_S)
        return
    if added:
        await c.fact("sigiliu", "kb.precedent_added", "knowledge.add_precedent", {"case_id": c.case_id},
                     {"outcome": outcome}, "The case was added to the precedents for similar cases (pseudonymized)",
                     Labels(conf="client", trust=Trust.TRUSTED, sinks=[Sink.CLIENT]))


def new_run_id() -> str:
    return "RUN-" + uuid.uuid4().hex[:8]
