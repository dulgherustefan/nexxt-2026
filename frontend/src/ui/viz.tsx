/**
 * Primitivele vizuale: inel, semicerc (gauge), bare, banda de avertizare, insigna de model.
 * SVG simplu, fără bibliotecă: se desenează la fel pe proiector și pe telefon.
 */
import type { ReactNode } from "react";
import { cx } from "./kit";

export type VizTone = "ink" | "ok" | "warn" | "danger" | "yellow" | "muted";

export const TONE_STROKE: Record<VizTone, string> = {
  ink: "var(--color-ink)",
  ok: "var(--color-ok)",
  warn: "var(--color-warn)",
  danger: "var(--color-danger)",
  yellow: "var(--color-yellow)",
  muted: "var(--color-line-strong)",
};

/** Inel de progres; `value` între 0 și 1. Conținutul stă în centru. */
export function Ring({ value, size = 140, stroke = 12, tone = "ink", track = "var(--color-hover)", children, label, className }: {
  value: number; size?: number; stroke?: number; tone?: VizTone; track?: string; children?: ReactNode; label?: string; className?: string;
}) {
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className={cx("relative inline-grid shrink-0 place-items-center", className)} style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={TONE_STROKE[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${c * v} ${c}`}
          style={{ transition: "stroke-dasharray 600ms cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

/** Semicerc de scor (0..1), cu acul colorat după prag. */
export function Gauge({ value, size = 160, label, sub, thresholds = [0.3, 0.7], className }: {
  value: number | null | undefined; size?: number; label?: ReactNode; sub?: ReactNode; thresholds?: [number, number]; className?: string;
}) {
  const v = value === null || value === undefined || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value));
  const w = size;
  const h = size * 0.62;
  const stroke = size * 0.1;
  const r = size / 2 - stroke / 2 - 2;
  const cx0 = w / 2;
  const cy0 = size / 2;
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from);
    const a1 = Math.PI * (1 - to);
    const x0 = cx0 + r * Math.cos(a0);
    const y0 = cy0 - r * Math.sin(a0);
    const x1 = cx0 + r * Math.cos(a1);
    const y1 = cy0 - r * Math.sin(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  const tone: VizTone = v === null ? "muted" : v >= thresholds[1] ? "danger" : v >= thresholds[0] ? "warn" : "ok";
  return (
    <div className={cx("inline-flex flex-col items-center", className)} role="img" aria-label={typeof label === "string" ? label : undefined}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        <path d={arc(0, thresholds[0])} stroke="var(--color-ok-line)" strokeWidth={stroke} fill="none" />
        <path d={arc(thresholds[0], thresholds[1])} stroke="var(--color-warn-line)" strokeWidth={stroke} fill="none" />
        <path d={arc(thresholds[1], 1)} stroke="var(--color-danger-line)" strokeWidth={stroke} fill="none" />
        {v !== null && v > 0 && <path d={arc(0, v)} stroke={TONE_STROKE[tone]} strokeWidth={stroke} fill="none" strokeLinecap="butt" style={{ transition: "d 600ms" }} />}
        {v !== null && (() => {
          const a = Math.PI * (1 - v);
          const x = cx0 + (r - stroke * 0.9) * Math.cos(a);
          const y = cy0 - (r - stroke * 0.9) * Math.sin(a);
          return <line x1={cx0} y1={cy0} x2={x} y2={y} stroke="var(--color-ink)" strokeWidth={3} strokeLinecap="round" />;
        })()}
        <circle cx={cx0} cy={cy0} r={5} fill="var(--color-ink)" />
      </svg>
      <div className="-mt-1 text-center leading-tight">
        <p className="display text-[1.9rem] font-black tabular-nums" style={{ color: TONE_STROKE[tone] }}>
          {v === null ? "—" : v.toFixed(2).replace(".", ",")}
        </p>
        {label && <p className="text-[0.8667rem] font-semibold">{label}</p>}
        {sub && <p className="text-[0.8rem] text-muted">{sub}</p>}
      </div>
    </div>
  );
}

/** Bară orizontală (0..1) cu etichetă. */
export function Bar({ value, tone = "ink", height = 8, className, title }: { value: number; tone?: VizTone; height?: number; className?: string; title?: string }) {
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <div className={cx("w-full overflow-hidden rounded-full bg-hover", className)} style={{ height }} title={title} aria-hidden>
      <div className="h-full rounded-full" style={{ width: `${v * 100}%`, background: TONE_STROKE[tone], transition: "width 600ms cubic-bezier(0.22,1,0.36,1)" }} />
    </div>
  );
}

/** Banda zonei AML: dungi galben-negru, cu textul pe o etichetă neagră. */
export function HazardBand({ children = "Zona AML · proces și bază de date separate", className }: { children?: ReactNode; className?: string }) {
  return (
    <div className={cx("hazard flex items-center px-3 py-1.5", className)} role="note">
      <span className="rounded-sm bg-ink px-2.5 py-0.5 text-[0.8rem] font-bold tracking-wide text-yellow">{children}</span>
    </div>
  );
}

export type ModelKind = "opus" | "sonnet" | "haiku" | "ml" | "human" | "none";

export function modelKind(m: string | null | undefined): ModelKind {
  const s = (m ?? "").toLowerCase();
  if (s.includes("opus")) return "opus";
  if (s.includes("sonnet")) return "sonnet";
  if (s.includes("haiku")) return "haiku";
  if (s === "ml" || s.startsWith("ml") || s.includes("m1") || s.includes("m5")) return "ml";
  if (s === "om" || s.includes("human") || s.includes("uman")) return "human";
  return "none";
}

const MODEL_STYLE: Record<ModelKind, { label: string; cls: string }> = {
  opus: { label: "Opus", cls: "bg-ink text-yellow border-ink" },
  sonnet: { label: "Sonnet", cls: "bg-ink-soft text-paper border-ink-soft" },
  haiku: { label: "Haiku", cls: "bg-paper text-ink border-ink" },
  ml: { label: "ML", cls: "bg-yellow text-ink border-ink" },
  human: { label: "om", cls: "bg-yellow-soft text-ink border-ink border-dashed" },
  none: { label: "fără LLM", cls: "bg-canvas text-muted border-line" },
};

export function ModelBadge({ model, className }: { model: string | null | undefined; className?: string }) {
  const k = modelKind(model);
  const st = MODEL_STYLE[k];
  return (
    <span className={cx("inline-flex h-[18px] items-center rounded-[4px] border px-1.5 text-[0.7rem] font-bold leading-none whitespace-nowrap", st.cls, className)} title={model ?? undefined}>
      {st.label}
    </span>
  );
}

/** Cifră mare cu etichetă: pentru KPI-uri. */
export function BigStat({ value, label, sub, tone = "ink", className }: { value: ReactNode; label: ReactNode; sub?: ReactNode; tone?: VizTone; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <p className="text-[0.8667rem] font-semibold text-muted">{label}</p>
      <p className="display mt-0.5 truncate text-[2.1rem] leading-none font-black tabular-nums" style={{ color: tone === "ink" ? undefined : TONE_STROKE[tone] }}>{value}</p>
      {sub && <p className="mt-1.5 text-[0.8667rem] text-ink-soft">{sub}</p>}
    </div>
  );
}

/** Tonul unui termen după fracția de timp rămasă din fereastră: semafor verde / chihlimbar / roșu. */
export function slaTone(fractionLeft: number | null, closed = false): VizTone {
  if (closed) return "ok";
  if (fractionLeft === null) return "muted";
  if (fractionLeft <= 0.2) return "danger";
  if (fractionLeft <= 0.5) return "warn";
  return "ok";
}
