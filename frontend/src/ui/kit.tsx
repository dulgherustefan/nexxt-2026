import { AlertTriangle, Check, ChevronDown, ChevronRight, CircleSlash, Clock3, Hand, Loader2, X } from "lucide-react";
import {
  Component,
  createContext,
  useContext,
  forwardRef,
  type ButtonHTMLAttributes,
  type ErrorInfo,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- butoane

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-yellow text-ink border-yellow-line hover:bg-yellow-hover",
  secondary: "bg-paper text-ink border-line-strong hover:bg-hover",
  ghost: "bg-transparent text-ink-soft border-transparent hover:bg-hover hover:text-ink",
  danger: "bg-paper text-danger border-danger-line hover:bg-danger-soft",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  icon?: ReactNode;
  busy?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, busy, disabled, className, children, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md border font-semibold whitespace-nowrap transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-[0.8667rem]" : "h-10 px-4 text-[0.9333rem]",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- stări (un singur set în toată aplicația)

export type Tone = "neutral" | "now" | "ok" | "danger" | "dark";

const TONES: Record<Tone, string> = {
  neutral: "bg-canvas text-ink-soft border-line",
  now: "bg-yellow-soft text-ink border-yellow-line",
  ok: "bg-ok-soft text-ok border-ok-line",
  danger: "bg-danger-soft text-danger border-danger-line",
  dark: "bg-ink text-paper border-ink",
};

/** Pastila de stare: un cuvânt, o culoare. */
export function Badge({ tone = "neutral", icon, children, className, title }: {
  tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[0.8rem] font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** Punctul de stare: se animă doar cât ceva rulează. */
export function Dot({ tone = "neutral", live = false, className }: { tone?: Tone; live?: boolean; className?: string }) {
  const color = { neutral: "bg-line-strong", now: "bg-yellow ring-1 ring-yellow-line", ok: "bg-ok", danger: "bg-danger", dark: "bg-ink" }[tone];
  return <span aria-hidden className={cx("inline-block size-2 shrink-0 rounded-full", color, live && "animate-pulse-dot", className)} />;
}

/** ID-uri: reguli, probe, cazuri, hash-uri. Mono, mici, secundare. */
export function IdTag({ children, onClick, title, tone = "neutral" }: {
  children: ReactNode; onClick?: () => void; title?: string; tone?: "neutral" | "now";
}) {
  const cls = cx(
    "inline-flex h-5 items-center rounded-[4px] border px-1.5 font-mono text-[0.75rem] tabular-nums whitespace-nowrap text-ink-soft",
    tone === "now" ? "border-yellow-line bg-yellow-soft" : "border-line bg-canvas",
    onClick && "cursor-pointer hover:border-line-strong hover:bg-yellow-tint hover:text-ink",
  );
  return onClick ? (
    <button type="button" className={cls} onClick={onClick} title={title}>{children}</button>
  ) : (
    <span className={cls} title={title}>{children}</span>
  );
}

// ---------------------------------------------------------------- containere

export function Panel({ title, actions, children, className, bodyClassName, id }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string; id?: string;
}) {
  return (
    <section id={id} className={cx("rounded-lg border border-line bg-paper", className)}>
      {(title || actions) && (
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-line px-4 py-2">
          {title && <h2 className="text-[0.9333rem] font-semibold">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Pagină afișată ca filă în „Sistem”: titlul devine mai mic, iar pagina nu mai are h1. */
export const EmbeddedPage = createContext(false);

export function PageHeader({ title, description, actions, children }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode;
}) {
  const embedded = useContext(EmbeddedPage);
  if (embedded) {
    return (
      <div className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="sr-only">{title}</h2>
            {description && <p className="max-w-[72ch] text-[0.9333rem] text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
        {children}
      </div>
    );
  }
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[1.4rem] leading-tight font-semibold">{title}</h1>
          {description && <p className="mt-1 max-w-[70ch] text-[0.9333rem] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

/** Firul paginii: „Contestații / CT-2026-…”. */
export function Breadcrumb({ items }: { items: Array<{ label: ReactNode; to?: string }> }) {
  return (
    <nav aria-label="Firul paginii" className="mb-4 flex min-w-0 items-center gap-1.5 text-[0.8667rem] text-muted">
      {items.map((it, i) => (
        <span key={i} className="flex min-w-0 items-center gap-1.5">
          {i > 0 && <ChevronRight aria-hidden className="size-3.5 shrink-0 text-subtle" />}
          {it.to ? (
            <Link to={it.to} className="font-medium text-ink-soft hover:text-ink hover:underline">{it.label}</Link>
          ) : (
            <span aria-current="page" className="truncate font-mono text-[0.8rem] text-ink">{it.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function Banner({ tone = "now", icon, title, children, actions }: {
  tone?: "now" | "danger" | "neutral" | "ok"; icon?: ReactNode; title: ReactNode; children?: ReactNode; actions?: ReactNode;
}) {
  const styles = {
    now: "border-yellow-line bg-yellow-tint",
    danger: "border-danger-line bg-danger-soft",
    neutral: "border-line bg-canvas",
    ok: "border-ok-line bg-ok-soft",
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border px-4 py-3", styles)}>
      {icon && <span className="shrink-0">{icon}</span>}
      <div className="min-w-[14rem] flex-1">
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-0.5 text-[0.9333rem] text-ink-soft">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action, icon }: { title: ReactNode; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-line-strong px-6 py-8">
      {icon && <span className="text-muted">{icon}</span>}
      <div>
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-1 max-w-[60ch] text-[0.9333rem] text-muted">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ error, onRetry, what = "datele" }: { error: unknown; onRetry?: () => void; what?: string }) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return (
    <Banner tone="danger" icon={<AlertTriangle aria-hidden className="size-5 text-danger" />}
      title={`Nu am putut încărca ${what}.`}
      actions={onRetry && <Button size="sm" onClick={onRetry}>Încearcă din nou</Button>}>
      {message ? `Motiv: ${message}` : "Serverul nu a răspuns."}
    </Banner>
  );
}

export function Loading({ label = "Se încarcă…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-[0.9333rem] text-muted">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-md bg-hover", className)} />;
}

// ---------------------------------------------------------------- cifre de sus (cel mult trei)

export function StatStrip({ items }: { items: Array<{ label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: "ink" | "now" | "ok" | "danger" } | null> }) {
  const list = items.filter(Boolean) as Array<{ label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: "ink" | "now" | "ok" | "danger" }>;
  return (
    <dl className="grid overflow-hidden rounded-lg border border-line sm:grid-cols-3">
      {list.map((s, i) => (
        <div key={i} className={cx("px-5 py-4", i > 0 && "border-t border-line sm:border-t-0 sm:border-l")}>
          <dt className="text-[0.8667rem] text-muted">{s.label}</dt>
          <dd className="mt-1 flex items-baseline gap-2">
            <span className={cx("text-[1.6rem] leading-none font-semibold tabular-nums", s.tone === "danger" && "text-danger", s.tone === "ok" && "text-ok")}>
              {s.tone === "now" && <span aria-hidden className="mr-2 inline-block size-2 -translate-y-1 rounded-full bg-yellow ring-1 ring-yellow-line" />}
              {s.value}
            </span>
            {s.sub && <span className="text-[0.8667rem] text-muted">{s.sub}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------- taburi și comutatoare

export function Tabs<T extends string>({ tabs, value, onChange, label, className }: {
  tabs: Array<{ id: T; label: ReactNode; count?: number }>; value: T; onChange: (id: T) => void; label: string; className?: string;
}) {
  const base = useId();
  return (
    <div role="tablist" aria-label={label} className={cx("flex gap-5 overflow-x-auto overflow-y-hidden border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", className)}>
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            id={`${base}-${t.id}`}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={cx(
              "relative -mb-px flex h-10 items-center gap-2 border-b-2 text-[0.9333rem] whitespace-nowrap transition-colors",
              active ? "border-ink font-semibold text-ink" : "border-transparent font-medium text-muted hover:text-ink",
            )}
          >
            {t.label}
            {typeof t.count === "number" && (
              <span className={cx("min-w-5 rounded-full px-1.5 text-center text-[0.75rem] font-semibold tabular-nums", active && t.count > 0 ? "bg-yellow text-ink" : "bg-hover text-muted")}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label, size = "sm", className }: {
  options: Array<{ id: T; label: ReactNode; disabled?: boolean; title?: string }>; value: T; onChange: (id: T) => void; label: string; size?: "sm" | "xs"; className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cx("inline-flex rounded-md border border-line bg-canvas p-0.5", className)}>
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button key={o.id} type="button" role="radio" aria-checked={on} disabled={o.disabled} title={o.title} onClick={() => onChange(o.id)}
            className={cx(
              "rounded-[5px] font-medium whitespace-nowrap transition-colors disabled:opacity-40",
              size === "sm" ? "h-7 px-3 text-[0.8667rem]" : "h-6 px-2.5 text-[0.8rem]",
              on ? "bg-paper text-ink shadow-[0_1px_2px_rgb(20_20_19/0.08)] ring-1 ring-line" : "text-muted hover:text-ink",
            )}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- secțiuni care se deschid la cerere

export function Collapsible({ title, meta, defaultOpen = false, open: controlled, onToggle, children, id, tone }: {
  title: ReactNode; meta?: ReactNode; defaultOpen?: boolean; open?: boolean; onToggle?: (open: boolean) => void; children: ReactNode; id?: string; tone?: "danger";
}) {
  const [inner, setInner] = useState(defaultOpen);
  const open = controlled ?? inner;
  const bodyId = useId();
  const toggle = () => {
    const next = !open;
    if (controlled === undefined) setInner(next);
    onToggle?.(next);
  };
  return (
    <section id={id} className="scroll-mt-20 border-t border-line first:border-t-0">
      <h2>
        <button type="button" onClick={toggle} aria-expanded={open} aria-controls={bodyId}
          className="group flex min-h-14 w-full items-center gap-3 py-3 text-left">
          <ChevronDown aria-hidden className={cx("size-4 shrink-0 text-muted transition-transform duration-200", !open && "-rotate-90")} />
          <span className={cx("font-semibold", tone === "danger" && "text-danger")}>{title}</span>
          {meta && <span className="ml-auto min-w-0 truncate pl-3 text-right text-[0.8667rem] font-normal text-muted">{meta}</span>}
        </button>
      </h2>
      {open && <div id={bodyId} className="animate-enter pb-6 pl-7">{children}</div>}
    </section>
  );
}

// ---------------------------------------------------------------- straturi: sertar lateral și dialog

function useLayer(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, []);
  return ref;
}

export function Drawer({ title, onClose, children, actions, width = 640 }: { title: ReactNode; onClose: () => void; children: ReactNode; actions?: ReactNode; width?: number }) {
  const ref = useLayer(onClose);
  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}>
      <button type="button" aria-label="Închide" tabIndex={-1} className="absolute inset-0 bg-ink/20" onClick={onClose} />
      <div ref={ref} tabIndex={-1} style={{ width: `min(${width}px, 100vw)` }}
        className="animate-drawer absolute inset-y-0 right-0 flex flex-col border-l border-line bg-paper shadow-[var(--shadow-overlay)] outline-none">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-5">
          <h2 className="min-w-0 flex-1 truncate font-semibold">{title}</h2>
          {actions}
          <button type="button" onClick={onClose} aria-label="Închide" className="grid size-8 place-items-center rounded-md text-muted hover:bg-hover hover:text-ink">
            <X className="size-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function Dialog({ title, onClose, children, footer, width = 520 }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number }) {
  const ref = useLayer(onClose);
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/25 p-4 sm:items-center" onClick={onClose}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}
        onClick={(e) => e.stopPropagation()} style={{ maxWidth: width }}
        className="animate-enter flex max-h-[calc(100dvh-2rem)] w-full flex-col rounded-lg bg-paper shadow-[var(--shadow-overlay)] outline-none">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line px-5">
          <h2 className="font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Închide" className="grid size-8 place-items-center rounded-md text-muted hover:bg-hover hover:text-ink">
            <X className="size-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex shrink-0 justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------- liste cheie / valoare

export function KeyValues({ rows }: { rows: Array<[ReactNode, ReactNode] | null | false> }) {
  return (
    <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-6 gap-y-2 text-[0.9333rem]">
      {rows.filter(Boolean).map((row, i) => {
        const [k, v] = row as [ReactNode, ReactNode];
        return (
          <div key={i} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="min-w-0 break-words">{v}</dd>
          </div>
        );
      })}
    </dl>
  );
}

// ---------------------------------------------------------------- iconițe de stare pentru pași

export function StepIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <Dot tone="now" live className="m-1" />;
    case "done":
      return <span className="grid size-4 place-items-center rounded-full bg-ink text-paper"><Check aria-hidden className="size-2.5" strokeWidth={3.5} /></span>;
    case "waiting":
      return <span className="grid size-4 place-items-center rounded-full border border-yellow-line bg-yellow"><Hand aria-hidden className="size-2.5" strokeWidth={2.5} /></span>;
    case "blocked":
    case "error":
      return <span className="grid size-4 place-items-center rounded-full bg-danger text-paper"><X aria-hidden className="size-2.5" strokeWidth={3.5} /></span>;
    case "skipped":
      return <span className="grid size-4 place-items-center rounded-full border border-dashed border-line-strong text-subtle"><CircleSlash aria-hidden className="size-2.5" /></span>;
    default:
      return <span className="block size-4 rounded-full border border-line-strong bg-paper" />;
  }
}

export const STEP_STATUS_LABEL: Record<string, string> = {
  idle: "în așteptare",
  running: "lucrează",
  done: "gata",
  waiting: "așteaptă un om",
  blocked: "oprit",
  error: "eroare",
  skipped: "nu e cazul",
};

// ---------------------------------------------------------------- termen

export function useNowTick(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

export function timeLeft(deadline: string | null | undefined, now: number): { text: string; seconds: number | null; tone: Tone } {
  if (!deadline) return { text: "—", seconds: null, tone: "neutral" };
  const s = Math.round((new Date(deadline).getTime() - now) / 1000);
  if (Number.isNaN(s)) return { text: "—", seconds: null, tone: "neutral" };
  if (s <= 0) return { text: "depășit", seconds: s, tone: "danger" };
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const text = h >= 48 ? `${Math.floor(h / 24)} zile` : h >= 1 ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
  return { text, seconds: s, tone: s < 6 * 3600 ? "danger" : "neutral" };
}

const TZ = "Europe/Bucharest";
const dayKey = (x: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(x);

/** „azi 23:59”, „mâine 23:59”, „joi 23:59” sau „30.10 23:59”, în ora României. */
export function dueText(v: string | null | undefined, now = Date.now()): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  const hm = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);
  if (dayKey(d) === dayKey(new Date(now))) return `azi ${hm}`;
  if (dayKey(d) === dayKey(new Date(now + 86_400_000))) return `mâine ${hm}`;
  const diff = d.getTime() - now;
  if (diff > 0 && diff < 6 * 86_400_000) return `${new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, weekday: "long" }).format(d)} ${hm}`;
  const date = new Intl.DateTimeFormat("ro-RO", { timeZone: TZ, day: "2-digit", month: "2-digit" }).format(d);
  return `${date} ${hm}`;
}

/** Timpul rămas; roșu sub 6 h. `done`: cazul e rezolvat, termenul nu mai contează. */
export function DeadlineText({ deadline, done, className, withDue = false }: { deadline?: string | null; done?: boolean; className?: string; withDue?: boolean }) {
  const now = useNowTick(done ? 60_000 : 1000);
  if (!deadline) return <span className={cx("text-muted", className)}>—</span>;
  const due = dueText(deadline, now);
  if (done) return <span className={cx("tabular-nums text-muted", className)} title={`Termen: ${due}`}>în termen</span>;
  const left = timeLeft(deadline, now);
  return (
    <span title={`Termen: ${due}`} className={cx("inline-flex items-center gap-1.5 tabular-nums whitespace-nowrap", left.tone === "danger" ? "font-semibold text-danger" : "text-ink", className)}>
      <Clock3 aria-hidden className="size-3.5 shrink-0" />
      {withDue ? `${due} · ${left.text}` : left.text}
    </span>
  );
}

// ---------------------------------------------------------------- limită de eroare pe secțiune

export class SectionBoundary extends Component<{ children: ReactNode; label?: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Secțiune căzută:", this.props.label, error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <Banner tone="danger" icon={<AlertTriangle aria-hidden className="size-5 text-danger" />}
          title={`„${this.props.label ?? "Secțiunea"}” nu s-a putut afișa.`}
          actions={<Button size="sm" onClick={() => this.setState({ error: null })}>Reîncearcă</Button>}>
          Detaliu: {this.state.error.message}
        </Banner>
      );
    }
    return this.props.children;
  }
}
