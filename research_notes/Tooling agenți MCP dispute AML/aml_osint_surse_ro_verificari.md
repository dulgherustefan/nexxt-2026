# Fraud-intelligence, AML and OSINT sources and methods for a Romanian bank (Judge + Investigator agents), with verification of draft claims (as of 28 Oct 2026)

Verification legend used throughout:
- **[V-PRIMARY]**: checked in this session against the primary document (official text or report).
- **[V-SECONDARY]**: checked in this session against press or secondary sources only. The primary source was not retrieved.
- **[KNOWLEDGE, not re-verified]**: comes from the researcher's prior knowledge. The URL is the canonical place to confirm it. It was not fetched in this session, so treat it as unverified until someone checks it.

---

## Q1. Phishing and domain intelligence in 2026: sources, access terms, and robust "domain age" and "similarity to bank domain"

### Takeaway
The building blocks the team named are all usable in 2026. Their commercial terms differ, though, and that matters for a bank. RDAP, Certificate Transparency (crt.sh), self-hosted dnstwist and the OpenPhish community feed cost nothing. PhishTank has accepted no new user registrations since 2020. Google Safe Browsing and the VirusTotal public API are restricted to non-commercial use, so a bank needs Google Web Risk and VirusTotal Premium, or an equivalent. Only the PhishTank and OpenPhish status could be verified in this session. Every other access term below comes from prior knowledge and should be checked against the vendor's documentation.

