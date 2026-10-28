"""A small English ↔ Romanian glossary of domain terms, used to expand BM25 queries across languages.

The rule catalog is in English and docs/context is in Romanian, so a lexical query in one language misses
the other. Each pair below is a plain translation of a term that appears in the corpus; the query gets the
stems of the other side as extra BM25 terms. Dense retrieval does not need it; the offline path does.
"""

from __future__ import annotations

from functools import lru_cache

# (English terms, Romanian terms); several words per side are alternatives, not a phrase
PAIRS: tuple[tuple[str, str], ...] = (
    ("refund refunded reimburse", "rambursare rambursează rambursarea rambursa"),
    ("complaint complaints", "reclamație reclamații reclamația plângere"),
    ("unauthorized unauthorised", "neautorizată neautorizate neautorizat"),
    ("authorized authorised approved", "autorizată autorizat aprobată"),
    ("deadline deadlines", "termen termenul termene"),
    ("business working", "lucrătoare lucrătoare"),
    ("day days", "zi zile ziua zilei"),
    ("month months", "luni lună"),
    ("customer client cardholder", "client clientul clientului titular"),
    ("payer", "plătitor plătitorul plătitorului"),
    ("beneficiary payee", "beneficiar beneficiarul"),
    ("negligence negligent", "neglijență neglijent neglijentă"),
    ("gross grossly", "gravă grav"),
    ("fraud fraudulent", "fraudă fraudei fraudulos"),
    ("scam", "înșelătorie fraudă"),
    ("suspicion suspicious suspect", "suspiciune suspectă suspecte"),
    ("report reports reporting", "raport raportare raportul rapoartele"),
    ("transaction transactions", "tranzacție tranzacția tranzacții"),
    ("payment payments", "plată plata plăți plății"),
    ("police", "poliție poliția"),
    ("evidence proof prove", "probă probe dovadă dovedește"),
    ("burden", "sarcina"),
    ("liability liable bears", "răspundere răspunderea suportă"),
    ("loss losses", "pierdere pierderi pierderile"),
    ("stolen theft", "furat furt"),
    ("lost", "pierdut pierdută"),
    ("salary salaries wage income", "salariu salariile venit venitul"),
    ("garnish garnishment garnishments seizure", "poprire popriri popririi poprit"),
    ("bailiff enforcement", "executor executare"),
    ("died deceased death dead", "decedat decesul deces decedatului"),
    ("heir heirs inheritance", "moștenitor moștenitori succesiune"),
    ("attorney proxy mandate", "procură procura mandat"),
    ("prosecutor", "procuror procurorul"),
    ("authority authorities", "autoritate autorități autoritatea"),
    ("cash", "numerar"),
    ("threshold", "prag pragul"),
    ("hold held suspend suspension", "suspendare suspendarea execută blocare"),
    ("human person", "om omul uman"),
    ("automated automatic automatically", "automată automat automate"),
    ("decision decisions decides", "decizie decizia decizii decide"),
    ("loan credit", "credit creditul"),
    ("account accounts", "cont contul conturi"),
    ("blocked block frozen", "blocat blocată blocare blocheaza"),
    ("recall", "rechemare rechemarea"),
    ("dispute disputes disputed", "dispută disputa dispute contestată contestate"),
    ("settlement settled", "decontare decontarea decontate"),
    ("investigation investigations", "investigație investigații anchetă"),
    ("notify notified notice notification", "notificare notifică anunță"),
    ("answer reply response", "răspuns răspunsul răspunde"),
    ("instructions instruction", "instrucțiuni instrucțiune"),
    ("hidden", "ascuns ascunse"),
    ("cap limit", "plafon plafonul limită"),
    ("approval approve", "aprobare aprobarea aprobă"),
    ("authentication authenticated", "autentificare autentificarea autentificată"),
    ("dynamic", "dinamică"),
    ("order ranking priority", "ordinea rang rangurile prioritate"),
    ("concurrent competing", "concurente"),
    ("structure format", "structură structura format"),
    ("check control", "control verificare"),
    ("digit", "cifră cifra"),
    ("share percentage percent", "procent procentul"),
    ("error mistake mistakenly", "greșeală eroare"),
    ("manipulation manipulated", "manipulare"),
    ("receipt received", "primire primirea primită"),
    ("final", "final finală"),
    ("extension extended", "prelungire prelungirea"),
    ("mule mules", "cărăuș cărăuși"),
    ("tipping", "tipping"),
    ("analysis", "analiza analiză"),
    ("money funds", "bani banii fonduri"),
    ("data", "date datele"),
    ("bank", "banca bănci băncii"),
    ("document documents", "document documente"),
    ("information", "informații informațiile"),
    ("request requests", "cerere cereri cererea"),
)


@lru_cache(maxsize=1)
def expansions() -> dict[str, tuple[str, ...]]:
    """Stemmed token → stemmed tokens of the other language."""
    from versoml.knowledge.text import tokenize

    table: dict[str, set[str]] = {}
    for en, ro in PAIRS:
        en_t = {t for w in en.split() for t in tokenize(w)}
        ro_t = {t for w in ro.split() for t in tokenize(w)}
        for t in en_t:
            table.setdefault(t, set()).update(ro_t - en_t)
        for t in ro_t:
            table.setdefault(t, set()).update(en_t - ro_t)
    return {k: tuple(sorted(v)) for k, v in table.items() if v}


def expand(tokens: list[str]) -> list[str]:
    """The query tokens plus their translations (each added once)."""
    table = expansions()
    seen = set(tokens)
    extra: list[str] = []
    for t in tokens:
        for x in table.get(t, ()):
            if x not in seen:
                seen.add(x)
                extra.append(x)
    return tokens + extra
