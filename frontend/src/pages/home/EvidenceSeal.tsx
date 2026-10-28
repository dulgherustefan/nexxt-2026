import { SealCheck, SealWarning } from "@phosphor-icons/react";
import { m, useInView, useReducedMotion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { canonical, sha256 } from "../../mocks/sha256";
import { cx } from "../../ui/kit";
import { useScramble } from "./useScramble";

const EASE = [0.22, 1, 0.36, 1] as const;
const ROW = 56;

const STATEMENT = "I did not authorize the payment of RON 3,200.00 on 28 Oct at 18:31.";
const TAMPERED = "I did authorize the payment of RON 3,200.00 on 28 Oct at 18:31.";

const ITEMS = [
  { id: "EV-001", label: "Transaction record", source: "core banking", content: { amount: 3200, currency: "RON", merchant: "Nova Electro Online", at: "2026-10-28T18:31:07+02:00" } },
  { id: "EV-002", label: "3-D Secure log", source: "card authentication", content: { eci: "07", cavv: null, challenge: "none" } },
  { id: "EV-003", label: "Device session", source: "device history", content: { device: "unknown", first_seen: "2026-10-28T18:29:44+02:00" } },
  { id: "EV-004", label: "Website check", source: "RDAP and certificate logs", content: { domain: "nova-courier.example", registered_hours_before: 6 } },
  { id: "EV-005", label: "Customer statement", source: "banking app", content: { text: STATEMENT } },
  { id: "EV-006", label: "Rule decision", source: "rules engine", content: { rule: "PAY-03", outcome: "refund_due" } },
];

/** All Merkle levels, pairing left to right and repeating the last node when a level is odd. */
function levels(leaves: string[]): string[][] {
  const out = [leaves];
  while (out[out.length - 1].length > 1) {
    const prev = out[out.length - 1];
    const next: string[] = [];
    for (let i = 0; i < prev.length; i += 2) next.push(sha256(prev[i] + (prev[i + 1] ?? prev[i])));
    out.push(next);
  }
  return out;
}

/** Indices of the nodes from a leaf up to the root (one per level). */
function pathOf(leaf: number, depth: number): number[] {
  const p: number[] = [];
  let i = leaf;
  for (let d = 0; d < depth; d++) {
    p.push(i);
    i = Math.floor(i / 2);
  }
  return p;
}

const short = (h: string) => `${h.slice(0, 8)}…${h.slice(-4)}`;

export default function EvidenceSeal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const reduce = useReducedMotion();
  const play = inView && !reduce;
  const [tampered, setTampered] = useState(false);
  const [focus, setFocus] = useState<number | null>(null);

  const sealed = useMemo(() => levels(ITEMS.map((it) => sha256(canonical(it.content)))), []);
  const current = useMemo(
    () => levels(ITEMS.map((it) => sha256(canonical(it.id === "EV-005" && tampered ? { text: TAMPERED } : it.content)))),
    [tampered],
  );
  const depth = current.length;
  const rootOk = current[depth - 1][0] === sealed[depth - 1][0];
  const brokenPath = tampered ? pathOf(4, depth) : [];
  const litPath = focus !== null ? pathOf(focus, depth) : [];

  // Geometry: leaves sit on the evidence rows; each level moves right.
  const H = ITEMS.length * ROW;
  const ys: number[][] = [];
  current.forEach((lvl, d) => {
    if (d === 0) ys.push(lvl.map((_, i) => i * ROW + ROW / 2));
    else {
      const prev = ys[d - 1];
      ys.push(lvl.map((_, i) => (prev[2 * i] + (prev[2 * i + 1] ?? prev[2 * i])) / 2));
    }
  });
  const X = (d: number) => 12 + d * 64;

  const lineState = (d: number, i: number) =>
    brokenPath[d] === i && brokenPath[d + 1] === Math.floor(i / 2) ? "broken" : litPath[d] === i && litPath[d + 1] === Math.floor(i / 2) ? "lit" : "idle";
  const nodeState = (d: number, i: number) => (brokenPath[d] === i ? "broken" : litPath[d] === i ? "lit" : "idle");

  return (
    <div ref={ref} className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
      <ul className="divide-y divide-night-line rounded-2xl bg-night-2 ring-1 ring-night-line" onMouseLeave={() => setFocus(null)}>
        {ITEMS.map((it, i) => (
          <EvidenceItem
            key={it.id}
            index={i}
            item={it}
            hash={current[0][i]}
            changed={tampered && it.id === "EV-005"}
            play={play}
            active={focus === i}
            onFocus={() => setFocus(i)}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-4">
        <svg viewBox={`0 0 ${X(depth - 1) + 24} ${H}`} className="hidden h-[336px] w-auto lg:block" role="img" aria-label={`Merkle tree of ${ITEMS.length} evidence items. ${rootOk ? "The root matches the signed seal." : "The root no longer matches the signed seal."}`}>
          {current.slice(0, -1).map((lvl, d) =>
            lvl.map((_, i) => {
              const s = lineState(d, i);
              const x1 = X(d);
              const y1 = ys[d][i];
              const x2 = X(d + 1);
              const y2 = ys[d + 1][Math.floor(i / 2)];
              const mid = (x1 + x2) / 2;
              return (
                <m.path
                  key={`${d}-${i}`}
                  d={`M${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  strokeWidth={s === "idle" ? 1 : 1.75}
                  className={cx("transition-[stroke] duration-200", s === "broken" ? "stroke-[#ff6b55]" : s === "lit" ? "stroke-yellow" : "stroke-white/20")}
                  initial={{ pathLength: play ? 0 : 1 }}
                  animate={{ pathLength: inView || reduce ? 1 : 0 }}
                  transition={{ duration: 0.3, ease: EASE, delay: play ? 0.9 + d * 0.25 : 0 }}
                />
              );
            }),
          )}
          {current.map((lvl, d) =>
            lvl.map((_, i) => {
              const s = nodeState(d, i);
              const root = d === depth - 1;
              return (
                <circle
                  key={`n${d}-${i}`}
                  cx={X(d)}
                  cy={ys[d][i]}
                  r={root ? 6 : 3.5}
                  className={cx(
                    "transition-[fill] duration-200",
                    s === "broken" || (root && !rootOk) ? "fill-[#ff6b55]" : s === "lit" || (root && focus !== null) ? "fill-yellow" : root ? "fill-white" : "fill-white/45",
                  )}
                />
              );
            }),
          )}
        </svg>

        <div aria-live="polite" className={cx("rounded-xl px-4 py-3 ring-1 transition-colors duration-200", rootOk ? "bg-white/[0.04] ring-night-line" : "bg-[#ff6b55]/10 ring-[#ff6b55]/40")}>
          <p className="flex items-center gap-2 text-[0.9333rem] font-medium">
            {rootOk ? <SealCheck size={18} className="text-[#7ee2a8]" /> : <SealWarning size={18} className="text-[#ff8a78]" />}
            {rootOk ? "Sealed · signature valid" : "Root mismatch · signature invalid"}
          </p>
          <p className="mt-1 font-mono text-[0.72rem] break-all text-night-muted">root {short(current[depth - 1][0])}</p>
          {!rootOk && <p className="mt-1 text-[0.8rem] text-[#ffb3a8]">EV-005 changed after it was sealed.</p>}
        </div>

        <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl px-4 py-3 ring-1 ring-night-line transition-colors hover:bg-white/[0.04]">
          <span className="text-[0.9333rem]">
            Change one word
            <span className="block text-[0.8rem] text-night-muted">“did not” becomes “did”</span>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={tampered}
            onClick={() => setTampered((t) => !t)}
            className={cx("relative h-6 w-10 shrink-0 rounded-full transition-colors duration-200", tampered ? "bg-[#ff6b55]" : "bg-white/20")}
          >
            <span className={cx("absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform duration-200 ease-[var(--ease-out)]", tampered && "translate-x-4")} />
            <span className="sr-only">Change one word in the customer’s statement</span>
          </button>
        </label>
      </div>
    </div>
  );
}

function EvidenceItem({ index, item, hash, changed, play, active, onFocus }: {
  index: number; item: (typeof ITEMS)[number]; hash: string; changed: boolean; play: boolean; active: boolean; onFocus: () => void;
}) {
  const shown = useScramble(short(hash), play, { delay: index * 70, spin: 240, perChar: 18 });
  return (
    <li
      tabIndex={0}
      onMouseEnter={onFocus}
      onFocus={onFocus}
      style={{ height: ROW }}
      className={cx("flex items-center gap-4 px-4 outline-none transition-colors duration-150 focus-visible:bg-white/[0.06]", active && "bg-white/[0.04]")}
    >
      <span className="id-text w-14 shrink-0 text-[0.8rem] text-night-muted">{item.id}</span>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-[0.9333rem] text-night-text">{item.label}</p>
        <p className="truncate text-[0.75rem] text-night-muted">{item.source}</p>
      </div>
      <span className={cx("font-mono text-[0.75rem] transition-colors duration-200", changed ? "text-[#ff8a78]" : active ? "text-yellow" : "text-night-muted")}>
        <span aria-hidden>{shown}</span>
        <span className="sr-only">{short(hash)}</span>
      </span>
    </li>
  );
}