### Cited Findings
- **PhishTank**: "In 2020, because of flagrant abuse of the Phishtank system, 'new user' registration was removed, and will remain off for the foreseeable future." [V-SECONDARY] [Wikipedia: PhishTank](https://en.wikipedia.org/wiki/PhishTank). A low-quality aggregator also claims a 2026 ML-based redesign. That claim is unverified.
- **OpenPhish**: the free community feed "is updated every 6 hours" and is at `https://openphish.com/feed.txt`, according to the 2025 SpamAssassin Phishing plugin docs. Premium feeds are commercial. [V-SECONDARY] [Mail::SpamAssassin::Plugin::Phishing (man.archlinux.org)](https://man.archlinux.org/man/extra/spamassassin/Mail::SpamAssassin::Plugin::Phishing.3pm.en)
- **CertStream (Calidog)**: the only material found was from 2017 and described it as a real-time CT certificate-event feed with a Python library. No source confirmed its 2026 operational status in either direction. [V-SECONDARY] [SANS ISC diary 23065](https://isc.sans.edu/diary/23065)
- **RDAP vs WHOIS** [KNOWLEDGE, not re-verified]:
  - ICANN's contracts made RDAP the authoritative source for gTLD registration data. The obligation to run port-43 WHOIS ended on 28 Jan 2025.
  - Bootstrap from the IANA file at `https://data.iana.org/rdap/dns.json`.
  - Domain age comes from the RDAP `events[]` entry with `eventAction: "registration"`.
  - Source: [ICANN RDAP](https://www.icann.org/rdap).
  - For **.ro**, ROTLD's WHOIS (`whois.rotld.ro`) shows a "Registered On" date. This session did not confirm whether ROTLD offers RDAP, so see Gaps.
- **crt.sh** [KNOWLEDGE, not re-verified]:
  - Free JSON endpoint: `https://crt.sh/?q=%25.<domain>&output=json`.
  - Public read-only PostgreSQL access: host `crt.sh`, port 5432, user `guest`, database `certwatch`. It is best-effort and often slow or rate-limited.
  - The first-seen certificate (`min(not_before)` / entry timestamp) is a second "age" signal that is independent of WHOIS redaction.
  - Source: [crt.sh](https://crt.sh/)
- **dnstwist** [KNOWLEDGE, not re-verified]:
  - Open-source permutation engine. Fuzzers include addition, bitsquatting, homoglyph, hyphenation, insertion, omission, repetition, replacement, subdomain, transposition, vowel-swap, dictionary and TLD-swap.
  - It resolves A/AAAA/NS/MX records.
  - It can compare page similarity with fuzzy hashes (ssdeep/TLSH) and screenshots with perceptual hashes (pHash).
  - It runs locally, so no third-party terms apply.
  - Source: [github.com/elceef/dnstwist](https://github.com/elceef/dnstwist)
- **urlscan.io** [KNOWLEDGE, not re-verified]:
  - REST API covers Submission (`POST /api/v1/scan/`, with `visibility` set to public, unlisted or private), Result (`/api/v1/result/{uuid}/`) and Search (Elasticsearch-style query syntax over domain, IP, ASN, page title, favicon hash and similar fields).
  - Quotas depend on the plan, and the free tier is limited.
  - Use `private` or `unlisted` visibility for anything that might carry customer data.
  - Source: [urlscan.io API docs](https://urlscan.io/docs/api/)
- **Google Web Risk vs Safe Browsing** [KNOWLEDGE, not re-verified]:
  - The Safe Browsing API is for non-commercial use.
  - Web Risk is the paid commercial counterpart. It offers a Lookup API (`uris.search`), an Update API (hash-prefix lists) and a Submission API for reporting suspected phishing URLs; Submission requires Google's approval.
  - Source: [Web Risk docs](https://cloud.google.com/web-risk/docs)
- **VirusTotal** [KNOWLEDGE, not re-verified]:
  - The free public API is rate-limited (about 4 requests/min and 500/day) and must not be used in commercial products or workflows.
  - A bank use case needs Premium/Enterprise.
  - Source: [VirusTotal: public vs premium API](https://docs.virustotal.com/reference/public-vs-premium-api)

### Inferences
- **Robust "domain age"**: take the earliest reliable date from three signals.
  - (1) The RDAP registration event, or WHOIS for ccTLDs without RDAP.
  - (2) The CT first-seen date from crt.sh.
  - (3) The passive-DNS first-seen date, if a provider is available.
  - Flag two edge cases: re-registered or drop-caught domains, where the registration date resets, and redacted RDAP records.
  - A practical scoring rule is age < 30 days = strong signal and < 7 days = very strong, especially combined with a fresh DV certificate.
- **Robust "similarity to the bank's domain"**: run a pipeline, not a single metric.
  - (1) Normalise: lowercase, decode punycode (`xn--`) under IDNA2008/UTS #46, then apply NFKC.
  - (2) Map to a **Unicode TS #39 confusables "skeleton"** to collapse homoglyphs, for example Cyrillic "а" to Latin "a" ([UTS #39](https://www.unicode.org/reports/tr39/), KNOWLEDGE). Add a custom multi-character list such as rn→m, vv→w, cl→d, 1→l and 0→o.
  - (3) Strip the public suffix with the Public Suffix List and compare the registrable label with Damerau-Levenshtein distance, Jaro-Winkler and keyboard-adjacency edits.
  - (4) Detect combosquatting by checking whether the brand token plus a keyword (login, secure, verificare, plata, card, ro, app) is contained in the label.
  - (5) Measure visual similarity: screenshot pHash against the real login page, and favicon hash.
  - (6) Treat a TLD swap (.ro to .com, .online, .top and so on) as its own feature.
  - Generate the candidate list proactively with dnstwist and watch CT logs (crt.sh polling or a self-hosted CertStream) for new certificates that contain the brand token.
- **Takedown and reporting** for the Judge's "report the phishing domain" step:
  - Send to the registrar abuse contact, taken from the RDAP entity with role `abuse`.
  - Send to the hosting provider.
  - For .ro domains, send to ROTLD.
  - Report to DNSC (see Q2).
  - Submit to Google Web Risk/Safe Browsing reporting.
  - Send a URL to urlscan only with private visibility.

### Gaps
- No 2026 source confirmed CertStream's hosted-service status, urlscan's current quotas or terms, Web Risk pricing, or the VirusTotal limits. Check each vendor's documentation before the demo.
- Whether ROTLD (.ro) offers RDAP in 2026 was not verified.

---

## Q2. Romanian sources: ANAF, ONRC/RECOM, BNR registers, DNSC, ONPCSB STR submission, Police/DIICOT

### Takeaway
ANAF's free VAT-registry web service, queried by CUI, is the main machine-readable company source. It is a POST to `/api/PlatitorTvaRest/v9/tva`, takes at most 100 CUIs per request, is limited to 1 request/second and needs no authentication. Banks submit STRs (RTS) to ONPCSB through ONPCSB's own online reporting system, `raportari.onpcsb.ro`, using forms set by ONPCSB order. No source showed Romania using goAML. Citizens report phishing to DNSC through the single number **1911** or the PNRISC platform. No public DNSC phishing API was found. ONRC/RECOM, the BNR registers and the Police/DIICOT channels were not verified in this session.

### Cited Findings
- **ANAF VAT web service v9** [V-SECONDARY: third-party API docs, not ANAF's own doc]:
  - Endpoint and payload: `POST /api/PlatitorTvaRest/v9/tva` with a JSON list of `{cui, data}` objects. The response contains `found[]` and `notFound[]`.
  - Batch size: at most 100 CUIs per request for v9 TVA, or 500 for the RegAgric/RegCult registers.
  - Rate limit: at most 1 request/second per client. ANAF warns that abuse can be sanctioned.
  - The live response differs from the official documentation: the documented `{"cod":200,...}` wrapper did not appear in live responses observed in July 2026.
  - Sources: [anafpy docs](https://anafpy.readthedocs.io/en/latest/anaf-reference/public/api/); [itrack/anaf (Packagist)](https://packagist.org/packages/itrack/anaf), which says "maxim 100 de CUI-uri simultan cu o rata de 1 request / secunda".
  - The older ANAF docs (v1–v8 lineage) are at [static.anaf.ro](https://static.anaf.ro/static/10/Anaf/Informatii_R/documentatie_SW_01112017.txt).
- **ANAF response fields** [KNOWLEDGE, not re-verified]:
  - `date_generale`: denumire, adresa, nrRegCom, telefon, cod_CAEN, data_inregistrare, stare_inregistrare, forma_juridica, organFiscalCompetent, statusRO_e_Factura.
  - Status blocks: `inregistrare_scop_Tva` (VAT periods), `inregistrare_RTVAI`, `stare_inactiv` (inactive or reactivated dates), `inregistrare_SplitTVA`.
  - Addresses: `adresa_sediu_social` and `adresa_domiciliu_fiscal`.
  - The service is free and needs no API key.
  - ANAF also has a separate free financial-statements service (`/bilant?an=YYYY&cui=...`) that returns turnover, profit and employee count. That service is unverified this session.
- **ONPCSB STR submission** [V-SECONDARY]:
  - Reports go through the reporting system ONPCSB provides at `https://raportari.onpcsb.ro/`. [fiscalitatea.ro](https://www.fiscalitatea.ro/raportare-la-onpcsb-cine-are-obligatia-de-raportare-un-studiu-de-caz-util-contribuabililor-24006/)
  - An ONPCSB President's order of June 2023 approved the form and content of the RTS for bank and non-bank entities. The RTS is a .pdf file generated in the online reporting system. [fiscalitatea.ro](https://www.fiscalitatea.ro/tranzactii-financiare-suspecte-in-domeniul-imobiliar-cand-se-depune-raportul-la-onpcsb-23245/); see also [Filip & Company: new ONPCSB report models and transmission methodology](https://filipandcompany.com/noi-modele-de-rapoarte-folosite-in-relaia-cu-onpcsb-i-metodologia-de-transmitere-a-acestora/)
- **Timing and suspension under Legea 129/2019 art. 8** [V-PRIMARY]:
  - The STR must be sent "de îndată" and before the transaction is carried out.
  - The transaction is not carried out until 24 hours after ONPCSB registers the report.
  - ONPCSB may suspend the transaction for up to 48 hours.
  - The suspension can be extended by up to 72 hours through the Prosecutor's Office at the High Court of Cassation and Justice (ÎCCJ).
  - Source: [Legea 129/2019, legislatie.just.ro](https://legislatie.just.ro/Public/DetaliiDocumentAfis/216157)
- **DNSC phishing reporting** [V-SECONDARY]:
  - The press reports DNSC alerts pointing to the **PNRISC platform (pnrisc.dnsc.ro)** or the single number **1911** for cyber-security incidents, including suspicious e-mails. [Capital.ro](https://www.capital.ro/mesajul-care-pare-oficial-dar-ascunde-o-frauda-avertismentul-transmis-de-dnsc-pentru-utilizatori.html); [Antena3](https://www.antena3.ro/actualitate/dnsc-avertizeaza-asupra-unei-campanii-de-tip-phishing-prin-emailuri-false-care-imita-organizatii-oficiale-758366.html)
  - 1911 is Romania's first single emergency number for cyber-security incidents. [Digi24](https://www.digi24.ro/stiri/actualitate/social/de-joi-romanii-care-sunt-victime-ale-unui-atac-cibernetic-pot-raporta-incidentul-la-numarul-unic-1911-1124468); [gadget.ro](https://gadget.ro/1911-este-primul-numar-unic-de-urgenta-din-romania-pentru-incidente-de-securitate-cibernetica/)
  - In 2025 DNSC said Romania detects only about 1 in 10 cyber attacks and urged reporting to 1911. [Playtech.ro](https://playtech.ro/2025/romania-detecteaza-doar-unul-din-zece-atacuri-cibernetice-dnsc-avertizeaza-si-cere-raportare-la-1911/)
  - A third-party guide, not affiliated with DNSC, says written reports go through a form on dnsc.ro rather than PNRISC. [InfoContact.ro](https://www.infocontact.ro/raportare-fraude-online-cibernetice-dnsc-1911/)
- **BNR registers** [KNOWLEDGE, not re-verified; this session's search found nothing]:
  - BNR keeps public registers of payment institutions, e-money institutions and their agents on bnr.ro.
  - The EBA also runs a central PSD2 register of payment and e-money institutions across the EEA ([EBA register](https://euclid.eba.europa.eu/register/pir/search)).
- **ONRC / RECOM** [KNOWLEDGE, not re-verified]:
  - RECOM online (recom.onrc.ro) is ONRC's paid service for company information and certificates.
  - ONRC publishes periodic open-data extracts of registered companies on data.gov.ro.
  - Access to the beneficial-ownership register has been restricted for the general public since the CJEU judgment C-37/20 (Nov 2022). Obliged entities such as banks keep access.

### Inferences
- The Investigator agent's minimum viable "company to lead" enrichment is:
  - ANAF v9 (registration date, CAEN code, inactive status, VAT status, e-Factura status, address).
  - ANAF financial statements (turnover and employees versus inflows received).
  - ONRC open data (directors, if available).
  - The BNR/EBA registers, to check whether a beneficiary is a licensed PI/EMI or an agent.
- Useful red flags: a newly registered company, an inactive or suspended VAT status, zero employees but large inflows, a registered address shared with many other companies, and a CAEN code inconsistent with the payments.
- Throttle at 1 request/second, batch up to 100 CUIs, and cache results. The ANAF rate-limit warning makes this a compliance point as well as a technical one.
- STRs must be filed in ONPCSB's own system. An agent can draft the RTS content (facts, indicators, linked cases), but a human AML officer should submit it. Nothing the customer sees, including dispute status messages, may reveal that an STR exists or is being considered; see claim (d).

### Gaps
- The official ANAF v9 documentation file (`doc_WS_V9.txt`, reportedly published 04.02.2025) was not opened. The exact field list and any change to the rate limit should be confirmed there.
- No evidence was found on whether ONPCSB uses UNODC goAML. All sources describe ONPCSB's own portal and PDF-based RTS. The exact RTS field list was not retrieved.
- No public DNSC API for phishing indicators was found. Bank-to-DNSC sharing channels (for example MISP or NIS2/DORA incident flows) were not researched.
- The BNR register URLs, the ONRC/RECOM terms and prices, and the Poliția Română / DIICOT complaint channels (online complaint, competence over computer fraud) were not verified in this session.

---

## Q3. Funds recall: SEPA SCT / SCT Inst (camt.056, FRAD, deadlines, pacs.004), domestic RON (SENT, Transfond instant), Verification of Payee, recall success rates

### Takeaway
A euro fraud recall uses **camt.056 with reason code FRAD**. The beneficiary PSP answers positively with a pacs.004 return or negatively with camt.029; LEGL is one negative-answer code. For SCT Inst, the beneficiary PSP must answer a recall or RFRO within **15 banking business days**. Romania is outside the euro area, so the Instant Payments Regulation's **Verification of Payee applies to Romanian PSPs from 9 July 2027** (euro area: 9 Oct 2025). For RON, Transfond runs an instant-payment system and the **SANB payee-name display** service. No public data on recall success rates was found. The only figure is a BNR official's statement that just **7%** of fraud proceeds are recovered worldwide.

### Cited Findings
- **FRAD** = "Fraudulent originated credit transfer", an R-transaction of type Recall. **LEGL** is used for a negative answer to a recall or a Request for Recall by the Originator (RFRO). [V-SECONDARY] [Treezor error codes](https://docs.treezor.com/guide/transfers/error-codes.html); FRAD and TECH also appear as camt.056 cancellation reasons in the ISO 20022 change request ([iso20022.org CR0006](https://iso20022.org/milestone/12491/download)).
- The EPC introduced the "Request for Recall by the Originator" process in the 2017 SCT and SCT Inst rulebooks. [V-SECONDARY] [iso20022.org CR0006](https://iso20022.org/milestone/12491/download)
- **SCT Inst**: a beneficiary PSP breaches the rulebook if it does not answer a Recall or RFRO within **15 banking business days** of receiving it. [V-SECONDARY] [EPC131-17 v3.1 Clarification Paper SCT & SCT Inst](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2025-04/EPC131-17%20v3.1%20Clarification%20Paper%20SCT%20and%20SCT%20Inst%20scheme%20rulebooks.pdf)
- The EPC reason-code guidance documents are **EPC135-18 v6.0** (SCT R-transactions) and **EPC059-18 v6.0** (SCT Inst), both from November 2024. They tell participants to avoid generic codes when a precise one exists. [V-SECONDARY] [EPC135-18 v6.0](https://europeanpaymentscouncil.eu/sites/default/files/kb/file/2024-11/EPC135-18%20v6.0%20Guidance%20on%20Reason%20Codes%20for%20SCT%20R-transactions.pdf); [EPC059-18 v6.0](https://europeanpaymentscouncil.eu/sites/default/files/kb/file/2024-11/EPC059-18%20v6.0%20Guidance%20on%20Reason%20Codes%20for%20SCT%20Inst%20R-transactions.pdf)
- **SCT recall timing and answers** [KNOWLEDGE, not re-verified]:
  - The originator PSP sends a recall (DUPL, TECH or FRAD) within **10 banking business days** after settlement.
  - An RFRO (AC03 wrong IBAN, AM09 wrong amount, CUST) can be sent up to **13 months** after the original transaction.
  - A positive answer is a **pacs.004** return. A negative answer is a **camt.029**, with codes such as NOAS, NOOR, ARDT, AC04, AM04, CUST and LEGL.
  - Whether recent rulebook versions let FRAD be raised beyond 10 days needs checking in the current SCT rulebook.
- **Instant Payments Regulation (EU) 2024/886 dates for non-euro Member States** [V-SECONDARY]:
  - Verification of Payee applies from **9 July 2027** (euro area: 9 Oct 2025). [ECB IPR page (RO)](https://www.ecb.europa.eu/paym/retail/instant_payments/html/instant_payments_regulation.ro.html); [Taylor Wessing](https://www.taylorwessing.com/de/insights-and-events/insights/2025/10/instant-payments-regulation)
  - Non-euro PSPs must **receive** euro instant payments by **9 Jan 2027** and **send** them by **9 July 2027**. [Worldline](https://worldline.com/en/home/main-navigation/resources/blogs/2025/instant-payments-regulation-a-key-development-for-non-eurozone-eu-countries)
- The **EBA/ECB 2025 report** notes that VoP becomes mandatory and "may thus, looking ahead, contribute to containing fraud". It reports average loss per fraudulent transaction ranging from **EUR 10 to EUR 13,430 (average EUR 3,632) for traditional SCT** and **EUR 74 to EUR 4,324 (average EUR 1,392) for SCT Inst**. Romania was excluded from the EU SCT Inst time series because data was not available for the whole period. [V-PRIMARY] [EBA/REP/2025/40 PDF](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf)
- **RON instant payments (Transfond)** [V-SECONDARY]:
  - The system has run since 2019 and settles in at most 10 seconds, 24/7.
  - The per-payment ceiling is **49,999.99 lei**, which may be out of date.
  - The fee was cut to 0.45 lei in 2021.
  - Source: [Financial Intelligence](https://financialintelligence.ro/transfond-a-ieftinit-platile-instant-la-045-lei-per-plata/)
- **SANB (Serviciul de Afișare a Numelui Beneficiarului)** shows the payee's first name and initial once the IBAN is entered. It works only if both banks participate. Its purpose is to prevent fraud and wrong-IBAN transfers. [V-SECONDARY] [Economedia](https://economedia.ro/proiect-pilot-clientii-bancilor-din-romania-vor-putea-verifica-identitatea-beneficiarului-real-al-platii.html)
- RoPay, Transfond's mobile account-to-account instant-payment service, is live and banks are joining it, for example Garanti BBVA. [V-SECONDARY] [Revista Biz](https://www.revistabiz.ro/garanti-bbva-romania-adereaza-la-ropay-si-ofera-plati-instant-in-lei/)
- **Recovery rate**: Alexandru Păunescu, BNR's representative on CSALB's Coordination Committee, said "Doar 7% din fondurile provenite din fraudă pot fi recuperate la nivel mondial" (only 7% of fraud proceeds can be recovered worldwide). [V-SECONDARY] [HotNews, 29.10.2025](https://hotnews.ro/cazurile-de-frauda-bancara-din-romania-cresc-pe-masura-ce-se-apropie-black-friday-zeci-de-romani-s-au-trezit-fara-bani-in-conturi-2097046)
- **Visa chargeback** [KNOWLEDGE, not re-verified]:
  - Fraud disputes use Visa reason code **10.4** (Other Fraud, card-absent environment), generally within 120 days.
  - When the transaction was authenticated with 3-D Secure, the fraud liability shift normally blocks a 10.4 chargeback.
  - A chargeback covers card payments only, so it is not available for credit-transfer APP scams.

### Inferences
- **Judge agent recovery playbook**:
  - (1) For a euro SCT or SCT Inst, send a camt.056/FRAD **the same day**, because funds in APP and mule cases are usually moved within minutes or hours.
  - (2) Track the camt.029 or pacs.004 answer against the 15-business-day SLA.
  - (3) For a RON instant or SENT payment, use the Transfond or interbank recall procedure (not public; see Gaps) and contact the beneficiary bank's fraud desk directly.
  - (4) Request an AML freeze review at the beneficiary bank. ONPCSB suspension under art. 8 Legea 129/2019 is available only through an STR.
  - (5) Pursue a Visa chargeback only for card-funded fraud without 3DS liability shift.
- Until July 2027, SANB is the only domestic analogue to VoP. The Judge should record whether SANB displayed a name and whether it matched, as evidence for the authorised-vs-unauthorised and gross-negligence analysis.

### Gaps
- No public rulebook was found for RON recalls in SENT or Transfond instant payments (procedure, deadlines, message types). These are likely in Transfond's participant rules or ARB conventions, which are not public.
- No EU or Romanian statistics on recall success rates were found. The 7% figure is a quoted global estimate with no primary source.
- The current SCT rulebook text on recall windows (10 days for FRAD, 13 months for RFRO) and the 2025 rulebook changes were not verified.

---

## Q4. Mule detection and case-linking methods (graph ML, community detection, features, entity resolution, synthetic data)

### Takeaway
The current open toolkit is:
- IBM's **AMLworld** synthetic transaction datasets (NeurIPS 2023 Datasets & Benchmarks) as the benchmark.
- **Multi-GNN** and the newer **MEGA-GNN** temporal multigraph GNNs as the state of the art in detection.
- **AMLNet** (arXiv 2509.11595, 2025) as a newer regulation-aware synthetic generator. Its data is embargoed on Zenodo.

For a hackathon, explainable graph features (fan-in, fan-out, pass-through), Leiden community detection and Splink entity resolution will link victims to mule clusters faster and more defensibly than training a GNN.

### Cited Findings
- **AMLworld**: Altman et al., "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models", NeurIPS 2023 Datasets & Benchmarks. [V-SECONDARY] [NeurIPS proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/5f38404edff6f3f642d6fa5892479c42-Abstract.html); [arXiv 2306.16424](https://arxiv.org/abs/2306.16424v2)
- **AMLNet**: Huda, Foo, Jadidi, Newton, Sattar, "AMLNet: A Knowledge-Based Multi-Agent Framework to Generate and Detect Realistic Money Laundering Transactions". [V-SECONDARY] [arXiv 2509.11595](https://arxiv.org/abs/2509.11595v1)
  - The generator produces **1,090,173** synthetic transactions, about **0.16%** of them laundering-positive.
  - Detection F1 is **0.90** on its internal test partitions, and the ensemble is also tested on SynthAML.
  - The Zenodo record gives slightly different numbers: 1,048,575 transactions, of which 1,547 (0.15%) are money laundering. It is **embargoed** and cites *Expert Systems with Applications*. [Zenodo 16482144](https://zenodo.org/records/16482144)
- **MEGA-GNN**: a TU Delft thesis evaluates "two MEGA-GNN variants" and calls them the current state of the art in temporal multigraph-compatible GNN architectures for AML. [V-SECONDARY] [TU Delft repository](https://repository.tudelft.nl/file/File_cfa6bd5a-2704-4fd9-a3e1-566f918aacc3?preview=1)
- **IBM Multi-GNN** [KNOWLEDGE, not re-verified]:
  - Egressy et al., "Provably Powerful Graph Neural Networks for Directed Multigraphs" (AAAI 2024).
  - It adds reverse message passing, port numbering and ego IDs to GIN/PNA-style GNNs, and its code is benchmarked on AMLworld.
  - [github.com/IBM/Multi-GNN](https://github.com/IBM/Multi-GNN)
- **Leiden** [KNOWLEDGE, not re-verified]: Traag, Waltman and van Eck (2019), "From Louvain to Leiden: guaranteeing well-connected communities", *Scientific Reports*. It fixes Louvain's badly connected communities. Implementations include `leidenalg` and `igraph`.
- **Splink** [KNOWLEDGE, not re-verified]: the UK Ministry of Justice's open-source probabilistic record linkage library. It uses the Fellegi–Sunter model with DuckDB, Spark or Athena backends. [github.com/moj-analytical-services/splink](https://github.com/moj-analytical-services/splink)
- **APP context from the EBA 2025 report** [V-PRIMARY]: manipulation of the payer was the largest share of fraudulent credit transfers. It rose from **65% to 74% by value** and from **55% to 71% by volume** between 2023 and 2024. Fraudsters use phishing and social networks to groom victims. [EBA/REP/2025/40](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf)
- **Romanian modus operandi seen at CSALB in 2026** [V-SECONDARY]:
  - Loans taken out online in the victim's name after callers posed as bank, police or BNR staff.
  - Malware delivered through a WhatsApp app, giving remote control of the phone.
  - Cash pushed into crypto ATMs.
  - Fake investment brokers.
  - Warnings about deepfake video identification.
  - Source: [HotNews, 09.09.2026](https://hotnews.ro/au-ramas-fara-economii-si-cu-credite-pe-numele-lor-ce-arata-cele-170-de-cazuri-analizate-de-csalb-2344897)

### Inferences
- **Feature set for the Investigator** (explainable, computable in SQL or Python):
  - Fan-in: the number of distinct senders to one beneficiary within 24h or 7d, especially senders who are confirmed fraud victims.
  - Fan-out after receipt.
  - Pass-through ratio: outflow divided by inflow within Δt (for example under 2h), plus the median dwell time of funds.
  - Account age and first-inbound-payment age.
  - Share of inflows from first-time payers.
  - Cash-out channel mix: ATM, crypto exchange or crypto ATM, PI/EMI wallets.
  - Device, IP, phone and e-mail overlap across customers.
  - Shared registered address or director across beneficiary companies (from ANAF or ONRC).
- **Case-linking**:
  - Build a heterogeneous graph with victim, beneficiary IBAN, company (CUI), phishing domain, IP/ASN, TLS certificate, phone and device nodes.
  - Resolve duplicate entities with Splink (company-name variants, addresses, persons).
  - Run Leiden, ideally on a time-windowed graph, to find clusters of victims linked through shared mule accounts or shared phishing infrastructure (same certificate issuer or serial pattern, same IP, same favicon hash on urlscan).
  - Use a GNN (Multi-GNN or MEGA-GNN trained on AMLworld) only as an optional score, because synthetic-to-real transfer is unproven.

### Gaps
- No published evaluation was found of these GNNs on Romanian or real bank data. AMLNet's dataset access is embargoed.
- The MEGA-GNN primary paper (authors, venue, code) was not verified in this session.

---

## Claim (a): EBA–ECB 2025 report. Romania 2024 credit-transfer fraud €63.9m and card fraud €10.0m; EEA users bore about 85% of credit-transfer and 38% of card fraud losses

### Takeaway
**The 85% and 38% figures are VERIFIED** in the report's Executive Summary. **The Romania figures of €63.9m and €10.0m are NOT VERIFIED.** They do not appear in the report's text. The country charts show Romania without numeric labels in the text layer, so the figures probably come from the ECB Data Portal or BNR payment statistics and need a separate source.

### Cited Findings
- Report identity: "2025 Report on Payment Fraud", **EBA/REP/2025/40**, December 2025, 49 pages. The joint press release is dated **15 December 2025**. [V-PRIMARY] [EBA PDF](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf); [ECB press release](https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.pr251215~e133d9d683.en.html)
- Exact text from the Executive Summary: "In 2024, PSUs bore 38% of the losses that arose from card payments and 53% for both direct debits and cash withdrawals, while this share was 26% for e-money transactions. In contrast, PSUs endured around 85% of total fraud losses for credit transfers in 2024." [V-PRIMARY] [EBA/REP/2025/40](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf)
- EEA headline figures: "Total value of fraud increased to €4.2 billion in 2024 from €3.5 billion in 2023". Credit-transfer losses were **€2.200 billion** (+16% y/y). Losses on card payments with EU/EEA-issued cards were **€1.329 billion**. Card fraud was about 17 times higher when the counterpart was outside the EEA. [V-PRIMARY] [ECB press release 15.12.2025](https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.pr251215~e133d9d683.en.html)
  - Secondary coverage cites €2.5bn for fraudulent credit transfers (+24%) and €1.3bn for cards. These are fraud **values**, as distinct from **losses**. [Payment Expert](https://paymentexpert.com/2025/12/16/credit-transfer-fraud-losses-hit-2-5bn/)
- **Romania-specific statement in the report**: for **cash withdrawals**, PSUs bore over 70% of reported fraud losses in more than half of reporting countries, Romania among them, and "in many of these, such as Greece, Lithuania, Romania, and Slovenia, PSUs had to bear the entirety of reported losses". For credit transfers, PSUs "consistently bore the majority of losses across most countries (see Chart 21)". [V-PRIMARY] [EBA/REP/2025/40](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf)
- Romania reports fraud data under the ECB Regulation on payments statistics, alongside the euro area, Bulgaria, Czechia and Hungary. Romania was excluded from the SCT Inst time-series box because its data was not available for the whole period. [V-PRIMARY] [EBA/REP/2025/40](https://www.eba.europa.eu/sites/default/files/2025-12/1709846a-84d9-47cf-86a0-b155efb34d66/EBA%20and%20ECB%20Report%20on%20Payment%20Fraud.pdf)
- A search of the full report text found neither "63.9" nor a Romanian card-fraud value of "10.0". [V-PRIMARY, negative result] (same PDF)

### Inferences
- In the pitch, keep "≈85% of credit-transfer fraud losses and 38% of card fraud losses borne by users (EEA, 2024)" and cite EBA/REP/2025/40.
- Drop the RO €63.9m and €10.0m figures, or re-source them from the ECB Data Portal (payment statistics, fraud series for RO, 2024) or from BNR and label them as such.
- The cash-withdrawal finding ("PSUs had to bear the entirety of reported losses" in Romania) is a strong, citable Romania-specific line.

### Gaps
- The Romania 2024 fraud values could not be checked against the ECB Data Portal within this session's call budget.

---

## Claim (b): ONPCSB received about 22,500 suspicious transaction reports in 2024

### Takeaway
**VERIFIED from secondary sources, not the primary report.** Several outlets reporting on ONPCSB's 2024 activity report give **22,500 STRs (RTS) in 2024**, up 5.62% on 2023 and 40.05% on 2022. ONPCSB's own PDF was not retrieved.

### Cited Findings
- "Numărul Rapoartelor de Tranzacții Suspecte a fost de 22.500 în 2024", described as "cu 5,62% mai mult față de 2023 și cu 40,05% mai mult față de 2022". Banks were the main reporting entities with **68.55%**, and RTS on natural persons made up **86.55%**. [V-SECONDARY] [Cursuri Bursa blog, 19.04.2025](https://blog.cursuribursa.ro/raportul-de-activitate-onpcsb-pentru-2024/)
- The same growth figures (+5.62% vs 2023, +40.05% vs 2022) appear in [Normedia (31.07.2025)](https://www.normedia.ro/2025/07/31/cum-a-ajuns-oficiul-pentru-combaterea-spalarii-banilor-condus-de-un-general-pensionar-si-un-avocat-cu-legaturi-psd-sinecuri-plagiat-si-tacere-institutionala/). [V-SECONDARY]
- ONPCSB "a analizat peste 22 de mii de rapoarte de tranzacții suspecte" in 2024, about 6% of them related to corruption, and sent no referral to DNA. [V-SECONDARY] [Context.ro](https://context.ro/politicienii-ocoliti-de-analizele-agentiei-care-combate-spalarea-banilor/)
- The most-reported predicate offences were tax evasion, fraud (înșelăciune) and computer fraud. [V-SECONDARY] (Cursuri Bursa, as above)

### Inferences
- "~22,500 STRs in 2024 (+5.6% y/y), ~69% from banks" is safe to use, citing the "ONPCSB Activity Report 2024 (as reported)".
- That fraud and computer fraud are among the top predicate offences supports the Judge-to-Investigator handoff narrative.

### Gaps
- The primary ONPCSB "Raport de activitate 2024" PDF was not found or opened, so the exact unrounded count is unconfirmed.

---

## Claim (c): CSALB. In 2025 banks accepted only 8 fraud cases into conciliation; the HotNews article on 170 CSALB fraud cases (2026)

### Takeaway
**VERIFIED, with nuances.** The "8 cases" figure comes from a HotNews article dated **29.10.2025**, so it is a **year-to-date figure for 2025, not a full-year one**. The "170 cases" article is HotNews, **09.09.2026**, by Dan Popa. It describes **more than 170 requests in 2026 to date**, mostly about **loans fraudulently contracted in victims' names**, and in all the cases described the banks closed or rejected the request. The primary source is a CSALB press release dated 09.09.2026.

### Cited Findings
- "Băncile au acceptat doar opt reclamații legate de fraudă pentru mediere în acest an, conform datelor CSALB." In those cases the banks agreed to partial refunds "cu condiția ca consumatorii să returneze fondurile dacă poliția recuperează sumele furate." The article is by Dan Popa, published 29.10.2025. [V-SECONDARY] [HotNews](https://hotnews.ro/cazurile-de-frauda-bancara-din-romania-cresc-pe-masura-ce-se-apropie-black-friday-zeci-de-romani-s-au-trezit-fara-bani-in-conturi-2097046)
  - The same "8 cases in 2025" is reported by [BZI](https://www.bzi.ro/ce-puteti-face-daca-ati-ramas-fara-banii-din-cont-in-urma-unei-fraude-bancare-specialistii-csalb-ofera-cateva-sfaturi-dupa-cresterea-numarului-de-solicitari-din-partea-victimelor-5409978).
- **HotNews, 09.09.2026, 10:09 (updated 10:59), Dan Popa** [V-SECONDARY] [HotNews](https://hotnews.ro/au-ramas-fara-economii-si-cu-credite-pe-numele-lor-ce-arata-cele-170-de-cazuri-analizate-de-csalb-2344897):
  - The URL slug and the search title read "Au rămas fără economii și cu credite pe numele lor. Ce arată cele 170 de cazuri analizate de CSALB". The fetched page headline was "„Am instalat o aplicație primită pe Whatsapp…”", so the headline was probably changed.
  - Consumers sent "peste 170 de cereri" this year about fraud through banking channels.
  - "Majoritatea creditelor frauduloase sunt contractate online."
  - Losses "ajung până la 20.000 de euro."
  - Banks argued that the operations were authenticated in homebanking and that "infractorii nu au atacat sistemele de securitate ale băncilor".
- Primary source: the CSALB press release "Credite fraudate", 09.09.2026. [V-SECONDARY: identified, not opened] [CSALB PDF](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf); [Spotmedia version](https://spotmedia.ro/stiri/economie/se-inmultesc-fraudele-cu-credite-bancare-zeci-de-cazuri-pe-luna-in-cererile-trimise-de-consumatori-catre-csalb)
- Do not mix in a different count from Antena3, which reported that about a third (14 cases) of one set of requests were accepted. That appears to be a separate category. [Antena3](https://www.antena3.ro/economic/cresc-tentative-fraudare-conturi-bancare-disparitie-bani-cont-660177.html)

### Inferences
- Rephrase the draft. Say "By end-October 2025, banks had accepted only 8 fraud complaints for CSALB conciliation (HotNews, 29.10.2025)" and "In 2026 to early September, CSALB received 170+ fraud-related requests, mostly fraudulent loans in victims' names; banks closed or rejected all cases described (HotNews/CSALB, 09.09.2026)."
- The banks' standard defence ("authenticated in homebanking, so authorised") is the same argument art. 171 of Legea 209/2019 weakens; see claim (g). This is a strong motivation for the Judge agent.

### Gaps
- No full-year 2025 CSALB fraud-conciliation figure was found.

---

## Claim (d): Which article of Legea 129/2019 prohibits tipping-off (is it art. 38?), and the penalty

### Takeaway
**PARTLY CORRECT.** The tipping-off ban is **art. 38 alin. (2)** (alin. (1) bans personal use of confidential information). The penalty is **criminal, under art. 47 alin. (1): imprisonment from 6 months to 3 years or a fine**, unless the act is a more serious offence. Breaching art. 38 is **not** among the contraventions in art. 43. Art. 50 deals with something else: mandatory precautionary asset measures.

### Cited Findings
- Art. 38 alin. (1): "Este interzisă folosirea în scop personal de către salariații entităților raportoare a informațiilor confidențiale primite în temeiul prezentei legi, atât în timpul activității, cât și după încetarea acesteia." [V-PRIMARY] [legislatie.just.ro, Legea 129/2019](https://legislatie.just.ro/Public/DetaliiDocumentAfis/216157)
- Art. 38 alin. (2) applies to reporting entities, their management, administrative and control bodies, directors and employees. They must "nu divulga clienților vizați și nici altor terți faptul că informațiile sunt în curs de transmitere, au fost sau vor fi transmise" under art. 6, or that an ML/TF analysis is under way or may be carried out. [V-PRIMARY] (same source); the wording is also in [Lege5 consolidated text](https://lege5.ro/gratuit/gmztsnrvha4a/legea-nr-129-2019-pentru-prevenirea-si-combaterea-spalarii-banilor-si-finantarii-terorismului-precum-si-pentru-modificarea-si-completarea-unor-acte-normative)
  - Alin. (2) was amended with effect from 15.07.2020 by an emergency ordinance, according to the consolidated-text annotation. [V-SECONDARY] (search snippet of the consolidated text)
- Exceptions include disclosure within a group of information reported to ONPCSB, unless ONPCSB forbids it. Disclosures made in good faith to ONPCSB do not breach contractual confidentiality and do not create liability. [V-SECONDARY] (Lege5 / consolidated text)
- **Penalty, art. 47 alin. (1)**: breaching art. 38 alin. (1)–(2) "constituie infracțiune și se pedepsește cu închisoare de la 6 luni la 3 ani sau cu amendă" (unless the act is a more serious offence). [V-PRIMARY] [legislatie.just.ro](https://legislatie.just.ro/Public/DetaliiDocumentAfis/216157)
- Art. 43 alin. (1) lists contraventions for arts. 6–26, 32, 33 and 37 alin. (2)–(3), **not art. 38**. Money laundering itself (art. 49 alin. (1)) is punished "cu închisoare de la 3 la 10 ani". [V-PRIMARY] (same source)

### Inferences
- Design rule for both agents: dispute messages to the customer ("refund issued", "recovery in progress") must never mention AML analysis, an STR, an ONPCSB suspension, or that the beneficiary is under investigation. This applies especially when the customer might be complicit (a mule or a first-party fraud claim). Keep separate audit trails, with AML notes visible only to the AML function.

### Gaps
- The exact amending act for the 2020 change to art. 38 alin. (2) was not confirmed. It is likely OUG 111/2020.

---

## Claim (e): EU AI Act art. 5(1)(d). Scope, exceptions, and whether it applies to assessing a beneficiary account or company from objective facts

### Takeaway
Art. 5(1)(d) bans AI risk assessments of **natural persons** that predict the risk of committing a **criminal offence** **solely** from profiling or personality traits. It does **not** apply to a system that **supports a human assessment already based on objective and verifiable facts directly linked to a criminal activity**. According to the Commission Guidelines as summarised by FPF, **risk assessments of legal entities are out of scope unless they target specific individuals**. **Private actors such as banks can be covered** where they act under a legal obligation such as AML. A beneficiary **company** assessed on objective transactional and registry facts therefore falls outside the ban. A **natural-person mule account** assessed on objective facts, such as receiving funds from confirmed victims and rapid pass-through, with a human analyst deciding, fits the exception. A pure "propensity" score built from demographics or personality would not.

### Cited Findings
- **Text of art. 5(1)(d)** [KNOWLEDGE, not re-verified]: the ban covers "the placing on the market, the putting into service for this specific purpose, or the use of an AI system for making risk assessments of natural persons in order to assess or predict the risk of a natural person committing a criminal offence, based solely on the profiling of a natural person or on assessing their personality traits and characteristics". It adds that the prohibition "shall not apply to AI systems used to support the human assessment of the involvement of a person in a criminal activity, which is already based on objective and verifiable facts directly linked to a criminal activity". It has applied since **2 Feb 2025**. [Regulation (EU) 2024/1689, EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
- **Commission Guidelines on prohibited AI practices**, C(2025) 884 final, 4 Feb 2025, as summarised by FPF on 11 Mar 2026 [V-SECONDARY] [FPF](https://fpf.org/blog/red-lines-under-the-eu-ai-act-unpacking-the-prohibition-of-individual-risk-assessment-for-the-prediction-of-criminal-offences/):
  - Private actors are covered when "entrusted by law to exercise public authority and public powers" or where processing is "objectively necessary for compliance with a legal obligation". The example given is a **bank obliged under EU AML law to screen and profile customers for money-laundering offences**.
  - Explicitly out of scope: "Risk assessments of legal entities (unless targeting specific individuals)" and "Location-based crime prediction without individual profiling".
  - "Solely" means other elements may be present, but they must be "real, substantial, and meaningful" and documented. Human involvement must be meaningful.
- Law-firm summaries add that the ban applies to **criminal offences only**. Administrative offences are out of scope, and supporting systems that rely on objective facts are generally treated as high-risk rather than prohibited. [V-SECONDARY] [CMS](https://cms.law/en/gbr/legal-updates/eu-commission-issues-guidelines-on-prohibited-ai-practices-part-i); [Orrick](https://www.orrick.com/en/Insights/2025/04/EU-Commission-Publishes-Guidelines-on-the-Prohibited-AI-Practices-under-the-AI-Act); [Bundesnetzagentur](https://bundesnetzagentur.de/EN/Areas/Digitalisation/AI/08_ProhibitedPractices/start.html)
- **Annex III point 5(b)** [KNOWLEDGE, not re-verified]: AI systems for creditworthiness or credit scoring of natural persons are high-risk, "with the exception of AI systems used for the purpose of detecting financial fraud". [EUR-Lex 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)

### Inferences
- **Investigator on a company (CUI)**: this is out of art. 5(1)(d) scope, as a legal-entity assessment. Avoid outputs that score individual directors or UBOs on "criminal propensity". If persons are named, present them as linked entities with facts, not as a risk prediction about the person.
- **Investigator on a natural-person beneficiary account**: keep it in the exception.
  - Base the output on **objective, verifiable facts directly linked to the specific fraud**: inbound transfers from confirmed fraud victims, pass-through timing, links to a reported phishing domain.
  - Present it as **decision support** to a human AML analyst, who must make a meaningful decision.
  - Exclude nationality, age, ethnicity and other protected or personality-type features.
  - Log the evidence chain.
- GDPR still applies to these decisions, including art. 22 for automated ones; this point is inference and was not researched here. Automatic account blocking based solely on the model should go through human review.

### Gaps
- The Guidelines PDF itself (C(2025) 884) was not opened, so the bank/AML example is reported through FPF's summary. Paragraph numbers were not captured.

---

## Claim (f): ANSPDCP fine against UniCredit Bank in 2026

### Takeaway
**VERIFIED from press reports.** In 2026, ANSPDCP fined UniCredit Bank S.A. a **total of 62,714 lei (about €12,000)** in two fines: **52,270 lei (€10,000)** for inadequate security measures and **10,454 lei (€2,000)** for late notification of the breach. The case involved erroneous notifications that disclosed clients' personal data. The investigation ended in May 2026 and the fine was reported in early June 2026. The ANSPDCP primary press release was not opened.

### Cited Findings
- ANSPDCP fined UniCredit Bank SA 62,714 lei in total (about €12,000): 52,270 lei (€10,000) plus 10,454 lei. The investigation concluded in May 2026, and erroneous notifications disclosed clients' names, addresses and other data. [V-SECONDARY] [Economica.net](https://www.economica.net/anspdcp-a-amendat-recent-o-banca-importanta-din-romania-pentru-divulgarea-datelor-unor-clienti-la-cat-s-a-ridicat-sanctiunea_946919.html); [Informat.ro](https://informat.ro/current-affairs/unicredit-romania-fined-12000-euros-for-disclosing-personal-data-124341)
- One outlet says the notifications concerned insurance policies and went to **mortgage-loan clients** by mobile banking, online banking and e-mail. The split was €10,000 for missing security measures and €2,000 for delayed breach notification. [V-SECONDARY] [Financiarul.ro](https://financiarul.ro/finante-si-banci/decizia-care-vizeaza-clientii-cu-credite-ipotecare-o-banca-de-top-plateste-12000-de-euro/index.html.md)
- **Do not confuse it with**:
  - The **2019** ANSPDCP fine on UniCredit of **€130,000** under GDPR art. 25(1), which concerned 337,042 data subjects. [Bugetul.ro](https://www.bugetul.ro/lovitura-pentru-unicredit-bank-amenda-uriasa-pentru-practicile-sale/); [Enforcement Tracker](https://www.enforcementtracker.com/ETid-3184)
  - The **Competition Council ROBOR** decision of June 2026, which fined about 431 million lei for UniCredit and also fined other banks. UniCredit is contesting it. That is a competition case, not a GDPR one. [UniCredit BVB announcement, 08.06.2026](https://bvb.ro/infocont/infocont26/UCB27_20260608114139_RO-Anunt-UniCredit-Bank-referitor-la-comunicatul-Consiliului.pdf)

### Inferences
- The case is relevant to the agents' design. Automated customer notifications (refund or dispute status) are a data-breach vector: wrong-recipient sends are a GDPR art. 32/33 risk. Template-to-recipient binding checks and breach-notification runbooks should be part of the solution.

### Gaps
- The dataprotection.ro press release and its exact date were not retrieved. The GDPR articles cited are inferred from "security measures" and "late notification" (art. 32 and art. 33) and were not quoted.

---

## Claim (g): Legea 209/2019 art. 171–172 on burden of proof (PIN/OTP alone not sufficient proof of authorisation)

### Takeaway
**VERIFIED in substance, with two corrections.**
- (1) The statutory wording is that use of a payment instrument recorded by the PSP is "**nu este în mod necesar suficientă**" ("not necessarily sufficient"). That is weaker than "not sufficient". OTP or PIN evidence alone does not discharge the burden, but it can count together with other evidence.
- (2) The **T+1 refund** obligation is in **art. 173**, not art. 171–172. Art. 171 transposes PSD2 art. 72, and art. 172, according to the commentary, places the burden of proving fraud or gross negligence on the PSP.

### Cited Findings
- **Art. 171**, as quoted and summarised by the commentary [V-SECONDARY: commentary quoting the law] [JURIDICE.ro, E. Jiurjiu, 30.09.2026](https://www.juridice.ro/856214/autorizarea-operatiunii-de-plata-versus-autentificarea-utilizatorului-de-la-eroarea-bancara-la-raspunderea-bancii.html):
  - When the user denies authorising an operation, the PSP must prove that it was authenticated, accurately recorded, entered in the accounts, and not affected by a technical breakdown or other deficiency.
  - Use of a recorded payment instrument "nu este în mod necesar suficientă" to prove authorisation, fraud or gross negligence.
  - It mirrors PSD2 art. 72(2), which requires the PSP to provide supporting evidence.
- **Art. 172**: per the same commentary, "sarcina probei cu privire la frauda sau neglijența gravă revine prestatorului" (the author's phrasing, not the statute's). [V-SECONDARY] (same source)
- **Art. 173**: the PSP must refund an unauthorised operation immediately, and in any event by the end of the next business day after noting or being notified of it. The exception is where the PSP has reasonable grounds to suspect fraud and "comunică în scris aceste motive autorității competente" (communicates these reasons in writing to the competent authority). [V-SECONDARY] (same source)
- The commentary's key argument:
  - Authorisation means the payer's consent (arts. 147–148). Authentication only proves that the instrument or credential was used.
  - An OTP, PIN or app confirmation does not prove consent.
  - The PSP must also show dynamic linking of the authentication to the amount and payee (Delegated Regulation 2018/389, art. 5).
  - In phishing cases, use of a stolen credential does not make a transaction authorised.
  - Source: [JURIDICE.ro](https://www.juridice.ro/856214/autorizarea-operatiunii-de-plata-versus-autentificarea-utilizatorului-de-la-eroarea-bancara-la-raspunderea-bancii.html)
- Consolidated text of Legea 209/2019: [Lege5](https://lege5.ro/gratuit/gm2tcnbxhe2q/legea-nr-209-2019-privind-serviciile-de-plata-si-pentru-modificarea-unor-acte-normative). [Not opened; the search confirms the "nu este în mod necesar suficientă" wording is in the law]
- Context [V-PRIMARY]: the EBA/ECB report says new fraud types involve "manipulating legitimate users into authenticating fraudulent transactions". These are APP scams: the payer consents, so the transaction is authorised under PSD2. [ECB press release](https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.pr251215~e133d9d683.en.html)

### Inferences
- **Judge agent decision logic**:
  - **Unauthorised**: the customer did not consent, for example credentials were phished and the fraudster initiated the payment, or remote-access malware was used. Refund under **art. 173 by end of the next business day**. The burden is on the bank (art. 171–172) to prove authorisation or the customer's gross negligence.
  - **APP**: the customer initiated or consented to the payment under manipulation. There is no statutory refund right under the current law. Recovery depends on recall and any voluntary goodwill policy.
  - The evidence pack should capture SCA logs with dynamic-linking data (amount and payee shown to the customer), device binding (new device or emulator), session anomalies (remote-access tools, unusual IP or ASN), timing (login-to-payment gap, new payee added just before the payment), SANB name display, and the phishing domain's age and similarity score.
- Do not tell judges or the jury that "OTP is never sufficient". Say that OTP or PIN use is "not necessarily sufficient" and that the bank must provide supporting evidence.

### Gaps
- The verbatim text of art. 171 letters a)–b) and of art. 172 was not retrieved from the official consolidated text. Confirm it on legislatie.just.ro or Lege5 before quoting article letters.
- How the EU Payment Services Regulation (PSR/PSD3) negotiations are changing APP and impersonation-fraud liability, and whether that will apply by 2027–2028, was not researched.
