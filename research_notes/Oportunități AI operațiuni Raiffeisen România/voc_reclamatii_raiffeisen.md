# Voice of the Customer: complaints and negative reviews about Raiffeisen Bank România (2023–2026), mapped to internal back-office processes

_Research snapshot: 28 Oct 2026. Every fact carries an inline link. "(snippet)" means the claim was seen only in a search-engine summary, not on the opened page, so treat it as lower confidence. Root-cause mappings are hypotheses and appear only under "Inferences". Reviews are paraphrased, with no reviewer names. Items before 2023 are labelled with their year._

## 1. What do customers complain about (app stores, Trustpilot, Reddit/forums, press)? Themes, rough counts, ratings and volumes

### Takeaway
Raiffeisen Smart Mobile has high store ratings: 4.8 on iOS RO from about 152k ratings, and about 4.5 on Google Play from about 154k ratings, with about 9% one-star. So most of the anger is not about the app's UX. It shows up on Trustpilot (1.4/5, 93% one-star) and in press cases, and it is mostly about service and operations: slow or scripted customer service, blocked accounts and personal-data (KYC) updates that get stuck, fraud losses the bank does not recover, fees, branch-only closure steps, and periodic outages.

### Cited Findings
**Ratings and volumes**
- iOS (App Store RO): Raiffeisen Smart Mobile is rated 4.8/5 from about 152k ratings. The latest version (2.0.57) was released a few days before the snapshot. — [App Store RO](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)
- Google Play (third-party tracker, package `ro.raiffeisen.smartmobile`): average 4.54 from 153,650 ratings, 1M+ installs, last update 9 Oct 2026. It shows 13,703 one-star ratings (about 8.9%, roughly 13.7k unhappy raters). The star distribution looks partly imputed (0 two-star, and identical 3- and 4-star counts), so treat it as approximate. — [AndroidRank](https://www.androidrank.org/application/raiffeisen_smart_mobile/ro.raiffeisen.smartmobile)
- The bank's own claim (Jul 2025) is 4.8 on both Google Play and App Store. It also says about 1.9 million individual clients have a Smart Mobile contract, and more than 83% of them opened the app in May 2025. This conflicts with the 4.54 average above, probably because the two sources calculate the score differently. — [Revista Biz, 8 Jul 2025](https://www.revistabiz.ro/raiffeisen-bank-relanseaza-experienta-de-mobile-banking-cu-un-nou-design-al-aplicatiei/)
- Scale: more than 2.36 million clients and 264 branches. In Q1 2026, new individual clients were up 50% YoY and digital (remote) enrolments were up 56% YoY. — [Revista Biz, 5 May 2026](https://www.revistabiz.ro/crestere-cu-50-a-numarului-de-clienti-pentru-raiffeisen-bank-in-t1-2026/)

**Trustpilot (raiffeisen.ro profile, unclaimed, so the bank does not invite reviews)**
- TrustScore 1.4/5 ("Bad"). 95 reviews, 34 of them in the last 12 months. 93% are one-star, 4% five-star, 1% three-star and 2% two-star. — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)
- Rough theme counts among the dated complaints on the first page (one review can carry several themes) — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro):
  - **Customer service, about 4** (Apr 2025, Jul 2025, May 2026, Oct 2026): long phone waits, scripted answers, no escalation, expensive calls from abroad, and help only when calling from the registered phone number.
  - **Fees, about 4** (Feb 2023 – Sep 2026): a monthly fee per account and per currency, inactivity fees, unused campaign accounts that went negative (Sep 2026), and an all-in cost of about 21.5% on one international transfer (Mar 2026).
  - **Trouble updating personal or contact data, about 3** (Apr 2025, Jun 2026, Oct 2026).
  - **App or activation not working, or often unavailable, about 3** (Jul 2025, Oct 2025, Oct 2026). One reviewer said branches no longer have a cash desk, so everything depends on the app (Oct 2025).
  - **Blocked accounts, about 2.** One account was blocked after the client travelled, with no warning and no escalation (Jul 2025). Another stayed locked while a phone-number update took about 3 weeks.
  - **Fraud, about 2.** A phishing theft was reported quickly, but the bank gave no help recovering the money and no follow-up after about 10 days (May 2026). In another case, money was taken without the client knowing (Oct 2026).
  - **Account closure, about 2.** Closed accounts kept receiving notices and were reportedly blocked for missing details (May 2025). Closing an account required a branch visit (Sep 2026).
  - **Branch not following the bank's published rules, 1** (Sep 2025).
  - **Positive reviews, about 2** (Mar 2026: the app keeps improving; Oct 2025: praise for one employee).

