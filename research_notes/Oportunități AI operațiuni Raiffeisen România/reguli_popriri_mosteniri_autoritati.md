# Romanian bank legal-operations back-office: popriri, authority information requests, inheritance/deceased clients and procuri. Codifiable rules, volumes and pain points (status 28 Oct 2026)

Scope note for the report writer: Romanian law only. Article texts were read from the official consolidated versions on legislatie.just.ro and ANAF's site, which I downloaded and parsed:
- **CPC**: Codul de procedură civilă, Legea 134/2010 republicată. Consolidated form dated 14.12.2025, with ÎCCJ notes up to March 2026.
- **CPF**: Codul de procedură fiscală, Legea 207/2015. Consolidated printable text that includes amendments up to OUG 7/2026, MO 146 of 25.02.2026.
- **OUG 99/2006**: latest consolidation listed is 05.03.2026.
- **Codul civil**: latest consolidation listed is 03.05.2026.
- **CPP**: Codul de procedură penală, latest consolidation listed is 13.06.2026.
- **OPANAF 878/2022, 626/2023 and 63/2017**: the PDFs published on static.anaf.ro.

Anything taken from a search-result summary rather than an opened page is marked "(search summary, page not opened)". The web-search budget ran out before I could search for dormant accounts, Avocatul Poporului or CSALB complaint statistics, or the post-death pension return rule. Those are listed under Gaps.

---

## 1. Popriri on bank accounts: legal basis (CPC + CPF), bank duties and deadlines, protected amounts, ranking, blocking vs transfer, future receipts, information duties, liability, and 2022–2026 changes

### Takeaway
Two parallel regimes govern garnishments on accounts:
- **CPC regime** (art. 781–792 + art. 729). Applies to bailiffs (executori judecătorești) enforcing civil titles. The bank blocks the funds and consigns or pays within **5 days**.
- **CPF regime** (art. 236). Applies to ANAF and to local tax authorities. The bank blocks up to the amount in the address and pays within **3 working days**. For ANAF this runs through the e-Popriri electronic cycle, which ends in about 4 days.

In both regimes the bank must apply the income-protection rules of CPC art. 729: the 1/3 and 1/2 caps, the half-of-minimum-net-wage floor, and the list of absolutely unseizable child allowances, special-purpose indemnities and similar benefits. Neither code has been substantively amended on these points since 2022, apart from the ANAF electronic workflow rules.

Two bills would change this, and the Senate rejected both in 2026. Both are still pending in the Chamber of Deputies:
- a 3,000-lei protected minimum balance (PLX 70/2026);
- a "single electronic garnishment" with lifting within 24h and a fee cap (L40/2026, PLX 198/2026).

### Cited Findings

