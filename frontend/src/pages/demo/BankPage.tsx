import NumberFlow from "@number-flow/react";
import { usePageTheme } from "../../ui/ThemeToggle";
import {
  ArrowCounterClockwise,
  ArrowDownLeft,
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Bus,
  ChatCircleText,
  Check,
  CircleNotch,
  Coffee,
  CreditCard,
  DeviceMobile,
  Drop,
  FilmSlate,
  FirstAidKit,
  ForkKnife,
  GasPump,
  Hourglass,
  Info,
  Lightning,
  Money,
  Pause,
  ShieldCheck,
  ShieldWarning,
  ShoppingCart,
  Taxi,
  User,
  WarningCircle,
  WifiHigh,
  WifiSlash,
  X,
  type Icon,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../../api/client";
import { clock, normalizeRo } from "../../api/format";
import { useApi, usePrefersReducedMotion, useResource, useRuntime } from "../../api/runtime";
import type { BankNotification, BankState, BankTransaction, CaseDetail } from "../../api/types";
import { cx, useNowTick } from "../../ui/kit";
import {
  amountText,
  answerBy,
  atWhen,
  bankPath,
  canDispute,
  clientFrom,
  dayLabel,
  DEMO_CLIENTS,
  FINAL,
  fullWhen,
  isDisputed,
  isOut,
  isRecent,
  isRefunded,
  isRefundTx,
  loadTracked,
  noteKind,
  refundBy,
  saveTracked,
  shortWhen,
  signedAmount,
  stepsFor,
  txCategory,
  useThemeColor,
  type Step,
  type TrackedDispute,
  type TxCategory,
} from "./bankModel";

/**
 * Demo Bank: the fictional bank's mobile app that a juror opens on their phone. It is the bank's
 * product, not the VersoML console, so it has its own small set of controls below.
 */

type SheetState = { tx: BankTransaction; mode: "details" | "confirm" } | null;

/** The app background, also used for the phone's browser bar. */
const APP_BG = "#f7f7f8";

export default function BankPage() {
  usePageTheme("light");
  const api = useApi();
  const { mode, mockReason } = useRuntime();
  const [search] = useSearchParams();
  const ref = clientFrom(search);
  const now = useNowTick(15_000);
  const reduced = usePrefersReducedMotion();
  const main = useRef<HTMLElement>(null);

  const [lastOk, setLastOk] = useState<number | null>(null);
  const bank = useResource<BankState>(async () => {
    const v = await api.bank(ref);
    setLastOk(Date.now());
    return v;
  }, [api, ref], { pollMs: 2000 });

  const [tracked, setTracked] = useState<TrackedDispute[]>(() => loadTracked(ref));
  useEffect(() => setTracked(loadTracked(ref)), [ref]);
  useEffect(() => saveTracked(ref, tracked), [ref, tracked]);
  useEffect(() => {
    document.title = "Demo Bank";
  }, []);
  useThemeColor(APP_BG);

  const [sheet, setSheet] = useState<SheetState>(null);
  const data = bank.data;
  const txs = useMemo(() => (Array.isArray(data?.transactions) ? data.transactions : []), [data]);
  const notes = useMemo(
    () => (Array.isArray(data?.notifications) ? [...data.notifications] : []).sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()),
    [data],
  );

  // the backend books the refund as its own row; the disputed payment keeps its status, so link the two here
  const refundedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const d of tracked) if (txs.some((t) => isRefundTx(t) && t.description.includes(d.case_id))) ids.add(d.transaction_id);
    return ids;
  }, [tracked, txs]);

  function onDisputed(d: TrackedDispute) {
    setTracked((list) => [d, ...list.filter((x) => x.case_id !== d.case_id)].slice(0, 5));
    setSheet(null);
    main.current?.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    void bank.reload();
  }

  const notFound = bank.error instanceof ApiError && bank.error.status === 404;
  const open = sheet !== null;

  return (
    <div className="min-h-dvh bg-canvas text-ink sm:grid sm:place-items-center sm:bg-line sm:p-6">
      <div className="relative mx-auto flex h-dvh w-full max-w-[440px] flex-col overflow-hidden bg-canvas sm:h-[min(880px,calc(100dvh-3rem))] sm:w-[400px] sm:rounded-[32px] sm:shadow-[var(--shadow-overlay)]">
        <AppBar alias={data?.customer_alias ?? (bank.error ? "—" : "…")} inert={open} />

        <main ref={main} inert={open} className="flex-1 overflow-y-auto overscroll-contain">
          {mode === "mock" && (
            <p className="mx-4 mt-1 flex items-start gap-2 rounded-xl bg-paper px-3 py-2 text-[0.8rem] text-muted shadow-[var(--shadow-card)]">
              <Info aria-hidden size={15} className="mt-0.5 shrink-0" />
              {mockReason === "forced"
                ? "Offline demo: this phone simulates the bank’s data."
                : "The bank’s server isn’t reachable, so this phone simulates the data."}
            </p>
          )}
          {bank.error && data && (
            <p role="status" className="mx-4 mt-2 flex items-start gap-2 rounded-xl bg-danger-soft px-3 py-2 text-[0.8rem] text-danger">
              <WifiSlash aria-hidden size={15} className="mt-0.5 shrink-0" />
              <span>
                No connection to the bank. Showing the data from {lastOk ? shortWhen(new Date(lastOk).toISOString(), Date.now()) : "the last update"}. Retrying automatically.
              </span>
            </p>
          )}

          {!data ? (
            bank.error ? (
              <BootError notFound={notFound} refName={ref} message={bank.error.message} onRetry={() => void bank.reload()} />
            ) : (
              <BootSkeleton />
            )
          ) : (
            <>
              <Balance state={data} txs={txs} now={now} />
              {tracked.length > 0 && (
                <section aria-label="Your disputes" className="flex flex-col gap-3 px-4 pb-3">
                  {tracked.map((d) => (
                    <DisputeCard
                      key={d.case_id}
                      d={d}
                      tx={txs.find((t) => t.id === d.transaction_id)}
                      refund={txs.find((t) => isRefundTx(t) && t.description.includes(d.case_id))}
                      now={now}
                      onHide={() => setTracked((list) => list.filter((x) => x.case_id !== d.case_id))}
                    />
                  ))}
                </section>
              )}
              <Notifications notes={notes} now={now} />
              <Transactions
                txs={txs}
                tracked={tracked}
                refundedIds={refundedIds}
                now={now}
                onOpen={(tx) => setSheet({ tx, mode: "details" })}
                onDispute={(tx) => setSheet({ tx, mode: "confirm" })}
              />
              <footer className="px-5 pt-3 pb-[max(1.75rem,env(safe-area-inset-bottom))] text-[0.8rem] text-subtle">
                <p>Demo Bank is a fictional bank. All data is synthetic.</p>
                <nav aria-label="Demo customers" className="mt-2.5 flex items-center gap-1.5">
                  <span className="mr-1">Demo customer</span>
                  {DEMO_CLIENTS.map((c, i) =>
                    c === ref ? (
                      <span key={c} aria-current="page" className="tnum grid size-8 place-items-center rounded-full bg-ink font-medium text-paper">
                        {i + 1}
                      </span>
                    ) : (
                      <Link
                        key={c}
                        to={bankPath(c)}
                        aria-label={`Demo customer ${i + 1}`}
                        className="tnum grid size-8 place-items-center rounded-full bg-paper font-medium text-ink-soft shadow-[var(--shadow-card)] transition-colors hover:text-ink"
                      >
                        {i + 1}
                      </Link>
                    ),
                  )}
                </nav>
              </footer>
            </>
          )}
        </main>

        {sheet && (
          <TxSheet
            key={sheet.tx.id}
            refName={ref}
            tx={sheet.tx}
            mode={sheet.mode}
            disputed={isDisputed(sheet.tx, tracked)}
            refunded={isRefunded(sheet.tx) || refundedIds.has(sheet.tx.id)}
            disputable={canDispute(sheet.tx, tracked)}
            onMode={(m) => setSheet({ tx: sheet.tx, mode: m })}
            onClose={() => setSheet(null)}
            onDisputed={onDisputed}
          />
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ the bank's own small controls

function BankMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cx("shrink-0", className)}>
      <rect width="32" height="32" rx="9" fill="currentColor" className="text-ink" />
      <path d="M10 8.5h5.6a7.5 7.5 0 0 1 0 15H10z" fill="#fff" />
      <path d="M13.4 12v8h2a4 4 0 0 0 0-8z" fill="currentColor" className="text-ink" />
    </svg>
  );
}

