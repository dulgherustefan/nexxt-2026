# Date sintetice, formate și validatori pentru operațiuni bancare românești

_Document de context pentru echipa NEXXT Summit 2026, track Raiffeisen „AI for Operational Efficiency". Sursa unică este cercetarea echipei despre date sintetice, formate și tooling (stare la 28.10.2026), completată cu teste locale. Toate datele din document sunt **fictive**. Orice valoare cu checksum valid poate coincide întâmplător cu un identificator real, așa că etichetați tot setul ca SINTETIC și nu asociați vectorii de test cu persoane sau firme reale._

**Legendă etichete**

- **[OFICIAL]**: format stabilit printr-o normă sau un standard citat în note.
- **[ȘABLON BANCĂ]**: șablon public al unei bănci, nu model național.
- **[RECONSTRUIT]**: listă de câmpuri dedusă; nu s-a găsit un model oficial.
- **[NEVERIFICAT]**: afirmație neconfirmată într-o sursă primară (marcaj păstrat din note).
- **[NEOFICIAL]**: algoritm folosit în practică, dar nepublicat de emitent.
- **[PRESUPUNERE]**: alegere de demo documentată aici, fără sursă.
- **[TESTAT]**: cod rulat local (Python 3.14.5; doar stdlib, plus Jinja2 la §5.3); toate aserțiunile trec.

Pe Windows rulați cu `python -X utf8 fisier.py`, pentru că mesajele conțin diacritice.

---

## 1. Rezumat

- Identificatorii românești de bază se generează și se validează offline cu sume de control simple: CNP (ponderi `279146358279`, mod 11, rest 10 → 1), CUI/CIF (ponderi `753217532`, ×10 mod 11 mod 10), IBAN RO (24 de caractere, mod 97), număr ONRC (vechi `J40/1234/2005`, nou `YAAAAXXXXXXJJC` din 26.07.2024). Codul din §2 e [TESTAT] pe vectorii din note, inclusiv pe doctest-urile python-stdnum.
- Cifra de control a numărului ONRC nou **nu e publicată oficial**. Validatorul de mai jos dă avertisment, nu eroare.
- MRZ: CI vechi = TD2 (2×36), CEI = TD1 (3×30, fără adresă tipărită), pașaport = TD3 (2×44). Algoritmul 7-3-1 și cele trei machete au fost verificate local pe specimenele ICAO. Ce conține MRZ-ul românesc în câmpurile opționale (CNP sau nu) rămâne [NEVERIFICAT].
- Puține documente au model național. Formate stabilite de stat: e-Factura (UBL 2.1 + CIUS-RO), poprirea ANAF pe conturi (electronică din 1.10.2023), formularele ONRC și chitanța 14-4-1. Pentru adeverința de venit există șablonul public Libra Internet Bank (2024). Procura, certificatul de moștenitor și poprirea prin executor sunt [RECONSTRUIT].
- Fișiere bancare: MT940 pentru extrase (ERP-urile românești încă îl importă), camt.053 ca direcție ISO 20022, pain.001.001.09 pentru plăți domestice SENT/ReGIS. Chei de reconciliere: EndToEndId, AcctSvcrRef, BkTxCd, RmtInf (respectiv :61: și :86: în MT940). Clearing-ul de card e proprietar (Mastercard IPM, Visa BASE II), deci în demo folosiți o schemă CSV simplificată.
- Nu există pe Hugging Face niciun dataset bancar sau de documente financiare în limba română. Luați comportamentul tranzacțional din AMLworld/PaySim și intențiile din banking77, iar stratul românesc îl generați voi. Berka conține date **reale** anonimizate.
- Faker `ro_RO` produce checksum-uri valide, dar distribuții nerealiste: ~25% născuți în anii 1800, ~18% cu data nașterii în viitor, coduri de bancă formate din litere aleatorii. Folosiți-l doar pentru nume și adrese.
- Extragerea: LLM multimodal plus validatori determiniști. Normalizați diacriticele (ș/ț cu virgulă vs ş/ţ cu sedilă) înainte de orice comparație.

### Start rapid

```bash
pip install python-stdnum schwifty faker jinja2 pydantic   # validare de referință, IBAN, nume/adrese, șabloane, scheme
pip install weasyprint            # sau: pip install playwright && playwright install chromium
pip install pymupdf augraphy opencv-python                  # PDF -> PNG (PyMuPDF e alegerea noastră, neevaluată în note) + zgomot
pip install anafpy                # opțional: client e-Factura ANAF
pip install langgraph      # sau pydantic-ai / openai-agents (vezi §8)
```

Ordinea în care merită scrise generatoarele:

1. `ro_ids.py` și `mrz.py` (§2): copiați blocurile și rulați testele, durează 5 minute.
2. `synth.py` (§5.2): un „caz" coerent cu client, act de identitate cu MRZ, cont RZBR, angajator, adeverință și extras, plus ground truth în JSON.
3. Un singur registru de tranzacții exportat ca MT940, camt.053 și pain.001 (§4).
4. Șabloane HTML (adeverință, poprire, extras) → PDF → zgomot de scanare (§5.3).
5. Anomalii plantate și harness de evaluare (§5.4).

---

## 2. Identificatori

Cele patru blocuri `ro_ids.py` (§2.1–2.4) sunt independente. Le puteți rula separat sau le puteți concatena, în ordine, într-un singur fișier `ro_ids.py`, cum presupune `synth.py` (§5.2). MRZ-ul are fișierul lui, `mrz.py` (§2.5). Testele rulează cu `python -X utf8 ro_ids.py` și `python -X utf8 mrz.py`.

### 2.1 CNP (cod numeric personal)

Structura are 13 cifre: `S AA LL ZZ JJ NNN C`.

