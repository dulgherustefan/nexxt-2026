# VersoML design

Two surfaces, one brand:

- **Homepage** (`src/pages/home`): dark graphite (`night*`) with Raiffeisen yellow `#FEE600` as the light in the room: the headline accent, the beams, the progress bars, the one yellow button (charcoal `#2B2D33` text). Motion-led: animated grid, beams from inputs into VersoML, a pinned scroll story, fingerprints that settle.
- **Console** (`/cases` and the rest): calm, after Mercury and Linear, in a light and a dark theme (the sun/moon toggle in the sidebar; the choice is saved, the system setting is the default). Quiet greys, statuses as a dot and a word, and Raiffeisen yellow on what a person acts on: the primary button, the active page in the sidebar, the "Waiting for you" lane, the step that needs you. The homepage stays dark and the Demo Bank pages stay light whatever the toggle says (`usePageTheme`).

The mark is a V split down the middle, each arm folded once like a ribbon so its darker back shows: the ink half is the case as reported, the yellow half is the verso, the side the bank has to prove (`src/ui/Logo.tsx`, `public/favicon.svg`).

Tokens live in `src/styles/index.css` (`@theme`). Primitives live in `src/ui/kit.tsx`; animated pieces live in `src/components/fx` (adapted from Magic UI, MIT). Use them; don't restyle them locally.

## Color

| Token | Value | Use |
|---|---|---|
| `ink` | `#121316` | text, primary button, active states |
| `ink-soft` / `muted` / `subtle` | `#2e3036` / `#5c5e66` / `#6f717a` | secondary text, labels, metadata |
| `line` / `line-strong` | `#e8e8ec` / `#d5d6dc` | hairlines, dividers |
| `paper` / `canvas` / `hover` | `#fff` / `#f7f7f8` / `#f1f1f4` | surfaces, sidebar, hover and selected rows |
| `yellow` (+ `-soft`, `-tint`) | `#fee600` (Raiffeisen) | console: "needs a person" dot, the live step, the proof path. Homepage: accents, beams, the main button. Never yellow text on a light background. |
| `ok` / `danger` / `warn` | `#127a47` / `#c4321d` / `#a8500d` | refunded/sealed, overdue/broken, warnings |
| `night*` | `#0f1012` … | homepage background, cards and text |

In the console, neutrals cover over 90% of every screen: no gradients, no glows, no colored icon tiles. The homepage may glow, but only in yellow and only behind content, never on it.

## Type

- Host Grotesk (variable, OFL, Element Type) for everything, IDs included: rule, evidence and case IDs use `id-text` (the text face with tabular digits). Fragment Mono (OFL) only for hashes, code and XML.
- Console: 15px root; body 0.9333rem (14px); metadata 0.8rem; page title 1.6rem semibold, tracking -0.02em.
- Homepage: H1 4.4rem semibold, tracking -0.04em; H2 2.6rem. The H1 never animates (it is the page's largest paint).
- Tabular figures (`tnum`) in tables, lists and countdowns only. Big display numbers use proportional figures.
- Weights 400 / 500 / 600 only. Sentence case.

## Shape and depth

- Radius: 8px controls, 12px cards and panels, 16–22px only for the homepage showcase.
- Cards use `shadow-[var(--shadow-card)]` (a 1px ring plus a faint drop), not borders. Floating layers use `--shadow-overlay`.
- Buttons are pills (`rounded-full`): `primary` = yellow with `on-yellow` text, `secondary` = paper with the card ring. One primary per view.

## Components and patterns

- Status: `<Status tone>` (6–8px dot + word). Pills (`<Badge>`) only when a row needs a second state.
- Lists: rows 48–56px, a 36px avatar or icon tile on the left, title + muted second line, amount right-aligned in `tnum`. Hover = `bg-hover`.
- Needs a person: `<Banner tone="now">`: yellow-tint card with a live dot, one sentence saying why, one primary action. On a case page the same buttons follow you in the step bar (and at the bottom of a phone screen) once the banner scrolls away.

## Console structure

- **Sidebar:** New case, then Cases; "What decides" (Rules, Knowledge); "Trust and setup" (Evaluation, MCP); "Try it as the customer" (Demo Bank, the fake courier page, QR codes).
- **Cases:** four lanes that are also the filters: Waiting for you (yellow when it has cases), Due within 24 h, In progress, Closed (with the amount refunded). Click a lane again for all cases. The list is sorted by urgency.
- **A case:** one page in the order the case happens: what the customer reported, the refund decision (rules and deadlines folded under it), getting the money back, the letter, the evidence file (six items, then "Show all"; the seal and "Verify integrity" on top). A sticky step bar names the five parts with where each stands and jumps to it. The agents, "Change a fact" and similar past cases sit in the right column.
- Deadlines: `<DeadlineText>` says "Due tomorrow, 23:59"; the full date is in the tooltip. Never write "T+1" in the UI.
- Empty states: say what's missing and offer one action ("No cases yet. Run a sample case.").
- Citations: numbered markers in the text (a small hairline tag, like an ID) jump to the source list; each source shows its kind, source, confidence word with the mark ([P], [S], [U]) and rule IDs, and opens the full passage in a side sheet. "Why this result" stays folded.
- Optional detail (other candidates, similar past cases, the router's reasons) starts folded or lives in the trace sheet. Past cases always say they are information, not a decision input.
- Errors: say what happened and what to do. No "please", no "sorry", no "successfully".

## Agent work, shown minimally

Three levels:
1. While running: one status line ("Collecting evidence · 2.4 s") and five phase segments.
2. When done: one line ("Agents finished · 16 steps · 58 s") with "View trace".
3. The full step list (model names, timings) opens in a side sheet on request.

## Motion

- CSS transitions for hovers (120–150ms) and presses (`press` utility: scale 0.97). Enter animations 200–260ms, `--ease-out`. Sheets 280ms, `--ease-drawer`.
- No animation on frequent actions (keyboard, row hover beyond color, approve-then-next).
- The homepage uses Motion (`LazyMotion` + `m`, features loaded on demand): the grid cells and the beams in the hero, the pinned scroll story (steps follow the scroll, the product card changes scene), the evidence fingerprints and the tamper switch, the recovery rows, the result counters. Every loop pauses off screen; with reduced motion everything renders in its final state.
- Respect `prefers-reduced-motion` (global CSS rule + `MotionConfig reducedMotion="user"`).

## Writing

US spelling, plain words, active voice. Money as `RON 3,200.00`. Dates as `29 Oct 2026, 23:59` (Bucharest time). Buttons are verb + noun ("Approve refund", "Run a sample case"). Say who acts: "The rules decided", "A person approved". No em dashes, no "seamless", no "not just X but Y".
