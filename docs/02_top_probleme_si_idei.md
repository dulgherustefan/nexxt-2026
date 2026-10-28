# Top probleme reale și idei de agent AI

**Raiffeisen Bank România · NEXXT Summit 2026 · track „AI for Operational Efficiency"**

Stare: research încheiat pe 6 direcții, plus 3 verificări în Perplexity (28.10.2026). MVP-ul **nu e ales**; documentul servește alegerii. Ce e marcat *(de verificat)* are o singură sursă sau surse în conflict.

## Pe scurt

- **Durerea cea mai bine documentată la Raiffeisen: contestațiile la tranzacții cu cardul și fraudele.** Raportul anual 2025 al băncii (p. 41) spune că circa 64% din totalul reclamațiilor sunt tranzacții cu cardul contestate. Pe 15.10.2026, CJUE a decis în cauza C-70/25 că banca nu poate refuza sau amâna rambursarea unei plăți neautorizate invocând neglijența gravă a clientului, așa că fluxul de dispute trebuie regândit chiar acum. Fraudele prin phishing și vishing cresc puternic.
- **Cel mai bun raport între reguli, volum și testabilitate: popririle.** ANAF a trimis 645.631 de adrese de poprire prin e-Popriri în 2024. BRD procesa circa 700.000 de popriri pe an cu 20 de oameni (2019). Regulile sunt la nivel de articol (CPC art. 729, 781–792; CPF art. 236), iar excepțiile reale sunt multe. Concurența: BCR folosește AI/ML pe popriri din 2020 *(de verificat)*; pentru Raiffeisen România nu există nicio dovadă publică.
- **Pariurile cele mai originale:** remedierile în masă (restituiri după decizii ANPC sau ale instanțelor), cererile de informații de la autorități (secret bancar) și integrarea Garanti BBVA România (migrare, reconciliere, KYC).
- **Ideile aglomerate**, pe care le vor alege multe din cele 29 de echipe: triaj de reclamații, pre-verificare de credit, chatbot, model generic de fraudă. Triajul reclamațiilor ar fi deja PoC la nivel de grup (Raiffeisen Tech), dar asta apare doar într-o verificare Perplexity *(de verificat)*.
- **Mesajul care se potrivește cu banca:** CEO-ul spune public că AI-ul pregătește decizia, iar supravegherea umană crește cu impactul asupra persoanei. Arhitectura care urmează mesajul: „LLM-ul extrage și redactează, motorul de reguli decide, omul aprobă excepțiile".

## Cum am punctat

Fiecare idee primește o notă de la 1 la 5 pe fiecare criteriu al juriului, ponderată cu procentele oficiale. Rezultatul e un scor din 5.

| Criteriu | Pondere | Ce am judecat |
|---|---:|---|
| Originalitate | 15% | Câte echipe din 29 ar alege-o; există deja la Raiffeisen sau la grup? |
| Research și domeniu | 15% | Câte reguli, cifre și dovezi de durere avem deja, cu surse |
| Design și orchestrare agent | 25% | Pași multipli, tool-uri reale, excepții naturale de arătat |
| Completitudine și testabilitate | 20% | Se poate face un scenariu end-to-end sigur și teste cu rezultat așteptat? |
| Arhitectură și reproductibilitate | 15% | Depinde mai ales de execuție; am pus 4 peste tot |
| Business | 10% | Volum, cost, amenzi, durere a clientului |

Notele sunt estimări ale noastre, nu ale băncii. Refaceți-le după ce vorbiți cu mentorii (vezi secțiunea 3).

## 1. Top probleme reale, clasate

Clasarea ține cont de cât de solidă e dovada, de volum, de presiunea legală (termene, amenzi), de cât de specifică e pentru Raiffeisen și de cât de potrivită e pentru un agent (documente + date + reguli).