**App Store review texts (small sample: 4 visible reviews, 2020–2024)** — [App Store RO](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)
- A long-standing client says their accounts were temporarily blocked for outdated data three years in a row, even though the bank said each time that the data had been updated. (KYC-refresh failure)
- A new client could only send and receive money for the first 3 days. Other functions stayed locked until a bank employee completed the enrolment. (manual onboarding step)
- The smart token has to be re-authorised after every app update. The token fails for 3-D Secure card payments. There is a password-field bug.
- A call-centre ticket took days to get a callback.
- A commercial review-analytics report (dated Dec 2025, now returning HTTP 410) said recent Smart Mobile updates got overwhelmingly negative App Store feedback for a confusing, less efficient UI. (snippet; weak, paid source) — [Kimola](https://kimola.com/reports/unlock-insights-raiffeisen-smart-mobile-app-customer-feedback-report-app-store-ro-156789)

**Product and channel changes that create complaint load**
- From 1 Feb 2022 Raiffeisen:
  - closed branch cash desks, so cash goes only through ATMs and MFMs, and only for cardholders;
  - stopped accepting most paper payment orders;
  - moved loan repayments, card closure and ending the relationship to online channels;
  - capped current accounts at 2 per currency;
  - announced a 0.25%/yr fee on large EUR balances from 1 Jun 2022.

  — [Economica.net, 1 Dec 2021](https://www.economica.net/raiffeisen-isi-schimba-strategia-interzice-operatiunile-cu-numerar-impune-taxe-pe-detinerile-de-valuta-si-obliga-persoanele-fizice-la-operatiuni-online_546416.html)
- The Smart Mobile redesign rolled out gradually from early July 2025, without a forced update. — [Revista Biz](https://www.revistabiz.ro/raiffeisen-bank-relanseaza-experienta-de-mobile-banking-cu-un-nou-design-al-aplicatiei/)
- The payment-authorisation flow changed in mid-April 2026, and the Smart Market loyalty app was merged into Smart Mobile from 15 May 2026. (snippet) — [Wall-Street.ro](https://www.wall-street.ro/articol/banking/raiffeisen-bank-schimba-aplicatia-smart-market-dispare-si-intra-in-smart-mobile.html)
- "Newer app": Raiffeisen Digital Bank AG, a separate digital bank, stopped operating in Romania on 11 Mar 2025. Its virtual cards were valid only until 6 Feb 2025, and transfers until 11 Mar 2025 at 17:00. — [Capital.ro, 5 Dec 2024](https://www.capital.ro/anunt-pentru-clientii-cu-cont-si-card-la-raifeissen-bank-trebuie-sa-vina-si-sa-semneze-personal.html)
- A Dec 2024 acquisition campaign paid 100 lei to anyone opening a current account and a savings account in the same month, valid until 30 Mar 2025. — [Capital.ro, 5 Dec 2024](https://www.capital.ro/anunt-pentru-clientii-cu-cont-si-card-la-raifeissen-bank-trebuie-sa-vina-si-sa-semneze-personal.html)

**Press-reported customer cases (older, labelled)**
- 2022: three Raiffeisen fraud victims.
  - One got about €9,300 (10 unauthorised transactions) back after the bank confirmed fraud.
  - One was refunded about 6 weeks later after a cumbersome procedure. The bank had refused to stop a transfer that was still pending.
  - One recovered the money only after about 3 months, and only after going to ANPC and the police, because written requests went unanswered.

  — [Capital.ro, 3 Aug 2022](https://www.capital.ro/au-ramas-fara-banii-de-pe-card-este-soc-total-in-sistemul-bancar-din-romania.html)
- 2020: during a disruption caused by an IT system update, clients reported:
  - ATM withdrawals debited but no cash dispensed;
  - one card payment charged 4 times;
  - 4 hours on the phone without reaching an operator.

  The bank said blocked amounts are released automatically, usually within about an hour. — [Capital.ro, 14 Jul 2020](https://www.capital.ro/probleme-pentru-clientii-raiffeisen-bank-ce-se-intampla-cu-banii-de-pe-carduri.html); [HotNews, 15 Jul 2020](https://hotnews.ro/?p=247641)

### Inferences
- High store ratings next to a very negative Trustpilot suggest the routine digital journey works. Dissatisfaction comes when something goes wrong and needs a human back-office action: unblocking, a data change, a dispute, or a closure. That is the hackathon's target zone.
- Closing cash desks and moving closure online in 2022 pushed exception handling to remote back-office and call-centre teams. That fits the complaints about call-centre bottlenecks and about branch visits still being required for closure, which contradicts the online-only policy.
- Fast client growth (+50% new individual clients and +56% digital enrolments in Q1 2026) grows today's onboarding and KYC review queues and tomorrow's KYC-refresh volume.
- The complaints about unused campaign accounts going negative may come from campaign-driven account opening, such as the Dec 2024 campaign, combined with fee rules. This is a hypothesis; no direct link is proven.

### Gaps
- Reddit (r/Romania, r/RoFinance) and Downdetector blocked the research tools for both search filtering and fetching, so I have no Reddit thread counts or Downdetector problem breakdowns.
- Google Play review texts could not be retrieved (the page was truncated), so the theme analysis relies on Trustpilot, the small App Store sample and the press.
- There is no systematic sample of hundreds of reviews. The counts above are rough, first-page counts.
- Forum anecdotes on avocatnet.ro about a Raiffeisen salary card blocked without a visible poprire, and a half-salary garnishment, appeared in search results but were not opened or verified.

## 2. Which complaints point to slow or manual internal processes, and which process most likely causes each one (pain point → process map)

### Takeaway
The Raiffeisen-specific evidence points most clearly to three processes:
1. complaint and case handling, including fraud-dispute investigation;
2. KYC refresh and data-change processing that leaves accounts restricted;
3. regulator-ordered remediation done contract by contract.

Garnishment (poprire) processing is probably the highest-volume process that runs on documents and fixed rules. Its customer harm (protected income frozen) is well documented market-wide, but there are fewer public complaints specific to Raiffeisen. Loan, inheritance and closure delays have only thin public evidence.

### Cited Findings
**A. KYC refresh / "actualizare date" / blocked accounts and cards**
- (Raiffeisen) Accounts were blocked for outdated data three years in a row despite repeated updates. — [App Store RO](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)
- (Raiffeisen) Trustpilot complaints:
  - an account stayed locked while a phone-number change took about 3 weeks;
  - an account was blocked after travel, with no warning and no escalation;
  - about 3 complaints describe trouble updating personal details.

  — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)
- (Market) Romanian banks tell clients that updating their data is mandatory under Legea 129/2019 (AML), and that without it they must stop the business relationship. (snippet) — [Alba24](https://alba24.ro/toti-clientii-bancilor-din-romania-trebuie-sa-si-actualizeze-datele-personale-ce-se-intampla-daca-refuzati-834289.html)
- (Market) CEC Bank blocked the accounts of clients who had not updated their data. (snippet; date not verified) — [Gândul](https://www.gandul.ro/actualitate/mai-multi-clienti-s-au-trezit-ca-au-blocate-conturile-la-cec-bank-ce-s-a-intamplat-20542308)
- (Market) A BNR first deputy governor told banks to stop blaming BNR when they ask clients to update their data. (snippet; date not verified) — [Bursa](https://www.bursa.ro/prim-viceguvernatorul-bnr-le-a-cerut-bancilor-sa-nu-mai-dea-vina-pe-bnr-cand-le-cer-clientilor-sa-si-actualizeze-datele-23791246)

**B. Popriri (garnishments) blocking protected income**
- (Market, Sep 2026) Salaried debtors often find the whole account frozen after a salary garnishment. The bank is not allowed to freeze the balance that existed before the poprire, or unseizable income. The practical fix is for the debtor to bring a salary certificate showing what kind of income comes into the account. (snippet) — [Puterea](https://www.puterea.ro/poprire-salariu-cont-blocat-deblocare/)
- (Market) When income is below the net minimum wage, only the part above half of it can be garnished. (snippet) — [Newsweek România](https://newsweek.ro/social/poate-fi-pusa-poprire-pe-pensie-sau-pe-salariu-minim-in-ce-conditii-executorul-poate-lua-banii)
- (Volume proxy, 2019) BRD, with about 2.3 million clients, said its garnishment volumes were:
  - 418,000 ANAF garnishment requests in the previous year;
  - about 700,000 in total;
  - plus about 250,000 a year from executori judecătorești.

  A dedicated 20-person unit handles them. ANAF sends popriri to all of a debtor's banks and accounts because it does not know the balances. — [Financial Intelligence, 9 Apr 2019](https://financialintelligence.ro/francois-bloch-directorul-general-al-brd-anul-trecut-am-primit-418-000-cereri-de-poprire-de-la-anaf/)
- (Market) How the electronic garnishment system has evolved:
  - ANAF has sent garnishment documents to banks electronically (e-Popriri) since Jun 2017.
  - Since 2021 the system has included features that limit the amounts blocked.
  - A 2023 draft ANAF order (planned to apply from 1 Oct 2023) would make every bank report through e-Popriri what it can pay each time money is credited, and stop transfers during suspensions.
  - As of 31 Mar 2023, only BCR had signed the voluntary framework convention.

  — [Profit.ro, 2 May 2023](https://www.profit.ro/taxe-si-consultanta/confirmare-bancile-vor-obligate-comunice-anaf-informatii-sumele-conturile-celor-popriti-astfel-incat-fie-evitate-platile-excesive-catre-fisc-pana-acum-bcr-acceptat-colaboreze-21112323)
- (Market) CSALB lists recurring complaint types that include refunds of garnished sums ("restituiri de sume poprite") and executare silită suspensions or stops. — [CSALB Q3 2025 report](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)

**C. Fraud refunds, disputes and chargebacks**
- (Raiffeisen, 2026) A phishing loss was reported quickly but got no recovery help and no follow-up after about 10 days (May 2026). In another case, money was taken without the client knowing (Oct 2026). — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)
- (Raiffeisen, 2022) Fraud refunds took between about 6 weeks and 3 months. One victim needed ANPC and the police to get one. — [Capital.ro](https://www.capital.ro/au-ramas-fara-banii-de-pe-card-este-soc-total-in-sistemul-bancar-din-romania.html)
- (Market, 2025) Banks accepted only 8 fraud cases into CSALB conciliation in 2025.
  - In those cases, banks refunded part of the loss on condition that the client repays it if the police recover the money.
  - In other cases, banks refused, arguing the client had authorised the transactions (for example with 3-D Secure).
  - Losses in the examples ranged from about 1,250 to 54,000 lei.
  - Ten fraud channels were described, including fake marketplace buyers, fake brokers using AnyDesk, WhatsApp impersonation, and enrolling the victim's card on a foreign device.

  — [Spotmedia/CSALB, 29 Oct 2025](https://spotmedia.ro/stiri/economie/10-metode-si-canale-bancare-de-frauda-ce-reclama-consumatorii-in-cererile-adresate-csalb-si-cate-cazuri-se-solutioneaza)
- (Market, 2026) CSALB had received more than 170 bank-fraud requests by 9 Sep 2026.
  - Most were loans taken out in victims' names after remote-access or vishing attacks, with losses up to €20,000.
  - Most banks refused conciliation, because police investigations were open and the criminals had used the holder's own credentials.
  - The BNR representative warned that video-identification recordings can be reused through deepfakes.

  — [CSALB press release, 9 Sep 2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- (Raiffeisen, regulator findings) In Nov 2022, ANSPDCP found:
  - credit-card and personal-loan applications processed without the applicant present, with clients' phone numbers replaced by an employee's number;
  - three credit facilities (Flexicredit, a Flexicredit refinancing, a Card de Cumpărături) opened without the client asking;
  - Smart Mobile data disclosed to other clients.

  — [Profit.ro, 18 Nov 2022](https://profit.ro/stiri/raiffeisen-bank-romania-a-fost-amendata-cu-28-000-euro-pentru-mai-multe-incidente-privind-securitatea-datelor-clientilor-20923023)
- (Raiffeisen, regulator findings) In Nov 2024, ANSPDCP found:
  - an employee had used a client's documents to take out a loan and withdraw money;
  - another employee allegedly altered client data for gain between 2015 and 2023.

  — [Puterea, 20 Nov 2024](https://www.puterea.ro/?p=409417)

**D. Complaint handling, call-centre waits, response times**
- (Raiffeisen) Long phone waits, scripted answers and no escalation (about 4 dated complaints, 2025–2026). — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)
- (Raiffeisen) A call-centre ticket took days to get a callback. — [App Store RO](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)
- (Raiffeisen, 2020) A client spent 4 hours on hold during an incident. — [Capital.ro](https://www.capital.ro/probleme-pentru-clientii-raiffeisen-bank-ce-se-intampla-cu-banii-de-pe-carduri.html)
- (Raiffeisen, regulator finding, 2022) ANSPDCP found that documents with personal data were e-mailed to the wrong recipients. In one case, the bank answered one client's complaint with another client's documents attached, because similar complaints were being answered one after another. — [Profit.ro, 18 Nov 2022](https://profit.ro/stiri/raiffeisen-bank-romania-a-fost-amendata-cu-28-000-euro-pentru-mai-multe-incidente-privind-securitatea-datelor-clientilor-20923023)
- (Legal frame, aggregator source; verify) Payment-service complaints must be answered within 15 business days, or up to 35 in exceptional cases, under Legea 209/2019. Other petitions have about 30 days. — [InfoContact](https://www.infocontact.ro/contact-raiffeisen-bank/)
- (Market, how disputes arrive) In 9M 2025, 541 of the 1,620 conforming bank complaints filed with CSALB (33%) arrived by post. 730 came through the web app, 319 by e-mail and 30 in person. — [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)

**E. Onboarding and document checks**
- (Raiffeisen) A new client had limited functions for 3 days until an employee completed the enrolment. — [App Store RO](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)
- (Raiffeisen) Digital enrolments grew 56% YoY in Q1 2026. — [Revista Biz](https://www.revistabiz.ro/crestere-cu-50-a-numarului-de-clienti-pentru-raiffeisen-bank-in-t1-2026/)
- (Raiffeisen) Fully digital enrolments in 2024 grew 440% over 2023. (snippet) — [Bankingnews.ro](https://bankingnews.ro/?p=75576)

**F. Account closure, data sync and fees**
- (Raiffeisen) Closure required a branch visit (Sep 2026). Notices kept coming after closure, and the account was blocked for missing details (May 2025). Campaign accounts went negative and inactivity fees were charged. — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)
- (Raiffeisen) Since 2022, the stated policy is that ending the relationship and closing cards are done online. — [Economica.net](https://www.economica.net/raiffeisen-isi-schimba-strategia-interzice-operatiunile-cu-numerar-impune-taxe-pe-detinerile-de-valuta-si-obliga-persoanele-fizice-la-operatiuni-online_546416.html)

**G. Regulator-ordered remediation (mass recalculations and refunds)**
- In 2021, ANPC fined Raiffeisen 100,000 lei for not refunding about 14,000 clients with restructured loans more than 1.5 years after the final ÎCCJ decision. ANPC also proposed suspending the bank's activity. — [Profit.ro](https://profit.ro/povesti-cu-profit/financiar/banci/ultima-ora-anpc-amendat-raiffeisen-bank-100-000-lei-pus-aplicare-decizie-instantei-circa-14-000-clienti-ar-afectati-practica-comerciala-declarata-incorecta-multe-instante-reactia-bancii-20382977)
- In Oct 2021 the bank said it had decided to automate the recalculation of about 14,000 additional acts ("softul este gata"):
  - each contract has its own particularities;
  - a representative sample was analysed first;
  - only positive differences are refunded;
  - the bank framed the refunds as voluntary.

  — [Profit.ro, 11 Oct 2021](https://profit.ro/povesti-cu-profit/financiar/banci/raiffeisen-bank-va-rambursa-in-aceasta-luna-catre-clienti-sumele-incasate-in-plus-din-restructurarea-creditelor-20422871)
- Pre-2009 loans interest-clause case:
  - The ÎCCJ upheld ANPC's order in spring 2022, and its written reasoning came out at the end of Oct 2022.
  - By 9 Dec 2022, Raiffeisen had paid about €13.4m (including €2.47m legal interest) to about 5,530 clients with active accounts.
  - 3,050 former clients without active accounts were still owed €7.2m and had to give a bank account in writing.
  - ANPC's total was €21.7m, against a bank provision of €18m.

  — [Profit.ro, 9 Dec 2022](https://profit.ro/povesti-cu-profit/financiar/banci/raifffeisen-bank-a-platit-clientilor-13-4-milioane-de-euro-pentru-dobanzile-incasate-nelegal-anpc-20945568)

**H. Loans, restructuring and refinancing**
- (Market) CSALB requests in H1 2026 hit a record 2,060, up 40% YoY. About 90% concern credit contracts:
  - refunds;
  - balance reduction;
  - lower instalments or cancelled arrears;
  - rescheduling, refinancing or renegotiation;
  - switching from ROBOR to IRCC.

  — [Spotmedia/CSALB, 14 Jul 2026](https://spotmedia.ro/stiri/economie/consumatorii-au-trimis-cu-40-mai-multe-cereri-de-negociere-cu-bancile-si-ifn-urile-in-cadrul-csalb-ce-au-solicitat)
- (Competitor signal) BCR reviewers describe refinancing help that was delayed and inaccurate (Feb 2025), applications that dragged on (Jul 2023), and branch appointments needed for simple tasks. — [Trustpilot BCR](https://www.trustpilot.com/review/bcr.ro)
- (Raiffeisen, volume driver) Net loans were up 15% YoY in Q1 2026, individual loans up 12% and unsecured loans up 17%. — [Revista Biz](https://www.revistabiz.ro/crestere-cu-50-a-numarului-de-clienti-pentru-raiffeisen-bank-in-t1-2026/)

**I. Inheritance (moșteniri)**
- (Market) Banks release a deceased client's funds only against a notarial certificat de moștenitor or a final court decision. (snippet) — [Capital.ro](https://www.capital.ro/obligatie-la-banca-nu-se-poate-intra-in-posesia-banilor-din-cont-documentul-care-trebuie-depus-neaparat.html)
- (Raiffeisen, unverified) A Trustpilot review, seen only through a search summary and not on the page, alleged that the bank kept collecting from a deceased borrower's account for about 8 months even though the loan was insured. — [Trustpilot DK](https://dk.trustpilot.com/review/raiffeisen.ro)

### Inferences
**Pain point → most likely internal process (hypotheses)**

| # | Customer pain point | Evidence (Raiffeisen / market) | Most likely internal back-office process | Why it is slow or error-prone (hypothesis) | AI-agent angle (documents + data + rules) |
|---|---|---|---|---|---|
| 1 | Account or card restricted for outdated data; data changes take weeks; blocks with no warning | Medium / High | Periodic KYC refresh (CDD under Legea 129/2019) plus back-office processing of data-change requests; AML/fraud monitoring rules that trigger blocks (e.g., after travel) | ID, address and income documents and FATCA/CRS self-certifications are checked by hand. Updates captured in the app or branch may not sync to the core system, so batch jobs flag the client again. Unblocking needs a manual review queue. | KYC-refresh agent: read ID/document images, compare with core data, list the differences, auto-clear low-risk cases, write a plain-language reason for the block and the exact documents needed |
| 2 | Whole account frozen by a poprire, including salary or child allowance; slow release after the debt is paid; double collection across banks | Low (no Raiffeisen-specific complaints found) / High (scale, legal rules, ANAF reform) | Poprire handling: taking in ANAF e-Popriri and executor orders (often PDF or paper), matching them to accounts, working out sume insesizabile per income type, paying out, and lifting the block (ridicare) | Very high volume (BRD: about 700k a year). Legal limits differ by income type. Incoming credits must be classified by source. ANAF sends blanket popriri to every bank. | Poprire agent: parse the order, match accounts, classify incoming credits (salary, pension, alocație), compute the protected amount, draft the reply to the executor, track releases and over-collection refunds |
| 3 | Fraud victims: slow or no refunds, no follow-up; loans taken out in victims' names | Medium / High (CSALB: more than 170 requests in 2026, banks mostly refuse) | Fraud dispute and chargeback investigation; PSD2 liability assessment ("gross negligence" vs. authorised transaction); handling fraudulent credit cases (suspending instalments, Biroul de Credit reporting) | Evidence sits in separate systems (3DS logs, device data, call records). Police coordination. Letters are written by hand. Deadlines are 15/35 business days. | Dispute-triage agent: build the evidence pack, apply PSD2 and card-scheme rules, recommend a decision, draft the letter, track deadlines, flag cases for suspending Biroul de Credit reporting |
| 4 | Long call-centre waits, scripted answers, callbacks after days, no escalation | Medium-High / Medium | Complaint intake, classification, routing and reply drafting; callback queue | Manual triage. Agents lack a single view of the client. Replies to similar complaints are assembled in sequence, which led to one client's documents being sent to another (ANSPDCP 2022). | Complaint copilot: classify and route, gather the facts, draft the reply, check recipient and redaction before sending, monitor SLAs |
| 5 | New digital client limited for days until an employee completes enrolment | Low-Medium / n/a | Back-office validation of digital onboarding (ID verification, sanctions/PEP screening hits) | Queue grows with +56% digital enrolments | Onboarding-review agent: pre-check documents, explain and resolve likely false-positive screening hits |
| 6 | Closure needs a branch visit; notices and blocks after closure; campaign accounts go negative | Low-Medium / n/a | Account-closure workflow (checking cards, debts, popriri, products); dormant and campaign-account lifecycle; fee rules | Closure prerequisites are checked by hand; data does not sync between systems | Closure-readiness agent; agent that sweeps dormant campaign accounts and recommends fee reversals |
| 7 | Court- or ANPC-ordered refunds delayed (2021: more than 1.5 years; 2022: 3,050 former clients unpaid) | High (official) / n/a | Regulator-ordered remediation: recalculating contract by contract and paying former clients | Each contract is different; legacy loan data; the bank needs a written IBAN from former clients | Remediation agent: extract clauses, recalculate, generate letters, collect IBANs |
| 8 | Hardship, restructuring and refinancing requests (record CSALB volume in 2026) | None / High | Handling restructuring and rescheduling requests (affordability documents, policy rules) | Each case is underwritten by hand | Hardship-request agent: check document completeness and propose rule-based options |
| 9 | Deceased client: debits continue, slow estate settlement | Low (1 unverified) / Medium | Processing death notifications and succession files; triggering the bancassurance claim | Reading the certificat de moștenitor and coordinating with the insurer are manual | Succession-file agent: parse the certificate, compute heirs' shares, trigger the insurance claim |
| 10 | Staff data mishandling (misdirected documents, unauthorised loans, data changes) | High (ANSPDCP 2019, 2022, 2024) / n/a | Manual document handling over e-mail; weak maker-checker controls on master-data changes | Free-form e-mail; no automatic checks | Outbound-document check agent; monitor for unusual data changes |

**Shortlist for the hackathon (inference)**
- **Best fit on public, Raiffeisen-specific proof:** #4 plus #3, a complaint and fraud-dispute triage agent. It is backed by Trustpilot (2025–2026), the App Store, the 2022 press cases, the 2022 ANSPDCP finding of complaint replies sent with the wrong client's documents, and CSALB's rising fraud volumes in 2025–2026.
- **Best fit on volume and fixed rules:** #2, a poprire-processing agent. It is document-heavy, governed by explicit legal limits and ANAF e-Popriri data, and causes high harm (frozen protected income). The weakness is that public complaints naming Raiffeisen are thin, so any pitch would rely on a BRD volume proxy and market evidence.
- **Strong secondary:** #1, KYC refresh and blocked-account resolution. It has direct Raiffeisen reviews, a clear legal basis (Legea 129/2019), and a growing client base (+50% new clients).
- Regulator findings against Raiffeisen cluster around two things: slow contract-level remediation, and staff handling documents and data by hand. Both are exactly "repetitive internal work involving documents, data and predefined rules".

### Gaps
- Raiffeisen does not publish internal volumes or backlogs (popriri per year, KYC refresh cases, disputes, complaint counts and resolution times). No complaint statistics were found in its annual or sustainability reports.
- No public Raiffeisen-specific complaints were found about mortgage, refinancing or Prima/Noua Casă processing delays.
- Inheritance evidence is a single unverified review.
- Whether the 2023 ANAF e-Popriri draft order was adopted is not verified. A CES opinion dated 30 Dec 2025 on poprire changes surfaced in search results but was not read.

## 3. What official sources say (CSALB, ANPC, BNR, ANSPDCP, courts, Consiliul Concurenței), plus market-wide complaint statistics

### Takeaway
Official actions against Raiffeisen fall into three groups:
- lending-clause litigation with ANPC (2017–2024) and slow regulator-ordered remediation;
- three GDPR fines tied to staff data handling (2019, 2022, 2024);
- the record ROBOR competition fine of 7 Jun 2026: 442.49m lei for Raiffeisen, which the bank is contesting.

No BNR consumer-protection sanction was found. CSALB publishes only market-wide figures, not per bank. They show record complaint volumes in 2026, a fast-growing fraud-loan problem, and banks rarely accepting fraud cases for conciliation.

### Cited Findings
**CSALB (alternative dispute resolution for banking): market-wide statistics**

| Period | Total requests | To banks | To IFN | Outcome / notes |
|---|---|---|---|---|
| 2023 | 2,932 | 1,885 | 1,047 | — |
| 2024 | 3,568 | 2,644 | 924 | 1,078 dossiers; average resolution 15 days |
| 2025 | 2,866 | 2,210 | 656 | 909 bank dossiers; 96% settled; average 13 days; €3.22m in benefits; banks' unjustified rejection rate 8%; 336 settled directly (286 by banks) |

— 2023–2025 figures: [Revista Biz, 27 Jan 2026](https://www.revistabiz.ro/96-dintre-negocierile-din-2025-s-au-incheiat-cu-impacarea-partilor-intr-un-timp-mediu-de-doar-13-zile/); 2024 resolution time also in [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)

- Requests to delete Biroul de Credit entries fell from 1,234 (2023) to 935 (2024) to 653 (2025). These cannot be negotiated through CSALB. — [Revista Biz](https://www.revistabiz.ro/96-dintre-negocierile-din-2025-s-au-incheiat-cu-impacarea-partilor-intr-un-timp-mediu-de-doar-13-zile/)
- 9M 2025, requests against banks: 1,620 conforming, 740 non-conforming and 530 requests for information. The 1,620 conforming requests broke down as follows. — [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)
  - 684 became dossiers;
  - 199 were still at the document filter;
  - 176 were settled directly by the bank after the client went to CSALB;
  - 578 were closed ("clasate"), mainly because the bank refused the ADR procedure;
  - 124 were merged with other requests.
- 9M 2025, IFNs: 445 of 501 requests were closed because the lenders refused. — [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)
- CSALB groups the operational complaint types as follows. — [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf)
  - **Card and payment operations:** ATM malfunctions and refunds; transfers and transaction fees; refunds after processing errors; recovering money sent by mistake through internet banking; how credit-card amounts are calculated; card name changes or cancellation; FX rates and interest on cards used abroad; interbank transfers.
  - **Other activities:** executare silită suspensions or stops; issuing documents (repayment schedules, statements); refunds of garnished sums; mortgage release (radiere ipotecă); fraud through banking channels.
- H1 2026, a record half-year. — [Spotmedia/CSALB, 14 Jul 2026](https://spotmedia.ro/stiri/economie/consumatorii-au-trimis-cu-40-mai-multe-cereri-de-negociere-cu-bancile-si-ifn-urile-in-cadrul-csalb-ce-au-solicitat)
  - 2,060 requests (+40% vs. 1,464), of which 1,458 against banks and 602 against IFNs.
  - 84% were negotiable.
  - Banks turned 395 of their 1,240 negotiable requests into dossiers (about 32%), and IFNs turned none of 480 into dossiers.
  - 332 settlements (91%), about €1m in benefits (about €2,700 each), and 166 direct settlements by banks (vs. 91 in H1 2025).
  - About 90% of requests concerned credit contracts.
- Fraud:
  - In 2025, banks accepted 8 fraud cases for conciliation. — [Spotmedia/CSALB](https://spotmedia.ro/stiri/economie/10-metode-si-canale-bancare-de-frauda-ce-reclama-consumatorii-in-cererile-adresate-csalb-si-cate-cazuri-se-solutioneaza)
  - Between 1 Jan and 9 Sep 2026 there were more than 170 fraud requests, mostly fraudulent loans, and the cases CSALB highlighted were all rejected or closed by the banks. — [CSALB, 9 Sep 2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)
- None of the CSALB reports reviewed give figures per bank. — [CSALB Q3 2025](https://csalb.ro/wp-content/uploads/2025/10/Raport-CSALB_T3-2025_RO_29.10.2025.pdf); [Revista Biz](https://www.revistabiz.ro/96-dintre-negocierile-din-2025-s-au-incheiat-cu-impacarea-partilor-intr-un-timp-mediu-de-doar-13-zile/)

**ANPC**
- 2021: a 100,000 lei fine for not carrying out the final ÎCCJ decision on about 14,000 restructured-loan clients, plus a proposal to suspend the bank's activity (more than €10m at stake). — [Profit.ro](https://profit.ro/povesti-cu-profit/financiar/banci/ultima-ora-anpc-amendat-raiffeisen-bank-100-000-lei-pus-aplicare-decizie-instantei-circa-14-000-clienti-ar-afectati-practica-comerciala-declarata-incorecta-multe-instante-reactia-bancii-20382977)
- 2022: after the ÎCCJ upheld ANPC's order on interest clauses in pre-2009 loans, the bank had refunded €13.4m of an ANPC-calculated €21.7m by Dec 2022. — [Profit.ro, 9 Dec 2022](https://profit.ro/povesti-cu-profit/financiar/banci/raifffeisen-bank-a-platit-clientilor-13-4-milioane-de-euro-pentru-dobanzile-incasate-nelegal-anpc-20945568)
- 15 May 2023: ANPC sanctioned 19 banks, including Raiffeisen, over how instalments were calculated on equal-instalment (annuity) loans after BNR raised the key rate.
  - ANPC also ordered new repayment schedules.
  - On 21 May 2024, Judecătoria Sectorului 1 upheld Raiffeisen's challenge at first instance, with ARB intervening on the bank's side, and ordered ANPC to pay about 23,000 lei in court costs.
  - The ruling could be appealed at Tribunalul București.

  — [Profit.ro, 21 May 2024](https://profit.ro/povesti-cu-profit/financiar/banci/raiffeisen-bank-castiga-pe-fond-procesul-cu-anpc-privind-ratele-la-credite-21598838)
- The 2023 fines came in two waves, 11 banks first and then 8 more banks fined 400,000 lei together. The per-bank amounts were not published in the sources found. (snippet) — [Digi24](https://www.digi24.ro/stiri/actualitate/anpc-a-amendat-inca-opt-banci-cu-400-000-de-lei-pentru-modul-de-calcul-al-ratelor-la-credite-2362315)

**Courts and abusive clauses**
- The landmark "comision de risc" case (ÎCCJ, 2014) involved Volksbank, not Raiffeisen. (snippet) — [Economica.net](https://www.economica.net/?p=91964)
- No Raiffeisen-specific ÎCCJ ruling on "comision de risc" was found. Raiffeisen's equivalent exposure is the interest-clause and restructured-loan litigation above.
- Older, 2018: the Sibiu Tribunal ordered Raiffeisen to refund about CHF 6,000 to one client in an abusive-clause case. (snippet) — [Bursa](https://www.bursa.ro/intr-un-proces-pe-clauze-abuzive-raiffeisen-bank-obligata-de-instanta-sa-returneze-aproape-6000-chf-unui-client-04031435)

**ANSPDCP (GDPR)**
- 2019 (older): a €150,000 fine. Two employees ran pre-scoring simulations on personal data passed on by staff of the broker Vreau Credit, which breached Art. 32(4) together with Art. 32(1)–(2) GDPR. Vreau Credit was fined €20,000 separately. The WhatsApp channel comes from the brief and was not re-verified. — [EDPB national news](https://edpb.europa.eu/news/national-news/2019/romanian-supervisory-authority-fines-raiffeisen-bank-sa-and-vreau-credit_it)
- A final court decision later cut that fine tenfold, to €15,000. — [Profit.ro](https://www.profit.ro/povesti-cu-profit/financiar/banci/raiffeisen-bank-obtine-in-instanta-in-urma-unei-decizii-definitive-reducerea-de-10-ori-a-unei-amenzi-de-150-000-euro-pe-subiectul-gdpr-20721151)
- Nov 2022 (investigation completed Sep 2022): 138,572 lei (about €28,000) in three fines (98,980 + 14,847 + 24,745 lei) under Art. 32 and Art. 25(1) GDPR, plus 2 warnings. — [Profit.ro, 18 Nov 2022](https://profit.ro/stiri/raiffeisen-bank-romania-a-fost-amendata-cu-28-000-euro-pentru-mai-multe-incidente-privind-securitatea-datelor-clientilor-20923023)
  - credit-bureau and ANAF queries made without signed documentation, affecting at least 169 people;
  - loans approved through an intermediary without the client asking;
  - e-mails sent to the wrong recipients, including a complaint reply that attached another client's documents;
  - suspected internal fraud;
  - Smart Mobile data exposed to other clients.
- Nov 2024 (investigation Oct 2024): 99,466 lei (about €20,000).
  - An employee used a client's documents to take out a loan and make withdrawals.
  - Employees shared a client's transactions with a former employee over social messaging.
  - Accounts and products were opened without consent, with alleged illegal operations between 2015 and 2023.
  - Ordered measures: periodic testing of processing operations and staff training every 6 months.
  - Single source.

  — [Puterea, 20 Nov 2024](https://www.puterea.ro/?p=409417)

**Consiliul Concurenței**
- On 7 Jun 2026 the Consiliul Concurenței fined 10 banks a total of 3.73bn lei. It found they had coordinated by exchanging confidential and strategic information, mainly on price, about ROBOR fixing quotes, in breach of Legea 21/1996 and the TFEU.
  - Raiffeisen's fine is 442.49m lei.
  - On 8 Jun 2026 the bank said it "categorically" rejects the findings and will contest the decision in court.

  — [BVB filing RBRO, 8 Jun 2026](https://bvb.ro/infocont/infocont26/RBRO27_20260608164353_Comunicat-decizie-Consiliul-Concurentei-RO.pdf)
- Older, around 2010 per the press: a fine of 14,006,712 lei for providing inaccurate information during a sector investigation. (snippet) — [Bursa](https://www.bursa.ro/consiliul-concurentei-a-sanctionat-raiffeisen-bank-sa-cu-14006712-lei-8112284)

**BNR**
- No BNR sanction against Raiffeisen was found, and no BNR statistics on consumer petitions per bank. The only BNR-related consumer item found is that BNR's representative in CSALB's Colegiul de Coordonare warned about fraudulent loans in Sep 2026. — [CSALB, 9 Sep 2026](https://csalb.ro/wp-content/uploads/2026/09/Credite-fraudate_Comunicat-de-presa-CSALB_09.09.2026.pdf)

### Inferences
- The regulator record shows operational weaknesses rather than one-off disputes:
  - remediation was slow because recalculations were contract-specific and payouts to former clients needed written IBANs;
  - staff handled documents and data loosely: misdirected e-mails, an unsupervised employee changing data for 8 years, and loans opened without consent.

  Both are processes an AI agent with rules and controls could take on.
- The record CSALB volumes in 2026, mostly credit hardship, and the fraud-loan wave suggest back-office complaint, restructuring and fraud workloads at all Romanian banks were rising in 2026.
- Banks turned about 32% of negotiable requests into CSALB dossiers in H1 2026 and settled 166 directly. This suggests a large share of complaints are still decided bilaterally inside the bank's own complaint-handling process.
- The ROBOR fine is not an operations issue. It may raise pressure on costs and reputation, which supports an efficiency pitch.

### Gaps
- No CSALB, ANPC or BNR complaint counts per bank for 2023–2026 were found, so Raiffeisen's share of market complaints is unknown.
- No ANSPDCP decisions from 2025–2026 against Raiffeisen were found.
- Whether the 2024 ANPC annuity ruling was confirmed on appeal is not verified.
- The individual ANPC fine paid by Raiffeisen in 2023 is unknown.
- Press reports mention a delivery of the Consiliul Concurenței reasoned decision (28 Sep 2026) and a later dispute with the authority's president about blocking the fine. (snippet; not verified)
- A Revista Biz piece dated 20 Oct 2026 reportedly gives Q1–Q3 2026 CSALB figures (572 bank-accepted negotiations, 90% agreement). Not verified, because the exact URL was not confirmed.

## 4. Outages and incidents of Raiffeisen digital channels (2023–2026)

### Takeaway
Major Raiffeisen digital incidents in the press:
- **May 2023:** all online channels down for several hours;
- **29–30 Oct 2023:** about 16–18 hours of disruption to the app, the website, biometric online payments, instant payments and MFM deposits;
- **12 Oct 2024:** card payments failing nationwide.

Earlier ones, labelled: Apr 2022 (cards, ATMs, the new Smart Mobile) and Jul 2020 (ATMs, debits without cash). No major outage of Raiffeisen Romania was found in the press for 2025–2026, though Trustpilot users still report the app being unavailable.

### Cited Findings
- **3 May 2023:** an "incident" took down:
  - Smart Mobile, Raiffeisen Online, SmartToken, Smart Business and Raiffeisen Online IMM;
  - OpenBanking (AISP/PISP/CISP);
  - Google Pay and Apple Pay enrolment, and Smart Market enrolment.

  The maintenance window was extended from 12:00–14:00 to 17:00. ATMs, POS and cards kept working, and clients were sent to branches for urgent operations. No cause was given. — [Adevărul, 3 May 2023](https://adevarul.ro/economie/probleme-pentru-raiffeisen-bank-in-romania-nicio-2263639.html)
- **29–30 Oct 2023 (Saturday):** failed services were:
  - Smart Mobile and Raiffeisen Online for individuals, SmartToken, Smart Business and Smart Market;
  - online payments with biometric approval;
  - instant payments;
  - cash deposits at MFMs;
  - the raiffeisen.ro website.

  POS and ATM card use worked, and so did the call centre and the virtual assistant. Everything was restored at 01:30 on 30 Oct, about 16–18 hours later. The bank cited only a "technical problem". — [Economedia, 30 Oct 2023](https://economedia.ro/clientii-reclama-probleme-cu-serviciile-raiffeisen-bank-sambata-banca-echipa-tehnica-lucreaza-pentru-remedierea-situatiei.html)
- **12 Oct 2024 (Saturday):** Raiffeisen cards failed at POS terminals across the country ("failed transaction"). The app showed a technical-problem message. No cause or duration was stated. — [Capital.ro, 12 Oct 2024](https://www.capital.ro/cardurile-raiffeisen-bank-nu-mai-functioneaza-anuntul-bancii-pentru-clienti.html)
- **14 Apr 2022 (older):** cards and ATMs were down until about 12:00. The bank said the incident hit the "new Smart Mobile" and card transactions, and business online banking still had problems after noon. The article said the bank's more than 2 million clients, including over 100,000 companies, were affected. — [Alba24, 14 Apr 2022](https://alba24.ro/clientii-raiffeisen-bank-nu-isi-pot-accesa-banii-din-conturi-sistemul-online-este-nefunctional-explicatiile-bancii-912365.html)
- **13–15 Jul 2020 (older):** intermittent ATM and debit-card problems after an IT system update. Amounts blocked by unfinished transactions were later released, and clients were told to call *2000 or visit a branch. — [HotNews, 15 Jul 2020](https://hotnews.ro/?p=247641); [Capital.ro, 14 Jul 2020](https://www.capital.ro/probleme-pentru-clientii-raiffeisen-bank-ce-se-intampla-cu-banii-de-pe-carduri.html)
- **2025–2026:** no press report of a major Raiffeisen Romania outage was found. Trustpilot reviews say the app was often unavailable (Jul 2025) and describe activation or app failures (Oct 2025, Oct 2026). — [Trustpilot](https://www.trustpilot.com/review/raiffeisen.ro)

### Inferences
- Outages are an IT and infrastructure problem, not a back-office one, so they are a poor direct target for an "internal operations" agent.
- Outages do create back-office spikes: blocked or duplicate debits, card-dispute tickets, refunds and call-centre surges (as in 2020). A post-incident reconciliation agent is a niche but measurable use case: find affected transactions, auto-reverse within the rules, and notify clients.

### Gaps
- Downdetector was not reachable, so there is no breakdown of the problems users reported or of report peaks.
- Press reports give no official root causes or client counts for 2023–2024.
- A Feb 2023 incident affecting online card payments, and an older power-grid outage in Bucharest, surfaced in search results but were not verified.

## 5. How Raiffeisen compares with Banca Transilvania, BCR, ING, BRD and CEC on complaints and app ratings

### Takeaway
On app-store ratings the six banks are effectively tied (iOS RO 4.7–4.9), so ratings do not tell them apart. On Trustpilot, a small, self-selected sample, Raiffeisen has the lowest score of the banks checked: 1.4, against BT 1.8, BCR 2.3 and ING 4.1. ING's profile is actively managed by the bank, so it is not comparable. Competitors' complaints show the same operational themes (blocked payments during verification, call-centre waits, paper-heavy processes), so these pains are industry-wide. No official complaint statistics per bank were found.

### Cited Findings

| Bank | Main app (iOS RO) | iOS rating | iOS ratings | Trustpilot score | Trustpilot reviews | 1-star share |
|---|---|---|---|---|---|---|
| Raiffeisen | Smart Mobile | 4.8 | about 152k ([link](https://apps.apple.com/ro/app/raiffeisen-smart-mobile/id1255136212)) | 1.4 | 95 | 93% ([link](https://www.trustpilot.com/review/raiffeisen.ro)) |
| Banca Transilvania | BT Pay | 4.8 | about 283k ([link](https://apps.apple.com/ro/app/bt-pay/id1326751685)) | 1.8 | 235 | 84% ([link](https://www.trustpilot.com/review/bancatransilvania.ro)) |
| BCR | George România | 4.8 | about 191k ([link](https://apps.apple.com/ro/app/george-rom%C3%A2nia/id1401166803)) | 2.3 | 83 | 86% ([link](https://www.trustpilot.com/review/bcr.ro)) |
| ING | Home'Bank | 4.9 | about 129k ([link](https://apps.apple.com/ro/app/ing-homebank/id458609168)) | 4.1 | 178 | 40% ([link](https://www.trustpilot.com/review/ing.ro)) |
| BRD | YOU BRD | 4.8 | about 120k ([link](https://apps.apple.com/ro/app/you-brd/id1484062157)) | not collected | — | — |
| CEC | CEC Bank Mobile Banking | 4.7 | about 8.2k ([link](https://apps.apple.com/ro/app/cec-app/id1071729654)) | not collected | — | — |

- The Raiffeisen and BT Trustpilot profiles are unclaimed. ING replies to reviews, so its profile is managed and likely invites reviews, which inflates its score. — [Trustpilot Raiffeisen](https://www.trustpilot.com/review/raiffeisen.ro); [Trustpilot BT](https://www.trustpilot.com/review/bancatransilvania.ro); [Trustpilot ING](https://www.trustpilot.com/review/ing.ro)
- BT complaint themes:
  - unresponsive call centre (Oct 2025 – Aug 2026);
  - payments held and accounts restricted, including loss of online access to a business account for about a month (Dec 2025 – Sep 2026);
  - slow merchant refunds and disputes (Oct 2025);
  - app login and PIN/SMS failures.

  A few reviewers praised BT's fraud team for recovering funds. — [Trustpilot BT](https://www.trustpilot.com/review/bancatransilvania.ro)
- BCR complaint themes:
  - funds frozen during verification (Nov 2023, Feb 2026);
  - cards or online banking cut off without notice (Apr and Aug 2024);
  - long phone waits and unanswered e-mails;
  - refinancing delays (Jul 2023, Feb 2025);
  - branch appointments and paper for simple tasks (Dec 2023 – Aug 2024);
  - a George FX transfer in the wrong direction that the bank refused to reverse (Feb 2025).

  — [Trustpilot BCR](https://www.trustpilot.com/review/bcr.ro)
- ING complaint themes:
  - payments repeatedly blocked even after the client approved them, with generic chat replies (Oct 2026);
  - yearly forced password changes for business users;
  - ING's own replies point clients to document requests, i.e. KYC.

  — [Trustpilot ING](https://www.trustpilot.com/review/ing.ro)
- App Store complaint themes for competitors (small visible samples):
  - **George:** card payments take hours or days to appear; statements lack an address, so they cannot serve as proof of address. — [App Store](https://apps.apple.com/ro/app/george-rom%C3%A2nia/id1401166803)
  - **BT Pay:** identity verification failures after an update (2022); fees on transfers between one's own accounts (2024). — [App Store](https://apps.apple.com/ro/app/bt-pay/id1326751685)

### Inferences
- With every bank at 4.7–4.9 stars, app ratings cannot "prove" pain. The distinguishing evidence is service and operations complaints, where Raiffeisen's public signal is among the worst of the banks checked, though the sample is small.
- Blocks during verification or AML review appear at BCR, BT and ING as well. A KYC and blocked-account resolution agent would therefore address an industry-wide problem, which strengthens a hackathon pitch on reusability.

### Gaps
- Trustpilot scores for BRD and CEC, and Google Play ratings for all competitors, were not collected.
- No per-bank complaint data from CSALB, ANPC or BNR was found.
- No independent NPS or customer-satisfaction survey comparing these banks in 2024–2026 was found.
