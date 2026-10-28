"""Text helpers for retrieval: normalization, tokens for BM25, rule IDs, confidence marks, sentences.

Tokens: ș/ț with comma below (cedillas normalized), lower case, no diacritics, Romanian and English stop
words removed, light suffix stemming shared by both languages. The same function runs on documents and
queries, so consistency matters more than linguistic precision.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from versoml.shared.privacy.text import normalize_ro

# Rule ID prefixes used in docs/context and in the rules registry
RULE_PREFIXES = ("POP", "REQ", "KYC", "AML", "CRD", "PAY", "CMP", "DP", "DSP", "REC", "URM", "SAN", "DEC", "PROC")
_PREFIX_ALT = "|".join(sorted(RULE_PREFIXES, key=len, reverse=True))
RULE_ID_RE = re.compile(rf"\b({_PREFIX_ALT})-(\d{{2}})\b")
# queries are looser: "pay-3", "PAY 03", "Pay03"
QUERY_RULE_ID_RE = re.compile(rf"(?i)(?<![A-Za-z])({_PREFIX_ALT})[\s\-]?(\d{{1,2}})(?!\d)")
TEST_ID_RE = re.compile(r"\b(TC|DT|DX|EX|EXC)-(\d{2})\b")
# [P], [S], [U], [S/U], [P — comunicat CURIA 147/26], [S, snippet], [P-proiect], [Inf], [PRESUPUNERE]
MARK_RE = re.compile(r"\[(P-proiect|P|S|U|Inf|PRESUPUNERE)((?:\s*/\s*(?:P|S|U))*)(?=[\]\s,;—–:\-])[^\]\n]{0,80}\]")
_MARK_ORDER = {"U": 0, "S": 1, "P": 2}

_WORD_RE = re.compile(r"[a-z0-9]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

STOPWORDS_RO = frozenset("""
a acea aceasta aceea acei aceia acel acela acelasi acele acelea acest acesta aceste acestea acestei acestia acestor
acestora acum adica ai aia aici al ale alt alta alte altele altfel alti am apoi ar are as asa asta astfel atat atata
atunci au avea avem aveti avut ca cand care careia carora caruia cat cata cate catre ce cea ceea cei ceilalti cel
cele celor ceva chiar ci cine cineva cu cum da daca dar de deci deja desi despre din dintre doar dupa ea ei el ele
era este eu fara fi fie fiecare fiind foarte fost i ia ii il im in inainte inca incat intr intre isi iti la le li
lor lui m ma mai mi mult multe multi ne nici niciun nicio nu numai o ori oricare orice pana pe pentru poate prin sa
sau se si sub sunt suntem sunteti ta tale tau te tine tot toata toate toti tu un una unde unei unele unii unor unui
va voi vor iar
""".split())

STOPWORDS_EN = frozenset("""
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other
our ours ourselves out over own same she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when where which while who whom why will
with would you your yours yourself yourselves must may might shall also s t
""".split())

STOPWORDS = STOPWORDS_RO | STOPWORDS_EN

# Light suffix stripping, longest first; the stem keeps at least 3 characters
_SUFFIXES = tuple(sorted({
    # Romanian (folded): articles, plurals, oblique cases
    "urilor", "iilor", "ilor", "elor", "ului", "uri", "iile", "ile", "ele", "lor", "iei", "ii", "ul", "ua", "ea", "ei",
    "le", "ia", "ie", "a", "e", "i",
    # English
    "ations", "ation", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly", "y",
}, key=len, reverse=True))


def fold(text: str) -> str:
    """Lower case, no diacritics, ș/ț normalized first."""
    text = normalize_ro(text or "").lower()
    out = []
    for ch in unicodedata.normalize("NFKD", text):
        if not unicodedata.combining(ch):
            out.append(ch)
    return "".join(out)


@lru_cache(maxsize=200_000)
def stem(token: str) -> str:
    if len(token) < 4 or not token.isalpha():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    """BM25 tokens. Rule IDs also yield one composite token (pay_03), so an exact ID is a rare, strong term."""
    folded = fold(text)
    tokens = [stem(t) for t in _WORD_RE.findall(folded) if t not in STOPWORDS]
    for rid in _rule_mentions(normalize_ro(text or "")):
        tokens.append(rid.lower().replace("-", "_"))
    return tokens


# "PAY-01, 03, 04" and "AML-07–09" name several rules; short ranges are expanded, long ones keep their ends
_ID_TAIL = re.compile(r"((?:\s*(?:,|–|-|și|si|and)\s*\d{2}\b(?!\s*[.:/]\d))+)")
_MAX_RANGE = 6


def _rule_mentions(text: str) -> list[str]:
    out: list[str] = []
    for m in RULE_ID_RE.finditer(text):
        prefix, first = m.group(1), int(m.group(2))
        out.append(f"{prefix}-{first:02d}")
        tail = _ID_TAIL.match(text, m.end())
        if not tail:
            continue
        prev = first
        for sep, num in re.findall(r"\s*(,|–|-|și|si|and)\s*(\d{2})", tail.group(1)):
            n = int(num)
            if sep in ("–", "-") and prev < n <= prev + _MAX_RANGE:
                out.extend(f"{prefix}-{i:02d}" for i in range(prev + 1, n + 1))
            else:
                out.append(f"{prefix}-{n:02d}")
            prev = n
    return out


def query_tokens(text: str) -> list[str]:
    """Like `tokenize`, plus the composite tokens of loosely written rule IDs ("pay 3")."""
    tokens = tokenize(text)
    for rid in query_rule_ids(text):
        composite = rid.lower().replace("-", "_")
        if composite not in tokens:
            tokens.append(composite)
    return tokens


def rule_ids_in(text: str) -> list[str]:
    """Rule IDs mentioned in a document, in order of first appearance ("PAY-01, 03" gives PAY-01 and PAY-03)."""
    return list(dict.fromkeys(_rule_mentions(normalize_ro(text or ""))))


def query_rule_ids(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for prefix, number in QUERY_RULE_ID_RE.findall(normalize_ro(text or "")):
        seen.setdefault(f"{prefix.upper()}-{int(number):02d}", None)
    return list(seen)


def test_ids_in(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for prefix, number in TEST_ID_RE.findall(text or ""):
        seen.setdefault(f"{prefix}-{number}", None)
    return list(seen)


def marks_in(text: str) -> dict[str, int]:
    """Counts of confidence marks: {"P": 3, "S": 1, "U": 0, "Inf": 0, "PRESUPUNERE": 0}."""
    counts = {"P": 0, "S": 0, "U": 0, "Inf": 0, "PRESUPUNERE": 0}
    for head, rest in MARK_RE.findall(text or ""):
        if head == "P-proiect":
            counts["U"] += 1  # an official draft that is not adopted: unverified as law
            continue
        letters = [head] + re.findall(r"[PSU]", rest)
        if head in ("Inf", "PRESUPUNERE"):
            counts[head] += 1
            continue
        # a combined mark such as [S/U] counts as its weakest part
        weakest = min(letters, key=lambda x: _MARK_ORDER[x])
        counts[weakest] += 1
    return counts


def weakest_mark(counts: dict[str, int]) -> str | None:
    """The weakest P/S/U mark present (U < S < P), or None."""
    for mark in ("U", "S", "P"):
        if counts.get(mark):
            return mark
    return None


_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[\"„“(\[*]?[A-ZĂÂÎȘȚ0-9])")


def sentences(text: str) -> list[str]:
    """Sentences and table cells, each a verbatim substring of `text` (used by the extractive answer)."""
    out: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or set(line) <= set("|-: "):
            continue
        parts = [c.strip() for c in line.strip("|").split("|")] if line.startswith("|") else [line]
        for part in parts:
            part = re.sub(r"^(?:[-*>]|\d+[.)])\s+", "", part).strip()
            for sent in _SENT_SPLIT.split(part):
                sent = sent.strip()
                if len(sent) >= 25 and sent in text:
                    out.append(sent)
    return out


def slugify(text: str, max_len: int = 60) -> str:
    slug = _NON_ALNUM.sub("-", fold(text)).strip("-")
    if len(slug) > max_len:
        cut = slug[:max_len]
        slug = cut.rsplit("-", 1)[0] if "-" in cut[20:] else cut
    return slug or "section"


def norm_for_match(text: str) -> str:
    """For quote checks: folded, quotes and dashes unified, whitespace collapsed."""
    text = fold(text)
    text = re.sub(r"[“”„«»\"]", '"', text)
    text = re.sub(r"[‘’‚`']", "'", text)
    text = re.sub(r"[‐-―−]", "-", text)
    text = re.sub(r"[*_]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def char_ngram_text(text: str) -> str:
    """The form used for character n-grams: folded, only letters and digits, single spaces, padded."""
    return " " + " ".join(_WORD_RE.findall(fold(text))) + " "
