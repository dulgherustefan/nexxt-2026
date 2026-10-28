import { CircleAlert, CircleCheck, ExternalLink, Minus, OctagonAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { OsintFinding, Signal } from "../../api/types";
import { Badge, cx, Dot, IdTag, Skeleton } from "../../ui/kit";
import { leadStatus, maskAccount, modeInfo, scoreLevel, SIGNAL_INFO, SIGNAL_ORDER, signalOf, toolLabel } from "./aml";
import { score as fmtScore } from "../../api/format";

// ------------------------------------------------------------------ tabele

export const TH = "h-10 whitespace-nowrap border-b border-line bg-canvas px-4 text-left text-[0.8667rem] font-semibold text-muted";
export const TD = "border-b border-line px-4 py-3 align-middle";

export function TableFrame({ label, minWidth = 720, children }: { label: string; minWidth?: number; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-paper">
      <table aria-label={label} className="w-full border-collapse [&_tbody_tr:last-child>td]:border-b-0" style={{ minWidth }}>
        {children}
      </table>
    </div>
  );
}

export function SkeletonRows({ rows = 4, cols }: { rows?: number; cols: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} aria-hidden>
          {Array.from({ length: cols }, (_, c) => (
            <td key={c} className={TD}>
              <Skeleton className={cx("h-4", c === 0 ? "w-28" : "w-20")} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Rândul întreg e clicabil, dar nu fură clicul de pe linkuri sau butoane din el. */
export function rowClick(go: () => void) {
  return (e: { target: EventTarget | null }) => {
    if (e.target instanceof Element && e.target.closest("a,button,input,select,textarea")) return;
    go();
  };
}

/** Datele vechi rămân pe ecran; doar anunțăm că ultima actualizare nu a mers. */
export function StaleNote({ error, every }: { error: unknown; every: string }) {
  if (!error) return null;
  return (
    <p role="status" className="mb-3 flex items-center gap-2 text-[0.8667rem] text-muted">
      <TriangleAlert aria-hidden className="size-4 text-danger" />
      Nu am putut actualiza datele; reîncerc automat la {every}. Afișez ultima versiune primită.
    </p>
  );
}

// ------------------------------------------------------------------ starea pistei

export function LeadStatusText({ status }: { status: string | null | undefined }) {
  const s = leadStatus(status);
  if (!s) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Dot tone={s.tone} live={s.live} />
      <span className={cx(s.tone === "danger" && "font-semibold text-danger", s.tone === "now" && "font-semibold")}>{s.label}</span>
    </span>
  );
}

export function LeadStatusBadge({ status }: { status: string | null | undefined }) {
  const s = leadStatus(status);
  if (!s) return null;
  return (
    <Badge tone={s.tone} icon={s.tone === "dark" ? undefined : <Dot tone={s.tone} live={s.live} className="size-2" />}>
      {s.label}
    </Badge>
  );
}

// ------------------------------------------------------------------ scorul M5

/** Număr + cuvânt; culoare doar pe nivelul ridicat, mereu împreună cu iconița și cuvântul. */
export function ScoreText({ score, label, unknown = false }: { score: number | null | undefined; label?: string | null; unknown?: boolean }) {
  const lvl = scoreLevel(score, label);
  if (unknown || !lvl || score === null || score === undefined) return <span className="text-muted">—</span>;
  const high = lvl.level === "high";
  return (
    <span className="inline-flex items-baseline gap-2 whitespace-nowrap">
      <span className={cx("font-semibold tabular-nums", high ? "text-danger" : lvl.level === "low" && "text-muted")}>{fmtScore(score)}</span>
      <span className={cx("inline-flex items-center gap-1 text-[0.8667rem]", high ? "font-semibold text-danger" : "text-muted")}>
        {high && <TriangleAlert aria-hidden className="size-3.5 self-center" />}
        {lvl.word}
      </span>
    </span>
  );
}

export function Account({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return <span className="text-muted">—</span>;
  return <span className={cx("font-mono text-[0.8667rem] whitespace-nowrap", className)}>{maskAccount(value)}</span>;
}

// ------------------------------------------------------------------ OSINT

const SIGNAL_ICON: Record<Signal, ReactNode> = {
  rosu: <OctagonAlert aria-hidden className="size-4 text-danger" />,
  galben: <CircleAlert aria-hidden className="size-4 text-ink-soft" />,
  neutru: <Minus aria-hidden className="size-4 text-subtle" />,
  verde: <CircleCheck aria-hidden className="size-4 text-ok" />,
};

export function SignalMark({ signal, withHint = false }: { signal: Signal; withHint?: boolean }) {
  const info = SIGNAL_INFO[signal];
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap font-semibold", signal === "rosu" && "text-danger", signal === "verde" && "text-ok")}>
      {SIGNAL_ICON[signal]}
      {info.label}
      {withHint && <span className="font-normal text-muted">· {info.hint}</span>}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: string | null | undefined }) {
  const m = modeInfo(mode);
  if (!m) return null;
  return (
    <Badge tone="neutral" title={m.title} className="font-medium">
      {m.label}
    </Badge>
  );
}

function hostOf(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.host : null;
  } catch {
    return null;
  }
}

export function SourceLink({ url }: { url: string | null | undefined }) {
  if (!url) return null;
  const host = hostOf(url);
  if (!host) return null;
  return (
    <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-[0.8667rem] font-semibold underline">
      Sursa: {host}
      <ExternalLink aria-hidden className="size-3.5" />
    </a>
  );
}

function FindingRow({ f, onCite, factTitle }: { f: OsintFinding; onCite?: (id: string) => void; factTitle?: (id: string) => string | undefined }) {
  const words = toolLabel(f.tool);
  return (
    <li className="grid gap-1 px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="font-semibold">{words ?? <span className="font-mono text-[0.9333rem]">{f.tool}</span>}</p>
        {words && <span className="font-mono text-[0.8667rem] text-muted">{f.tool}</span>}
        <span className="ml-auto flex items-center gap-2">
          {f.ok === false && <Badge tone="neutral">fără răspuns</Badge>}
          <ModeBadge mode={f.mode} />
        </span>
      </div>
      {f.target && <p className="font-mono text-[0.8667rem] text-ink-soft break-all">{f.target}</p>}
      {f.summary && <p className="text-ink">{f.summary}</p>}
      {(f.source_url || f.fact_id) && (
        <div className="mt-0.5 flex flex-wrap items-center gap-3">
          <SourceLink url={f.source_url} />
          {f.fact_id && (
            <IdTag onClick={onCite ? () => onCite(f.fact_id!) : undefined} title={factTitle?.(f.fact_id) ?? "Proba din registrul AML"}>
              {f.fact_id}
            </IdTag>
          )}
        </div>
      )}
    </li>
  );
}

/** Rezultatele grupate pe semnal: roșu → galben → neutru → verde. */
export function OsintGroups({ findings, onCite, factTitle }: {
  findings: OsintFinding[];
  onCite?: (id: string) => void;
  factTitle?: (id: string) => string | undefined;
}) {
  const groups = SIGNAL_ORDER.map((s) => ({ signal: s, items: findings.filter((f) => signalOf(f) === s) })).filter((g) => g.items.length);
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <section key={g.signal} aria-label={`${SIGNAL_INFO[g.signal].label}: ${g.items.length}`} className="overflow-hidden rounded-lg border border-line bg-paper">
          <header className="flex items-center gap-2 border-b border-line bg-canvas px-4 py-2 text-[0.9333rem]">
            <SignalMark signal={g.signal} withHint />
            <span className="ml-auto text-[0.8667rem] tabular-nums text-muted">{g.items.length}</span>
          </header>
          <ul className="divide-y divide-line">
            {g.items.map((f, i) => (
              <FindingRow key={`${f.tool}-${f.target}-${i}`} f={f} onCite={onCite} factTitle={factTitle} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function signalCounts(findings: OsintFinding[]): Record<Signal, number> {
  const out: Record<Signal, number> = { rosu: 0, galben: 0, neutru: 0, verde: 0 };
  for (const f of findings) out[signalOf(f)] += 1;
  return out;
}
