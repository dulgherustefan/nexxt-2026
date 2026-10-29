"""The letter check: forbidden terms (true positives), harmless phrases (no false blocks), canary, raw personal data.

A letter is in Romanian when the customer wrote in Romanian and in English otherwise, so every term is checked in both
languages, with or without diacritics.
"""

from __future__ import annotations

import pytest

from versoml.wall import check_letter, journal, register_classifier

FULL_NAME = "ONPCSB (full name)"
INVESTIGATION = "investigation of the payee or an account"
BLOCKED_AT_REQUEST = "blocked at the authorities' request"
REPORTED = "reported to the authorities"

BLOCKED_EN = [
    ("We have reported the payee's account to the FIU.", "FIU"),
    ("The account was reported to the Financial Intelligence Unit.", "financial intelligence unit"),
    ("The details went to the National Office for the Prevention and Control of Money Laundering.", FULL_NAME),
    ("Our colleagues told ONPCSB about the transfer.", "ONPCSB"),
    ("We filed a suspicious transaction report about the recipient.", "suspicious transaction report"),
    ("A suspicious activity report has been submitted.", "suspicious transaction report"),
    ("An STR has been submitted for this account.", "STR"),
    ("We filed a S.T.R. yesterday.", "STR"),
    ("A SAR is on file.", "SAR"),
    ("Our AML team is reviewing the payee.", "AML"),
    ("The case has been passed to our MLRO.", "MLRO"),
    ("The beneficiary is under investigation.", "under investigation"),
    ("The recipient's account is under surveillance.", "under investigation"),
    ("The payee is being investigated by the bank.", INVESTIGATION),
    ("We are investigating the recipient's account.", INVESTIGATION),
    ("The transfer was flagged by compliance.", "compliance review"),
    ("Our compliance team has the case.", "compliance review"),
    ("The recipient is suspected of money laundering.", "money laundering"),
    ("The money was laundered through several accounts.", "money laundering"),
    ("Under anti-money-laundering rules we cannot tell you more.", "money laundering"),
    ("This could involve terrorist financing.", "terrorist financing"),
    ("We are monitoring the payee's account.", "monitored account"),
    ("We are keeping an eye on that account.", "monitored account"),
    ("The funds were frozen at the request of the authorities.", BLOCKED_AT_REQUEST),
    ("The account was blocked by the police.", BLOCKED_AT_REQUEST),
    ("We have informed the competent authorities about this case.", REPORTED),
    ("The case has been referred to law enforcement.", REPORTED),
    ("The account belongs to a money mule.", "money mule"),
    ("The payment stays on hold until the review ends.", "HOLD"),
    ("The HOLD signal came in from the other team.", "HOLD"),
    ("Under Law 129/2019 we cannot share details.", "Law 129/2019"),
    ("This looks like a suspicious transaction.", "suspicious transaction"),
    ("There is suspicious activity on the recipient's account.", "suspicious transaction"),
    ("Our financial crime team has opened a case on the account holder.", "financial crime"),
    ("The payment was flagged and is being watched.", "flagged account or payment"),
    ("We've flagged the account of the beneficiary.", "flagged account or payment"),
    ("We are not allowed to tip you off.", "tipping-off"),
    ("We suspect the payee.", "suspicion"),
]