| # | Problemă | Cea mai puternică dovadă | Procesul intern care o produce | Direcția din brief |
|---:|---|---|---|---|
| 1 | Contestații card și fraude nerambursate | ~64% din totalul reclamațiilor sunt tranzacții card contestate (raport anual 2025, p. 41); CJUE C-70/25 (15.10.2026) impune rambursarea D+1 chiar la neglijență gravă; phishing +70,6% în 2025; vishing 42% din sesizări în S1 2026 | Investigație manuală, colectare de dovezi (SCA/3-D Secure, dispozitiv), termene PSD2 și ale schemelor de card urmărite de mână | Triaj, anomalii |
| 2 | Popriri pe conturi și venituri protejate blocate | 645.631 adrese ANAF în 2024; ~525.000 persoane cu popriri în 2025; 2,25 mil. acte în S1 2025; BRD: ~700.000/an cu 20 de oameni (2019) | Popririle de la executori vin încă pe PDF sau hârtie; venitul protejat trebuie identificat manual; ridicarea e lentă | Validare, triaj, anomalii |
| 3 | Actualizare date (KYC) blocată, conturi blocate | Recenzii: conturi blocate trei ani la rând deși clientul actualizase datele; blocaj de ~3 săptămâni la schimbarea telefonului; client nou limitat 3 zile până la finalizarea înrolării | Revalidare manuală a documentelor; noul CEI nu are adresă tipărită; reîmprospătare după norme interne de risc | Validare |
| 4 | Reclamații: termene, triaj și scurgeri de date | ANSPDCP 2022: răspuns la reclamație cu documentele altui client atașate; CSALB: record +40% în S1 2026, +60% în 9 luni 2026; 33% din reclamații vin prin poștă | Triaj și redactare manuală; atașamente verificate de om; termene de 15/35 zile lucrătoare | Triaj |
| 5 | Remedieri în masă întârziate | ANPC 2021: amendă de 100.000 lei pentru restituiri la ~14.000 de clienți făcute cu peste 1,5 ani întârziere; ÎCCJ 2022: 3.050 de foști clienți (7,2 mil. €) neplătiți pentru că trebuiau să trimită IBAN-ul în scris | Recalcul și plată organizate manual, pe campanii; colectare de IBAN pe hârtie | Reconciliere, validare |
| 6 | Alerte AML și fraude de identitate | ~95% din alertele AML sunt fals pozitive (industrie); CSALB: peste 170 de cereri de fraudă până la 9.09.2026, mai ales credite luate pe numele victimelor, iar băncile refuză de regulă concilierea | Bucla manuală alertă → e-mail de cerere de informații → documente → verificare în CRM și sisteme interne → concluzie (anunț AML Raiffeisen, 2021 *(de verificat cu mentorii)*) | Anomalii |
| 7 | Integrarea Garanti BBVA România | Achiziție de ~591 mil. € anunțată pe 28.03.2026; finalizare T4 2026; integrare până în S2 2027 | Migrare de clienți și conturi, reconciliere de date, revalidare KYC, mutarea mandatelor și popririlor active | Reconciliere |
| 8 | Reconcilieri și excepții de plăți | CRISP (centrul de servicii RBI din România) reconciliază pentru 14 piețe; volume așteptate de 4 ori mai mari; 1–5% din plăți ajung în investigație (estimare de industrie) | Rezolvarea manuală a diferențelor; noi tipuri de excepții la plățile instant în euro și Verification of Payee (9.01.2027 / 9.07.2027) | Reconciliere |
| 9 | Cereri de informații de la autorități | Reguli clare, dar în conflict: CPC art. 660(2) cere răspuns „de îndată" executorilor, iar OUG 99/2006 art. 113 limitează ce li se poate da | Verificarea manuală a temeiului legal și a scopului cererii | Validare, triaj |
| 10 | Succesiuni și procuri | Reguli clare în Codul civil; dovada publică a durerii e slabă (o singură recenzie, neverificată) | Verificarea manuală a certificatelor de moștenitor, a minorilor și a procurilor; banca nu poate interoga RNNEPR | Validare |

### Ce trebuie reținut despre primele cinci

