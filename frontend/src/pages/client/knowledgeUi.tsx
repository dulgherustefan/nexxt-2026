/**
 * Knowledge passages, wherever they show up: the Knowledge page, the legal basis of a case and
 * its precedents. One row, one passage sheet, one way to show numbered citations.
 */
import { useState, type ReactNode } from "react";
import type { KbHit, KbWhy } from "../../api/types";
import { cx, IdTag, KeyValues, Status, type Tone } from "../../ui/kit";
import { Sheet } from "./caseUi";

const KIND: Record<string, string> = {
  rule: "Rule",
  law: "Law",
  guidance: "Guidance",
  typology: "Typology",
  case_study: "Case study",
  precedent: "Past case",
};

export function kindLabel(kind: string | null | undefined): string {
  return KIND[String(kind)] ?? String(kind ?? "Passage").replace(/_/g, " ");
}

const CONFIDENCE: Record<string, { word: string; tone: Tone; explain: string }> = {
  P: { word: "Official text", tone: "dark", explain: "Read in the official legal text." },
  S: { word: "Secondary source", tone: "neutral", explain: "Taken from a secondary source, such as a guide or a scheme summary." },
  U: { word: "Unverified", tone: "warn", explain: "An inference or a proposal. Confirm it before relying on it." },
};

/** The confidence mark: the word, then the mark itself ([P], [S], [U]) as the rule docs write it. */
export function ConfidenceMark({ mark }: { mark: string | null | undefined }) {
  const c = mark ? CONFIDENCE[mark] : undefined;
  if (!c) return null;
  return (
    <span title={c.explain}>
      <Status tone={c.tone}>
        {c.word}
        <span className="id-text font-normal text-subtle">[{mark}]</span>
      </Status>
    </span>
  );
}

function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

/** Why the search put this passage here: its keyword rank, its meaning rank and the fused score. */
export function whySentence(why: KbWhy | null | undefined): string {
  if (!why) return "No ranking details.";
  const parts = [
    typeof why.bm25_rank === "number" ? `Keyword search (BM25) ranked it ${ordinal(why.bm25_rank)}.` : "No keyword match (BM25).",
    why.dense === false
      ? "Meaning search is off."
      : typeof why.dense_rank === "number"
        ? `Meaning search (dense) ranked it ${ordinal(why.dense_rank)}.`
        : "Meaning search (dense) didn't rank it.",
    typeof why.rrf === "number" ? `Combined score ${why.rrf.toFixed(4)} (RRF).` : "",
  ];
  return parts.filter(Boolean).join(" ");
}

function WhyToggle({ why }: { why: KbWhy }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="text-[0.8rem] font-medium text-muted underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink"
      >
        Why this result
      </button>
      {open && <p className="basis-full text-[0.8rem] text-muted">{whySentence(why)}</p>}
    </>
  );
}