BLOCKED_RO = [
    ("Contul beneficiarului a fost raportat la ONPCSB.", "ONPCSB"),
    ("Am transmis informațiile către O.N.P.C.S.B.", "ONPCSB"),
    ("Datele au ajuns la Oficiul Național de Prevenire și Combatere a Spălării Banilor.", FULL_NAME),
    ("Există o suspiciune de spălare a banilor.", "money laundering"),
    ("posibila spalare de bani", "money laundering"),
    ("SPĂLAREA BANILOR este analizată", "money laundering"),
    ("A fost întocmit un raport de tranzacție suspectă.", "suspicious transaction report"),
    ("Rapoartele privind tranzacțiile suspecte au fost trimise.", "suspicious transaction report"),
    ("Am depus un RTS pentru acest cont.", "RTS"),
    ("Tranzacția a fost semnalată ca suspectă.", "suspicious transaction"),
    ("Operațiunile din contul destinatar sunt suspecte.", "suspicious transaction"),
    ("Investigăm în prezent contul beneficiarului.", INVESTIGATION),
    ("Contul beneficiarului este investigat.", INVESTIGATION),
    ("Banca a deschis o anchetă privind titularul contului.", INVESTIGATION),
    ("Clientul pare suspect.", "suspicion"),
    ("Avem suspiciuni privind această plată.", "suspicion"),
    ("Echipa AML analizează cazul.", "AML"),
    ("Conform politicii anti-money laundering a băncii", "money laundering"),
    ("Contul destinatar este monitorizat.", "monitored account"),
    ("Monitorizăm contul beneficiarului.", "monitored account"),
    ("Un analist AML a preluat cazul.", "AML"),
    ("Am identificat o pistă nouă.", "investigation lead"),
    ("Suma a fost blocată la cererea autorităților.", BLOCKED_AT_REQUEST),
    ("Fondurile sunt reținute la solicitarea procurorului.", BLOCKED_AT_REQUEST),
    ("Cazul a fost raportat autorităților competente pentru verificări.", REPORTED),
    ("Suspiciunea a fost comunicată autorității, conform art. 173.", REPORTED),
    ("Plata rămâne pe hold până la analiză.", "HOLD"),
    ("Conform Legii nr. 129/2019, nu vă putem oferi detalii.", "Law 129/2019"),
    ("Contul aparține unui cărăuș.", "money mule"),
    ("Tranzac\u0163ia este suspectă.", "suspicious transaction"),   # cedilla on the way in
    # the Romanian forms of the terms that used to be English only
    ("Datele au ajuns la Unitatea de Informații Financiare.", "financial intelligence unit"),
    ("Cazul a fost transmis către departamentul de conformitate.", "compliance review"),
    ("Echipa de conformitate analizează plata.", "compliance review"),
    ("Beneficiarul se află sub investigație.", "under investigation"),
    ("Contul este in curs de investigare.", "under investigation"),
    ("Titularul face obiectul unei anchete.", "under investigation"),
    ("Contul beneficiarului a fost marcat de bancă.", "flagged account or payment"),
    ("Am semnalat contul beneficiarului.", "flagged account or payment"),
    ("Titularul este pe lista neagră.", "flagged account or payment"),
    ("Echipa de criminalitate financiară are cazul.", "financial crime"),
    ("Avem interdicția de a vă informa despre analiză.", "tipping-off"),
    ("Nu avem voie să vă avertizăm.", "tipping-off"),
]

BENIGN_EN = [
    "We have refunded RON 3,200.00 to your account.",
    "Under Article 173 of Law 209/2019 and CJEU ruling C-70/25, we refunded you by the end of the next business day.",
    "Your card was blocked at your request and a new one is on its way.",
    "We have put a temporary block on your card at your request.",
    "If you get suspicious messages, do not open them. Call us instead.",
    "Do not open suspicious-looking links sent by text message.",
    "If you notice any suspicious transaction, tell us straight away.",
    "If you ever see a suspicious payment on your account, call us.",
    "If you suspect fraud, call us on +40 700 000 100.",
    "If anything looks suspicious, hang up and call the number on the back of your card.",
    "We recommend that you monitor your account in the Demo Bank app.",
    "You can keep an eye on your account in the app.",
    "We recommend that you report the incident to the police and to DNSC (1911).",
    "We have reported the fake page to DNSC.",
    "You can report it to the police as well.",
    "We looked into your claim about the payment to the account you mentioned.",
    "We have asked the bank that received the money to return it (camt.056 recall).",
    "If you disagree with our answer, you can complain to the National Authority for Consumer Protection (ANPC), the "
    "National Agency for Fiscal Administration (ANAF), the National Bank of Romania (BNR) or the Alternative Dispute "
    "Resolution Center in Banking (CSALB), or go to court.",
    "If you are not happy, you can report it to the National Authority for Consumer Protection.",
    "The payment was made on a fake site that copied the bank's page.",
    "Your case number is CT-2026-000123.",
    "The refund does not depend on the outcome of our review.",
    "The account the money went to is at another bank.",
    "Keep hold of any messages or receipts linked to this payment.",
    "We will hold your new card at the branch until you collect it.",
    "The account holder will receive a new card by post.",
    "This letter is in compliance with Law 209/2019.",
    "Our street address is 5 Str. Lalelelor, Bucharest.",
    "We refunded the payment you flagged to us.",
    "Thank you for reporting the payment so quickly.",
    "A Visa chargeback is under way.",
    "The payment was approved with strong customer authentication (SCA).",
    "Kind regards,\nDisputes team, Demo Bank",
]

BENIGN_RO = [
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
    "Răspunsul nostru este în conformitate cu Legea nr. 209/2019.",
    "Plata pe care ne-ați semnalat-o a fost rambursată.",
    "Ne-ați informat că nu ați autorizat plata și ați semnalat-o în termenul de 13 luni.",
    "Am analizat reclamația dumneavoastră, datele tranzacției și jurnalul de autentificare.",
    "Nu putem oferi informații despre conturile altor persoane, dar am ținut cont de ce ne-ați spus.",
    "Am cerut și băncii care a primit banii să îi returneze.",
    "Un coleg din echipa de contestații a verificat și a aprobat această decizie.",
    "Puteți sesiza și Poliția. Păstrați mesajele și chitanțele legate de această plată.",
]