1. **Disputele card și fraudele** au cea mai puternică dovadă *internă* Raiffeisen (raportul anual 2025) și o presiune legală dură. Legea 209/2019 cere rambursarea unei tranzacții neautorizate până la sfârșitul zilei lucrătoare următoare (art. 173). Răspunderea clientului e plafonată la 30 € (art. 179), iar neglijența gravă trebuie dovedită de bancă. Hotărârea CJUE C-70/25 din 15.10.2026 a clarificat că neglijența gravă nu justifică refuzul sau amânarea rambursării. Singura excepție e suspiciunea rezonabilă de fraudă din partea clientului, notificată autorității competente; banca poate cere ulterior banii înapoi, dacă dovedește neglijența. Practic, fiecare caz se împarte acum în două: rambursare imediată, apoi un dosar separat de recuperare. În 2026, CSALB raporta că băncile refuzau de regulă concilierea în cazurile de fraudă, invocând autentificarea SCA.
2. **Popririle** au cel mai mare volum documentat public și cele mai precise reguli. ANAF trimite popririle electronic, prin e-Popriri (OPANAF 878/2022), iar din 1.10.2023 mecanismul de recuperare unică se aplică la toate băncile (OPANAF 626/2023). Executorii și primăriile trimit însă încă PDF-uri pe e-mail sau hârtie. Daune documentate: aceeași datorie blocată la mai multe bănci, venit protejat înghețat până la deblocarea manuală, erori de persoană sau CNP, comisioane cumulate. În Parlament sunt două proiecte (PLX 70/2026 pentru un sold protejat de 3.000 lei și PLX 198/2026 pentru o poprire electronică unică). Ambele au fost respinse de Senat și sunt acum la Camera Deputaților.
3. **KYC-ul blocat** e plângerea cea mai „personală" din recenzii. Mai sunt trei motive pentru care subiectul crește: noul card de identitate electronic (CEI, din 2025) nu mai are adresa tipărită; AMLR, aplicabil din 10.07.2027, cere reîmprospătare anuală pentru clienții cu risc ridicat și cel mult la 5 ani pentru ceilalți; integrarea Garanti BBVA aduce clienți noi de revalidat.
4. **Reclamațiile** sunt reale și au termene legale, dar ideea e aglomerată și pare să existe deja un PoC de grup *(de verificat)*. Un unghi distinct ar fi protecția împotriva scurgerilor de date: verificarea că atașamentele și datele dintr-un răspuns aparțin clientului corect, adică exact cazul amendat de ANSPDCP.
5. **Remedierile** leagă trei amenzi sau decizii publice de un proces pe care nimeni nu-l vede ca „automatizabil". Mai sunt o variantă cu originalitate mare.

## 2. Idei de agent AI, punctate

| # | Idee | Orig. 15% | Research 15% | Agent 25% | Testare 20% | Arhit. 15% | Business 10% | Scor /5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| I1 | Agent de popriri cu protecția veniturilor | 4 | 5 | 5 | 5 | 4 | 4 | **4,60** |
| I2 | Agent de dispute card și fraude cu „ceas legal" | 4 | 5 | 5 | 4 | 4 | 5 | **4,50** |
| I3 | Agent de remedieri în masă | 5 | 4 | 5 | 4 | 4 | 4 | **4,40** |
| I4 | Agent pentru cereri de la autorități (secret bancar) | 5 | 5 | 4 | 4 | 4 | 3 | **4,20** |
| I7 | Agent de investigare alerte AML și fraude de identitate | 3 | 4 | 5 | 4 | 4 | 4 | **4,10** |
| I6 | Agent de reconciliere pentru integrarea Garanti BBVA | 5 | 3 | 4 | 4 | 4 | 4 | **4,00** |
| I10 | Agent pentru dosare de succesiune | 5 | 3 | 4 | 4 | 4 | 3 | **3,90** |
| I5 | Agent KYC refresh și deblocare cont | 3 | 4 | 4 | 4 | 4 | 4 | **3,85** |
| I9 | Pre-verificare dosar de credit (DTI/LTV) | 2 | 4 | 4 | 5 | 4 | 3 | **3,80** |
| I8 | Triaj reclamații cu protecție PII | 2 | 4 | 4 | 4 | 4 | 4 | **3,70** |

Diferențele sub 0,3 puncte nu sunt semnificative. Contează mai mult ce vă spun mentorii și ce puteți executa sigur.

**O a doua evaluare, independentă.** Raportul de research a punctat separat 8 idei (fără remedieri) și a ajuns la aceeași ordine în vârf: popriri 4,48, dispute 4,38. Diferențe:
- raportul pune KYC pe locul 3 (4,20), pentru testabilitate;
- raportul coboară cererile de la autorități (3,95) și AML-ul (3,85), pentru că lipsesc volumele publice.

Raportul propune să alegeți după direcția accentuată în brief-ul oficial. Brief-ul prezentat pe scenă listează însă toate cele patru direcții, deci decid tot răspunsurile mentorilor.

### I1. Agent de popriri cu protecția veniturilor — 4,60

