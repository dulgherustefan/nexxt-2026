"""M3: scorul de domeniu-sosie (0–1), cu explicații în română.

Pași:
1. pentru fiecare domeniu protejat generăm permutări în stilul dnstwist (homoglyph, bitsquatting,
   insertion, omission, repetition, replacement, transposition, vowel-swap, hyphenation, addition,
   subdomain, TLD swap, dictionary, plural);
2. domeniul evaluat se decodează din punycode, se reduce la un „schelet" în stilul Unicode TR39
   (confusables: chirilic/grec → latin, 0/o, 1/l/i, rn/m, vv/w, cl/d) și se compară cu fiecare brand:
   Damerau-Levenshtein, Jaro-Winkler, conținerea brandului, scheletul, cuvintele de risc, cratimele,
   TLD-ul, vârsta domeniului și a certificatului;
3. trăsăturile se combină logistic: scor = 1 / (1 + e^(-z)), z = W0 + Σ wᵢ·xᵢ (ponderile în WEIGHTS).

Ponderile sunt alese de echipă și calibrate pe cazurile de test, nu învățate pe date reale [U].
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from collections import defaultdict
from functools import lru_cache
from typing import Any

from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler

from versoml.osint.base import ToolResult, en_count, failure, tool
from versoml.osint.params import param
from versoml.osint.util import DomainParts, split_domain, to_ascii

# Ponderile modelului logistic (z = W0 + Σ w·x). Documentate aici, folosite în explicații.
WEIGHTS: dict[str, float] = {
    "bias": -4.0,                # un domeniu oarecare pornește de la ~0,02
    "permutation": 2.0,          # apare exact în permutările generate pentru brand
    "skeleton_equal": 6.0,       # aceeași formă vizuală ca brandul (homoglife, cratime, rn→m), alt text
    "tld_swap": 6.0,             # eticheta brandului pe alt TLD
    "brand_in_label": 4.5,       # brandul + alte cuvinte (combosquatting)
    "brand_in_skeleton": 5.0,    # brandul apare doar după scheletizare (homoglife + combo)
    "brand_in_subdomain": 4.0,   # brandul e pus în subdomeniu (bancademo.example.altceva.test)
    "typo": 3.0,                 # × (sim_DL − 0,75)/0,25, doar pentru sim ≥ 0,75
    "jaro_winkler": 1.5,         # × (JW − 0,85)/0,15, doar pentru JW ≥ 0,85
    "keyword": 0.6,              # pe fiecare cuvânt de risc (maximum 3)
    "hyphen": 0.3,               # pe fiecare cratimă (maximum 3)
    "idn": 1.0,                  # domeniu IDN (punycode)
    "risky_tld": 0.8,            # TLD folosit des în campanii de phishing [U]
    "young_domain": 1.5,         # × 1 sub 7 zile, × 0,5 sub 30 de zile (din RDAP)
    "young_cert": 0.8,           # primul certificat sub 72 de ore (din CT)
}

QWERTY: dict[str, str] = {
    "1": "2q", "2": "3wq1", "3": "4ew2", "4": "5re3", "5": "6tr4", "6": "7yt5", "7": "8uy6", "8": "9iu7",
    "9": "0oi8", "0": "po9", "q": "12wa", "w": "3esaq2", "e": "4rdsw3", "r": "5tfde4", "t": "6ygfr5",
    "y": "7uhgt6", "u": "8ijhy7", "i": "9okju8", "o": "0plki9", "p": "lo0", "a": "qwsz", "s": "edxzaw",
    "d": "rfcxse", "f": "tgvcdr", "g": "yhbvft", "h": "ujnbgy", "j": "ikmnhu", "k": "olmji", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}
ASCII_GLYPHS: dict[str, tuple[str, ...]] = {
    "0": ("o",), "1": ("l", "i"), "3": ("8",), "5": ("s",), "6": ("9",), "8": ("3",), "9": ("6",),
    "a": ("4",), "b": ("d", "lb"), "c": ("e",), "d": ("b", "cl"), "e": ("c", "3"), "g": ("q",), "h": ("lh",),
    "i": ("1", "l"), "k": ("lc",), "l": ("1", "i"), "m": ("n", "nn", "rn"), "n": ("m", "r"), "o": ("0",),
    "q": ("g",), "s": ("5",), "u": ("v",), "v": ("u",), "w": ("vv",),
}
# Homoglife Unicode (chirilic, grec, latin extins) folosite la generare
UNICODE_GLYPHS: dict[str, tuple[str, ...]] = {
    "a": ("а", "ɑ", "à", "á", "â", "ä", "ă"), "c": ("с", "ç"), "d": ("ԁ",), "e": ("е", "é", "è", "ê"),
    "h": ("һ",), "i": ("і", "í", "ı", "î"), "j": ("ј",), "k": ("κ",), "l": ("ӏ",), "n": ("ո",), "o": ("о", "ο", "ó", "ö"),
    "p": ("р",), "s": ("ѕ", "ș"), "t": ("ț",), "u": ("υ", "ü"), "x": ("х",), "y": ("у",),
}
# Tabelul de confusables pentru schelet (un subset compact din TR39 + cifre); restul se rezolvă prin NFKD
CONFUSABLES: dict[str, str] = {
    "а": "a", "ɑ": "a", "α": "a", "в": "b", "с": "c", "ϲ": "c", "ԁ": "d", "е": "e", "ε": "e", "ҽ": "e",
    "һ": "h", "і": "l", "ı": "l", "ι": "l", "ӏ": "l", "ј": "j", "κ": "k", "к": "k", "м": "m", "ո": "n",
    "п": "n", "η": "n", "о": "o", "ο": "o", "σ": "o", "р": "p", "ρ": "p", "ѕ": "s", "т": "t", "τ": "t",
    "υ": "u", "ν": "v", "ѵ": "v", "ш": "w", "ω": "w", "х": "x", "χ": "x", "у": "y", "γ": "y", "з": "3",
    "0": "o", "1": "l", "i": "l", "|": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a",
}
MULTI_CONFUSABLES: tuple[tuple[str, str], ...] = (("rn", "m"), ("vv", "w"), ("cl", "d"))
VOWELS = "aeiouy"
ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
DICTIONARY = (
    "plati", "plata", "livrare", "confirmare", "secure", "login", "verificare", "cont", "card", "colet",
    "securitate", "autentificare", "online", "suport", "client", "app", "actualizare", "rambursare", "taxa",
)
RISKY_KEYWORDS = frozenset(DICTIONARY) | {
    "verifica", "plateste", "vamala", "bonus", "premiu", "castig", "update", "verify", "account", "banking",
    "support", "service", "curier", "posta", "awb", "tracking", "sms", "otp", "3ds", "deblocare", "blocat",
    "urgent", "refund", "pay", "payment", "wallet", "info",
}
SWAP_TLDS = (
    "com", "net", "org", "info", "biz", "ro", "eu", "online", "site", "shop", "top", "xyz", "app", "live",
    "store", "co", "io", "me", "cc", "icu", "click", "support", "help", "tech", "website", "cloud", "pro",
    "vip", "life", "example", "test",
)
RISKY_TLDS = frozenset({
    "top", "xyz", "online", "site", "shop", "icu", "live", "click", "support", "help", "buzz", "cfd", "sbs",
    "rest", "monster", "cyou", "quest", "vip", "work", "store", "website", "space", "fun", "life",
})


# ---------------------------------------------------------------- schelet și permutări


def skeleton(text: str) -> str:
    """Forma vizuală canonică: confusables → latin, fără diacritice, fără cratime, rn→m, vv→w, cl→d."""
    out = []
    for ch in unicodedata.normalize("NFC", text.casefold()):
        if ch in CONFUSABLES:
            out.append(CONFUSABLES[ch])
            continue
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        out.append(CONFUSABLES.get(base, base))
    flat = "".join(out).replace("-", "").replace("_", "")
    for seq, repl in MULTI_CONFUSABLES:
        flat = flat.replace(seq, repl)
    return flat


def _valid_label(label: str) -> bool:
    return bool(label) and not label.startswith("-") and not label.endswith("-") and "--" not in label[2:4]


def _label_variants(label: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    n = len(label)
    for c in ALNUM:
        out["addition"].add(label + c)
    for i, ch in enumerate(label):
        for mask in (1, 2, 4, 8, 16, 32, 64, 128):
            flipped = chr(ord(ch) ^ mask)
            if flipped in ALNUM or flipped == "-":
                out["bitsquatting"].add(label[:i] + flipped + label[i + 1:])
        for glyph in ASCII_GLYPHS.get(ch, ()) + UNICODE_GLYPHS.get(ch, ()):
            out["homoglyph"].add(label[:i] + glyph + label[i + 1:])
        out["omission"].add(label[:i] + label[i + 1:])
        out["repetition"].add(label[:i] + ch + label[i:])
        for key in QWERTY.get(ch, ""):
            out["replacement"].add(label[:i] + key + label[i + 1:])
        if ch in VOWELS:
            for vowel in VOWELS:
                if vowel != ch:
                    out["vowel-swap"].add(label[:i] + vowel + label[i + 1:])
    for seq, repl in (("rn", "m"), ("m", "rn"), ("vv", "w"), ("w", "vv"), ("cl", "d"), ("d", "cl")):
        start = label.find(seq)
        while start != -1:
            out["homoglyph"].add(label[:start] + repl + label[start + len(seq):])
            start = label.find(seq, start + 1)
    for i in range(1, n):
        out["hyphenation"].add(label[:i] + "-" + label[i:])
    for i in range(1, n - 1):
        for key in QWERTY.get(label[i], ""):
            out["insertion"].add(label[:i] + key + label[i:])
            out["insertion"].add(label[:i + 1] + key + label[i + 1:])
    for i in range(n - 1):
        if label[i] != label[i + 1]:
            out["transposition"].add(label[:i] + label[i + 1] + label[i] + label[i + 2:])
    out["plural"].update({label + "s", label + "es"})
    for fuzzer in out:
        out[fuzzer] = {v for v in out[fuzzer] if v != label and _valid_label(v)}
    return out


@lru_cache(maxsize=64)
def permutations(protected_domain: str) -> dict[str, str]:
    """Permutările unui domeniu protejat: domeniu ASCII → fuzzer-ul care l-a generat."""
    parts = split_domain(protected_domain)
    if parts is None:
        return {}
    label, tld = parts.unicode_label, parts.suffix
    found: dict[str, str] = {}

    def add(domain: str, fuzzer: str) -> None:
        ascii_domain = to_ascii(domain)
        if ascii_domain and ascii_domain != parts.registered:
            found.setdefault(ascii_domain, fuzzer)

    for fuzzer, variants in _label_variants(label).items():
        for variant in variants:
            add(f"{variant}.{tld}", fuzzer)
    for i in range(1, len(label)):
        add(f"{label[:i]}.{label[i:]}.{tld}", "subdomain")
    for swap in SWAP_TLDS:
        if swap != tld:
            add(f"{label}.{swap}", "tld-swap")
    for word in DICTIONARY:
        for variant in (f"{word}-{label}", f"{label}-{word}", f"{word}{label}", f"{label}{word}"):
            for suffix in {tld, *SWAP_TLDS}:
                add(f"{variant}.{suffix}", "dictionary")
    return found


# ---------------------------------------------------------------- trăsături și scor


def _keywords(label: str, brand: str) -> list[str]:
    rest = label.replace(brand, " ")
    tokens = [t for t in re.split(r"[-_.\d]+|\s+", rest) if t]
    found = [t for t in tokens if t in RISKY_KEYWORDS]
    for kw in sorted(RISKY_KEYWORDS, key=len, reverse=True):
        if len(kw) >= 5 and kw in rest and kw not in found and not any(kw in f for f in found):
            found.append(kw)
    return found[:5]


def _features(parts: DomainParts, brand: DomainParts, age_hours: float | None,
              cert_age_hours: float | None) -> tuple[float, list[dict[str, Any]], dict[str, Any]]:
    label, blabel = parts.unicode_label, brand.unicode_label
    skel, bskel = skeleton(label), skeleton(blabel)
    feats: dict[str, Any] = {"brand": brand.registered, "skeleton": skel, "brand_skeleton": bskel}
    reasons: list[dict[str, Any]] = []

    def add(name: str, x: float, text: str) -> None:
        if x:
            reasons.append({"reason": text, "weight": round(WEIGHTS[name] * x, 2), "feature": name})

    perm = permutations(brand.registered).get(parts.registered) or permutations(brand.registered).get(parts.host)
    feats["permutation"] = perm
    if perm:
        add("permutation", 1, f"appears among the permutations generated for {brand.registered} ({perm.replace('-', ' ')})")
    if label == blabel and parts.suffix != brand.suffix:
        add("tld_swap", 1, f"the brand name \"{blabel}\" on another TLD (.{parts.suffix} instead of .{brand.suffix})")
    elif skel == bskel and label != blabel:
        add("skeleton_equal", 1, f"looks the same as \"{blabel}\" (homoglyphs, hyphens or rn→m) but is another domain")
    elif blabel in label and label != blabel:
        add("brand_in_label", 1, f"contains the brand \"{blabel}\" plus other words (combosquatting)")
    elif bskel in skel and len(bskel) >= 4:
        add("brand_in_skeleton", 1, f"contains the brand \"{blabel}\" written with deceptive characters")
    if parts.subdomain and bskel in skeleton(parts.subdomain).replace(".", "") and parts.registered != brand.registered:
        add("brand_in_subdomain", 1, f"the brand \"{blabel}\" sits in a subdomain; the real domain is {parts.registered}")
    dl = 1 - DamerauLevenshtein.normalized_distance(label, blabel)
    jw = JaroWinkler.normalized_similarity(label, blabel)
    feats.update({"sim_damerau_levenshtein": round(dl, 3), "sim_jaro_winkler": round(jw, 3)})
    if dl >= 0.75 and label != blabel:
        add("typo", (dl - 0.75) / 0.25, f"differs from \"{blabel}\" by very few characters (similarity {dl:.2f})")
    if jw >= 0.85 and label != blabel:
        add("jaro_winkler", (jw - 0.85) / 0.15, f"starts almost exactly like \"{blabel}\" (Jaro-Winkler {jw:.2f})")
    kws = _keywords(label, blabel)
    feats["keywords"] = kws
    if kws:
        add("keyword", min(len(kws), 3), "risk words: " + ", ".join(kws))
    hyphens = label.count("-")
    feats["hyphens"] = hyphens
    if hyphens:
        add("hyphen", min(hyphens, 3), f"{hyphens} hyphens" if hyphens > 1 else "a hyphen")
    if parts.is_idn:
        add("idn", 1, f"an IDN domain (punycode {parts.registered} = {parts.unicode_registered})")
    if parts.suffix in RISKY_TLDS:
        add("risky_tld", 1, f"the .{parts.suffix} TLD, common in phishing campaigns")
    if age_hours is not None:
        days = age_hours / 24
        if days < float(param("domain_age_red_days")):
            add("young_domain", 1, f"domain registered {en_count(round(age_hours), 'hour')} ago" if age_hours < 48
                else f"domain registered {en_count(int(round(days)), 'day')} ago")
        elif days < float(param("domain_age_yellow_days")):
            add("young_domain", 0.5, f"domain registered {en_count(int(round(days)), 'day')} ago")
    if cert_age_hours is not None and cert_age_hours < float(param("cert_age_red_hours")):
        add("young_cert", 1, f"first TLS certificate issued {en_count(round(cert_age_hours), 'hour')} ago")
    z = WEIGHTS["bias"] + sum(r["weight"] for r in reasons)
    return z, reasons, feats


def _logistic(z: float) -> float:
    """Funcția logistică, plafonată la [0,01; 0,99]: scorul e o euristică, nu o certitudine."""
    return min(0.99, max(0.01, 1 / (1 + math.exp(-z))))


def _fmt(score: float) -> str:
    return f"{score:.2f}"


def score_domain(domain: str, protected: list[str] | None = None, age_hours: float | None = None,
                 cert_age_hours: float | None = None) -> dict[str, Any]:
    """Calculul M3 fără ambalajul ToolResult (folosit și de alte module)."""
    parts = split_domain(domain)
    if parts is None:
        raise ValueError(f"invalid domain: {domain}")
    brands = [b for b in (split_domain(p) for p in (protected or param("protected_domains"))) if b]
    allow = {split_domain(a).registered for a in param("allowlist_domains") if split_domain(a)}
    base = {"domain": parts.host, "unicode_domain": parts.unicode_host, "registered": parts.registered,
            "protected": [b.registered for b in brands], "weights": WEIGHTS}
    own = next((b for b in brands if b.registered == parts.registered), None)
    if own is not None or parts.registered in allow:
        name = own.registered if own else parts.registered
        return {**base, "score": 0.01, "closest_brand": name, "legit": True, "permutation_match": None,
                "explanations": [{"reason": f"is the protected domain {name} itself (or one of its subdomains)",
                                  "weight": None, "feature": "protected"}], "features": {}}
    best: tuple[float, list[dict[str, Any]], dict[str, Any]] | None = None
    per_brand: dict[str, float] = {}
    for brand in brands:
        z, reasons, feats = _features(parts, brand, age_hours, cert_age_hours)
        per_brand[brand.registered] = round(_logistic(z), 4)
        if best is None or z > best[0]:
            best = (z, reasons, feats)
    if best is None:
        z, reasons, feats = WEIGHTS["bias"], [], {"brand": None}
    else:
        z, reasons, feats = best
    score = round(_logistic(z), 4)
    perm = feats.get("permutation")
    return {
        **base,
        "score": score,
        "z": round(z, 3),
        "legit": False,
        "closest_brand": feats.get("brand"),
        "permutation_match": {"brand": feats.get("brand"), "fuzzer": perm} if perm else None,
        "explanations": sorted(reasons, key=lambda r: -(r["weight"] or 0)),
        "features": feats,
        "brand_scores": per_brand,
    }


@tool("lookalike_score", group="domain-intel")
def lookalike_score(domain: str, protected: list[str] | None = None, age_hours: float | None = None,
                    cert_age_hours: float | None = None) -> ToolResult:
    """M3: scorul 0–1 că domeniul imită un domeniu protejat (permutări dnstwist, schelet TR39, distanțe, vârstă), cu explicații."""
    started = time.perf_counter()
    args: dict[str, Any] = {"domain": domain}
    if protected:
        args["protected"] = protected
    try:
        data = score_domain(domain, protected, age_hours, cert_age_hours)
    except ValueError as exc:
        return failure("lookalike_score", args, f"Invalid domain: {domain}.", error=str(exc))
    args["domain"] = data["registered"] if data.get("legit") else data["domain"]
    score, brand = data["score"], data.get("closest_brand")
    if data["legit"]:
        summary, signal = f"{data['domain']} is the protected domain {brand} (or a subdomain of it): not a lookalike.", "verde"
    else:
        top = [r["reason"] for r in data["explanations"][:3]]
        reason = "; ".join(top) if top else "no resemblance to the protected domains"
        summary = f"Lookalike score {_fmt(score)} against {brand}: {reason}."
        kws = data["features"].get("keywords", [])
        if score < float(param("lookalike_yellow")) and len(kws) >= 2:
            summary = (f"It does not directly imitate a protected domain (score {_fmt(score)}), but it has risk words: "
                       f"{', '.join(kws)}.")
        if score >= float(param("lookalike_red")):
            signal = "rosu"
        elif score >= float(param("lookalike_yellow")) or len(kws) >= 2:
            signal = "galben"
        elif score < 0.2:
            signal = "verde"
        else:
            signal = "neutru"
    return ToolResult(tool="lookalike_score", args=args, ok=True, data=data, summary=summary, signal=signal,
                      mode="offline", latency_ms=int((time.perf_counter() - started) * 1000))