| Componentă | Semnificație | Valori |
|---|---|---|
| S | sex și secol | 1/2 = M/F născuți 1900–1999; 3/4 = 1800–1899; 5/6 = 2000–2099; 7/8 = rezidenți străini M/F. Valoarea 9 apare doar în python-stdnum („alt străin", aparent doar NIF) |
| AA LL ZZ | data nașterii | an pe 2 cifre, luna 01–12, zi validă pentru lună |
| JJ | județul sau sectorul nașterii/înregistrării | 01–39 județe, 40 București, 41–46 sectoarele 1–6, 51 Călărași, 52 Giurgiu. Rare: 47/48 (sectoarele 7/8, desființate), 70 (orice înregistrare, după intrarea în funcțiune a SII), 80–83 (doar python-stdnum, „Unknown"; un furnizor KYC mapează 80 la „Outside_Romania") |
| NNN | număr de ordine | 001–999 |
| C | cifra de control | vezi mai jos |

**Algoritm:** înmulțiți primele 12 cifre cu cifrele corespunzătoare din `279146358279` și adunați. Restul împărțirii la 11 este C; dacă restul e 10, C = 1. Sursa python-stdnum notează că algoritmul „nu a fost confirmat de o sursă independentă", dar coincide cu Wikipedia RO. Pentru S = 7/8/9 secolul nu se poate deduce: python-stdnum presupune 1900, deci o dată de 29 februarie din anii 2000 poate fi respinsă greșit. Actul normativ care definește S = 9 și codurile 70/80–83 nu a fost găsit.

```python
# fișier: ro_ids.py  (partea 1/4: CNP) -- doar stdlib, Python >= 3.10
from datetime import date

CNP_PONDERI = "279146358279"
JUDETE_CNP = {
    1: "Alba", 2: "Arad", 3: "Argeș", 4: "Bacău", 5: "Bihor", 6: "Bistrița-Năsăud",
    7: "Botoșani", 8: "Brașov", 9: "Brăila", 10: "Buzău", 11: "Caraș-Severin",
    12: "Cluj", 13: "Constanța", 14: "Covasna", 15: "Dâmbovița", 16: "Dolj",
    17: "Galați", 18: "Gorj", 19: "Harghita", 20: "Hunedoara", 21: "Ialomița",
    22: "Iași", 23: "Ilfov", 24: "Maramureș", 25: "Mehedinți", 26: "Mureș",
    27: "Neamț", 28: "Olt", 29: "Prahova", 30: "Satu Mare", 31: "Sălaj", 32: "Sibiu",
    33: "Suceava", 34: "Teleorman", 35: "Timiș", 36: "Tulcea", 37: "Vaslui",
    38: "Vâlcea", 39: "Vrancea", 40: "București", 41: "București S1",
    42: "București S2", 43: "București S3", 44: "București S4", 45: "București S5",
    46: "București S6", 51: "Călărași", 52: "Giurgiu",
}
# acceptate doar cu permite_rare=True (cazuri-limită / python-stdnum)
JUDETE_CNP_RARE = {47: "București S7 (desființat)", 48: "București S8 (desființat)",
                   70: "orice înregistrare (SII)", 80: "necunoscut", 81: "necunoscut",
                   82: "necunoscut", 83: "necunoscut"}
SECOL_CNP = {"1": 1900, "2": 1900, "3": 1800, "4": 1800, "5": 2000, "6": 2000}
COD_S = {(1900, "M"): 1, (1900, "F"): 2, (1800, "M"): 3, (1800, "F"): 4,
         (2000, "M"): 5, (2000, "F"): 6}


def cnp_cifra_control(primele12: str) -> int:
    r = sum(int(a) * int(b) for a, b in zip(primele12, CNP_PONDERI)) % 11
    return 1 if r == 10 else r


def valideaza_cnp(cnp: str, *, permite_rare: bool = False,
                  azi: date | None = None) -> list[str]:
    """Lista de erori; listă goală = CNP valid."""
    if len(cnp) != 13 or not cnp.isdigit():
        return ["format: sunt necesare exact 13 cifre"]
    erori = []
    s = cnp[0]
    if s == "0" or (s == "9" and not permite_rare):
        erori.append(f"S={s} nepermis")
    jj = int(cnp[7:9])
    if jj not in JUDETE_CNP and not (permite_rare and jj in JUDETE_CNP_RARE):
        erori.append(f"cod județ JJ={jj:02d} nepermis")
    if cnp[9:12] == "000":
        erori.append("NNN=000 (interval 001-999)")
    an = SECOL_CNP.get(s, 1900) + int(cnp[1:3])  # 7/8/9: secol necunoscut -> 1900 (ca stdnum)
    try:
        dn = date(an, int(cnp[3:5]), int(cnp[5:7]))
        if dn > (azi or date.today()):
            erori.append("data nașterii este în viitor")
    except ValueError:
        erori.append("data nașterii inexistentă")
    if cnp_cifra_control(cnp[:12]) != int(cnp[12]):
        erori.append("cifra de control greșită")
    return erori


def parseaza_cnp(cnp: str) -> dict:
    s = cnp[0]
    an = SECOL_CNP.get(s, 1900) + int(cnp[1:3])
    return {"sex": "M" if int(s) % 2 else "F",
            "data_nasterii": f"{an}-{cnp[3:5]}-{cnp[5:7]}",
            "rezident_strain": s in "78",
            "judet": JUDETE_CNP.get(int(cnp[7:9])) or JUDETE_CNP_RARE.get(int(cnp[7:9])),
            "nnn": cnp[9:12]}


def genereaza_cnp(data_nasterii: date, sex: str, judet: int, nnn: int) -> str:
    """CNP fictiv valid pentru o persoană născută 1800-2099 (S = 1..6)."""
    s = COD_S[(data_nasterii.year // 100 * 100, sex)]
    corp = f"{s}{data_nasterii:%y%m%d}{judet:02d}{nnn:03d}"
    return corp + str(cnp_cifra_control(corp))


if __name__ == "__main__":
    for ok in ["1630615123457", "6010315431239", "1900101401091"]:
        assert valideaza_cnp(ok) == [], ok
    assert genereaza_cnp(date(2001, 3, 15), "F", 43, 123) == "6010315431239"
    assert genereaza_cnp(date(1990, 1, 1), "M", 40, 109) == "1900101401091"  # rest 10 -> 1
    assert valideaza_cnp("1630615123458") == ["cifra de control greșită"]
    assert valideaza_cnp("1631315123457") == ["data nașterii inexistentă"]
    assert valideaza_cnp("1630615473457") == ["cod județ JJ=47 nepermis"]
    assert valideaza_cnp("1630615473457", permite_rare=True) == []
    assert valideaza_cnp("9630615123451") == ["S=9 nepermis"]
    assert valideaza_cnp("5990101123458") == ["data nașterii este în viitor"]
    assert valideaza_cnp("163061512345") == ["format: sunt necesare exact 13 cifre"]
    assert parseaza_cnp("6010315431239")["judet"] == "București S3"
    print("CNP OK")
```

| CNP (fictiv) | Rezultat | Observație |
|---|---|---|
| `1630615123457` | valid | doctest python-stdnum; suma 216, restul 7 |
| `6010315431239` | valid | F, 15.03.2001, București S3, NNN 123; suma 141, restul 9 |
| `1900101401091` | valid | suma 175, restul 10 → C = 1 (testează regula 10→1) |
| `1630615123458` | invalid | cifra de control |
| `1631315123457` | invalid | luna 13 (cifra de control e corectă) |
| `1630615473457` | invalid strict, valid cu `permite_rare` | JJ = 47 (sector desființat) |
| `9630615123451` | invalid strict | S = 9 |
| `5990101123458` | invalid | născut în 2099 |
| `163061512345` | invalid | 12 cifre |

### 2.2 CUI / CIF

CUI este codul firmelor obligate să se înregistreze la Registrul Comerțului, iar CIF este același tip de număr pentru entitățile fără această obligație; în practică termenii se folosesc interschimbabil. Prefixul „RO" arată înregistrarea în scopuri de TVA, informație care nu reiese din număr.

**Algoritm** (python-stdnum): eliminați „RO". Ultima cifră este cifra de control. Completați restul cu zerouri la stânga până la 9 cifre, înmulțiți cu `7,5,3,2,1,7,5,3,2`, apoi calculați suma × 10 mod 11 mod 10 (restul 10 devine 0). Lungimea validă este 2–10 cifre, fără 0 la început.

```python
# fișier: ro_ids.py  (partea 2/4: CUI/CIF)
import random

CUI_PONDERI = "753217532"


def cui_cifra_control(corp: str) -> int:
    """corp = cifrele fără cifra de control (max. 9)."""
    return sum(int(a) * int(b) for a, b in zip(corp.zfill(9), CUI_PONDERI)) * 10 % 11 % 10


def normalizeaza_cui(valoare: str) -> tuple[str, bool]:
    """('18547290', True) pentru 'RO 185 472 90'; al doilea element = prefix RO (TVA)."""
    v = valoare.upper().replace(" ", "").replace("-", "").replace(".", "")
    return (v[2:], True) if v.startswith("RO") else (v, False)


def valideaza_cui(valoare: str) -> list[str]:
    cui, _ = normalizeaza_cui(valoare)
    if not cui.isdigit():
        return ["format: doar cifre (după eliminarea prefixului RO)"]
    if not 2 <= len(cui) <= 10:
        return ["lungime în afara intervalului 2-10"]
    if cui[0] == "0":
        return ["începe cu 0"]
    if cui_cifra_control(cui[:-1]) != int(cui[-1]):
        return ["cifra de control greșită"]
    return []


def genereaza_cui(rng: random.Random, lungime: int = 8, cu_ro: bool = False) -> str:
    corp = str(rng.randint(1, 9)) + "".join(rng.choice("0123456789") for _ in range(lungime - 2))
    cui = corp + str(cui_cifra_control(corp))
    return "RO" + cui if cu_ro else cui


if __name__ == "__main__":
    for ok in ["18547290", "RO 185 472 90", "12345674", "RO12345674"]:
        assert valideaza_cui(ok) == [], ok
    assert valideaza_cui("18547291") == ["cifra de control greșită"]
    assert valideaza_cui("01234567") == ["începe cu 0"]
    assert valideaza_cui("1") == ["lungime în afara intervalului 2-10"]
    assert valideaza_cui("RO1854729A") == ["format: doar cifre (după eliminarea prefixului RO)"]
    r = random.Random(7)
    assert all(valideaza_cui(genereaza_cui(r, n)) == [] for n in range(2, 11) for _ in range(200))
    print("CUI OK")
```

| Valoare | Rezultat | Observație |
|---|---|---|
| `18547290` | valid | doctest python-stdnum (folosiți-l doar ca vector de test) |
| `RO 185 472 90` | valid | prefix și spații acceptate |
| `12345674` | valid | 001234567 × 753217532 = 95; 950 mod 11 = 4 |
| `18547291` | invalid | cifra de control |
| `01234567` | invalid | începe cu 0 |
| `1` | invalid | lungime |
| `RO1854729A` | invalid | caracter nenumeric |

### 2.3 IBAN RO

**Structură:** 24 de caractere, `RO kk bbbb cccc cccc cccc cccc` (BBAN 4a,16c). `kk` sunt cifrele de control, `bbbb` primele patru litere din BIC-ul băncii, iar cele 16 caractere alfanumerice conțin sucursala și contul, în format specific fiecărei bănci. Structura internă a conturilor Raiffeisen nu e publică.

**Validare** (ISO 13616, mod 97): verificați lungimea, mutați primele 4 caractere la final, înlocuiți literele cu numere (A=10 … Z=35); numărul obținut mod 97 trebuie să fie 1. **Generare:** puneți „00" în locul cifrelor de control, rearanjați și convertiți la fel; cifrele de control sunt 98 − (n mod 97), completate la 2 cifre.

| Cod bancă | Bancă | Sursă | Statut |
|---|---|---|---|
| RZBR | Raiffeisen Bank | Slash | confirmat de o sursă secundară |
| BTRL | Banca Transilvania | Slash | idem |
| BRDE | BRD | Slash | idem |
| RNCB | BCR | folositor.ro | idem |
| INGB | ING | folositor.ro | idem |
| BREL | Revolut după financer.ro; în note apare și amintirea (neverificată) că BRELROBU e BIC-ul Libra Internet Bank | — | **[NEVERIFICAT, disputat]** |
| NBOR, ABNA, BUCU, ARBL, MIND, BPOS, CARP, BROM, BITR, BRMA, DAFB, MIRB, CECE, CITI, CRCO, FNNB, EGNA, BSEA, EXIM, UGBI, HVBL, CRDZ, BNRB, PIRB, PORL, MIRO, RZBL, ROIN, WBAN, TRFD, TREZ, BACX, VBBU, DARO | fără denumire în sursă | lista Faker `bank/ro_RO` (40 de coduri în total) | **[NEVERIFICAT]** |

Lista oficială (Regulamentul BNR privind IBAN, Anexa 1) nu a putut fi citită. Exemplele de mai jos folosesc TREZ pentru contul de Trezorerie, presupunând că TREZ e codul Trezoreriei **[PRESUPUNERE]**. schwifty poate genera IBAN-uri aleatorii valide și poate căuta BIC-ul după codul băncii, dar acoperirea pentru România nu a fost verificată.

```python
# fișier: ro_ids.py  (partea 3/4: IBAN RO)
import random
import re

# coduri confirmate de cel puțin o sursă secundară din note
BANCI_RO_CONFIRMATE = {"RZBR": "Raiffeisen Bank", "BTRL": "Banca Transilvania",
                       "BRDE": "BRD", "RNCB": "BCR", "INGB": "ING"}
# prezente doar în lista Faker ro_RO; denumirea băncii NEVERIFICATĂ (BREL: disputat)
BANCI_RO_FAKER_NEVERIFICATE = (
    "NBOR ABNA BUCU ARBL MIND BPOS CARP BROM BITR BRMA DAFB MIRB CECE CITI CRCO FNNB "
    "EGNA BSEA EXIM UGBI HVBL BREL CRDZ BNRB PIRB PORL MIRO RZBL ROIN WBAN TRFD TREZ "
    "BACX VBBU DARO").split()


def _numeric(s: str) -> int:
    return int("".join(str(int(c, 36)) for c in s))  # cifre -> 0-9, A=10 ... Z=35


def iban_cifre_control(tara: str, bban: str) -> str:
    return f"{98 - _numeric((bban + tara + '00').upper()) % 97:02d}"


def valideaza_iban_ro(iban: str) -> list[str]:
    s = iban.replace(" ", "").upper()
    if not re.fullmatch(r"RO\d{2}[A-Z]{4}[0-9A-Z]{16}", s):
        return ["format: RO + 2 cifre + 4 litere (cod bancă) + 16 alfanumerice = 24"]
    if _numeric(s[4:] + s[:4]) % 97 != 1:
        return ["cifre de control (mod 97) greșite"]
    return []


def avertismente_iban_ro(iban: str) -> list[str]:
    cod = iban.replace(" ", "").upper()[4:8]
    if cod in BANCI_RO_CONFIRMATE:
        return []
    if cod in BANCI_RO_FAKER_NEVERIFICATE:
        return [f"cod bancă {cod}: doar în lista Faker, denumire neverificată"]
    return [f"cod bancă {cod} necunoscut"]


def genereaza_iban_ro(rng: random.Random, banca: str = "RZBR", cont: str | None = None) -> str:
    cont = (cont or "".join(rng.choice("0123456789") for _ in range(16))).upper()
    assert len(cont) == 16 and len(banca) == 4
    return "RO" + iban_cifre_control("RO", banca + cont) + banca + cont


def formateaza_iban(iban: str) -> str:
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


if __name__ == "__main__":
    assert valideaza_iban_ro("RO54RZBR0000060012345678") == []
    assert valideaza_iban_ro("RO54 RZBR 0000 0600 1234 5678") == []
    assert valideaza_iban_ro("RO49AAAA1B31007593840000") == []        # cont cu litere
    assert genereaza_iban_ro(random.Random(), "RZBR", "0000060012345678") == "RO54RZBR0000060012345678"
    assert valideaza_iban_ro("RO55RZBR0000060012345678") == ["cifre de control (mod 97) greșite"]
    assert valideaza_iban_ro("RO54RZBR000006001234567")[0].startswith("format")
    assert avertismente_iban_ro("RO49AAAA1B31007593840000") == ["cod bancă AAAA necunoscut"]
    r = random.Random(1)
    assert all(valideaza_iban_ro(genereaza_iban_ro(r, b)) == []
               for b in list(BANCI_RO_CONFIRMATE) * 100)
    print("IBAN OK")
```

| IBAN (fictiv) | Rezultat | Observație |
|---|---|---|
| `RO54RZBR0000060012345678` | valid | exemplul din note; contul de 16 cifre e arbitrar |
| `RO54 RZBR 0000 0600 1234 5678` | valid | forma tipărită, în grupe de 4 |
| `RO49AAAA1B31007593840000` | valid mod 97, cu avertisment „cod bancă necunoscut" | cont alfanumeric |
| `RO55RZBR0000060012345678` | invalid | mod 97 |
| `RO54RZBR000006001234567` | invalid | 23 de caractere |

### 2.4 Număr de ordine ONRC

**Formatul vechi** `YJJ/XXXX/AAAA` (ex. `J40/1234/2005`) se citește registru / județ / număr / an. python-stdnum acceptă număr de cel mult 5 cifre, județ pe 1–2 cifre și an între 1990 și 2024.

**Formatul nou** `YAAAAXXXXXXJJC` (14 caractere) e în vigoare de la 26.07.2024, când a pornit noul sistem informatic ONRC:

| Poziție | Conținut |
|---|---|
| Y | registrul: J = persoane juridice; F = PFA, întreprinderi individuale și familiale; C = societăți cooperative |
| AAAA | anul înregistrării |
| XXXXXX | număr de ordine pe 6 cifre, numărat separat pentru fiecare registru |
| JJ | „00" pentru entitățile înregistrate după 26.07.2024; pentru cele mai vechi, codul județului ultimului sediu înregistrat |
| C | cifră de control „dintr-un algoritm" nedescris de sursă |

Numărul se alocă o singură dată, la nivel național, și se păstrează toată viața entității, indiferent de mutările sediului. Entitățile vechi primesc numărul nou când înregistrează schimbări de denumire, sediu, activitate principală sau formă juridică. Reguli python-stdnum pentru JJ: dacă anul < 2024, JJ ∈ {1–40, 51, 52}; în 2024, JJ e un județ sau 00; după 2024, JJ = 00.

**Cifra de control [NEOFICIAL]:** litera se înlocuiește cu `ord(literă) % 10` (J→4, F→0, C→7), se adună toate cifrele fără ultima, iar rezultatul mod 10 este C. Algoritmul vine din python-stdnum, care trimite la un articol de blog (targetare.ro). Baza legală a noului format (posibil Legea 265/2022) nu e confirmată. Validați cu avertisment, nu cu eroare.

```python
# fișier: ro_ids.py  (partea 4/4: număr de ordine ONRC)
import random
import re
from datetime import date

JUDETE_ONRC = set(range(1, 41)) | {51, 52}


def onrc_cifra_control(primele13: str) -> int:
    """NEOFICIAL: algoritmul din python-stdnum (sursa: blog targetare.ro)."""
    return sum(int(c) for c in str(ord(primele13[0]) % 10) + primele13[1:]) % 10


def valideaza_onrc(nr: str, azi: date | None = None) -> tuple[list[str], list[str]]:
    """Întoarce (erori, avertismente). Cifra de control produce doar avertisment."""
    s = nr.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([JFC])(\d{1,2})/(\d{1,5})/(\d{4})", s)          # vechi: J40/1234/2005
    if m:
        erori = [] if int(m[2]) in JUDETE_ONRC else ["județ invalid"]
        if not 1990 <= int(m[4]) <= 2024:
            erori.append("an în afara intervalului 1990-2024")
        return erori, []
    m = re.fullmatch(r"([JFC])(\d{4})(\d{6})(\d{2})(\d)", s)             # nou: YAAAAXXXXXXJJC
    if not m:
        return ["format necunoscut (nici vechi, nici nou)"], []
    an, jj, erori = int(m[2]), int(m[4]), []
    if an > (azi or date.today()).year:
        erori.append("an în viitor")
    if an < 2024 and jj not in JUDETE_ONRC:
        erori.append("JJ trebuie să fie cod de județ (an < 2024)")
    elif an == 2024 and jj not in JUDETE_ONRC | {0}:
        erori.append("JJ trebuie să fie cod de județ sau 00 (an 2024)")
    elif an > 2024 and jj != 0:
        erori.append("JJ trebuie să fie 00 (an > 2024)")
    avert = [] if onrc_cifra_control(s[:13]) == int(s[13]) else \
        ["cifra de control nu corespunde algoritmului neoficial"]
    return erori, avert


def genereaza_onrc_nou(rng: random.Random, an: int, registru: str = "J",
                       nr_ordine: int | None = None, judet: int = 0) -> str:
    corp = f"{registru}{an:04d}{nr_ordine or rng.randint(1, 999999):06d}{judet:02d}"
    return corp + str(onrc_cifra_control(corp))


def genereaza_onrc_vechi(rng: random.Random, judet: int, an: int, registru: str = "J") -> str:
    return f"{registru}{judet:02d}/{rng.randint(1, 29999)}/{an}"


if __name__ == "__main__":
    assert valideaza_onrc("J40/1234/2005") == ([], [])
    for ok in ["J2012000750528", "J2005001234405", "J2025000123009", "F2025004521001"]:
        assert valideaza_onrc(ok) == ([], []), ok
    assert genereaza_onrc_nou(random.Random(), 2005, nr_ordine=1234, judet=40) == "J2005001234405"
    assert genereaza_onrc_nou(random.Random(), 2025, nr_ordine=123) == "J2025000123009"
    assert valideaza_onrc("J2012000750529") == ([], ["cifra de control nu corespunde algoritmului neoficial"])
    assert valideaza_onrc("J40/1234/2025")[0] == ["an în afara intervalului 1990-2024"]
    assert valideaza_onrc("X40/1234/2005")[0] == ["format necunoscut (nici vechi, nici nou)"]
    assert valideaza_onrc("J2025000123403") == (["JJ trebuie să fie 00 (an > 2024)"], [])
    print("ONRC OK")
```

| Număr (fictiv) | Rezultat | Observație |
|---|---|---|
| `J40/1234/2005` | valid | format vechi |
| `J2012000750528` | valid | doctest python-stdnum |
| `J2005001234405` | valid | conversie ilustrativă a `J40/1234/2005`, cu numărul vechi devenit XXXXXX și JJ = județul **[PRESUPUNERE]** |
| `J2025000123009` | valid | înmatriculare 2025, nr. 123, JJ = 00 |
| `F2025004521001` | valid | registrul F (PFA/II/IF) |
| `J2012000750529` | doar avertisment | cifra de control (în stdnum: InvalidChecksum) |
| `J40/1234/2025` | invalid | format vechi folosit după 2024 |
| `J2025000123403` | invalid | JJ ≠ 00 după 2024 |
| `X40/1234/2005` | invalid | registru necunoscut |

### 2.5 MRZ: CI (TD2), CEI (TD1), pașaport (TD3)

**Ce spun sursele despre acte**

- **CI vechi:** serie din 2 litere plus un număr unic pentru fiecare card; CNP (același pe toate cardurile unei persoane); nume, prenume, sex și cetățenie (care a înlocuit numele părinților în 2009); adresă (pe formatul ID-2); emitent, de regulă „SPCLEP" urmat de localitate; date de emitere și expirare în format zz/ll/aaaa; două rânduri MRZ.
- **Serii CI:** București DP, DR, DT, RD, RR, RT, RX, RK (MB pe CEI); Alba AX (AB pe CEI); Cluj KX, CJ; Constanța KT, KZ; Arad AR, ZR; Teleorman TR; Iași MX, MZ, IZ (IS pe CEI). Seria nu corespunde întotdeauna prescurtării județului.
- **Valabilitate CI (ID-2):** 4 ani pentru 14–17 ani; 7 ani pentru 18–24; 10 ani sau până la 3.08.2031 pentru 25–54 (dacă a fost emisă după 2.08.2021); fără termen la 55+, dar după 3.08.2031 nu mai poate fi folosită pentru călătorii.
- **CEI:** pilot la Cluj-Napoca din 2.08.2021, în tot județul Cluj din august 2022, extindere națională graduală din 20.03.2025 (altă sursă: toată țara din mai 2025). Adresa **nu e tipărită**, ci stocată electronic. Seria e tipărită cu caractere mici pe verso și gravată în dreapta fotografiei (relevant pentru OCR). Cipul suportă 11 servicii digitale și poate produce semnătură electronică. Cartea e document de călătorie UE. Valabilitate: 2 ani pentru primul card al copiilor, 4 ani între 2 și 14 ani, 5 ani între 14 și 18, 10 ani peste 18. Instituțiile fără cititor de cip cer dovadă separată de domiciliu (de ex. certificatul de atestare a domiciliului).
- **CIS (carte de identitate simplă):** emisă din 20.05.2025, fără cip, cu adresa tipărită, nu e document de călătorie, costă 39 lei. Formatul ei MRZ nu e cunoscut.
- **Pașaport:** furnizorul KYC Druid extrage, între altele, DocumentNumber (în exemplu, 9 cifre), PlaceOfBirth, **CNP** și MRZ pe 2 rânduri.
- **Validări KYC:** furnizorii folosesc TD1 pentru CEI, TD2 pentru CI și TD3 pentru pașaport. Pe CI și pașaport compară data nașterii și „ultimele 6 cifre ale CNP" între CNP și MRZ; pe CEI aceste verificări „întorc mereu N/A".

**Cifra de control ICAO 9303:** ponderi 7, 3, 1 repetate. Cifrele își păstrează valoarea, A–Z valorează 10–35, iar `<` valorează 0. Rezultatul este suma mod 10. Verificare: `L898902C3` → 6, `740812` → 2.

| Format | Rând | Conținut (pozițiile numerotate de la 1) |
|---|---|---|
| TD2 (CI), 2×36 | 1 | cod document 2 (`ID`) · stat 3 (`ROU`) · `NUME<<PRENUME` pe 31 de caractere |
| | 2 | nr. document 9 (serie + 6 cifre + `<`) · control · cetățenie · data nașterii AALLZZ · control · sex · data expirării · control · opțional 7 · control compus (peste pozițiile 1–10, 14–20, 22–35) |
| TD1 (CEI), 3×30 | 1 | cod document 2 · stat 3 · nr. document 9 · control · opțional 15 |
| | 2 | data nașterii · control · sex · data expirării · control · cetățenie 3 · opțional 11 · control compus (peste r1 6–30, r2 1–7, 9–15, 19–29) |
| | 3 | `NUME<<PRENUME` pe 30 de caractere |
| TD3 (pașaport), 2×44 | 1 | `P<` · stat 3 · `NUME<<PRENUME` pe 39 de caractere |
| | 2 | nr. document 9 · control · cetățenie · data nașterii · control · sex · data expirării · control · număr personal 14 · control · control compus (peste 1–10, 14–20, 22–43) |

**Particularități românești**

- **TD2, câmpul opțional (7 caractere) [NEVERIFICAT]:** probabil S + ultimele 6 cifre ale CNP. E o inferență din faptul că furnizorii compară „ultimele 6 cifre". Dacă se confirmă, CNP-ul se poate reconstrui ca S + data nașterii + ultimele 6 și compara cu cel tipărit. Confirmați pe un specimen PRADO.
- **TD1 (CEI) [PRESUPUNERE]:** MRZ-ul nu conține CNP (de aici N/A-ul furnizorilor). CNP-ul se citește prin OCR de pe față, adresa din cip sau din dovada de domiciliu. Codul de document `ID`, formatul numărului (serie + 7 cifre) și CAN-ul (prezență, poziție) sunt neconfirmate.
- **TD3 [PRESUPUNERE]:** CNP-ul e pus în câmpul „număr personal".
- **Rândul 1 al TD2** începe cu `IDROU` (cod `ID` + stat `ROU`). Prefixul apare și în exemplul pachetului `mmltech/cnp-decoder`.
- **Transliterare simplificată:** majuscule fără diacritice (ș/ş → S, ț/ţ → T, ă/â → A, î → I), cratimele și spațiile devin `<`, numele lungi se trunchiază fără regulile ICAO de prescurtare.

```python
# fișier: mrz.py -- ICAO 9303: cifră de control 7-3-1, TD1 (CEI), TD2 (CI vechi), TD3 (pașaport)
import re
import unicodedata


def mrz_cifra_control(s: str) -> int:
    val = lambda c: 0 if c == "<" else int(c) if c.isdigit() else ord(c) - 55  # A=10..Z=35
    return sum(val(c) * (7, 3, 1)[i % 3] for i, c in enumerate(s)) % 10


def camp(valoare: str, lungime: int) -> str:
    """Majuscule fără diacritice (ș/ş/ț/ţ/ă/â/î -> s/t/a/a/i), restul -> '<', completare cu '<'."""
    v = unicodedata.normalize("NFD", valoare.upper())
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = re.sub(r"[^A-Z0-9<]", "<", v)
    return v[:lungime].ljust(lungime, "<")       # trunchiere simplificată


def _cd(s: str) -> str:
    return str(mrz_cifra_control(s))


def mrz_td3(stat, nume, prenume, nr_doc, cetatenie, dn, sex, de, nr_personal=""):
    """Pașaport, 2 x 44. dn/de = YYMMDD."""
    l1 = "P<" + stat + camp(f"{nume}<<{prenume}", 39)
    doc, pn = camp(nr_doc, 9), camp(nr_personal, 14)
    l2 = doc + _cd(doc) + cetatenie + dn + _cd(dn) + sex + de + _cd(de) + pn + _cd(pn)
    return [l1, l2 + _cd(l2[0:10] + l2[13:20] + l2[21:43])]


def mrz_td2(cod, stat, nume, prenume, nr_doc, cetatenie, dn, sex, de, optional=""):
    """Carte de identitate format TD2, 2 x 36."""
    l1 = camp(cod, 2) + stat + camp(f"{nume}<<{prenume}", 31)
    doc = camp(nr_doc, 9)
    l2 = doc + _cd(doc) + cetatenie + dn + _cd(dn) + sex + de + _cd(de) + camp(optional, 7)
    return [l1, l2 + _cd(l2[0:10] + l2[13:20] + l2[21:35])]


def mrz_td1(cod, stat, nr_doc, dn, sex, de, cetatenie, nume, prenume, opt1="", opt2=""):
    """Card format TD1, 3 x 30."""
    doc = camp(nr_doc, 9)
    l1 = camp(cod, 2) + stat + doc + _cd(doc) + camp(opt1, 15)
    l2 = dn + _cd(dn) + sex + de + _cd(de) + cetatenie + camp(opt2, 11)
    l2 += _cd(l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29])
    return [l1, l2, camp(f"{nume}<<{prenume}", 30)]


def parseaza_mrz(linii: list[str]) -> tuple[dict, list[str]]:
    """Detectează TD1/TD2/TD3, extrage câmpurile și verifică toate cifrele de control."""
    lung = [len(x) for x in linii]
    if any(not re.fullmatch(r"[A-Z0-9<]+", x) for x in linii):
        return {}, ["caractere în afara setului A-Z 0-9 <"]
    if lung == [30, 30, 30]:
        l1, l2, l3 = linii
        f = {"format": "TD1", "nr_doc": l1[5:14], "dn": l2[0:6], "sex": l2[7],
             "de": l2[8:14], "cetatenie": l2[15:18], "optional": l1[15:30] + l2[18:29],
             "nume": l3}
        verif = [(l1[5:14], l1[14]), (l2[0:6], l2[6]), (l2[8:14], l2[14]),
                 (l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29], l2[29])]
    elif lung in ([36, 36], [44, 44]):
        l1, l2 = linii
        n = lung[0]
        f = {"format": "TD2" if n == 36 else "TD3", "nr_doc": l2[0:9], "cetatenie": l2[10:13],
             "dn": l2[13:19], "sex": l2[20], "de": l2[21:27], "optional": l2[28:n - 1],
             "nume": l1[5:]}
        verif = [(l2[0:9], l2[9]), (l2[13:19], l2[19]), (l2[21:27], l2[27]),
                 (l2[0:10] + l2[13:20] + l2[21:n - 1], l2[n - 1])]
        if n == 44:
            f["optional"] = l2[28:42]
            verif.insert(3, (l2[28:42], l2[42]))
    else:
        return {}, [f"lungimi neașteptate {lung}"]
    nume = ["document", "data nașterii", "data expirării", "personal", "compus"]
    if len(verif) == 4:
        nume.remove("personal")
    erori = [f"cifra de control {n} greșită" for (s, c), n in zip(verif, nume)
             if not (c == "<" and set(s) == {"<"}) and _cd(s) != c]
    return f, erori


def verifica_mrz_cu_cnp(f: dict, cnp: str) -> list[str]:
    """Verificări încrucișate MRZ <-> CNP (stil furnizori KYC)."""
    erori = []
    if f["dn"] != cnp[1:7]:
        erori.append("data nașterii MRZ != CNP")
    if f["sex"] != ("M" if int(cnp[0]) % 2 else "F"):
        erori.append("sexul MRZ != CNP")
    if f["format"] != "TD1" and cnp[-6:] not in f["optional"]:   # pe CEI: N/A
        erori.append("ultimele 6 cifre CNP lipsesc din MRZ")
    return erori


if __name__ == "__main__":
    assert mrz_cifra_control("L898902C3") == 6 and mrz_cifra_control("740812") == 2
    # specimene ICAO 9303 (stat fictiv UTO), reproduse din memorie, verificate prin cifrele lor
    td3 = ["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
           "L898902C36UTO7408122F1204159ZE184226B<<<<<10"]
    td2 = ["I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<", "D231458907UTO7408122F1204159<<<<<<<6"]
    td1 = ["I<UTOD231458907<<<<<<<<<<<<<<<", "7408122F1204159UTO<<<<<<<<<<<6",
           "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"]
    for spec in (td1, td2, td3):
        assert parseaza_mrz(spec)[1] == [], spec
    assert mrz_td3("UTO", "Eriksson", "Anna Maria", "L898902C3", "UTO", "740812", "F",
                   "120415", "ZE184226B") == td3
    assert mrz_td2("I", "UTO", "Eriksson", "Anna Maria", "D23145890", "UTO", "740812",
                   "F", "120415") == td2
    assert mrz_td1("I", "UTO", "D23145890", "740812", "F", "120415", "UTO",
                   "Eriksson", "Anna Maria") == td1
    # CI românesc fictiv (TD2): optional = S + ultimele 6 cifre CNP (PRESUPUNERE neverificată)
    cnp = "6010315431239"
    ci = mrz_td2("ID", "ROU", "Testescu", "Ana-Maria", "XT123456", "ROU", cnp[1:7], "F",
                 "320315", cnp[0] + cnp[-6:])
    f, err = parseaza_mrz(ci)
    assert err == [] and verifica_mrz_cu_cnp(f, cnp) == []
    assert ci[0] == "IDROUTESTESCU<<ANA<MARIA<<<<<<<<<<<<"
    stricat = [ci[0], ci[1][:9] + "0" + ci[1][10:]]
    assert "cifra de control document greșită" in parseaza_mrz(stricat)[1]
    assert camp("Ștefănescu-Țăranu", 20) == camp("Ştefănescu-Ţăranu", 20) == "STEFANESCU<TARANU<<<"
    # CEI fictiv (TD1), fără CNP în MRZ (presupunere); pașaport fictiv (TD3) cu CNP în câmpul personal
    cei = mrz_td1("ID", "ROU", "XT1234567", cnp[1:7], "F", "350315", "ROU", "Testescu", "Ana-Maria")
    assert parseaza_mrz(cei)[1] == [] and verifica_mrz_cu_cnp(parseaza_mrz(cei)[0], cnp) == []
    pas = mrz_td3("ROU", "Testescu", "Ana-Maria", "059912345", "ROU", cnp[1:7], "F", "310315", cnp)
    assert parseaza_mrz(pas)[1] == [] and verifica_mrz_cu_cnp(parseaza_mrz(pas)[0], cnp) == []
    print("\n".join(ci + cei + pas))
    print("MRZ OK")
```

| Vector (fictiv) | MRZ | Rezultat |
|---|---|---|
| Specimen ICAO TD3 (stat fictiv UTO) | `P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<` / `L898902C36UTO7408122F1204159ZE184226B<<<<<10` | valid |
| Specimen ICAO TD2 | `I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<` / `D231458907UTO7408122F1204159<<<<<<<6` | valid |
| Specimen ICAO TD1 | `I<UTOD231458907<<<<<<<<<<<<<<<` / `7408122F1204159UTO<<<<<<<<<<<6` / `ERIKSSON<<ANNA<MARIA<<<<<<<<<<` | valid |
| CI fictiv (TD2), CNP 6010315431239 | `IDROUTESTESCU<<ANA<MARIA<<<<<<<<<<<<` / `XT123456<9ROU0103152F320315664312398` | valid și concordant cu CNP-ul |
| CEI fictiv (TD1) | `IDROUXT12345676<<<<<<<<<<<<<<<` / `0103152F3503155ROU<<<<<<<<<<<8` / `TESTESCU<<ANA<MARIA<<<<<<<<<<<` | valid |
| Pașaport fictiv (TD3) | `P<ROUTESTESCU<<ANA<MARIA<<<<<<<<<<<<<<<<<<<<` / `0599123450ROU0103152F31031536010315431239<24` | valid |
| CI cu cifra de control a documentului alterată (`XT123456<0…`) | — | invalid: „cifra de control document greșită" |

Specimenele ICAO au fost reproduse din memorie, fără descărcarea Doc 9303. Local, toate cifrele lor de control, inclusiv cea compusă, se potrivesc cu implementarea, ceea ce confirmă machetele TD1/TD2/TD3.

---

## 3. Documente românești: scheme de câmpuri

Toate exemplele JSON folosesc aceeași distribuție fictivă, iar identificatorii lor trec validatorii din §2:

| Persoană / firmă | Identificatori (fictivi) |
|---|---|
| TESTESCU Ana-Maria | CNP 6010315431239, CI XT123456, IBAN RO47RZBR0000060098765432 |
| DEMOVICI Elena | CNP 2580722120774, IBAN RO49RZBR0000060077700003 |
| DEMOVICI Andrei | CNP 1830512123183 |
| PROBEANU Ioana | CNP 2850930324027 |
| FICTIVESCU Radu (decedat) | CNP 1410203222156, IBAN RO29RZBR0000060055501234 |
| EXEMPLU SOFTWARE DEMO SRL | CUI RO12345674, ONRC J2025000123009, IBAN RO54RZBR0000060012345678 |
| TESTARE LOGISTIC DEMO SRL | CUI 20433211, ONRC J2005001234405, IBAN RO53BTRL0000042000777001 |
| FURNIZOR EXEMPLU SRL | CUI 43890832, IBAN RO62BRDE0000007000123456 |

### 3.1 Adeverință de venit [ȘABLON BANCĂ]

Sursa este „Anexa 1 – Adeverinta de venit tip" a Libra Internet Bank (PDF de 2 pagini, datat 12.03.2024). Nu există model național: fiecare bancă își publică propriul șablon. Șablonul BT Direct a răspuns cu HTTP 403. Cel Porsche Finance are, după snippet, câte un rând pe lună pentru ultimele 6 luni, cu venitul net, venitul brut total și sporurile permanente separat. Adeverința fiscală ANAF (OANAF 3396/2016) e alt document, bazat pe evidența fiscală.

| Bloc | Câmpuri (în ordinea șablonului) | Verificare automată |
|---|---|---|
| Antet | denumirea completă a angajatorului, C.U.I., nr. de ordine în Registrul Comerțului (J…/…/…), tel./fax, persoana de contact și funcția ei | checksum CUI; format ONRC; concordanță cu certificatul constatator și cu e-Factura |
| Sediu, reprezentant | str., nr., bl., sc., et., ap., județ/sector; reprezentantul legal și calitatea lui | — |
| Angajat | nume, CNP; contract pe perioadă nedeterminată (de la data …) sau determinată (de la … până la …) | checksum CNP; CNP identic cu cel din CI |
| Funcție, studii | funcția ocupată conform COR; ultima școală absolvită, bifată: generală / liceu / universitate / post-universitare | — |
| Vechime | neîntreruptă la angajatorul anterior, întreruperea dintre locuri de muncă, vechimea totală | coerență cu data angajării |
| Rețineri | salariul e grevat de rețineri lunare DA/NU; suma lunară; motivul (CAR, rate, popriri, alte rețineri legale) | „DA" → escaladare și căutare de popriri |
| Tabel venit | anul anterior plus anul curent până la luna dinaintea emiterii (exemplul Libra are 16 luni). Coloane: Luna/An; Salariul de încadrare (brut, fără sporuri, conform CIM/Registrului general de evidență a salariaților); Salariul net aferent; Norma de hrană (net); Norma de echipament (net); Bonuri de masă; Alte bonusuri/sporuri nete permanente; Alte bonusuri/sporuri nete ocazionale | netul trebuie să corespundă creditelor salariale din extras |
| Final | notă: se completează salariul net, fără alte beneficii salariale; declarație de răspundere; societatea „se află / nu se află" în procedura insolvenței (Legea nr. 85/2014); funcția, numele și semnătura semnatarului, ștampila; adăugirile, ștersăturile și corecturile trebuie semnate și/sau ștampilate | „se află" → escaladare |

```json
{"tip_document": "adeverinta_venit", "data_emiterii": "2026-10-20", "nr_inregistrare": "1024/2026",
 "angajator": {"denumire": "TESTARE LOGISTIC DEMO SRL", "cui": "20433211", "nr_onrc": "J2005001234405",
   "sediu": "Bd. Testului nr. 10, București, Sector 3", "telefon": "0700 000 000",
   "persoana_contact": {"nume": "Probeanu Ioana", "functie": "Contabil-șef"},
   "reprezentant_legal": {"nume": "Demovici Andrei", "calitate": "Administrator"}},
 "angajat": {"nume": "Testescu Ana-Maria", "cnp": "6010315431239",
   "contract": {"durata": "nedeterminata", "de_la": "2023-02-01", "pana_la": null},
   "functie_cor": "Operator introducere date", "ultima_scoala": "universitate"},
 "vechime_luni": {"angajator_anterior": 14, "intrerupere": 1, "totala": 58},
 "retineri": {"grevat": "NU", "suma_lunara": 0, "motiv": null},
 "venituri": [
   {"luna": "2026-08", "salariu_incadrare": 6000, "salariu_net": 3510, "norma_hrana_net": 0,
    "norma_echipament_net": 0, "bonuri_masa": 400, "sporuri_permanente_net": 0, "sporuri_ocazionale_net": 0},
   {"luna": "2026-09", "salariu_incadrare": 6000, "salariu_net": 3510, "norma_hrana_net": 0,
    "norma_echipament_net": 0, "bonuri_masa": 400, "sporuri_permanente_net": 0, "sporuri_ocazionale_net": 250}],
 "insolventa": "nu se afla", "semnatar": {"functie": "Administrator", "nume": "Demovici Andrei"}}
```

### 3.2 Adresă de înființare a popririi: ANAF e-Popriri și executor judecătoresc [proces OFICIAL; câmpuri RECONSTRUIT]

**Ce e stabilit oficial.** Din 1.10.2023 se aplică OPANAF 878/2022, modificat prin OPANAF 626/2023, care reglementează transmiterea electronică a actelor de executare. Printr-un protocol între ANAF, Asociația Română a Băncilor (ARB) și bănci, actele ajung automat la bănci. Formularistica ANAF include „adresa de înființare a popririi asupra disponibilităților bănești" și „adresa de înștiințare privind înființarea popririi" (după un snippet de căutare). Raportul ANAF pe S1 2025 pomenește sistemul e-Popriri și 581.804 adrese de poprire asupra sumelor datorate debitorilor de terți. Cifra vine tot dintr-un snippet și poate include popriri în afara conturilor bancare.

**Fluxul la bancă** (din notificarea ProCredit privind protocolul):

1. În fiecare zi lucrătoare, la **15:30**, banca trimite „sold cert", adică suma de plătit din conturile debitorului, pentru fiecare poprire fiscală primită electronic.
2. După sold cert, suma blocată nu mai poate fi atinsă. Retragerile permise de art. 236(14) din Codul de procedură fiscală (salarii, accize, obligații care mențin valabilă o facilitate de plată) nu mai sunt aprobate.
3. În ziua lucrătoare următoare, ANAF trimite fiecărei bănci o **instrucțiune fermă de plată**, pe baza sold cert-ului ei. Banca o execută în aceeași zi. Doar ANAF decide care bancă plătește și cât.
4. Dacă ANAF nu cere plata, suma rămâne blocată până la o „instrucțiune de sistare a popririi".
5. Aceleași termene se aplică popririlor altor organe de executare aflate în concurs cu ANAF (art. 220(13) coroborat cu art. 236(11) CPF).

**Ce nu s-a obținut:** modelul oficial actual al adresei, schema XML a schimbului ANAF–bănci, procedura executorilor judecătorești și sumele exceptate de la poprire. Lista de câmpuri de mai jos e o inferență din note. În demo, serializați același obiect ca XML cu etichete proprii marcate DEMO (mesajul electronic) și ca PDF (adresa tipărită).

| Câmp | ANAF (e-Popriri) | Executor judecătoresc |
|---|---|---|
| emitent | unitate ANAF | birou de executor judecătoresc |
| nr./dată act, nr. dosar de executare | da | da |
| creditor | statul | creditorul din titlul executoriu **[RECONSTRUIT]** |
| debitor: nume, CNP/CUI | da (validați CNP/CUI) | da |
| suma datorată, moneda | da | da |
| cont de plată | cont de Trezorerie | contul indicat în adresă **[RECONSTRUIT]** |
| temei legal | CPF art. 236 | Codul de procedură civilă |
| canal | electronic (XML) plus PDF | PDF/hârtie **[RECONSTRUIT]** |

```json
{"tip_document": "adresa_infiintare_poprire", "canal": "e-Popriri",
 "emitent": {"tip": "ANAF", "unitate": "Unitate fiscală DEMO"},
 "nr_act": "EP-DEMO-000123", "data_act": "2026-10-20", "dosar_executare": "DE-DEMO-5551",
 "debitor": {"nume": "Demovici Elena", "cnp": "2580722120774"},
 "suma_datorata": 4250.00, "moneda": "RON",
 "cont_plata": {"iban": "RO56TREZ2654235116155940", "titular": "Trezorerie (fictiv)"},
 "temei_legal": "Codul de procedură fiscală, art. 236",
 "conturi_vizate": [{"iban": "RO49RZBR0000060077700003", "sold_disponibil": 3120.45}],
 "evenimente": [
   {"tip": "primire_act", "moment": "2026-10-21T09:12:00"},
   {"tip": "sold_cert", "moment": "2026-10-21T15:30:00", "suma": 3120.45},
   {"tip": "instructiune_ferma_plata", "moment": "2026-10-22T10:00:00", "suma": 3120.45},
   {"tip": "instructiune_sistare", "moment": null}]}
```

```json
{"tip_document": "adresa_infiintare_poprire", "canal": "executor_judecatoresc",
 "emitent": {"tip": "executor_judecatoresc", "birou": "BEJ DEMO"}, "dosar_executare": "123/2026",
 "creditor": {"denumire": "FURNIZOR EXEMPLU SRL", "cui": "43890832"},
 "debitor": {"nume": "Demovici Elena", "cnp": "2580722120774"},
 "suma_datorata": 1800.00, "moneda": "RON", "cont_plata": {"iban": "RO33INGB0000999900000123"},
 "temei_legal": "Codul de procedură civilă"}
```

Idee de tool pentru agent: un „calculator de poprire" cu sold cert = min(sold disponibil, sumă datorată − sume deja reținute), cu sumele exceptate ca parametru, pentru că regula lor nu a fost cercetată.

### 3.3 Certificat de moștenitor [RECONSTRUIT]

Nu s-a găsit niciun model oficial și nicio listă de câmpuri. Conținutul de mai jos e cunoaștere generală, marcată în note ca neverificată. Verificări utile: CNP-ul defunctului este al titularului contului, cotele moștenitorilor însumează 1, iar identitatea fiecărui moștenitor corespunde actului lui de identitate.

| Câmp | Conținut |
|---|---|
| birou notarial, nr. și dată certificat, nr. dosar succesoral | identificare document |
| defunct | nume, CNP, data decesului, ultimul domiciliu |
| moștenitori | nume, CNP, act de identitate, calitate, cotă |
| masa succesorală | bunuri, inclusiv conturi bancare (IBAN) |

```json
{"tip_document": "certificat_mostenitor", "birou_notarial": "Birou Notarial DEMO", "numar": "45",
 "data": "2026-09-15", "dosar_succesoral": "112/2026",
 "defunct": {"nume": "Fictivescu Radu", "cnp": "1410203222156", "data_decesului": "2026-03-02",
   "ultimul_domiciliu": "Iași, jud. Iași"},
 "mostenitori": [
   {"nume": "Probeanu Ioana", "cnp": "2850930324027", "calitate": "descendent", "cota": "1/2"},
   {"nume": "Demovici Andrei", "cnp": "1830512123183", "calitate": "descendent", "cota": "1/2"}],
 "masa_succesorala": [{"tip": "cont_bancar", "iban": "RO29RZBR0000060055501234"}]}
```

### 3.4 Procură notarială [RECONSTRUIT]

RNNEPR (Registrul Național Notarial de Evidență a Procurilor și a Revocării acestora) e registrul electronic al UNNPR pentru procurile notariale și revocările lor. Conform art. 2033 Cod civil, notarul care autentifică revocarea unei procuri autentice o trimite imediat registrului. Nu s-a aflat cum interoghează băncile RNNEPR, așa că în demo folosiți un mock. Câmpurile de mai jos sunt neverificate.

| Câmp | Verificare |
|---|---|
| birou notarial; încheiere de autentificare (nr., dată) | existența în RNNEPR (mock) |
| mandant: nume, CNP, act de identitate | CNP = titularul contului |
| mandatar: nume, CNP, act de identitate | actul să fie valabil |
| puteri; conturi; termen | operațiunea cerută să fie acoperită, data în termen |
| rezultatul verificării revocării | revocată → refuz |

```json
{"tip_document": "procura_notariala", "birou_notarial": "Birou Notarial DEMO",
 "incheiere_autentificare": {"numar": "1187", "data": "2026-05-12"},
 "mandant": {"nume": "Demovici Elena", "cnp": "2580722120774", "act_identitate": "CI XT654321"},
 "mandatar": {"nume": "Demovici Andrei", "cnp": "1830512123183", "act_identitate": "CEI XT7654321"},
 "puteri": ["consultare sold", "retragere numerar", "închidere cont"],
 "conturi": [{"iban": "RO49RZBR0000060077700003"}], "valabila_pana_la": "2027-05-12",
 "verificare_rnnepr": {"revocata": false, "verificat_la": "2026-10-28", "sursa": "mock"}}
```

### 3.5 Certificat constatator ONRC [câmpuri din surse secundare]

Conținut tipic (blog StartCo): număr ONRC, denumire, formă juridică, CUI, sediu social, starea firmei, coduri CAEN (principal și secundare), capital social, administratori, asociați/acționari. Variante: „de bază", „fonduri IMM" (cu date financiare), „pentru insolvență". Se obține online sau la ghișeu, pentru circa 30 de lei (cifră de blog; verificați tariful ONRC). Nu s-a obținut un specimen oficial, iar schimbările de coduri din CAEN Rev. 3 nu au fost verificate: codurile din exemplu sunt ilustrative.

| Câmp | Sursă | Verificare |
|---|---|---|
| număr ONRC, denumire, formă juridică, CUI | blog StartCo | `valideaza_onrc`, `valideaza_cui`; identice cu adeverința și e-Factura |
| sediu social | blog StartCo | concordanță cu adresa din e-Factura |
| starea firmei | blog StartCo | altă stare decât „funcțiune" → escaladare |
| coduri CAEN (principal, secundare) | blog StartCo | listă CAEN Rev. 3 neverificată |
| capital social | blog StartCo | — |
| administratori; asociați/acționari cu cote | blog StartCo | CNP valid; asociații corespund declarației BR (§3.6) |
| număr, dată, variantă certificat | **[RECONSTRUIT]** | actualitatea certificatului |

```json
{"tip_document": "certificat_constatator", "varianta": "de baza", "numar": "CC-DEMO-778899", "data": "2026-10-01",
 "firma": {"denumire": "EXEMPLU SOFTWARE DEMO SRL", "forma_juridica": "SRL", "cui": "12345674",
   "nr_onrc": "J2025000123009", "sediu_social": "Str. Exemplului nr. 1, Cluj-Napoca, jud. Cluj",
   "stare": "funcțiune", "caen_principal": "6201", "caen_secundare": ["6202"], "capital_social_lei": 1000},
 "administratori": [{"nume": "Demovici Andrei", "cnp": "1830512123183"}],
 "asociati": [{"nume": "Demovici Andrei", "cnp": "1830512123183", "cota_procent": 60},
              {"nume": "Probeanu Ioana", "cnp": "2850930324027", "cota_procent": 40}]}
```

### 3.6 Declarație privind beneficiarul real [modele ONRC OFICIALE; câmpuri RECONSTRUIT]

Firmele înregistrate în registrul comerțului depun declarația la ONRC (Legea 129/2019, art. 19 alin. 5). Legea 315/2021 a eliminat depunerea anuală: declarația se depune la înregistrare și la fiecare modificare (o sursă indică termen de 15 zile de la modificare). Modelele ONRC sunt nr. 6, pentru declarația dată în fața reprezentantului ONRC, și nr. 6A, orientativ, pentru declarația sub semnătură privată. Se depune la ghișeu, prin notar sau avocat, ori online, cu semnătură electronică calificată. Sursele dau amenzi de până la 10.000 de lei, dar nu concordă între ele. Câmpurile formularelor nu au fost obținute. Verificare utilă pentru demo: beneficiarii și procentele trebuie să corespundă asociaților din certificatul constatator (§3.5).

| Câmp **[RECONSTRUIT]** | Verificare |
|---|---|
| entitate: denumire, CUI, nr. ONRC | identice cu certificatul constatator |
| model (6 sau 6A), data | depusă la înregistrare sau după ultima modificare |
| declarant: nume, calitate | — |
| beneficiar real: nume, CNP, cetățenie, domiciliu, act de identitate | CNP valid; act valabil |
| modalitatea de control, procent | suma procentelor ≤ 100; concordanță cu asociații |

```json
{"tip_document": "declaratie_beneficiar_real", "model": "6A", "data": "2026-10-01",
 "entitate": {"denumire": "EXEMPLU SOFTWARE DEMO SRL", "cui": "12345674", "nr_onrc": "J2025000123009"},
 "declarant": {"nume": "Demovici Andrei", "calitate": "administrator"},
 "beneficiari_reali": [
   {"nume": "Demovici Andrei", "cnp": "1830512123183", "cetatenie": "română", "domiciliu": "Cluj-Napoca",
    "act_identitate": "CEI XT7654321", "modalitate_control": "deținere directă", "procent": 60},
   {"nume": "Probeanu Ioana", "cnp": "2850930324027", "cetatenie": "română", "domiciliu": "Sibiu",
    "act_identitate": "CI XT112233", "modalitate_control": "deținere directă", "procent": 40}]}
```

### 3.7 Extras de cont [RECONSTRUIT]

Ghidul Raiffeisen de Internet Banking pentru corporații (februarie 2024) are o secțiune „Extras de cont", dar formatele de export nu au fost confirmate. ERP-ul WinMentor importă extrase MT940. Randați PDF-ul din același registru din care generați MT940 și camt.053 (§4).

| Câmp **[RECONSTRUIT]** | Verificare |
|---|---|
| bancă, titular, CNP/CUI titular, IBAN, monedă, perioadă | IBAN valid, cod bancă RZBR |
| sold inițial, total credit, total debit, sold final | sold inițial + credite − debite = sold final |
| tranzacții: data înregistrării, data valutei, descriere, contrapartidă și IBAN-ul ei, referința băncii, sumă | aceleași referințe ca în :61: (MT940) și AcctSvcrRef (camt.053) |

```json
{"tip_document": "extras_cont", "banca": "Raiffeisen Bank (demo)", "titular": "EXEMPLU SOFTWARE DEMO SRL",
 "cui": "12345674", "iban": "RO54RZBR0000060012345678", "moneda": "RON",
 "perioada": ["2026-10-27", "2026-10-27"], "sold_initial": 15000.00, "total_credit": 1210.00,
 "total_debit": 4535.50, "sold_final": 11674.50,
 "tranzactii": [
   {"data": "2026-10-27", "valuta": "2026-10-27", "descriere": "Plata factura DEMO-2026-0042",
    "contrapartida": "TESTARE LOGISTIC DEMO SRL", "iban_contrapartida": "RO53BTRL0000042000777001",
    "ref_banca": "RZB2610270001", "suma": 1210.00},
   {"data": "2026-10-27", "valuta": "2026-10-27", "descriere": "Factura FX-0007",
    "contrapartida": "FURNIZOR EXEMPLU SRL", "iban_contrapartida": "RO62BRDE0000007000123456",
    "ref_banca": "RZB2610270002", "suma": -4500.00},
   {"data": "2026-10-27", "valuta": "2026-10-27", "descriere": "POS 25.10.2026 MAGAZIN DEMO CLUJ",
    "ref_banca": "RZB2610270003", "suma": -35.50}]}
```

### 3.8 e-Factura (UBL 2.1 + CIUS-RO) [OFICIAL]

- **CustomizationID** (OMF 4092/2022): `urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1`. Valoarea mai veche `…:RO_CIUS:1.0.0.2021` încă apare într-un pachet .NET.
- **Format:** RO_CIUS este specificația națională de utilizare a EN 16931. Se acceptă UBL și CII; UBL e mai răspândit.
- **Validare:** XSD, Schematron, liste de coduri și reconcilierea totalurilor. Instrumente terțe declară că folosesc pachetul Schematron **ro16931-ubl 1.0.9** (în vigoare din 5.06.2024); autoritar rămâne validatorul ANAF din SPV.
- **API de validare** (după documentația anafpy): `POST https://api.anaf.ro/prod/FCTEL/rest/validare/FACT1` (sau `/FCN`), cu OAuth2. Există și o variantă publică, fără autentificare, pe webservicesp.anaf.ro. Gazda de test întoarce 404 la validare.
- **Respingeri frecvente:** unități de măsură nestandard, coduri de scutire TVA lipsă, totaluri care nu se reconciliază cu liniile, coduri de țară greșite, identificatori de partener incompleți.
- **Termene:** raportare B2B obligatorie din 1.01.2024, B2C din 1.01.2025, cu sancțiuni B2C din 1.07.2025. Termenul de transmitere e de 5 zile calendaristice din 1.07.2024; un blog susține 5 zile lucrătoare din 1.01.2026, deci sursele se contrazic.
- **Reguli CIUS-RO [NEVERIFICAT]:** județul în format ISO 3166-2:RO (ex. `RO-CJ`), sectoarele Bucureștiului scrise „SECTOR1"…„SECTOR6", InvoiceTypeCode 380/381/384/389/751.
- **Cota de TVA:** 21% în exemplu este **[PRESUPUNERE]**. Nu apare în note, deci parametrizați-o și verificați cota în vigoare.

| Câmp (element UBL) | Exemplu | Verificare |
|---|---|---|
| `cbc:CustomizationID` | CIUS-RO 1.0.1 | valoare exactă |
| `cbc:ID`, `cbc:IssueDate`, `cbc:DueDate` | DEMO-2026-0042 | ID-ul trebuie să apară în RmtInf la încasare |
| `cbc:InvoiceTypeCode`, `cbc:DocumentCurrencyCode` | 380, RON | listă de coduri |
| furnizor: `PartyTaxScheme/CompanyID`, `PartyLegalEntity` | RO12345674, J2025000123009 | CUI și ONRC (§2) |
| adrese: `CityName`, `CountrySubentity`, `Country` | RO-CJ / SECTOR3, RO-B | reguli CIUS-RO [NEVERIFICAT] |
| `cac:PaymentMeans/PayeeFinancialAccount/cbc:ID` | IBAN | `valideaza_iban_ro` |
| `cac:TaxTotal`, `cac:LegalMonetaryTotal`, `cac:InvoiceLine` | 1.000 + 210 = 1.210 | `verifica_efactura.py` |

```json
{"CustomizationID": "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1",
 "ID": "DEMO-2026-0042", "IssueDate": "2026-10-15", "DueDate": "2026-11-14", "InvoiceTypeCode": "380",
 "DocumentCurrencyCode": "RON",
 "furnizor": {"nume": "EXEMPLU SOFTWARE DEMO SRL", "cui": "RO12345674", "nr_onrc": "J2025000123009",
   "oras": "Cluj-Napoca", "judet": "RO-CJ"},
 "client": {"nume": "TESTARE LOGISTIC DEMO SRL", "cui": "20433211", "oras": "SECTOR3", "judet": "RO-B"},
 "iban_plata": "RO54RZBR0000060012345678",
 "linii": [{"denumire": "Ore suport software (demo)", "cantitate": 10, "um": "HUR", "pret": 100.00,
            "valoare": 1000.00, "cota_tva": 21}],
 "total_fara_tva": 1000.00, "tva": 210.00, "total_plata": 1210.00}
```

Trei alegeri din exemplu nu vin din note **[PRESUPUNERE]**: numărul ONRC pus în `PartyLegalEntity/CompanyID`, apoi `PaymentMeansCode` 30 (transfer) și `unitCode` HUR (oră), luate din listele de coduri UN/ECE folosite de EN 16931. Verificați-le cu Schematron-ul.

Fișier `efactura_demo.xml`, minimal și nevalidat cu Schematron-ul CIUS-RO:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1</cbc:CustomizationID>
 <cbc:ID>DEMO-2026-0042</cbc:ID>
 <cbc:IssueDate>2026-10-15</cbc:IssueDate>
 <cbc:DueDate>2026-11-14</cbc:DueDate>
 <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
 <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
 <cac:AccountingSupplierParty><cac:Party>
  <cac:PostalAddress><cbc:StreetName>Str. Exemplului nr. 1</cbc:StreetName><cbc:CityName>Cluj-Napoca</cbc:CityName>
   <cbc:CountrySubentity>RO-CJ</cbc:CountrySubentity><cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyTaxScheme><cbc:CompanyID>RO12345674</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>EXEMPLU SOFTWARE DEMO SRL</cbc:RegistrationName><cbc:CompanyID>J2025000123009</cbc:CompanyID></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party>
  <cac:PostalAddress><cbc:StreetName>Bd. Testului nr. 10</cbc:StreetName><cbc:CityName>SECTOR3</cbc:CityName>
   <cbc:CountrySubentity>RO-B</cbc:CountrySubentity><cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyLegalEntity><cbc:RegistrationName>TESTARE LOGISTIC DEMO SRL</cbc:RegistrationName><cbc:CompanyID>20433211</cbc:CompanyID></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingCustomerParty>
 <cac:PaymentMeans><cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
  <cac:PayeeFinancialAccount><cbc:ID>RO54RZBR0000060012345678</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
 <cac:TaxTotal><cbc:TaxAmount currencyID="RON">210.00</cbc:TaxAmount>
  <cac:TaxSubtotal><cbc:TaxableAmount currencyID="RON">1000.00</cbc:TaxableAmount><cbc:TaxAmount currencyID="RON">210.00</cbc:TaxAmount>
   <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>21</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
 <cac:LegalMonetaryTotal>
  <cbc:LineExtensionAmount currencyID="RON">1000.00</cbc:LineExtensionAmount>
  <cbc:TaxExclusiveAmount currencyID="RON">1000.00</cbc:TaxExclusiveAmount>
  <cbc:TaxInclusiveAmount currencyID="RON">1210.00</cbc:TaxInclusiveAmount>
  <cbc:PayableAmount currencyID="RON">1210.00</cbc:PayableAmount>
 </cac:LegalMonetaryTotal>
 <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="HUR">10</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="RON">1000.00</cbc:LineExtensionAmount>
  <cac:Item><cbc:Name>Ore suport software (demo)</cbc:Name>
   <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>21</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>
  <cac:Price><cbc:PriceAmount currencyID="RON">100.00</cbc:PriceAmount></cac:Price>
 </cac:InvoiceLine>
</Invoice>
```

```python
# fișier: verifica_efactura.py -- verificări aritmetice minime pe UBL (NU înlocuiește Schematron-ul CIUS-RO)
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal

NS = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}


