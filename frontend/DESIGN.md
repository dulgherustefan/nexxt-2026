# VersoML · design

Unealtă internă de back-office, la standardul Linear / Stripe Dashboard. Un singur lucru principal pe ecran; prima privire spune ce ai de făcut; detaliile se deschid la cerere. Tokenurile sunt în `src/styles/index.css` (`@theme`), primitivele în `src/ui/kit.tsx`.

## Arhitectura informației

- Bara de sus: marca „V” + VersoML, comutatorul de rol (Operator / Analist AML), punctul de stare (Live / Replay / Offline / Date demo), butonul „Demo”.
- Navigarea din stânga: Operator → Contestații, Sistem. AML → Piste, Verificare OSINT, Sistem.
- **Contestații** (`/`): trei cifre (De rezolvat azi · Așteaptă semnătura ta · Rambursat azi), filele De făcut / Așteaptă semnătura / Rezolvate, un tabel, butonul „Caz nou” (dialog cu scenariile).
- **Caz** (`/cazuri/:id`): o coloană de maximum 960 px. Antet (sumă, client, ce s-a întâmplat, termen, stare) → cutia deciziei (o propoziție, cine a decis, semnătura, trei motive, „Vezi regulile”) → „Ce s-a întâmplat” → secțiuni pliabile (Probe, Scrisoarea, Recuperare, Procuror ↔ Avocat, Dacă schimb un fapt, Registru). Graful agenților stă în sertarul „Cum a decis VersoML”.
- **Piste** (`/aml`) și **Pistă** (`/aml/piste/:id`): același tipar; graful banilor e vizualul principal, restul pliabil.
- **Sistem** (`/sistem/:tab`, `/aml/sistem/:tab`): file Zidul, Reguli, Evaluare, MCP, Coduri QR (+ Jurnal de acces pentru analist).
- **Demo** (`/demo`): pașii sus, telefonul în stânga, ecranul operatorului în dreapta. `/banca` și `/demo/livrare` rămân pagini de telefon.

## Culoare

| Token | Valoare | Rol |
|---|---|---|
| `yellow` | `#ffe500` | butonul principal, selecția (navigare, filă activă), cutia care cere semnătura |
| `yellow-soft` / `yellow-tint` / `yellow-line` | `#fff5b8` / `#fffbe5` / `#e8d23a` | fundal selectat, rând evidențiat, chenarul galbenului |
| `ink` / `ink-soft` / `muted` / `subtle` | `#141413` / `#3d3d39` / `#66665f` / `#74746c` | text, de la principal la metadate (toate ≥ 4,5:1 pe alb) |
| `line` / `line-strong` | `#e6e6e1` / `#cfcfc8` | chenare de 1 px |
| `paper` / `canvas` / `hover` | `#fff` / `#f7f7f5` / `#f0f0ec` | suprafețe; `canvas` = bara laterală |
| `danger`, `ok`, `warn` (+ `-soft`, `-line`) | `#c4311a`, `#15793b`, `#9a5a00` | doar stare: excepții și termen sub 6 h; bani returnați; scor mediu |

Galbenul apare mereu cu text negru și nu marchează avertismente. Benzile galben-negru apar doar ca fâșie de 3 px deasupra textului „Zona AML · date separate”.

## Tipografie și spațiu

- Archivo Variable la lățime normală, rădăcină 15 px; corp 14 px (0,9333rem), metadate 12–13 px; JetBrains Mono doar pentru ID-uri, hash-uri și coduri de regulă, mic și secundar.
- Titlu de pagină 21 px semibold; suma din antetul cazului 26 px; propoziția deciziei 20 px.
- Grilă de 8 px; raze 6 / 8 / 10 px; chenare de 1 px; umbră doar pe straturi (dialog, sertar).

## Tipare

- **Decizia întâi**: o propoziție despre bani și termen, cine a decis, cel mult trei motive scrise din faptele folosite de reguli. ID-urile de regulă și citările EV stau sub „Vezi regulile”.
- **Un singur buton galben pe ecran.**
- **Secțiuni pliabile** închise implicit; „Probe” se deschide singură cât lucrează agenții.
- **Sertarul** pentru graful agenților; în antet, cât rulează: „Agenții lucrează · 9/17 pași”.
- **Telefon (390 px)**: tabelele devin liste; navigarea intră în meniul din stânga.

## Ce nu folosim

Titluri-poster, ticker pe ecranele de lucru, mozaicuri de cifre, grafice decorative, gradient, text conturat, galben pentru avertismente.
