"""Filtrul scrisorilor: termeni interziși (adevărat pozitive), formulări benigne (fals pozitive), canary, PII."""

from __future__ import annotations

import pytest

from versoml.wall import check_letter, journal, register_classifier

BLOCKED = [
    ("Contul beneficiarului a fost raportat la ONPCSB.", "ONPCSB"),
    ("Am transmis informațiile către O.N.P.C.S.B.", "ONPCSB"),
    ("Datele au ajuns la Oficiul Național de Prevenire și Combatere a Spălării Banilor.",
     "Oficiul Național de Prevenire și Combatere a Spălării Banilor"),
    ("Există o suspiciune de spălare a banilor.", "spălare de bani"),
    ("posibila spalare de bani", "spălare de bani"),
    ("SPĂLAREA BANILOR este analizată", "spălare de bani"),
    ("A fost întocmit un raport de tranzacție suspectă.", "raport de tranzacție suspectă"),
    ("Rapoartele privind tranzacțiile suspecte au fost trimise.", "raport de tranzacție suspectă"),
    ("Am depus un RTS pentru acest cont.", "RTS"),
    ("Tranzacția a fost semnalată ca suspectă.", "tranzacție suspectă"),
    ("Operațiunile din contul destinatar sunt suspecte.", "tranzacție suspectă"),
    ("Investigăm în prezent contul beneficiarului.", "investigație privind beneficiarul sau contul"),
    ("Contul beneficiarului este investigat.", "investigație privind beneficiarul sau contul"),
    ("Banca a deschis o anchetă privind titularul contului.", "investigație privind beneficiarul sau contul"),
    ("Clientul pare suspect.", "suspect / suspiciune"),
    ("Avem suspiciuni privind această plată.", "suspect / suspiciune"),
    ("Echipa AML analizează cazul.", "AML"),
    ("Conform politicii anti-money laundering a băncii", "money laundering"),
    ("Contul destinatar este monitorizat.", "cont monitorizat"),
    ("Monitorizăm contul beneficiarului.", "cont monitorizat"),
    ("Un analist AML a preluat cazul.", "AML"),
    ("Am identificat o pistă nouă.", "pistă"),
    ("Suma a fost blocată la cererea autorităților.", "blocat la cererea autorităților"),
    ("Fondurile sunt reținute la solicitarea procurorului.", "blocat la cererea autorităților"),
    ("Cazul a fost raportat autorităților competente pentru verificări.", "raportat autorităților competente"),
    ("Suspiciunea a fost comunicată autorității, conform art. 173.", "raportat autorităților competente"),
    ("Plata rămâne pe hold până la analiză.", "hold"),
    ("Conform Legii nr. 129/2019, nu vă putem oferi detalii.", "Legea 129/2019"),
    ("Contul aparține unui cărăuș.", "cărăuș (money mule)"),
    ("Tranzac\u0163ia este suspectă.", "tranzacție suspectă"),   # cedilă la intrare
]

BENIGN = [
    "Vă informăm că suma de 3.200,00 lei a fost rambursată în contul dumneavoastră.",
    "Conform art. 173 din Legea nr. 209/2019 și hotărârii CJUE C-70/25, rambursarea s-a făcut la T+1.",
    "Cardul dumneavoastră a fost blocat la cererea dumneavoastră și a fost emis un card nou.",
    "Suspendarea cardului la cererea dumneavoastră a fost înregistrată.",
    "Dacă primiți mesaje suspecte, nu le deschideți și sunați-ne.",
    "Nu accesați linkuri suspecte primite prin SMS.",
    "Dacă observați orice tranzacție suspectă, anunțați-ne imediat.",
    "Vă recomandăm să vă monitorizați contul în aplicația Banca Demo.",
    "Monitorizați-vă contul și raportați-ne orice plată neautorizată.",
    "Puteți monitoriza contul din aplicație.",
    "Vă recomandăm să raportați incidentul la Poliție și la DNSC (1911).",
    "Am raportat pagina falsă către DNSC.",
    "Am investigat contestația dumneavoastră privind plata către contul indicat.",
    "Am inițiat rechemarea transferului (camt.056) către banca beneficiarului.",
    "Vă puteți adresa CSALB, ANPC sau BNR dacă nu sunteți mulțumit de răspuns.",
    "Tranzacția a fost efectuată pe un site fraudulos care imita pagina băncii.",
    "Numărul cazului dumneavoastră este CT-2026-000123.",
    "Suma rambursată nu este condiționată de rezultatul analizei.",
    "Contul în care au ajuns banii aparține unei alte bănci.",
    "Vă mulțumim pentru răbdare. Cu stimă, Banca Demo",
    "Strada Exemplului nr. 10, București. Str. Lalelelor nr. 5.",
    "Contul dumneavoastră RO49 **** **** 0000 a fost creditat. Pentru întrebări: 021 123 4567, ajutor@bancademo.example.",
]

