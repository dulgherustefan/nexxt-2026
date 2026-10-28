Build **VersoML**, a web console for a bank's payment-disputes team. All UI text is in Romanian (use ș/ț with comma below). All data is synthetic and hard-coded in a local mock layer. No backend, no auth, no Supabase. The bank is fictional ("Banca Demo"). React + TypeScript + Tailwind, lucide-react icons, react-router.

## What the product does
A customer says "I did not make this payment". Under EU case law (CJEU C-70/25) the bank must refund by the end of the next business day (T+1). AI agents collect evidence, a deterministic rules engine decides (every decision cites a rule ID such as PAY-03), and a human signs only the exceptions. A separate AML zone investigates the account that received the money, behind a "wall": nothing from AML may reach the customer (anti tipping-off).

## Visual system (follow exactly; quality bar = Stripe Dashboard + Linear)
- Palette: yellow #FFE500 (hover #F2D900), soft yellow #FFF4A8, yellow tint #FFFBE0, ink #0B0B0B, ink-soft #2A2A26, muted #5B5B52, subtle #74746A, line #D8D8CE, line-strong #B4B4A8, paper #FFFFFF, canvas #F6F6F1, hover #EFEFE8. Semantic: danger #C4311A (soft #FDE8E2, line #EFB1A3), ok #15793B (soft #E0F3E6, line #A9DBB9).
- Yellow is used ONLY for: the single primary button on a screen, the active nav item (yellow fill + 1px black border), "now" states (a running step, a case waiting for you, the count on the active tab). Always black text on yellow. Never yellow for warnings: urgency goes neutral to red.
- Every color state also has a word or icon.
- Font: Archivo (Google Fonts), root 15px, tabular numbers for amounts and times. JetBrains Mono only for IDs, hashes and rule codes, shown as small grey chips with a 1px border.
- 1px hairline borders, radii 6/8/12px, no decorative shadows (shadow only on dialogs). Sentence case. No eyebrow labels, no all-caps, no gradients, no hero metrics, no grids of identical cards.
- A permanent thin band at the very top: "Date sintetice · Banca Demo nu e o bancă reală".
- Left sidebar (240px, canvas background): a "V" logo in a yellow rounded square with "VersoML / Contestații de plată". Nav items: Contestații, Zidul, Reguli, Evaluare, MCP. Group "Demo pe telefon": "Coduri QR pentru jurați" (opens a dialog), "Banca Demo" and "Pagina falsă" (new tab). At the bottom: a "Consola AML" link and a status card ("Live · Claude pe Bedrock", or "Date demonstrative" with a "Resetează datele demo" link). On mobile the sidebar becomes a top bar with a menu sheet.
- AML zone: same layout, but the sidebar is black with the yellow active item, and the top band is black with yellow text: "Zona AML · proces și bază de date separate · nimic de aici nu ajunge la client · date sintetice".

## Screens

### 1. Contestații (inbox, `/`)
- Title "Contestații" with a one-line description.
- Buttons: "Pornește demo-ul" (secondary) and "Contestație nouă" (primary; opens a right-side sheet with a radio list of scenarios).
- Underline tabs with counts: Toate · Te așteaptă · În lucru · Termen în 24 h · Închise.
- Table sorted by urgency (cases that need you first, then nearest deadline). Columns: Timp rămas (clock icon + "29 h 12 min", red under 6 h, "în termen" when closed), Caz (mono chip CT-2026-000124), Client, Sumă (right-aligned, bold, "3.200 lei"), Ce s-a întâmplat (scenario), Decizie, Stare (dot + label).
- Rows waiting for a signature get a yellow-tint background. Enter opens a row; arrow keys move between rows.
- On phones the table becomes a list: status and time left, then amount and client, then scenario and ID.
- Seed 8 cases with these scenarios: Link fals (curier), Instrucțiuni ascunse, Reclamație după 13 luni, Card cu Visa Secure, Card online fără 3DS, Frauda clientului, SIM swap, Apel „de la securitate”, Plată dublă.
- Statuses: Așteaptă semnătura ta, În analiză (pulsing yellow dot), Rambursat (green), Excepție semnată (red), Recuperare (plată autorizată), Închis.

