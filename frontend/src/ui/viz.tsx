/**
 * Primitivele vizuale: inel, semicerc (gauge), bară, banda zonei AML, eticheta de model.
 * SVG simplu, fără bibliotecă; fiecare arată o valoare reală, nimic decorativ.
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
export function Ring({ value, size = 96, stroke = 8, tone = "ink", track = "var(--color-hover)", children, label, className }: {
  value: number; size?: number; stroke?: number; tone?: VizTone; track?: string; children?: ReactNode; label?: string; className?: string;
}) {
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className={cx("relative inline-grid shrink-0 place-items-center", className)} style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={TONE_STROKE[tone]} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${c * v} ${c}`} style={{ transition: "stroke-dasharray 500ms cubic-bezier(0.22,1,0.36,1)" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

function gaugeTone(v: number | null, thresholds: [number, number]): VizTone {
  return v === null ? "muted" : v >= thresholds[1] ? "danger" : v >= thresholds[0] ? "warn" : "ok";
}

/** Semicerc de scor (0..1). Mic: un arc subțire și cifra dedesubt. */
export function Gauge({ value, size = 120, label, sub, thresholds = [0.3, 0.7], className }: {
  value: number | null | undefined; size?: number; label?: ReactNode; sub?: ReactNode; thresholds?: [number, number]; className?: string;
}) {
  const v = value === null || value === undefined || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value));
  const w = size;
  const stroke = Math.max(6, size * 0.07);
  const r = size / 2 - stroke / 2 - 1;
  const h = r + stroke + 2;
  const cx0 = w / 2;
  const cy0 = r + stroke / 2 + 1;
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from);
    const a1 = Math.PI * (1 - to);
    return `M ${cx0 + r * Math.cos(a0)} ${cy0 - r * Math.sin(a0)} A ${r} ${r} 0 0 1 ${cx0 + r * Math.cos(a1)} ${cy0 - r * Math.sin(a1)}`;
  };
  const tone = gaugeTone(v, thresholds);
  return (
    <div className={cx("inline-flex flex-col items-center", className)} role="img" aria-label={typeof label === "string" ? `${label}: ${v === null ? "necunoscut" : v.toFixed(2)}` : undefined}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        <path d={arc(0, 1)} stroke="var(--color-hover)" strokeWidth={stroke} fill="none" strokeLinecap="round" />
        {v !== null && v > 0 && <path d={arc(0, Math.max(v, 0.02))} stroke={TONE_STROKE[tone]} strokeWidth={stroke} fill="none" strokeLinecap="round" />}
      </svg>
      <div className="-mt-[0.9em] text-center leading-tight">
        <p className="text-[1.25rem] font-semibold tabular-nums" style={{ color: TONE_STROKE[tone] }}>{v === null ? "—" : v.toFixed(2).replace(".", ",")}</p>
        {label && <p className="mt-0.5 text-[0.8rem] text-muted">{label}</p>}
        {sub && <p className="text-[0.75rem] text-muted">{sub}</p>}
      </div>
    </div>
  );
}

/** Bară orizontală (0..1). */
export function Bar({ value, tone = "ink", height = 6, className, title }: { value: number; tone?: VizTone; height?: number; className?: string; title?: string }) {
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <div className={cx("w-full overflow-hidden rounded-full bg-hover", className)} style={{ height }} title={title} aria-hidden>
      <div className="h-full rounded-full" style={{ width: `${v * 100}%`, background: TONE_STROKE[tone], transition: "width 500ms cubic-bezier(0.22,1,0.36,1)" }} />
    </div>
  );
}

/** Banda zonei AML: o fâșie subțire și un rând de text liniștit. */
export function HazardBand({ children = "Zona AML · date separate", className }: { children?: ReactNode; className?: string }) {
  return (
    <div className={cx("bg-paper", className)} role="note">
      <div className="hazard-thin h-[3px]" aria-hidden />
      <p className="border-b border-line bg-canvas px-4 py-1 text-[0.8rem] font-medium text-ink-soft sm:px-6">{children}</p>
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

const MODEL_LABEL: Record<ModelKind, string> = { opus: "Opus", sonnet: "Sonnet", haiku: "Haiku", ml: "ML", human: "om", none: "reguli" };

export function ModelBadge({ model, className }: { model: string | null | undefined; className?: string }) {
  const k = modelKind(model);
  return (
    <span className={cx("inline-flex h-[18px] items-center rounded-[4px] border px-1.5 text-[0.7rem] font-medium leading-none whitespace-nowrap",
      k === "none" ? "border-line bg-paper text-muted" : "border-line-strong bg-canvas text-ink-soft", className)} title={model ?? undefined}>
      {MODEL_LABEL[k]}
    </span>
  );
}

/** Cifră cu etichetă. */
export function BigStat({ value, label, sub, tone = "ink", className }: { value: ReactNode; label: ReactNode; sub?: ReactNode; tone?: VizTone; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <p className="text-[0.8667rem] text-muted">{label}</p>
      <p className="mt-1 truncate text-[1.5rem] leading-none font-semibold tabular-nums" style={{ color: tone === "ink" ? undefined : TONE_STROKE[tone] }}>{value}</p>
      {sub && <p className="mt-1.5 text-[0.8667rem] text-muted">{sub}</p>}
    </div>
  );
}

/** Tonul unui termen după fracția de timp rămasă din fereastră. */
export function slaTone(fractionLeft: number | null, closed = false): VizTone {
  if (closed) return "ok";
  if (fractionLeft === null) return "muted";
  if (fractionLeft <= 0.2) return "danger";
  if (fractionLeft <= 0.5) return "warn";
  return "ok";
}