/** One passage in a list. `index` shows the citation number used in an answer. */
export function HitRow({ hit, index, onOpen, flash, showWhy = true, extra }: {
  hit: KbHit; index?: number; onOpen: (hit: KbHit) => void; flash?: boolean; showWhy?: boolean; extra?: ReactNode;
}) {
  return (
    <li id={index ? `citation-${index}` : undefined} className={cx("flex scroll-mt-24 gap-3 px-5 py-4", flash && "animate-flash")}>
      {index !== undefined && (
        <span className="id-text mt-0.5 grid h-6 min-w-6 shrink-0 place-items-center rounded-md bg-paper px-1 text-[0.8rem] font-medium text-ink-soft ring-1 ring-inset ring-line">
          {index}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[0.8rem] text-muted">
          <span className="font-medium text-ink-soft">{kindLabel(hit.kind)}</span>
          {hit.source ? <> · {hit.source}</> : null}
        </p>
        <button type="button" onClick={() => onOpen(hit)} className="mt-0.5 text-left font-medium leading-snug hover:underline hover:underline-offset-2">
          {hit.title}
        </button>
        <p className="mt-1 line-clamp-2 text-[0.9333rem] text-ink-soft">{hit.text}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <ConfidenceMark mark={hit.confidence} />
          {hit.rule_ids?.length ? <span className="flex flex-wrap gap-1">{hit.rule_ids.slice(0, 4).map((r) => <IdTag key={r}>{r}</IdTag>)}</span> : null}
          {extra}
          {showWhy && hit.why && Object.keys(hit.why).length > 0 && <WhyToggle why={hit.why} />}
        </div>
      </div>
    </li>
  );
}

export function HitList({ children, label }: { children: ReactNode; label: string }) {
  return (
    <ul aria-label={label} className="divide-y divide-line overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      {children}
    </ul>
  );
}

/** The full passage, in a side sheet. `note` says how the case used it. */
export function PassageSheet({ hit, onClose, note }: { hit: KbHit; onClose: () => void; note?: ReactNode }) {
  return (
    <Sheet title={hit.title} description={`${kindLabel(hit.kind)}${hit.source ? ` · ${hit.source}` : ""}`} onClose={onClose}>
      {note && <p className="mb-4 rounded-xl bg-canvas px-4 py-3 text-[0.9333rem] text-ink-soft">{note}</p>}
      <p className="text-[0.9667rem] leading-relaxed whitespace-pre-wrap">{hit.text}</p>
      <div className="mt-6 border-t border-line pt-4 text-[0.9333rem]">
        <KeyValues rows={[
          hit.confidence ? ["Confidence", <ConfidenceMark mark={hit.confidence} />] : null,
          hit.rule_ids?.length ? ["Rules", <span className="flex flex-wrap gap-1">{hit.rule_ids.map((r) => <IdTag key={r}>{r}</IdTag>)}</span>] : null,
          hit.why && Object.keys(hit.why).length ? ["Why this result", <span className="text-ink-soft">{whySentence(hit.why)}</span>] : null,
          ["Passage ID", <span className="id-text text-[0.8667rem] text-muted">{hit.id}</span>],
        ]} />
      </div>
    </Sheet>
  );
}

/** A citation marker inside text: a small numbered tag that opens or scrolls to its source. */
export function Marker({ n, onClick, title }: { n: number; onClick: (n: number) => void; title?: string }) {
  return (
    <button
      type="button"
      onClick={() => onClick(n)}
      title={title ?? `Source ${n}`}
      aria-label={`Source ${n}${title ? `: ${title}` : ""}`}
      className="id-text ml-1 inline-grid h-[1.15rem] min-w-[1.15rem] place-items-center rounded px-1 align-[0.12em] text-[0.7rem] leading-none font-medium text-muted ring-1 ring-inset ring-line transition-colors hover:text-ink hover:ring-line-strong"
    >
      {n}
    </button>
  );
}

/** Answer text with [1], [2] or [1, 2] markers turned into clickable citations. */
export function CitedText({ text, onMarker, titles }: { text: string; onMarker: (n: number) => void; titles?: Array<string | undefined> }) {
  const parts: ReactNode[] = [];
  const re = /\[(\d+(?:\s*[,;]\s*\d+)*)\]/g;
  let at = 0;
  let k = 0;
  for (const m of text.matchAll(re)) {
    const i = m.index ?? 0;
    if (i > at) parts.push(text.slice(at, i).replace(/\s+$/, ""));
    for (const raw of m[1].split(/[,;]/)) {
      const n = Number(raw.trim());
      if (Number.isFinite(n) && n > 0) parts.push(<Marker key={`m${k++}`} n={n} onClick={onMarker} title={titles?.[n - 1]} />);
    }
    at = i + m[0].length;
  }
  parts.push(text.slice(at));
  return <>{parts}</>;
}

/** Inline source chips, e.g. under a letter: "Law 209/2019, art. 173". */
export function SourceChips({ hits, onOpen, label = "Legal sources" }: { hits: KbHit[]; onOpen: (h: KbHit) => void; label?: string }) {
  if (!hits.length) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 text-muted">
      {label}
      {hits.map((h, i) => (
        <span key={h.id} className="inline-flex items-center gap-x-1.5">
          {i > 0 && <span aria-hidden className="text-subtle">·</span>}
          <button
            type="button"
            onClick={() => onOpen(h)}
            title={h.title}
            className="rounded text-[0.8667rem] text-ink-soft underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink"
          >
            {h.source || h.title}
          </button>
        </span>
      ))}
    </span>
  );
}
