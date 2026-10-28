# Card disputes, chargebacks and fraud claims at Romanian card issuers (focus: Raiffeisen Bank România), status late Oct 2026

Source labels: **[P]** primary document opened and read in this session (text extracted from the PDF); **[S]** secondary (press, law firm, processor documentation); **[V]** vendor claim; **[snippet]** seen only in search-result summaries, page not opened, so verify before reuse. Items older than 2024 carry their year. Legea 209/2019 articles 169, 173, 177, 179 and 224, and the general phishing/DNSC statistics, are covered in `reguli_kyc_aml_credit_plati_reclamatii.md` §3–4 and are only cross-referenced here.

## 1. Verifying the "about 64% of complaints are disputed card transactions" statement

### Takeaway
The figure is verified, with one correction. It comes from Raiffeisen Bank România's **Raport Anual 2025** (in Romanian), p. 41. It describes **all complaints registered by the bank in 2025**. The report prints it in the paragraph after the PULS/Medallia paragraph, but never says the 64% was measured on PULS. The report gives no absolute complaint count and no breakdown by type of dispute.

### Cited Findings
- Exact sentence (diacritics restored): „Din totalul reclamațiilor, aproximativ 64% reprezintă tranzacții cu card contestate." The sentence before it says the number of complaints registered by Raiffeisen Bank in 2025 fell 3% versus 2024. The sentence after it says that in 2025 the bank resolved 34 conciliation files through CSALB (Centrul de Soluționare Alternativă a Litigiilor în domeniul Bancar), with a total benefit to clients of about EUR 90,000 [P] — [Raiffeisen Bank România, Raport Anual 2025, p. 41](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf)
- Location: PDF page 41 (printed "041"), chapter "Raportul diviziilor" (retail part). It sits under the sub-heading "Construim viitorul bankingului împreună cu clienții noștri", right after the "Carduri și plăți" block. The PDF's InDesign last-modified stamp is 29 April 2026 [P] — [Raport Anual 2025](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf)
- The PULS paragraph is separate and comes immediately before. It says the strategic partnership with Medallia supports continuous development of the "PULS Customer Experience" platform, which gives a centralised, real-time view of client information. It also says the bank collects more than 200,000 feedback items a year from branch visits, personal-banker interactions, direct sales, digital channels, the call centre and the complaints-management department. A Mystery Shopping programme is mentioned next [P] — [Raport Anual 2025, p. 41](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf)
- Card context in the same chapter (2025):
  - virtual credit and debit cards usable from account opening (online, wallet, phone payments);
  - e-wallet transactions up more than 60% year on year;
  - "my Visa" integrated in Smart Mobile;
  - online card transactions authorised directly in Smart Mobile, without Smart Token;
  - card purchases convertible into interest-free instalments in the app.

  Most payments ran through cards issued by the bank and its digital apps [P] — [Raport Anual 2025, pp. ~40–41](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf)