function BankButton({ variant = "secondary", size = "md", busy, icon, className, children, disabled, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "press inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap",
        "transition-[background-color,color,box-shadow,opacity] duration-150 disabled:cursor-not-allowed disabled:opacity-55",
        size === "sm" ? "h-10 px-4 text-[0.8667rem]" : size === "lg" ? "h-[3.25rem] px-6 text-[1rem]" : "h-11 px-5 text-[0.9333rem]",
        variant === "primary"
          ? "bg-ink text-paper shadow-[0_1px_2px_rgb(18_19_22/0.16)] hover:bg-ink-soft"
          : variant === "ghost"
            ? "text-ink-soft hover:bg-hover hover:text-ink"
            : "bg-paper text-ink shadow-[var(--shadow-card)] hover:bg-hover",
        className,
      )}
    >
      {busy ? <CircleNotch aria-hidden size={18} weight="bold" className="animate-spin" /> : icon}
      {children}
    </button>
  );
}

function Shimmer({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-lg bg-line/70", className)} />;
}

/** True for list keys that arrive after the first paint, so only new rows slide in. */
function useFreshKeys(keys: string[]): (key: string) => boolean {
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!seen.current) seen.current = new Set(keys);
    else for (const k of keys) seen.current.add(k);
  });
  return (k) => seen.current !== null && !seen.current.has(k);
}