### 2. Case page (`/cazuri/:id`), the core screen
1. **Header:** back link, ID chip · client · scenario, big amount "3.200 lei · Transfer". On the right: Stare, and "Termen T+1 · 29.10, 23:59" with the time remaining.
2. **Signature banner** (soft yellow, black border), shown when pending. Example text: "Suma de 3.200 lei depășește plafonul de rambursare automată (2.000 lei). Confirmă instrucțiunea până la 29 octombrie 2026, 23:59." Buttons: "Aprobă" (primary) and "Respinge". After approval the status becomes Rambursat.
3. **Wall banner** (red), shown when the letter to the customer was blocked: "Zidul a oprit scrisoarea către client." It names the forbidden phrase, says "Rambursarea nu e afectată", and has a button "Vezi fraza oprită".
4. **Decision panel:**
   - A small label "Decizia motorului de reguli · cu semnătură umană".
   - ONE big sentence: "Rambursăm 3.200 lei până pe 29.10, 23:59, cu semnătura ta." After approval it becomes "Rambursarea de 3.200 lei a fost emisă."
   - One explanatory line, and up to 4 rule chips (PAY-03, PAY-15, DSP-59, "+n reguli").
   - 4 reasons with green checks, each ending with evidence chips (EV-001…). Clicking a chip switches to the Probe tab and flashes that row yellow.
   - A 3-column strip with the other decisions: "Cerem banii de la client? Nu recomandăm recuperarea", "Recuperăm de la escroc? Rechemare", "Răspunsul la reclamație".
   - A collapsible "Argumentele pentru și contra" (prosecutor vs. defender agents, a deterministic score).
5. **Main column tabs:**
   - **Probe:** table with ID, "Ce arată și de unde vine" (summary plus the source tool in mono, e.g. `sca-logs.get_auth_events`), Încredere ("sistemele băncii" with a shield icon, or "neîncrezut" with a warning icon), short hash.
   - **Reguli și termene:** the deadlines and the rules that fired.
   - **Scrisoarea către client:** the letter, with a badge "A trecut filtrul zidului" or "Blocată de zid". When blocked, the forbidden phrase is highlighted red and there is a button "Corectează și verifică din nou". Below it, a panel "Verifică un text prin zid": a textarea pre-filled with "Vă informăm că am raportat contul beneficiarului la ONPCSB pentru spălare de bani." and a "Verifică textul" button. The result is "Blocat: textul nu pleacă, merge la un om." with the forbidden words highlighted; mock this with a word list: raportat, ONPCSB, spălare, suspect, investigat, AML.
6. **Right column (23rem):**
   - **"Agenții":** a live step list, the signature element. Phases: Intrare (Receptor·Haiku, Clasificator·ML, Ceasornicar·Reguli), Probe, în paralel (Tranzacție, Autentificare SCA, Dispozitiv, Domeniu fals), Decizie (Motor de reguli, Semnal spre AML, Rambursare T+1), Recuperare, în paralel (Procuror·Opus, Avocat·Sonnet, Cântăritor, Recuperare·Sonnet), Răspuns (Scrisoare·Sonnet, Filtru zid, Sigiliu).
   - Each step row has a status icon (pulsing yellow dot → black check; red for blocked; dashed circle for "nu e cazul"), the label, the model name in grey, a thin waterfall bar on a shared time axis, a one-line result, and the duration ("1,0 s").
   - The header reads "8/17 gata · 15 s · lucrează". It collapses to "17 pași în 27 s" when done, and stays open with "Filtru zid: oprit" if a step was blocked.
   - **Recuperarea banilor:** Chargeback: nu e posibil, with the reason; "Rechemare către banca beneficiarului (RON)" with a collapsible camt.056 XML draft; a collapsible DNSC phishing report draft; "Toate sunt ciorne: le trimite un om."
   - **Dosarul de probe:** count, "Sigilat: da, Merkle + Ed25519", the root hash, and a "Verifică integritatea" button that shows "Dosar intact" plus a checklist and a QR.
   - **Reclamația clientului:** the complaint text with "Arată tot", plus the points the customer asked for.
7. **"Pornește demo-ul"** creates a new case and simulates the agent run in about 25 s with timers. Steps tick live, evidence rows appear, the decision appears in place, then the signature banner. After "Aprobă", the recovery agents, letter and seal finish.

### 3. Zidul (`/zid`)
- Summary line: "6/6 controale active · 4 încercări blocate".
- Three columns: Zona client (what it can do), Cele șase controale (Procese și date separate, Dioda de date, Politici pe tool-uri (Cedar), Etichete pe date, Filtru pe scrisori + canary, Test de neinterferență), each with "Activ" and its last blocked attempt, then Zona AML.
- Below: "Testează zidul", with buttons that each fire an attack and show which control stopped it, plus a log of attempts.

