"""Artefactele comune ale scenariilor: domenii, telefoane, firma-fantomă, exchange-ul sintetic.

Modulul OSINT folosește exact aceleași nume în fixture-urile lui, deci valorile de aici sunt contract.
Domeniile escrocilor sunt doar pe .example / .test (RFC 2606), telefoanele în intervalul fictiv +40700xxxxxx.
"""

from __future__ import annotations

from versoml.data import ids

# ---------------------------------------------------------------- domenii

LEGIT_BRAND_DOMAIN = "bancademo.example"          # Demo Bank (fictitious)
LEGIT_COURIER_DOMAIN = "curierdemo.example"       # Demo Courier (fictitious)

SCAM_DOMAIN_DEMO = "livrare-bancademo.example"    # demo_t1 (și campania „taxă de livrare")
SCAM_DOMAIN_CARD = "bancadem0-plati.test"         # phishing card / Visa Secure
SCAM_DOMAIN_INEL = "confirmare-colet-demo.example"  # inel_carausi
SCAM_DOMAIN_VISHING = "securitate-bancademo.test"   # pagina de „verificare" din vishing

DEMO_SMS_TEXT = ("Your parcel could not be delivered. Confirm your address and pay the RON 2.99 delivery fee: "
                 "https://livrare-bancademo.example/colet/RO4471")
DEMO_URL = "https://livrare-bancademo.example/colet/RO4471"

# ---------------------------------------------------------------- telefoane

SCAM_PHONE_SECURITATE = "+40700000111"   # vishing „departamentul de securitate"
SCAM_PHONE_CONT_SIGUR = "+40700000222"   # „mută banii într-un cont sigur"
BANK_OFFICIAL_PHONE = "+40700000100"     # Demo Bank's (fictitious) helpline, the legitimate reference

# ---------------------------------------------------------------- firme

SHELL_COMPANY_NAME = "EXPRES LIVRARE DEMO SRL"
SHELL_COMPANY_CUI = ids.make_invalid_cui("4471202")      # cifră de control greșită în mod deliberat

CRYPTO_EXCHANGE_NAME = "CryptoX Exchange (synthetic)"
CRYPTO_EXCHANGE_CUI = ids.make_invalid_cui("3901777")
CRYPTO_EXCHANGE_IBAN = ids.make_iban("ZBNK", "9000000000777000")

CASH_NODE = "NUMERAR"                    # nod tehnic: retrageri și depuneri de numerar

BANK_NAME = "Demo Bank"
BANK_CODE = ids.OWN_BANK


def _onrc(body13: str) -> str:
    return body13 + str(ids.onrc_check_digit(body13))


SHELL_COMPANY_ONRC = _onrc("J202600447100")   # înregistrată în 2026 (JJ = 00); cifra ONRC e neoficială

SHARED_ARTIFACTS: dict = {
    "legit_domains": [LEGIT_BRAND_DOMAIN, LEGIT_COURIER_DOMAIN],
    "scam_domains": {
        "demo_t1": SCAM_DOMAIN_DEMO,
        "card_visa_secure": SCAM_DOMAIN_CARD,
        "inel_carausi": SCAM_DOMAIN_INEL,
        "vishing_securitate": SCAM_DOMAIN_VISHING,
    },
    "scam_phones": {
        "vishing_securitate": SCAM_PHONE_SECURITATE,
        "cont_sigur": SCAM_PHONE_CONT_SIGUR,
    },
    "shell_company": {"name": SHELL_COMPANY_NAME, "cui": SHELL_COMPANY_CUI, "onrc": SHELL_COMPANY_ONRC},
    "crypto_exchange": {"name": CRYPTO_EXCHANGE_NAME, "cui": CRYPTO_EXCHANGE_CUI, "iban": CRYPTO_EXCHANGE_IBAN},
    "demo_sms": DEMO_SMS_TEXT,
    "demo_url": DEMO_URL,
}