def verifica_totaluri(cale: str) -> list[str]:
    inv = ET.parse(cale).getroot()
    d = lambda el, p: Decimal(el.findtext(p, namespaces=NS))
    erori = []
    linii = inv.findall("cac:InvoiceLine", NS)
    for l in linii:
        if d(l, "cbc:InvoicedQuantity") * d(l, "cac:Price/cbc:PriceAmount") != d(l, "cbc:LineExtensionAmount"):
            erori.append(f"linia {l.findtext('cbc:ID', namespaces=NS)}: cantitate x preț != valoare")
    tot = inv.find("cac:LegalMonetaryTotal", NS)
    if sum(d(l, "cbc:LineExtensionAmount") for l in linii) != d(tot, "cbc:LineExtensionAmount"):
        erori.append("suma liniilor != LineExtensionAmount")
    tva = d(inv, "cac:TaxTotal/cbc:TaxAmount")
    for st in inv.findall("cac:TaxTotal/cac:TaxSubtotal", NS):
        calc = (d(st, "cbc:TaxableAmount") * d(st, "cac:TaxCategory/cbc:Percent") / 100).quantize(Decimal("0.01"))
        if calc != d(st, "cbc:TaxAmount"):
            erori.append(f"TVA subtotal {calc} != {d(st, 'cbc:TaxAmount')}")
    if d(tot, "cbc:TaxExclusiveAmount") + tva != d(tot, "cbc:TaxInclusiveAmount"):
        erori.append("TaxExclusive + TVA != TaxInclusive")
    if d(tot, "cbc:TaxInclusiveAmount") != d(tot, "cbc:PayableAmount"):   # fără avansuri/rotunjiri
        erori.append("TaxInclusive != Payable")
    return erori