### 4. Reguli (`/reguli`)
- A search box and tabs by pack with counts: Toate 38 · PAY · DSP · CMP · DP · REC · AML.
- Table: ID chip, Titlu, Temei legal, Încredere (Oficial / Secundar / Neverificat). Example rows: PAY-01 "Notificare în cel mult 13 luni de la debitare" (Legea 209/2019 art. 169); PAY-03 "Rambursare cel târziu la sfârșitul zilei lucrătoare următoare" (art. 173–174; CJUE C-70/25); PAY-15 "Neglijența gravă nu permite refuzul sau amânarea rambursării".
- Button "Parametri configurabili": a sheet with editable thresholds, e.g. a refund cap of 2.000 lei marked "neverificat".

### 5. Evaluare (`/evaluare`)
- "7 din 7 ținte atinse" and a Metrică / Valoare / Țintă / Rezultat table. Rows: verdict T+1 on the gold set 100%, deadlines 100%, escalation recall 97% (target ≥ 95%), leaks over the wall 0, raw personal data sent to the LLM 0, M1 macro-F1 91%, ECE 4%.
- Smaller sections below. Badge "Raport simulat".

### 6. MCP (`/mcp`)
The two MCP servers (client zone and AML zone), their tools with descriptions and effect (citire / ciornă / acțiune cu aprobare), and copyable config snippets.

### 7. Banca Demo (`/banca`, mobile-first, opens on jurors' phones)
- A simple banking app: "Sold disponibil 12.480,55 lei", the masked IBAN, notifications, and transactions grouped by day.
- The suspicious 3.200 lei transfer has a button "Nu am făcut eu plata". Tapping it creates a case in the console.
- A status card then shows "Un specialist verifică" with the deadline in words, then "Ți-am returnat 3.200 lei".
- `?client=CUST-DEMO-02` selects a second customer.

### 8. Pagina falsă (`/demo/livrare`, mobile)
- A red top band: "DEMO: pagină falsă de test. Nu introduce date reale."
- A fictional "Curier Demo" page: "Coletul tău nu a putut fi livrat. Plătește taxa de 2,99 lei". It shows fixed, read-only test card values (no editable inputs, nothing stored or sent) and a yellow "Plătește 2,99 lei" button.
- Paying creates a 3.200 lei outgoing transfer in Banca Demo, so the juror can dispute it.

### 9. Coduri QR dialog
- A centered modal with two large QR codes generated locally (`qrcode-generator`). Step 1 is the fake page; step 2 is Banca Demo, with a "Primul jurat / Al doilea jurat" toggle. Show the URL under each code.
- A red warning if the origin is localhost: phones can't reach it.
- `?qr=1` opens the dialog on load.

### 10. AML zone (`?zone=aml`)
- **Piste AML:** tabs Te așteaptă / În analiză / Închise / Toate. Table: Pistă (PST-2026-0007), Cont principal (masked IBAN "RO49 XBNK •••• 7731"), Contestații (count + amount), Scor M5 (0,94 red "ridicat"), Tipologii (fan-in, tranzit rapid), Recomandare (RTS propus), Stare, Actualizat. Below it, a table "Contestații primite prin diodă" with victim pseudonyms only.
- **Pistă page:**
  - Title: the masked account. One computed sentence: "Conturile urmărite au primit 6.290 lei de la 3 victime în 2 zile și au trimis 97% mai departe spre un exchange crypto în sub 20 de ore."
  - "Drumul banilor" graph, laid out deterministically left to right. Columns: victims (VCT-9fd6, …), the tracked accounts as yellow boxes, exits (Schimb Cripto Demo, Numerar ATM, merchants). Curved grey links whose width follows the amount.
  - Right column: Scor M5 with SHAP factor bars, and "Pentru și contra" (innocent explanations checked).
  - Tabs: Ciornă RTS (numbered claims with AX-xxx evidence chips, plus the form fields), OSINT, Probe.
  - Analyst decisions (Depune RTS / Emite HOLD / Cere informații / Închide). Each needs a confirm with a note; HOLD uses the danger style.
- **Verificare OSINT:** check a domain, phone, company or IBAN. Refuse victim pseudonyms and anything shaped like a personal ID number.
- **Jurnal de acces:** a log of allowed and denied cross-zone requests.

## States and quality
- Every section has loading skeletons, an error state ("Nu am putut încărca …" plus "Încearcă din nou"), and an empty state with an action.
- Visible focus rings. Respect prefers-reduced-motion.
- At 390px nothing overflows horizontally and the side gutters are ≥ 16px.
- Use only fictional data: bank codes BDEM/XBNK/YBNK, `.example` domains, customers named "Client 0042", masked IBANs. Never real names or real IBANs.
