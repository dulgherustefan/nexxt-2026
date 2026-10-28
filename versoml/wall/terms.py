"""Termenii interziși în ieșirile zonei client (zidul, stratul 5; docs/05 §6.3).

Potrivirea se face pe textul pliat (fără diacritice, litere mici), cu flexiunile românești.
Înainte de potrivire se maschează formulările benigne dintr-o scrisoare de rambursare
(„blocat la cererea dumneavoastră", „mesaje suspecte", „monitorizați-vă contul").
Lista e o alegere de design, nu o regulă legală; temeiul interdicției e Legea 129/2019
art. 38 alin. (2) (tipping-off), citat în docs/05 §0 și §3.
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


@dataclass(frozen=True)
class TermHit:
    term_id: str
    label: str
    start: int
    end: int
    why: str


_W = r"(?:\S+\s+)"  # un cuvânt (cu punctuația lipită) urmat de spațiu
_CONT = r"cont(?:ul(?:ui)?|uri(?:le|lor)?)?\b"
_BENEF = r"beneficiar(?:ul|ului|i|ii|ilor|a|ei)?\b"
_SUBJECT = rf"(?:{_BENEF}|{_CONT}|destinatar\w*|titular\w*|persoan\w*|firm[aei]\w*|societat\w*|platitor\w*)"
_INVESTIG = r"(?:investig\w*|anchet\w*)"


def _t(term_id: str, label: str, pattern: str, why: str) -> Term:
    return Term(term_id, label, re.compile(pattern), why)


# Ordinea contează: termenii specifici întâi; zona lor e mascată înainte de cei generali
TERMS: tuple[Term, ...] = (
    _t("onpcsb", "ONPCSB",
       r"(?<![a-z0-9])[o0]\W{0,2}n\W{0,2}p\W{0,2}c\W{0,2}s\W{0,2}b(?![a-z0-9])",
       "numește autoritatea de raportare AML"),
    _t("oficiul", "Oficiul Național de Prevenire și Combatere a Spălării Banilor",
       r"\boficiul\w*\s+national\w*\s+de\s+prevenire\b|\bprevenire\w*\s+si\s+combatere\w*\s+a\s+spalarii\b"
       r"|\bcombaterea?\s+spalarii\s+banilor\b",
       "numește autoritatea de raportare AML"),
    _t("spalare_bani", "spălare de bani",
       r"\bspal(?:are|area|arii|ari|at|ate|ati|atul)\s+(?:a\s+|de\s+|unor\s+)?ban(?:i|ii|ilor)\b"
       r"|\bspalator\w*\s+de\s+bani\b|\banti[\s-]?spalare\w*",
       "dezvăluie o suspiciune de spălare a banilor"),
    _t("money_laundering", "money laundering", r"\b(?:anti[\s-]?)?money[\s-]+launder\w*|\blaunder(?:ing|ed)\b",
       "dezvăluie o suspiciune de spălare a banilor"),
    _t("finantare_terorism", "finanțarea terorismului", r"\bfinantar\w*\s+(?:a\s+)?terorism\w*|\bterrorist\s+financing\b",
       "dezvăluie o suspiciune de finanțare a terorismului"),
    _t("raport_suspect", "raport de tranzacție suspectă",
       rf"\brap(?:ort|oart)\w*\s+{_W}{{0,3}}?(?:tranzacti\w*|operatiun\w*|activitat\w*)\s+susp\w*"
       r"|\bsuspicious\s+(?:transaction|activity)\s+report\w*",
       "dezvăluie existența unui raport de tranzacție suspectă"),
    _t("rts", "RTS", r"(?<![a-z0-9])r[\s.]?t[\s.]?s(?![a-z0-9])", "acronimul raportului de tranzacție suspectă"),
    _t("legea_129", "Legea 129/2019", r"\b129\s*/\s*2019\b", "citează legea AML"),
    _t("aml", "AML", r"(?<![a-z0-9])a\.?m\.?l\.?(?![a-z0-9])", "numește zona sau analiza AML"),
    _t("tipping_off", "tipping-off", r"\btipping[\s-]?off\b", "numește chiar interdicția"),
    _t("carausi", "cărăuș (money mule)", r"\bcarau\w*|\bmoney[\s-]+mule\w*|\bmule\s+account\w*",
       "dezvăluie analiza conturilor-cărăuș"),
    _t("tranzactie_suspecta", "tranzacție suspectă",
       rf"\b(?:tranzacti\w*|operatiun\w*|activitat\w*|plat[ai]\w*|transfer\w*|fonduri\w*|{_CONT}|{_BENEF})\s+"
       rf"{_W}{{0,4}}?(?:suspect\w*|suspicio\w*)",
       "califică o tranzacție sau un cont drept suspecte"),
    _t("cont_monitorizat", "cont monitorizat",
       rf"\b{_CONT}\s+{_W}{{0,3}}?(?:monitorizat\w*|supravegheat\w*|sub\s+(?:monitorizare|supraveghere|observatie))"
       rf"|\bmonitoriz(?:am|eaza|at|ata|ate)\s+{_W}{{0,2}}?(?:{_CONT}|{_BENEF}|tranzacti\w*|activitat\w*|destinatar\w*)",
       "dezvăluie monitorizarea unui cont"),
    _t("investigatie", "investigație privind beneficiarul sau contul",
       rf"\b{_INVESTIG}\s+{_W}{{0,3}}?{_SUBJECT}|\b{_SUBJECT}\s+{_W}{{0,3}}?{_INVESTIG}",
       "dezvăluie o investigație asupra beneficiarului sau a unui cont"),
    _t("blocat_la_cerere", "blocat la cererea autorităților",
       r"\b(?:bloc\w*|suspend\w*|retinut\w*|retinere\w*|inghet\w*|sechestr\w*|poprit\w*|oprit\w*)\s+"
       rf"{_W}{{0,4}}?la\s+(?:cererea|solicitarea|dispozitia|ordinul|indicatia)\b"
       rf"|\bla\s+(?:cererea|solicitarea|dispozitia)\s+{_W}{{0,1}}?(?:autoritat\w*|organel\w*|procuror\w*|parchet\w*"
       r"|oficiul\w*|diicot|politi\w*)",
       "dezvăluie o blocare dispusă de o autoritate"),
    _t("raportat_autoritati", "raportat autorităților competente",
       r"\b(?:raportat\w*|raportare\w*|raportam|raporteaza|semnalat\w*|semnalam|sesizat\w*|sesizam|comunicat\w*"
       rf"|notificat\w*|transmis\w*|informat\w*)\s+{_W}{{0,4}}?(?:autoritat\w*|organel\w*\s+(?:de\s+)?"
       r"(?:urmarire|cercetare|competente|abilitate)|oficiul\w*\s+national|parchet\w*|diicot)",
       "dezvăluie o raportare către autorități"),
    _t("suspect", "suspect / suspiciune", r"\bsuspect\w*|\bsuspici\w*", "exprimă o suspiciune"),
    _t("pista", "pistă", r"\bpist(?:a|e|ei|ele|elor)\b", "vorbește despre o pistă de investigație"),
    _t("hold", "hold", r"\bhold\b", "numește semnalul HOLD din zona AML"),
)

# Formulări benigne într-o scrisoare de rambursare: se maschează înainte de căutare
ALLOW: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"\bla\s+(?:cererea|solicitarea|initiativa)\s+(?:dumneavoastra|dvs\.?|dumitale|clientului|titularului)",
    r"\b(?:mesaj\w*|sms\w*|link\w*|apel\w*|e-?mail\w*|site\w*|pagin\w*|notificar\w*|aplicati\w*|numar\w*"
    r"|apelant\w*|convorbir\w*|atasament\w*|qr)\s+" + _W + r"{0,2}?(?:suspect\w*|suspicio\w*)",
    r"\b(?:observati|constatati|identificati|remarcati|primiti|vedeti|sesizati)\s+" + _W + r"{0,3}?(?:suspect\w*|suspicio\w*)",
    r"\bmonitorizati(?:-v[ao]|-l|-le)?\b",
    r"\b(?:sa|va\s+rugam\s+sa|puteti|trebuie\s+sa)\s+(?:ne\s+|le\s+)?(?:raportati|semnalati|sesizati|notificati"
    r"|informati|transmiteti|contactati)\b",
))


def _mask(folded: str, start: int, end: int) -> str:
    return folded[:start] + " " * (end - start) + folded[end:]


def find_terms(text: str) -> list[TermHit]:
    """Toate aparițiile termenilor interziși, în ordinea din text."""
    text = normalize_ro(text or "")
    folded = fold(text)
    for allow in ALLOW:
        for m in allow.finditer(folded):
            folded = _mask(folded, m.start(), m.end())
    hits: list[TermHit] = []
    for term in TERMS:
        for m in term.pattern.finditer(folded):
            if m.end() > m.start():
                hits.append(TermHit(term.id, term.label, m.start(), m.end(), term.why))
        for hit in hits:
            if hit.term_id == term.id:
                folded = _mask(folded, hit.start, hit.end)
    return sorted(hits, key=lambda h: h.start)


def labels(hits: list[TermHit]) -> list[str]:
    """Etichetele unice, în ordinea apariției."""
    seen: list[str] = []
    for hit in hits:
        if hit.label not in seen:
            seen.append(hit.label)
    return seen


def snippet(text: str, start: int, end: int, width: int = 40) -> str:
    """Fragmentul din jurul unei potriviri, pe un singur rând."""
    text = normalize_ro(text or "")
    left = max(0, start - width)
    right = min(len(text), end + width)
    body = " ".join(text[left:right].split())
    return ("…" if left > 0 else "") + body + ("…" if right < len(text) else "")