REFUND_LETTER = """Dear <CLIENT_1>,

On 28 Oct 2026 you told us that you did not make the transfer of RON 3,200.00 earlier that day. We have refunded the
full amount to your account. Thank you for telling us so quickly.

Under Article 173 of Law 209/2019, we must refund a payment you did not authorize by the end of the next business day
after you report it. The payment was made from a new device two minutes after a link in a text message was opened.

Your card was blocked at your request, and a new one is on its way. We are also asking the bank that received the
money to return it, and we have reported the fake page to DNSC. You do not need to do anything for this. If you get
suspicious messages, do not open them, and keep an eye on your account in the app.

If you disagree with our answer, you can complain to the National Authority for Consumer Protection (ANPC), the
National Agency for Fiscal Administration (ANAF), the National Bank of Romania (BNR) or the Alternative Dispute
Resolution Center in Banking (CSALB), or go to court. If you have questions, call us on +40 700 000 100 or reply to
this email, quoting case CT-2026-000123.

Kind regards,
Disputes team, Demo Bank"""

REFUND_LETTER_RO = """Stimată doamnă <CLIENT_1>,

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


@pytest.mark.parametrize("text, label", BLOCKED_EN + BLOCKED_RO)
def test_forbidden_terms_are_blocked(text, label, registry):
    result = check_letter(text, registry=registry)
    assert not result.passed and label in result.blocked_terms, result.blocked_terms
    assert result.reasons and all(r.startswith("Forbidden term “") for r in result.reasons)


@pytest.mark.parametrize("text", BENIGN_EN + BENIGN_RO)
def test_benign_refund_phrases_pass(text, registry):
    result = check_letter(text, registry=registry)
    assert result.passed, (result.blocked_terms, result.pii_findings)


@pytest.mark.parametrize("letter", [REFUND_LETTER, REFUND_LETTER_RO])
def test_full_refund_letter_passes(letter, registry):
    result = check_letter(letter, registry=registry)
    assert result.passed and result.reasons == []


def test_reasons_quote_the_fragment_in_english(registry):
    [reason] = check_letter("The funds are on hold for now.", registry=registry).reasons
    assert reason.startswith("Forbidden term “HOLD”: it says money or an account is on hold")
    assert reason.endswith("in “The funds are on hold for now”.")


@pytest.mark.parametrize("text", [
    "Suma a fost rambursată. Ref. internă: {token} pentru RTS.",
    "The amount was refunded. Internal ref: {token} for the STR.",
])
def test_canary_blocks_without_echoing_aml_content(text, registry):
    token = registry.mint("LD-0042")
    result = check_letter(text.format(token=token.lower()), registry=registry)
    assert not result.passed and result.canaries_found == 1 and {"RTS", "STR"} & set(result.blocked_terms)
    assert all(token.lower() not in r and token not in r for r in result.reasons)
    assert any("1 canary token from the AML files" in r for r in result.reasons)


@pytest.mark.parametrize("text, kind", [
    ("Clientul cu CNP 6010315431239 a fost rambursat.", "CNP"),
    ("The customer with CNP 6010315431239 was refunded.", "CNP"),
    ("Card 4111 1111 1111 1111 was blocked at your request.", "CARD"),
    ("The money went to account RO49AAAA1B31007593840000.", "IBAN"),
])
def test_raw_pii_in_letter_blocks(text, kind, registry):
    result = check_letter(text, registry=registry)
    assert not result.passed and result.pii_findings and result.pii_findings[0].startswith(kind)
    assert "6010315431239" not in " ".join(result.pii_findings + result.reasons)


def test_classifier_hook_can_only_add_blocks(registry):
    flagged = check_letter("The amount was refunded.", registry=registry, classifier=lambda text: True)
    assert not flagged.passed and flagged.classifier_flag
    clean = check_letter("The amount was refunded.", registry=registry, classifier=lambda text: False)
    assert clean.passed
    still = check_letter("We reported the account to ONPCSB.", registry=registry, classifier=lambda text: False)
    assert not still.passed

    def broken(text: str) -> bool:
        raise TimeoutError("model unavailable")

    failed = check_letter("The amount was refunded.", registry=registry, classifier=broken)
    assert not failed.passed and failed.classifier_flag  # fail-closed
    assert "The classifier could not check the letter" in " ".join(failed.reasons)


def test_registered_default_classifier(registry):
    register_classifier(lambda text: "zone" in text)
    try:
        assert not check_letter("A message from zone X.", registry=registry).passed
        assert check_letter("The amount was refunded.", registry=registry).passed
    finally:
        register_classifier(None)


@pytest.mark.parametrize("text", [
    "Contul beneficiarului, cu soldul de 7.000 lei, a fost raportat la ONPCSB.",
    "The payee's account, with a balance of RON 7,000.00, was reported to ONPCSB.",
])
def test_blocks_are_journaled_without_letter_fragments(text, registry):
    check_letter(text, case_id="CT-2026-000123", registry=registry)
    [event] = journal.blocks(5)
    assert event["case_id"] == "CT-2026-000123" and event["terms"] == ["ONPCSB"]
    assert "7.000" not in " ".join(event["reasons"]) and "7,000" not in " ".join(event["reasons"])
    assert event["reasons"] == ["Forbidden term “ONPCSB”."]