const withPeriod = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);

/** Keeps a masked IBAN's last group with its dots ("•••• 7731") when a line wraps. */
const keepTogether = (s: string) => s.replace(/(•{4}) (?=\d)/g, "$1\u00A0");

// ------------------------------------------------------------------ top bar and first load

function AppBar({ alias, inert }: { alias: string; inert: boolean }) {
  return (
    <header inert={inert} className="relative z-10 flex items-center justify-between gap-3 bg-canvas px-5 pt-[max(0.875rem,env(safe-area-inset-top))] pb-2.5">
      <div className="flex min-w-0 items-center gap-2.5">
        <BankMark className="size-8" />
        <div className="min-w-0 leading-tight">
          <p className="text-[1rem] font-semibold tracking-[-0.01em]">Demo Bank</p>
          <p className="text-[0.75rem] text-subtle">Demo · synthetic data</p>
        </div>
      </div>
      <span className="inline-flex h-9 max-w-[48%] items-center gap-2 rounded-full bg-paper pr-3.5 pl-1 text-[0.8667rem] font-medium shadow-[var(--shadow-card)]">
        <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-canvas text-ink-soft">
          <User size={15} weight="bold" />
        </span>
        <span className="truncate">{alias.replace(/^Demo /, "")}</span>
      </span>
    </header>
  );
}

function BootSkeleton() {
  return (
    <div role="status" aria-label="Loading your account" className="flex flex-col gap-3 px-5 pt-5">
      <Shimmer className="h-4 w-32" />
      <Shimmer className="h-11 w-56" />
      <Shimmer className="h-4 w-48" />
      <Shimmer className="mt-6 h-20 rounded-2xl" />
      <Shimmer className="h-40 rounded-2xl" />
    </div>
  );
}