**Problema.** Banca primește popriri prin două canale: electronic de la ANAF (e-Popriri, PDF semnat + XML) și pe PDF sau hârtie de la executori și primării. Pentru fiecare trebuie să identifice debitorul, să blocheze doar ce e legal, să raporteze suma și să plătească la termen. Mai trebuie să ridice poprirea la încetare. Partea grea e venitul protejat: salariul se poate popri doar parțial (1/3 pentru datorii obișnuite, 1/2 pentru întreținere și 1/2 în total la popriri multiple), alocațiile și ajutoarele cu destinație specială sunt neurmăribile, iar veniturile sub salariul minim net au protecție suplimentară (CPC art. 729). O încălcare face executarea nulă (art. 730).

**Utilizator intern.** Echipa de popriri și sechestre din back-office.

**Input → reguli → rezultat.** Adresă de poprire + conturi și tranzacții ale debitorului → CPC art. 729, 781–792; CPF art. 236; ordinea de plată → instrucțiune de blocare, sumă raportată, plată sau **excepție** cu motiv.

**Pașii agentului.**
1. Clasifică documentul (ANAF XML, PDF de executor, scan) și extrage câmpurile (debitor, CNP/CUI, sumă, creditor, titlu, dosar).
2. Identifică clientul (CNP/CUI, nume, sucursala adresată — o poprire trimisă unei sucursale leagă doar conturile acelei sucursale, art. 783(5)).
3. Caută duplicate: aceeași datorie deja blocată sau poprită la mai multe bănci.
4. Clasifică încasările din cont (salariu, pensie, alocație, ajutor social, altele) după plătitor și descriere — aici e partea de ML.
5. Calculează suma urmăribilă cu motorul de reguli (determinist) și ordinea între popririle concurente.
6. Produce instrucțiunea, răspunsul către creditor (inclusiv codurile de respingere: fără cont, insolvență, cont închis, debitor decedat, alt motiv) și jurnalul de audit.
7. Trimite la om tot ce e ambiguu.

**Situații neprevăzute de arătat.** Poprire fără CNP, doar cu nume; alocație intrată în aceeași zi cu salariul; două popriri cu reguli de ordine contradictorii; debitor decedat (trece în fluxul de succesiune); scan ilizibil; instrucțiuni ascunse în PDF (prompt injection); ambiguitatea legală dacă plafonul de 1/3 se aplică peste pragul de salariu minim. Exemplu concret din raport: la un salariu net de 2.000 lei și un salariu minim net de 2.699 lei, partea urmăribilă e 650,50 lei sau 216,83 lei, după ordinea în care se aplică alin. (3) și (1) ale art. 729. Agentul calculează ambele variante și trimite cazul la om.

**Date sintetice.** Clienți, conturi și tranzacții coerente; adrese de poprire în ambele formate; 15–20 de cazuri de aur cu rezultat așteptat. Formate și validatori: [context/12](context/12_date_sintetice_formate_validatori.md).

**Ce există deja.** BCR procesează popriri cu AI/ML din 2020, în 371 de sucursale, cu Zipper *(de verificat)*. Raiffeisen Ucraina raportează peste 60 de procese robotizate, inclusiv documente de executare. Pentru Raiffeisen România nu am găsit nimic public. Avantajul vostru e clasificarea venitului protejat și explicabilitatea calculului, nu simpla citire a documentului.

**Riscuri.** Dovada publică de durere specifică Raiffeisen e slabă; o confirmă sau o infirmă mentorii. Valoarea salariului minim net pentru 2026 (2.699 lei într-un calculator comercial) e neverificată și trebuie ținută ca parametru.

**Context:** [context/10 — reguli popriri, autorități, succesiuni](context/10_reguli_popriri_autoritati_mosteniri.md)

### I2. Agent de dispute card și fraude cu „ceas legal" — 4,50

**Problema.** Circa 64% din reclamațiile înregistrate de Raiffeisen în 2025 sunt tranzacții cu cardul contestate (raport anual 2025, p. 41). Fiecare caz cere:
- clasificare (fraudă, dispută cu comerciantul, eroare de procesare, înșelătorie autorizată de client);
- urmărirea ceasurilor legale: 13 luni pentru notificare (art. 169), rambursare până la sfârșitul zilei lucrătoare următoare (art. 173), răspuns în 15/35 de zile lucrătoare (art. 224);
- urmărirea termenelor Visa/Mastercard;
- strângerea dovezilor.

Hotărârea CJUE C-70/25 (15.10.2026) schimbă fluxul. Neglijența gravă nu mai justifică refuzul sau amânarea rambursării. Banca rambursează întâi, apoi deschide separat un dosar de recuperare, în care trebuie să dovedească neglijența.

