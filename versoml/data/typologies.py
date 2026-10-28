"""Tipologiile de fraudă din `typologies_ro.yaml` (cercetare), folosite de generator.

Fiecare tipologie se mapează pe un constructor existent (`maps_to_scenario`), deci pe aceeași rută de reguli:
nu adăugăm valori noi în `contracts.Scenario` (o escrocherie cu investiții și una romantică ajung amândouă la
„plată autorizată sub manipulare”, ca `cont_sigur`; diferența e în poveste, nu în regim sau în rută).

`typology_corpus()` produce reclamații din frazele `complaint_cues_en` / `complaint_cues_ro` ale fiecărei
tipologii (2–3 indicii + fraza despre bani potrivită clasei PSD2), cu aceleași grupuri de variante ca restul
corpusului (`complaints_ro.pick`). Numele de mărci din textul de cercetare se înlocuiesc (`corpus_llm.scrub`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from versoml.data import ids
from versoml.data.complaints import SCENARIO_LABELS, add_typos, fmt_amount
from versoml.data.complaints_ro import pick
from versoml.data.text import fmt_lei, normalize_ro, strip_diacritics

TYPOLOGIES_YAML = Path(__file__).resolve().parent / "typologies_ro.yaml"

MONEY = {
    "en": {"authorized_push_payment": ["In the end I sent {suma} myself, from the app.",
                                       "I transferred {suma} because I believed them.",
                                       "Altogether I paid {suma} before I realised it was a scam."],
           "unauthorized": ["Then {suma} left my account and I did not approve it.",
                            "After that someone took {suma} from my account without my consent.",
                            "I never authorised the {suma} payment that followed."],
           "not_fraud": ["I paid {suma} and the problem is still not solved.", "It is about {suma}.",
                         "The amount is {suma} and I want it corrected."]},
    "ro": {"authorized_push_payment": ["Până la urmă am trimis eu {suma}, din aplicație.",
                                       "Am transferat {suma} pentru că i-am crezut.",
                                       "În total am plătit {suma} până mi-am dat seama că e o țeapă."],
           "unauthorized": ["Apoi au plecat din cont {suma} și nu am aprobat eu.",
                            "După asta cineva mi-a luat {suma} din cont fără acordul meu.",
                            "Nu am autorizat niciodată plata de {suma} care a urmat."],
           "not_fraud": ["Am plătit {suma} și problema tot nu e rezolvată.", "E vorba de {suma}.",
                         "Suma este {suma} și vreau să fie corectată."]},
}
ASK = {"en": ["Please help me get the money back.", "What can you do?", "I want my money back.", "Please check urgently."],
       "ro": ["Vă rog să mă ajutați să recuperez banii.", "Ce puteți face?", "Vreau banii înapoi.", "Va rog verificati urgent"]}


@lru_cache(maxsize=2)
def load_typologies(path: str | None = None) -> tuple[dict, ...]:
    """Tipologiile valide (cu `maps_to_scenario` cunoscut); tuplu gol dacă fișierul lipsește."""
    p = Path(path) if path else TYPOLOGIES_YAML
    if not p.exists():
        return ()
    import yaml

    from versoml.data.corpus_llm import scrub

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for t in data.get("typologies") or []:
        if not (isinstance(t, dict) and t.get("id") and t.get("maps_to_scenario") in SCENARIO_LABELS):
            continue
        t = dict(t)
        t["complaint_cues_en"] = [scrub(c, "en")[0] for c in t.get("complaint_cues_en") or []]
        t["complaint_cues_ro"] = [scrub(c, "ro")[0] for c in t.get("complaint_cues_ro") or []]
        out.append(t)
    return tuple(out)


def typology_corpus(n_per_typology: int = 24, seed: int = 7, *, language: str = "en", group: int | None = None,
                    typo_boost: float = 0.0) -> list[dict]:
    """Reclamații etichetate pentru M1, câte `n_per_typology` pe tipologie (aceeași formă ca `generate_corpus`)."""
    rng = ids.sub_rng("typology-corpus", seed, language, group)
    rows = []
    for t in load_typologies():
        cues = t.get(f"complaint_cues_{language}") or []
        if len(cues) < 2:
            continue
        sc = t["maps_to_scenario"]
        cls = t.get("psd2_class") if t.get("psd2_class") in MONEY["en"] else "unauthorized"
        ch, dt = SCENARIO_LABELS[sc]
        for _ in range(n_per_typology):
            k = min(len(cues), rng.choice([2, 2, 3]))
            first = pick(rng, cues, group)
            rest = [c for c in cues if c != first]
            chosen = [first] + rng.sample(rest, k - 1)
            amount = round(rng.choice([rng.uniform(80, 900), rng.uniform(900, 6000), rng.uniform(6000, 40000)]), 2)
            suma = fmt_lei(amount, rng.randrange(5)) if language == "ro" else fmt_amount(amount, rng.randrange(5))
            parts = chosen + [str(pick(rng, MONEY[language][cls], group)).replace("{suma}", suma)]
            if rng.random() < 0.6:
                parts.append(str(pick(rng, ASK[language], group)))
            text = " ".join(parts)
            if language == "ro" and rng.random() < 0.5:
                text = strip_diacritics(text)
            if rng.random() < 0.15:
                text = text.lower()
            text = normalize_ro(add_typos(text, rng, rng.choice([0.0, 0.02, 0.05]) + typo_boost))
            meta = {"attachments": [], "source": rng.choice(["app", "app", "email", "web_form", "call_center"])}
            if rng.random() < 0.5:
                meta["channel_hint"] = ch
            rows.append({"text": text, "attachments": [], "meta": meta, "channel": ch, "dispute_type": dt,
                         "scenario": sc, "underlying": None, "language": language, "group": group,
                         "source": "typology", "typology": t["id"]})
    return rows
