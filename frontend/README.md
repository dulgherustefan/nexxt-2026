# VERSOML · frontend

O singură aplicație cu două roluri (Operator contestații / Analist AML), Banca Demo, pagina falsă de demo și demo-ul ghidat. Vite + React 19 + TypeScript strict + Tailwind CSS v4, lucide-react și @xyflow/react (graful agenților și graful banilor). Fonturile (Archivo, JetBrains Mono) sunt incluse în build, deci totul merge fără internet.

Designul și tokenurile: [DESIGN.md](DESIGN.md). Contractul API: `docs/06_implementare.md` §6.

## Pornire

Cerințe: Node 24, npm 11.

```bash
cd frontend
npm install

npm run dev        # zona client: proxy /api și /diode → http://127.0.0.1:8000
npm run dev:aml    # zona AML:    proxy → http://127.0.0.1:8001
npm run dev:mock   # fără backend: date simulate + rularea demo-ului în browser

npm run build      # tsc -b (strict, zero erori) + vite build → frontend/dist
npm run preview    # servește dist/ cu același proxy
```

Ținta proxy-ului se poate schimba: `VITE_API_TARGET=http://127.0.0.1:8001 npm run dev`.

În producție, FastAPI servește `frontend/dist` pe ambele porturi; căile de assets sunt absolute de la `/` (`/assets/...`), iar fallback-ul SPA (orice rută necunoscută → `index.html`) e pe server. Aplicația află zona din `GET /api/meta` (`zone: "client" | "aml"`).

Serverul de dev ascultă și pe IP-ul din rețea (`host: true`), ca telefoanele să deschidă `/banca` și `/demo/livrare`. „Coduri QR pentru jurați” din bara laterală (sau `?qr=1`) arată QR-urile, construite din adresa la care e deschisă consola.

## Modul mock

UI-ul trece singur pe date simulate dacă `GET /api/meta` nu răspunde (în 2,5 s) sau nu întoarce JSON. Se poate forța cu `VITE_MOCK=1` (`npm run dev:mock`) sau cu `?mock=1` în URL.

- `?zone=aml` deschide zona AML (se ține minte în fila curentă; `?zone=client` revine).
- Starea stă în `localStorage`, deci filele o împart: Banca Demo, consola client și consola AML deschise în file diferite văd aceleași cazuri. O filă-lider avansează rulările; dacă o închizi, preia alta.
- „Pornește demo-ul T+1" rulează graful Judecătorului în ~25 s: Receptor → Clasificator → Ceasornicar → 4 colectori în paralel → Motor de reguli → Rambursare (așteaptă semnătura) ‖ Procuror + Avocat → Cântăritor → Recuperare → Redactor → Filtru zid → Sigiliu. Faptele au hash-uri SHA-256 reale, înlănțuite, cu rădăcină Merkle și QR (semnătura e simulată).
- Pagina falsă → plata de 3.200 lei în Banca Demo → „Nu am făcut eu plata" → cazul pornește → aprobi în consolă → „Ți-am returnat 3.200 lei" pe telefon.
- Faptele trec „prin diodă" în zona AML: victima apare în graful pistei `PST-2026-0007`. „Pornește Investigatorul" rulează OSINT, Graf + ML, Avocatul nevinovăției și ciorna RTS; „Emite HOLD" trimite înapoi doar un boolean.
- Resetarea datelor mock: „Resetează datele demo” din caseta de stare din bara laterală (sau ștergi cheile `versoml.mock.*` din `localStorage`).

Toate datele sunt sintetice: bănci fictive (BDEM, XBNK, YBNK), domenii `.example`, clienți cu alias. Rapoartele din mock (de exemplu evaluarea) sunt marcate „simulat".

## Rute

O singură adresă: aplicația servită de zona client pe `:8000`. Comutatorul din bara de sus schimbă rolul.

Operator: `/` „Azi” (indicatori, coada după termenul T+1, agenții live, campanii) · `/cazuri` · `/cazuri/:id` camera cazului · `/demo` demo-ul ghidat (telefon + caz + 7 pași) · `/zid` · `/reguli` · `/evaluare` · `/mcp` · `/banca` (Banca Demo, `?client=CUST-DEMO-02` pentru al doilea jurat) · `/demo/livrare` (pagina falsă).

Analist AML: `/aml` piste, campanii și rețeaua · `/aml/piste/:leadId` camera pistei (graful banilor) · `/aml/osint` · `/aml/jurnal`. Vederea AML citește direct din procesul AML (`urls.aml` din `/api/meta`, CORS permis pentru `:8000`); rolul de operator nu apelează niciodată API-ul AML. Deschisă pe `:8001`, aplicația pornește direct în rolul AML.

## Structura

```
src/
  api/        types.ts (oglinda versoml/contracts.py), client.ts (un apel per endpoint din §6),
              sse.ts (EventSource cu reconectare și de-duplicare după seq), runtime.tsx (zona, modul, useResource),
              format.ts (lei, ore RO, etichete în română, normalizarea ş/ţ → ș/ț)
  lib/        pipeline.ts (graful Judecătorului, potrivirea evenimentelor pe noduri), params.ts
  mocks/      store.ts (starea comună), engine.ts (rularea scriptată), stories.ts (scenariile),
              aml.ts (pista, graful, OSINT), fixtures.ts, sha256.ts, calendar.ts
  ui/         kit.tsx (primitivele: butoane, badge-uri, file, panouri, stări goale și de eroare)
  shell/      AppShell.tsx (bara laterală, banda de mediu), PhoneDemo.tsx (codurile QR)
  pages/      client/*, aml/*, demo/* (Banca Demo, pagina falsă)
```

## Ce așteaptă UI-ul de la backend (în plus față de forme)

- Evenimentele SSE au `step` egal cu ID-ul nodului din `CaseDetail.pipeline` (ID-urile canonice sunt în `src/lib/pipeline.ts`: `receptor`, `clasificator`, `ceasornicar`, `colector_tranzactie|sca|dispozitiv|domeniu`, `motor_reguli`, `outbox_aml`, `rambursare`, `procuror`, `avocat`, `cantaritor`, `recuperare`, `redactor`, `filtru_zid`, `sigiliu`). Dacă nu se potrivesc exact, UI-ul încearcă după etichetă și după `agent`.
- `seq` crescător pe flux (de-duplicarea la reconectare). Fără `seq`, cheia e conținutul evenimentului.
- Opțional: `STEP_FINISHED.data.status = "skipped" | "blocked"`, `CUSTOM interrupt` cu `data.pending`, `TEXT_MESSAGE_CONTENT` cu `data.message_id` și `data.delta` (dezbaterea live), iar în zona AML `data.graph_update: true` când se schimbă graful și pașii `receptor_fapte`, `osint`, `graf_ml`, `avocat_nevinovatie`, `redactor_rts`, `analist`.
- Banca Demo citește și `GET /api/cases/{id}` (doar `summary`) ca să arate starea contestației.
- Verificarea dosarului trimite la `POST /api/verify` obiectul `{case_id, facts, seal}` din `GET /api/ledger/{id}`; „Exportă JSON" descarcă același obiect.
- `PUT /api/rules/params` primește doar cheile schimbate.