**Utilizator intern.** Echipa de dispute card și investigații de fraudă.

**Input → reguli → rezultat.** Reclamația clientului + jurnalul tranzacției + datele SCA/3-D Secure → Legea 209/2019, C-70/25, regulile Visa/Mastercard → rambursare D+1, chargeback cu cod de motiv, dosar de recuperare, respingere motivată sau **escaladare** (suspiciune de fraudă din partea clientului, de notificat autorității).

**Pașii agentului.**
1. Clasifică cererea: neautorizată (fraudă), dispută cu comerciantul, eroare de procesare sau înșelătorie autorizată chiar de client. Ultima nu intră în coada de chargeback, ci pe un traseu de sprijin.
2. Calculează termenele legale și pe cele ale schemei. La Visa: 120 de zile pentru codul 10.4; etapele ulterioare au 30, 30 și 10 zile; un termen ratat în Visa Resolve Online pierde cazul.
3. Strânge dovezile prin tool-uri: tranzacție, SCA, dispozitiv, comerciant. Din 2025, plățile online cu cardul se aprobă în Smart Mobile, deci jurnalele SCA sunt chiar ale băncii.
4. Aplică regulile: fără SCA cerută, clientul nu suportă nimic (art. 177); răspunderea lui e plafonată la 30 € (art. 179); rambursarea D+1 se face chiar dacă banca suspectează neglijență gravă (C-70/25).
5. Setează indicatorul „recuperabil prin chargeback" din ECI, CAVV și token. O fraudă autentificată cu Visa Secure (ECI 5 + CAVV) nu poate fi contestată pe codul 10.4, deci pierderea rămâne la bancă.
6. Propune decizia împreună cu dosarul de dovezi și redactează scrisoarea, verificând că datele și atașamentele aparțin clientului.

**Situații neprevăzute de arătat.**
- Cerere venită după 13 luni.
- Vishing în care fraudatorul a inițiat plata cu datele clientului: rambursare D+1 și dosar separat de recuperare. Dacă însă clientul a aprobat el însuși plata, cazul e o înșelătorie autorizată și merge pe alt traseu. Când nu e clar care din două, decide un om.
- Tranzacție fără SCA.
- Fraudă autentificată 3-D Secure, deci nerecuperabilă prin chargeback.
- Cont cu peste 35 de dispute în 120 de zile.
- Cumpărare de cripto contestată ulterior.
- Reclamație primită pe hârtie.

**Ce există deja.**
- Raiffeisen Tech ar avea un PoC de automatizare a reclamațiilor la nivel de grup *(doar din Perplexity; de verificat)*.
- BCR folosește din ianuarie 2026 un formular de dispută care cere plângere la poliție pentru fraudă, permite retragerea sumelor creditate provizoriu și promite răspuns în 15 zile.
- Rezultatele AI publicate pentru disputele card sunt doar declarații ale furnizorilor, de exemplu procesare cu 40% mai rapidă.
- La NEXXT 2025, finalistul FraudForecaster a propus agenți de detectare a fraudelor, deci un simplu clasificator de fraudă nu mai pare nou.
- Unghiul C-70/25 e nou: hotărârea are două săptămâni.

**Riscuri.** Regulile Mastercard provin din surse secundare care se contrazic. Nu avem volumele Raiffeisen și nici formularul ei de dispută. Cazul C-70/25 privea un transfer bancar, nu o plată cu cardul. Aplicarea la carduri decurge din art. 73 PSD2, care acoperă orice operațiune de plată neautorizată, dar confirmați lectura cu mentorii. Rămâne deschisă și întrebarea dacă un phishing în care victima a aprobat ea însăși 3-D Secure e o operațiune neautorizată: notele spun da, practica băncilor spune nu.

**Context:** [context/14 — dispute card și fraude](context/14_dispute_card_fraude.md), [context/11](context/11_reguli_kyc_aml_credit_plati_reclamatii.md)

### I3. Agent de remedieri în masă — 4,40

**Problema.** Când o instanță, ANPC sau un incident intern obligă banca să recalculeze și să restituie bani unui grup de clienți, munca se face pe campanii: selecția clienților, recalculul, colectarea IBAN-urilor, plățile și scrisorile. Întârzierile au costat deja: amenda ANPC din 2021 pentru restituiri făcute cu peste 1,5 ani întârziere la ~14.000 de clienți, apoi cei 3.050 de foști clienți (7,2 mil. €) încă neplătiți în decembrie 2022 pentru că trebuiau să trimită IBAN-ul în scris. După amenda Consiliului Concurenței din iunie 2026 (ROBOR, 442,49 mil. lei pentru Raiffeisen, contestată), subiectul rămâne actual. În pitch, păstrați-l neutru și nu sugerați vinovăție.

