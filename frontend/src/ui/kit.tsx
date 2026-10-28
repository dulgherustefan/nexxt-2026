import { AlertTriangle, Check, Clock3, Hand, Loader2, Minus, X } from "lucide-react";
import {
  Component,
  createContext,
  forwardRef,
  type ButtonHTMLAttributes,
  type ErrorInfo,
  type ReactNode,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { dateFull, dueLabel } from "../api/format";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- buttons

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-yellow text-on-yellow hover:bg-yellow-hover shadow-[0_1px_2px_rgb(18_19_22/0.12)]",
  secondary: "bg-paper text-ink shadow-[var(--shadow-card)] hover:bg-hover",
  ghost: "bg-transparent text-ink-soft hover:bg-hover hover:text-ink",
  danger: "bg-paper text-danger shadow-[var(--shadow-card)] hover:bg-danger-soft",
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
        "press inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap",
        "transition-[background-color,color,box-shadow] duration-150 disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3.5 text-[0.8667rem]" : "h-9 px-4 text-[0.9333rem]",
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

// ---------------------------------------------------------------- statuses (one set across the app)

export type Tone = "neutral" | "now" | "ok" | "danger" | "dark" | "warn";

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-muted",
  now: "text-ink",
  ok: "text-ok",
  danger: "text-danger",
  dark: "text-ink",
  warn: "text-warn",
};

const TONE_BG: Record<Tone, string> = {
  neutral: "bg-hover text-ink-soft",
  now: "bg-yellow-tint text-ink ring-1 ring-inset ring-yellow-line",
  ok: "bg-ok-soft text-ok",
  danger: "bg-danger-soft text-danger",
  dark: "bg-ink text-paper",
  warn: "bg-warn-soft text-warn",
};

/** A soft pill. Use sparingly: most statuses read better as `<Status>` (dot + word). */
export function Badge({ tone = "neutral", icon, children, className, title }: {
  tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string;
}) {
  return (
    <span
      title={title}
      className={cx("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[0.8rem] font-medium whitespace-nowrap", TONE_BG[tone], className)}
    >
      {icon}
      {children}
    </span>
  );
}

/** Status dot. Only pulses while something is running or waiting on a person. */
export function Dot({ tone = "neutral", live = false, className }: { tone?: Tone; live?: boolean; className?: string }) {
  const color = { neutral: "bg-dot", now: "bg-yellow", ok: "bg-ok", danger: "bg-danger", dark: "bg-ink", warn: "bg-warn" }[tone];
  return <span aria-hidden className={cx("inline-block size-2 shrink-0 rounded-full", color, live && "live-dot", className)} />;
}

/** Dot + word: the default way to show a status in lists. */
export function Status({ tone = "neutral", live, children, className }: { tone?: Tone; live?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2 text-[0.8667rem] font-medium whitespace-nowrap", TONE_TEXT[tone], className)}>
      <Dot tone={tone} live={live} />
      {children}
    </span>
  );
}

/** Rule, evidence and case IDs: a hairline label in the text face with even digits. */
export function IdTag({ children, onClick, title, tone = "neutral" }: {
  children: ReactNode; onClick?: () => void; title?: string; tone?: "neutral" | "now";
}) {
  const cls = cx(
    "id-text inline-flex h-[1.375rem] items-center rounded-md px-1.5 text-[0.7667rem] font-medium whitespace-nowrap ring-1 ring-inset",
    tone === "now" ? "bg-yellow-tint text-ink ring-yellow-line" : "bg-paper text-muted ring-line",
    onClick && "cursor-pointer transition-colors hover:text-ink hover:ring-line-strong",
  );
  return onClick ? (
    <button type="button" className={cls} onClick={onClick} title={title}>{children}</button>
  ) : (
    <span className={cls} title={title}>{children}</span>
  );
}

// ---------------------------------------------------------------- containers

/** Panels inside a titled page section use h3 for their own title; the section provides the level. */
export const PanelHeadingLevel = createContext<2 | 3>(2);

