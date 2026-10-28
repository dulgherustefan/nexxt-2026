# Synthetic-data demo build reference: Romanian bank back-office AI agent (identifiers, documents, banking formats, datasets, tooling), as of 28 Oct 2026

_Context: NEXXT Summit 2026 hackathon, Raiffeisen track "AI for Operational Efficiency" (synthetic data only). Every identifier in these notes is synthetic. I computed the worked examples locally with my own code, which implements the cited algorithms. "Unverified" marks claims I could not confirm against a primary source._

---

## 1. Romanian identifiers and their validation algorithms (CNP, IBAN, CUI/CIF, ONRC, CI/CEI, passport)

### Takeaway
All core Romanian identifiers can be generated and validated offline with simple checksums:
- **CNP:** 13 digits, weights 279146358279, mod 11, a remainder of 10 gives 1.
- **CUI/CIF:** 2–10 digits, weights 753217532, ×10 mod 11 mod 10.
- **RO IBAN:** 24 characters: "RO" + 2 check digits + a 4-letter BIC bank code (e.g. RZBR for Raiffeisen) + 16 alphanumerics, checked with ISO mod-97.
- **ONRC registration number:** since 26 Jul 2024, a 14-character `YAAAAXXXXXXJJC` with a check digit (the algorithm is not officially published).

For ID documents, the legacy CI has a 2-line TD2 MRZ. The new electronic CEI (national rollout from 20 Mar 2025) has a 3-line TD1 MRZ and does not print the address. Passports use a TD3 MRZ.

### Cited Findings