**Utilizator intern.** Echipa de remediere / juridic + operațiuni.

**Input → reguli → rezultat.** Decizia (hotărâre, ordin ANPC, memo de incident) + portofoliul de contracte → regula de remediere aprobată de juridic → sumă per client, canal de plată, scrisoare sau **excepție**.

**Pașii agentului.**
1. Citește decizia și propune o specificație structurată: ce clauză, ce perioadă, ce formulă.
2. Un om de la juridic aprobă specificația. Acesta e punctul de human-in-the-loop.
3. Selectează clienții afectați și recalculează determinist.
4. Rutează plata: IBAN existent și valid; cont închis → cere IBAN; client decedat → flux de succesiune; client cu poprire activă → verifică regulile de poprire.
5. Generează scrisorile și urmărește termenele.

**Situații neprevăzute de arătat.** Contract cu clauza modificată prin act adițional; client decedat; cont închis; client cu poprire activă; specificație ambiguă pe care agentul refuză s-o execute fără aprobare.

**Ce există deja.** Nimic public pentru România.

**Riscuri.** Scopul e mare; pentru demo păstrați o singură clauză și o singură formulă. Interpretarea juridică trebuie să rămână la om.

**Context:** [context/10](context/10_reguli_popriri_autoritati_mosteniri.md) (succesiuni, popriri), [context/11](context/11_reguli_kyc_aml_credit_plati_reclamatii.md) (credit, reclamații).

### I4. Agent pentru cereri de la autorități — 4,20

**Problema.** Instanțe, procurori, poliție, ANAF, executori și primării cer informații despre clienți. Secretul bancar (OUG 99/2006 art. 111–116) permite răspunsul doar dacă cererea are temei legal, client identificat, categorie de informații și scop (art. 113(3)). Regulile se bat cap în cap: executorii cer răspuns „de îndată" (CPC art. 660(2)), dar OUG 99 le dă doar „existența conturilor"; poliția are nevoie de ordonanța procurorului (CPP art. 153).

**Pașii agentului.** Clasifică solicitantul → verifică temeiul și elementele obligatorii → decide ce informații se pot da → calculează termenul → redactează răspunsul sau refuzul → escaladează conflictele de lege → jurnal de audit.

**De ce e originală.** Probabil nicio altă echipă nu o alege, iar regulile sunt deja la nivel de articol. Punctul slab: nu avem volume publice.

**Variantă combinată.** Un singur „hub de ordine legale" (popriri + cereri de la autorități + succesiuni) care folosește aceleași tool-uri: identificarea clientului, căutarea conturilor și motorul de reguli. Pentru demo, nucleul e poprirea, iar cererile sunt extensia.

**Context:** [context/10](context/10_reguli_popriri_autoritati_mosteniri.md)

### I7. Agent de investigare alerte AML și fraude de identitate — 4,10

**Problema.** Circa 95% din alertele AML sunt fals pozitive (sondaj NICE Actimize). Un anunț AML Raiffeisen din 2021 descrie bucla manuală: alertă → e-mail de cerere de informații → documente strânse prin telefon sau e-mail → verificare în CRM și în istoricul tranzacțiilor → concluzie și arhivare *(anunț vechi; de verificat cu mentorii)*. În 2026, CSALB vede tot mai multe credite luate pe numele victimelor.

**Pașii agentului.** Îmbogățește alerta → aplică tipologii (de exemplu fragmentare sub praguri, conturi de tranzit, intrări și ieșiri rapide) → scrie narațiunea și recomandarea (închidere sau escaladare) → pregătește raportul de tranzacție suspectă cu termenele din Legea 129/2019 (art. 6 și 8) → redactează cererile de informații.

**Date.** IBM AMLworld (date sintetice publice).

**Ce există deja.** Starling a redus timpul pe alertă de la 15–30 de minute la sub 17 secunde; FIS și Anthropic proiectează reduceri de peste 90% (proiecții, nu rezultate). Idee bună tehnic, dar frecventă la hackathoane.