function BootError({ notFound, refName, message, onRetry }: { notFound: boolean; refName: string; message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 px-5 pt-8">
      <span className="grid size-11 place-items-center rounded-full bg-danger-soft text-danger">
        <WarningCircle aria-hidden size={22} />
      </span>
      {notFound ? (
        <>
          <p className="text-[1.0667rem] font-semibold">Demo Bank has no customer {refName}.</p>
          <p className="text-muted">Open one of the demo customers instead.</p>
          <div className="flex gap-2">
            {DEMO_CLIENTS.map((c, i) => (
              <Link key={c} to={bankPath(c)} className="press inline-flex h-11 items-center rounded-full bg-paper px-5 font-medium shadow-[var(--shadow-card)] hover:bg-hover">
                Customer {i + 1}
              </Link>
            ))}
          </div>
        </>
      ) : (
        <>
          <p className="text-[1.0667rem] font-semibold">Can’t connect to Demo Bank.</p>
          <p className="text-muted">{withPeriod(message || "The server didn’t answer")} Check the Wi-Fi and try again.</p>
          <BankButton variant="primary" onClick={onRetry}>Try again</BankButton>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ balance

function Balance({ state, txs, now }: { state: BankState; txs: BankTransaction[]; now: number }) {
  const prev = useRef(state.balance);
  const [rising, setRising] = useState(false);
  useEffect(() => {
    const before = prev.current;
    prev.current = state.balance;
    if (typeof state.balance !== "number" || typeof before !== "number" || state.balance <= before) return;
    setRising(true);
    const t = window.setTimeout(() => setRising(false), 1800);
    return () => {
      window.clearTimeout(t);
      setRising(false);
    };
  }, [state.balance]);

  const refund = useMemo(
    () =>
      txs
        .filter((t) => isRefundTx(t) && now - new Date(t.ts).getTime() < 24 * 3600_000)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0],
    [txs, now],
  );
  const ok = typeof state.balance === "number" && Number.isFinite(state.balance);

  return (
    <section aria-labelledby="balance-label" className="px-5 pt-4 pb-6">
      <p id="balance-label" className="text-[0.8667rem] text-muted">Current account</p>
      <p className={cx("mt-1.5 flex items-baseline gap-2 transition-colors duration-500", rising ? "text-ok" : "text-ink")}>
        <span className="text-[1.15rem] font-medium opacity-80">RON</span>
        <span className="tnum text-[2.6rem] leading-none font-semibold tracking-[-0.035em]">
          {ok ? (
            <NumberFlow
              value={state.balance}
              locales="en-GB"
              format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
              className={cx("[&::part(fraction)]:transition-colors", rising ? "[&::part(fraction)]:text-ok" : "[&::part(fraction)]:text-subtle")}
            />
          ) : (
            "—"
          )}
        </span>
      </p>
      <p className="tnum mt-2 text-[0.8667rem] tracking-[0.01em] text-muted">{state.iban_masked || "IBAN not available"}</p>
      {refund && (
        <p className="mt-3 inline-flex animate-enter items-center gap-1.5 rounded-full bg-ok-soft px-3 py-1 text-[0.8rem] font-medium text-ok">
          <ArrowCounterClockwise aria-hidden size={14} weight="bold" />
          <span className="tnum">+{amountText(refund.amount)} refunded {atWhen(refund.ts, now)}</span>
        </p>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ the dispute and its tracker

const STATE_WORD: Record<Step["state"], string> = {
  done: "done",
  now: "in progress",
  todo: "not yet",
  ok: "done",
  info: "see the note below",
};

const MARK_ICON: Record<NonNullable<Step["mark"]>, Icon> = {
  recover: ArrowCounterClockwise,
  wait: Hourglass,
  stop: X,
  closed: Check,
  pause: Pause,
};

function StepDot({ step }: { step: Step }) {
  switch (step.state) {
    case "done":
      return (
        <span className="grid size-5 place-items-center rounded-full bg-ink text-paper">
          <Check aria-hidden size={11} weight="bold" />
        </span>
      );
    case "ok":
      return (
        <span className="grid size-5 place-items-center rounded-full bg-ok text-paper">
          <Check aria-hidden size={11} weight="bold" />
        </span>
      );
    case "now":
      return (
        <span className="grid size-5 place-items-center rounded-full bg-paper ring-2 ring-ink ring-inset">
          <span className="live-dot block size-2 rounded-full bg-ink" />
        </span>
      );
    case "info": {
      const MarkIcon = MARK_ICON[step.mark ?? "wait"];
      return (
        <span className="grid size-5 place-items-center rounded-full bg-ink-soft text-paper">
          <MarkIcon aria-hidden size={11} weight="bold" />
        </span>
      );
    }
    default:
      return <span className="block size-5 rounded-full bg-paper ring-2 ring-line-strong ring-inset" />;
  }
}

function Tracker({ steps }: { steps: Step[] }) {
  const reached = steps.reduce((n, s, i) => (s.state === "todo" ? n : i), 0);
  const progress = steps.length > 1 ? reached / (steps.length - 1) : 0;
  const refunded = steps[steps.length - 1]?.state === "ok";
  return (
    <div className="relative mt-4">
      <span aria-hidden className="absolute top-[9px] right-2.5 left-2.5 h-0.5 rounded-full bg-line" />
      <span
        aria-hidden
        className={cx("absolute top-[9px] right-2.5 left-2.5 h-0.5 origin-left rounded-full transition-transform duration-700 ease-[var(--ease-out)]", refunded ? "bg-ok" : "bg-ink")}
        style={{ transform: `scaleX(${progress})` }}
      />
      <ol aria-label="Dispute progress" className="relative grid grid-cols-3">
        {steps.map((s, i) => (
          <li
            key={`${s.label}-${i}`}
            aria-current={s.state === "now" ? "step" : undefined}
            className={cx("flex flex-col gap-2", i === 0 ? "items-start text-left" : i === steps.length - 1 ? "items-end text-right" : "items-center text-center")}
          >
            <StepDot step={s} />
            <span className={cx("text-[0.8rem] leading-tight", s.state === "todo" ? "text-subtle" : s.state === "ok" ? "font-semibold text-ok" : "font-medium text-ink")}>
              {s.label}
              <span className="sr-only">: {STATE_WORD[s.state]}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function DisputeCard({ d, tx, refund, now, onHide }: {
  d: TrackedDispute; tx?: BankTransaction; refund?: BankTransaction; now: number; onHide: () => void;
}) {
  const api = useApi();
  const cache = useRef<CaseDetail | null>(null);
  const res = useResource<CaseDetail>(async () => {
    // once the case reaches a final state, stop asking the server
    if (cache.current && FINAL.has(String(cache.current.summary?.status))) return cache.current;
    const v = await api.caseDetail(d.case_id);
    cache.current = v;
    return v;
  }, [api, d.case_id], { pollMs: 2000 });

  const summary = res.data?.summary;
  const status = String(summary?.status ?? "");
  const steps = stepsFor(res.data ? status : "NOU", summary?.verdict);
  const note = steps.find((s) => s.note)?.note;
  const gone = res.error instanceof ApiError && res.error.status === 404 && !res.data;
  const due = refundBy(summary?.deadline ?? res.data?.clock?.t1_deadline, now);
  const writeBy = answerBy(res.data?.clock?.answer_deadline);
  const amount = tx ? amountText(tx.amount) : summary?.amount ? amountText(summary.amount.value) : null;
  const done = status === "RAMBURSAT";

  let foot: ReactNode = null;
  if (done) {
    foot = (
      <p className="font-medium text-ok">
        We refunded {amount ?? "the money"}{refund ? ` ${atWhen(refund.ts, now)}` : ""}. It’s already in your balance.
      </p>
    );
  } else if (status === "TRASEU_APP") {
    foot = <p>We’re asking the payee’s bank to return the money. {writeBy ? `We’ll write to you by ${writeBy}.` : "We’ll write to you."}</p>;
  } else if (FINAL.has(status)) {
    foot = <p>We’ll explain everything in writing{writeBy ? ` by ${writeBy}` : ""}.</p>;
  } else if (due) {
    foot = <p>If you didn’t authorize this payment, you’ll get the money back by {due}.</p>;
  }

  return (
    <article className={cx("animate-enter rounded-2xl bg-paper p-4 shadow-[var(--shadow-card)]", done && "ring-1 ring-ok-line")}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">Your dispute</h2>
        <span className="tnum shrink-0 rounded-md bg-canvas px-1.5 py-0.5 font-mono text-[0.72rem] text-ink-soft">{d.case_id}</span>
      </div>
      <p className="mt-0.5 text-[0.8667rem] text-muted">
        {keepTogether(tx?.description ?? "Disputed payment")}
        {amount ? <span className="tnum whitespace-nowrap"> · {amount}</span> : null}
      </p>

      {gone ? (
        <div className="mt-3 text-[0.9333rem] text-ink-soft">
          <p>We can’t find this dispute on the server any more. It may have restarted. The payment is still disputed in the bank’s records.</p>
          <BankButton size="sm" className="mt-3" onClick={onHide}>Hide card</BankButton>
        </div>
      ) : (
        <>
          <div aria-live="polite">
            <Tracker steps={steps} />
            {note && <p className="mt-3 text-[0.8667rem] text-ink-soft">{note}</p>}
          </div>
          {foot && <div className="mt-3.5 border-t border-line pt-3 text-[0.9333rem] text-ink-soft">{foot}</div>}
          {res.error && (
            <p className="mt-2.5 flex items-center gap-1.5 text-[0.8rem] text-danger">
              <WifiSlash aria-hidden size={14} />
              We can’t check the status right now. Retrying automatically.
            </p>
          )}
          {!res.data && !res.error && (
            <p className="mt-2.5 flex items-center gap-1.5 text-[0.8rem] text-muted">
              <CircleNotch aria-hidden size={14} className="animate-spin" />
              Checking your dispute…
            </p>
          )}
        </>
      )}
    </article>
  );
}

// ------------------------------------------------------------------ notifications

function NoteIcon({ n }: { n: BankNotification }) {
  const k = noteKind(n);
  if (k === "refund") {
    return (
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-ok-soft text-ok">
        <ArrowCounterClockwise aria-hidden size={17} weight="bold" />
      </span>
    );
  }
  const Glyph = k === "security" ? DeviceMobile : k === "money" ? ArrowUpRight : ChatCircleText;
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-canvas text-ink-soft">
      <Glyph aria-hidden size={17} />
    </span>
  );
}

const noteKey = (n: BankNotification) => `${n.ts}|${n.text}`;

function Notifications({ notes, now }: { notes: BankNotification[]; now: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? notes : notes.slice(0, 3);
  const fresh = useFreshKeys(notes.map(noteKey));
  return (
    <section aria-labelledby="bank-notes" className="px-4 pt-3">
      <div className="flex items-baseline justify-between gap-3 px-1">
        <h2 id="bank-notes" className="text-[0.9333rem] font-semibold">Notifications</h2>
        {notes.length > 3 && (
          <button type="button" className="text-[0.8667rem] font-medium text-muted transition-colors hover:text-ink" onClick={() => setAll((v) => !v)}>
            {all ? "Show fewer" : `Show all ${notes.length}`}
          </button>
        )}
      </div>
      {notes.length === 0 ? (
        <p className="mt-2 rounded-2xl bg-paper px-4 py-3.5 text-[0.9333rem] text-muted shadow-[var(--shadow-card)]">No new notifications.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
          {shown.map((n) => {
            const k = noteKey(n);
            const refund = noteKind(n) === "refund";
            return (
              <li key={k} className={cx("flex items-start gap-3 px-4 py-3", fresh(k) && "animate-enter")}>
                <NoteIcon n={n} />
                <span className="min-w-0 flex-1 pt-0.5">
                  <span className={cx("block text-[0.9333rem] leading-snug", refund ? "font-semibold text-ink" : "text-ink-soft")}>{keepTogether(n.text)}</span>
                  <span className="tnum mt-0.5 block text-[0.8rem] text-subtle">{shortWhen(n.ts, now)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ transactions

const CATEGORY_ICON: Record<TxCategory, Icon> = {
  refund: ArrowCounterClockwise,
  income: Briefcase,
  groceries: ShoppingCart,
  health: FirstAidKit,
  energy: Lightning,
  water: Drop,
  telecom: WifiHigh,
  transit: Bus,
  taxi: Taxi,
  food: ForkKnife,
  coffee: Coffee,
  fuel: GasPump,
  books: BookOpen,
  cinema: FilmSlate,
  cash: Money,
  transfer_out: ArrowUpRight,
  transfer_in: ArrowDownLeft,
  card: CreditCard,
};

function TxIcon({ t, large, onCanvas }: { t: BankTransaction; large?: boolean; onCanvas?: boolean }) {
  const cat = txCategory(t);
  const Glyph = CATEGORY_ICON[cat];
  return (
    <span
      aria-hidden
      className={cx(
        "grid shrink-0 place-items-center rounded-full",
        large ? "size-14" : "size-9",
        cat === "refund" ? "bg-ok-soft text-ok" : cx(onCanvas ? "bg-paper" : "bg-canvas", large ? "text-ink" : "text-ink-soft"),
      )}
    >
      <Glyph size={large ? 26 : 17} weight={cat === "refund" ? "bold" : "regular"} />
    </span>
  );
}

function TxMeta({ t, tracked, refunded }: { t: BankTransaction; tracked: TrackedDispute[]; refunded: boolean }) {
  const disputed = isDisputed(t, tracked);
  return (
    <span className="tnum block text-[0.8rem] text-muted">
      {clock(t.ts, false)}
      {refunded ? (
        <> · <span className="font-medium text-ok">Refunded</span></>
      ) : disputed ? (
        <> · <span className="font-medium text-ink-soft">Disputed</span></>
      ) : null}
    </span>
  );
}

function Transactions({ txs, tracked, refundedIds, now, onOpen, onDispute }: {
  txs: BankTransaction[];
  tracked: TrackedDispute[];
  refundedIds: Set<string>;
  now: number;
  onOpen: (t: BankTransaction) => void;
  onDispute: (t: BankTransaction) => void;
}) {
  const sorted = useMemo(() => [...txs].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()), [txs]);
  const groups = useMemo(() => {
    const out: Array<{ day: string; items: BankTransaction[] }> = [];
    for (const t of sorted) {
      const day = dayLabel(t.ts, now);
      const last = out[out.length - 1];
      if (last && last.day === day) last.items.push(t);
      else out.push({ day, items: [t] });
    }
    return out;
  }, [sorted, now]);
  const fresh = useFreshKeys(sorted.map((t) => t.id));

  return (
    <section aria-labelledby="bank-tx" className="px-4 pt-6 pb-2">
      <h2 id="bank-tx" className="px-1 text-[0.9333rem] font-semibold">Transactions</h2>
      {sorted.length === 0 ? (
        <p className="mt-2 rounded-2xl bg-paper px-4 py-3.5 text-[0.9333rem] text-muted shadow-[var(--shadow-card)]">No transactions yet.</p>
      ) : (
        groups.map((g) => (
          <div key={g.day} className="mt-3">
            <h3 className="px-1 pb-1.5 text-[0.8rem] font-medium text-muted">{g.day}</h3>
            <ul className="divide-y divide-line overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
              {g.items.map((t) => {
                const out = isOut(t);
                const inline = canDispute(t, tracked) && isRecent(t, now);
                return (
                  <li key={t.id} className={cx(fresh(t.id) && "animate-enter")}>
                    <button type="button" onClick={() => onOpen(t)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-hover active:bg-hover">
                      <TxIcon t={t} />
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 block text-[0.9333rem] leading-snug font-medium break-words">{keepTogether(t.description || "Transaction")}</span>
                        <TxMeta t={t} tracked={tracked} refunded={isRefunded(t) || refundedIds.has(t.id)} />
                      </span>
                      <span className={cx("tnum shrink-0 text-[0.9333rem] font-semibold whitespace-nowrap", !out && "text-ok")}>{signedAmount(t)}</span>
                    </button>
                    {inline && (
                      <div className="px-4 pb-3.5 pl-16">
                        <BankButton
                          variant="primary"
                          size="sm"
                          className="w-full"
                          icon={<ShieldWarning aria-hidden size={17} weight="bold" />}
                          onClick={() => onDispute(t)}
                        >
                          I didn’t make this payment
                        </BankButton>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

// ------------------------------------------------------------------ the bottom sheet: details and the dispute

function TxSheet({ refName, tx, mode, disputed, refunded, disputable, onMode, onClose, onDisputed }: {
  refName: string;
  tx: BankTransaction;
  mode: "details" | "confirm";
  disputed: boolean;
  refunded: boolean;
  disputable: boolean;
  onMode: (m: "details" | "confirm") => void;
  onClose: () => void;
  onDisputed: (d: TrackedDispute) => void;
}) {
  const api = useApi();
  const reduced = usePrefersReducedMotion();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const closing = useRef(false);
  // focus goes to the sheet, not to the text box: on a phone the keyboard would cover the send button
  const panel = useRef<HTMLDivElement>(null);

  // slide in on the next frame, and give focus back to the row when the sheet goes away
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const raf = requestAnimationFrame(() => setShown(true));
    return () => {
      cancelAnimationFrame(raf);
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
  }, [mode]);

  function requestClose() {
    if (busy || closing.current) return;
    closing.current = true;
    setShown(false);
    window.setTimeout(onClose, reduced ? 0 : 200);
  }

  const close = useRef(requestClose);
  close.current = requestClose;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.bankDispute(refName, { transaction_id: tx.id, text: normalizeRo(text.trim()) });
      if (!out?.case_id) throw new Error("The server didn’t return a dispute number.");
      onDisputed({ case_id: out.case_id, transaction_id: tx.id, at: Date.now() });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const status = refunded ? "Refunded" : disputed ? "Disputed" : "Completed";

  return (
    <div className="absolute inset-0 z-30 flex flex-col justify-end" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <div
        aria-hidden
        onClick={requestClose}
        className={cx("absolute inset-0 bg-ink/40 transition-opacity duration-200 ease-[var(--ease-out)]", shown ? "opacity-100" : "opacity-0")}
      />
      <div
        ref={panel}
        tabIndex={-1}
        className={cx(
          "relative max-h-[92%] overflow-y-auto overscroll-contain rounded-t-[28px] bg-paper px-5 pt-2.5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-[var(--shadow-overlay)] outline-none",
          "transition-transform duration-[280ms] ease-[var(--ease-drawer)]",
          shown ? "translate-y-0" : "translate-y-full",
        )}
      >
        <span aria-hidden className="mx-auto mb-2 block h-1 w-9 rounded-full bg-line-strong" />
        <div className="flex items-center justify-between gap-3">
          <h2 id="sheet-title" className="text-[1.0667rem] font-semibold">{mode === "confirm" ? "Dispute this payment" : "Payment details"}</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={requestClose}
            disabled={busy}
            className="relative grid size-9 place-items-center rounded-full bg-canvas text-ink-soft transition-colors before:absolute before:-inset-1 hover:bg-hover hover:text-ink disabled:opacity-50"
          >
            <X aria-hidden size={16} weight="bold" />
          </button>
        </div>

        {mode === "details" ? (
          <div className="mt-3">
            <div className="flex flex-col items-center text-center">
              <TxIcon t={tx} large />
              <p className="mt-3 max-w-full font-medium break-words">{keepTogether(tx.description || "Transaction")}</p>
              <p className={cx("tnum mt-1 text-[2rem] leading-tight font-semibold tracking-[-0.03em]", !isOut(tx) && "text-ok")}>{signedAmount(tx)}</p>
              <p className="tnum mt-1 text-[0.8667rem] text-muted">{fullWhen(tx.ts)}</p>
            </div>
            <dl className="mt-5 divide-y divide-line rounded-2xl bg-canvas px-4 text-[0.9333rem]">
              <div className="flex items-center justify-between gap-4 py-3">
                <dt className="text-muted">Status</dt>
                <dd className={cx("font-medium", status === "Refunded" && "text-ok")}>{status}</dd>
              </div>
              <div className="flex items-center justify-between gap-4 py-3">
                <dt className="text-muted">Type</dt>
                <dd className="font-medium">{isOut(tx) ? "Money out" : "Money in"}</dd>
              </div>
              <div className="flex items-center justify-between gap-4 py-3">
                <dt className="shrink-0 text-muted">Reference</dt>
                <dd className="min-w-0 font-mono text-[0.8rem] break-all text-ink-soft">{tx.id}</dd>
              </div>
            </dl>
            {disputable ? (
              <BankButton
                variant="primary"
                size="lg"
                className="mt-4 w-full"
                icon={<ShieldWarning aria-hidden size={19} weight="bold" />}
                onClick={() => onMode("confirm")}
              >
                I didn’t make this payment
              </BankButton>
            ) : disputed ? (
              <p className="mt-4 rounded-2xl bg-canvas px-4 py-3 text-[0.9333rem] text-ink-soft">
                You’ve disputed this payment. Its progress is at the top of the app, under “Your dispute”.
              </p>
            ) : null}
          </div>
        ) : (
          <div className="mt-3">
            <div className="flex items-center gap-3 rounded-2xl bg-canvas p-3.5">
              <TxIcon t={tx} onCanvas />
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 leading-snug font-medium break-words">{keepTogether(tx.description || "Transaction")}</p>
                <p className="tnum text-[0.8rem] text-muted">{fullWhen(tx.ts)}</p>
              </div>
              <p className="tnum shrink-0 font-semibold">{signedAmount(tx)}</p>
            </div>

            <label className="mt-5 block">
              <span className="font-medium">
                What happened? <span className="font-normal text-muted">(optional)</span>
              </span>
              <textarea
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={1000}
                disabled={busy}
                placeholder="For example: I got a text from a courier and entered my card details."
                className="mt-2 block w-full resize-none rounded-2xl bg-paper px-3.5 py-3 text-[1.0667rem] leading-snug shadow-[inset_0_0_0_1px_var(--color-line-strong)] transition-shadow outline-none focus:shadow-[inset_0_0_0_2px_var(--color-ink)] disabled:opacity-60"
              />
            </label>

            <p className="mt-3.5 flex gap-2.5 text-[0.8667rem] leading-snug text-ink-soft">
              <ShieldCheck aria-hidden size={18} weight="fill" className="mt-px shrink-0 text-ok" />
              <span>If you didn’t authorize this payment, the law requires us to refund you by the end of the next business day.</span>
            </p>

            {error && (
              <p role="alert" className="mt-4 flex items-start gap-2 rounded-2xl bg-danger-soft px-3.5 py-3 text-[0.9333rem] text-danger">
                <WarningCircle aria-hidden size={18} className="mt-px shrink-0" />
                <span>Your dispute didn’t go through. {withPeriod(error)} Try again.</span>
              </p>
            )}

            <BankButton variant="primary" size="lg" className="mt-5 w-full" busy={busy} onClick={submit}>
              {busy ? "Sending…" : "Send dispute"}
            </BankButton>
            <BankButton variant="ghost" className="mt-1.5 w-full" disabled={busy} onClick={requestClose}>
              Cancel
            </BankButton>
          </div>
        )}
      </div>
    </div>
  );
}