- A targeted Romanian search found no press release, sustainability report or Medallia case study that repeats the 64%. Press results only showed older card incidents at Raiffeisen, for example a 2022 case of ten unauthorised transactions totalling EUR 9,300, where the client went to ANPC and the police after about three months [S, snippet, 2022] — [Capital.ro (2022)](https://www.capital.ro/au-ramas-fara-banii-de-pe-card-este-soc-total-in-sistemul-bancar-din-romania.html)

### Inferences
- In Romanian banking usage, "tranzacții cu card contestate" covers *refuz la plată* (chargeback) requests and unauthorised-transaction claims. BCR, for example, formats its dispute intake as a complaint letter ("Aviz de refuz la plată / Letter of Complaint", see §4). If Raiffeisen also logs every card dispute as a *reclamație*, then the 64% measures dispute intake workload rather than dissatisfaction alone. This is an inference to confirm with Raiffeisen mentors.
- For the pitch, cite it as "Raiffeisen Bank România, Raport Anual 2025, p. 41: about 64% of complaints registered in 2025 were disputed card transactions". Do not call it "64% of PULS complaints".
- Raiffeisen's 2025 move to in-app (Smart Mobile) approval of online card payments means the bank holds its own SCA and 3-D Secure approval logs (device, biometric or PIN approval, timestamp). Those logs are the central evidence in unauthorised-CNP claims (see §2–3).

### Gaps
- Not published: the absolute number of complaints or card disputes; the split into fraud, consumer dispute and processing error; handling times; chargeback win rates.
- The 2024 annual report was not checked for a comparable percentage, so no trend is available.
- medallia.com was not searched specifically for a Raiffeisen România customer story.

## 2. Visa and Mastercard dispute rules relevant to an issuer back office (2025–2026)

### Takeaway
Visa's rules are public and current. The **Visa Core Rules and Visa Product and Service Rules, edition 18 April 2026**, together with Visa's **October 2026** merchant guide, give rules an agent can encode directly:
- four dispute categories (10 Fraud, 11 Authorization, 12 Processing Errors, 13 Consumer Disputes);
- a 120-day issuer window for most conditions;
- 30/30/10-day downstream stages, where a missed deadline loses the case;
- explicit invalidity rules, for example no fraud dispute on a Visa Secure-authenticated (ECI 5 + CAVV) e-commerce transaction, a cap of 35 disputes per account in 120 days, and no fraud dispute for crypto/NFT purchases the cardholder made under deception;
- Compelling Evidence 3.0, which allows cross-merchant prior transactions from 24 Oct 2026.

Mastercard's official Chargeback Guide could not be retrieved (HTTP 403), so its timeframes below are secondary and partly conflicting.

### Cited Findings

#### Visa: structure, stages and deadlines (primary)
- **Categories and conditions (Apr 2026 rules):**
  - 10 Fraud: 10.1 EMV Liability Shift Counterfeit; 10.2 EMV Liability Shift Non-Counterfeit; 10.3 Other Fraud – Card-Present; 10.4 Other Fraud – Card-Absent; 10.5 Visa Fraud Monitoring Program.
  - 11 Authorization: 11.1 Card Recovery Bulletin; 11.2 Declined Authorization; 11.3 No Authorization/Late Presentment.
  - 12 Processing Errors: 12.2 Incorrect Transaction Code; 12.3 Incorrect Currency; 12.4 Incorrect Account Number; 12.5 Incorrect Amount; 12.6 Duplicate Processing/Paid by Other Means; 12.7 Invalid Data.
  - 13 Consumer Disputes: 13.1 Merchandise/Services Not Received; 13.2 Cancelled Recurring; 13.3 Not as Described/Defective; 13.4 Counterfeit Merchandise; 13.5 Misrepresentation; 13.6 Credit Not Processed; 13.7 Cancelled Merchandise/Services; 13.8 Original Credit Transaction Not Accepted; 13.9 Non-Receipt of Cash at an ATM.

  There is no 12.1: late presentment sits under 11.3 [P] — [Visa Core Rules and Visa Product and Service Rules, 18 Apr 2026, ch. 11](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- The October 2026 merchant guide uses the same four categories. Its table of contents and section headings label 10.3 as "EMV Liability Shift Counterfeit Fraud" and 13.1 as "Invalid Data". These look like editorial errors, so use the Core Rules names [P] — [Visa Dispute Management Guide for Merchants, Oct 2026](https://by.visa.com/dam/VCOM/global/support-legal/documents/merchants-dispute-management-guidelines.pdf)
- **Fraud and Authorization flow** (categories 10 and 11, Table 11-1) has no "dispute response" stage:
  - Issuer opens the Dispute (time limit set per condition).
  - Acquirer may make a pre-Arbitration attempt within **30 calendar days** of the Dispute Processing Date.
  - Issuer answers within **30 days**. It accepts liability, or declines if it has new information or can rebut Compelling Evidence.
  - Acquirer may file Arbitration within **10 calendar days** of the pre-Arbitration response [P] — [Visa Rules Apr 2026, Table 11-1](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Processing Errors and Consumer Disputes flow** (categories 12 and 13, Table 11-2):
  - Issuer opens the Dispute.
  - Acquirer sends a Dispute Response within **30 days**.
  - Issuer may make a pre-Arbitration attempt within **30 days** of the Dispute Response, with new information, a changed condition, or a certification that the cardholder still disputes after reviewing the merchant's evidence.
  - Acquirer answers within **30 days**.
  - Issuer may file Arbitration within **10 days** [P] — [Visa Rules Apr 2026, Table 11-2](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **General process rules (11.2.1):**
  - Each transaction must be disputed separately, and only once (10.5 excepted).
  - When counting deadlines, the processing date of the preceding event does not count as a day.
  - If a member does not act in **Visa Resolve Online (VROL)** within the timeframe, or accepts responsibility, the cycle closes and that member bears the last amount received.
  - Dispute financials go through VROL or VisaNet on the same day as the VROL action [P] — [Visa Rules Apr 2026, §11.2.1](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Issuer duties (11.1.2):**
  - Extend to cardholders all protections provided under applicable law, using the issuer's customary practices.
  - Never process invalid disputes, and carry out "adequate due diligence" on each dispute.
  - Provide enhanced support for Visa Signature and Infinite cardholders during disputes [P] — [Visa Rules Apr 2026, §11.1.2](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Proof of the cardholder's claim:**
  - Category 10: the issuer may *certify* on the cardholder's behalf only if the claim came through a secure method equal to a signature. Examples are secure online banking with password or login, or telephone banking at funds-transfer security level. Otherwise it needs a signed cardholder letter with the full or partial card number, merchant name(s) and amount(s).
  - Category 13: the same applies to non-receipt letters [P] — [Visa Rules Apr 2026, §11.7.1, §11.10.1](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Time limits:**
  - 10.4: **120 calendar days from the Transaction Processing Date**.
  - 13.1: within 120 days of the processing date or of the last expected delivery date, **never more than 540 days** after processing. The issuer must first wait **15 calendar days** in some cases (no delivery date specified, goods returned, merchant cancelled), or 30 days for travel agencies and ticket resellers [P] — [Visa Rules Apr 2026, Tables 11-29, 11-92](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Minimum dispute amount:** T&E transactions have a **USD 25** minimum (or local-currency equivalent) under most conditions. From 18 Apr 2026 either the transaction amount or the partial dispute amount must reach that minimum. The exclusion list names 10.1–10.5, 13.3, 13.8 and 13.9, but footnotes narrow some of these exclusions (for 10.2–10.4, to the Visa Commercial Choice Travel product). The rest of the table, including any Europe-specific rows, was not reviewed [P] — [Visa Rules Apr 2026, Table 11-5](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)

#### Visa: fraud disputes (10.4) and evidence (primary)
- **When 10.4 applies:** the cardholder denies authorising or taking part in a card-absent transaction. Before opening the dispute, the issuer must report the fraud activity to Visa. (The table layout suggests this applies to all regions. The adjacent rule on high-risk MCCs 4829, 5967, 6051, 6540, 7801, 7802 and 7995 applying "regardless of ECI" is US-domestic.) [P] — [Visa Rules Apr 2026, Table 11-27](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **10.4 is invalid** (selection), when:
  - the account number already has **more than 35 disputes** opened by the issuer in the previous 120 days;
  - it is an e-commerce transaction with **ECI 5** where the issuer answered with an Authentication Confirmation through **Visa Secure with EMV 3DS** and the **CAVV** was in the authorisation;
  - it is an authenticated tokenised transaction (TAVV present and an approved cardholder verification method);
  - the cardholder **took part in buying crypto or an NFT but later says they were deceived** into sending it to a fraudulent recipient;
  - CE3.0 criteria are met (next bullet).

  ECI 6 "attempted" authentication also creates invalidity under conditions that were not fully read [P] — [Visa Rules Apr 2026, Table 11-28](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Compelling Evidence 3.0 (CE3.0):** a 10.4 dispute is invalid, or can be defeated at pre-Arbitration, when:
  - **two earlier transactions** on the same credential were *not reported by the issuer as fraud*;
  - they were processed more than 120 days before the dispute (the guide adds: within 365 days before the disputed transaction);
  - device ID, device fingerprint or IP address, plus at least one more element (login ID, full delivery address), match;
  - goods/services descriptions are provided (or purchase-order numbers for Visa Secure ECI 7 cases).

  Format rules: device ID at least 15 characters in clear text; fingerprint at least 20 characters, hashing allowed; IP address in clear text.

  **From 24 Oct 2026** the two prior transactions may come from **one or more merchants**, on the same card or an associated token. Device ID and fingerprint then count as the same element, so the acquirer cannot supply both [P] — [Visa Rules Apr 2026, Table 11-28](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf); [Visa merchant guide Oct 2026, pp. 22–23, 78–79](https://by.visa.com/dam/VCOM/global/support-legal/documents/merchants-dispute-management-guidelines.pdf). CE3.0 originally took effect in April 2023 [S, snippet] — [Qualpay help](https://help.qualpay.com/help/visa-compelling-evidence-30-ce-30-and-april-2023-changes)
- **Issuer response to Compelling Evidence at pre-Arbitration (fraud and authorization):** the issuer must certify one of two things:
  - the contact details the merchant supplied do not match its cardholder records; or
  - it contacted the cardholder to review the evidence and recorded why they still dispute.

  If the evidence is delivery to an address with an AVS "Y" match, the issuer must explain why it returned "Y" [P] — [Visa Rules Apr 2026, Table 11-1](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Fraud reporting duty (Visa Core Rules 1.9.4.3):**
  - The issuer reports fraud activity through VisaNet on detection, whatever the transaction status.
  - For approved fraud, this must happen within **60 calendar days of the transaction date**, or within 30 days of receiving the cardholder's notification if that came later.
  - At least 90% of rejected reports must be resubmitted and accepted.
  - **Europe intraregional:** 80% of lost/stolen/counterfeit/never-received fraud within 60 days and the rest within 90; 65% of fraudulent credential use within 60 days and the rest within 90.
  - Non-compliance brings elevated risk scoring and fees [P] — [Visa Core Rules Apr 2026, §1.9.4.3](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **How disputes are reviewed:** against the condition, eligibility, timing and stage-permitted documentation, not intent or effort. Extra documentation beyond what is required "does not necessarily influence the outcome", and evidence submitted at the wrong stage may be disregarded [P] — [Visa merchant guide Oct 2026, pp. 11–12](https://by.visa.com/dam/VCOM/global/support-legal/documents/merchants-dispute-management-guidelines.pdf)
- **Pre-dispute deflection:**
  - **Verifi Order Insight** lets participating merchants share enhanced purchase details with participating issuers when a cardholder questions a charge.
  - **Rapid Dispute Resolution (RDR)** lets merchants (through their acquirer) set rules that auto-accept eligible disputes. Acceptance triggers VROL to create a case that moves liability [P] — [Visa merchant guide Oct 2026, p. 99](https://by.visa.com/dam/VCOM/global/support-legal/documents/merchants-dispute-management-guidelines.pdf)
- Visa Claims Resolution (VCR), launched in April 2018, grouped the old reason codes into the four categories. Fraud and authorization run as an "allocation" flow, processing and consumer disputes as a "collaboration" flow [S, snippet, 2018] — [chargeback.io on VCR](https://www.chargeback.io/fr/blog/what-is-visa-claims-resolution)

#### Mastercard (official guide not retrievable; secondary)
- Mastercard's Chargeback Guide PDF on mastercard.us returned **HTTP 403** in this session — [Mastercard Chargeback Guide (blocked)](https://www.mastercard.us/content/dam/public/mastercardcom/na/global-site/documents/chargeback-guide.pdf)
- **Main issuer chargeback reason codes** (processor spec, undated):
  - 4808 Authorization-related;
  - 4834 Point-of-Interaction Error (processing);
  - **4837 No Cardholder Authorization** (fraud);
  - **4853 Cardholder Dispute**;
  - fraud group also covers 4849 Questionable Merchant Activity, 4870 Chip Liability Shift and 4871 Chip Liability Shift Lost/Stolen/NRI;
  - 4863 eliminated 17 July 2020; 4840 eliminated.

  The cycle runs: chargeback (issuer) → representment, or second presentment (acquirer) → issuer accepts or files pre-arbitration → acquirer accepts or declines → issuer files arbitration with Mastercard [S] — [Valitor/Rapyd dispute spec, Mastercard](https://specs.valitor.is/Dispute/mastercard/)
- A merchant-side guide says 4855 and 4863 no longer exist as stand-alone codes and now run through 4853 and 4837. It claims to have checked a 19 May 2026 edition of the Mastercard guide [S, snippet, unverified] — [redo.com](https://redo.com/resources/articles/chargebacks/mastercard-chargeback-reason-codes)
- **Timeframes (secondary, conflicting):**
  - First chargeback generally within 120 days.
  - Second presentment within 45 days.
  - Issuer pre-arbitration within 45 days of second presentment, though some sources say 30.
  - Acquirer pre-arbitration response within 30 days.
  - Arbitration case filing reported as no earlier than 30 and no later than 75 days after second presentment.
  - Sources disagree on whether pre-arbitration is mandatory (reported as mandatory for 4853/4834 and optional for 4837/4808).
  - Pre-arbitration cases are filed in **Mastercom** [S, snippet] — [Chargeback Gurus](https://www.chargebackgurus.com/blog/mastercard-chargeback); [ChargebackStop](https://www.chargebackstop.com/blog/mastercard-chargeback-rules); [Chargeflow, reason codes](https://chargeflow.io/blog/mastercard-chargeback-reason-codes); [Chargeflow, time limits (general 120-day window)](https://www.chargeflow.io/fr/blog/chargeback-time-limit)
- **First-Party Trust** (Mastercard's friendly-fraud programme): merchants share enhanced data (purchase history, device, identity, delivery, location) at authorisation or after a dispute, so issuers can tell first-party misuse from third-party fraud. Merchants that meet the data requirements may get chargeback protection. In **June 2025** it expanded from the US to Canada, Latin America and the Caribbean, and Asia Pacific. Europe was not in that list [S, snippet] — [Mastercard press release, June 2025](https://www.mastercard.com/news/latin-america/en/newsroom/press-releases/pr-en/2025/june/to-counter-friendly-fraud-mastercard-expands-technology-to-new-markets); [PYMNTS](https://www.pymnts.com/mastercard/2025/mastercard-targets-friendly-fraud-with-expanded-program/). A vendor explainer says First-Party Trust does not help with stolen-card disputes, because no matching history exists [V, snippet] — [cside](https://cside.com/blog/mastercard-fpt-how-it-reduces-chargebacks)
- **Mastercard "State of Chargebacks" 2025:**
  - global chargeback cost to merchants forecast at about **USD 42 bn by 2028**, "nearly half" reported as fraud;
  - volume forecast of **261 million chargebacks in 2025**, rising to **324 million by 2028**;
  - fraud share about 45%; first-party misuse "over a quarter" [S, snippet] — [Fintech Times](https://thefintechtimes.com/?p=125007); [Stripe Sessions 2025 summary](https://stripe.com/th/sessions/2025/mastercard-strategies-for-reducing-chargebacks)

### Inferences
- **Recoverability rule, the core issuer economics:**
  - Under PSD2 most EEA e-commerce card payments are authenticated with SCA via 3-D Secure (apart from exemptions such as low value, transaction-risk analysis, and merchant-initiated or recurring payments).
  - A Visa CNP fraud claim on a Visa Secure-authenticated transaction (ECI 5 + CAVV) **cannot be charged back under 10.4**.
  - When Raiffeisen must still refund an "unauthorised" claim under Legea 209/2019 and the CJEU ruling (§3), the loss stays with the bank unless it can later prove *neglijență gravă*.
  - The agent should therefore compute a "chargeback-recoverable: yes/no" flag early, from ECI, CAVV, token and wallet, POS entry mode and MCC. This changes which team handles the case.
- **Configurable deadline table:** the agent should hold one row per scheme × condition × stage rather than hard-coded numbers. Visa rows can be filled from the April 2026 Core Rules. Mastercard rows should be marked "to confirm against the Mastercard Chargeback Guide or Mastercom" for the synthetic dataset.
- **Rules the agent can apply directly:**
  1. Is the claim within the 120-day scheme window (13.1: 540-day cap and 15-day wait)?
  2. Has the account had more than 35 fraud disputes in 120 days?
  3. Is it a crypto/NFT purchase the cardholder made under deception? Then it is not 10.4; treat as a scam or authorised-payment case.
  4. Has fraud been reported to Visa before the dispute and within 60 days?
  5. Did intake come through an authenticated channel (Smart Mobile or authenticated call)? Then issuer certification is enough; otherwise request a signed letter.
  6. For CE3.0 pre-arbitration, check whether the bank itself flagged the two prior transactions as fraud; from 24 Oct 2026 this can involve other merchants.
  7. Missing a VROL deadline means automatic loss.
- **Reason-code selection** is a good AI task (narrative → category/condition). It must be constrained by the hard invalidity rules above, because Visa reviews strictly by condition, eligibility and timing.

### Gaps
- Mastercard's official 2025–2026 timeframes, 4837 prerequisites (for example, reporting to the Mastercard Fraud and Loss Database before a chargeback) and any per-account cap were not verified from a Mastercard document.
- Visa Europe-region specifics (domestic Romanian rules, SCA-exemption handling in disputes, Europe rows of the minimum-amount table, full ECI 6 conditions) were not fully read.
- No public source showed whether First-Party Trust or Visa Order Insight is live with Romanian issuers.

## 3. Romanian practice: PSD2 refund duty plus scheme chargebacks, gross-negligence refusals, evidence, and authority and court positions (2023–2026)

### Takeaway
The legal position changed in October 2026. In **CJEU C-70/25 (15 Oct 2026)**, the Court held that a PSP **may not refuse the immediate refund** (by the end of the next business day) of an unauthorised transaction on the ground of the customer's *neglijență gravă*. The only exception is reasonable suspicion of fraud by the customer, notified to the competent authority. The bank may later try to recover the loss, and it carries the burden of proving gross negligence.

Romanian practice up to 2026, as documented by CSALB, ran the other way: banks treated SCA-authenticated or "holder-enabled" operations as authorised and refused or closed fraud claims. No Romanian court decision, BNR guidance or ANPC sanction specific to unrefunded card or phishing fraud was found.

### Cited Findings
- **CJEU, Case C-70/25 [Tukowiecka], judgment of 15 Oct 2026** (press release 147/26). A Polish customer was phished through a fake buyer on a sales platform and a spoofed bank site, losing about EUR 700. Her bank refused a refund, citing gross negligence. The Court held:
  - the PSP must refund an unauthorised transaction immediately, at the latest by the end of the next business day after noting or being notified, provided the customer notified without undue delay;
  - the **only** exception is reasonable grounds to suspect **fraud by the customer**, communicated to the competent national authority;
  - the PSP's view that the customer was grossly negligent **does not** entitle it to refuse the immediate refund;
  - refund and final allocation of loss are separate questions; afterwards the PSP may seek reimbursement if it proves intent or gross negligence, and **the burden of proof is on the PSP** [P] — [CJEU press release No 147/26](https://curia.europa.eu/site/upload/docs/application/pdf/2026-10/cp260147en.pdf)
- **Advocate General Rantos's Opinion (5 Mar 2026)** reached the same conclusion under PSD2 **art. 73(1)**. It notes there is no immediate-refund duty if the customer notifies more than 13 months after the debit. If the customer refuses to repay later, the bank must go to court itself [P] — [CJEU press release No 31/26](https://curia.europa.eu/site/upload/docs/application/pdf/2026-03/cp260031en.pdf). (In Romania, PSD2 art. 73 is transposed by Legea 209/2019 art. 173; see the project's legal notes.)
- Law-firm commentary:
  - the ruling does not mean customers are always finally released from liability after phishing;
  - it cannot be extended automatically to every form of banking fraud;
  - older cases rejected solely for gross negligence may merit review if not time-barred [S, snippet] — [Lewis Silkin, 21 Oct 2026](https://www.lewissilkin.com/insights/2026/10/21/cjeu-confirms-immediate-refund-duty-for-unauthorised-payments-despite-customer-gr-102o62q); [MTR Legal](https://www.mtrlegal.com/en/cjeu-strengthens-rights-of-phishing-victims/)
- **CSALB press release, 9 Sept 2026:**
  - In 2026 consumers sent CSALB **more than 170 requests about fraud through banking channels**.
  - Most concern **loans taken out in the victim's name** after criminals got passwords, confidential data, or control of phones and banking apps. Some concern loans the victims took out themselves and transferred onward (crypto, "shares", covering supposed debts).
  - Losses in the analysed cases reach **EUR 20,000**.
  - In most cases **banks do not accept conciliation**. Their reasons: the cases are under police investigation, and the criminals did not attack the bank's security systems but accessed accounts with the holders' help.
  - All of the cases presented had been closed or rejected by the banks [P] — [CSALB, "Se înmulțesc fraudele cu credite bancare", 09.09.2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- **Typical bank reasoning, from the same release:**
  - In a remote-access malware case (an app installed via WhatsApp; a 29,000 lei loan; 90,000 lei taken from accounts through successive transfers sized to stay under security limits), the bank answered that payments came from the homebanking app with SCA (security code or phone biometrics), that it executed transfers as instructed, and that under the law a payment order is correctly executed if it follows the IBAN the payer gave.
  - In another case the bank demanded repayment of a fraudulent credit card because access "had been authorised" by the client. The client accepted a 36-month rescheduling to avoid *poprire* [P] — [CSALB 09.09.2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- **BNR's representative on CSALB's Coordination College** (Alexandru Păunescu) said that in most fake-credit cases consumers who gave criminals access to accounts, apps, phones or laptops bear the losses in full. He warned that video-identification recordings made for fake "brokers" can be reused through deepfakes to get past banks' authentication [P] — [CSALB 09.09.2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- **Raiffeisen's own CSALB outcome:** 34 conciliation files resolved in 2025, worth about EUR 90,000 to clients. The topics are not given [P] — [Raport Anual 2025, p. 41](https://www.raiffeisen.ro/content/dam/rbi/retail/eu/ro/documents/rapoarte/anuale/2025-Raport-anual-Raiffeisen-Bank.pdf.coredownload.inline.pdf)
- **Provisional credit in Romanian practice (BCR, Jan 2026 form):**
  - By signing the dispute form the client accepts that the bank may take back "amounts credited in advance" for disputed transactions, including where there are fraud indicators, if the dispute proves unjustified or the merchant already refunded.
  - The bank may charge a fee for an unjustified dispute.
  - The bank may block and reissue the card at the client's cost [P] — [BCR, Aviz de refuz la plată, ian. 2026](https://cdn0.erstegroup.com/content/dam/ro/bcr/www_bcr_ro/informatii-utile/Refuz-la-Plata_ian2026.pdf)
- **Evidence asked of clients (BCR):**
  - merchant processing confirmation (POS slips, e-tickets, confirmation e-mails);
  - goods or services details;
  - proof of paying by other means;
  - proof of trying to contact the merchant;
  - proof of cancellation;
  - **a police complaint (*sesizare la Poliție*) for fraud**;
  - any other written evidence [P] — [BCR form, Jan 2026](https://cdn0.erstegroup.com/content/dam/ro/bcr/www_bcr_ro/informatii-utile/Refuz-la-Plata_ian2026.pdf). An earlier secondary source also reports Romanian banks often asking for a police complaint in cloning or unauthorised cases (see `reguli_kyc_aml_credit_plati_reclamatii.md`).
- A consumer guide (Aug 2026) describes the escalation path after a refused fraud refund: formal complaint to the bank, then CSALB, ANPC or court [S, snippet] — [Bitdefender RO](https://www.bitdefender.com/ro-ro/blog/hotforsecurity/banca-refuza-rambursarea-frauda)
- **ANPC:** no 2025–2026 ANPC sanction about refusals to refund card or phishing fraud was found. ANPC's 2025 actions against 11 banks (550,000 lei in fines, partly suspended in court) concerned loan-instalment calculation, not fraud [S, snippet] — [Euronews RO](https://www.euronews.ro/articole/presedintele-anpc-a-semnat-11-ordine-de-incetare-a-practicilor-inselatoare-de-cat)
- **EU context (not binding in Romania):** an Antwerp court ruled in June 2026 that banks must reimburse phishing victims immediately [S, snippet] — [VRT News, 3 Jun 2026](https://www.vrt.be/vrtnws/en/2026/06/03/court-rules-banks-must-compensate-phishing-victims-immediately/)

### Inferences
- **Two-step decision model.** C-70/25 is binding on Romanian courts when they interpret art. 173 of Legea 209/2019. For a claim the client classifies as *unauthorised*, the agent should:
  1. check notification within 13 months;
  2. check for **reasonable grounds to suspect client fraud**. If found, hold the refund and draft the written notice to the competent authority (exception path, human sign-off);
  3. otherwise refund (provisional credit) by the end of the next business day;
  4. open a separate track for "*neglijență gravă* assessment / recovery from client" with an evidence pack. The bank carries the burden of proof, and the 30 EUR cap under art. 179(1) applies where there is no gross negligence;
  5. in parallel, open a scheme chargeback only if it is recoverable (§2).

  Refusing up front because of gross negligence, as CSALB's 2026 cases describe, is now high-risk for unauthorised transactions.
- **Authorised vs unauthorised is the key classification and the hardest one.** In remote-access, malware or "lawyer friend" cases, banks argue that SCA plus device equals authorisation. Under Legea 209/2019 art. 171–172 (see legal notes), using the instrument alone is not necessarily enough proof. The agent should therefore record *who* performed the SCA step and *how*: new device binding, remote-access app indicators, unusual session, transfers split under limits, newly enrolled device. It should flag these for human review instead of auto-labelling them "authorised".
- **Authorised push-payment scams** need separate handling: social engineering where the victim takes a loan, withdraws cash and loads a crypto ATM, or buys crypto by card. These are outside the unauthorised-refund regime, and for card crypto purchases they are explicitly invalid under Visa 10.4. The agent should route them to fraud investigation and support (police complaint, rescheduling, Biroul de Credit handling) with a clear explanation letter, not to the chargeback queue.
- **Evidence pack per unauthorised card claim** (inferred from Visa rules, CSALB cases and the BCR form):
  - 3DS / Visa Secure result (ECI, CAVV, authentication timestamp, approval channel: Smart Mobile push, biometrics, PIN);
  - device-binding history and IP;
  - card status timeline (lost/stolen reported at);
  - merchant MCC and country (EEA or non-EEA, since SCA may not apply outside the EEA);
  - the bank's own earlier fraud flags (needed for CE3.0 rebuttals);
  - police complaint reference;
  - customer narrative.

### Gaps
- No Romanian court decision (tribunal, Curtea de Apel or ÎCCJ) from 2023–2026 on refunds of phishing, vishing, "cont sigur" or OLX/courier fraud was found. A targeted search on portal.just.ro, ReJust or juridice.ro is needed.
- No BNR guidance, BNR sanction or ANPC sanction specific to fraud-refund refusals was found.
- Not verified here: which authority (BNR or ANPC) receives the art. 173 "reasonable grounds to suspect fraud" notice for banks, and whether Romanian banks actually file such notices.
- Raiffeisen's own dispute form, provisional-credit policy, unjustified-dispute fee and police-complaint requirement were not found publicly (general T&C PDFs were not reviewed).
- The PSR/PSD3 impersonation-refund regime (around 2028) is covered in the legal notes and not repeated here.

## 4. Issuer dispute workflow, manual effort, benchmarks and documented AI results

### Takeaway
A Romanian issuer's dispute workflow can be rebuilt from public pieces: intake through app, contact centre or branch; a structured reason form; evidence collection including a police complaint for fraud; a 15-day answer target; and scheme filing in VROL or Mastercom against hard deadlines. The manual work sits in classification, evidence chasing, deadline tracking and customer letters. Public benchmarks are almost all vendor or merchant-side. **No independent or bank-published measurement of AI in issuer dispute handling was found.**

### Cited Findings
- **Intake and data model (BCR, Jan 2026), a close proxy for a Raiffeisen-style form:**
  - Cardholder data: name, card number, address, phone, e-mail, ID/CNP.
  - Transaction: date, amount, merchant/ATM name and location.
  - Reason taxonomy: ATM did not dispense (fully or partly); goods/services not provided (expected date); not as described or defective (return or cancellation date); order cancelled but not refunded; subscription cancelled; double debit; paid by other means; **"I neither made nor authorised the transaction"**, with card location at the time (in my possession / reported stolen / lost / **"I provided card data"**); other.
  - Free-text description; signed declaration authorising transmission to the acquirer.
  - Channels: **George app, Contact Center *2227, branch**.
  - Promise: "we analyse and come back to you **within a maximum of 15 days**" [P] — [BCR, Refuz la plată, Jan 2026](https://cdn0.erstegroup.com/content/dam/ro/bcr/www_bcr_ro/informatii-utile/Refuz-la-Plata_ian2026.pdf)
- **Scheme-side duties that create back-office work:**
  - due diligence on every dispute;
  - one dispute per transaction;
  - fraud reporting within 60 days (Europe: 60/90-day distribution);
  - cardholder certification or letter;
  - pre-Arbitration certifications after contacting the cardholder about merchant evidence;
  - VROL actions within 30/30/10-day windows, where non-response means loss [P] — [Visa Rules, 18 Apr 2026](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- **Statutory clocks** in the same workflow, covered elsewhere: refund of unauthorised transactions by the end of the next business day; complaint answer within 15 business days, extendable to 35 (Legea 209/2019 art. 173, 224) — see `reguli_kyc_aml_credit_plati_reclamatii.md`. The CJEU confirmed the next-business-day refund rule [P] — [CJEU press release 147/26](https://curia.europa.eu/site/upload/docs/application/pdf/2026-10/cp260147en.pdf)
- **Benchmarks (label carefully):**
  - "A credit card dispute typically takes between two business days and two weeks"; the vendor claims AI pre-fill and decision support cut average wait and handling time by 60% [V, snippet] — [Camunda Marketplace, credit-card fraud dispute handling](https://marketplace.camunda.com/en-US/apps/449510/credit-card-fraud-dispute-handling)
  - Manual issuer investigation estimated at USD 25–50 per dispute, falling to USD 2–5 with automation; resolution from 4–8 hours to 3–5 minutes [V] — [Maven AGI](https://www.mavenagi.com/resources/banking-transaction-disputes) (already in `ai_operatiuni_bancare_benchmark_reglementare.md`)
  - Merchant-side: about USD 28 of internal labour per manually worked dispute; total cost about USD 166; 60–80% "friendly fraud" [V/S] — [Chargeflow citing Chargebacks911](https://www.chargeflow.io/blog/cost-of-manual-vs-automated-chargeback-processing) (already in the benchmark note)
  - Market volume: 261 million chargebacks forecast for 2025, rising to 324 million by 2028; USD 42 bn merchant cost by 2028 [S, snippet] — [Fintech Times on Mastercard 2025 report](https://thefintechtimes.com/?p=125007)
- **Documented AI results (all self-reported):**
  - **Airwallex** (issuer of corporate cards; fintech; vendor blog): an LLM-based tool categorises disputes and auto-populates the forms submitted to Visa; it handles all its card-issuing dispute cases and cuts processing time by **40%**, or "nearly half" of manual submission time in another post [V, snippet] — [Airwallex blog](https://www.airwallex.com/us/blog/ai-corporate-card-dispute-processing)
  - **HCLTech** case study at an unnamed bank: more than **80%** process automation in chargeback handling [V, snippet] — [HCLTech](https://www.hcltech.com/de-de/case-study/reimagining-financial-workflows-with-ai-driven-chargeback-automation)
  - **N26** (bank, AWS Summit talk in May 2026, reported by a third party): "Payment Trouble" SLA improved from 48% to 85%. The speaker cautioned that unstructured data thrown directly at LLMs does not give usable chargeback decisions [S, snippet] — [Classmethod write-up](https://dev.classmethod.jp/en/articles/n26-aws-summit/)
  - Merchant-side vendors claim AI-assembled evidence wins 45–65% of disputes versus 20–30% manually [V, snippet] — [ChatFin](https://chatfin.ai/blog/chargeback-automation-ai-dispute-management-2026)
  - Older: an AI dispute platform pitched at FinovateFall **2019** to cut credit-card disputes that "traditionally take up to 45 days" and to score dispute qualification [V, 2019] — [PR Newswire, Finscend](https://prnewswire.com/il/news-releases/finscend-demonstrates-proprietary-ai-powered-bank-dispute-platform-at-finovatefall-2019-862054605.html)

### Inferences
- **Hackathon agent scope** ("input → predefined rules → outcome or exception"):
  1. *Intake parsing.* Free text or form → structured case, with a confidence score.
  2. *Classification.* Unauthorised (card-present or card-absent) / authorised scam / consumer dispute (13.x) / processing error (12.x) / authorisation (11.x) / ATM (13.9).
  3. *Legal clock.* 13-month check; refund due by the end of the next business day for unauthorised claims; 15/35-business-day answer.
  4. *Scheme clock.* Condition-specific window from the processing date; fraud reported to Visa ≤60 days; downstream 30/30/10.
  5. *Recoverability.* ECI/CAVV/token → can or cannot charge back.
  6. *Invalidity checks.* More than 35 disputes per 120 days; crypto/NFT deception; T&E USD 25 minimum; duplicate dispute.
  7. *Evidence checklist.* Gaps trigger a customer request (police complaint, merchant contact proof, cancellation proof).
  8. *Draft outputs.* Customer acknowledgement and answer letter in Romanian; dispute filing payload; written fraud-suspicion notice for the exception path.
  9. *Exceptions to humans.* Fraud suspicion against the client; gross-negligence recovery; authorised-scam cases; amounts above a threshold; CE3.0 rebuttal.
- **Minimum synthetic-data fields per case:** case_id, intake_channel, intake_authenticated (Y/N), customer_id, masked PAN or token, scheme, ARN/transaction ID, transaction date, processing date, amount, currency, merchant, MCC, merchant country (EEA flag), POS entry mode / card-present flag, wallet/token flag, ECI, CAVV present, 3DS version, SCA method and channel, device ID / IP, new-device-binding timestamp, card status events, claim reason (free text plus code), police complaint (Y/N, date), merchant-contact proof (Y/N), disputes on account in the last 120 days, prior fraud flags, provisional credit date, scheme stage and due date, outcome.
- **KPIs to show:** share of cases auto-classified to a valid condition; share auto-checked for invalidity; average time from intake to provisional credit (target ≤1 business day for unauthorised claims); zero missed VROL deadlines; complaint answers within 15 business days; human-review rate. Vendor benchmarks of 40–60% handling-time reduction are plausible targets, but they are not independent evidence.

### Gaps
- No issuer-side cost or handling-time data for Romania or the EU was found. Raiffeisen's internal volumes, FTEs and backlog are not public, so ask mentors.
- No Romanian bank has published results from AI in dispute handling. The Airwallex, HCLTech and Maven numbers are vendor self-reports. N26 is a third-party write-up of a conference talk.
- Mastercom API capabilities were not verified: the developer documentation page returned 404.

## 5. Fraud typologies in Romania 2024–2026 that generate disputes and claims, with numbers

### Takeaway
The claims hitting Romanian banks in 2025–2026 are dominated by **social engineering**:
- vishing with impersonation of bank, police or BNR;
- remote-access takeover of phones and banking apps;
- **loans contracted in the victim's name** or by the victim under manipulation, often cashed out through **crypto ATMs** or fake investment brokers;
- marketplace and courier phishing (the CJEU case pattern).

Classic card-not-present fraud continues, but official Romanian numbers are scarce. The best primary data point is CSALB's (more than 170 fraud requests in 2026, losses up to EUR 20,000 per case, nearly all refused by banks). BNR, ARB and DIICOT aggregate statistics were not found.

### Cited Findings
- **Typologies documented by CSALB (Sept 2026; cases with fictitious names but real counties):**
  1. Malware / remote control via an app installed through WhatsApp; the criminals opened an online account and took a 29,000 lei loan, then drained 90,000 lei in successive transfers sized to avoid security limits.
  2. Vishing chain "bank employee → Police → BNR"; victim told to take a loan of about 100,000 lei, withdraw cash and feed a **crypto ATM** in 10,000 lei amounts.
  3. Identity theft with a personal loan in June 2026, funds moved to external accounts for laundering.
  4. A "friend" posing as a lawyer controlled the victim's phone for months and accessed three banks' apps; a credit card was issued and used for more than 15,000 lei.
  5. A 66,000 lei loan after the victim did a video identification for a Facebook "investment broker".
  6. Fake BNR and police officers led to a 110,000 lei loan.
  7. A 70,000 lei loan withdrawn in cash and deposited at a Bitcoin ATM in 14 transactions; the monthly instalment of 1,450 lei exceeds 30% of the victim's income.
  8. Fake site and "Hidroelectrica shares": 10,600 lei withdrawn plus a 67,000 lei loan over 60 months taken through the bank's app.

  [P] — [CSALB, 09.09.2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- **Scale relative to CSALB's total:** the more than 170 fraud requests in 2026 (as of 9 Sept) compare with 3,394 total CSALB requests in 9M 2026 (from the project's complaint notes, citing CSALB's 20 Oct 2026 press release) — [CSALB 09.09.2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf); [CSALB 20.10.2026 via Alba24](https://alba24.ro/wp-content/uploads/2026/10/Crestere-cereri_Comunicat-de-presa-CSALB_20.10.2026.pdf)
- **Phishing via a marketplace "buyer" link**, the pattern in CJEU C-70/25: a fake buyer sends a "confirm the sale" link to a spoofed bank page, and the victim enters online-banking credentials. The case is Polish, but the same OLX/courier pattern is common in Romania (BCR's form links to a dedicated "bcr.ro/OLX" fraud page) [P] — [CJEU 147/26](https://curia.europa.eu/site/upload/docs/application/pdf/2026-10/cp260147en.pdf); [BCR form, Jan 2026](https://cdn0.erstegroup.com/content/dam/ro/bcr/www_bcr_ro/informatii-utile/Refuz-la-Plata_ian2026.pdf). An OLX Romania partnership with the Romanian Police against platform fraud was reported (date unclear) [S, snippet] — [StartupCafe](https://startupcafe.ro/olx-colaborare-politie-capitala-combatere-fraude-online-htm-27705)
- **Card base and fraud rate:**
  - **28.63 million active cards** at end-2025, up 10.07% from June 2025 (BNR data) [S, snippet] — [Economedia](https://economedia.ro/bnr-numarul-de-carduri-a-ajuns-la-286-milioane-de-unitati-la-sfarsitul-lui-2025-in-crestere-cu-peste-10-comparativ-cu-iunie-2025.html)
  - A BNR payments-oversight official put Romania's fraud rate at about **0.007%**, "among the lowest in Europe" (Nov 2024) [S, snippet] — [Agerpres, 7 Nov 2024](https://agerpres.ro/economic/2024/11/07/micu-bnr-piata-bancara-din-romania-are-printre-cele-mai-mici-rate-de-frauda-din-europa--1383384)
- **Card-not-present (CNP) fraud mechanics:**
  - more than 85% of fraudulent remote card payments in a first half-year came from theft of card data (year not clear) [S, snippet] — [Capital.ro](https://www.capital.ro/informatie-de-ultima-ora-pentru-toti-cei-care-au-conturi-la-banca-vestea-cumplita-a-venit-chiar-de-la-bnr.html)
  - by value, 67% of fraud is card-not-present, 18% POS and 15% ATM (Revolut analysis, period not specified) [V/S, snippet] — [StartupCafe](https://startupcafe.ro/revolut-frauda-bani-card-romania-htm-11743)
- **Money mules and organised fraud:**
  - April 2025: a Romania-based group that recruited **hundreds of money mules** was dismantled with Eurojust support [S, snippet] — [Eurojust](https://www.eurojust.europa.eu/news/illegal-money-mule-network-grinds-halt-eurojust-support)
  - Survey (undated): 13% of Romanians would knowingly act as money mules and about 39% could become one unknowingly [S, snippet] — [Gândul](https://www.gandul.ro/financiar/carausi-de-bani-fara-voie-sau-in-cunostinta-de-cauza-cati-romani-ar-accepta-joburi-care-le-impun-deschiderea-sau-folosirea-contului-lor-bancar-si-efectuarea-de-transferuri-19472141)
  - DIICOT found more than 5,000 fake online ads that caused more than EUR 800,000 in losses (date unclear) [S, snippet] — [Gândul](https://www.gandul.ro/actualitate/diicot-a-descoperit-peste-5-000-de-anunturi-false-in-online-care-au-cauzat-un-prejudiciu-de-peste-800-000-de-euro-cum-erau-pacalite-victimele-20947211)
- **Scheme-rule link:** card purchases of crypto or NFTs where the cardholder took part but was deceived are **invalid as Visa 10.4 fraud disputes**. The crypto-ATM and fake-broker typologies above therefore cannot be recovered through fraud chargebacks [P] — [Visa Rules Apr 2026, Table 11-28](https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf)
- Already covered elsewhere, not repeated: DNSC 2025 incident statistics; H1 2026 vishing at 42% of reported frauds; EBA-ECB 2025 EEA fraud report — `reguli_kyc_aml_credit_plati_reclamatii.md` §3.

### Inferences
- **Typology → claim type → regime → route** (a basis for the agent's classifier and for synthetic test cases):

  | Typology | Claim type | Legal regime | Scheme route |
  |---|---|---|---|
  | Stolen card data, CNP purchase without SCA (e.g., non-EEA merchant, exemption) | Unauthorised | Refund by end of next business day; liability 0 / 30 EUR / full only with proven fraud or gross negligence | Visa 10.4 / MC 4837 chargeback possible |
  | Phishing link → credentials entered → 3DS approved by fraudster or victim | Unauthorised (bank may argue gross negligence) | Refund first (C-70/25), assess recovery later | Usually not chargeable (ECI 5 + CAVV) → bank loss |
  | Remote-access app or "friend" controls phone; transfers or loans | Disputed authorisation | Same refund duty if unauthorised; strong human review | Not a card chargeback (credit transfers or loans) |
  | Vishing → victim takes loan, withdraws cash, loads crypto ATM | Authorised scam | No PSD2 refund right today (PSR later) | None; support path (police, rescheduling, Biroul de Credit) |
  | Card purchase of crypto/NFT after deception | Authorised scam | As above | Visa 10.4 invalid |
  | Merchant non-delivery / not as described / subscription | Consumer dispute | Complaint deadlines | Visa 13.x / MC 4853 after merchant contact |
  | Double debit, wrong amount, ATM non-dispense | Processing error | Correction | Visa 12.x / 13.9; MC 4834 |

- Loans in victims' names are mostly **credit-fraud complaints, not card disputes**. They matter because they land in the same complaints/CSALB funnel. A triage agent should detect and route them (credit-fraud team, Biroul de Credit reporting hold request, police reference) instead of rejecting them as "not a card dispute".

### Gaps
- No BNR, ARB, DIICOT or Poliția Română aggregate statistics for 2024–2026 were found on: card-fraud value in lei; numbers of account-takeover, CNP, authorised-push-payment or loan-in-victim's-name cases; money-mule accounts. Leads seen only in search snippets and not attributed reliably:
  - a DIICOT case in Vâlcea (at least 20 suspects, about 110 accounts in RO/DE/ES/UK, Sept 2025–Apr 2026);
  - a June 2025 laundering network (44 searches in RO/MD, accounts opened with recruited identities);
  - "about 15,000 criminal files in H1 2026" for phone-scam-led fraud.
- The BNR 0.007% fraud rate is a 2024 statement seen in a snippet; its basis (cards only or all payments, value or volume) was not checked.
- No Raiffeisen-specific fraud-loss or chargeback figures are public.