**Context:** [context/11](context/11_reguli_kyc_aml_credit_plati_reclamatii.md), [context/13](context/13_arhitectura_agent_guardrails_evaluare.md)

### I6. Agent de reconciliere pentru integrarea Garanti BBVA — 4,00

Două extrase sintetice de core banking (clienți, conturi, produse, stare KYC) intră în agent. Acesta face potrivirea entităților (CNP/CUI, nume cu și fără diacritice, adrese), aplică regulile de mapare a produselor și IBAN-urilor și găsește discrepanțele: date în conflict, KYC expirat la banca sursă, duplicate, mandate și popriri active care trebuie mutate. Rezultatul e o coadă de excepții cu sarcini de remediere. **Pro:** e foarte actuală și specifică Raiffeisen. **Contra:** nu știm cum plănuiește banca integrarea, deci poate părea prezumțioasă; întrebați întâi mentorii.

### I10. Agent pentru dosare de succesiune — 3,90

Agentul verifică certificatul de moștenitor (Codul civil art. 1.132–1.134), calculează cotele, cere autorizarea instanței de tutelă pentru minori, închide mandatele și procurile (moartea le stinge, art. 2.030) și pregătește plățile. E originală și are reguli clare, dar dovezile de durere sunt slabe. Se potrivește mai bine ca ramură a I1 sau a I3.

### I5. Agent KYC refresh și deblocare cont — 3,85

Agentul validează actele (verificarea MRZ, coerența CNP-ului, expirarea). Știe că noul CEI nu are adresă și cere dovada potrivită. Aplică reîmprospătarea după risc și tratează rezultatele de screening PEP și sancțiuni. Decizia: deblocare, cerere țintită pentru documentul lipsă sau due diligence sporit. Dovezile din recenzii sunt directe, dar ideea e frecventă. Unghiul Garanti BBVA o poate face mai interesantă.

### I9. Pre-verificare dosar de credit — 3,80

Calculul gradului de îndatorare și al LTV-ului (Reg. BNR 17/2012: 40%, sau 45% la prima locuință; LTV între 60% și 85%) e ușor de testat. Ideea e însă cea mai aglomerată. Dacă o alegeți, prezentați agentul ca unul care pregătește dosarul pentru analistul de credit, fără să decidă: scoringul persoanelor e „risc ridicat" în AI Act de la 2.12.2027 (Regulamentul (UE) 2026/1744), iar GDPR art. 22 și jurisprudența SCHUFA cer intervenție umană.

### I8. Triaj reclamații cu protecție PII — 3,70

Agentul clasifică reclamațiile, calculează termenele, sumarizează, rutează și redactează răspunsul. Elementul distinctiv e garda care verifică datele și atașamentele înainte de trimitere. E aglomerată și pare să existe un PoC de grup *(de verificat)*; folosiți-o ca modul în I2, nu ca idee de sine stătătoare.

## 3. Shortlist propus și cum decideți

| Opțiune | Alegeți-o dacă… |
|---|---|
| **I1 Popriri** | vreți cel mai sigur raport între reguli, testabilitate și impresia de domeniu; mentorii confirmă că executorii și venitul protejat consumă muncă manuală |
| **I2 Dispute card și fraude** | vreți valoarea de business cea mai evidentă pentru Raiffeisen și un subiect foarte actual (C-70/25); mentorii confirmă că investigația e manuală |
| **I3 Remedieri** sau **I4 Cereri de la autorități** | vreți să mizați pe originalitate și puteți ține scopul mic |

**Trei întrebări pentru mentori, înainte de a alege.** Răspunsurile lor valorează și la criteriul de business (10%) și la cel de domeniu (15%), pentru că le puteți cita în pitch.

1. „Cum vin azi popririle de la executori și primării și cât din procesare e manuală? Cum identificați venitul protejat?"
2. „Din reclamațiile pe card, ce parte ajunge în investigație manuală, cât durează un caz și cum se schimbă fluxul după hotărârea CJUE C-70/25?"
3. „Unde anticipați cel mai mult efort manual la integrarea Garanti BBVA?"

**Decizie în 15 minute.** Puneți întrebările, refaceți notele din tabelul de mai sus cu ce ați aflat, alegeți ideea cu scorul cel mai mare pe care o puteți demonstra sigur, cu cel puțin trei excepții scriptate.

## 4. Ce să evitați