#### 1.1 Which regime applies to which issuer
- Enforcement of any executory title is done only by the executor judecătoresc. The exception is titles for revenues owed to the general consolidated budget or to the EU budget. — [CPC art. 623, legislatie.just.ro](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- The CPF covers the administration of fiscal claims owed to the general consolidated budget, "indiferent de autoritatea care le administrează". This includes the organul fiscal local, i.e. DITL/DGITL and primării. — [CPF art. 1–2, legislatie.just.ro](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Fiscal enforcement starts with a **somație**. If the debt is not paid, and no mediation is notified, within **15 days** of its communication, enforcement continues. The somație is accompanied by the executory title. — [CPF art. 230(1)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- A bailiff poprire is set up **without somație**, based on the încheierea de încuviințare a executării. — [CPC art. 783(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - Under the current art. 666, that încheiere is issued by the **instanța de executare** (the court) within 7 days of the bailiff's request.
  - It states the title, and the sum with accessories, when determined or determinable. Approval is valid nationwide and allows all enforcement methods simultaneously. — [CPC art. 666(1)–(4)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - A search summary reports a late-2025 amendment of art. 666 that returned approval competence to the courts, and a 2026 Senate proposal on direct enforcement of titles that are executory by law. (search summary, page not opened — [juridice.ro](https://www.juridice.ro/811329/executarea-silita-fara-instanta-de-executare-o-analiza-critica-a-noii-filosofii-legislative-consacrate-de-art-666-cod-procedura-civila.html))
- Territorial competence: the bailiff's office must be in the circumscription of the court of appeal where the debtor has domicile or seat. — [CPC art. 782(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Concurrent fiscal and non-fiscal enforcement: if enforcement is started on the same income or assets for both fiscal titles and other titles, the enforcements are **joined (se conexează)**. They are then carried out under the CPF by the fiscal enforcement body that holds the larger fiscal claim. — [CPF art. 220(13)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

#### 1.2 CPC (bailiff) poprire: object, content of the address, effects

**Object**
- Garnishable: sums of money, securities and other incorporeal movables owed to the debtor or held in the debtor's name by a third person, including sums the third person "i le va datora în viitor" under existing legal relations. — [CPC art. 781(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- For **bank accounts**, both the **credit balance** and **future receipts** ("încasările viitoare") can be garnished, "cu respectarea limitelor prevăzute la art. 729, dacă este cazul". — [CPC art. 781(2)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Claims with a term or condition can be garnished, but the poprire is executable only after the term or condition. — [CPC art. 781(4)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - Related ÎCCJ case law: HP 24/2026, MO 195 of 13.03.2026, rejection decision. — [CPC consolidated notes](https://legislatie.just.ro/Public/DetaliiDocument/140271)

**Content of the address**
- The address must forbid the garnishee to pay the debtor and declares the sums garnished "în măsura necesară pentru realizarea obligației ce se execută silit". — [CPC art. 783(2)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Mandatory content: debtor name and domicile (individual) or name and seat (company), plus **CNP / CUI / CIF "dacă sunt cunoscute"**. — [CPC art. 783(3)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- If all of a person's accounts are targeted, including those of sub-units without legal personality, the identification elements of each account are given "dacă sunt cunoscute". — [CPC art. 783(4)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Branch rule**: an address sent to an operational unit of a credit institution attaches only to the accounts held at that unit. If the debtor has no account there, the unit must inform the bailiff about accounts at other units. — [CPC art. 783(5)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Conversion of a poprire asigurătorie into an executory one: the bailiff sends a certified copy of the title plus an address. The address contains the debtor's identification, the number and date of the original address, the **enforcement file number**, and the account where the sums were consigned. — [CPC art. 783(7)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Other creditors may garnish the same claim until the sums are released or distributed. — [CPC art. 783(8)](https://legislatie.just.ro/Public/DetaliiDocument/140271)

**Effects of the poprire**
- From the moment of communication, **all** garnished sums are blocked (indisponibilizate). Until full payment, the garnishee may make no payment or operation that could diminish them, **including during suspension**, unless the law provides otherwise. — [CPC art. 784(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Blocking extends to sums with future maturities, to civil fruits and to accessories. Payment or assignment is not opposable to the creditor, and the poprire interrupts prescription. — [CPC art. 784(2)–(5)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Blocking ends only if the debtor consigns, with special destination and at the bailiff's disposal, all sums covered by the poprire (art. 721). The bailiff then informs the garnishee. — [CPC art. 784(6)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- Banks may convert foreign currency to lei, or into the title's currency, **without the holder's consent**, at the **BNR rate** of the day. — [CPC art. 784(7)–(8)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - Under the CPF the conversion is done at the bank's own displayed rate. — [CPF art. 236(3)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

#### 1.3 CPC: what the bank (terț poprit) must do, and by when
- **Within 5 days** of communication (for future sums, from their maturity), the garnishee must do one of two things. — [CPC art. 787(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - **Consign** the sum, if the claim is exigible, and send proof to the bailiff. This is the default for ordinary claims.
  - **Pay directly to the creditor** for maintenance (întreținere) or child allowance, and for damages for death or injury to body or health. On request, the payment is sent to the creditor's domicile at the debtor's cost.
- With several popriri, the garnishee follows art. 787(1) and communicates to the bailiff or creditors the **names and addresses of the other creditors and the sums garnished by each**. — [CPC art. 787(2)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- If several popriri together exceed the garnishable sum, the garnishee retains and consigns the garnishable sum within the 787(1) term and informs all bailiffs involved. Distribution is done by the competent bailiff under art. 864+. — [CPC art. 789](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- The garnishee cannot file a contestation against the poprire. It raises its defences in the validation court. — [CPC art. 787(5)](https://legislatie.just.ro/Public/DetaliiDocument/140271)

**Validation (validarea popririi)**
- Trigger: the garnishee fails its obligations, including releasing the sum to the debtor instead of consigning it. The creditor, the debtor or the bailiff may seize the court **within at most one month** of the date the sum should have been consigned. — [CPC art. 790(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- For bank accounts, the court orders the poprire maintained for future sums until the claim is fully realised. — [CPC art. 790(6)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- A bad-faith garnishee may be fined **2,000–10,000 lei**. — [CPC art. 790(9)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- The validation judgment can be appealed within 5 days. Once definitive, it works as an **assignment of the claim** and is an executory title against the bank, up to the validated sum. — [CPC art. 791–792](https://legislatie.just.ro/Public/DetaliiDocument/140271)

**End of enforcement**
- Grounds include: full payment including costs, no seizable assets, creditor waiver, annulled title or enforcement. The bailiff issues an încheiere de încetare, communicated immediately to creditor and debtor. This is the document that lifts the poprire. — [CPC art. 703](https://legislatie.just.ro/Public/DetaliiDocument/140271)

#### 1.4 CPF (ANAF and local tax) poprire: art. 236 (text unchanged since OG 11/2022)

**Scope and set-up**
- Object: any seizable sums of income and cash in lei and foreign currency, securities and incorporeal movables held or owed by third parties, **including future sums** under existing relations. — [CPF art. 236(1)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **Not** garnishable: non-reimbursable credits and financing from national or international bodies for programmes or projects. — [CPF art. 236(2), as amended by OG 30/2017](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- An individual's employment income, pensions of any kind, and special-purpose aids or indemnities are seizable at the payer "**numai în condițiile Codului de procedură civilă**". — [CPF art. 236(4), as amended by Legea 82/2017](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- The poprire is set up by an address communicated to the garnishee, respecting art. 230, **with notice to the debtor**. **It is not subject to validation.** — [CPF art. 236(5)–(6)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- It takes effect **when the garnishee receives the address**. The garnishee **must record the day and the hour of receipt**. — [CPF art. 236(8)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

**Garnishee obligations**
- Pay the withheld sum within **3 working days** of set-up, or of exigibility, into the account indicated. — [CPF art. 236(9)(a), as amended by OG 5/2020](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- For a poprire asigurătorie other than on bank accounts, transfer the sum to the guarantees account. — [CPF art. 236(9)(c)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- If nothing is owed now or in the future, notify the enforcement body **within 5 days** of receipt. — [CPF art. 236(10)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- If several creditors garnish, the garnishee informs them in writing and distributes the sums following the order of preference in art. 258. — [CPF art. 236(11)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

**Bank accounts**
- Holders of bank accounts can be pursued by poprire on account sums. — [CPF art. 236(12)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **Existing sums and future daily receipts**, in lei and foreign currency, are blocked "**în limita sumei necesare** … astfel cum aceasta rezultă din adresa de înființare a popririi". Banks must pay blocked sums **within 3 working days of blocking**. — [CPF art. 236(13), as amended by OG 11/2022](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- From the date and hour of receipt, banks stop settling payment documents, debiting accounts or accepting other payments until the claim is fully paid. — [CPF art. 236(14)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K) Exceptions:
  - (a) sums for **salary payments** and the related withheld taxes and contributions, if the debtor or its legal representative declares on their own responsibility (declarație pe propria răspundere) that it has no other funds;
  - (b) excise payments by authorised warehouse-keepers, with a certified copy of the authorisation;
  - (c) excise paid on their behalf by buyers of energy products;
  - (d) payments needed to keep a payment facility (înlesnire) valid, with a certified copy of the approval.
- During a **poprire asigurătorie**, banks accept payments for the art. 236(14) items and for fiscal obligations to budgets administered by the fiscal body that set up the poprire. — [CPF art. 236(15)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Breach of art. 236(9), (11), (13), (14), (18), (20) or (21) makes **any payment null**. — [CPF art. 236(16)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- If suspension is not notified, the bank continues under (13), (14), (20) and (21). — [CPF art. 236(17)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Titles that cannot be honoured on the same day are pursued from the debtor's **daily receipts**. — [CPF art. 236(18)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

**Popriri set up by the organul fiscal central (ANAF)** — [CPF art. 236(20)–(21), added by OG 5/2020, in force 03.02.2020](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Banks send the "suma disponibilă de plată" **electronically**. Until the actual payment they do not debit the account or accept other payments. Art. 236(14) payments may be made only until the bank sends that information.
- Payment goes to the special account at the **Trezoreria Operativă Centrală**, quoting the **număr de evidență a plății**. If that number is wrong, the Treasury returns the money to the bank.

**Executing against the garnishee**
- If the garnishee says it owes nothing but ANAF has indications otherwise, the court of the garnishee's seat decides whether to maintain or set aside the poprire. A decision to maintain it is an executory title against the garnishee. — [CPF art. 237](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

**ANAF's electronic channel (Punctul central)**
- An ANAF president's order may designate other fiscal bodies to carry out enforcement acts through "procese electronice masive". This is the legal hook for the e-Popriri **Punctul central**. — [CPF art. 220(2^1)(b)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

**Operational timing since 01.10.2023, as one bank explains it to its customers** — [Intesa Sanpaolo Bank Romania notice](https://www.intesasanpaolobank.ro/document/documents/ISPROMANIA/Protocoale-ANAF/protocol-ANAF-poprirea-electronica.pdf)
- **Legal persons**: the art. 236(14) payments (salaries, excise, facility-maintaining taxes) can be made **only on the day the poprire is set up** (if funds exist) or **on the day the account is credited** (future receipts). After that, the funds go to ANAF.
- **Individuals**: the bank pays ANAF the sums coming from salaries, pensions and other labour income "**în cotele legale urmăribile**", starting the day the poprire is set up or the day the account is credited.
- The same timelines apply to popriri from **other enforcement bodies that compete with ANAF's**. The notice cites art. 220(13) together with art. 236(11) CPF.

#### 1.5 Protected and unseizable amounts (applied by banks to account credits)

**CPC art. 729, "Limitele urmăririi veniturilor bănești"** — [CPC art. 729](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- (1) Salaries and other periodic income, social-insurance pensions and other periodic subsistence sums can be seized:
  - a) up to **1/2 of net monthly income** for maintenance or child allowance (alocație pentru copii);
  - b) up to **1/3** for any other debts.
- (2) With several seizures on the same sum, the total **cannot exceed 1/2 of net monthly income**, whatever the nature of the claims, unless the law provides otherwise.
- (3) If employment income or other periodic subsistence sums are **below the salariul minim net pe economie**, only "**partea ce depășește jumătate din acest cuantum**" can be seized.
- (4)–(5) Sick-leave benefits (incapacitate temporară de muncă), dismissal compensation and unemployment benefits can be seized **only** for maintenance or for damages for death or bodily injury, and only **up to half** of their amount.
- (7) **Absolutely unseizable for any debt**:
  - alocațiile de stat și indemnizațiile pentru copii;
  - ajutoarele pentru îngrijirea copilului bolnav;
  - ajutoarele de maternitate;
  - ajutoarele acordate în caz de deces;
  - bursele de studii acordate de stat;
  - diurnele;
  - "orice alte asemenea indemnizații cu destinație specială, stabilite potrivit legii".

**Related rules**
- Waiving these protections, and any seizure or assignment made in breach of them, is "**nule de drept**". — [CPC art. 730](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Not** garnishable under the CPC. — [CPC art. 781(5)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - a) special-purpose sums the debtor cannot dispose of;
  - b) non-reimbursable credits or financing for programmes or projects;
  - c) sums for paying **future salary rights for 3 months** from set-up. With several popriri on the same account, the 3 months run once, from the first poprire. This matters for corporate debtors.
  - RIL 1/2020: salary sums held in public institutions' accounts at the Treasury and at banks cannot be garnished.
- Banks' own account of how this works in practice, as described in the CES opinion. — [CES opinion 8071/30.12.2025](https://www.ces.ro/newlib/PDF/avize/2026/2.21-b674-Aviz-CES-30.12.2025.pdf)
  - When a poprire is set up, the accounts are blocked "cu sau fără disponibil, necunoscând soldul contului sau natura sumelor".
  - **Afterwards** the banks analyse account turnover and the nature of credited sums under art. 236(4) CPF together with art. 729 CPC, so that legally unseizable sums are released to the debtor.
- Minimum wage values used for art. 729(3) (secondary source, not verified against the HG): gross minimum wage **4,325 lei**, citing HG 146/2026 and OUG 89/2025; **salariul minim net 2,699 lei from 1 July 2026**; protected half = **1,349.50 lei**. — [zarinacrm.ro calculator (commercial)](https://www.zarinacrm.ro/calculator-poprire-salariu/)

#### 1.6 Multiple garnishments: ranking and concurrency

**CPC ranking for distribution by the bailiff** — [CPC art. 865](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- a) enforcement and conservation costs;
- b) funeral costs of the debtor;
- c) salaries, pensions, unemployment and social-insurance benefits, and claims for damages for death or injury;
- d) maintenance, child allowance and other periodic subsistence sums;
- e) fiscal claims;
- f) state loans;
- g) damages to public property;
- h) bank loans, supplies, services, rents;
- i) **fines** to the state or local budgets;
- j) other claims.
- Claims of equal rank share **pro rata**.
- Holders of secured rights (gaj/ipotecă) rank before item c). — [CPC art. 867](https://legislatie.just.ro/Public/DetaliiDocument/140271)

**CPF ranking** — [CPF art. 258](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Same structure as the CPC: a) costs, b) funeral, c) salaries etc., d) maintenance, e) fiscal claims, **including fines** to the state or local budgets, f) state loans, g) damages to public property, h) bank loans etc., i) other claims.
- Pro rata within the same rank.

**Payment order in e-Popriri**
- Banks must pay blocked sums to the account indicated by the enforcement body "**în ordinea vechimii primirii adreselor de înființare a popririi**". — [OPANAF 878/2022, Annex 1 pct. 8.5](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)

**Income-based popriri**
- The **cumulative cap of 1/2** of net monthly income applies whatever the number of creditors. — [CPC art. 729(2)](https://legislatie.just.ro/Public/DetaliiDocument/140271)

#### 1.7 Suspension and lifting (CPF)
- **During suspension** — [CPF art. 233(3)–(5)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - Earlier enforcement measures, including blocked bank sums, **stay in place**.
  - If suspension follows a guarantee (art. 235), the poprire amount is updated within **2 days**.
  - Suspending a bank poprire stops the blocking of **future** daily receipts from the date and hour the suspension address is communicated.
  - Sums already in the account stay blocked. The debtor may use them only to pay fiscal obligations or salaries.
- **Suspension on request**: if popriri make it impossible to continue business, with special social consequences, the fiscal body may suspend fully or partly on the debtor's request. This is allowed **once in 2 calendar years**, for at most **6 consecutive months**, and the debtor must offer unencumbered assets or guarantees. — [CPF art. 233(7)–(10)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **Lifting** — [CPF art. 234(2)–(5)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - Measures are lifted by a decision issued **within at most 2 days** of the end of enforcement.
  - The enforcement body **lifts the bank poprire for sums exceeding the claim** when the banks' information shows that blocked sums cover it.
  - A poprire left "fără obiect" (without object) is also lifted.
- **e-Popriri versions**
  - During suspension, the Treasury does **not validate** bank transfers. — [OPANAF 626/2023, new pct. 4.2^1](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_626_2023.pdf)
  - Blocked sums used under art. 233(5) are transferred by the bank to the relevant fiscal revenue accounts. — [OPANAF 626/2023, amended pct. 5.3](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_626_2023.pdf)

#### 1.8 Duty to inform
- **Debtor, CPC regime**: the **bailiff** informs the debtor and sends a copy of the poprire address, the approval (încuviințare) and the title if not already communicated. — [CPC art. 783(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Debtor, CPF regime**: the **fiscal body** notifies the debtor ("cu înștiințarea debitorului"). — [CPF art. 236(5), (7)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - The ANAF form is "Adresă de înștiințare privind înființarea popririi". — [OPANAF 63/2017, Annex 27](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_63_2017.pdf)
- **Bank to enforcement body**
  - Notice that nothing is owed: 5 days under the CPF. — [CPF art. 236(10)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - Written notice to all creditors when there are several. — [CPF art. 236(11)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - Names, addresses and sums of the other creditors, and notice to all bailiffs when popriri exceed the garnishable sum. — [CPC art. 787(2), 789(1)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - Accounts held at other units of the bank. — [CPC art. 783(5)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Bank to client**: no statutory duty was found in the CPC or CPF. In practice, most banks notify the account holder by SMS, e-mail or banking app, and some use all three. — [Wall-street.ro, 9 Mar 2025](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html)
  - The Civil Code requires banks to inform clients free of charge, monthly by default, about operations in their accounts. — [Codul civil art. 2.191(3)](https://legislatie.just.ro/Public/DetaliiDocument/175630)

#### 1.9 Bank liability, sanctions and debtor remedies
- **Joint and several liability**: garnishees are jointly liable with the debtor in the cases of art. 236(9), (11), (13), (14), (18), (20) and (21) CPF, "**în limita sumelor sustrase indisponibilizării**". A debtor's legal representative who falsely declares under art. 236(14)(a) that the debtor has no other funds is also jointly liable. — [CPF art. 25(1)(b)–(c)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **Contravention fines**: "nerespectarea obligațiilor ce îi revin terțului poprit, potrivit art. 236 alin. (9)-(11) și (21)" is a contravention, art. 336(1)(k). The fine under art. 336(2)(d) is **1,000–5,000 lei** for medium and large taxpayers and 500–1,000 lei for others. — [CPF art. 336](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **e-Popriri follow-up**: if a bank does not transfer, or transfers only partly, an amount it confirmed and was ordered to pay, the Punctul central sends a **referat** to the competent fiscal body. That body examines solidarity under art. 25(1)(b). Late transfer is examined for sanction under art. 336(2)(d). Foreign-exchange differences between confirmation and transfer **do not** trigger solidarity. — [OPANAF 878/2022, pct. 3.11–3.13](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- **CPC**: validation and a bad-faith fine of 2,000–10,000 lei. — [CPC art. 790](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Debtor remedies**: a **contestație la executare** within **15 days** of receiving the communication or notice of the poprire. For periodic income, the term starts at the latest with the first retention. — [CPC art. 712, 715(1) pct. 2](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - Fiscal acts: contestation within 15 days under art. 260–261 CPF, as stated on the ANAF form. — [OPANAF 878/2022, Annex 3](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- **Commentary (Oct 2026)**: an IT error is **not force majeure**. Liability for wrongful blocks becomes a "labirint al răspunderii" between bank, ANAF and bailiff. The author argues that the stamp duty for contestation and the cauțiune for suspension make remedies ineffective for a debtor whose funds are frozen. — [juridice.ro, L. Gînga, 23.10.2026](https://www.juridice.ro/862896/interoperabilitatea-bazelor-de-date-in-procedura-popririi-electronice-de-la-automatizarea-interogarilor-la-riscul-erorilor-de-sistem.html)

#### 1.10 Amendments 2022–2026 and pending proposals

**Fiscal (CPF) side**
- **OG 11/2022** (MO 97 of 31.01.2022, in force 03.02.2022) rewrote art. 236(3) (FX conversion at the bank's rate), (13) (blocking up to the address amount, payment within 3 working days), (14) (exceptions) and (15). — [CPF consolidated notes](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Up to the latest amendments captured (OUG 7/2026), **art. 236 was not further amended**. 2023–2026 amendments to Title VII touched other articles, e.g. Legea 239/2025 and OUG 20/2023. — [CPF consolidated notes](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **OPANAF 878/2022** of 03.05.2022 (MO 466 of 10.05.2022) replaced OMFP 1665/2020, which was abrogated on 11.05.2022 by OMF 1112/2022. It sets up the e-Popriri workflow. — [OPANAF 878/2022](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- The ANAF–banks collaboration protocol under it has been in force since **29.09.2022**. — [Intesa notice](https://www.intesasanpaolobank.ro/document/documents/ISPROMANIA/Protocoale-ANAF/protocol-ANAF-poprirea-electronica.pdf)
- **OPANAF 626/2023** of 05.05.2023 — [OPANAF 626/2023](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_626_2023.pdf)
  - From **01.10.2023**, it abrogated the voluntary convenție-cadru (Annex 2).
  - It also abrogated pct. 8.4. That point had exempted banks that had not signed the convention from Chapter III, the "analysis of payable sums" mechanism. The effect is that the single-recovery payment logic now applies to all banks.
  - Reconciliation of pre-existing popriri is done on a calendar agreed with the banks.
  - A trade-press headline at the time read "Popririle pe mai multe conturi bancare pentru aceeași datorie nu vor mai fi posibile". (search summary, page not opened — [Bursa, 07.06.2023](https://www.bursa.ro/popririle-pe-mai-multe-conturi-bancare-pentru-aceeasi-datorie-nu-vor-mai-fi-posibile-29649941))
- **Revolut Bank UAB Vilnius Sucursala București** joined the e-Popriri mechanism on **07.02.2025**. Before that, ANAF had to request garnishment through the Lithuanian authorities under Directive 2010/24/EU. — [Wall-street.ro](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html); [ANAF Brașov communiqué 23.10.2023](https://static.anaf.ro/static/3/Brasov/20231023105828_comunicat_popriri_pf.pdf)

**Civil (CPC) side**
- No amendment notes for art. 729 or art. 781–792 dated 2022–2025 appear in the consolidated text. The latest notes on art. 783 date from OUG 1/2016, and art. 660(3) was abrogated by Legea 310/2018. — [CPC consolidated](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- **Legea 192/2022** (in force 02.07.2022) added art. 154^1. It concerns e-mail communication of **court judgments**, not popriri. — [Stanciu, Analele UB 2/2022](https://drept.unibuc.ro/documente/2022/2,%202022,%201.%20Roxana%20Stanciu%20-%20Legea%20nr.%20192%202022%20pentru%20completarea%20Legii%20nr.%20134%202010%20privind%20Codul%20de%20procedura%20civila.pdf)
- The CCR is reported to have upheld poprire **without prior somație** (art. 783(1)) in **Decision 235/2026**. This comes from a commentary and was not checked against the decision text. — [juridice.ro 23.10.2026](https://www.juridice.ro/862896/interoperabilitatea-bazelor-de-date-in-procedura-popririi-electronice-de-la-automatizarea-interogarilor-la-riscul-erorilor-de-sistem.html)

**Pending proposal 1: 3,000-lei protected balance**
- Bill **B528/2025 / PLX 70/2026** amends CPC art. 781. Balances up to **3,000 lei** in individuals' accounts would be fully protected from poprire. The amount would be indexed yearly by Finance Minister order to minimum-wage growth, and the rule would also apply to pending enforcements. — [juridice.ro](https://www.juridice.ro/804470/sumele-sub-3-000-lei-din-conturi-nu-pot-fi-poprite-proiect.html)
- Initiators: 11 POT parliamentarians. The Legislative Council, the CSM and the committees gave negative opinions. **Senate rejected it on 11.02.2026** (82 for rejection, 6 against, 9 abstentions). It is now in the Chamber of Deputies' committees. — [Factual.ro](https://www.factual.ro/declaratii/fals-anamaria-gavrila-sustine-ca-milioane-de-romani-au-popriri-pe-conturi/)

**Pending proposal 2: single electronic garnishment**
- Bill **b674/2025 / L40/2026 / PLX 198/2026**, initiated by Senator Gheorghe Vela, amends the CPF. It would: — [Senate explanatory memorandum](https://www.senat.ro/legis/PDF/2026/26L040EM.pdf)
  - introduce a "**poprire unică electronică**": one order sent simultaneously to all banks;
  - require **automatic lifting within 24 hours** of full recovery;
  - cap the bank fee for a poprire through a BNR regulation, charged **once per claim**;
  - add art. 164^1, automatic regularisation of payments made to the wrong public-institution account within 15 working days;
  - give 90 days for secondary legislation and 120 days for IT implementation.
- History — [Senate file L40/2026](https://www.senat.ro/legis/lista.aspx?nr_cls=L40&an_cls=2026)
  - Opinions: Legislative Council favourable; **CES, BNR and the Government negative**.
  - **Senate rejected it on 11.03.2026** (59–36).
  - Sent to the Chamber on 16.03.2026. The last recorded event was 19.05.2026.
- The CES's reasons: the mechanism already exists in e-Popriri. One poprire takes **4 days**: day 1 set-up, day 2 banks report payable amounts, day 3 payment, day 4 lifting at all banks. Delays come from the Treasury and local fiscal-body flows, not from banks. Banks "au investit masiv" in e-Popriri. — [CES opinion](https://www.ces.ro/newlib/PDF/avize/2026/2.21-b674-Aviz-CES-30.12.2025.pdf)

**Earlier history**
- In 2019 the Finance Minister announced that ANAF would garnish only the sums owed and lift in real time. (search summary, page not opened — [Profit.ro](https://www.profit.ro/taxe-si-consultanta/exclusiv-anaf-va-popri-in-conturile-bancare-doar-sumele-datorate-si-va-ridica-poprirea-in-timp-real-teodorovici-introducem-masura-in-cel-mai-scurt-timp-19039293)) This was implemented through OG 5/2020 and OMFP 1665/2020, now OPANAF 878/2022.

### Inferences

**Draft rules-engine decision table for an incoming poprire, built from the findings above. Each rule cites its basis.**
- **POP-01 Classify the issuer and regime**
  - ANAF via e-Popriri → CPF art. 236 + OPANAF 878/2022.
  - Local tax body (DITL/DGITL/primărie) → CPF art. 236(1)–(19). The e-Popriri-specific (20)–(21) do not apply.
  - Bailiff → CPC art. 781–792.
  - Anything else (e.g., a court acting directly) → exception.
- **POP-02 Completeness check, bailiff**: address + title + **court încheiere de încuviințare**, or a certificate of the solution (CPC 783(1), 666). Debtor name and domicile or seat; CNP/CUI if known (783(3)); bailiff territorial competence (782(1)). Missing CNP or ambiguous identity → human review (homonym risk).
- **POP-03 Completeness check, fiscal**: issuing body, debtor CIF/CNP, amount, executory title(s), payment account / număr de evidență a plății.
- **POP-04 Customer matching**: by CNP or CUI. Possible negative responses, using the e-Popriri reason codes:
  - 1 = no account;
  - 2 = insolvency;
  - 3 = account closed;
  - 4 = debtor deceased or deregistered;
  - 5 = other.
  - A branch-addressed bailiff poprire binds only that unit's accounts; if the debtor has no account there, inform the bailiff of accounts at other units (783(5)).
- **POP-05 Timestamp**: fiscal popriri take effect at receipt, and day and hour must be recorded (236(8)). e-Popriri items are deemed received at the start of the first banking day after upload (OPANAF 878 art. 6, pct. 2.3).
- **POP-06 Block** the existing balance and future receipts up to the amount in the address (CPF 236(13); CPC 781(2), 784(1)–(2)).
- **POP-07 Classify every credit (individuals only)**:
  - unseizable, CPC 729(7) — child allowances, maternity, death aid, sick-child aid, state study grants, diurne, special-purpose indemnities → release;
  - limited, 729(4)–(5) — sick leave, unemployment, dismissal compensation → seizable only for maintenance or bodily-injury damages, max 1/2;
  - periodic income, 729(1)–(3) — salary, pension → apply the 1/3 or 1/2 caps, the 1/2 aggregate cap, and the half-minimum-net-wage floor;
  - other → fully seizable.
  - This needs a reliable source tag on each credit: payer IBAN or CUI (employer, Casa de Pensii, ANPIS/AJPIS, AJOFM) and the payment description.
- **POP-08 Exceptions for legal persons (CPF 236(14))**: salary payments plus withheld taxes (with a declarație pe propria răspundere), excise, facility-maintaining taxes. Since 01.10.2023 these are allowed only on the day of set-up or the day of crediting (Intesa). CPC regime: 3-month salary carve-out (781(5)(c)).
- **POP-09 Payment**
  - CPC: consign, or pay maintenance and child allowance directly to the creditor, within 5 days (787).
  - CPF (paper): pay within 3 working days (236(9)(a), (13)).
  - e-Popriri: send the "suma ce poate fi plătită" message by 17:00 of the next banking day, and again after each credit (pct. 3.2). Pay on the day the ordonanțare de plată is downloaded (pct. 3.8) to IBAN RO08TREZ999506702XXXXXXX with the număr de evidență a plății.
- **POP-10 Concurrency**: queue by receipt time (OPANAF 878 pct. 8.5). Apply the CPC 729(2) aggregate cap. CPC 789: consign the garnishable sum and inform all bailiffs. CPF 236(11)/258: notify creditors and distribute by rank. CPF 220(13): conexare when fiscal and non-fiscal enforcement overlap. **Any conflict between first-come-first-served and rank-based distribution → human review.**
- **POP-11 Suspend, continue, update, lift**: handle the e-Popriri statuses transformare / înființare / suspendare / continuare / ridicare / actualizare sume (OPANAF 878 pct. 1.2(i)). The CPC regime lifts only on a bailiff's încheiere de încetare (703) or proof of consignment (784(6)). Client documents alone are not enough (see the Revolut practice in Q2).

**Worked numbers for art. 729(3), using the unverified 2026 value of 2,699 lei net minimum wage (floor = 1,349.50 lei)**
- For a monthly salary of 2,000 lei, the seizable base is 650.50 lei.
- The commercial calculator then applies 1/3 to that base (216.83 lei).
- The text of art. 729(3) can also be read as allowing the whole 650.50 lei, subject only to the 1/3 cap on total net income (666.67 lei).
- The two readings give different results, so this should be a configurable parameter and an escalation flag.

**What "limiting blocking to the debt amount" means in practice**
- Under the CPF and e-Popriri, each bank blocks up to the full debt (236(13)).
- Only **payment** is capped across banks (pct. 3.6). Excess blocks are lifted after payment (CES: day 4).
- A debtor with accounts at N banks can therefore have up to N × the debt frozen for several days. This is the pain point both 2026 bills target.

**No protected minimum balance exists in force.**
- The only floor is income-based (729(3)). It requires the bank to infer the "venit lunar net" from account credits, which is error-prone.

### Gaps
- Amendments to CPF art. 236 or CPC art. 729/781–792 after **February 2026 (CPF)** and **December 2025 (CPC)** could not be confirmed. Neither could the final fate of PLX 70/2026 and PLX 198/2026 after May 2026. The web-search budget was exhausted.
- The exact deadline for ANAF and bailiff **lifting at banks other than the one that paid**, outside e-Popriri, was not found.
- **Fee rules**: no BNR or statutory cap on poprire fees was found. Only press data points (see Q3).
- The full text of the "art. 666 modification adopted end-2025" and of CCR Decision 235/2026 was not opened.
- The CPC regime for **poprire asigurătorie** by bailiffs (precautionary measures) was not extracted.
- No authoritative interpretation was found of art. 729(3) combined with art. 729(1) (floor first, then 1/3 or 1/2?) as applied to bank-account credits. ÎCCJ case law on this was not searched.

---

## 2. How popriri reach banks today (channels by issuer), the data fields they contain, and the official templates

### Takeaway
- **ANAF** popriri arrive **only electronically** through **e-Popriri**, a private space on the ANAF portal. Each act is a signed PDF with an attached XML, keyed by a **număr de evidență a plății**. Banks answer with structured messages: reasons for non-registration, payable amounts.
- **Bailiffs** and **local authorities** (primării/DITL) still send **paper or e-mailed PDF** addresses. Their content is set by CPC art. 783 or by the CPF.
- The ANAF form models are in **OPANAF 63/2017** (Annex 24: "Adresă de înființare a popririi asupra disponibilităților bănești") and in the e-Popriri annexes of **OPANAF 878/2022**.

### Cited Findings

#### 2.1 ANAF e-Popriri (OPANAF 878/2022 as amended by OPANAF 626/2023)

**Transport and timing**
- ANAF gives banks a system in the private space of the ANAF portal for uploading and downloading documents. Acts are communicated "sub forma unui fișier .pdf cu .xml atașat, semnat electronic". Bank access uses the identification procedure of the CPF art. 61 information-exchange order. — [OPANAF 878/2022 art. 2](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- **Date of communication** = the first banking day after upload; **time** = the start of the banking day. Upload deadline is 24:00. — [OPANAF 878/2022 art. 6; Annex 1 pct. 2.3](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Acts carry the extended electronic signature of the Ministry of Finance or a qualified signature (eIDAS). — [art. 9](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Each day, the central fiscal bodies (art. 30, 33, 35 CPF) send their poprire addresses electronically to the Unitatea de Imprimare Rapidă (UIR). After validation, e-Popriri, built by CNIF, loads them for each bank. — [Annex 1 pct. 1.3–1.4, 2.1–2.4](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- One address is generated **per bank where the debtor has accounts**. If ANAF later finds a new account at another bank, it sends a new address for the **remaining balance**. — [pct. 2.1, 2.6](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- ANAF knows where accounts are because banks report **daily** every account opened or closed: holders, signatories, beneficial owners, IBAN, opening and closing dates. — [CPF art. 61(2)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Statuses: transformare (precautionary → executory), înființare, suspendare totală/parțială, continuare, ridicare, actualizare sume. — [pct. 1.2(i)](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Glossary — [pct. 1.2(d)–(h)](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
  - **număr de evidență a plății** = unique ID of the poprire address;
  - **sumă poprire** = amount for which the poprire was set up;
  - **suma rămasă de recuperat** = amount still outstanding;
  - **suma ce poate fi plătită** = amount the bank confirms it can pay;
  - **ordonanțare de plată** = payment request message sent to the bank.

**Bank message: non-registration** — [pct. 2.5](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf); [Annex 4](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Fields: (a) număr de evidență a plății; (b) the debtor's tax identification code, or that of a registered secondary seat; (c) reason.
- Reasons: c1 no account open; c2 company in insolvency; c3 account closed; c4 debtor deceased or deregistered; c5 other reasons agreed with the Punctul central.
- Annex 4 table columns: ID poprire, număr de evidență a plății, cod de identificare fiscală, motivul neînregistrării (codes 1–5).

**Bank message: payable amount** — [pct. 3.2–3.4](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf); [Annex 5](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Sent as a signed PDF+XML in a single file:
  - by **17:00 of the next banking day** after the poprire is communicated; and
  - by 17:00 of the next banking day after **any credit** to the debtor's accounts.
- Minimum fields: număr de evidență a plății; debtor CIF; **suma pe care o poate plăti**; any other relevant data.
- From the moment it is sent, the bank does not debit the account or accept other payments until the actual payment.
- Annex 5 columns: ID poprire, număr de evidență a plății, cod de identificare fiscală, data (ZZ.LL.AAAA), suma care poate fi plătită (lei).

**ANAF payment algorithm** — [pct. 3.5–3.7](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- After the deadline, confirmed amounts are sorted automatically in **descending order**. Payment orders are uploaded daily by 24:00.
- If one bank confirms the full remaining amount, only that bank receives the order.
- If the confirmations together do not cover the amount, every bank receives an order for its confirmed sum.
- If they exceed it, orders are capped at the remaining amount. The last bank is ordered to pay only the difference.
- If there are no funds, the poprire stays in place for future credits.

**Bank payment** — [pct. 3.8](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf); [Annex 6](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf); [pct. 4.1](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- The bank downloads the orders at opening of business and pays **the same day**.
- Payment-order fields:
  - "Beneficiar" = the debtor's name;
  - "Cod de identificare fiscală" = the debtor's CIF;
  - "Cod IBAN beneficiar" = **RO08TREZ999506702XXXXXXX**;
  - "La" = "Trezoreria Operativă Centrală";
  - "Nr. de evidență a plății".
- The Annex 6 ordonanțare cites art. 236(20)–(21) CPF and gives: număr de evidență a plății, ID poprire, debtor CNP/CIF and the amount.
- The account is 50.67.02 "Disponibil din sume încasate din înființarea popririi (bancă/terți) asupra sumelor ce se cuvin debitorilor".

**Partial or non-payment** — [pct. 3.9–3.10](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- If a bank pays only part or nothing, the remaining amount is updated. The unpaid confirmation is cancelled and the sorting runs again.
- The bank re-sends its payable amount, updated with new funds.

**Treasury validation** — [pct. 4.2–4.6](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- The Treasury validates automatically, matching număr de evidență and CIF. If the remaining amount is 0, it does not validate.
- Unvalidated payments are returned to the bank on the next working day.
- Data fed back to e-Popriri: beneficiary CIF, amount, document number and date, număr de evidență, the bank's SWIFT/BIC, statement date, payment date, payer CIF, payment explanations.

**Updates and lifting** — [pct. 6.1–6.4, 7.1–7.2](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Every day **by 11:00** the system takes from the fiscal bodies the remaining amount for each număr de evidență. It keeps the **lower** of its own value and the fiscal body's value.
- An "adresă pentru înștiințarea instituțiilor de credit privind sumele rămase de recuperat" (Annex 3) is then sent.
- If the remaining amount reaches **0 lei**, the Punctul central issues the **decizie de ridicare** through e-Popriri.

**Other rules**
- Fallback if the platform is down: the "cale alternativă … privind schimbul masiv de date". — [pct. 8.2](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Archive: 5 years after enforcement ends. — [pct. 8.6](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Responsibility for the correctness of data lies "exclusiv" with the territorial enforcement bodies. — [pct. 8.8](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- Personal data processed under the original convenție-cadru: name, home address, CNP/NIF, amount of fiscal obligations. — [Annex 2 art. 5.2, abrogated from 01.10.2023 by OPANAF 626/2023](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- "Zi bancară" = any day except Saturday, Sunday and legal holidays. The bank declares its banking-day start time. — [Annex 2 pct. 3.2, abrogated with the convention](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
- **Annex 3 text**, the update address to banks — [Annex 3](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
  - legal basis art. 230(5) and 233(3) CPF;
  - număr de evidență a plății, debtor CIF, new remaining amount;
  - "produce efecte din momentul primirii … aveți obligația să înregistrați atât ziua, cât și ora primirii";
  - contestation within 15 days (art. 260–261 CPF).

#### 2.2 ANAF form catalogue (paper or IT-generated), OPANAF 63/2017 (MO 32 and 32 bis of 11.01.2017)
- OPANAF 63/2017 approves 58 models. Those relevant to banks: — [OPANAF 63/2017 art. 1](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_63_2017.pdf)
  - Annex 10: Adresă de înființare a popririi **asigurătorii** asupra disponibilităților bănești;
  - Annex 14: Decizie de ridicare a popririi asigurătorii asupra disponibilităților bănești;
  - Annex 17: Titlu executoriu;
  - Annex 18: Somație;
  - Annex 20: Adresă de înființare a popririi **executorii** asupra disponibilităților bănești (after conversion from asigurătorie);
  - Annex 22: Adresă de înștiințare privind înființarea popririi executorii ca urmare a transformării;
  - **Annex 24: Adresă de înființare a popririi asupra disponibilităților bănești**;
  - Annex 25: Adresă … asupra sumelor datorate debitorului de către terți;
  - Annex 27: Adresă de înștiințare privind înființarea popririi (to the debtor);
  - Annex 48: Adresă de suspendare … a indisponibilizării conturilor;
  - Annex 50: Adresă privind continuarea măsurilor de executare silită prin poprire asupra disponibilităților bănești;
  - Annex 53: Decizie de ridicare a măsurilor de executare silită asupra disponibilităților bănești.
- The annex texts themselves were published in **MO 32 bis**, which is not on the ANAF page. — [OPANAF 63/2017](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_63_2017.pdf)
- **OPANAF 3942/2020** replaced Annexes 48 and 49, the suspension addresses. The Annex 48 model contains: — [contabilul.manager.ro](https://contabilul.manager.ro/a/25506/ordinul-nr-39422020-modifica-doua-formulare-utilizate-in-domeniul-colectarii-creantelor-fiscale.html)
  - ANAF logo and issuer name and address;
  - debtor name, fiscal domicile and fiscal code (CNP/CIF/CUI);
  - temporary, total or partial suspension, with a reference to the original poprire address, its **număr de evidență a plății**, date and amount;
  - legal basis: art. 203(2)–(4), 233, 235, 236(17), 264(12) CPF;
  - the rule that existing sums stay blocked and may be used only for fiscal obligations or salaries;
  - contestation within 15 days, and effect from receipt, with day and hour to be recorded;
  - format A4, sent to the bank electronically or on paper.
  - The Annex 49 table (third parties) has columns: obligation name, payment category, titlu executoriu nr./dată, suspended amount, total.

#### 2.3 Bailiffs and local tax authorities: still paper or e-mail
- e-Popriri covers only the **central** fiscal bodies (art. 30, 33, 35 CPF). — [OPANAF 878/2022 pct. 1.3](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)
  - CPF art. 236(20)–(21) likewise refer only to the "organul fiscal central". — [CPF](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- Revolut's published intake rules show how the non-ANAF channels work in practice. — [Revolut "Informații despre popriri", 26.03.2025](https://cdn.revolut.com/terms_and_conditions/pdf/informa_ii_despre_popriri_b41776b9_1.0.0_1742987422_ro.pdf)
  - Bailiffs, **primării and other institutions with enforcement powers** must send addresses **only** to a dedicated e-mail address or on paper to a stated address.
  - E-mail rules: **one PDF attachment per e-mail** (poprire plus annexes), ideally under 3 MB. Other formats such as jpeg, .doc or .p7s, or details in the e-mail body, cannot be processed under the same conditions.
  - The subject line must be **unique per poprire**, in the format "tip poprire/nume_prenume/data", e.g. "Infiintare/Popescu Ion/150125". Preferred sending window is 09:00–14:00.
  - Paper: the full package stapled together, A4; batches need a cover list (opis).
  - Non-ANAF popriri are lifted **only after an address from the issuing authority**. Client requests "nu pot fi procesate".
  - ANAF popriri are standardised under the e-Popriri protocol and are lifted automatically, "fără posibilitatea ridicării la solicitarea clientului".
- Bank practice on lifting (survey of banks): most banks lift an ANAF poprire **only on an ANAF address**. They do not accept another bank's statement or a payment order. Some lift if the payment was made from an account at the same bank using the poprire's details. — [Wall-street.ro](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html)
- Targeting differs by issuer. According to BRD's CEO in 2019, ANAF sends popriri to **all** of a person's accounts, whereas bailiffs target a specific account. — [Adevărul, 10.04.2019](https://adevarul.ro/economie/stiri-economice/avalansa-popririlor-milioane-conturi-blocate-anaf-pune-fiscul-poprire-conturile-debitorului-aceeasi-datorie-1_5caddb67445219c57e56305c/index.html)
- How bailiffs find accounts, according to an October 2026 commentary:
  - Their case-management software (e.g. Zenic, ExecSoft) queries **PatrimVen**, the Ministry of Finance asset and income aggregator fed daily by banks, through APIs using the debtor's CNP/CIF.
  - Garnishment addresses are then "generated and disseminated at once", and accounts can be blocked "în câteva secunde".
  - — [juridice.ro 23.10.2026](https://www.juridice.ro/862896/interoperabilitatea-bazelor-de-date-in-procedura-popririi-electronice-de-la-automatizarea-interogarilor-la-riscul-erorilor-de-sistem.html)
  - Legal basis for fiscal bodies to share data with bailiffs: [CPC art. 660(2)](https://legislatie.just.ro/Public/DetaliiDocument/140271).
- Public authorities' requests for bank-account information are handled exclusively electronically through ANAF's **PatrimVen** system (access procedure in OMF 109/2022). Start date not verified. (search summary, page not opened — [Profit.ro](https://profit.ro/stiri/economie/anaf-le-va-furniza-autoritatilor-publice-informatii-referitoare-la-conturile-bancare-doar-in-format-electronic-15956462); [OMF 109/2022](https://static.anaf.ro/static/10/Anaf/legislatie/OMF_109_2022.pdf))

#### 2.4 Mandatory content of a bailiff poprire address (CPC)
- The address must specify the **titlul executoriu**. — [CPC art. 783(1)–(4), (7)](https://legislatie.just.ro/Public/DetaliiDocument/140271)
- It is accompanied by the **încheierea de încuviințare** or a certificate of the solution.
- It contains the prohibition to pay the debtor, "în măsura necesară".
- Debtor name and domicile, or name and seat, plus CNP/CUI/CIF if known.
- For "all accounts" requests: identification of each account and sub-unit, if known.
- For conversion from asigurătorie: number and date of the original address, **număr dosar de executare**, and the account where sums were consigned.
- The încheiere de încuviințare itself states the title, the sum with accessories, and the method of enforcement if requested. — [CPC art. 666(3)](https://legislatie.just.ro/Public/DetaliiDocument/140271)

### Inferences
**Canonical input data model for the agent (union of the sources above)**
- Document metadata:
  - type: înființare / actualizare / suspendare / continuare / ridicare / transformare / înștiințare;
  - regime: CPC or CPF-central or CPF-local;
  - issuer name, address and CIF;
  - issuer's registration number and date;
  - **received date and time**;
  - channel: e-Popriri / e-mail / post / counter.
- Debtor: name; CNP or CUI/CIF; domicile or seat; secondary seats.
- Claim:
  - total amount and currency;
  - per-title rows: obligation name, title number and date, amount;
  - accessories and enforcement costs;
  - număr de evidență a plății (ANAF) or dosar de executare (bailiff).
- Targets: specific IBANs or "toate conturile"; branch (unit).
- Payment destination: Treasury IBAN or the bailiff's consignment account.
- Attachments: title, încheiere de încuviințare.
- Legal basis cited.
- Precautionary vs executory flag.
- References to earlier addresses (for updates and lifting).

**Matching rules**
- e-Popriri XML gives structured fields. E-mail and paper popriri need OCR and extraction. These are the main automation gap: bailiffs plus every primărie/DITL acting as organ fiscal local (count of issuers not researched).
- The CNP or CUI should be the primary match key. Where it is missing (it is optional under CPC 783(3) "dacă sunt cunoscute"), fall back to name + address with mandatory human confirmation.

### Gaps
- The full current text of **OPANAF 63/2017 Annex 24** (the ANAF paper/IT form "Adresă de înființare a popririi asupra disponibilităților bănești") could not be retrieved, since it was published only in MO 32 bis. Its exact field list is therefore inferred, not quoted. Later orders amending Annex 24 were not checked.
- **XML schema** of e-Popriri messages: not public in the sources found.
- No official form for **bailiff** poprire addresses was found (e.g. a Ministry of Justice order or a UNEJ model). No UNEJ–ARB electronic garnishment channel was found either.
- No official channel was found for **local tax authorities** (DITL/DGITL). Their CPF form models (MDLPA/MF order) were not retrieved.
- Whether bailiffs' **direct API access to PatrimVen** has a formal legal basis (protocol or order) was not verified. It is reported only by a commentary.

---

## 3. Volumes and evidence of problems (customer harm, errors, manual effort) that justify automation

### Takeaway
ANAF alone generates hundreds of thousands of bank popriri a year, plus a larger number of follow-up acts:
- **645,631** poprire addresses in 2024;
- **~525,000** individuals garnished in 2025;
- **2.25 million** e-Popriri acts in H1 2025, of which more than 1.12 million were lifting documents.

Bailiffs add a comparable paper and e-mail stream. One large bank reported in 2019 about 250k bailiff popriri a year, against 418k from ANAF.

The documented harm is consistent across sources:
- the same debt blocked in several banks;
- protected income (salaries, pensions, child allowances) frozen until manually released;
- slow, manual lifting;
- identity and data errors;
- cumulative fees.

### Cited Findings

#### 3.1 Volumes
- **2024**: ANAF loaded **645,631** "Adrese de înființare a popririi" on e-Popriri between 01.01 and 31.12.2024 (ANAF reply to the publication). — [Wall-street.ro, 09.03.2025](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html)
- **2025**: ANAF set up popriri on bank funds and third-party sums for **525,000 individual taxpayers** between 01.01 and 31.12.2025. — [Factual.ro](https://www.factual.ro/declaratii/fals-anamaria-gavrila-sustine-ca-milioane-de-romani-au-popriri-pe-conturi/)
- **H1 2025**: **2.25 million** enforcement acts were sent to banks through e-Popriri, of which more than **1.12 million** ended existing popriri (ANAF report of 18.08.2025, as cited). Factual notes these are acts, not persons. — [Factual.ro](https://www.factual.ro/declaratii/fals-anamaria-gavrila-sustine-ca-milioane-de-romani-au-popriri-pe-conturi/)
- **2023 (claimed)**: the L40/2026 memorandum says ANAF issued "peste 2.500.000 de ordine de poprire", of which about **750,000** hit taxpayers with two or more active accounts. — [Senate memorandum](https://www.senat.ro/legis/PDF/2026/26L040EM.pdf)
  - Not independently confirmed. Factual shows a similar 2.5 million figure conflated acts with people.
- **Regional**: ANAF Brașov applied **11,487** bank popriri totalling **88,046,562 lei** to individuals in the first 9 months of 2023. — [ANAF DGRFP Brașov, 23.10.2023](https://static.anaf.ro/static/3/Brasov/20231023105828_comunicat_popriri_pf.pdf)
- **Per bank (2018 data, said in 2019)**, BRD CEO François Bloch:
  - **418,000** garnishment requests from ANAF in 2018;
  - about **250,000/year** from bailiffs;
  - **700,000** requests in total, with a figure of about **2.3 million** clients mentioned alongside. The article does not make clear how the two figures relate; 2.3 million may be BRD's total client base.
  - BRD said ANAF blocked about **one third** of the accounts opened at the bank.
  - — [Adevărul, 10.04.2019](https://adevarul.ro/economie/stiri-economice/avalansa-popririlor-milioane-conturi-blocate-anaf-pune-fiscul-poprire-conturile-debitorului-aceeasi-datorie-1_5caddb67445219c57e56305c/index.html)
- **Value**: ANAF performance reports put the value of garnished bank accounts at 3.8 billion lei (2017) and 4.0 billion lei (2016). (search summary, page not opened — [ANAF Raport de performanță 2017](https://static.anaf.ro/static/10/Anaf/Informatii_R/Raport_performanta_2017_26032018.pdf))
- **Revolut-held debtors**: by early 2025 ANAF's recovery requests via the Lithuanian authorities had grown from about 5 million lei (late 2022) to a figure the article prints inconsistently, most likely 624,660,795 lei. — [Wall-street.ro](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html)

#### 3.2 Customer harm and error patterns
- **Same debt blocked at several banks**
  - In 2019 ANAF's president told senators that the tax authority does not know account balances, so it sends notices to all banks.
  - Senators asked why a 10,000-lei debt froze 10 accounts of 30,000 lei each.
  - Two senators said their own accounts were blocked and that popriri were hard to lift.
  - — [Adevărul 2019](https://adevarul.ro/economie/stiri-economice/avalansa-popririlor-milioane-conturi-blocate-anaf-pune-fiscul-poprire-conturile-debitorului-aceeasi-datorie-1_5caddb67445219c57e56305c/index.html)
- The 2026 memorandum describes:
  - separate orders per account "chiar și pentru creanțe modice";
  - sums withheld above the debt;
  - **cumulative bank fees, including for accounts with no funds**;
  - lifting done "preponderent manual, cu întârziere";
  - good-faith payers whose popriri are not lifted automatically;
  - payments to the wrong budget IBAN treated as non-payment, leading to penalties and enforcement.
  - — [Senate memorandum L40/2026](https://www.senat.ro/legis/PDF/2026/26L040EM.pdf)
- **Protected income frozen**
  - Banks block at set-up without knowing the nature of the sums, and release unseizable sums only after analysing turnover. — [CES opinion](https://www.ces.ro/newlib/PDF/avize/2026/2.21-b674-Aviz-CES-30.12.2025.pdf)
  - A customer complained that her child allowance was held. BRD's spokesperson said that under popriri, allowance and salary sums "sunt eliberate clienților conform legii", but the account stays blocked if other sums come in. — [Reclamații Bănci, 2014](https://www.reclamatiibanci.ro/brd-mi-a-pus-poprire-pe-alocatiile-copiilor-au-voie-sa-faca-asta/)
  - Banks do not automatically know an account receives only allowances. Parents must prove the source of funds to the bank and the bailiff with a sworn statement, statements and the allowance decision. Banks usually require an official document from the bailiff, or a court decision, to lift. (search summary, page not opened — [Martor Incomod/Cuculis](https://www.martorincomod.ro/poprirea-alocatiei-copiilor-ce-prevede-legea-si-cum-pot-parintii-recupera-banii-explica-adrian-cuculis/); [Avocatnet](https://www.avocatnet.ro/articol_49074/S-a-pus-poprire-pe-aloca%C8%9Bia-copilului-pensia-de-intre%C8%9Binere-sau-indemniza%C8%9Bia-de-la-stat-Ce-i-de-f%C4%83cut.html))
- **Systemic error types** (commentary): — [juridice.ro 23.10.2026](https://www.juridice.ro/862896/interoperabilitatea-bazelor-de-date-in-procedura-popririi-electronice-de-la-automatizarea-interogarilor-la-riscul-erorilor-de-sistem.html)
  - **wrong debtor** (homonyms, CNP errors);
  - a natural person wrongly linked to a company's debts;
  - **protected income frozen** because banks do not tag the source of each credit (no "semantic interoperability"), e.g. a 3,000-lei balance made up of child allowances;
  - **lifting delays** of "days or weeks" because human validation is needed across bank, executor and ANAF;
  - over-securing across all accounts.
  - Quote: "Automatizarea nu elimină posibilitatea apariției erorilor, ci le amplifică viteza de propagare și aria de impact."
- **Debtor confusion**: some banks lift only on an ANAF address and reject proof of payment from another bank. — [Wall-street.ro](https://www.wall-street.ro/articol/Finante-Banci/314727/poprirea-contului-bancar-cati-romani-au-avut-conturile-executate-de-anaf-si-ce-trebuie-sa-stii-despre-procedura.html)

#### 3.3 Manual effort and operating cost
- BRD set up a **dedicated department of 20 staff** to manage popriri and notify clients, plus staff for digital client relations. — [Adevărul 2019](https://adevarul.ro/economie/stiri-economice/avalansa-popririlor-milioane-conturi-blocate-anaf-pune-fiscul-poprire-conturile-debitorului-aceeasi-datorie-1_5caddb67445219c57e56305c/index.html)
- Fees charged to customers (2019 data, likely outdated): Banca Transilvania 15 lei to set up a poprire; **Raiffeisen 2.5 lei for amounts up to 100 lei**. — [Adevărul 2019](https://adevarul.ro/economie/stiri-economice/avalansa-popririlor-milioane-conturi-blocate-anaf-pune-fiscul-poprire-conturile-debitorului-aceeasi-datorie-1_5caddb67445219c57e56305c/index.html)
- Banks "au investit masiv" in e-Popriri, with "resurse masive din punct de vedere operațional și IT". Banks still analyse turnover after each blocking to release unseizable sums. — [CES opinion](https://www.ces.ro/newlib/PDF/avize/2026/2.21-b674-Aviz-CES-30.12.2025.pdf)
- Non-ANAF popriri come in as e-mailed PDFs or paper packages that must be read, matched and answered individually. — [Revolut intake rules](https://cdn.revolut.com/terms_and_conditions/pdf/informa_ii_despre_popriri_b41776b9_1.0.0_1742987422_ro.pdf)

#### 3.4 Institutional positions
- **Against new legislation**: CES, BNR and the Government opposed L40/2026, saying the e-Popriri mechanism already works and further change would bring operational and legal risk. — [Senate file](https://www.senat.ro/legis/lista.aspx?nr_cls=L40&an_cls=2026); [CES](https://www.ces.ro/newlib/PDF/avize/2026/2.21-b674-Aviz-CES-30.12.2025.pdf)
- **For it**: the initiators describe the current practice as "executare silită abuzivă, ineficientă și inechitabilă". — [Senate memorandum](https://www.senat.ro/legis/PDF/2026/26L040EM.pdf)
- **Counter to inflated claims**: a claim of "2.5 million Romanians garnished in one year" was rated **FALSE** by Factual. — [Factual.ro](https://www.factual.ro/declaratii/fals-anamaria-gavrila-sustine-ca-milioane-de-romani-au-popriri-pe-conturi/)

### Inferences
**Automation targets suggested by the evidence**
- (1) Classify credits as protected or seizable at the moment of blocking, rather than after manual turnover analysis.
- (2) Extract data from bailiff and primărie PDF popriri and match them to customers.
- (3) Orchestrate lifting and updates.
- (4) Handle concurrency and ranking.

**Implied cycle volume**
- Follow-up acts dominate e-Popriri traffic. Half of the 2.25 million acts in H1 2025 were lifting documents, and the remainder includes amount updates and suspensions as well as set-ups.
- Every set-up therefore generates several downstream acts that must be processed. An exact ratio cannot be derived, because the 2024 figure (645,631 set-up addresses) and the H1 2025 figure (all acts) measure different things and different periods.

**Raiffeisen-level volume (assumption)**
- No Raiffeisen-specific figure was found. If Raiffeisen's share of retail accounts is roughly comparable to the large banks' 10–15%, one would expect on the order of 60–100k ANAF poprire addresses a year, plus a bailiff stream.
- This is an assumption to be confirmed with the bank.

### Gaps
- No complaint statistics were found from **ANPC, CSALB, BNR or Avocatul Poporului** on popriri or protected income. The search budget was exhausted.
- No figures for **bailiff popriri** nationally (UNEJ statistics) or for **local tax authorities' popriri**.
- No Raiffeisen-specific poprire volumes, FTE counts or error rates.
- Not verified: the ECHR case "Iorga și alții c. România (2015)" cited in the L40/2026 memorandum.

---

## 4. Information requests from courts, prosecutors, police, ANAF, bailiffs and notaries: legal basis, deadlines, banking secrecy

### Takeaway
Banking secrecy (OUG 99/2006 art. 111) yields only in listed cases (art. 113(2), 114). Each requester has its own legal basis and form:
- **bailiffs**: CPC art. 660, "de îndată". OUG 99 art. 113(2)(f) speaks only of the "existence of accounts".
- **prosecutors**: CPP art. 153, by **ordonanță**, "de îndată", confidential. Police must go through the prosecutor.
- **courts**: OUG 99 art. 113(2)(e), 114.
- **ANAF**: CPF art. 61, all turnover and balances, plus daily account reporting. Other fiscal bodies: CPF art. 58, written request.
- **notaries** in a succession: art. 113(2)(g).
- **heirs**: art. 113(2)(a).

Written requests under art. 113(2)(c) must state the legal basis, the client's identity, the category of information and the purpose.

### Cited Findings
- **Scope of secrecy**: the bank must keep confidential all facts, data and information about clients' persons, property, business and accounts (balances, turnover, operations), services and contracts. The duty extends to **former** clients and to prospects with whom a transaction was negotiated. — [OUG 99/2006 art. 111(1)–(2)](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- Staff confidentiality: during employment and after. — [OUG 99/2006 art. 112](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- **Exceptions**: secrecy cannot be opposed to supervisory authorities, art. 113(1). Under art. 113(2), information may be provided "în măsura în care [este] justificată de scopul pentru care [este] cerută", in these cases: — [OUG 99/2006 art. 113](https://legislatie.just.ro/Public/DetaliiDocument/166384)
  - (a) at the request of the account holder **or their heirs**, including legal or statutory representatives, or with their express consent;
  - (b) where the bank justifies a legitimate interest;
  - (c) on the written request of other authorities, or ex officio, **if a special law entitles them** and **clearly identifies the information** that may be provided;
  - (d) on the written request of the **spouse** who proves a court claim for division of common property, or at the court's request;
  - (e) at the request of the **court** to resolve cases;
  - (f) at the request of the **executor judecătoresc**, for enforcement, "**pentru existența conturilor debitorilor urmăriți**" (as amended by OUG 113/2013);
  - (g) at the request of the **notary in the notarial succession procedure** (added by Legea 71/2011).
- Required content of a written request under art. 113(2)(c): "**temeiul legal** al solicitării de informații, **identitatea clientului** …, **categoria informațiilor** solicitate și **scopul**". — [OUG 99/2006 art. 113(3)](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- **Prosecutor and court**: banks must provide secrecy-covered information on their request, and the CPP provisions on special surveillance or investigation methods apply accordingly. — [OUG 99/2006 art. 114 (as amended by Legea 255/2013)](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- Not a breach of secrecy: aggregated data; data to the Centrala Riscurilor Bancare, the Centrala Incidentelor de Plăți and the deposit guarantee fund; the bank's auditor; correspondent banks for correspondent-account operations; group entities for consolidated supervision and AML; CRB data returned to banks. — [art. 115](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- Recipients must keep the information confidential and use it only for the stated purpose. — [art. 116](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- **Bailiffs**: — [CPC art. 660](https://legislatie.just.ro/Public/DetaliiDocument/140271)
  - On request, anyone who owes money to the debtor or holds the debtor's assets must disclose in writing everything needed for enforcement: the extent of its obligations, prior seizures, assignments and similar. — art. 660(1)
  - "**instituțiile publice, instituțiile de credit** și orice alte persoane … sunt obligate să îi comunice, **de îndată**, în copie, documentele, precum și, în scris, datele și informațiile apreciate de executorul judecătoresc ca fiind necesare …, **inclusiv codul numeric personal** …, **chiar dacă prin legi speciale se dispune altfel**". — art. 660(2)
  - Fiscal bodies must also provide the data they administer. — art. 660(2)
  - On request, the court may impose judicial fines (art. 187(1) pct. 2 lit. f) and damages (art. 189). — art. 660(1)–(2)
  - The bailiff must keep the information secret and may not use it for other purposes or build personal databases. — art. 660(4)
- **Prosecutors and police**: — [CPP art. 153](https://legislatie.just.ro/Public/DetaliiDocument/120611)
  - The **prosecutor** may ask a credit institution for "datele privind existența și conținutul conturilor unei persoane" where there are strong indications of an offence and the data may be evidence. — art. 153(1)
  - The measure is ordered **ex officio or at the request of the criminal investigation body (police)**, by an **ordonanță**. Besides the art. 286(2) mentions, it must state: the institution holding the data, the suspect's or defendant's name, the reasons the conditions are met, and the institution's duty to communicate **immediately and confidentially**. — art. 153(2)
  - The institution must provide the data "**de îndată**". — art. 153(3)
  - More generally, criminal investigation bodies or the court may order any person to hand over objects, documents or computer data. — [CPP art. 170](https://legislatie.just.ro/Public/DetaliiDocument/120611)
- **ANAF** — [CPF art. 61](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - On the central fiscal body's request, banks, payment institutions and e-money institutions must communicate for each holder "**toate rulajele și/sau soldurile**" and the information and documents on operations. — art. 61(1)
  - They must report **daily**: holders who open or close accounts, signatories, persons acting for the client, beneficial owners (Legea 129/2019 art. 15 data), IBAN, opening and closing dates, and safe-deposit box renters. — art. 61(2)
  - Retention: 10 years. Procedure: ANAF order. — art. 61(5)–(6)
  - Non-compliance is a contravention under art. 336(1)(i), fined under art. 336(2)(d): **1,000–5,000 lei** for medium and large taxpayers. — [CPF art. 336](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **Any fiscal body, including local**: the fiscal body may request information from persons who have or had economic or legal relations with the taxpayer, and they must provide it. The request is **written** and must specify the nature of the information and supporting documents. — [CPF art. 58(1)–(2)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
  - Local fiscal bodies may obtain other fiscally relevant information from ANAF electronically. — [CPF art. 60(7)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)
- **FATCA/CRS** documentation must be provided within 45 days of an ANAF request. — [CPF art. 62(12)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

### Inferences
**Validation rules for an incoming information request (derived)**
- **REQ-01 Identify the requester type and legal basis.** Reject or escalate if the basis is missing. Art. 113(3) requires the legal basis, client identity, category of information and purpose for 113(2)(c) requests.
- **REQ-02 Prosecutor and police**
  - Require a **prosecutor's ordonanță** naming the bank, the suspect or defendant, the reasons, and the confidentiality and immediacy duty (CPP 153(2)).
  - A police letter without a prosecutor's ordonanță → exception, unless it is an art. 170 order.
  - SLA = "de îndată". Tipping-off the client must be blocked (confidentiality).
- **REQ-03 Bailiff**
  - SLA "de îndată" (CPC 660(2)). Scope as considered necessary by the bailiff.
  - **Conflict flag**: OUG 99 art. 113(2)(f) limits disclosure to the "existence of accounts", while CPC 660(2) overrides special laws. Each bank needs a legal-policy decision on how much it discloses (balances, statements). → configurable policy plus escalation.
- **REQ-04 ANAF (central)**: art. 61(1) covers balances, turnover and documents per holder. Local tax bodies fall under art. 58, which is general.
  - **Conflict flag**: art. 113(2)(c) requires the special law to "clearly identify" the information; art. 58 does not list bank data specifically. → legal review for local-authority requests beyond balances.
- **REQ-05 Notary**: only within a succession procedure (113(2)(g)). Require the case reference and proof of death. Heirs: art. 113(2)(a), with proof of heir status.
- **REQ-06 Courts**: civil cases under 113(2)(e); criminal under 114 + CPP. Spouse: only with proof of a filed partition claim (113(2)(d)).

**Deadlines to encode**
- "de îndată": CPC 660(2), CPP 153(3);
- 5 days: CPF 236(10), "no sums owed" notice for popriri;
- 45 days: CRS/FATCA;
- no explicit deadline in CPF art. 61(1); set by ANAF procedure (not verified).

### Gaps
- **AML**: ONPCSB requests and transaction-suspension duties under Legea 129/2019, and their deadlines, were not researched (out of budget).
- The ANAF procedure order under CPF art. 61(6), with formats and deadlines for answering art. 61(1) requests, was not retrieved.
- **CPP art. 153 version**: the downloaded consolidated page shows no requirement for prior approval by the judecător de drepturi și libertăți. I could not confirm whether later amendments or CCR decisions added one. Verify before encoding.
- No volume data on information requests received by banks.
- The CPC civil-procedure rules on courts ordering documents from third parties (art. 293–298) were not extracted.

---

## 5. Inheritance (succesiuni / moșteniri), deceased clients' accounts and cards, and notarised powers of attorney (procuri) including RNNEPR

### Takeaway
- **Heir status and quotas**: proved by the notary's **certificat de moștenitor**, which evidences heir status and the property right in the estate in each heir's quota. A court decision can replace it. Vacant estates go to the commune, town or municipality (UAT).
- **Effect of death on mandates**: death ends every mandate and procura (Codul civil art. 2.030(c), 1.307). Third parties who neither knew nor should have known are protected.
- **Bank practice**: block on notice of death; release by quotas against the certificate, the death certificate, the heirs' IDs and all heirs' signatures or express consent. Minors need the guardianship rules.
- **Revocations of notarised procuri**: recorded in **RNNEPR**, which **only notaries can query** (Codul civil art. 2.033). Banks therefore cannot verify revocation directly.

### Cited Findings

#### 5.1 Succession documents and their effects
- The **certificat de moștenitor** is issued by the notary and contains findings on the estate, the number and status of the heirs and their quotas. — [Codul civil art. 1.132](https://legislatie.just.ro/Public/DetaliiDocument/175630)
  - It "face dovada calității de moștenitor, legal sau testamentar, precum și dovada dreptului de proprietate al moștenitorilor acceptanți asupra bunurilor din masa succesorală, în cota care se cuvine fiecăruia". The notary first liquidates the matrimonial regime. — [art. 1.133](https://legislatie.just.ro/Public/DetaliiDocument/175630)
  - Persons harmed may ask the court to annul it. — [art. 1.134](https://legislatie.just.ro/Public/DetaliiDocument/175630)
  - An action for absolute nullity of the certificate is **imprescriptible** where it concerns the estate's composition or partition (subject to acceptance in time). — [art. 2.502(2) pct. 4](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- The **succession option** must be exercised within **one year** of the opening of the succession, with special start dates. — [Codul civil art. 1.103](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **Vacant estate**: if there are no legal or testamentary heirs, the estate is vacant. It goes to the commune, town or municipality where the assets were located, into its private domain. Liability for estate debts is limited to the value of the assets. — [Codul civil art. 1.135, 1.138, 1.139](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **Banking secrecy is lifted**:
  - at the request of the account holder's **heirs**, art. 113(2)(a);
  - at the request of the **notary in the notarial succession procedure**, art. 113(2)(g).
  - — [OUG 99/2006 art. 113(2)](https://legislatie.just.ro/Public/DetaliiDocument/166384)
- In e-Popriri, a bank answers a poprire on a deceased client with reason code **4 "debitor decedat/radiat"**. — [OPANAF 878/2022 pct. 2.5, Annex 4](https://static.anaf.ro/static/10/Anaf/legislatie/OPANAF_878_2022.pdf)

#### 5.2 Death of the client: proxies, account handling
- A mandate ends on "moartea, incapacitatea sau falimentul mandantului ori a mandatarului". The exception is ongoing activity of a continuous character. — [Codul civil art. 2.030(c)](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- The power of representation ends on the death of the representative or the represented person, unless the agreement or the nature of the business implies otherwise, art. 1.307(1). **Termination has no effect on third parties who, at contracting, neither knew nor should have known of it**, art. 1.307(4). — [Codul civil art. 1.307](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- On death, the heirs or representatives must **inform the other party immediately**. The mandatary must continue if delay would endanger the principal's or heirs' interests. — [Codul civil art. 2.035](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **Bank practice** (legal blog, 03.09.2026): — [Lexeto](https://www.lexeto.ro/conturi-bancare-succesiune-deblocare/)
  - Accounts are **blocked once the bank learns of the death**. Pensions, rent or interest may still be credited.
  - Withdrawals after death, including by a former proxy, must be returned to the estate even if the bank did not yet know.
  - Banks generally do not disclose account data to heirs before the procedure ends. The notary can request it.
  - Documents usually required: certificat de moștenitor, death certificate, the heirs' IDs, a release request signed by **all heirs or their representative**, account documents.
  - Funds are released by the quotas in the certificate, or to one heir if the others **expressly consent**. A joint account does not automatically pass to the survivor.
  - Overdrafts and loans become estate liabilities.

#### 5.3 Minors and incapacitated heirs
- Parents administer the child's property and represent the child, or approve the child's acts. **From age 14 the minor acts alone with parental approval and, where required, the guardianship court's (instanța de tutelă).** — [Codul civil art. 501](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- Parents' rights over the child's property are **the same as a guardian's**. — [art. 502(1)](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- Acts beyond administration (alienation, partition, renouncing patrimonial rights) need **the opinion of the consiliul de familie and the instanța de tutelă's authorisation**. Acts in breach can be annulled. — [Codul civil art. 144(2)–(3)](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- Minors aged 14 or over need written approval, plus court authorisation for the same acts. — [art. 146](https://legislatie.just.ro/Public/DetaliiDocument/175630)

#### 5.4 Powers of attorney (procuri)
- **Form**: a mandate may be written (authentic or private) or oral. But a mandate to conclude an act that must take a certain form **must take that form**. — [Codul civil art. 2.013](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **Scope**: a general mandate covers only conservation and administration acts. **Acts of disposal**, alienation, encumbrance, settlements, bills of exchange or promissory notes, and court actions require **express** authorisation. — [Codul civil art. 2.016](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **Revocation**: the principal may revoke at any time, expressly or tacitly, even a mandate stated to be irrevocable, art. 2.031(1). A new mandate for the same business revokes the old one, art. 2.031(2). — [Codul civil art. 2.031](https://legislatie.just.ro/Public/DetaliiDocument/175630)
  - Changes and revocation must be brought to third parties' knowledge, or they are not opposable unless the third party knew or could have known. — [Codul civil art. 1.306](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- **RNNEPR** — [Codul civil art. 2.033](https://legislatie.just.ro/Public/DetaliiDocument/175630)
  - The notary who authenticates the **revocation** of an authentic procura must send it "de îndată" to the **Registrul național notarial**, kept electronically. — art. 2.033(1)
  - The notary who authenticates **the act for which a procura was given** must check in that register whether it was revoked. — art. 2.033(2)
  - The same applies to Romanian consulates. — art. 2.033(3)
- **RNNEPR access**: it is the Registrul Național Notarial de Evidență a Procurilor și a Revocărilor acestora, administered by **CNARNN** and reached through the **Infonot** platform.
  - "Orice interogare poate fi realizată **exclusiv de un notar public**", at the interested person's request. "Persoanele fizice sau juridice nu pot accesa direct RNNEPR". Banks are not mentioned.
  - A query generates an electronic certificate with the result and the date, hour and minute.
  - — [Legal Badger, 13.03.2025](https://legalbadger.org/stiri/administratie/cum-poti-verifica-rapid-o-procura-sau-un-mandat-in-sistemul-rnnepr/)
  - Procuri used in notarial acts are checked in RNNEPR on the day of authentication for existence, authenticity and non-revocation. (search summary, page not opened — [Lege5, Regulament proceduri notariale](https://lege5.ro/Gratuit/gm3tgmbzgm/procedura-actelor-notariale-regulament?dp=gy2tgmrrgy3dq))

#### 5.5 Delays and complaints
- The release timeline depends on the succession procedure followed by the bank's own deadlines. The article gives no typical day counts. — [Lexeto](https://www.lexeto.ro/conturi-bancare-succesiune-deblocare/)
- Forum reports say some banks (e.g. CEC) require the certificate to **expressly mention bank funds**, forcing heirs to obtain a **certificat suplimentar**. Notaries are said not to be obliged to search all banks for the deceased's accounts; heirs must name the bank. (search summary, page not opened — [Avocatnet forum](https://www.avocatnet.ro/forum/discutie_434375/Atestare-a-calitatii-de-mostenitor.html))
- Paying **funeral costs** from the deceased's account: practice varies by bank and there is no general rule. (search summary, pages not opened — [Observatorul Prahovean](https://www.observatorulph.ro/national/2795661-cine-poate-retrage-banii-din-contul-unei-persoane-decedate-ce-spune-legea-si-ce-acte-sunt-necesare); [Capital](https://www.capital.ro/banca-blocheaza-accesul-la-banii-din-cont-situatia-in-care-nu-se-poate-retrage-cash-documentul-care-trebuie-prezentat.html))
  - Funeral costs do rank second among creditors' claims in enforcement distribution. — [CPC art. 865(1)(b)](https://legislatie.just.ro/Public/DetaliiDocument/140271); [CPF art. 258(1)(b)](https://legislatie.just.ro/Public/FormaPrintabila/00000G0YZX4HQ2NBF771PRKG2U2WS61K)

### Inferences
**Draft rule set: deceased client and inheritance (derived)**
- **DEC-01 Death notice**
  - Inputs: death certificate (certificat de deces), a notary letter, or a death flag on a poprire.
  - Verify CNP match. Set the "deceased" flag with the date of death.
  - Block debit operations and cards. Revoke all mandates and împuterniciri (CC 2.030(c), 1.307(1)).
  - Flag transactions after the date of death for review: possible return to the estate (Lexeto) and good-faith protection (CC 1.307(4)).
- **DEC-02 Incoming credits after death**: pensions, salaries, allowances. Flag them for possible return to the payer. The exact rule (e.g. Legea 360/2023) is unverified; see Gaps.
- **DEC-03 Popriri on a deceased debtor**: answer e-Popriri with reason code 4. For bailiffs, reply in writing and flag for legal review.
- **DEC-04 Heir release**
  - Require a certificat de moștenitor (original or legalised copy), a court decision, or a certificat de vacanță succesorală (pays the UAT, CC 1.138).
  - Extract: deceased identity, issuing notary office, certificate number and date, heirs with quotas, whether assets/bank funds are listed.
  - Check every heir's ID. Require all heirs' signatures, special procuri, or express consent for payment to one heir.
  - Minors or protected persons: parent or guardian. Disposal acts need instanța de tutelă authorisation (CC 144, 146, 502). Escalate if missing.
  - Compute payout = balance × quota. Escalate any discrepancy.
- **DEC-05 Information to notary or heirs**: allowed under OUG 99 art. 113(2)(g) and (a). The notary request must reference the succession file.
- **PROC-01 Procura check**
  - Identify the type: authentic or private; general or special.
  - For disposal acts (withdrawal, transfer, closure, credit), require express powers (CC 2.016(2)). Banks typically require an authentic form (bank policy; no legal source found).
  - Check validity dates and scope wording, and the principal's and mandatary's IDs.
  - Check the principal is not deceased (internal flag).
  - **Revocation check**: banks cannot query RNNEPR directly. Options are to require a recent notary verification certificate, or to call the issuing notary office. Otherwise escalate.
  - Foreign procuri: apostille or translation requirements (not verified here).

### Gaps
- Exact current article numbers of **Legea 36/1995** (republished 2018) for:
  - the succession procedure;
  - the "**certificat de calitate de moștenitor**" (what it proves; whether banks accept it for releasing funds);
  - "certificat de legatar" and "certificat suplimentar";
  - RNNEPS (succession register).
  - Not retrieved; the notari.pro copy shows an outdated 2013 republication.
- The **European Certificate of Succession** (Reg. (EU) 650/2012) could not be fetched; EUR-Lex blocked automated access.
  - From general knowledge, not verified this session: art. 62–73 govern the certificate; art. 69 presumes accuracy and protects persons paying to the person named; art. 70 says certified copies are valid 6 months.
  - Verify before encoding.
- No legal rule was confirmed for **paying funeral expenses** from a deceased client's account. Secondary sources conflict.
- Return of **pensions credited after death**: secondary sources mention Legea 360/2023 and a 30-day bank restitution term. Not verified. (search summary, page not opened — [Capital](https://www.capital.ro/pensie-2026-casa-de-pensii-poate-cere-inapoi-banii-in-aceste-cazuri-ce-trebuie-sa-stie-toti-pensionarii.html))
- No statistics on inheritance files, delays or complaints at banks; no data on procura fraud or revocation incidents.
- Whether banks may obtain **Infonot/RNNEPR access** through a protocol with UNNPR/CNARNN: not found.

---

## 6. Dormant / inactive accounts (relevance to the above)

### Takeaway
No Romanian statute on dormant accounts or unclaimed assets was found in this session, because the search budget ran out. The only related rules confirmed:
- a deceased client's funds pass to heirs or, if there are none, to the UAT (Codul civil art. 1.135–1.139);
- the bank must keep informing the client about account operations (art. 2.191(3)).

### Cited Findings
- On a fund deposit, the credit institution becomes owner of the sums. It must return the same amount at term or on demand, and must inform the client free of charge (monthly by default) of account operations. — [Codul civil art. 2.191](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- Vacant estates, including bank balances of a deceased with no heirs, go to the commune, town or municipality. — [Codul civil art. 1.135, 1.138–1.139](https://legislatie.just.ro/Public/DetaliiDocument/175630)
- Restitution of bank deposits is **not** among the imprescriptible actions listed in art. 2.502(2). — [Codul civil art. 2.502](https://legislatie.just.ro/Public/DetaliiDocument/175630)

### Inferences
- For the agent, "dormant" matters mainly as a trigger to check for a possible unreported death (e.g. a long-inactive account receiving no pension), and as context for e-Popriri reason codes 3 ("cont închis") and 4.
- No legal duty to transfer dormant balances to the state was identified.

### Gaps
- Not researched (search budget exhausted):
  - any Romanian rule or BNR guidance on inactive accounts or their fees;
  - closure of basic payment accounts after inactivity (Legea 258/2017, transposing Directive 2014/92/EU);
  - prescription of deposit-restitution claims.
- No data on the volume of dormant balances.
