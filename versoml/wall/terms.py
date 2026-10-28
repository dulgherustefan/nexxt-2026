"""Forbidden terms in what the client zone writes (the wall, layer 5; docs/05 §6.3).

Letters are in English now, so every term has its English forms next to the Romanian ones (with their
inflections). Matching runs on the folded text (no diacritics, lower case). A few acronyms that are also ordinary
words (STR for "strada", SAR, FIU, the HOLD signal) are matched with their capitals, on a copy of the text that
keeps the case but has the same length and positions.

Before matching, harmless phrases in a refund letter are masked out ("blocked at your request", "suspicious
messages", "keep an eye on your account", "you can report it to the police"). The list is a design choice, not a
legal rule; the reason behind the ban is Law 129/2019, art. 38(2) (tipping-off), cited in docs/05 §0 and §3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from versoml.shared.privacy.text import fold, normalize_ro


@dataclass(frozen=True)
class Term:
    id: str
    label: str
    pattern: re.Pattern[str]
    why: str
    cased: bool = False      # matched on the text with its capitals kept


@dataclass(frozen=True)
class TermHit:
    term_id: str
    label: str
    start: int
    end: int
    why: str


_W = r"(?:\S+\s+)"  # one word (with any punctuation attached) followed by whitespace
_CONT = r"(?:cont(?:ul(?:ui)?|uri(?:le|lor)?)?|accounts?)\b"
_BENEF = r"(?:beneficiar(?:ul|ului|i|ii|ilor|a|ei)?|beneficiar(?:y|ies)|payees?|recipients?)\b"
_SUBJECT = (rf"(?:{_BENEF}|{_CONT}|destinatar\w*|titular\w*|persoan\w*|firm[aei]\w*|societat\w*|platitor\w*"
            r"|(?:account\s+)?holders?\b|owners?\b|individuals?\b|persons?\b|compan(?:y|ies)\b|firms?\b|business(?:es)?\b)")
_INVESTIG = r"(?:investig\w*|anchet\w*)"
_AUTHORITY = (r"(?:authorit(?:y|ies)\b|prosecutor\w*|diicot\b|fiu\b|financial\s+intelligence\b|law\s+enforcement\b"
              r"|police\b)")


def _t(term_id: str, label: str, pattern: str, why: str, *, cased: bool = False) -> Term:
    return Term(term_id, label, re.compile(pattern), why, cased)


# Order matters: specific terms first; their span is masked before the general ones run
TERMS: tuple[Term, ...] = (
    _t("onpcsb", "ONPCSB",
       r"(?<![a-z0-9])[o0]\W{0,2}n\W{0,2}p\W{0,2}c\W{0,2}s\W{0,2}b(?![a-z0-9])",
       "names the AML reporting authority"),
    _t("oficiul", "ONPCSB (full name)",
       r"\boficiul\w*\s+national\w*\s+de\s+prevenire\b|\bprevenire\w*\s+si\s+combatere\w*\s+a\s+spalarii\b"
       r"|\bcombaterea?\s+spalarii\s+banilor\b"
       r"|\bnational\s+office\s+for\s+(?:the\s+)?prevention\s+and\s+(?:control|combating|combat)\s+of\s+money\s+launder\w*",
       "names the AML reporting authority"),
    _t("fiu", "financial intelligence unit", r"\bfinancial\s+intelligence(?:\s+units?)?\b",
       "names the financial intelligence unit, the AML reporting authority"),
    _t("fiu_acronym", "FIU", r"(?<![A-Za-z0-9])F\.?I\.?U\.?s?(?![A-Za-z0-9])",
       "names the financial intelligence unit, the AML reporting authority", cased=True),
    _t("spalare_bani", "money laundering",
       r"\bspal(?:are|area|arii|ari|at|ate|ati|atul)\s+(?:a\s+|de\s+|unor\s+)?ban(?:i|ii|ilor)\b"
       r"|\bspalator\w*\s+de\s+bani\b|\banti[\s-]?spalare\w*",
       "reveals a money laundering suspicion"),
    _t("money_laundering", "money laundering", r"\b(?:anti[\s-]?)?money[\s-]*launder\w*|\blaunder\w*",
       "reveals a money laundering suspicion"),
    _t("finantare_terorism", "terrorist financing",
       r"\bfinantar\w*\s+(?:a\s+)?terorism\w*|\bterror\w*[\s-]+financ\w*|\bfinanc\w*\s+(?:of\s+)?terror\w*",
       "reveals a terrorist financing suspicion"),
    _t("raport_suspect", "suspicious transaction report",
       rf"\brap(?:ort|oart)\w*\s+{_W}{{0,3}}?(?:tranzacti\w*|operatiun\w*|activitat\w*)\s+susp\w*"
       r"|\bsuspicious[\s-]+(?:transaction|activity|activities|matter|operation)s?[\s-]+reports?\b"
       rf"|\breports?\s+{_W}{{0,3}}?(?:on|of|about)\s+(?:an?\s+|the\s+)?suspicious\s+(?:transaction|activit|payment"
       r"|transfer|operation)\w*",
       "reveals that a suspicious transaction report exists"),
    _t("rts", "RTS", r"(?<![a-z0-9])r[\s.]?t[\s.]?s(?![a-z0-9])", "the Romanian acronym for a suspicious transaction report"),
    _t("str", "STR", r"(?<![A-Za-z0-9])S\.?T\.?R\.?s?(?![A-Za-z0-9])", "the acronym for a suspicious transaction report",
       cased=True),
    _t("sar", "SAR", r"(?<![A-Za-z0-9])S\.?A\.?R\.?s?(?![A-Za-z0-9])", "the acronym for a suspicious activity report",
       cased=True),
    _t("legea_129", "Law 129/2019", r"\b129\s*/\s*2019\b", "cites the AML law"),
    _t("aml", "AML", r"(?<![a-z0-9])a\.?m\.?l\.?(?![a-z0-9])", "names the AML zone or an AML review"),
    _t("mlro", "MLRO", r"\bmlros?\b", "names the money laundering reporting officer"),
    _t("tipping_off", "tipping-off", r"\btipping[\s-]?off\b|\btip[\s-]off\b|\btip(?:ped|ping|s)?\s+(?:\S+\s+)?off\b",
       "names the ban itself"),
    _t("carausi", "money mule", r"\bcarau\w*|\bmoney[\s-]+mules?\b|\bmule\s+accounts?\b|\bmules?\b",
       "reveals the money mule analysis"),
    _t("financial_crime", "financial crime", r"\bfinancial[\s-]+crimes?\b|\bfin[\s-]?crime\b",
       "names the financial crime team or review"),
    _t("compliance", "compliance review",
       rf"\b(?:flagged|referred|escalated|reported|passed|sent|forwarded)\s+{_W}{{0,3}}?(?:by|to|with)\s+(?:our\s+|the\s+)?"
       r"compliance\b|\bcompliance\s+(?:team|department|unit|officer|function|review|check|investigation|analyst|hold"
       r"|flag)\w*",
       "reveals a compliance review"),
    _t("under_investigation", "under investigation",
       r"\bunder\s+(?:an?\s+)?(?:\w+\s+)?(?:investigation|scrutiny|surveillance|observation)\b"
       r"|\b(?:pending|subject\s+to)\s+(?:an?\s+|the\s+)?(?:\w+\s+)?investigation\b",
       "says someone or something is under investigation"),
    _t("tranzactie_suspecta", "suspicious transaction",
       rf"\b(?:tranzacti\w*|operatiun\w*|activitat\w*|plat[ai]\w*|transfer\w*|fonduri\w*|{_CONT}|{_BENEF})\s+"
       rf"{_W}{{0,4}}?(?:suspect\w*|suspicio\w*)"
       rf"|\b(?:transactions?|operations?|activit(?:y|ies)|payments?|funds?)\s+{_W}{{0,4}}?(?:suspect\w*|suspicious\w*)"
       rf"|\bsuspicious(?:ly)?\s+{_W}{{0,2}}?(?:transactions?|operations?|activit\w*|payments?|transfers?|funds?|{_CONT}"
       rf"|{_BENEF}|behaviou?r|patterns?)",
       "calls a transaction or an account suspicious"),
    _t("cont_monitorizat", "monitored account",
       rf"\b{_CONT}\s+{_W}{{0,3}}?(?:monitorizat\w*|supravegheat\w*|sub\s+(?:monitorizare|supraveghere|observatie)"
       r"|monitored|watched|under\s+(?:monitoring|surveillance|observation|watch))"
       rf"|\bmonitoriz(?:am|eaza|at|ata|ate)\s+{_W}{{0,2}}?(?:{_CONT}|{_BENEF}|tranzacti\w*|activitat\w*|destinatar\w*)"
       rf"|\bmonitor(?:ing|ed|s)?\s+{_W}{{0,2}}?(?:{_CONT}|{_BENEF}|transactions?|activit\w*)"
       rf"|\bkeep(?:ing)?\s+(?:a\s+close\s+|an\s+)?eye\s+on\s+(?:the|their|this|that)\s+(?:{_CONT}|{_BENEF})",
       "reveals that an account is being monitored"),
    _t("investigatie", "investigation of the payee or an account",
       rf"\b{_INVESTIG}\s+{_W}{{0,3}}?{_SUBJECT}|\b{_SUBJECT}\s+{_W}{{0,3}}?{_INVESTIG}",
       "reveals an investigation into the payee or an account"),
    # passive ("the account was flagged") or the bank as the subject ("we've flagged"); "the payment you flagged
    # to us" is the customer reporting it, and stays allowed
    _t("flagged", "flagged account or payment",
       rf"\b(?:{_CONT}|{_BENEF}|holders?|transactions?|payments?|transfers?)\s+{_W}{{0,3}}?(?:was|were|is|are|been"
       r"|being)\s+(?:\w+\s+)?(?:flagged|blacklisted|black-listed|watch-?listed)\b"
       r"|\b(?:we|we've|we\s+have|we\s+had|our\s+\w+\s+(?:has|have|had))\s+(?:\w+\s+)?(?:flagged|blacklisted"
       r"|watch-?listed)\b",
       "reveals that an account or a payment was flagged"),
    _t("blocat_la_cerere", "blocked at the authorities' request",
       r"\b(?:bloc\w*|suspend\w*|retinut\w*|retinere\w*|inghet\w*|sechestr\w*|poprit\w*|oprit\w*)\s+"
       rf"{_W}{{0,4}}?la\s+(?:cererea|solicitarea|dispozitia|ordinul|indicatia)\b"
       rf"|\bla\s+(?:cererea|solicitarea|dispozitia)\s+{_W}{{0,1}}?(?:autoritat\w*|organel\w*|procuror\w*|parchet\w*"
       r"|oficiul\w*|diicot|politi\w*)"
       rf"|\b(?:block\w*|suspend\w*|froze|frozen|freez\w*|held|seiz\w*|retain\w*|stopped|restrict\w*)\s+{_W}{{0,4}}?"
       r"(?:at|on|upon|by|following|under)\s+(?:the\s+)?(?:request|order|instruction|direction|demand)s?\s+(?:of|from)\s+"
       rf"(?:the\s+)?{_W}{{0,1}}?(?:{_AUTHORITY}|courts?\b)"
       r"|\b(?:at|on|upon|following)\s+the\s+(?:request|order|instruction|direction)s?\s+of\s+(?:the\s+)?"
       rf"{_W}{{0,1}}?{_AUTHORITY}"
       rf"|\b(?:blocked|frozen|seized|suspended|held|stopped)\s+by\s+(?:the\s+)?{_W}{{0,1}}?{_AUTHORITY}",
       "reveals a block ordered by an authority"),
    _t("raportat_autoritati", "reported to the authorities",
       r"\b(?:raportat\w*|raportare\w*|raportam|raporteaza|semnalat\w*|semnalam|sesizat\w*|sesizam|comunicat\w*"
       rf"|notificat\w*|transmis\w*|informat\w*)\s+{_W}{{0,4}}?(?:autoritat\w*|organel\w*\s+(?:de\s+)?"
       r"(?:urmarire|cercetare|competente|abilitate)|oficiul\w*\s+national|parchet\w*|diicot)"
       r"|\b(?:report(?:ed|ing|s)?|notif(?:ied|y|ying)|inform(?:ed|ing)?|alert(?:ed|ing)?|flag(?:ged|ging)?"
       r"|refer(?:red|ring)?|disclos(?:ed|ing)|forward(?:ed|ing)?|escalat(?:ed|ing)|submitted|filed|passed)\s+"
       rf"{_W}{{0,4}}?(?:to\s+)?(?:the\s+)?(?:competent\s+|relevant\s+|appropriate\s+|national\s+)?"
       r"(?:authorit(?:y|ies)\b|prosecutor\w*|diicot\b|financial\s+intelligence\b|law\s+enforcement\b)",
       "reveals a report to the authorities"),
    _t("suspect", "suspicion", r"\bsuspect\w*|\bsuspici\w*", "expresses a suspicion"),
    _t("pista", "investigation lead", r"\bpist(?:a|e|ei|ele|elor)\b", "talks about an investigation lead"),
    _t("hold_signal", "HOLD", r"(?<![A-Za-z0-9])HOLD(?![A-Za-z0-9])", "names the HOLD signal from the AML zone",
       cased=True),
    _t("hold", "HOLD",
       r"\bpe\s+hold\b|\b(?:on|under)\s+(?:a\s+)?hold\b|\bhold\s+(?:signal|flag|order|request|notice|status|code)s?\b"
       r"|\b(?:a|an|the|this|un|o)\s+hold\s+(?:on|over|against|pe|asupra)\b|\bsemnal\w*\s+(?:de\s+)?hold\b"
       r"|\bhold-?ul(?:ui)?\b",
       "says money or an account is on hold (the AML zone's HOLD signal)"),
)

# Harmless phrases in a refund letter: masked out before the search
ALLOW: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    # Romanian
    r"\bla\s+(?:cererea|solicitarea|initiativa)\s+(?:dumneavoastra|dvs\.?|dumitale|clientului|titularului)",
    r"\b(?:mesaj\w*|sms\w*|link\w*|apel\w*|e-?mail\w*|site\w*|pagin\w*|notificar\w*|aplicati\w*|numar\w*"
    r"|apelant\w*|convorbir\w*|atasament\w*|qr)\s+" + _W + r"{0,2}?(?:suspect\w*|suspicio\w*)",
    r"\b(?:observati|constatati|identificati|remarcati|primiti|vedeti|sesizati)\s+" + _W + r"{0,3}?(?:suspect\w*|suspicio\w*)",
    r"\bmonitorizati(?:-v[ao]|-l|-le)?\b",
    r"\b(?:sa|va\s+rugam\s+sa|puteti|trebuie\s+sa)\s+(?:ne\s+|le\s+)?(?:raportati|semnalati|sesizati|notificati"
    r"|informati|transmiteti|contactati)\b",
    # English: the customer's own request
    r"\b(?:at|on|upon)\s+(?:your|the\s+customer'?s|the\s+cardholder'?s|the\s+account\s+holder'?s)\s+(?:own\s+)?request\b",
    # English: scam messages and links, and the customer noticing something
    r"\b(?:suspicious|suspect)(?:-looking)?\s+" + _W + r"{0,1}?(?:message|text|sms|link|call|caller|e-?mail|site"
    r"|website|page|number|notification|app|attachment|qr|request|offer|people)\w*",
    r"\b(?:message|text|sms|link|call|e-?mail|site|website|page|number|notification|app|attachment|offer)\w*\s+"
    + _W + r"{0,2}?(?:that\s+|which\s+)?(?:looks?|seems?|appears?|sounds?)\s+suspicious\b",
    r"\byou\s+" + _W + r"{0,1}?(?:notice|see|spot|get|receive|find|come\s+across|hear)\s+" + _W
    + r"{0,3}?(?:suspicious|suspect)\w*",
    r"\b(?:if|when|whenever)\s+you\s+(?:ever\s+)?suspect\b",
    r"\b(?:anything|something)\s+" + _W + r"{0,1}?(?:looks?|seems?|feels?|sounds?)\s+suspicious\b",
    # English: the customer keeping an eye on their own account, or reporting something themselves
    r"\b(?:you\s+(?:can|could|should|may|might)\s+(?:also\s+)?|please\s+|recommend\s+(?:that\s+)?you\s+"
    r"|advise\s+you\s+to\s+|remember\s+to\s+|to\s+)(?:keep\s+)?monitor(?:ing)?\s+your\s+(?:own\s+)?(?:account|card"
    r"|transactions|payments|statements?)\w*",
    r"\byou\s+(?:can|could|should|may|might|are\s+entitled\s+to|have\s+the\s+right\s+to)\s+(?:also\s+)?(?:\S+\s+)?"
    r"(?:report|refer|notify|tell|contact|inform|complain|escalate|write|take|alert)\w*",
    r"\bplease\s+(?:also\s+)?(?:report|tell|contact|notify|let|inform|alert)\w*",
    r"\b(?:recommend|suggest|advise|encourage|ask)\w*\s+(?:that\s+)?you\s+" + _W
    + r"{0,1}?(?:report|notify|tell|contact|inform|alert|file|make)\w*",
))


def _mask(folded: str, start: int, end: int) -> str:
    return folded[:start] + " " * (end - start) + folded[end:]


def _cased(text: str, folded: str) -> str:
    """The folded text with the capitals put back (same length and positions as the original)."""
    return "".join(f.upper() if ch.isupper() and len(f.upper()) == 1 else f for ch, f in zip(text, folded))


def find_terms(text: str) -> list[TermHit]:
    """Every occurrence of a forbidden term, in text order."""
    text = normalize_ro(text or "")
    folded = fold(text)
    cased = _cased(text, folded)
    for allow in ALLOW:
        for m in allow.finditer(folded):
            folded, cased = _mask(folded, m.start(), m.end()), _mask(cased, m.start(), m.end())
    hits: list[TermHit] = []
    for term in TERMS:
        for m in term.pattern.finditer(cased if term.cased else folded):
            if m.end() > m.start():
                hits.append(TermHit(term.id, term.label, m.start(), m.end(), term.why))
        for hit in hits:
            if hit.term_id == term.id:
                folded, cased = _mask(folded, hit.start, hit.end), _mask(cased, hit.start, hit.end)
    return sorted(hits, key=lambda h: h.start)


def labels(hits: list[TermHit]) -> list[str]:
    """The distinct labels, in order of appearance."""
    seen: list[str] = []
    for hit in hits:
        if hit.label not in seen:
            seen.append(hit.label)
    return seen


def snippet(text: str, start: int, end: int, width: int = 40) -> str:
    """The text around a match, on one line."""
    text = normalize_ro(text or "")
    left = max(0, start - width)
    right = min(len(text), end + width)
    body = " ".join(text[left:right].split())
    return ("…" if left > 0 else "") + body + ("…" if right < len(text) else "")