REFUND_LETTER = """Stimată doamnă <CLIENT_1>,

Ca urmare a contestației dumneavoastră din 28.10.2026 privind plata de 3.200,00 lei, vă informăm că am
rambursat integral suma în contul dumneavoastră, în termenul prevăzut de art. 173 din Legea nr. 209/2019,
așa cum a fost interpretat prin hotărârea CJUE C-70/25.

Plata a fost inițiată de pe un dispozitiv nou, la două minute după accesarea unui link primit prin SMS.
Pentru siguranța dumneavoastră, cardul a fost blocat la cererea dumneavoastră și veți primi unul nou.
Am inițiat rechemarea transferului către banca beneficiarului și am raportat pagina falsă către DNSC.

Dacă primiți mesaje suspecte, nu le deschideți. Vă recomandăm să vă monitorizați contul în aplicație.
Dacă nu sunteți mulțumit de acest răspuns, vă puteți adresa CSALB sau Autorității Naționale pentru
Protecția Consumatorilor, în termen de 30 de zile.

Cu stimă,
Echipa de contestații, Banca Demo"""


@pytest.mark.parametrize("text, label", BLOCKED)
def test_forbidden_terms_are_blocked(text, label, registry):
    result = check_letter(text, registry=registry)
    assert not result.passed and label in result.blocked_terms, result.blocked_terms
    assert result.reasons and all(r for r in result.reasons)


@pytest.mark.parametrize("text", BENIGN)
def test_benign_refund_phrases_pass(text, registry):
    result = check_letter(text, registry=registry)
    assert result.passed, (result.blocked_terms, result.pii_findings)


def test_full_refund_letter_passes(registry):
    result = check_letter(REFUND_LETTER, registry=registry)
    assert result.passed and result.reasons == []


def test_canary_blocks_without_echoing_aml_content(registry):
    token = registry.mint("LD-0042")
    result = check_letter(f"Suma a fost rambursată. Ref. internă: {token.lower()} pentru RTS.", registry=registry)
    assert not result.passed and result.canaries_found == 1 and "RTS" in result.blocked_terms
    assert all(token.lower() not in r and token not in r for r in result.reasons)


@pytest.mark.parametrize("text, kind", [
    ("Clientul cu CNP 6010315431239 a fost rambursat.", "CNP"),
    ("Cardul 4111 1111 1111 1111 a fost blocat la cererea dumneavoastră.", "CARD"),
    ("Banii au plecat în contul RO49AAAA1B31007593840000.", "IBAN"),
])
def test_raw_pii_in_letter_blocks(text, kind, registry):
    result = check_letter(text, registry=registry)
    assert not result.passed and result.pii_findings and result.pii_findings[0].startswith(kind)
    assert "6010315431239" not in " ".join(result.pii_findings + result.reasons)


def test_classifier_hook_can_only_add_blocks(registry):
    flagged = check_letter("Suma a fost rambursată.", registry=registry, classifier=lambda text: True)
    assert not flagged.passed and flagged.classifier_flag
    clean = check_letter("Suma a fost rambursată.", registry=registry, classifier=lambda text: False)
    assert clean.passed
    still = check_letter("Am raportat contul la ONPCSB.", registry=registry, classifier=lambda text: False)
    assert not still.passed

    def broken(text: str) -> bool:
        raise TimeoutError("model indisponibil")

    failed = check_letter("Suma a fost rambursată.", registry=registry, classifier=broken)
    assert not failed.passed and failed.classifier_flag  # fail-closed


def test_registered_default_classifier(registry):
    register_classifier(lambda text: "zona" in text)
    try:
        assert not check_letter("Mesaj din zona X.", registry=registry).passed
        assert check_letter("Suma a fost rambursată.", registry=registry).passed
    finally:
        register_classifier(None)


def test_blocks_are_journaled_without_letter_fragments(registry):
    check_letter("Contul beneficiarului, cu soldul de 7.000 lei, a fost raportat la ONPCSB.", case_id="CT-2026-000123",
                 registry=registry)
    [event] = journal.blocks(5)
    assert event["case_id"] == "CT-2026-000123" and event["terms"] == ["ONPCSB"]
    assert "7.000" not in " ".join(event["reasons"])
