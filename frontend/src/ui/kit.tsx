import { AlertTriangle, Check, CircleSlash, Clock3, Hand, Loader2, X } from "lucide-react";
import {
  Component,
  forwardRef,
  type ButtonHTMLAttributes,
  type ErrorInfo,
  type ReactNode,
  useEffect,
  useId,
  useState,
} from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- butoane

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-yellow text-ink border-ink hover:bg-yellow-hover",
  secondary: "bg-paper text-ink border-line-strong hover:bg-hover",
  ghost: "bg-transparent text-ink border-transparent hover:bg-hover",
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
        "inline-flex items-center justify-center gap-2 rounded-md border font-semibold whitespace-nowrap transition-colors",
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
  now: "bg-yellow-soft text-ink border-[#e6d44a]",
  ok: "bg-ok-soft text-ok border-ok-line",
  danger: "bg-danger-soft text-danger border-danger-line",
  dark: "bg-ink text-paper border-ink",
};

export function Badge({ tone = "neutral", icon, children, className, title }: {
  tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-[0.8667rem] font-semibold whitespace-nowrap",
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
  const color = { neutral: "bg-line-strong", now: "bg-yellow ring-1 ring-ink/40", ok: "bg-ok", danger: "bg-danger", dark: "bg-ink" }[tone];
  return <span aria-hidden className={cx("inline-block size-2.5 shrink-0 rounded-full", color, live && "animate-pulse-dot", className)} />;
}

/** ID-uri copiabile: reguli, probe, cazuri, hash-uri. Mono pentru că sunt date, nu decor. */
export function IdTag({ children, onClick, title, tone = "neutral" }: {
  children: ReactNode; onClick?: () => void; title?: string; tone?: "neutral" | "now";
}) {
  const cls = cx(
    "inline-flex h-6 items-center rounded-sm border px-1.5 font-mono text-[0.8rem] tabular-nums whitespace-nowrap",
    tone === "now" ? "border-[#e6d44a] bg-yellow-soft" : "border-line bg-canvas",
    onClick && "cursor-pointer hover:border-ink hover:bg-yellow-tint",
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
          {title && <h2 className="text-[1rem] font-semibold">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions, children }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode;
}) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[1.6rem] font-bold leading-tight">{title}</h1>
          {description && <p className="mt-1 max-w-[70ch] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function Banner({ tone = "now", icon, title, children, actions }: {
  tone?: "now" | "danger" | "neutral" | "ok"; icon?: ReactNode; title: ReactNode; children?: ReactNode; actions?: ReactNode;
}) {
  const styles = {
    now: "border-ink bg-yellow-soft",
    danger: "border-danger-line bg-danger-soft",
    neutral: "border-line bg-canvas",
    ok: "border-ok-line bg-ok-soft",
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border px-4 py-3", styles)}>
      {icon && <span className="shrink-0">{icon}</span>}
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
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-line-strong bg-canvas px-6 py-8">
      {icon && <span className="text-muted">{icon}</span>}
      <div>
        <p className="font-semibold">{title}</p>
        {children && <p className="mt-1 max-w-[60ch] text-muted">{children}</p>}
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
      {message ? `Motiv: ${message}` : "Serverul nu a răspuns."} Restul paginii funcționează.
    </Banner>
  );
}

export function Loading({ label = "Se încarcă…" }: { label?: string }) {
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

// ---------------------------------------------------------------- taburi

export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: Array<{ id: T; label: ReactNode; count?: number }>; value: T; onChange: (id: T) => void; label: string;
}) {
  const base = useId();
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
              "relative -mb-px flex h-10 items-center gap-2 border-b-2 px-3 font-semibold whitespace-nowrap",
              active ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
            {typeof t.count === "number" && (
              <span className={cx("rounded-sm px-1.5 text-[0.8rem] tabular-nums", active ? "bg-yellow text-ink" : "bg-canvas text-muted")}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- liste cheie / valoare

export function KeyValues({ rows }: { rows: Array<[ReactNode, ReactNode] | null | false> }) {
  return (
    <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-4 gap-y-2">
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
      return <Dot tone="now" live className="m-[3px]" />;
    case "done":
      return <span className="grid size-4 place-items-center rounded-full bg-ink text-paper"><Check aria-hidden className="size-3" strokeWidth={3} /></span>;
    case "waiting":
      return <span className="grid size-4 place-items-center rounded-full border border-ink bg-yellow"><Hand aria-hidden className="size-2.5" strokeWidth={2.5} /></span>;
    case "blocked":
    case "error":
      return <span className="grid size-4 place-items-center rounded-full bg-danger text-paper"><X aria-hidden className="size-3" strokeWidth={3} /></span>;
    case "skipped":
      return <span className="grid size-4 place-items-center rounded-full border border-dashed border-line-strong text-subtle"><CircleSlash aria-hidden className="size-2.5" /></span>;
    default:
      return <span className="block size-4 rounded-full border border-line-strong bg-paper" />;
  }
}

export const STEP_STATUS_LABEL: Record<string, string> = {
  idle: "în așteptare",
  running: "rulează",
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

export function DeadlineText({ deadline, done, className }: { deadline?: string | null; done?: boolean; className?: string }) {
  const now = useNowTick(done ? 60_000 : 1000);
  if (!deadline) return <span className={cx("text-muted", className)}>—</span>;
  const exact = new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(deadline));
  if (done) return <span className={cx("tabular-nums text-muted", className)} title={`Termen: ${exact}`}>în termen</span>;
  const left = timeLeft(deadline, now);
  return (
    <span title={`Termen: ${exact}`} className={cx("inline-flex items-center gap-1.5 tabular-nums", left.tone === "danger" ? "font-semibold text-danger" : "text-ink", className)}>
      <Clock3 aria-hidden className="size-3.5" />
      {left.text}
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
          title={`Secțiunea „${this.props.label ?? "aceasta"}” nu s-a putut afișa.`}
          actions={<Button size="sm" onClick={() => this.setState({ error: null })}>Reîncearcă</Button>}>
          Restul paginii funcționează. Detaliu: {this.state.error.message}
        </Banner>
      );
    }
    return this.props.children;
  }
}