if __name__ == "__main__":
    print(verifica_totaluri(sys.argv[1] if len(sys.argv) > 1 else "efactura_demo.xml") or "TOTALURI OK")
```

Pe fișierul de mai sus scriptul afișează `TOTALURI OK`. Cu `PayableAmount` schimbat în 1201.00 afișează `['TaxInclusive != Payable']` [TESTAT].

### 3.9 Chitanță [formular OFICIAL; câmpuri RECONSTRUIT]

OMFP 2634/2015 privind documentele financiar-contabile a apărut în MO 910 din 9.12.2015 și se aplică din 1.01.2016. Anexa 1 stabilește elementele obligatorii (pct. 2 și 10), iar Anexa 3 conține modelele. Chitanța are codul 14-4-1, varianta pentru valută 14-4-1/a, și se emite în 2 exemplare. Lista exactă a elementelor obligatorii nu a fost obținută. Pentru câmpurile scrise de mână (suma, semnătura) folosiți un LLM cu viziune sau revizuire umană, pentru că Azure DI nu suportă scris de mână în română.

| Câmp **[RECONSTRUIT]** | Verificare |
|---|---|
| unitatea: denumire, CUI, nr. ONRC, sediu | CUI și ONRC valide |
| serie, număr, dată; formular 14-4-1 sau 14-4-1/a | serie + număr unice |
| „am primit de la": nume, CNP/CUI | identificatori valizi |
| suma în cifre și în litere | cele două trebuie să coincidă |
| „reprezentând" (de ex. factura nr.) | factura există și suma corespunde |
| semnătura casierului | scris de mână → LLM cu viziune sau om |

```json
{"tip_document": "chitanta", "formular": "14-4-1", "serie": "DEMO", "numar": "000123", "data": "2026-10-20",
 "unitate": {"denumire": "EXEMPLU SOFTWARE DEMO SRL", "cui": "12345674", "nr_onrc": "J2025000123009",
   "sediu": "Cluj-Napoca"},
 "am_primit_de_la": {"nume": "Probeanu Ioana", "cnp": "2850930324027"},
 "suma": 350.00, "suma_in_litere": "trei sute cincizeci lei", "reprezentand": "c/v factura DEMO-2026-0050",
 "casier": "semnătură olografă"}