export function Panel({ title, actions, children, className, bodyClassName, id, description }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string; id?: string; description?: ReactNode;
}) {
  const H = useContext(PanelHeadingLevel) === 3 ? "h3" : "h2";
  return (
    <section id={id} className={cx("rounded-xl bg-paper shadow-[var(--shadow-card)]", className)}>
      {(title || actions || description) && (
        <header className="flex min-h-12 items-center justify-between gap-3 px-5 pt-4 pb-1">
          <div className="min-w-0">
            {title && <H className="text-[0.9333rem] font-semibold">{title}</H>}
            {description && <p className="mt-0.5 text-[0.8667rem] text-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName ?? "px-5 py-4"}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions, children, eyebrow }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode; eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-7">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && <div className="mb-1.5 text-[0.8667rem] text-muted">{eyebrow}</div>}
          <h1 className="text-[1.6rem] leading-tight font-semibold tracking-[-0.02em]">{title}</h1>
          {description && <p className="mt-1.5 max-w-[68ch] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

/** A calm notice. `now` is for the one thing that needs a person; it gets a yellow dot, not a yellow block. */
export function Banner({ tone = "now", icon, title, children, actions }: {
  tone?: "now" | "danger" | "neutral" | "ok"; icon?: ReactNode; title: ReactNode; children?: ReactNode; actions?: ReactNode;
}) {
  const styles = {
    now: "bg-yellow-tint shadow-[var(--shadow-raise)] ring-1 ring-inset ring-yellow-line",
    danger: "bg-danger-soft ring-1 ring-inset ring-danger-line",
    neutral: "bg-canvas ring-1 ring-inset ring-line",
    ok: "bg-ok-soft ring-1 ring-inset ring-ok-line",
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl px-5 py-4", styles)}>
      {icon ? <span className="shrink-0">{icon}</span> : tone === "now" ? <Dot tone="now" live className="self-start mt-2" /> : null}
      <div className="min-w-[16rem] flex-1">
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-0.5 text-[0.9333rem] text-ink-soft">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action, icon }: { title: ReactNode; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl bg-canvas px-6 py-12 text-center">
      {icon && <span className="grid size-10 place-items-center rounded-full bg-paper text-muted shadow-[var(--shadow-card)]">{icon}</span>}
      <div>
        <p className="font-semibold">{title}</p>
        {children && <p className="mx-auto mt-1 max-w-[52ch] text-muted">{children}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ error, onRetry, what = "this" }: { error: unknown; onRetry?: () => void; what?: string }) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return (
    <Banner tone="danger" icon={<AlertTriangle aria-hidden className="size-5 text-danger" />}
      title={`Couldn't load ${what}.`}
      actions={onRetry && <Button size="sm" onClick={onRetry}>Try again</Button>}>
      {message ? `${message}.` : "The server didn't respond."} The rest of the page still works.
    </Banner>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-muted">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-md bg-hover", className)} />;
}

// ---------------------------------------------------------------- tabs

/**
 * Tabs with a sliding underline. The bar is one element moved with transform (compositor only),
 * so it stays smooth while the next tab's content renders.
 */
export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: Array<{ id: T; label: ReactNode; count?: number }>; value: T; onChange: (id: T) => void; label: string;
}) {
  const base = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const [bar, setBar] = useState<{ x: number; w: number } | null>(null);
  useLayoutEffect(() => {
    const list = listRef.current;
    const el = list?.querySelector<HTMLElement>(`[data-tab="${CSS.escape(String(value))}"]`);
    if (!list || !el) return;
    const measure = () => setBar({ x: el.offsetLeft, w: el.offsetWidth });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(list);
    return () => ro.disconnect();
  }, [value, tabs.length]);
  return (
    <div ref={listRef} role="tablist" aria-label={label} className="relative flex gap-6 overflow-x-auto overflow-y-hidden border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            data-tab={t.id}
            id={`${base}-${t.id}`}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={cx(
              "relative flex h-10 items-center gap-1.5 text-[0.9333rem] font-medium whitespace-nowrap transition-colors",
              active ? "text-ink" : "text-muted hover:text-ink",
            )}
          >
            {t.label}
            {typeof t.count === "number" && (
              <span className={cx("tnum text-[0.8rem]", active ? "text-ink-soft" : "text-subtle")}>{t.count}</span>
            )}
          </button>
        );
      })}
      {bar && (
        <span
          aria-hidden
          className="pointer-events-none absolute bottom-0 left-0 h-[2px] w-px origin-left rounded-full bg-ink transition-transform duration-[260ms] ease-[var(--ease-out)]"
          style={{ transform: `translateX(${bar.x}px) scaleX(${bar.w})` }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- key / value lists

export function KeyValues({ rows }: { rows: Array<[ReactNode, ReactNode] | null | false> }) {
  return (
    <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-6 gap-y-2.5">
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

// ---------------------------------------------------------------- step icons

export function StepIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <span className="grid size-4 place-items-center"><Dot tone="now" live /></span>;
    case "done":
      return <span className="grid size-4 place-items-center rounded-full bg-ink text-paper"><Check aria-hidden className="size-2.5" strokeWidth={3} /></span>;
    case "waiting":
      return <span className="grid size-4 place-items-center rounded-full bg-yellow text-ink"><Hand aria-hidden className="size-2.5" strokeWidth={2.5} /></span>;
    case "blocked":
    case "error":
      return <span className="grid size-4 place-items-center rounded-full bg-danger text-paper"><X aria-hidden className="size-2.5" strokeWidth={3} /></span>;
    case "skipped":
      return <span className="grid size-4 place-items-center rounded-full bg-hover text-subtle"><Minus aria-hidden className="size-2.5" strokeWidth={2.5} /></span>;
    default:
      return <span className="block size-4 rounded-full ring-1 ring-inset ring-line-strong" />;
  }
}

export const STEP_STATUS_LABEL: Record<string, string> = {
  idle: "waiting",
  running: "running",
  done: "done",
  waiting: "needs a person",
  blocked: "stopped",
  error: "error",
  skipped: "not needed",
};

// ---------------------------------------------------------------- deadlines

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
  if (s <= 0) return { text: "Overdue", seconds: s, tone: "danger" };
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const text = h >= 48 ? `${Math.floor(h / 24)} days left` : h >= 1 ? `${h} h ${String(m).padStart(2, "0")} min left` : `${m} min left`;
  return { text, seconds: s, tone: s < 6 * 3600 ? "danger" : "neutral" };
}

/** "Due tomorrow, 23:59" with the exact time in the tooltip; red in the last 6 hours. */
export function DeadlineText({ deadline, done, className }: { deadline?: string | null; done?: boolean; className?: string }) {
  const now = useNowTick(30_000);
  if (!deadline) return <span className={cx("text-muted", className)}>—</span>;
  const exact = dateFull(deadline);
  if (done) return <span className={cx("tabular-nums text-muted", className)} title={exact}>On time</span>;
  const left = timeLeft(deadline, now);
  return (
    <span title={`${exact} · ${left.text}`} className={cx("inline-flex items-center gap-1.5 tabular-nums", left.tone === "danger" ? "font-medium text-danger" : "text-ink-soft", className)}>
      <Clock3 aria-hidden className="size-3.5 opacity-70" strokeWidth={1.75} />
      {left.seconds !== null && left.seconds <= 0 ? "Overdue" : dueLabel(deadline, now)}
    </span>
  );
}

// ---------------------------------------------------------------- per-section error boundary

export class SectionBoundary extends Component<{ children: ReactNode; label?: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Section failed:", this.props.label, error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <Banner tone="danger" icon={<AlertTriangle aria-hidden className="size-5 text-danger" />}
          title={`The ${this.props.label ? `"${this.props.label}"` : ""} section couldn't load.`}
          actions={<Button size="sm" onClick={() => this.setState({ error: null })}>Try again</Button>}>
          The rest of the page still works. {this.state.error.message}
        </Banner>
      );
    }
    return this.props.children;
  }
}
