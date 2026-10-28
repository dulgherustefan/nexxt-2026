# VersoML: demo și pitch

Traseul exact prin aplicație pentru demo-ul de 4 minute din `docs/05` §13, cu ce spune prezentatorul. Totul rulează pe date sintetice („Banca Demo", „Curier Demo").

## Înainte de demo (5 minute)

1. `uv run versoml up`: pornesc zona client (:8000) și zona AML (:8001).
2. Pe ecranul mare deschideți două ferestre alăturate: consola de contestații la `http://127.0.0.1:8000` și consola AML la `http://127.0.0.1:8001`.
3. Pe telefon (sau într-o fereastră îngustă) deschideți Banca Demo: `http://<ip-laptop>:8000/banca`. Telefonul trebuie să fie pe același Wi-Fi; altfel folosiți fereastra îngustă.
4. Dacă rețeaua e nesigură, setați `VERSOML_LLM_MODE=replay` în `.env`: răspunsurile LLM înregistrate se redau identic.
5. Pentru repetiții, butonul de reset (sau `POST /api/demo/reset` și `POST /api/aml/reset`) golește cazurile.

## Desfășurare

| Minut | Click | Ce spune prezentatorul |
|---|---|---|
| 0:00 | Telefonul juratului: `/demo/livrare` („Curier Demo", marcat DEMO) → plătește taxa de 2,99 lei cu date de test | „Un SMS de curier, o pagină falsă. Escrocul înrolează un telefon nou și trimite 3.200 de lei." |
| 0:30 | Banca Demo (`/banca`): soldul a scăzut → „Nu am făcut eu plata" | „Clientul contestă din aplicație. Din acest moment curge termenul legal T+1." |
| 0:40 | Consola: cazul nou se deschide singur; pipeline-ul se aprinde | „Receptorul e un LLM izolat, fără tool-uri: textul escrocului e dată, nu instrucțiune. Patru colectori lucrează în paralel: tranzacția, autentificarea SCA, dispozitivul, domeniul fals." |
| 1:10 | Tab „Probe" | „Dispozitiv nou, plata la 118 secunde după click, domeniu creat acum 6 ore, scor de sosie 0,9. Fiecare probă are hash și pașaport." |
| 1:30 | Tab „Decizii" → `RAMBURSEAZA`, reguli PAY-…; telefonul primește „Ți-am returnat 3.200 lei" | „Motorul de reguli decide, nu LLM-ul. Sub plafon și fără semnale, rambursarea pleacă automat. Peste plafon, un om aprobă cu un click." |
| 1:50 | Tab „Dezbatere" | „Procurorul pe Opus, Avocatul pe alt model. Fiecare afirmație are citări; cele fără sursă se resping automat. Rubrica e deterministă. Dezbatem doar recuperarea, nu rambursarea, pentru că literatura arată că dezbaterea nu crește precizia." |
| 2:10 | Comutatorul „Schimbă un fapt: ecranul a afișat suma și beneficiarul" | „Recomandarea de recuperare se schimbă. Rambursarea rămâne: după C-70/25, neglijența nu justifică refuzul." |
| 2:40 | Al doilea jurat: `/banca?client=CUST-DEMO-02` (transfer „cont sigur" în același cont) | „Altă țeapă, același cont." Pe consola AML, graful se aprinde: două victime, un cont, tranzit rapid spre crypto. |
| 3:00 | Consola AML: pista → graful, scorurile ML, OSINT, Avocatul nevinovăției, ciorna RTS | „ML-ul dă scorurile, LLM-ul explică. Înainte de RTS, Avocatul nevinovăției caută explicațiile nevinovate. Fiecare frază din RTS citează o probă. Decide analistul." |
| 3:20 | Consola client: pagina „Zidul" → „Atacă zidul"; tab „Scrisoare" → scrieți „contul a fost raportat la ONPCSB" | „Încercați să scoateți ceva din AML spre client. Cedar refuză, dioda respinge textul liber, filtrul blochează scrisoarea, canary-ul se aprinde." |
| 3:40 | Pagina „Evaluare" | „Reguli 100% pe setul de aur, termene corecte, zero scurgeri peste zid în testul de neinterferență, zero date personale brute spre model." |

## Pitch în 30 de secunde

> „Două treimi din reclamațiile Raiffeisen sunt plăți cu cardul contestate. Acum două săptămâni, Curtea de Justiție a UE a schimbat regula: banca rambursează imediat, chiar dacă clientul a greșit, și abia apoi încearcă să recupereze. VersoML face asta într-o zi: rambursează când legea o cere, construiește dosarul de probe, pornește recuperarea și transformă contul escrocului într-o pistă pentru AML. Între echipa de contestații și AML stă un zid testat, pentru că a-i spune cuiva că e investigat e infracțiune. Regulile decid, omul semnează, iar fiecare frază are o sursă. Și e un server MCP: îl folosiți din orice asistent."

## Întrebări probabile de la juriu

| Întrebare | Răspuns scurt |
|---|---|
| De ce nu decide LLM-ul? | Pentru că termenele și obligațiile sunt lege, nu opinie. LLM-ul extrage, argumentează și redactează; motorul de reguli decide cu ID de regulă; omul semnează excepțiile (GDPR art. 22). |
| Cum știți că zidul ține? | Șase straturi, fiecare cu test. Testul de neinterferență rulează graful real cu zona AML goală, apoi plină de canary și text de tipping-off: decizii identice, zero canary în ieșirile zonei client. |
| De ce două modele în dezbatere? | Agenții de același tip capitulează și ajung la acord greșit (până la 86% din rulări). Folosim modele diferite, declarații independente, o singură replică și citări obligatorii. |
| Ce face ML-ul, concret? | M1 clasifică reclamația cu probabilitate calibrată. M5 scorează conturile-cărăuș pe trăsături de graf; comparăm cinstit cu baseline-uri (reguli simple, GBDT fără graf). LLM-ul singur e mai slab decât GBDT pe triajul AML; de aceea ML-ul scorează, iar LLM-ul explică. |
| Și dacă reclamația conține o injecție? | Receptorul nu are tool-uri, iar textul nu intră în contextul regulilor. Injecția se semnalează omului și nu schimbă nicio decizie. |
| Date personale spre model? | PrivacyProxy pseudonimizează înainte de fiecare apel, iar o gardă refuză apelul dacă rămâne ceva brut. În evaluare: 0. |
| De ce `us-east-1`, nu UE? | Contul de hackathon are o politică SCP care blochează Bedrock în UE. În producție: regiune UE; modelul primește oricum doar date pseudonimizate. |
| Ce se întâmplă fără internet? | Modul replay redă răspunsurile LLM înregistrate; OSINT-ul are înregistrări pentru scenariile sintetice. |
| Cum ajungeți în producție? | P1 pe AWS: AgentCore Runtime câte unul pe zonă, Gateway pentru tool-uri, Policy pe Cedar (aceleași politici), Evaluations; vezi `docs/05` §6.2. |