- **Chatbot pentru clienți.** Provocarea cere muncă internă, iar Raiffeisen are deja Ana, ARI și ERIC.
- **Model de scoring de credit care decide.** E risc ridicat în AI Act, intră sub GDPR art. 22 și e cea mai aglomerată idee.
- **„Detecție de fraudă" ca model ML fără proces.** Juriul cere input → reguli → rezultat sau excepție, nu doar un scor, iar FraudForecaster a fost finalist pe această temă în 2025.
- **Clasificator de reclamații simplu.** E o idee frecventă, iar la nivel de grup pare să existe deja un PoC *(de verificat)*.
- **Agent care mută bani sau ia decizii ireversibile singur.** Notele de research recomandă un set închis de tool-uri, aprobare umană și jurnal de audit.

## 5. Cifre de citat, cu nivelul de încredere

| Cifră | Sursă | Încredere |
|---|---|---|
| Raiffeisen 2025: profit net 1,75 mld lei, ~2,33 mil. clienți, cost/venit 42,6%, 4.698 angajați (−255, atribuit digitalizării) | Raport anual 2025 | Ridicată |
| ~64% din totalul reclamațiilor sunt tranzacții card contestate | Raport anual Raiffeisen 2025, p. 41 | Ridicată |
| CJUE C-70/25 (15.10.2026): neglijența gravă nu justifică refuzul rambursării D+1 | [Comunicat CURIA](https://curia.europa.eu/site/upload/docs/application/pdf/2026-10/cp260147en.pdf) | Ridicată |
| 645.631 adrese ANAF în e-Popriri (2024); 2,25 mil. acte în S1 2025 | ANAF, prin notele despre popriri | Ridicată |
| BRD: ~418.000 popriri ANAF + ~250.000 de la executori pe an, echipă de 20 (2019) | Presă, 2019 | Medie (cifră veche) |
| BCR: popriri procesate cu AI/ML din 2020, în 371 de sucursale | Notele despre AI în operațiuni | De verificat |
| Phishing: 4.975 incidente în 2025 (+70,6%); vishing 42% din sesizări în S1 2026 | Notele despre reguli KYC/plăți | Medie |
| CSALB: 3.394 cereri în 9 luni 2026 (+60%); peste 170 de cereri de fraudă | CSALB, comunicat 20.10.2026 | Ridicată |
| ~95% din alertele AML sunt fals pozitive | Sondaj NICE Actimize (vendor) | Medie (vendor) |
| Peste 40% din proiectele de AI agentic vor fi anulate până la finalul lui 2027 | Gartner | Medie (prognoză) |
| AI Act: obligațiile pentru risc ridicat (Anexa III) se aplică de la 2.12.2027 | Regulamentul (UE) 2026/1744 | Ridicată |

## 6. Context Raiffeisen care contează pentru pitch

- **Poziție:** locul 6 după active (~9,3%), aproximativ 2,4 mil. clienți în S1 2026, 1,81 mil. clienți digitali.
- **AI intern:** departament propriu din 2019 (~30 de ingineri și 12 aplicații în 2024); ARI pentru angajați (2024); Ana pentru clienți; ERIC pentru IMM-uri (2026); RPA și citire automată de documente în onboardingul IMM (2025).
- **Grupul RBI:** RBI GPT pe Azure OpenAI, cu peste 20.000 de utilizatori; peste 160 de cazuri de utilizare AI; direcție declarată spre AI agentic.
- **Stack:** AWS, Databricks, Python, OpenShift, Oracle, Salesforce, SAP (din anunțurile de angajare).
- **Juriul 2025** a inclus CRO-ul, COO-ul și directorul de Advanced Analytics. Câștigătorii au fost SmartBranch (locul 1) și Deepfake Detection (locul 2).

## 7. Unde găsiți restul

| Ce | Unde |
|---|---|
| Reguli pentru popriri, cereri de la autorități, succesiuni | [context/10](context/10_reguli_popriri_autoritati_mosteniri.md) |
| Reguli KYC/AML, credit, plăți, reclamații | [context/11](context/11_reguli_kyc_aml_credit_plati_reclamatii.md) |
| Identificatori, formate, date sintetice, tooling | [context/12](context/12_date_sintetice_formate_validatori.md) |
| Arhitectură de agent, guardrails, evaluare, întrebări de la juriu | [context/13](context/13_arhitectura_agent_guardrails_evaluare.md) |
| Dispute card, chargeback, fraude, C-70/25 | [context/14](context/14_dispute_card_fraude.md) |
