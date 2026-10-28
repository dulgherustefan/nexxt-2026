# VersoML frontend

The bank console for "I didn't make this payment" disputes, the homepage that explains it, and the Demo Bank pages used in the live demo. Built with Vite, React 19, TypeScript (strict), Tailwind CSS v4 and React Router 7. Icons come from Phosphor. The fonts (Host Grotesk, Fragment Mono) are bundled, so everything works offline.

Design rules and tokens: [DESIGN.md](DESIGN.md). API contract: `docs/06_implementare.md` §6.

## Run it

Requires Node 24 and npm 11.

```bash
cd frontend
npm install

npm run dev        # console and homepage; proxies /api and /diode to http://127.0.0.1:8000
npm run dev:mock   # no backend: demo data, and the demo case runs in the browser

npm run build      # tsc -b (strict, zero errors), then vite build into frontend/dist
npm run preview    # serves dist/ with the same proxy
```

`npm run dev` expects the backend on port 8000. Start it from the project root with `uv run versoml up`. To point the proxy somewhere else: `VITE_API_TARGET=http://127.0.0.1:9000 npm run dev`.

In production, FastAPI serves `frontend/dist`. Asset paths are absolute (`/assets/...`) and the server answers any unknown path with `index.html`, so deep links such as `/cases/CT-2026-000123` load directly.

The dev server also listens on your network address (`host: true`), so phones on the same Wi-Fi can open `/bank` and `/demo/delivery`. "QR codes for the jury" in the sidebar (or `?qr=1` in the URL) shows QR codes built from the address the console is open at.

## Routes

| Path | Page |
|---|---|
| `/` | Homepage. It paints right away, without waiting for the server. |
| `/cases` | Cases, most urgent first |
| `/cases/:id` | One case: the decision, the deadline, the evidence, recovery and the letter |
| `/rules` | The rule catalog and the parameters the bank sets |
| `/evaluation` | The evaluation report: refund decisions, deadlines, privacy, prompt injections, the claim classifier |
| `/mcp` | MCP setup for Claude Desktop, Cursor and HTTP clients, and the tools the server offers |
| `/bank` | Demo Bank, the customer's phone app. `?client=CUST-DEMO-02` opens the second customer. |
| `/demo/delivery` | The fake courier page from the demo scam |

The old Romanian paths (`/cazuri`, `/cazuri/:id`, `/reguli`, `/evaluare`, `/banca`, `/demo/livrare`) redirect to the new ones, so printed QR codes keep working.

## Mock mode

The console switches to demo data by itself when `GET /api/meta` doesn't answer within 2.5 seconds or doesn't return JSON. To force it, run `npm run dev:mock` (it sets `VITE_MOCK=1`) or add `?mock=1` to the URL. The status at the bottom of the sidebar shows which mode you're in.

- State lives in `localStorage`, so tabs share it: Demo Bank, the case list and a case page open in different tabs see the same cases. One tab leads the runs; if you close it, another one takes over.
- "Run demo case" runs a case end to end in about 25 seconds: intake, evidence, decision (it waits for your approval when one is needed), recovery and the reply letter. Each fact gets a real SHA-256 hash, chained into a Merkle root with a QR code. Only the signature is simulated.
- The whole story: the fake courier page, a RON 3,200.00 payment in Demo Bank, "I didn't make this payment", the case starts, you approve it in the console, and the phone shows the refund.
- "Reset demo data" under the sidebar status clears everything. Deleting the `versoml.mock.*` keys from `localStorage` does the same.

All data is synthetic: made-up banks (BDEM, XBNK, YBNK), `.example` domains and customers with aliases. Reports in mock mode, such as the evaluation, carry a "Demo data" label.

## Structure

```
src/
  api/        types.ts (mirrors versoml/contracts.py), client.ts (one call per endpoint),
              sse.ts (EventSource with reconnects and de-duplication by seq),
              runtime.tsx (live or mock mode, useResource), format.ts (money, Bucharest time, labels)
  lib/        pipeline.ts (the case steps and how events map onto them), params.ts
  mocks/      store.ts (shared state), engine.ts (the scripted run), stories.ts (scenarios), fixtures.ts, ...
  ui/         kit.tsx (buttons, statuses, panels, tabs, empty and error states), Logo.tsx
  shell/      AppShell.tsx (sidebar and system status), PhoneDemo.tsx (QR codes)
  pages/      home/*, client/* (cases, case, rules, evaluation, MCP), demo/* (Demo Bank, fake courier page)
```

## What the UI expects from the backend

On top of the shapes in `src/api/types.ts`:

- SSE events carry a `step` equal to a node ID from `CaseDetail.pipeline`. The canonical IDs are in `src/lib/pipeline.ts`: `receptor`, `clasificator`, `ceasornicar`, `colector_tranzactie|sca|dispozitiv|domeniu`, `motor_reguli`, `rambursare`, `procuror`, `avocat`, `cantaritor`, `recuperare`, `redactor`, `filtru_zid`, `sigiliu`. When they don't match exactly, the UI tries the step's label and `agent`.
- `seq` goes up within a stream; the UI uses it to drop duplicates after a reconnect. Without `seq`, the event's content is the key.
- Optional: `STEP_FINISHED.data.status = "skipped" | "blocked"`, a `CUSTOM interrupt` event with `data.pending`, and `TEXT_MESSAGE_CONTENT` with `data.message_id` and `data.delta` for the live debate.
- Demo Bank also reads `GET /api/cases/{id}` (only `summary`) to show the dispute's status.
- The evidence check sends the `{case_id, facts, seal}` object from `GET /api/ledger/{id}` to `POST /api/verify`. "Export JSON" downloads the same object.
- `PUT /api/rules/params` gets only the changed keys. A 400 whose `detail` reads `key: reason; key2: reason` puts each reason under its field.
- `GET /api/eval` returns `var/eval/report.json`, or `{status: "missing", message}` until the first `uv run versoml eval --fast`. The page lists the client metrics from `sections`; the raw JSON stays one click away.
- `GET /api/rules`: rules in the `AML` pack or the `aml` zone, and `aml_*` parameters, aren't shown. `GET /api/mcp`: only client-zone tools are listed, and AML servers are left out of the configs people copy.
