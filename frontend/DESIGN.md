# VersoML · design

Consolă de operare, la standardul categoriei (reper: Stripe Dashboard + Linear). Operatorul vede întâi decizia, termenul și ce așteaptă semnătura lui. Tokenurile sunt în `src/styles/index.css` (`@theme`), primitivele în `src/ui/kit.tsx`.

## Culoare

Paleta e impusă: galben, alb, negru. Tot restul e neutru sau semantic.

| Token | Valoare | Rol |
|---|---|---|
| `yellow` | `#ffe500` | doar: acțiunea principală, elementul activ din navigare, „acum” (pas care rulează, caz care te așteaptă), numărul filei active |
| `yellow-soft` / `yellow-tint` | `#fff4a8` / `#fffbe0` | banner de semnătură; rânduri „te așteaptă”; hover pe rânduri |
| `ink` | `#0b0b0b` | text, chenarul elementelor active, bara laterală AML |
| `ink-soft` / `muted` / `subtle` | `#2a2a26` / `#5b5b52` / `#74746a` | text secundar, etichete, metadate |
| `line` / `line-strong` | `#d8d8ce` / `#b4b4a8` | chenare de 1 px |
| `paper` / `canvas` / `hover` | `#fff` / `#f6f6f1` / `#efefe8` | suprafețe |
| `danger` (+ `-soft`, `-line`) | `#c4311a` | excepții, blocări, termen sub 6 h |
| `ok` (+ `-soft`, `-line`) | `#15793b` | bani returnați, verificări trecute |

Reguli:
- Galbenul apare mereu cu text negru și nu marchează niciodată un avertisment; urgența merge neutru → roșu.
- Culoarea nu poartă singură sensul: orice stare are și cuvânt sau iconiță.
- Zona AML are bara laterală neagră și banda de mediu neagră cu text galben; restul suprafeței rămâne alb.

## Tipografie

- Archivo Variable (inclus în build), rădăcină 15 px (lizibil pe proiector), numerale tabulare pentru sume și termene.
- JetBrains Mono doar pentru ID-uri, hash-uri și coduri de regulă (`IdTag`).
- Ierarhie: titlu de pagină 1,75 rem bold, propoziția deciziei 1,45 rem bold, titlu de panou 1 rem semibold, corp 1 rem, metadate 0,8–0,87 rem.
- Majuscule obișnuite (sentence case), fără supratitluri, fără text rotit, fără majuscule spațiate.

## Formă și spațiu

- Raze: 6 px (chip-uri), 8 px (butoane, câmpuri), 12 px (panouri). Chenare de 1 px, fără umbre decorative; umbra există doar la straturi (dialog, meniu mobil).
- Marginea laterală pe telefon e 18 px; conținutul are maximum 1320 px.

## Tipare

- **Decizia întâi.** Cazul se deschide cu o propoziție despre bani și termen („Rambursarea de 3.200 lei a fost emisă.”), apoi motivele, fiecare cu probele citate (clic → proba clipește în tabel).
- **Un singur buton principal pe ecran.**
- **File cu numărătoare** pentru filtre (Toate, Te așteaptă, În lucru, Termen în 24 h, Închise).
- **Lista de pași a agenților:** cascadă pe o axă de timp comună, grupată pe faze. Se strânge când rularea s-a încheiat și rămâne deschisă dacă un pas e oprit.
- **Bannere:** galben pentru „semnătura ta”, roșu pentru „zidul a oprit scrisoarea”, fiecare cu o singură acțiune.
- **Banda de mediu** permanentă: „Date sintetice”.
- **Telefon:** tabelele devin liste de rânduri, cu starea, timpul rămas și suma la început.

## Rezerve (fallback)

Mod demonstrativ automat când serverul nu răspunde (sau `?mock=1`), interogare periodică în locul fluxului live, `SectionBoundary` pe fiecare secțiune, eroare cu „Încearcă din nou”, stări goale cu o acțiune, ultima stare păstrată când se pierde legătura.

## Demo pe telefon

„Coduri QR pentru jurați” (sau `?qr=1`) deschide două coduri mari pentru proiector: pagina falsă și Banca Demo, cu avertisment dacă consola e pe localhost.

## Ce nu folosim

Grafic decorativ (fiecare inel, bară sau graf arată o dată reală), gradient, galben pentru avertismente, text conturat sau rotit. Benzile cu dungi galben-negru apar doar la zid și în zona AML. Semaforul termenelor folosește verde / chihlimbar (`warn`) / roșu.