```

---

## 4. Formate de fișiere bancare

**Scenariu comun.** Contul RO54RZBR0000060012345678 al EXEMPLU SOFTWARE DEMO SRL, pe 27.10.2026: sold inițial 15.000,00 RON; +1.210,00 (încasarea facturii DEMO-2026-0042); −4.500,00 (plată către furnizor, inițiată prin pain.001); −35,50 (POS); sold final 11.674,50. A doua plată din pain.001 (800,00) nu apare în extras, iar reconcilierea trebuie s-o semnaleze. Toate fișierele vin din același registru, așa cum recomandă notele: pain.001 pentru plățile trimise, camt.053.001.08 ca extras XML, MT940 ca extras text, plus PDF-ul extrasului.

### 4.1 MT940

| Tag | Conținut | Statut | Format |
|---|---|---|---|
| :20: | Transaction Reference Number | M | 16x |
| :21: | Related Reference | O | |
| :25: | identificarea contului | M | 35x |
| :28C: | număr extras / secvență | M | 5n[/5n] |
| :60F: / :60M: | sold de deschidere: D/C, dată AALLZZ, monedă, sumă | M | 1!a6!n3!a15d |
| :61: | linie de tranzacție | O | vezi mai jos |
| :86: | informații pentru titular | O | 6x65x |
| :62F: / :62M: | sold final contabil | M | |
| :64: | sold final disponibil | O | |
| :65: | sold disponibil viitor | O | |

Formatul `:61:` este `6!n[4!n]2a[1!a]15d1!a3!c16x[//16x][34x]`. Descompunerea primei linii din exemplu, `2610271027C1210,00NTRFTLD-INV-0042//RZB2610270001`:

| Subcâmp | Valoare | Semnificație |
|---|---|---|
| 6!n | 261027 | data valutei |
| [4!n] | 1027 | data înregistrării (LLZZ) |
| 2a | C | marcaj debit/credit (D/C) |
| [1!a] | — | cod de fonduri |
| 15d | 1210,00 | sumă, cu virgulă zecimală |
| 1!a3!c | NTRF | tipul tranzacției (codurile NTRF/NMSC sunt uzuale, dar lista SWIFT nu e în note **[NEVERIFICAT]**) |
| 16x | TLD-INV-0042 | referința titularului; aici e EndToEndId-ul **[PRESUPUNERE]** |
| [//16x] | RZB2610270001 | referința băncii |
| [34x] | — | detalii suplimentare, pe rândul următor |

Fișier `extras.mt940`:

```text
:20:STMT20261027
:25:RO54RZBR0000060012345678
:28C:207/1
:60F:C261026RON15000,00
:61:2610271027C1210,00NTRFTLD-INV-0042//RZB2610270001
:86:TESTARE LOGISTIC DEMO SRL RO53BTRL0000042000777001
Plata factura DEMO-2026-0042
:61:2610271027D4500,00NTRFEXS-20261027-01//RZB2610270002
:86:FURNIZOR EXEMPLU SRL RO62BRDE0000007000123456 Factura FX-0007
:61:2610271027D35,50NMSCNONREF//RZB2610270003
:86:POS 25.10.2026 MAGAZIN DEMO CLUJ
:62F:C261027RON11674,50
:64:C261027RON11674,50
```

Specificațiile oficiale SWIFT MT940/MT942 sunt accesibile doar membrilor, iar MT942 (raportul intrazilnic) nu e acoperit de nicio sursă. Nu s-a găsit niciun ghid MT940 sau camt.053 publicat de o bancă românească.

### 4.2 camt.053 (BkToCstmrStmt)

| Cheie | Cale (relativ la `Stmt/Ntry`) | Rol în reconciliere |
|---|---|---|
| AcctSvcrRef | `AcctSvcrRef` | referința pusă de bancă pe fiecare intrare; folosită la reconcilieri și dispute |
| EndToEndId | `NtryDtls/TxDtls/Refs/EndToEndId` | pusă de plătitor și păstrată neschimbată pe tot lanțul; poate conține numărul facturii |
| BkTxCd | `BkTxCd/Domn/Cd` + `Fmly/Cd` + `Fmly/SubFmlyCd` (sau `Prtry`) | cod ISO pe trei niveluri, Domain/Family/SubFamily, ori cod proprietar |
| RmtInf | `NtryDtls/TxDtls/RmtInf/Ustrd` (sau `Strd`) | text liber sau date structurate (de ex. referința creditorului) |

Intrările de tip lot din camt.053 se pot reconcilia la nivel de tranzacție cu camt.054. Codurile BkTxCd din exemplu (PMNT/RCDT/DMCT, PMNT/ICDT/DMCT, PMNT/CCRD/POSD) sunt luate din lista externă ISO, care nu e în note **[NEVERIFICAT]**. Exemplul a fost parsat și soldurile verificate, dar nu a fost validat cu XSD-ul oficial.

Fișier `extras_camt053.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
 <BkToCstmrStmt>
  <GrpHdr><MsgId>CAMT-20261027-0001</MsgId><CreDtTm>2026-10-27T20:00:00</CreDtTm></GrpHdr>
  <Stmt>
   <Id>STMT20261027</Id><ElctrncSeqNb>207</ElctrncSeqNb><CreDtTm>2026-10-27T20:00:00</CreDtTm>
   <Acct><Id><IBAN>RO54RZBR0000060012345678</IBAN></Id><Ccy>RON</Ccy></Acct>
   <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="RON">15000.00</Amt>
    <CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-10-26</Dt></Dt></Bal>
   <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="RON">11674.50</Amt>
    <CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-10-27</Dt></Dt></Bal>
   <Ntry><Amt Ccy="RON">1210.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <BookgDt><Dt>2026-10-27</Dt></BookgDt><ValDt><Dt>2026-10-27</Dt></ValDt>
    <AcctSvcrRef>RZB2610270001</AcctSvcrRef>
    <BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>RCDT</Cd><SubFmlyCd>DMCT</SubFmlyCd></Fmly></Domn></BkTxCd>
    <NtryDtls><TxDtls><Refs><EndToEndId>TLD-INV-0042</EndToEndId></Refs>
     <RltdPties><Dbtr><Pty><Nm>TESTARE LOGISTIC DEMO SRL</Nm></Pty></Dbtr>
      <DbtrAcct><Id><IBAN>RO53BTRL0000042000777001</IBAN></Id></DbtrAcct></RltdPties>
     <RmtInf><Ustrd>Plata factura DEMO-2026-0042</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="RON">4500.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <BookgDt><Dt>2026-10-27</Dt></BookgDt><ValDt><Dt>2026-10-27</Dt></ValDt>
    <AcctSvcrRef>RZB2610270002</AcctSvcrRef>
    <BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>ICDT</Cd><SubFmlyCd>DMCT</SubFmlyCd></Fmly></Domn></BkTxCd>
    <NtryDtls><TxDtls><Refs><EndToEndId>EXS-20261027-01</EndToEndId></Refs>
     <RltdPties><Cdtr><Pty><Nm>FURNIZOR EXEMPLU SRL</Nm></Pty></Cdtr>
      <CdtrAcct><Id><IBAN>RO62BRDE0000007000123456</IBAN></Id></CdtrAcct></RltdPties>
     <RmtInf><Ustrd>Factura FX-0007</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="RON">35.50</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <BookgDt><Dt>2026-10-27</Dt></BookgDt><ValDt><Dt>2026-10-27</Dt></ValDt>
    <AcctSvcrRef>RZB2610270003</AcctSvcrRef>
    <BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>CCRD</Cd><SubFmlyCd>POSD</SubFmlyCd></Fmly></Domn></BkTxCd>
    <AddtlNtryInf>POS 25.10.2026 MAGAZIN DEMO CLUJ</AddtlNtryInf></Ntry>
  </Stmt>
 </BkToCstmrStmt>
</Document>
```

### 4.3 pain.001.001.09 (plăți domestice)

- **PKO BP, sucursala România** (anunț din 24.09.2026): acceptă **pain.001.001.09** la importul transferurilor domestice SENT/ReGIS. Suportă în continuare MT103, Elixir-0, CSV, pain.001.001.07 și pain.001.001.03. Numele și adresa au câmpuri separate (țară, localitate, cod poștal), iar contrapartida se identifică prin LEI (20 de caractere) sau prin CNP/CUI.
- **ReGIS** (RTGS-ul BNR) folosește XML ISO 20022. **SENT** e clearing-ul de retail al TransFond, decontat prin ReGIS (RON) și TARGET2 (EUR); TransFond operează și Plăți Instant.
- **Chei de reconciliere:** `PmtId/EndToEndId` din pain.001 corespunde lui `Refs/EndToEndId` din camt.053.
- **[PRESUPUNERE]** în exemplu: `SchmeNm/Cd = TXID` pentru CUI și `NOTPROVIDED` pentru agentul debitorului sunt convenții ISO/EPC care nu apar în note. Verificați-le în ghidul băncii.

Fișier `plati_pain001.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">
 <CstmrCdtTrfInitn>
  <GrpHdr><MsgId>PAIN-20261027-01</MsgId><CreDtTm>2026-10-27T09:00:00</CreDtTm>
   <NbOfTxs>2</NbOfTxs><CtrlSum>5300.00</CtrlSum><InitgPty><Nm>EXEMPLU SOFTWARE DEMO SRL</Nm></InitgPty></GrpHdr>
  <PmtInf><PmtInfId>LOT-20261027</PmtInfId><PmtMtd>TRF</PmtMtd><NbOfTxs>2</NbOfTxs><CtrlSum>5300.00</CtrlSum>
   <ReqdExctnDt><Dt>2026-10-27</Dt></ReqdExctnDt>
   <Dbtr><Nm>EXEMPLU SOFTWARE DEMO SRL</Nm>
    <Id><OrgId><Othr><Id>12345674</Id><SchmeNm><Cd>TXID</Cd></SchmeNm></Othr></OrgId></Id></Dbtr>
   <DbtrAcct><Id><IBAN>RO54RZBR0000060012345678</IBAN></Id></DbtrAcct>
   <DbtrAgt><FinInstnId><Othr><Id>NOTPROVIDED</Id></Othr></FinInstnId></DbtrAgt>
   <CdtTrfTxInf><PmtId><EndToEndId>EXS-20261027-01</EndToEndId></PmtId>
    <Amt><InstdAmt Ccy="RON">4500.00</InstdAmt></Amt>
    <Cdtr><Nm>FURNIZOR EXEMPLU SRL</Nm><PstlAdr><PstCd>400001</PstCd><TwnNm>Cluj-Napoca</TwnNm><Ctry>RO</Ctry></PstlAdr></Cdtr>
    <CdtrAcct><Id><IBAN>RO62BRDE0000007000123456</IBAN></Id></CdtrAcct>
    <RmtInf><Ustrd>Factura FX-0007</Ustrd></RmtInf></CdtTrfTxInf>
   <CdtTrfTxInf><PmtId><EndToEndId>EXS-20261027-02</EndToEndId></PmtId>
    <Amt><InstdAmt Ccy="RON">800.00</InstdAmt></Amt>
    <Cdtr><Nm>PRESTATOR TEST SRL</Nm><PstlAdr><TwnNm>Iasi</TwnNm><Ctry>RO</Ctry></PstlAdr></Cdtr>
    <CdtrAcct><Id><IBAN>RO72INGB0000999912345678</IBAN></Id></CdtrAcct>
    <RmtInf><Ustrd>Factura PT-0311</Ustrd></RmtInf></CdtTrfTxInf>
  </PmtInf>
 </CstmrCdtTrfInitn>
</Document>
```

### 4.4 Clearing de card: schemă simplificată pentru demo [PRESUPUNERE]

**Formatele reale** sunt proprietare și accesibile doar membrilor rețelelor:

- **Mastercard IPM:** formatul standard de clearing prin GCMS, bazat pe ISO 8583, în fișiere T112. Reconcilierea folosește mesajele Reconciliation/1644.
- **Visa BASE II:** mecanismul central pentru schimbul de date de interchange și decontarea între acquireri și emitenți. Documentația fișierului de captură pomenește înregistrări TC 05 și TC 90/91/92 (header, lot, trailer).
- **Potrivire:** ARN-ul se folosește împreună cu BRN și TRC.
- **Parsare:** biblioteca Python `cardutil` citește fișiere IPM.

Schema de mai jos imită cheile de reconciliere IPM/BASE II, dar lungimile câmpurilor (de ex. ARN pe 23 de cifre) sunt **[NEVERIFICAT]**.

| Câmp | Exemplu | Notă |
|---|---|---|
| arn | 74000000000000000000001 | 23 de cifre [NEVERIFICAT]; cheia pentru dispute |
| pan_mascat | 411111******1111 | nu stocați niciodată PAN-ul complet |
| cod_autorizare, rrn | A1B2C3, 629900000001 | legătura cu autorizarea |
| data_tranzactie, data_decontare | 2026-10-25, 2026-10-27 | |
| suma/moneda tranzacției, suma/moneda decontării | 120.00 EUR → 597.60 RON | curs implicit |
| comision_interchange, mcc | 0.24, 5812 | |
| merchant_id, terminal_id | DEMOMERCH000002, DEMOT002 | |

Fișier `clearing_card.csv`:

```csv
arn,pan_mascat,cod_autorizare,rrn,data_tranzactie,data_decontare,suma_tranzactie,moneda_tranzactie,suma_decontare,moneda_decontare,comision_interchange,mcc,merchant_id,terminal_id
74000000000000000000001,411111******1111,A1B2C3,629900000001,2026-10-25,2026-10-27,35.50,RON,35.50,RON,0.07,5411,DEMOMERCH000001,DEMOT001
74000000000000000000002,411111******1111,D4E5F6,629900000002,2026-10-25,2026-10-27,120.00,EUR,597.60,RON,0.24,5812,DEMOMERCH000002,DEMOT002
```

### 4.5 Parsare și reconciliere [TESTAT]

Scriptul citește cele patru fișiere din directorul curent, verifică soldurile MT940 și camt.053 și controlul `NbOfTxs`/`CtrlSum` din pain.001. Apoi potrivește plățile după EndToEndId, încasările după numărul facturii din RmtInf și înregistrările de card după sumă.

```python
# fișier: reconciliere.py -- parsează exemplele MT940 / camt.053 / pain.001 / CSV card și le potrivește
import csv
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

RE_61 = re.compile(r"(?P<data_val>\d{6})(?P<data_inreg>\d{4})?(?P<dc>R?[DC])(?P<fond>[A-Z])?"
                   r"(?P<suma>\d[\d,]{0,14})(?P<tip>[NSF][A-Z0-9]{3})(?P<ref_client>.{1,16}?)"
                   r"(?://(?P<ref_banca>.{1,16}))?$")
RE_SOLD = re.compile(r"(?P<dc>[DC])(?P<data>\d{6})(?P<moneda>[A-Z]{3})(?P<suma>[\d,]+)")


def _dec(s: str) -> Decimal:
    return Decimal(s.replace(",", "."))


def parseaza_mt940(text: str) -> dict:
    campuri, extras = [], {"tranzactii": []}
    for linie in text.splitlines():
        m = re.match(r":(\d{2}[A-Z]?):(.*)", linie)
        if m:
            campuri.append([m[1], m[2]])
        elif campuri:
            campuri[-1][1] += "\n" + linie                  # continuare (:86:, detalii :61:)
    for tag, val in campuri:
        if tag in ("60F", "60M", "62F", "62M", "64"):
            m = RE_SOLD.fullmatch(val)
            semn = 1 if m["dc"] == "C" else -1
            extras[tag[:2]] = semn * _dec(m["suma"])
        elif tag == "61":
            m = RE_61.match(val.split("\n")[0])
            t = m.groupdict()
            t["suma"] = _dec(t["suma"]) * (1 if t["dc"].endswith("C") else -1)
            extras["tranzactii"].append(t)
        elif tag == "86" and extras["tranzactii"]:
            extras["tranzactii"][-1]["info"] = val.replace("\n", " ")
        else:
            extras[tag] = val
    return extras


NS_CAMT = {"c": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"}
NS_PAIN = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"}


def parseaza_camt053(cale: str) -> dict:
    stmt = ET.parse(cale).getroot().find("c:BkToCstmrStmt/c:Stmt", NS_CAMT)
    t = lambda el, p: el.findtext(p, default="", namespaces=NS_CAMT)
    solduri = {t(b, "c:Tp/c:CdOrPrtry/c:Cd"): Decimal(t(b, "c:Amt")) *
               (1 if t(b, "c:CdtDbtInd") == "CRDT" else -1) for b in stmt.findall("c:Bal", NS_CAMT)}
    intrari = []
    for n in stmt.findall("c:Ntry", NS_CAMT):
        semn = 1 if t(n, "c:CdtDbtInd") == "CRDT" else -1
        intrari.append({
            "suma": semn * Decimal(t(n, "c:Amt")),
            "data": t(n, "c:BookgDt/c:Dt"),
            "AcctSvcrRef": t(n, "c:AcctSvcrRef"),
            "BkTxCd": "/".join([t(n, "c:BkTxCd/c:Domn/c:Cd"), t(n, "c:BkTxCd/c:Domn/c:Fmly/c:Cd"),
                                t(n, "c:BkTxCd/c:Domn/c:Fmly/c:SubFmlyCd")]),
            "EndToEndId": t(n, "c:NtryDtls/c:TxDtls/c:Refs/c:EndToEndId"),
            "RmtInf": t(n, "c:NtryDtls/c:TxDtls/c:RmtInf/c:Ustrd") or t(n, "c:AddtlNtryInf"),
        })
    return {"iban": t(stmt, "c:Acct/c:Id/c:IBAN"), "solduri": solduri, "intrari": intrari}


def parseaza_pain001(cale: str) -> dict:
    doc = ET.parse(cale).getroot().find("p:CstmrCdtTrfInitn", NS_PAIN)
    t = lambda el, p: el.findtext(p, default="", namespaces=NS_PAIN)
    plati = [{"EndToEndId": t(x, "p:PmtId/p:EndToEndId"), "suma": Decimal(t(x, "p:Amt/p:InstdAmt")),
              "beneficiar": t(x, "p:Cdtr/p:Nm"), "RmtInf": t(x, "p:RmtInf/p:Ustrd")}
             for x in doc.iter(f"{{{NS_PAIN['p']}}}CdtTrfTxInf")]
    return {"NbOfTxs": int(t(doc, "p:GrpHdr/p:NbOfTxs")),
            "CtrlSum": Decimal(t(doc, "p:GrpHdr/p:CtrlSum")), "plati": plati}


def reconciliaza(camt: dict, pain: dict, facturi_emise: set[str]) -> list[str]:
    rezultate = []
    e2e_extras = {i["EndToEndId"]: i for i in camt["intrari"] if i["EndToEndId"]}
    for p in pain["plati"]:
        i = e2e_extras.get(p["EndToEndId"])
        if i is None:
            rezultate.append(f"NEPOTRIVIT {p['EndToEndId']}: plată inițiată, absentă din extras")
        elif -i["suma"] != p["suma"]:
            rezultate.append(f"DIFERENȚĂ {p['EndToEndId']}: {p['suma']} vs {-i['suma']}")
        else:
            rezultate.append(f"OK {p['EndToEndId']} <-> {i['AcctSvcrRef']}")
    for i in camt["intrari"]:
        if i["suma"] > 0:
            facturi = set(re.findall(r"DEMO-\d{4}-\d{4}", i["RmtInf"])) & facturi_emise
            rezultate.append(f"{'OK' if facturi else 'NEIDENTIFICAT'} încasare {i['suma']} "
                             f"{i['AcctSvcrRef']} -> {sorted(facturi)}")
    return rezultate


if __name__ == "__main__":
    mt = parseaza_mt940(open("extras.mt940", encoding="utf-8").read())
    assert mt["60"] + sum(t["suma"] for t in mt["tranzactii"]) == mt["62"] == Decimal("11674.50")
    assert mt["tranzactii"][0]["ref_client"] == "TLD-INV-0042"
    assert mt["tranzactii"][2]["ref_banca"] == "RZB2610270003"
    camt = parseaza_camt053("extras_camt053.xml")
    s = camt["solduri"]
    assert s["OPBD"] + sum(i["suma"] for i in camt["intrari"]) == s["CLBD"]
    pain = parseaza_pain001("plati_pain001.xml")
    assert pain["NbOfTxs"] == len(pain["plati"]) and pain["CtrlSum"] == sum(p["suma"] for p in pain["plati"])
    rez = reconciliaza(camt, pain, facturi_emise={"DEMO-2026-0042"})
    print("\n".join(rez))
    assert rez[0].startswith("OK EXS-20261027-01") and rez[1].startswith("NEPOTRIVIT EXS-20261027-02")
    card = list(csv.DictReader(open("clearing_card.csv", encoding="utf-8")))
    assert all(len(r["arn"]) == 23 and r["arn"].isdigit() for r in card)
    pos = [i for i in camt["intrari"] if i["BkTxCd"] == "PMNT/CCRD/POSD"]
    nepotrivite = [r["arn"] for r in card if not any(-i["suma"] == Decimal(r["suma_decontare"]) for i in pos)]
    print("Card fără intrare în extras:", nepotrivite)
    assert nepotrivite == ["74000000000000000000002"]
    print("RECONCILIERE OK")
```

Ieșire așteptată:

```text
OK EXS-20261027-01 <-> RZB2610270002
NEPOTRIVIT EXS-20261027-02: plată inițiată, absentă din extras
OK încasare 1210.00 RZB2610270001 -> ['DEMO-2026-0042']
Card fără intrare în extras: ['74000000000000000000002']
RECONCILIERE OK
```

---

## 5. Rețetă de date sintetice

### 5.1 Reguli de coerență

| Legătură | Regulă de generare | Verificare pe care o face agentul |
|---|---|---|
| CNP ↔ data nașterii ↔ sex ↔ județ | generați întâi persoana (data nașterii dintr-o distribuție de adulți, sexul, județul), apoi derivați CNP-ul. JJ înseamnă județul nașterii/înregistrării, nu domiciliul actual | `parseaza_cnp` comparat cu datele din documente |
| CNP ↔ act ↔ MRZ | MRZ-ul se construiește din aceleași câmpuri. Pe CI pune S + ultimele 6 cifre (presupunere), pe CEI nu pune CNP | `parseaza_mrz` + `verifica_mrz_cu_cnp` |
| vârstă ↔ valabilitatea actului | CI: 7 ani la 18–24, 10 ani la 25–54, fără termen la 55+. CEI: 10 ani la 18+, 5 ani la 14–18 | act expirat la data cererii → escaladare |
| CEI ↔ domiciliu | CEI nu are adresă tipărită, deci dosarul trebuie să conțină o dovadă de domiciliu | CEI fără dovadă → cerere de completare |
| IBAN ↔ bancă | clienții „noștri" au RZBR, contrapartidele au alte coduri confirmate, toate cu cifre de control calculate | `valideaza_iban_ro` + `avertismente_iban_ro` |
| angajator ↔ CUI ↔ ONRC | anul de înregistrare decide JJ (județ înainte de 2024, 00 după) | concordanță cu certificatul constatator și cu e-Factura |
| venit ↔ extras | fiecare lună din adeverință produce un credit salarial cu același net, de la IBAN-ul angajatorului, cu „SALARIU AAAA-LL" | media netului recalculată și comparată cu creditele |
| factură ↔ plată | ID-ul facturii apare în RmtInf/:86:, EndToEndId apare în pain.001 și în camt.053 | potrivire; elementele nepotrivite se escaladează cu motiv |

### 5.2 Generator de cazuri [TESTAT]

`synth.py` construiește un caz complet: persoană, act de identitate cu MRZ, cont RZBR, angajator, adeverință pe 12 luni și extras cu salarii și plăți POS. Tot el plantează anomalii controlate și conține un detector determinist folosit ca baseline. Testul rulează 300 de cazuri: cazurile curate nu produc nicio alarmă, iar fiecare anomalie plantată singură e găsită (precizie 1,00, recall 1,00). Agentul LLM se evaluează cu exact aceleași etichete.

```python
# fișier: synth.py -- caz sintetic coerent (client + CI/CEI + cont + angajator + venit + extras)
import copy
import json
import random
from datetime import date, timedelta

from mrz import mrz_td1, mrz_td2, parseaza_mrz, verifica_mrz_cu_cnp
from ro_ids import (JUDETE_CNP, genereaza_cnp, genereaza_cui, genereaza_iban_ro, genereaza_onrc_nou,
                    valideaza_cnp, valideaza_cui, valideaza_iban_ro, valideaza_onrc)

AZI = date(2026, 10, 28)
PRENUME = {"F": ["Ana-Maria", "Elena", "Ioana", "Andreea"], "M": ["Andrei", "Mihai", "Ștefan", "Radu"]}
NUME = ["Testescu", "Exemplaru", "Demovici", "Fictivescu", "Probeanu"]       # intenționat fictive
SERII_CI = {1: ["AX"], 2: ["AR", "ZR"], 12: ["KX", "CJ"], 13: ["KT", "KZ"], 22: ["MX", "MZ", "IZ"],
            34: ["TR"], **{j: ["DP", "DR", "DT", "RD", "RR", "RT", "RX", "RK"] for j in range(40, 47)}}
SERII_CEI = {1: "AB", 22: "IS", **{j: "MB" for j in range(40, 47)}}
RATA_NET = 0.585      # APROXIMARE de demo brut->net, NU calcul fiscal; parametrizați


def _plus_ani(d: date, ani: int) -> date:
    return d.replace(year=d.year + ani) if (d.month, d.day) != (2, 29) else date(d.year + ani, 3, 1)


def _varsta(dn: date, la: date) -> int:
    return la.year - dn.year - ((la.month, la.day) < (dn.month, dn.day))


def _luna_anterioara(d: date, k: int) -> str:                   # "AAAA-LL", cu k luni în urmă
    an, luna = divmod(d.year * 12 + d.month - 1 - k, 12)
    return f"{an}-{luna + 1:02d}"


def _ani_valabilitate(tip: str, varsta: int) -> int | None:      # None = fără termen (CI, 55+)
    if tip == "CEI":
        return 10 if varsta >= 18 else 5
    return None if varsta >= 55 else 10 if varsta >= 25 else 7 if varsta >= 18 else 4


def mrz_act(p: dict, a: dict) -> list[str]:
    exp = f"{date.fromisoformat(a['expira']):%y%m%d}" if a["expira"] else "<<<<<<"  # 55+: NECONFIRMAT
    if a["tip"] == "CEI":                                   # TD1, fără CNP în MRZ (presupunere)
        return mrz_td1("ID", "ROU", a["serie_numar"], p["cnp"][1:7], p["sex"], exp, "ROU",
                       p["nume"], p["prenume"])
    return mrz_td2("ID", "ROU", p["nume"], p["prenume"], a["serie_numar"], "ROU", p["cnp"][1:7],
                   p["sex"], exp, p["cnp"][0] + p["cnp"][-6:])        # PRESUPUNERE: S + ultimele 6


def act_identitate(rng, p: dict, tip: str | None = None, emis: date | None = None) -> dict:
    majorat = _plus_ani(date.fromisoformat(p["data_nasterii"]), 18)     # emitere după 18 ani
    emis = emis or AZI - timedelta(days=rng.randint(30, max(30, min(6 * 365, (AZI - majorat).days))))
    tip = tip or ("CEI" if emis >= date(2025, 3, 20) and rng.random() < 0.5 else "CI")
    ani = _ani_valabilitate(tip, _varsta(date.fromisoformat(p["data_nasterii"]), emis))
    if tip == "CEI":
        nr = SERII_CEI.get(p["judet"], "XX") + f"{rng.randint(0, 9999999):07d}"  # format NECONFIRMAT
    else:
        nr = rng.choice(SERII_CI.get(p["judet"], ["XX"])) + f"{rng.randint(0, 999999):06d}"
    a = {"tip": tip, "serie_numar": nr, "emis": emis.isoformat(),
         "expira": _plus_ani(emis, ani).isoformat() if ani else None, "adresa_tiparita": tip == "CI"}
    a["mrz"] = mrz_act(p, a)
    return a


def caz_client(rng: random.Random, luni: int = 12) -> dict:
    sex = rng.choice("MF")
    dn = date(AZI.year - rng.randint(19, 70), 1, 1) + timedelta(days=rng.randrange(365))
    judet = rng.choice(list(JUDETE_CNP))                 # ponderați cu populația pentru realism
    p = {"nume": rng.choice(NUME), "prenume": rng.choice(PRENUME[sex]), "sex": sex,
         "data_nasterii": dn.isoformat(), "judet": judet,
         "cnp": genereaza_cnp(dn, sex, judet, rng.randint(1, 999))}
    p["act"] = act_identitate(rng, p)
    an_inreg = rng.randint(2005, 2025)
    angajator = {"denumire": f"{rng.choice(['ALFA', 'BETA', 'GAMA'])} DEMO SRL",
                 "cui": genereaza_cui(rng, 8),
                 "nr_onrc": genereaza_onrc_nou(rng, an_inreg, judet=40 if an_inreg < 2024 else 0),
                 "iban": genereaza_iban_ro(rng, rng.choice(["BTRL", "BRDE", "INGB", "RNCB"]))}
    net = rng.randrange(3500, 12000, 50)
    luni_iso = [_luna_anterioara(AZI, k) for k in range(luni, 0, -1)]   # până la luna anterioară
    venit = [{"luna": l, "salariu_incadrare_brut": round(net / RATA_NET), "salariu_net": net}
             for l in luni_iso]
    extras = [{"data": f"{v['luna']}-10", "suma": v["salariu_net"], "contrapartida": angajator["denumire"],
               "iban_contrapartida": angajator["iban"], "BkTxCd": "PMNT/RCDT/DMCT",
               "detalii": f"SALARIU {v['luna']}"} for v in venit]
    extras += [{"data": f"{l}-{rng.randint(11, 28):02d}", "suma": -round(rng.uniform(20, 400), 2),
                "contrapartida": "POS MAGAZIN DEMO", "BkTxCd": "PMNT/CCRD/POSD", "detalii": "POS"}
               for l in luni_iso for _ in range(rng.randint(2, 6))]
    return {"client": p, "iban": genereaza_iban_ro(rng, "RZBR"), "angajator": angajator,
            "documente": ["act_identitate", "adeverinta_venit"] +
                         (["dovada_domiciliu"] if p["act"]["tip"] == "CEI" else []),
            "adeverinta": {"cnp": p["cnp"], "angajator_cui": angajator["cui"], "venit": venit,
                           "retineri": "NU", "insolventa": "nu se afla"},
            "extras": sorted(extras, key=lambda t: t["data"]), "anomalii_plantate": []}


def _act_expirat(c, r):
    a = c["client"]["act"]
    exp = AZI - timedelta(days=r.randint(1, 400))
    a.update(expira=exp.isoformat(), emis=_plus_ani(exp, -10).isoformat())
    a["mrz"] = mrz_act(c["client"], a)


def _cei_fara_domiciliu(c, r):
    c["client"]["act"] = act_identitate(r, c["client"], tip="CEI", emis=date(2025, 6, 2))
    c["documente"] = [d for d in c["documente"] if d != "dovada_domiciliu"]


ANOMALII = {
    "cnp_cifra_control": lambda c, r: c["adeverinta"].update(
        cnp=c["adeverinta"]["cnp"][:12] + str((int(c["adeverinta"]["cnp"][12]) + 1) % 10)),
    "cnp_diferit": lambda c, r: c["adeverinta"].update(cnp=genereaza_cnp(       # valid, dar alt NNN
        date.fromisoformat(c["client"]["data_nasterii"]), c["client"]["sex"], c["client"]["judet"],
        int(c["client"]["cnp"][9:12]) % 999 + 1)),
    "act_expirat": _act_expirat,
    "cei_fara_dovada_domiciliu": _cei_fara_domiciliu,
    "venit_neconcordant": lambda c, r: [v.update(salariu_net=round(v["salariu_net"] * 1.3))
                                        for v in c["adeverinta"]["venit"]],
    "retineri_poprire": lambda c, r: c["adeverinta"].update(retineri="DA"),
}


def planteaza(caz: dict, rng: random.Random, tipuri: list[str]) -> dict:
    caz = copy.deepcopy(caz)
    for t in tipuri:
        ANOMALII[t](caz, rng)
        caz["anomalii_plantate"].append(t)              # ground truth pentru evaluare
    return caz


def detecteaza(caz: dict, azi: date = AZI, prag: float = 0.10) -> set[str]:
    """Baseline determinist; agentul LLM ar trebui să apeleze aceleași verificări ca tool-uri."""
    gasite, act = set(), caz["client"]["act"]
    cnp_doc, cnp_ci = caz["adeverinta"]["cnp"], caz["client"]["cnp"]
    if valideaza_cnp(cnp_doc, azi=azi):
        gasite.add("cnp_cifra_control")
    elif cnp_doc != cnp_ci:
        gasite.add("cnp_diferit")
    f, erori_mrz = parseaza_mrz(act["mrz"])
    if erori_mrz or verifica_mrz_cu_cnp(f, cnp_ci):
        gasite.add("mrz_neconcordant")
    if act["expira"] and act["expira"] < azi.isoformat():
        gasite.add("act_expirat")
    if act["tip"] == "CEI" and "dovada_domiciliu" not in caz["documente"]:
        gasite.add("cei_fara_dovada_domiciliu")
    salarii = sum(t["suma"] for t in caz["extras"] if t["detalii"].startswith("SALARIU"))
    if abs(sum(v["salariu_net"] for v in caz["adeverinta"]["venit"]) - salarii) > prag * salarii:
        gasite.add("venit_neconcordant")
    if caz["adeverinta"]["retineri"] == "DA":
        gasite.add("retineri_poprire")
    return gasite


if __name__ == "__main__":
    rng = random.Random(2026)
    tp = fp = fn = 0
    for _ in range(300):
        c = caz_client(rng)
        assert valideaza_cnp(c["client"]["cnp"], azi=AZI) == [] and valideaza_cui(c["angajator"]["cui"]) == []
        assert valideaza_iban_ro(c["iban"]) == [] == valideaza_iban_ro(c["angajator"]["iban"])
        assert valideaza_onrc(c["angajator"]["nr_onrc"], azi=AZI) == ([], [])
        assert detecteaza(c) == set(), detecteaza(c)                     # caz curat
        for t in ANOMALII:                                               # câte o anomalie pe caz
            gasit = detecteaza(planteaza(c, rng, [t]))
            tp, fp, fn = tp + (t in gasit), fp + len(gasit - {t}), fn + (t not in gasit)
    print(f"precizie={tp / (tp + fp):.2f} recall={tp / (tp + fn):.2f}")
    assert [_luna_anterioara(AZI, k) for k in (12, 1)] == ["2025-10", "2026-09"]
    print(json.dumps(planteaza(c, rng, ["act_expirat"])["client"], ensure_ascii=False))
    print("SYNTH OK")
```

Generatorul are câteva simplificări asumate:

- județul se alege uniform, nu ponderat cu populația, pentru că notele nu conțin date de populație;
- rata brut→net de 0,585 este o aproximare de demo **[PRESUPUNERE]**, nu un calcul fiscal;
- seria XX e folosită pentru județele fără exemplu de serie în surse;
- CI vechi poate fi emisă și după 2025 (data de la care nu mai sunt emise nu e în note);
- codificarea „fără termen" pentru CI la 55+ (`<<<<<<`) e neconfirmată.

### 5.3 Randare: HTML → PDF → „scanare"

Pipeline-ul din note, pentru 1–2 zile de lucru:

1. nume și adrese din Faker `ro_RO`, identificatori din generatoarele proprii;
2. un JSON de ground truth pentru fiecare caz;
3. șabloane Jinja2 în HTML, randate în PDF cu WeasyPrint sau Playwright (neevaluate în note);
4. rasterizare, apoi zgomot Augraphy, rotație și ștampile;
5. extragere cu un LLM multimodal într-o schemă Pydantic, cu Tesseract `ron` sau PaddleOCR `ro` ca baseline ieftin;
6. validatori determiniști;
7. orchestrare ca agent cu tool-uri (validatori, mock de core banking, calculator de poprire), cu rutare la om când încrederea e scăzută;
8. evaluare față de ground truth.

`synth.py` folosește liste fixe de nume evident fictive, ca să nu depindă de Faker. Pentru varietate, înlocuiți-le cu nume generate de Faker `ro_RO`.

**Diacritice:** în documentele sintetice amestecați ș/ț cu virgulă dedesubt (U+0219/U+021B) și ş/ţ cu sedilă (U+015F/U+0163), pentru că documentele reale și fonturile vechi le folosesc pe amândouă. Înainte de orice potrivire normalizați la forma cu virgulă.

```python
# fișier: render.py -- HTML (Jinja2) pentru adeverință + diacritice mixte (testat local)
import random

from jinja2 import Template

ADEVERINTA = Template("""<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:"DejaVu Sans",sans-serif;font-size:11px} td,th{border:1px solid #000;padding:2px 6px}
table{border-collapse:collapse}</style></head><body>
<p><b>{{ a.denumire }}</b><br>C.U.I.: {{ a.cui }}<br>Nr. de ordine în Registrul Comerțului: {{ a.nr_onrc }}</p>
<h3 style="text-align:center">ADEVERINȚĂ DE VENIT</h3>
<p>Se adeverește că {{ c.nume|upper }} {{ c.prenume }}, CNP {{ d.cnp }}, este angajat(ă) al(a) societății.</p>
<p>Salariul este grevat de rețineri lunare: <b>{{ d.retineri }}</b></p>
<table><tr><th>Luna / An</th><th>Salariul de încadrare</th><th>Salariul net</th></tr>
{% for v in d.venit %}<tr><td>{{ v.luna }}</td><td>{{ v.salariu_incadrare_brut }}</td><td>{{ v.salariu_net }}</td></tr>
{% endfor %}</table>
<p>Societatea {{ d.insolventa }} în procedura insolvenței (Legea nr. 85/2014).</p></body></html>""")

SPRE_SEDILA = str.maketrans("șțȘȚ", "şţŞŢ")       # U+0219/021B -> U+015F/0163 (font vechi)
SPRE_VIRGULA = str.maketrans("şţŞŢ", "șțȘȚ")


def diacritice_mixte(text: str, rng: random.Random, p: float = 0.3) -> str:
    return text.translate(SPRE_SEDILA) if rng.random() < p else text


def normalizeaza(text: str) -> str:                 # aplicați ÎNAINTE de orice comparație
    return text.translate(SPRE_VIRGULA)


def html_adeverinta(caz: dict, rng: random.Random) -> str:
    html = ADEVERINTA.render(a=caz["angajator"], c=caz["client"], d=caz["adeverinta"])
    return diacritice_mixte(html, rng)


if __name__ == "__main__":
    from synth import caz_client
    rng = random.Random(5)
    html = html_adeverinta(caz_client(rng, luni=6), random.Random(1))
    assert "ADEVERIN" in html and normalizeaza(html).count("ț") >= 1
    assert normalizeaza("Ştefan Ţăranu") == "Ștefan Țăranu"
    open("adeverinta.html", "w", encoding="utf-8").write(html)
    print("RENDER OK", len(html))
```

Pașii PDF → PNG → zgomot de mai jos **nu au fost rulați local** (pachetele nu erau instalate). API-urile sunt cele publice ale bibliotecilor; verificați-le pe versiunea instalată (Augraphy apare pe PyPI la 8.2.4).

```python
# NETESTAT local: necesită weasyprint (sau playwright), pymupdf, augraphy, opencv-python
from weasyprint import HTML
import fitz                                    # PyMuPDF
import cv2
from augraphy import default_augraphy_pipeline

HTML(filename="adeverinta.html").write_pdf("adeverinta.pdf")            # HTML -> PDF
fitz.open("adeverinta.pdf")[0].get_pixmap(dpi=200).save("adeverinta.png")  # PDF -> PNG
img = cv2.imread("adeverinta.png")
scan = default_augraphy_pipeline().augment(img)["output"]               # cerneală, hârtie, scanner, fax
cv2.imwrite("adeverinta_scan.png", scan)
```

Alternativa Playwright (tot netestată): `page.set_content(html)` urmat de `page.pdf(path="adeverinta.pdf")`, în Chromium.

### 5.4 Anomalii controlate și metrici

| Anomalie | Unde se plantează | Ce trebuie să detecteze agentul | Implementare |
|---|---|---|---|
| `cnp_cifra_control` | CNP-ul din adeverință | checksum invalid | `synth.py` |
| `cnp_diferit` | CNP valid, dar alt NNN decât cel din CI | nepotrivire între documente | `synth.py` |
| `act_expirat` | data expirării actului (MRZ regenerat) | act expirat la data cererii | `synth.py` |
| `cei_fara_dovada_domiciliu` | CEI fără dovadă de domiciliu | dosar incomplet | `synth.py` |
| `venit_neconcordant` | netul din adeverință ×1,3 | diferență peste prag față de creditele salariale | `synth.py` |
| `retineri_poprire` | „rețineri = DA" | escaladare / verificare popriri | `synth.py` |
| total factură greșit | `PayableAmount` ≠ total | `TaxInclusive != Payable` | `verifica_efactura.py` |
| plată fără intrare în extras | EndToEndId absent din camt.053 | element nepotrivit, cu motiv | `reconciliere.py` |
| card fără intrare în extras | ARN fără intrare POS | element nepotrivit | `reconciliere.py` |

Pentru că ground truth-ul e cunoscut, toate metricile se calculează automat:

- exact match și F1 la nivel de câmp, pe tip de document;
- rata de valori cu checksum valid;
- rata de procesare automată fără intervenție umană (straight-through processing);
- precizia și recall-ul escaladărilor pe anomaliile plantate;
- timpul pe caz.

Pentru teste de regresie folosiți promptfoo sau DeepEval, iar pentru trace-uri Langfuse.

### 5.5 De ce nu Faker `ro_RO` direct

Faker are pentru `ro_RO` provideri de adresă, autovehicul, bancă, firmă, monedă, dată, internet, job, persoană, telefon, ssn și vat_id. Numerele lui trec checksum-urile (notele au revalidat local exemplele din documentație), dar distribuțiile sunt nerealiste. Concluziile de mai jos sunt derivate din codul sursă citat în note:

- `ssn()` alege prima cifră uniform din 1–8. Asta dă ~25% persoane născute 1900–1999 (S = 1/2), **~25% născute în anii 1800** (3/4) și **~25% rezidenți străini** (7/8, cărora Faker le dă implicit secolul 1900).
- Pentru S = 5/6 anul se alege din 00–99, deci 0,25 × 73/100 ≈ **18% din CNP-uri au data nașterii în viitor** (anii 2027–2099).
- Județele sunt 01–46, 51, 52, iar NNN e 001–999; aici nu sunt probleme.
- `iban()` folosește `bban_format = "????################"`: patru **litere aleatorii** în loc de un cod de bancă real (exemplul din documentație e „MYNB"), deși lista `swift_bank_codes` de 40 de coduri conține RZBR. Cifrele de control mod 97 sunt totuși valide.
- `vat_id()` produce o bază de 9 cifre plus cifra de control, deci mereu un CUI de 10 cifre, cu prefix „RO" opțional. E valid ca checksum; `genereaza_cui` din §2.2 permite orice lungime între 2 și 10.

Soluția e o funcție proprie de circa 30 de rânduri: data nașterii dintr-o distribuție de adulți, județe ponderate cu populația, coduri de bancă reale, cifre de control calculate (vezi `caz_client`). Alternativele nu ajută: Mimesis nu are localizare românească (47 de localizări), iar SDV e sub Business Source License 1.1, care nu e licență OSI (în regulă pentru hackathon; restricția cea mai clară privește oferirea de servicii de date sintetice către terți).

---

## 6. Dataset-uri publice

| Dataset | Conținut | Dimensiune | Licență | Potrivire | Avertismente |
|---|---|---|---|---|---|
| IBM AMLworld (NeurIPS 2023) | tranzacții sintetice AML, 8 tipare de spălare (fan-out, fan-in, ciclu, aleator, bipartit, stivă, scatter-gather, gather-scatter) | HI-Small 5M tranzacții (1 spălare la 981) … HI-Large 180M; LI-Small 7M … LI-Large 176M | „Community Data License Agreement" pe Kaggle; varianta (Sharing/Permissive) **neconfirmată**; codul GNN e Apache | monitorizare tranzacții, narațiuni de alertă în română | schema coloanelor neconfirmată; remapați la IBAN RO, CNP/CUI sintetice, RON/EUR |
| PaySim | tranzacții sintetice de mobile money, dintr-o lună de loguri ale unui serviciu african | ~6,36M rânduri × 11 coloane (un sfert din original) | CC BY-SA 4.0, citată frecvent, **neconfirmată** | fraudă | nu e context RO; autorii cer citare |
| Berka / PKDD'99 Financial | date **reale anonimizate** ale unei bănci cehe | 8 tabele, 1.090.086 rânduri, 78,8 MB; 606 credite rambursate, 76 nerambursate | nespecificată | scoring, credit | **date reale**, în conflict cu regula „fără date bancare reale" (confirmați cu organizatorii); depozitul avertizează de scurgeri temporale |
| banking77 (PolyAI) | 13.083 întrebări de client în engleză, 77 de intenții | 13.083 | **CC BY 4.0** | rutare de intenții | tradus/parafrazat în română cu atribuire; adăugați intenții de back-office (poprire, certificat de moștenitor, actualizare date CEI, adeverință) |
| CFPB Consumer Complaint Database | reclamații SUA fără identificatori direcți: produs, problemă, companie, stat, canal, răspunsul companiei, Complaint ID | — | nespecificată pe pagina citită | prototip de triere reclamații în engleză | date reale; narațiunile sunt publicate doar cu consimțământ, după anonimizare; o sursă subțire din 2026 spune că au fost retrase |
| HF RO: mteb/RomanianReviewsSentiment; DGurgurov/romanian_sa; dariuschrl/romanian-sentiment-reviews-5k; DS4AI-UPB/romanian-re-semeval; xd-br0/cemrc-romanian-ner-mrc | sentiment, extragere de relații, NER | — | CC BY 4.0; CC BY-SA 4.0; CC0; CC BY 4.0; „other" | ton al reclamațiilor, NER | nu sunt bancare |
| HF RO: corpusuri juridice Coltuc2026; Yxanul/Romanian-finepdfs; Neurograf/Romanian-Instruct-SFT; saillab/alpaca-romanian-cleaned | juridic, text extras din PDF, instrucțiuni | — | mixte, autodeclarate (CC BY-NC 4.0, MIT, Apache-2.0, CC BY 4.0); Apache-2.0; nespecificat în note | text juridic, stil | licențe neverificate |

Căutarea „romanian" pe Hugging Face (109 rezultate, 28.10.2026) nu a găsit dataset-uri bancare sau financiare. Nu există nici imagini publice de acte de identitate românești, nici documente financiare românești. Seturile de credit (German Credit, Taiwan default, Home Credit, Give Me Some Credit, Lending Club) și SAML-D nu au fost verificate.

---

## 7. OCR și extragere pentru limba română

| Instrument | Suport pentru română | Diacritice | Observații |
|---|---|---|---|
| Tesseract | `ron` („Romanian; Moldavian; Moldovan") în tessdata, tessdata_best și tessdata_fast, în toate versiunile | neevaluat | baseline local ieftin |
| PaddleOCR PP-OCRv5 | `latin_PP-OCRv5_mobile_rec` listează `ro`; documentația Docling listează `ro` sub PP-OCRv6 | neevaluat | local |
| docTR | `VOCABS["romanian"] = english + "ăâîșțĂÂÎȘȚ"`; vocabularul „multilingual" include româna | **doar formele cu virgulă dedesubt**; ş/ţ cu sedilă lipsesc | normalizați înainte |
| Azure AI Document Intelligence v4.0 | `ro` pentru text **tipărit** în prebuilt-read și prebuilt-layout | neevaluat | **fără scris de mână în română** (scrisul de mână e suportat doar pentru en, zh-Hans, fr, de, it, th, ja, ko, pt, es, ru, ar) |
| Google Document AI | română în Enterprise Document OCR, Form Parser și Layout Parser | neevaluat | Custom Extractor generativ: oficial doar engleza; procesoarele de identitate acoperă doar documente din SUA |
| LLM multimodal | nu s-a găsit niciun benchmark pe documente sau acte românești | depinde de model | practic: LLM → schemă Pydantic → validatori determiniști; câmpurile scrise de mână merg la LLM cu viziune sau la om |
| Druid, FintechOS (comercial) | CI/CEI/pașaport RO cu CNP, MRZ și validare SIRUTA | — | utile ca listă de referință a verificărilor KYC |

Nu s-au verificat pentru română: Mistral OCR, olmOCR, DeepSeek-OCR, PaddleOCR-VL, Docling (ca pipeline), Marker.

---

## 8. Biblioteci și framework-uri

**Validare și date**

| Bibliotecă | Licență / versiune | Când o folosiți |
|---|---|---|
| python-stdnum (`stdnum.ro.cnp`, `.cui`, `.onrc`) | LGPL-2.1+ | validare de referință: CNP cu `get_county()`, CUI, ONRC vechi și nou (cifra nouă e neoficială). Importul ca bibliotecă e în regulă; copierea codului în cod proprietar atrage obligații LGPL (notă generală, nu sfat juridic) |
| schwifty | licență neverificată | validare, generare și randomizare de IBAN-uri, BIC; acoperirea RO e neverificată |
| Faker `ro_RO` | — | doar nume, adrese și telefoane (vezi §5.5) |
| Mimesis | — | fără localizare RO |
| SDV | BSL 1.1 (nu e OSI) | date tabulare sintetice din distribuții; rar necesar aici |
| Augraphy | MIT, 8.2.4 | zgomot de imprimantă, scanner și fax pe documente |
| anafpy | — | client Python pentru API-ul e-Factura; ID-urile regulilor urmează Schematron-ul CIUS-RO 1.0.9 |
| RoeFactura (.NET), Odoo `l10n_ro_account_edi_ubl` | — | referințe UBL românești |
| cardutil | — | parsare de fișiere Mastercard IPM |
| npm: `romanian-personal-identity-code-validator`, `js-romanian-cnp-validation`, `parsecnp` | mentenanță neverificată | front-end JS; mai simplu e să portați cele 3 funcții de checksum (~30 de rânduri). Pachet npm dedicat CUI nu s-a găsit |
| PHP `alcea/cif`, `oriceon/cnp`, `mmltech/cnp-decoder` (exemplul lui conține un MRZ IDROU); Elixir `validators_ro`; Ruby `romanianvalidators`; R `rocnp` | neverificate | alte ecosisteme |

**Framework-uri de agent** (versiuni PyPI la 28.10.2026, conform notelor):

| Pachet | Versiune, licență | Când îl folosiți |
|---|---|---|
| `langgraph` | 1.2.18, MIT | fluxuri explicite cu stare și human-in-the-loop (de ex. poprire → sold cert → instrucțiune) |
| `pydantic-ai` | 2.63.0, MIT | extragere tipizată, pornind de la schemă (documente → modele Pydantic) |
| `openai-agents` | 0.24.0, MIT | setup independent de furnizor (peste 100 de LLM-uri prin LiteLLM/any-llm) |

Alegerea e o judecată, nu rezultatul unui benchmark.

**Evaluare** (licențele provin din bloguri de vendor; verificați fișierul LICENSE al fiecărui proiect):

| Unealtă | Licență | Când o folosiți |
|---|---|---|
| promptfoo | MIT | regresii de prompt în CI, pe cazurile sintetice |
| DeepEval | Apache-2.0 | teste în stil pytest pe extragere și decizii |
| Langfuse | în mare parte MIT, self-hostable | trace-uri ale agentului pentru demo și depanare |
| Inspect AI | MIT (UK AI Security Institute) | evaluări structurate de agent |
| Arize Phoenix | Elastic License 2.0 (source-available) | observabilitate, dacă licența e acceptabilă |

---

## 9. Goluri și de verificat

**Identificatori**

- Anexa 1 a Regulamentului BNR privind IBAN nu a putut fi citită, deci lista de coduri de bancă vine din Faker și din surse secundare. BREL e disputat; TREZ ca Trezorerie e presupunere.
- Algoritmul cifrei de control ONRC e neoficial (python-stdnum, după un blog), iar baza legală a noului format (posibil Legea 265/2022) nu e confirmată. Conversia vechi → nou din §2.4 e ilustrativă.
- Nu s-a găsit actul normativ pentru CNP cu S = 9 și pentru codurile 70/80–83, nici dacă 70 e deja în uz.
- **MRZ:** machetele au fost verificate pe specimenele ICAO reproduse din memorie, iar PRADO a răspuns cu HTTP 403. Rămân neconfirmate:
  - conținutul opțional al TD2 (S + ultimele 6 cifre CNP);
  - lipsa CNP-ului din MRZ-ul CEI, codul de document și formatul numărului CEI, CAN-ul;
  - CNP-ul în câmpul personal al pașaportului;
  - codificarea „fără termen" pentru CI la 55+;
  - MRZ-ul CIS.
- Druid descrie verificarea cifrei documentului pe „rândul 2" și la cardurile noi, deși în TD1 cifra documentului e pe rândul 1. Clarificați pe un specimen.
- Nuanța „10 ani sau până la 3.08.2031" pentru CI la 25–54 nu e implementată.

**Documente**

- Nu s-au obținut: modelul ANAF actual al adresei de poprire, schema XML ANAF–bănci (protocolul Intesa a răspuns cu HTTP 403), procedura executorilor, sumele exceptate de la poprire.
- Certificatul de moștenitor și procura sunt reconstruite. Nu se știe cum interoghează băncile RNNEPR.
- Elementele obligatorii ale chitanței 14-4-1, câmpurile formularelor BR 6/6A, specimenul certificatului constatator, codurile CAEN Rev. 3 și o modificare din octombrie 2025 a Legii 129/2019 (apărută în rezultate de căutare) nu au fost verificate.
- Pagina tehnică e-Factura a ANAF a eșuat (ECONNRESET). Neconfirmate față de sursa primară: Schematron-ul 1.0.9; endpoint-urile de upload, stareMesaj, listaMesaje, descarcare; regulile CIUS-RO RO-XX, SECTOR1–6 și lista InvoiceTypeCode. Termenul de transmitere e contradictoriu (5 zile calendaristice vs. 5 zile lucrătoare din 2026).
- Exemplul UBL nu a fost validat cu Schematron-ul sau cu validatorul ANAF. Cota de TVA de 21% și rata netă 0,585 sunt parametri de demo, absenți din note.

**Formate bancare**

- Exemplele camt.053 și pain.001 au fost doar parsate (ElementTree) și verificate aritmetic, nu validate cu XSD. Codurile BkTxCd, TXID, NOTPROVIDED și NTRF/NMSC vin din liste externe ISO/SWIFT/EPC care nu sunt în note.
- Lipsesc: un ghid MT940/camt de la o bancă românească, MT942, pacs.008 la nivel de element, calendarul de migrare ISO 20022 al SENT, obligațiile din Regulamentul UE privind plățile instant și Verification of Payee pentru România (o sursă secundară pomenește 2027).
- Structura ARN, lungimile câmpurilor și lista de câmpuri IPM/BASE II nu sunt confirmate.

**Date și unelte**

- Neconfirmate: licența PaySim; varianta CDLA și schema AMLworld; licențele Berka și CFPB; disponibilitatea narațiunilor CFPB în 2026.
- Neverificate local: WeasyPrint, Playwright, PyMuPDF, Augraphy. Compararea uneltelor HTML→PDF (inclusiv starea de mentenanță a wkhtmltopdf) lipsește.
- Nu există benchmark OCR/LLM pe documente românești.
- Neverificate: versiunile CrewAI, Microsoft Agent Framework, Google ADK, Mastra; datele de lansare LangGraph 1.0 și PydanticAI 1.0/2.0; licențele uneltelor de evaluare; licența schwifty și acoperirea RO; mentenanța pachetelor npm/PHP/Ruby; bibliotecile JS de IBAN (ibantools, iban.js); versiunea curentă python-stdnum și modulul `stdnum.ro.cf`.

---

## 10. Surse

**Identificatori**

- Wikipedia RO, Cod numeric personal: https://ro.wikipedia.org/wiki/Cod_numeric_personal_(Rom%C3%A2nia)
- python-stdnum: https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cnp.py · https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cui.py · https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/onrc.py
- IBAN: https://en.wikipedia.org/wiki/International_Bank_Account_Number · https://www.bnr.ro/files/d/Legislatie/EN/Reg_IBAN.pdf · https://folositor.ro/glosar/iban · https://qonto.com/es/iban/romania · https://www.slash.com/routing-numbers/country/romania · https://financer.ro/banii-tai/cate-cifre-are-un-cont-bancar/
- Faker: https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/bank/ro_RO/__init__.py · https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/ssn/ro_RO/__init__.py · https://faker.readthedocs.io/en/master/locales/ro_RO.html
- ONRC, format nou: https://contabilul.manager.ro/a/28861/atentie-iata-noul-format-al-numarului-de-ordine-din-registrul-comertului.html
- Acte de identitate: https://en.wikipedia.org/wiki/Romanian_identity_card · https://romania.rferl.org/a/cartea-electronica-de-identitate/33354995.html · https://hotnews.ro/romanii-care-au-buletine-noi-cu-cip-se-plang-ca-trebuie-sa-aduca-dovada-domiciliului-la-ghisee-pentru-ca-nu-exista-cititoare-mai-raspunde-ca-a-trimis-institutiilor-mesaje-de-responsabilizar-2112313 · https://www.wall-street.ro/articol/fara-categorie/problema-adresei-din-cei-mai-promite-ca-de-marti-va-exista-o-rezolvare.html
- KYC: https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/New%20Romanian%20Identity%20Cards%20OCR.htm · https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/Romanian%20Passport%20OCR.htm · https://docs.fintechos.com/APs/SysPack/24.5/UserGuide/Content/ComputerVision/Validations.htm

**Documente**

- Adeverință de venit: https://www.librabank.ro/documente/Adeverinta_venit.pdf · https://www.btdirect.ro/storage/app/media/documente/Adeverinta-de-venit.pdf · https://www.porschefinance.ro/files/romania/documente/Adeverinta-de-venit-pentru-leasing-persoane-fizice.pdf · https://legeaz.net/monitorul-oficial-955-2016/oanaf-3396-model-continut-adeverinta-venit
- Extras de cont: https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/corporatii/20240201-Ghid-utilizare-Internet-Banking-Corporatii.pdf · https://portal.winmentor.ro/wme/docs/down/solutii_suport/Service/Import%20date%20din%20alte%20aplicatii/WME%20-%20Import%20extrase%20de%20cont%20in%20format%20MT.doc
- Poprire: https://www.fiscalitatea.ro/anaf-a-schimbat-9-formulare-17133/ · https://procreditbank.ro/wp-content/uploads/files/Protocolul%20de%20colaborare%20privind%20implementarea%20sistemului%20de%20instituire%20electronica%CC%86%20a%20popririi%20asupra%20conturilor%20bancare.pdf · https://static.anaf.ro/static/10/Anaf/Informatii_R/18.08.2025%20-%20Raport%20de%20activitateANAF_2025S1_V7.pdf · https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_626_2023.pdf
- Certificat constatator: https://startco.ro/blog/certificatul-constatator-ce-este-si-pentru-ce-il-folosesti/ · https://bono.ro/blog/certificat-constatator
- Beneficiar real: https://www.fiscalitatea.ro/declaratia-de-beneficiar-real-ce-este-unde-se-depune-si-cine-trebuie-sa-completeze-formularul-21828/ · https://www.fiscalitatea.ro/declaratia-privind-beneficiarii-reali-nu-mai-trebuie-depusa-anual-insa-anumite-persoane-au-in-continuare-aceasta-obligatielegea-315221-21596/ · https://www.fiscalitatea.ro/declaratia-privind-beneficiarul-real-formularul-se-depune-in-fiecare-an-sau-numai-atunci-cand-apar-modificari-22299/ · https://www.fiscalitatea.ro/onrc-anunta-ca-au-fost-elaborate-noi-modele-de-declaratii-privind-beneficiarii-reali-21240/ · https://bono.ro/blog/declaratie-beneficiar-real · https://www.onrc.ro/documente/ghid%20completare%20cerere%20de%20depunere%20declaratie%20BR.pdf · https://www.fiscalitatea.ro/declaratia-privind-beneficiarii-reali-2025-amenzile-ajung-pana-la-10000-lei-pentru-nedepunere-24002/
- Procură / RNNEPR: https://notari.pro/dictionar-juridic-dex/rnnepr · https://e-justice.europa.eu/topics/family-matters-inheritance/inheritance/information-authorities-issuing-ecs/ro_en · https://legeaz.net/noul-cod-civil/art-2033-publicitatea-revocarii-procurii-autentice-notariale-mandatul-cu-reprezentare-contractul-de-mandat
- e-Factura: https://static.anaf.ro/static/10/Anaf/legislatie/OMF_4092_2022.pdf · https://packages.nuget.org/packages/RoeFactura · https://www.ediconnect.ro/en/e-invoice/ubl-xml-e-invoice · https://apify.com/kamerozkan/romania-efactura-validator · https://demoanaf.ro/en/efactura/validare · https://anafpy.readthedocs.io/en/latest/anaf-reference/efactura/api/ · https://www.fiscalitatea.ro/e-factura-b2c-23791/ · https://startupcafe.ro/e-factura-b2c-perioada-fara-sanctiuni-expira-in-iunie-2025-ce-amenzi-risca-firmele-82751 · https://economedia.ro/cum-se-calculeaza-termenul-de-transmitere-a-facturilor-in-sistemul-national-ro-e-factura.html · https://bono.ro/blog/ghid-ro-e-factura
- Chitanță: https://www.avocatnet.ro/articol_42147/Ordinul-MFP-nr-2634-2015-documentele-financiar-contabile.html · https://contabilul.manager.ro/a/16855/ordinul-mfp-nr-26342015-privind-documentele-financiar-contabile.html · https://www.rubinian.com/dictionar/chitanta-pentru-operatiuni-in-valuta · https://www.fiscalitatea.ro/studiu-de-caz-consecintele-suportate-de-o-societate-in-cazul-unor-chitante-intocmite-incorect-2509/

**Formate bancare**

- MT940: https://www.sepaforcorporates.com/swift-for-corporates/account-statement-mt940-file-format-overview/
- camt.053/054: https://developer.gs.com/docs/services/transaction-banking/best-practices-iso-recon/ · https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/diepm/integrations_bai_adding_source_104x758c3e29_106x758c5280.html · https://docs.numeral.io/docs/camt053-xsd-business-logic · https://assets.ing.com/m/19ba05999348c5c7/original/Sample-Files-CAMT.pdf · https://docs.continia.com/da-dk/continia-banking/business-functionality/payment-import/bank-account-statement/reconciling-camt054-entries-from-camt053/
- Plăți RO: https://www.pkobp.pl/en/romania-branch/news/changes-to-domestic-sent-and-regis-transfers · https://www.forbes.ro/?p=374165 · https://thepaypers.com/fintech/news/allevo-provides-17-banks-with-access-to-the-regis-system · https://www.transfi.com/jp/blog/romanias-payment-rails-how-they-work---sent-sepa-instant-transfers · https://www.platiinstant.ro/en/the-service · https://economedia.ro/?p=219575
- Carduri: https://afferentsoftware.com/?p=3666 · https://developer.paymentology.com/docs/data-reconciliation-report · https://developer.paymentology.com/bankinglive/docs/txn-clearing-settlement-reconciliation · https://www.intelica.com/en/blog/mastercard-visa-clearing-process · https://developer.visaacceptance.com/docs/vas/en-us/payments/acq/all/na/payments-acq/payments-acq-references-capture-file.html · https://developer.mastercard.com/fld-fraud-submission/documentation/parameters/fda-req-res-complete/ · https://cardutil.readthedocs.io/en/latest/api.html

**Dataset-uri**

- AMLworld: https://arxiv.org/html/2306.16424v1 · https://proceedings.neurips.cc/paper_files/paper/2023/hash/5f38404edff6f3f642d6fa5892479c42-Abstract.html · https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- PaySim: https://baselight.app/u/kaggle/dataset/ealaxi_paysim1 · https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/2588208
- Berka: https://relational.fel.cvut.cz/dataset/Financial · https://www.kdnuggets.com/news/99/n09/i2.html
- banking77: https://huggingface.co/datasets/PolyAI/banking77
- CFPB: https://www.consumerfinance.gov/complaint/data-use/ · https://www.consumerfinance.gov/about-us/newsroom/cfpb-publishes-over-7700-consumer-complaint-narratives-about-financial-companies · https://files.consumerfinance.gov/a/assets/201503_cfpb_Narrative-Scrubbing-Standard.pdf · https://newsletter.cobaltintelligence.com/p/cfpb-pulls-3m-complaint-narratives
- Hugging Face RO: https://huggingface.co/datasets?search=romanian

**Unelte**

- Date sintetice: https://mimesis.name/master/locales.html · https://pypi.org/project/sdv · https://github.com/sdv-dev/SDV · https://www.everydev.ai/tools/sdv · https://pypi.org/project/augraphy/ · https://arxiv.org/abs/2208.14558v2
- OCR: https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html · https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html · https://docling-project.github.io/docling/concepts/OCR_native/ · https://github.com/mindee/doctr/blob/main/doctr/datasets/vocabs.py · https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 · https://docs.cloud.google.com/document-ai/docs/languages
- Agenți: https://pypi.org/pypi/langgraph/json · https://pypi.org/pypi/pydantic-ai/json · https://pypi.org/pypi/openai-agents/json · https://www.morphllm.com/ai-agent-framework · https://www.noqta.tn/en/blog/ai-agent-frameworks-langgraph-crewai-openai-sdk-comparison-2026 · https://rickhigh.substack.com/p/langgraph-vs-crewai-vs-claude-agent
- Evaluare: https://futureagi.com/blog/best-open-source-eval-frameworks-2026 · https://techsy.io/en/blog/llm-evaluation-framework-open-source
- Validatori: https://schwifty.readthedocs.io/en/latest/ · https://npmjs.org/package/romanian-personal-identity-code-validator · https://npmjs.org/package/js-romanian-cnp-validation · https://classic.yarnpkg.com/en/package/parsecnp · https://packagist.org/packages/alcea/cif · https://packagist.org/packages/oriceon/cnp · https://packagist.org/packages/mmltech/cnp-decoder · https://github.com/mtarnovan/validators_ro · https://codeclimate.com/github/mtarnovan/romanianvalidators/README.md/source · https://mynixos.com/nixpkgs/package/rPackages.rocnp
- e-Factura tooling: https://pypi.org/project/anafpy/ · https://anafpy.readthedocs.io/en/latest/library/efactura/ · https://apps.odoo.com/apps/modules/15.0/l10n_ro_account_edi_ubl