**CNP (Cod numeric personal)**
- 13 digits in 7 components, S AA LL ZZ JJ NNN C:
  - S = sex/century.
  - AA = last two digits of the birth year, LL = month (01–12), ZZ = day.
  - JJ = county or Bucharest sector of birth/registration.
  - NNN = serial 001–999, separating people with the same sex, place and date of birth.
  - C = control digit.
  — [Wikipedia RO – Cod numeric personal](https://ro.wikipedia.org/wiki/Cod_numeric_personal_(Rom%C3%A2nia))
- S values: 1/2 = male/female born 1900–1999; 3/4 = 1800–1899; 5/6 = 2000–2099; 7/8 = male/female residents (foreigners). The RO Wikipedia page does not list 9 — [Wikipedia RO](https://ro.wikipedia.org/wiki/Cod_numeric_personal_(Rom%C3%A2nia))
- python-stdnum accepts first digits 1–9. Its source comment says 7/8 are foreign residents and 9 is "another foreigner (apparently only used as NIF)". It has no century mapping for 7/8/9 and falls back to 1900 — [python-stdnum ro/cnp.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cnp.py)
- County codes JJ:
  - 01 Alba, 02 Arad, 03 Argeș, 04 Bacău, 05 Bihor, 06 Bistrița-Năsăud, 07 Botoșani, 08 Brașov, 09 Brăila, 10 Buzău
  - 11 Caraș-Severin, 12 Cluj, 13 Constanța, 14 Covasna, 15 Dâmbovița, 16 Dolj, 17 Galați, 18 Gorj, 19 Harghita, 20 Hunedoara
  - 21 Ialomița, 22 Iași, 23 Ilfov, 24 Maramureș, 25 Mehedinți, 26 Mureș, 27 Neamț, 28 Olt, 29 Prahova, 30 Satu Mare
  - 31 Sălaj, 32 Sibiu, 33 Suceava, 34 Teleorman, 35 Timiș, 36 Tulcea, 37 Vaslui, 38 Vâlcea, 39 Vrancea, 40 București
  - 41–46 București Sectors 1–6; 47 and 48 Sectors 7 and 8 (both "desființat", i.e. abolished)
  - 51 Călărași, 52 Giurgiu
  - 70: a single code "for any registration regardless of the county where the birth took place", applicable once the Sistemul Informatic Integrat is in operation
  — [Wikipedia RO](https://ro.wikipedia.org/wiki/Cod_numeric_personal_(Rom%C3%A2nia))
- python-stdnum accepts the same codes plus 70 ("Any") and 80–83 ("Unknown") — [python-stdnum ro/cnp.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cnp.py). A commercial KYC OCR vendor maps county code 80 to "Outside_Romania" and 0 to invalid — [Druid – New Romanian Identity Cards OCR](https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/New%20Romanian%20Identity%20Cards%20OCR.htm)
- Control digit: multiply the first 12 digits by the matching digit of 279146358279, sum, divide by 11. A remainder below 10 is C; a remainder of 10 gives C = 1 — [Wikipedia RO](https://ro.wikipedia.org/wiki/Cod_numeric_personal_(Rom%C3%A2nia)). python-stdnum implements the same weights (2,7,9,1,4,6,3,5,8,2,7,9) with the 10→1 rule. Its source notes the algorithm "has not been confirmed by an independent source". Its doctest valid example is `1630615123457` (Cluj) — [python-stdnum ro/cnp.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cnp.py)

**CUI / CIF (Cod unic de înregistrare / Cod de identificare fiscală)**
- CUI is assigned to companies that must register with the Trade Register. CIF is the same kind of number for entities without that obligation. The terms are often used interchangeably, and an "RO" prefix indicates VAT registration — [python-stdnum ro/cui.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cui.py)
- Algorithm, all from the same source — [python-stdnum ro/cui.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cui.py):
  - Strip "RO". The last digit is the check digit.
  - Left-pad the remaining digits to 9 and multiply by weights 7,5,3,2,1,7,5,3,2.
  - Take the sum ×10 mod 11 mod 10, so a remainder of 10 gives 0.
  - Valid length is 2–10 digits, digits only, no leading 0.
  - Doctests: `18547290` valid, `18547291` invalid, and `RO 185 472 90` accepted.

**Romanian IBAN**
- Romania IBAN: 24 characters, `RO kk bbbb cccc cccc cccc cccc` (BBAN format 4a,16c). bbbb is the "BIC Bank code (first four alpha characters)" and cccc is the "Branch code and account number (bank-specific format)" — [Wikipedia – IBAN](https://en.wikipedia.org/wiki/International_Bank_Account_Number)
- A search snippet of the BNR IBAN regulation says the code has 24 alphanumeric characters, with segments defined in Annex 1 (I could not open the PDF myself) — [BNR Reg. IBAN](https://www.bnr.ro/files/d/Legislatie/EN/Reg_IBAN.pdf). A secondary source gives the same structure: RO + 2 check digits + 4-letter bank code + 16 characters — [folositor.ro](https://folositor.ro/glosar/iban). The check digits use MOD 97 (ISO 13616) — [Qonto](https://qonto.com/es/iban/romania)
- Validation:
  1. Check the length.
  2. Move the first 4 characters to the end.
  3. Convert letters to numbers (A=10 … Z=35).
  4. The integer mod 97 must equal 1.
- Generation:
  1. Set the check digits to "00".
  2. Rearrange and convert as above.
  3. Check digits = 98 − (n mod 97), zero-padded to 2 digits.
  — [Wikipedia – IBAN](https://en.wikipedia.org/wiki/International_Bank_Account_Number)
- Bank codes:
  - RZBR = Raiffeisen Bank; BTRL = Banca Transilvania; BRDE = BRD — [Slash](https://www.slash.com/routing-numbers/country/romania)
  - RNCB = BCR; INGB = ING — [folositor.ro](https://folositor.ro/glosar/iban)
- Faker's ro_RO bank provider holds 40 Romanian SWIFT bank codes — [Faker bank/ro_RO source](https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/bank/ro_RO/__init__.py):
  - NBOR, ABNA, BUCU, ARBL, MIND, BPOS, CARP, RNCB, BROM, BITR
  - BRDE, BRMA, BTRL, DAFB, MIRB, CECE, CITI, CRCO, FNNB, EGNA
  - BSEA, EXIM, UGBI, HVBL, INGB, BREL, CRDZ, BNRB, PIRB, PORL
  - MIRO, RZBL, RZBR, ROIN, WBAN, TRFD, TREZ, BACX, VBBU, DARO
- A consumer site attributes BREL to Revolut in Romania — [financer.ro](https://financer.ro/banii-tai/cate-cifre-are-un-cont-bancar/). This is unverified, and BREL may belong to another bank (see Gaps).

**ONRC registration number (număr de ordine în Registrul Comerțului)**
- Old format `YJJ/XXXX/AAAA`, e.g. J40/1234/2005: register letter / county / serial / year. python-stdnum validates it with serial ≤5 digits, county 1–2 digits and year 1990–2024 — [python-stdnum ro/onrc.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/onrc.py)
- New format `YAAAAXXXXXXJJC` from 26.07.2024, when the new ONRC IT system went live — [Contabilul.ro, 2 Oct 2024](https://contabilul.manager.ro/a/28861/atentie-iata-noul-format-al-numarului-de-ordine-din-registrul-comertului.html):
  - Y = register: J = legal persons; F = PFA, întreprinderi individuale and familiale; C = cooperative societies.
  - AAAA = year of registration.
  - XXXXXX = order number, zero-padded to 6 digits, counted separately per register type.
  - JJ = "00" for entities registered after 26.07.2024; for older entities, the county code of the last registered seat.
  - C = control digit "from an algorithm", not described in the article.
- Under the new system, the number is allocated once at national level and kept for life regardless of seat moves. Older entities receive the new-format number when they register changes to name, seat, main activity or legal form — [Contabilul.ro](https://contabilul.manager.ro/a/28861/atentie-iata-noul-format-al-numarului-de-ordine-din-registrul-comertului.html)
- python-stdnum's new-format implementation — [python-stdnum ro/onrc.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/onrc.py):
  - Docstring: "On 2024-07-26 a new format was introduced and for a while both old and new formats need to be valid". It links to a targetare.ro blog post.
  - County rules: year < 2024 → county in 1–40, 51, 52; year 2024 → county or 00; year > 2024 → 00.
  - Check digit: replace the letter with `ord(letter) % 10`, sum all digits except the last, take mod 10.
  - Doctests: `J2012000750528` valid; `J2012000750529` gives InvalidChecksum.

**Identity cards: CI (legacy), CEI (electronic), CIS (simple)**
- Legacy CI data, per [Wikipedia – Romanian identity card](https://en.wikipedia.org/wiki/Romanian_identity_card):
  - Series of 2 letters plus a card number unique to each card.
  - CNP (the same on all of a person's cards).
  - Surname, given names, sex, and nationality (which replaced parents' names in 2009).
  - Address on ID-2.
  - Issuing authority, usually "SPCLEP <City>", and issue/expiry dates in dd/mm/yyyy.
  - Two rows of machine-readable text.
- Series examples from the same page:
  - Bucharest: DP, DR, DT, RD, RR, RT, RX, RK ("MB" on the electronic card)
  - Alba: AX ("AB" on the CEI)
  - Cluj: KX, CJ; Constanța: KT, KZ; Arad: AR, ZR; Teleorman: TR
  - Iași: MX, MZ, IZ ("IS" on the CEI)
  - The series does not always match the county abbreviation.
  — [Wikipedia](https://en.wikipedia.org/wiki/Romanian_identity_card)
- ID-2 validity:
  - ages 14–17: 4 years
  - 18–24: 7 years
  - 25–54 (issued after 2 Aug 2021): 10 years or until 3 Aug 2031
  - 55+: no expiry, but cannot be used for travel after 3 Aug 2031
  — [Wikipedia](https://en.wikipedia.org/wiki/Romanian_identity_card)
- MRZ formats: a KYC vendor's validation docs list **TD1 for biometric (new) IDs, TD2 for standard IDs and TD3 for passports**. They compare the birth date and "the final 6 CNP digits" between the CNP and the MRZ on standard IDs and passports. On new cards these CNP/MRZ checks "always return N/A" — [FintechOS – Computer Vision Validations](https://docs.fintechos.com/APs/SysPack/24.5/UserGuide/Content/ComputerVision/Validations.htm)
- New-card OCR output from another KYC vendor — [Druid – New Romanian Identity Cards OCR](https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/New%20Romanian%20Identity%20Cards%20OCR.htm):
  - Identity and document: Nume, Prenume, Series, Number, DocumentNumber, Issuing Authority, DateOfIssue, ExpireDate, DateOfBirth, Sex, Cetățenie.
  - CNP plus CNP-derived DateOfBirth, Sex and CountyOfBirth.
  - Address: Domiciliu, County, Locality, StreetName, StreetNo, BuildingNo, EntranceNo, Floor, Apartment, with SIRUTA ids.
  - Three MRZ lines (MRZ1–MRZ3) and parsed fields (mrz.DocumentSeries, mrz.OptionalData…).
  - Validations: document number check digit against the 1st control digit of MRZ line 2, DOB against the 2nd and expiry against the 3rd; Sex must be F/M; CNP checksum; cross-checks of sex, DOB, issue and expiry dates between document, CNP and MRZ; locality against the SIRUTA dictionary.
  - Since Druid 9.12 it also accepts the official address certificate.
- CEI timeline: pilot in Cluj-Napoca from 2 Aug 2021; Cluj county-wide from Aug 2022; gradual national rollout from 20 Mar 2025 — [Wikipedia](https://en.wikipedia.org/wiki/Romanian_identity_card). Another source gives requests from 20 Mar 2025 in Cluj, Bucharest from early April and nationwide from May 2025, with a target of 5 million cards by June 2026 — [RFE/RL (Europa Liberă)](https://romania.rferl.org/a/cartea-electronica-de-identitate/33354995.html)
- CEI facts, per [RFE/RL](https://romania.rferl.org/a/cartea-electronica-de-identitate/33354995.html):
  - The address is **not printed**; it is stored electronically.
  - The chip supports "11 servicii digitale"; holders get a PIN for MAI apps; the card can produce electronic signatures.
  - Series printed in tiny characters on the back and engraved right of the photo.
  - Valid as an EU travel document.
  - Validity: first card for children 2 years; ages 2 to under 14: 4 years; 14–18: 5 years; 18+: 10 years.
  - Free up to 5 million copies (PNRR-funded).
- Because CEIs do not print the address, institutions without chip readers ask for separate proof of domicile — [HotNews](https://hotnews.ro/romanii-care-au-buletine-noi-cu-cip-se-plang-ca-trebuie-sa-aduca-dovada-domiciliului-la-ghisee-pentru-ca-nu-exista-cititoare-mai-raspunde-ca-a-trimis-institutiilor-mesaje-de-responsabilizar-2112313); [Wall-Street.ro](https://www.wall-street.ro/articol/fara-categorie/problema-adresei-din-cei-mai-promite-ca-de-marti-va-exista-o-rezolvare.html)
- CIS (carte de identitate simplă): issued from 20 May 2025, no chip, address printed, not a travel document, 39 lei — [RFE/RL](https://romania.rferl.org/a/cartea-electronica-de-identitate/33354995.html)

**Passport**
- KYC vendor extraction of Romanian passports — [Druid – Romanian Passports OCR](https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/Romanian%20Passport%20OCR.htm):
  - Fields: Type, IssueState, DocumentNumber (the example has 9 digits), Issuer, IssueDate, DateOfExpiry, LastName, FirstName, Citizenship, DateOfBirth, PlaceOfBirth, Sex, **CNP**, and a 2-line MRZ (MRZ1, MRZ2).
  - Checks: the same MRZ line-2 control digits as the ID card, plus cross-checks of CNP, document and MRZ.
- A second vendor validates the passport MRZ against TD3 and compares the last 6 CNP digits between the CNP and the MRZ — [FintechOS](https://docs.fintechos.com/APs/SysPack/24.5/UserGuide/Content/ComputerVision/Validations.htm)

### Inferences

**Worked examples (computed locally, all synthetic):**
- CNP `1630615123457` (stdnum doctest): weighted sum 216, 216 mod 11 = 7 ✓.
- CNP `6010315431239`: female, born 15.03.2001, Bucharest Sector 3 (43), serial 123. The sum 141 mod 11 = 9, so C = 9.
- CNP `1900101401091`: the sum 175 mod 11 = 10, so C = **1**. This is a good unit test for the 10→1 rule.
- CUI `12345674`: 001234567 × 753217532 = 95, 95 × 10 = 950, 950 mod 11 = 4. stdnum's `18547290` also validates.
- IBAN `RO54RZBR0000060012345678` passes mod-97. The 16-character account part is arbitrary because Raiffeisen's internal account structure is not public.
- ONRC: J40/1234/2005 would become `J2005001234405` under stdnum's algorithm. A 2025 registration with serial 123 becomes `J2025000123009`.
- ICAO 7-3-1 MRZ check: my implementation reproduces the ICAO 9303 specimen values (`L898902C3` → 6, `740812` → 2). It weights characters 7,3,1 repeating; digits keep their value, A–Z = 10–35 and '<' = 0; the result is the sum mod 10.

**Reference implementation** for the team, using the cited rules:
```python
def cnp_cd(d12): r = sum(int(a)*int(b) for a,b in zip(d12,"279146358279")) % 11; return 1 if r==10 else r
def cui_cd(body): return sum(int(a)*int(b) for a,b in zip(body.zfill(9),"753217532"))*10 % 11 % 10
def iban_cd(cc,bban): n=int("".join(str(int(c,36)) for c in bban+cc+"00")); return f"{98-n%97:02d}"
def onrc_cd(first13): return sum(int(c) for c in str(ord(first13[0])%10)+first13[1:]) % 10   # unofficial
def mrz_cd(s): v=lambda c:0 if c=="<" else int(c) if c.isdigit() else ord(c)-55; return sum(v(c)*(7,3,1)[i%3] for i,c in enumerate(s))%10
```

**Document-specific inferences:**
- **Legacy CI (TD2):** by the ICAO TD2 layout, line 2 has 36 characters: document number (series + 6 digits + '<'), check, "ROU", DOB, check, sex, expiry, check, 7 characters of optional data, composite check. Vendors compare "the final 6 CNP digits" with the MRZ, so the 7-character optional field very likely holds the CNP's S digit plus its last 6 digits. That would let an agent rebuild the full CNP as S + DOB + last six and cross-check it against the printed CNP. This is unverified; confirm on a PRADO specimen.
- **CEI (TD1, 3×30):** CNP/MRZ checks return N/A on new cards, so the CEI MRZ probably does not carry the CNP. The agent would have to OCR the CNP from the card face and get the address from the chip or from a separate proof of domicile, such as the certificat de atestare a domiciliului. "CEI + dovadă de domiciliu" is a realistic KYC-update scenario for a demo.
- **Realism for synthetic CNPs:** use county codes 01–46, 51 and 52, and add edge cases (47/48 abolished sectors, 70, a remainder-10 check digit, and S = 7/8 foreign residents) as negative or rare tests.
- **IBANs:** use a real bank code (RZBR for "own bank", others for counterparties) with random 16 digits and computed check digits. Label the data as synthetic, since random accounts could collide with real ones.

### Gaps
- I could not read the BNR IBAN regulation's Annex 1 (the fetch returned only site navigation), so there is no authoritative list of Romanian bank codes here. The codes rely on Faker's list and secondary sources.
- The BREL attribution is unverified. financer.ro attributes it to Revolut; my own unverified recollection is that BRELROBU is Libra Internet Bank's BIC.
- The ONRC check-digit algorithm is not in any official text I found. python-stdnum's version traces to a blog post (targetare.ro). The legal basis for the new number format, possibly Legea 265/2022 on the Trade Register, is unconfirmed.
- The official definitions of CNP first digit 9 and county codes 70/80–83 (which legal act, and whether 70 is already in use) were not found.
- I could not verify the exact MRZ layouts of the CI (TD2), CEI (TD1) and passport (TD3), including their optional-data contents, against PRADO (HTTP 403) or ICAO Doc 9303 (not fetched). The full printed field list of the CEI and the presence and position of a CAN were not confirmed by an official MAI source.
- The passport number format and whether the CNP is printed or encoded in the MRZ personal-number field rest only on vendor evidence.

---

## 2. Typical Romanian documents: fields, layout, official templates

### Takeaway
Most back-office documents have no single national template:
- Each bank publishes its own "adeverință de venit tip". Libra Internet Bank's 2024 Anexa 1 is a complete public example.

State-defined formats do exist for the following:
- **e-Factura:** UBL 2.1 + CIUS-RO XML, CustomizationID set by OMF 4092/2022.
- **ANAF garnishment on bank accounts:** fully electronic since 1 Oct 2023 under OPANAF 878/2022 as amended by OPANAF 626/2023, with an ANAF–ARB–banks protocol.
- **ONRC documents:** the certificat constatator, and beneficial-owner declaration forms 6/6A.
- **Chitanță:** form 14-4-1 under OMFP 2634/2015.

For the remaining documents (procură, certificat de moștenitor, the bailiff's poprire), only partial or secondary information was found.

### Cited Findings

**Adeverință de venit (employer income certificate for lending)**
- Libra Internet Bank's "Anexa 1 – Adeverinta de venit tip" (2 pages, PDF dated 12 Mar 2024) — [Libra Internet Bank template PDF](https://www.librabank.ro/documente/Adeverinta_venit.pdf) (text extracted locally with pdftotext). Its fields in order:
  - **Header:** full employer name ("denumirea completa a unitatii"), C.U.I., "Nr. de ordine in registrul Comertului J…/…/…", Tel./Fax, contact person and their function.
  - **Title:** "ADEVERINTA DE VENIT".
  - **Body:**
    - Employer: registered seat (str., nr., bl., sc., et., ap., județ/sector) and legal representative with their capacity.
    - Employee: name and CNP; employed for a period "nedeterminata incepand cu data de…" or "determinata de la data de … pana la data de …".
    - Job and education: "Functia ocupata in prezent (conform COR)"; last school graduated, as checkboxes (școală generală / liceu / universitate / studii post-universitare).
    - Seniority: uninterrupted seniority at the previous employer, the gap between jobs, and total seniority.
    - Deductions: "Salariul este grevat de retineri lunare: DA / NU", the monthly amount of deductions and the reason ("CAR, rate, popriri, alte retineri legale").
  - **Income table:** previous year plus the current year up to the month before issue (the sample has 16 months, Sep 2023–Dec 2024). Columns:
    - Luna / An
    - Salariul de încadrare: gross base salary without bonuses, per the CIM / Registrul general de evidență a salariaților
    - Salariul net (aferent salariului de încadrare)
    - Norma de hrană (net), Norma de echipament (net), Bonuri de masă
    - Alte bonusuri/sporuri nete cu caracter permanent
    - Alte bonusuri/sporuri nete cu caracter ocazional
  - **Footnotes and closing:**
    - Footnote: "*Se va completa salariul net, fara a fi adaugate alte beneficii salariale".
    - A responsibility statement.
    - A statement that the company "se afla / nu se afla" in an insolvency procedure under Legea nr. 85/2014.
    - Signatory function, name and signature, and the company stamp.
    - A note that any additions, erasures or corrections must carry the issuer's signature and/or stamp.
- Other bank and leasing templates exist, for example [BT Direct](https://www.btdirect.ro/storage/app/media/documente/Adeverinta-de-venit.pdf) (HTTP 403 when fetched) and [Porsche Finance](https://www.porschefinance.ro/files/romania/documente/Adeverinta-de-venit-pentru-leasing-persoane-fizice.pdf). According to the search snippet, the Porsche Finance template has one row per month for the last 6 months with net income, total gross income and permanent bonuses listed separately.
- ANAF issues a separate fiscal income certificate ("adeverință de venit") whose model and content were approved by OANAF 3396/2016. It is based on fiscal records and is not a bank form — [legeaz.net – OANAF 3396/2016](https://legeaz.net/monitorul-oficial-955-2016/oanaf-3396-model-continut-adeverinta-venit)

**Extras de cont (bank statement)**
- Raiffeisen's corporate Internet Banking guide (Feb 2024) has an "Extras de cont" section. I did not confirm which export formats it supports — [Raiffeisen Ghid Internet Banking Corporații](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/corporatii/20240201-Ghid-utilizare-Internet-Banking-Corporatii.pdf)
- The Romanian ERP WinMentor documents importing bank statements in MT940 format — [WinMentor – Import extrase de cont în format MT940](https://portal.winmentor.ro/wme/docs/down/solutii_suport/Service/Import%20date%20din%20alte%20aplicatii/WME%20-%20Import%20extrase%20de%20cont%20in%20format%20MT.doc)

**Adresă de înființare a popririi (garnishment order), ANAF**
- ANAF's form set includes "adresa de infiintare a popririi asupra disponibilitatilor banesti" and "adresa de instiintare privind infiintarea popririi" (per search snippet) — [Fiscalitatea – ANAF a schimbat 9 formulare](https://www.fiscalitatea.ro/anaf-a-schimbat-9-formulare-17133/)
- From 1 Oct 2023, OPANAF 878/2022 applies, as amended by OPANAF 626/2023. It sets the electronic means for transmitting enforcement acts. Under a protocol between ANAF, the Asociația Română a Băncilor (ARB) and credit institutions, enforcement acts reach banks automatically and electronically. The bank-side procedure — [ProCredit Bank notice on the ANAF e-poprire protocol](https://procreditbank.ro/wp-content/uploads/files/Protocolul%20de%20colaborare%20privind%20implementarea%20sistemului%20de%20instituire%20electronica%CC%86%20a%20popririi%20asupra%20conturilor%20bancare.pdf) (text extracted locally):
  1. Every working day at **15:30** the bank sends the "sold cert", i.e. the amount payable from the debtor's accounts, for each electronically received fiscal poprire.
  2. After that, the blocked amount cannot be touched. Withdrawals under art. 236(14) of the Codul de procedură fiscală (salaries, excise duties, obligations that keep a payment facility valid) are no longer approved.
  3. The next working day ANAF sends a **firm payment instruction**, bank by bank, based on each bank's sold cert. The bank executes it the same day, and ANAF alone decides which bank pays and how much.
  4. If ANAF does not request payment, the amount stays blocked until an "instrucțiune de sistare a popririi" arrives.
  5. The same timings apply to garnishments from other enforcement bodies that compete with ANAF's (art. 220(13) together with art. 236(11) CPF).
- ANAF's H1 2025 activity report mentions an e-Popriri system. It also cites 581,804 "adrese de înființare a popririi asupra sumelor datorate debitorilor de către terți" issued in that period. This figure is per search snippet and may cover third-party garnishments beyond bank accounts — [ANAF Raport de activitate S1 2025](https://static.anaf.ro/static/10/Anaf/Informatii_R/18.08.2025%20-%20Raport%20de%20activitateANAF_2025S1_V7.pdf)
- OPANAF 626/2023 also covers how the amounts in the garnishment address are applied — [OPANAF 626/2023](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_626_2023.pdf)

**Certificat constatator (ONRC)**
- Typical content: ONRC number, company name, legal form, CUI, registered office, company status, CAEN codes (main and secondary), share capital, administrators and associates/shareholders — [StartCo blog](https://startco.ro/blog/certificatul-constatator-ce-este-si-pentru-ce-il-folosesti/)
- Variants: "de bază", "fonduri IMM" (with financial data) and "pentru insolvență". It can be obtained online or at the counter for about 30 lei (blog figure; check the ONRC tariff) — [Bono.ro](https://bono.ro/blog/certificat-constatator)

**Declarație privind beneficiarul real (beneficial owner declaration, ONRC)**
- Under Legea 129/2019 art. 19(5), companies registered in the trade register file the declaration at ONRC — [Fiscalitatea](https://www.fiscalitatea.ro/declaratia-de-beneficiar-real-ce-este-unde-se-depune-si-cine-trebuie-sa-completeze-formularul-21828/)
- The annual filing requirement was dropped by Legea 315/2021. A declaration is now filed at registration and at each change, with one source citing 15 days after a change — [Fiscalitatea (Legea 315/2021)](https://www.fiscalitatea.ro/declaratia-privind-beneficiarii-reali-nu-mai-trebuie-depusa-anual-insa-anumite-persoane-au-in-continuare-aceasta-obligatielegea-315221-21596/); [Fiscalitatea](https://www.fiscalitatea.ro/declaratia-privind-beneficiarul-real-formularul-se-depune-in-fiecare-an-sau-numai-atunci-cand-apar-modificari-22299/)
- ONRC form-type models: no. 6, used when the declaration is made before the ONRC representative, and no. 6A, orientative, for declarations under private signature — [Fiscalitatea](https://www.fiscalitatea.ro/onrc-anunta-ca-au-fost-elaborate-noi-modele-de-declaratii-privind-beneficiarii-reali-21240/)
- It can be filed at the counter, through a notary or lawyer, or online with a qualified e-signature on the ONRC portal — [Bono.ro](https://bono.ro/blog/declaratie-beneficiar-real); ONRC filing guide — [ONRC ghid completare cerere BR](https://www.onrc.ro/documente/ghid%20completare%20cerere%20de%20depunere%20declaratie%20BR.pdf)
- Fines of up to 10,000 lei are reported, but sources disagree — [Fiscalitatea](https://www.fiscalitatea.ro/declaratia-privind-beneficiarii-reali-2025-amenzile-ajung-pana-la-10000-lei-pentru-nedepunere-24002/)

**Procură notarială (notarial power of attorney)**
- RNNEPR (Registrul Național Notarial de Evidență a Procurilor și a Revocării acestora) is the national electronic register, kept by UNNPR, of notarial powers of attorney and their revocations — [notari.pro](https://notari.pro/dictionar-juridic-dex/rnnepr); [European e-Justice](https://e-justice.europa.eu/topics/family-matters-inheritance/inheritance/information-authorities-issuing-ecs/ro_en)
- Civil Code art. 2033: the notary who authenticates the revocation of an authentic power of attorney must send it to the national register immediately — [legeaz.net – Cod civil art. 2033](https://legeaz.net/noul-cod-civil/art-2033-publicitatea-revocarii-procurii-autentice-notariale-mandatul-cu-reprezentare-contractul-de-mandat)

**e-Factura (RO e-Factura, UBL 2.1 + CIUS-RO)**
- CustomizationID per OMF 4092/2022: `urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1` — [OMF 4092/2022](https://static.anaf.ro/static/10/Anaf/legislatie/OMF_4092_2022.pdf). An older value, `…:RO_CIUS:1.0.0.2021`, still appears in a .NET package — [RoeFactura (NuGet)](https://packages.nuget.org/packages/RoeFactura)
- RO_CIUS is the national usage specification of EN 16931. UBL and CII are both accepted, and UBL is the more common. Validation runs XSD plus Schematron, code lists and total reconciliation. Common rejections — [EDIconnect](https://www.ediconnect.ro/en/e-invoice/ubl-xml-e-invoice):
  - non-standard units of measure
  - missing VAT exemption codes
  - totals that do not reconcile with the lines
  - wrong country codes
  - incomplete partner identifiers
- Third-party validator tools state that they use the Schematron package **ro16931-ubl 1.0.9 (effective 2024-06-05)** — [Apify Romania e-Factura Validator](https://apify.com/kamerozkan/romania-efactura-validator). Another notes that the ANAF validator in SPV remains authoritative — [demoanaf.ro](https://demoanaf.ro/en/efactura/validare). Both are third-party claims.
- ANAF validation API, per a community library: `POST https://api.anaf.ro/prod/FCTEL/rest/validare/{FACT1|FCN}` with OAuth2, plus a public no-auth variant on webservicesp.anaf.ro. The test host returns 404 for validation — [anafpy docs](https://anafpy.readthedocs.io/en/latest/anaf-reference/efactura/api/)
- Timelines:
  - B2B reporting mandatory from 1 Jan 2024; B2C from 1 Jan 2025, with B2C penalties from 1 Jul 2025 — [Fiscalitatea](https://www.fiscalitatea.ro/e-factura-b2c-23791/); [StartupCafe](https://startupcafe.ro/e-factura-b2c-perioada-fara-sanctiuni-expira-in-iunie-2025-ce-amenzi-risca-firmele-82751)
  - Transmission deadline of 5 calendar days from 1 Jul 2024 — [Economedia](https://economedia.ro/cum-se-calculeaza-termenul-de-transmitere-a-facturilor-in-sistemul-national-ro-e-factura.html). This is contradicted by a blog claiming 5 working days from 1 Jan 2026 — [Bono.ro](https://bono.ro/blog/ghid-ro-e-factura).

**Chitanță (cash receipt)**
- OMFP 2634/2015 on financial-accounting documents was published in MO 910 on 9 Dec 2015 and applies from 1 Jan 2016. Annex 1 sets the mandatory elements (points 2 and 10) and Annex 3 holds the models — [avocatnet](https://www.avocatnet.ro/articol_42147/Ordinul-MFP-nr-2634-2015-documentele-financiar-contabile.html); [Contabilul.ro](https://contabilul.manager.ro/a/16855/ordinul-mfp-nr-26342015-privind-documentele-financiar-contabile.html)
- The receipt is form code 14-4-1. The foreign-currency receipt is 14-4-1/a, and receipts are issued in 2 copies — [Rubinian](https://www.rubinian.com/dictionar/chitanta-pentru-operatiuni-in-valuta); [Fiscalitatea case study](https://www.fiscalitatea.ro/studiu-de-caz-consecintele-suportate-de-o-societate-in-cazul-unor-chitante-intocmite-incorect-2509/)

### Inferences
- **Highest-fidelity synthetic documents for a 1–2 day build:**
  - adeverință de venit (clone the Libra template structure in HTML, with a 6–16 month table)
  - e-Factura (generate UBL XML, validate it with the Schematron, render a PDF view)
  - poprire (a JSON "electronic act" plus a PDF "adresă" letter, simulating the 15:30 sold-cert to firm-instruction cycle)
  - certificat constatator (data fields are well known)
  - extras de cont (rendered from the same ledger that produces MT940/camt.053)
  - CI/CEI card images with MRZ
- **Agent tasks that exercise the validators:**
  - Cross-check the CNP across the CI, the adeverință and the procură.
  - Cross-check the CUI and ONRC number across the adeverință, the certificat constatator and the e-Factura.
  - Recompute average net income from the adeverință and reconcile it with salary credits in the extras de cont.
  - Flag "rețineri/popriri = DA" and insolvency statements.
  - Detect expired IDs and CEI cases with missing proof of address.
  - Compute the poprire "sold cert" excluding exempt amounts.
- **Poprire letters:** include the issuing body (ANAF unit or executor judecătoresc), enforcement file number, debtor name and CNP/CUI, amount owed, Treasury account for payment, and legal basis (CPF art. 236 for ANAF; Codul de procedură civilă for bailiffs). This field list is inferred, not taken from an official model.

### Gaps
- I did not retrieve the official current ANAF model of the "adresă de înființare a popririi asupra disponibilităților bănești", or the data schema of the ANAF–bank e-poprire exchange. The Intesa protocol PDF returned HTTP 403.
- I did not research bailiff garnishments (executor judecătoresc, Codul de procedură civilă) or the amounts exempt from garnishment.
- No official template or field list was found for the certificat de moștenitor or the procură notarială, nor any description of how banks query RNNEPR. The general content I would expect (notary office, încheiere de autentificare number and date, parties identified by name, CNP and ID series/number, powers or estate composition, heirs' shares) is background knowledge only and unverified.
- The exact mandatory fields of chitanța 14-4-1 (OMFP 2634/2015 Annex 1 and 3) were not retrieved.
- Raiffeisen's own adeverință template was not found online. The fields of ONRC beneficial-owner forms 6/6A, and the content of an October 2025 amendment to Legea 129/2019 mentioned in search results, were not retrieved.
- I did not retrieve an official layout or specimen of the certificat constatator. CAEN Rev. 3 code changes, which affect realism, were not checked.
- The official ANAF e-Factura technical page (mfinante.gov.ro/ro/web/efactura/informatii-tehnice) failed twice with ECONNRESET. That leaves the CIUS-RO 1.0.9 Schematron and the upload, stareMesaj, listaMesaje and descarcare endpoints unconfirmed against primary sources, along with the following CIUS-RO rules I remember but could not verify:
  - county as ISO 3166-2:RO (e.g. RO-CJ)
  - Bucharest sectors written as "SECTOR1"…"SECTOR6"
  - InvoiceTypeCode values 380/381/384/389/751

---

## 3. Banking file formats (MT940/MT942, camt.053/054, pain.001/pacs.008, card clearing) and reconciliation fields

### Takeaway
- **Statements:** MT940 is still used for corporate statements in Romania (local ERPs import it), but ISO 20022 is the direction.
- **Domestic payments:** a Romanian bank branch already accepts pain.001.001.09 for domestic SENT/ReGIS transfers, and ReGIS connectivity runs on ISO 20022 XML.
- **Reconciliation keys:** in camt.053/054 they are EndToEndId, AcctSvcrRef, BkTxCd and RmtInf; in MT940, the :61: references plus the :86: narrative.
- **Card clearing:** formats are network-proprietary (Mastercard IPM via GCMS and T112 files, ISO 8583-based; Visa BASE II TC records) and members-only, so a demo should use a simplified, documented schema.

### Cited Findings
- **MT940 structure** — [SEPA for Corporates – MT940](https://www.sepaforcorporates.com/swift-for-corporates/account-statement-mt940-file-format-overview/)

  | Tag | Content | Status | Format |
  |---|---|---|---|
  | :20: | Transaction Reference Number | M | 16x |
  | :21: | Related Reference | O | |
  | :25: | Account Identification | M | 35x |
  | :28C: | Statement / sequence number | M | 5n[/5n] |
  | :60F: / :60M: | Opening balance: D/C mark, date YYMMDD, currency, amount | M | 1!a6!n3!a15d |
  | :61: | Statement line | O | see below |
  | :86: | Information to account owner | O | 6x65x |
  | :62F: / :62M: | Closing booked balance | M | |
  | :64: | Closing available balance | O | |
  | :65: | Forward available balance | O | |

- **MT940 :61: format** `6!n[4!n]2a[1!a]15d1!a3!c16x[//16x][34x]` breaks down into — [SEPA for Corporates](https://www.sepaforcorporates.com/swift-for-corporates/account-statement-mt940-file-format-overview/):
  - value date
  - entry date (MMDD)
  - debit/credit mark
  - funds code
  - amount
  - transaction type identification code
  - reference for the account owner
  - account-servicing institution reference
  - supplementary details
- **camt.053 reconciliation elements:**
  - **AcctSvcrRef:** reference the bank assigns to each entry, used for reconciliation and disputes.
  - **EndToEndId:** set by the payer and preserved unchanged through the payment chain. It can carry an invoice number.
  - **BkTxCd:** ISO three-level Domain/Family/SubFamily code, or a proprietary code.
  - **RmtInf:** unstructured text, or structured data such as a creditor reference.
  — [Goldman Sachs TxB – ISO reconciliation best practices](https://developer.gs.com/docs/services/transaction-banking/best-practices-iso-recon/); [Oracle EPM – BAI/MT940/CAMT.053](https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/diepm/integrations_bai_adding_source_104x758c3e29_106x758c5280.html); [Numeral – camt.053.001.08 XSD](https://docs.numeral.io/docs/camt053-xsd-business-logic); [ING CAMT sample files](https://assets.ing.com/m/19ba05999348c5c7/original/Sample-Files-CAMT.pdf)
- Batch entries in camt.053 can be reconciled at transaction level using camt.054 — [Continia](https://docs.continia.com/da-dk/continia-banking/business-functionality/payment-import/bank-account-statement/reconciling-camt054-entries-from-camt053/)
- **Romanian domestic payments (PKO BP Romania branch, notice dated 24.09.2026)** — [PKO BP Romania](https://www.pkobp.pl/en/romania-branch/news/changes-to-domestic-sent-and-regis-transfers):
  - Accepts **pain.001.001.09** for imports of domestic SENT/ReGIS transfers.
  - Still supports MT103, Elixir-0, CSV, pain.001.001.07 and pain.001.001.03.
  - New separate name and address fields (country, town, postal code).
  - Counterparty identified by either a 20-character LEI or a CNP/CUI.
- **ReGIS (BNR's RTGS):** Allevo connected 17 banks, about half the market, using XML ISO 20022 — [Forbes România](https://www.forbes.ro/?p=374165); [The Paypers](https://thepaypers.com/fintech/news/allevo-provides-17-banks-with-access-to-the-regis-system)
- **SENT and instant payments:** SENT is TransFond's retail clearing system, settled via ReGIS for RON and TARGET2 for EUR — [TransFi](https://www.transfi.com/jp/blog/romanias-payment-rails-how-they-work---sent-sepa-instant-transfers). TransFond runs Plăți Instant with central-bank settlement — [platiinstant.ro](https://www.platiinstant.ro/en/the-service). Instant payment volume rose about 93% in the first ten months of 2024 — [Economedia](https://economedia.ro/?p=219575)
- **Card clearing:**
  - Mastercard IPM is the standard file format for clearing through GCMS, based on ISO 8583 — [Afferent Software](https://afferentsoftware.com/?p=3666)
  - Reconciliation uses the Reconciliation/1644 messages in the T112 IPM clearing file — [Paymentology](https://developer.paymentology.com/docs/data-reconciliation-report); [Paymentology – clearing, settlement, reconciliation](https://developer.paymentology.com/bankinglive/docs/txn-clearing-settlement-reconciliation)
  - Visa BASE II is the core mechanism for exchanging interchange data and settling between acquirers and issuers — [Intelica](https://www.intelica.com/en/blog/mastercard-visa-clearing-process)
  - Visa capture-file docs reference TC 05 clearing records and TC 90/91/92 (file header, batch, trailer) — [Visa Acceptance – capture file](https://developer.visaacceptance.com/docs/vas/en-us/payments/acq/all/na/payments-acq/payments-acq-references-capture-file.html)
  - ARN is used alongside BRN and TRC to match transactions — [Mastercard developer](https://developer.mastercard.com/fld-fraud-submission/documentation/parameters/fda-req-res-complete/)
  - The Python library `cardutil` parses Mastercard IPM files — [cardutil docs](https://cardutil.readthedocs.io/en/latest/api.html)

### Inferences
- **Demo design:** generate one synthetic ledger and export it as pain.001 (outgoing), camt.053.001.08 (XML statement), MT940 (text statement) and a PDF extras de cont.
- **Reconciliation agent matching:**
  - pain.001 `PmtId/EndToEndId` ↔ camt.053 `Ntry/NtryDtls/TxDtls/Refs/EndToEndId`
  - invoice numbers in `RmtInf/Ustrd` or :86: ↔ e-Factura IDs
  - amounts and dates ↔ :61:
  - The agent escalates unmatched items with a reason.
- **Domestic realism:** use pain.001.001.09 with structured addresses, and include the counterparty CNP/CUI in identification fields, as the PKO branch now allows.
- **Card settlement simulation:** use a documented CSV with ARN (23 digits), masked PAN, auth code, RRN, transaction and settlement dates, transaction and settlement amounts and currencies, interchange fee, MCC, merchant ID and terminal ID. This mirrors the keys used in IPM/BASE II reconciliation, but the field lengths (e.g. 23-digit ARN) are unverified.

### Gaps
- No public MT940 or camt.053 implementation guide from a Romanian bank (Raiffeisen included) was found.
- The SWIFT MT940/MT942 official specs are members-only and were not accessed. MT942 (intraday interim report) was not covered by any fetched source.
- pacs.008 element-level detail was not fetched.
- TransFond's official ISO 20022 migration timeline for SENT was not found.
- The euro instant-payment and Verification of Payee obligations for Romania under the EU Instant Payments Regulation come only from a secondary source (Gadget.ro mentions 2027) and are unverified.
- Visa and Mastercard clearing specifications are proprietary, so the ARN structure and the IPM/BASE II field list are unconfirmed.

---

## 4. Public datasets usable for a demo (with licences)

### Takeaway
English-language synthetic and public financial datasets cover transactions, AML, fraud, loans, intents and complaints. There is **no Romanian banking or financial-document dataset** on Hugging Face; Romanian resources are general NLP (sentiment, NER/RE, legal corpora, instruction data). The best approach: use AMLworld or PaySim for transaction behaviour and banking77 for an intent taxonomy, then generate the Romanian layer (names, CNP/CUI/IBAN, documents, Romanian text) synthetically.

### Cited Findings
- **IBM AMLworld** (Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models", NeurIPS 2023 Datasets & Benchmarks) — [arXiv 2306.16424](https://arxiv.org/html/2306.16424v1); [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2023/hash/5f38404edff6f3f642d6fa5892479c42-Abstract.html); [Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)

  | Dataset | Transactions | Laundering transactions | Rate (1 per N) |
  |---|---|---|---|
  | HI-Small | 5M | 3.6K | 981 |
  | LI-Small | 7M | 4.0K | 1,942 |
  | HI-Medium | 32M | 35K | 905 |
  | LI-Medium | 31M | 16K | 1,948 |
  | HI-Large | 180M | 223K | 807 |
  | LI-Large | 176M | 100K | 1,750 |

  - Eight laundering patterns: fan-out, fan-in, cycle, random, bipartite, stack, scatter-gather, gather-scatter.
  - Published on Kaggle "under a Community Data License Agreement"; the paper's GNN code is under Apache.
- **PaySim:** synthetic mobile-money transactions built from one month of logs of an African mobile-money service. The Kaggle version is scaled to one quarter of the original, about 6.36M rows × 11 columns. Users are asked to cite Lopez-Rojas, Elmir and Axelsson — [Baselight mirror of Kaggle ealaxi/paysim1](https://baselight.app/u/kaggle/dataset/ealaxi_paysim1); [NTNU thesis on PaySim](https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/2588208)
- **Berka / PKDD'99 Financial:** real anonymized data of a Czech bank:
  - 8 tables, 1,090,086 rows (78.8 MB), 606 successful and 76 unsuccessful loans.
  - The repository warns of temporal leakage.
  - Publicly available from the CTU relational repository's MariaDB server.
  — [CTU Prague relational repository](https://relational.fel.cvut.cz/dataset/Financial); [KDnuggets 1999](https://www.kdnuggets.com/news/99/n09/i2.html)
- **banking77:** 13,083 English customer-service queries labelled with 77 intents, licence **CC BY 4.0** — [Hugging Face PolyAI/banking77](https://huggingface.co/datasets/PolyAI/banking77)
- **CFPB Consumer Complaint Database:**
  - Published fields: Date received, Product, Sub-product, Issue, Sub-issue, Company public response, Company, State, ZIP code, Tags, Submitted via, Date sent to company, Company response to consumer, Timely response?, Complaint ID.
  - Complaints are published after the company responds or after 15 days, without direct identifiers — [CFPB – data use](https://www.consumerfinance.gov/complaint/data-use/)
  - Narratives are published only with opt-in consent and after scrubbing — [CFPB newsroom 2015](https://www.consumerfinance.gov/about-us/newsroom/cfpb-publishes-over-7700-consumer-complaint-narratives-about-financial-companies); [CFPB Narrative Scrubbing Standard](https://files.consumerfinance.gov/a/assets/201503_cfpb_Narrative-Scrubbing-Standard.pdf)
  - A thin 2026 source claims narratives were pulled — [Cobalt newsletter](https://newsletter.cobaltintelligence.com/p/cfpb-pulls-3m-complaint-narratives)
- **Romanian datasets on Hugging Face** (search "romanian", 109 results, 28 Oct 2026):
  - No banking or finance datasets.
  - Usable general resources: mteb/RomanianReviewsSentiment (CC BY 4.0); DGurgurov/romanian_sa (CC BY-SA 4.0); dariuschrl/romanian-sentiment-reviews-5k (CC0); DS4AI-UPB/romanian-re-semeval (CC BY 4.0); xd-br0/cemrc-romanian-ner-mrc ("other").
  - Legal corpora from Coltuc2026 (mixed licences: CC BY-NC 4.0, MIT, Apache-2.0, CC BY 4.0; self-described, unverified).
  - Yxanul/Romanian-finepdfs (Apache-2.0, PDF-extracted text); Neurograf/Romanian-Instruct-SFT; saillab/alpaca-romanian-cleaned.
  - killua93/German_Italian_French_Romanian_English_Insurance_Analyzer (no description).
  — [Hugging Face dataset search](https://huggingface.co/datasets?search=romanian)

### Inferences
- **AML / transaction-monitoring demo:** sample HI-Small and remap its banks and accounts to synthetic RO IBANs (RZBR plus counterparties), customers to synthetic CNPs and CUIs, and currencies to RON/EUR. The agent then drafts alert narratives or SAR notes in Romanian.
- **Intent and routing demo:** translate and paraphrase banking77 into Romanian with an LLM (attribution required under CC BY 4.0), and add back-office intents such as "poprire", "certificat de moștenitor", "actualizare date CEI" and "adeverință".
- **Berka:** it is real (anonymized) bank data, so given the "no real bank data" rule, prefer synthetic sources or confirm with the organisers.
- **CFPB:** real US consumer complaints. Fine for an English complaint-triage prototype, but not Romanian.

### Gaps
- I did not confirm the PaySim licence on the Kaggle page (commonly cited as CC BY-SA 4.0; unverified).
- I did not confirm the exact CDLA variant for IBM AMLworld (Sharing-1.0 or Permissive) or its file column schema.
- No licence terms are stated for Berka or on the fetched CFPB page, and the 2026 availability of CFPB narratives is unclear.
- I did not verify credit datasets (German Credit, Taiwan default of credit card clients, Home Credit, Give Me Some Credit, Lending Club) or other synthetic AML datasets (e.g. SAML-D).
- Kaggle could not be searched directly (its connector is unauthenticated).
- No public Romanian ID-document image dataset or Romanian financial-document dataset was found.

---

## 5. Tools: synthetic data, document generation, OCR/extraction, agent frameworks, evaluation

### Takeaway
- **Synthetic data:** Faker `ro_RO` produces checksum-valid CNPs (`ssn()`), CUIs (`vat_id()`) and mod-97-valid RO IBANs, but with realism problems: random bank-code letters, people born in the 1800s, and future birth dates. Wrap it with custom generators. Mimesis has no Romanian locale. SDV is under BSL-1.1, which is fine for a hackathon but is not OSI open source.
- **Scan noise:** Augraphy (MIT) simulates printing, scanning and faxing.
- **OCR with Romanian support:** Tesseract `ron`, PaddleOCR PP-OCRv5 latin (`ro`), a docTR `romanian` vocab, Azure Document Intelligence Read/Layout (printed text only; no Romanian handwriting), and Google Document AI Enterprise OCR, Form and Layout parsers. Cloud ID-card parsers do not cover Romanian IDs, so a multimodal LLM plus deterministic validators is the practical extractor.
- **Agent frameworks (Oct 2026):** LangGraph 1.x, PydanticAI 2.x and OpenAI Agents SDK 0.24 (provider-agnostic) are all MIT-licensed packages.

### Cited Findings

**Synthetic data**
- Faker `ro_RO` has these providers — [Faker docs – ro_RO](https://faker.readthedocs.io/en/master/locales/ro_RO.html):
  - address (e.g. "Intrarea Preda Nr. 864 / Pogoanele, 482421"); automotive (license plate "IL-04-QPM")
  - bank (`iban()` → "RO62MYNB4876475938242194", `swift8()` → "MYNBROQ6"); company (e.g. "Nistor Albu CRL"); currency (`pricetag()` → "7.604,87 Lei")
  - date_time (Romanian day and month names); internet; job; person; phone_number ("0785 604 876")
  - ssn (13 digits, "Romanian Social Security Number"); vat_id
- `ssn()` internals — [Faker ssn/ro_RO source](https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/ssn/ro_RO/__init__.py):
  - First digit drawn uniformly from 1–8. The century map is 1/2 → 1900, 3/4 → 1800, 5/6 → 2000; 7/8 default to 1900.
  - Year 00–99, day valid for the month.
  - Counties 01–46, 51, 52; serial 001–999.
  - Checksum weights (2,7,9,1,4,6,3,5,8,2,7,9) with 10 → 1.
- `vat_id()` internals — [Faker ssn/ro_RO source](https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/ssn/ro_RO/__init__.py):
  - A 9-digit base with an optional "RO" prefix.
  - Check digit with weights 7,5,3,2,1,7,5,3,2, ×10 mod 11 mod 10, giving 10 digits.
- The ro_RO bank provider has `bban_format = "????################"` (4 random letters + 16 digits) and a 40-entry `swift_bank_codes` list that includes RZBR — [Faker bank/ro_RO source](https://raw.githubusercontent.com/joke2k/faker/master/faker/providers/bank/ro_RO/__init__.py)
- Mimesis supports 47 locales, and Romanian is not among them — [Mimesis locales](https://mimesis.name/master/locales.html)
- SDV (DataCebo):
  - Business Source License 1.1 since 14 Apr 2023; not an OSI licence.
  - Sources disagree on commercial use. The clearest restriction is offering a synthetic-data service to third parties, and PyPI describes it as free for non-commercial use.
  - A paid SDV Enterprise tier exists.
  — [PyPI – sdv](https://pypi.org/project/sdv); [GitHub sdv-dev/SDV](https://github.com/sdv-dev/SDV); [EveryDev – SDV](https://www.everydev.ai/tools/sdv)
- Augraphy:
  - MIT licence (Sparkfish LLC).
  - Extracts an "ink" layer, then distorts the ink and paper to imitate dirty printers, office scanners and low-resolution fax.
  - `default_augraphy_pipeline()`; latest PyPI release seen 8.2.4.
  — [PyPI – augraphy](https://pypi.org/project/augraphy/); [arXiv 2208.14558 (ICDAR 2023 paper)](https://arxiv.org/abs/2208.14558v2)

**OCR and extraction for Romanian**
- Tesseract: `ron` traineddata ("Romanian; Moldavian; Moldovan") is available in every version, in tessdata, tessdata_best and tessdata_fast — [tessdoc – Data files](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html)
- PaddleOCR: `latin_PP-OCRv5_mobile_rec` lists Romanian (`ro`) — [PaddleOCR PP-OCRv5 multilingual docs](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html). Docling's docs list `ro` under PP-OCRv6 — [Docling OCR languages](https://docling-project.github.io/docling/concepts/OCR_native/)
- docTR: `VOCABS["romanian"] = VOCABS["english"] + "ăâîșțĂÂÎȘȚ"`. These are the comma-below letters; the cedilla ş/ţ are absent. The "multilingual" vocab includes Romanian — [docTR vocabs.py](https://github.com/mindee/doctr/blob/main/doctr/datasets/vocabs.py)
- Azure AI Document Intelligence v4.0 (page updated in 2026) — [Microsoft Learn – Read/Layout language support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0):
  - Romanian (`ro`) is supported for **printed** text in prebuilt-read and prebuilt-layout.
  - **Handwritten** support covers only en, zh-Hans, fr, de, it, th, ja, ko, pt, es, ru and ar.
- Google Document AI — [Google Cloud – Document AI languages](https://docs.cloud.google.com/document-ai/docs/languages):
  - Romanian is supported in Enterprise Document OCR, Form Parser and Layout Parser.
  - Custom Extractor with generative AI: "Only the English language is officially supported".
  - The identity processors (ID Proofing, US Driver License) cover **US documents only**.
- Commercial Romanian KYC OCR exists (Druid, FintechOS) with CNP, MRZ and SIRUTA validations — [Druid](https://docs.druidai.com/1385954/Content/Druid%20AI%20Services/New%20Romanian%20Identity%20Cards%20OCR.htm); [FintechOS](https://docs.fintechos.com/APs/SysPack/24.5/UserGuide/Content/ComputerVision/Validations.htm)

**Agent frameworks, as of 28 Oct 2026**
- **LangGraph:** PyPI version 1.2.18, MIT — [PyPI JSON – langgraph](https://pypi.org/pypi/langgraph/json)
- **PydanticAI:** PyPI version 2.63.0, MIT ("AI Agent Framework, the Pydantic way") — [PyPI JSON – pydantic-ai](https://pypi.org/pypi/pydantic-ai/json)
- **OpenAI Agents SDK:** PyPI `openai-agents` 0.24.0, MIT. It describes itself as provider-agnostic, supporting "100+ other LLMs", with LiteLLM and any-llm as optional dependencies — [PyPI JSON – openai-agents](https://pypi.org/pypi/openai-agents/json)
- Comparison articles (vendor and listicle, directional only) group frameworks as:
  - graph-based: LangGraph, Mastra
  - role-based: CrewAI, AutoGen
  - provider SDKs: OpenAI Agents SDK

  They describe LangGraph as best for complex stateful flows but with a steep learning curve, and CrewAI as fast for prototyping but weaker on state — [Morph – AI agent frameworks 2026](https://www.morphllm.com/ai-agent-framework); [Noqta comparison 2026](https://www.noqta.tn/en/blog/ai-agent-frameworks-langgraph-crewai-openai-sdk-comparison-2026); [Hightower substack](https://rickhigh.substack.com/p/langgraph-vs-crewai-vs-claude-agent)

**Evaluation tooling**
- Licences and focus, from vendor-authored comparisons — [FutureAGI – open-source eval frameworks 2026](https://futureagi.com/blog/best-open-source-eval-frameworks-2026); [Techsy – LLM evaluation frameworks](https://techsy.io/en/blog/llm-evaluation-framework-open-source):
  - DeepEval: Apache-2.0, pytest-style.
  - promptfoo: MIT, CI-native prompt evals.
  - Langfuse: mostly MIT, self-hostable tracing.
  - Inspect AI: MIT, from the UK AI Security Institute.
  - Arize Phoenix: Elastic License 2.0, source-available rather than OSI open source.

### Inferences
- **Faker realism problems,** derived from the cited source code:
  - Only about 25% of Faker CNPs are "typical citizens born 1900–1999" (first digit 1/2).
  - About 25% are born in the 1800s (3/4).
  - About 25% are foreign residents (7/8).
  - About 18% have future birth dates (5/6 with a year from 27 to 99).
  - Faker IBANs use random letters instead of real bank codes (its docs example shows "MYNB"), although their mod-97 check digits are valid. I re-validated Faker's documented CNP, CUI and IBAN examples locally, and all pass their checksums.
  - **Fix:** write a 30-line generator that samples DOB from an adult age distribution and counties weighted by population, uses real bank codes, and computes the check digits.
- **Suggested 1–2 day pipeline (Python):**
  1. Faker(ro_RO) names and addresses plus custom ID generators.
  2. A ground-truth JSON per case.
  3. Jinja2 HTML templates, rendered to PDF with WeasyPrint or Playwright (not evaluated here).
  4. Rasterize, then apply Augraphy noise, rotation and stamps.
  5. Extract with a multimodal LLM into a Pydantic schema, with Tesseract `ron` or PaddleOCR `ro` as a cheap baseline.
  6. Run deterministic validators (CNP, CUI, IBAN, ONRC, MRZ checksums; cross-document consistency; date logic).
  7. Orchestrate as an agent with tools (validators, a "core banking" mock, a poprire calculator) and route to a human when confidence is low.
  8. Evaluate against ground truth.
- **Metrics,** all computable automatically because the ground truth is known:
  - field-level exact match and F1 per document type
  - checksum-valid rate
  - straight-through-processing rate
  - escalation precision and recall on seeded anomalies (bad checksum, CNP mismatch, expired CI, missing address on CEI, totals mismatch)
  - time per case
  - Use promptfoo or DeepEval for regression tests and Langfuse for traces.
- **Diacritics:** synthetic documents should mix comma-below ș/ț (U+0219/U+021B) and legacy cedilla ş/ţ (U+015F/U+0163), because real Romanian documents and older fonts use both. Normalise before matching; docTR's vocab only has the comma-below forms.
- **Handwriting:** Azure DI has no Romanian handwriting support, so handwritten fields (signatures, amounts on a chitanță) should go to LLM vision or a human-review step.
- **Framework choice for a 1–2 day build:** PydanticAI suits typed, schema-first extraction. LangGraph suits explicit stateful workflows with human-in-the-loop. OpenAI Agents SDK suits provider-agnostic setups. This is a judgment call, not from a benchmark.

### Gaps
- I did not compare HTML-to-PDF tools (WeasyPrint, Playwright/Chromium, wkhtmltopdf maintenance status).
- I found no accuracy benchmark of OCR engines or multimodal LLMs on Romanian documents or ID cards.
- I did not check newer OCR/VLM options (Mistral OCR, olmOCR, DeepSeek-OCR, PaddleOCR-VL, Docling, Marker) for Romanian support.
- I did not check versions for CrewAI, Microsoft Agent Framework, Google ADK or Mastra. The release dates of LangGraph 1.0 and of PydanticAI 1.0/2.0 were not confirmed because the PyPI JSON output was truncated.
- The evaluation-tool licences come from vendor blogs; check each project's LICENSE file.

---

## 6. Open-source libraries for validating CNP, CUI and IBAN (Python, JS)

### Takeaway
- **python-stdnum** (LGPL-2.1+) is the most complete Romanian validator set: `stdnum.ro.cnp` (including counties 47/48/70/80–83), `stdnum.ro.cui`, and `stdnum.ro.onrc` (old and new 2024 formats, with check digit).
- **schwifty** validates, generates and randomizes IBANs.
- **Faker** generates checksum-valid data.
- **JavaScript:** small npm CNP validators exist, but no dedicated CUI package was found; the checksums are short enough to port.
- **ANAF integration:** anafpy (Python), RoeFactura (.NET) and Odoo l10n_ro modules.

### Cited Findings
- python-stdnum ro.cnp: validation of county code, first digit, date and checksum, plus `get_county()`. Licensed LGPL 2.1 or later — [python-stdnum ro/cnp.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cnp.py)
- python-stdnum ro.cui: checksum, RO-prefix stripping, length 2–10 — [python-stdnum ro/cui.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/cui.py)
- python-stdnum ro.onrc: old and new formats, county and year rules, new-format checksum — [python-stdnum ro/onrc.py](https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/ro/onrc.py)
- schwifty can:
  - validate IBAN check digits and country-specific format
  - validate BICs
  - generate IBANs from country, bank and account codes
  - "generate random valid IBANs"
  - look up the BIC for an IBAN's bank code
  — [schwifty docs](https://schwifty.readthedocs.io/en/latest/)
- npm CNP validators:
  - `romanian-personal-identity-code-validator`, TypeScript, with a `CNP` class exposing `isValid()` — [npm](https://npmjs.org/package/romanian-personal-identity-code-validator)
  - `js-romanian-cnp-validation` — [npm](https://npmjs.org/package/js-romanian-cnp-validation)
  - `parsecnp` — [Yarn](https://classic.yarnpkg.com/en/package/parsecnp)
- Other ecosystems:
  - PHP: `alcea/cif` (CIF) — [Packagist](https://packagist.org/packages/alcea/cif); `oriceon/cnp` — [Packagist](https://packagist.org/packages/oriceon/cnp); `mmltech/cnp-decoder`, whose sample includes an IDROU MRZ — [Packagist](https://packagist.org/packages/mmltech/cnp-decoder)
  - Elixir: `validators_ro` (CIF, CNP, IBAN) — [GitHub](https://github.com/mtarnovan/validators_ro)
  - Ruby: `romanianvalidators` — [CodeClimate](https://codeclimate.com/github/mtarnovan/romanianvalidators/README.md/source)
  - R: `rocnp` — [MyNixOS](https://mynixos.com/nixpkgs/package/rPackages.rocnp)
- ANAF e-Factura tooling:
  - `anafpy`, a Python client for the e-Factura API whose rule IDs mirror the CIUS-RO 1.0.9 Schematron — [PyPI](https://pypi.org/project/anafpy/); [docs](https://anafpy.readthedocs.io/en/latest/library/efactura/)
  - RoeFactura (.NET) — [NuGet](https://packages.nuget.org/packages/RoeFactura)
  - Odoo `l10n_ro_account_edi_ubl` — [Odoo Apps](https://apps.odoo.com/apps/modules/15.0/l10n_ro_account_edi_ubl)

### Inferences
- **Recommended setup:** a Python backend with python-stdnum for validation, schwifty for IBANs and custom generators (section 1 code). In a JS front end, port the three checksum functions (about 30 lines) instead of depending on small, possibly unmaintained npm packages.
- **LGPL note:** importing python-stdnum as a library is generally fine for a hackathon or closed app. Copying its code into proprietary code would trigger LGPL obligations. This is a general licensing note, not legal advice.
- **ONRC:** python-stdnum is the only library found that handles the new 14-character number. Treat its check digit as provisional and design validators to warn rather than fail on it.

### Gaps
- I did not verify the maintenance status, licences or download counts of the npm, PHP and Ruby packages.
- I did not confirm whether schwifty's bank registry covers Romania (BIC lookup for RO bank codes) or what its licence is.
- I did not verify JS IBAN libraries (e.g. ibantools, iban.js) in this session.
- The python-stdnum documentation index returned 404, so the current release number and the `stdnum.ro.cf` module (Cod fiscal: CNP or CUI) were not confirmed. A generic `stdnum.iban` module is likely present but was not re-verified.
