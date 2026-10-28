/**
 * Shared pieces for the Rules, Evaluation and MCP pages: copy to clipboard with a fallback,
 * code blocks, accent-insensitive search and a few text helpers.
 */
import { Check, Copy } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { isValidDate, num, TZ } from "../../api/format";
import { cx } from "../../ui/kit";

// ---------------------------------------------------------------- text

/** "29 Oct 2026, 23:59", Bucharest time. `null` when the value isn't a date. */
export function dateTimeYear(v: string | number | Date | null | undefined): string | null {
  if (v === null || v === undefined || v === "" || !isValidDate(v)) return null;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(v instanceof Date ? v : new Date(v));
}

/**
 * A few backend texts still say "T+1". The console says "next business day" instead,
 * so the same deadline never has two names.
 */
export function withoutT1(text: string): string {
  return text
    .replace(/\s*\(T\+1\)/g, "")
    .replace(/^T\+1 clock\b/, "Refund deadline clock")
    .replace(/^T\+1 runs from\b/, "The refund deadline runs from")
    .replace(/\bthe T\+1 (refund|deadline)\b/g, "the next-business-day $1")
    .replace(/\bT\+1 (refund|deadline)\b/g, "next-business-day $1")
    .replace(/\bT\+1\b/g, "next business day");
}

/** For search: no accents, lower case. */
export function fold(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Romanian plural (1 regulă, 3 reguli, 20 de reguli). Only the legacy wall page still uses it. */
export function ro(n: number, one: string, many: string): string {
  if (n === 1) return `1 ${one}`;
  const rest = Math.abs(n) % 100;
  const de = n !== 0 && (rest === 0 || rest >= 20);
  return `${num(n)} ${de ? "de " : ""}${many}`;
}

// ---------------------------------------------------------------- clipboard

/** The Clipboard API when the page is in a secure context, `execCommand("copy")` otherwise. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the older way */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

function selectContents(el: HTMLElement | null) {
  if (!el) return;
  const range = document.createRange();
  range.selectNodeContents(el);
  const sel = window.getSelection();
  sel?.removeAllRanges();
  sel?.addRange(range);
}

/**
 * A quiet copy button: "Copy" turns into "Copied" for a moment. If the browser refuses,
 * `onFail` runs so the caller can select the text for a manual copy.
 */
export function CopyButton({ text, label = "Copy", onFail, className }: {
  text: string; label?: string; onFail?: () => void; className?: string;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const done = copied === text;

  async function onCopy() {
    const ok = await copyText(text);
    window.clearTimeout(timer.current);
    setFailed(!ok);
    if (!ok) {
      setCopied(null);
      onFail?.();
      return;
    }
    setCopied(text);
    timer.current = window.setTimeout(() => setCopied(null), 1600);
  }

  return (
    <>
      <button
        type="button"
        onClick={onCopy}
        className={cx(
          "press inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[0.8rem] font-medium transition-colors",
          done ? "text-ink" : "text-ink-soft hover:bg-hover hover:text-ink",
          className,
        )}
      >
        {done ? <Check aria-hidden size={14} weight="bold" className="text-ok" /> : <Copy aria-hidden size={14} className="text-subtle" />}
        {done ? "Copied" : label}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {done ? "Copied to the clipboard." : failed ? "Copying didn't work. The text is selected, so you can copy it yourself." : ""}
      </span>
    </>
  );
}

function ManualCopyNote() {
  return (
    <p className="border-t border-line bg-paper px-4 py-2 text-[0.8rem] text-muted">
      This browser blocked copying. The text is selected: press ⌘C on a Mac or Ctrl+C elsewhere.
    </p>
  );
}

// ---------------------------------------------------------------- code

/** A labeled, copyable block of code or configuration. */
export function CodeBlock({ code, label, className }: { code: string; label?: string; className?: string }) {
  const pre = useRef<HTMLPreElement>(null);
  const [manual, setManual] = useState(false);
  return (
    <div className={cx("overflow-hidden rounded-xl bg-canvas ring-1 ring-inset ring-line", className)}>
      <div className="flex h-10 items-center justify-between gap-3 border-b border-line bg-paper pr-1.5 pl-4">
        <span className="truncate text-[0.8rem] font-medium text-muted">{label}</span>
        <CopyButton text={code} onFail={() => { setManual(true); selectContents(pre.current); }} />
      </div>
      <pre
        ref={pre}
        tabIndex={0}
        className="max-h-[28rem] overflow-auto px-4 py-3 font-mono text-[0.8rem] leading-relaxed whitespace-pre text-ink-soft"
      >
        {code}
      </pre>
      {manual && <ManualCopyNote />}
    </div>
  );
}

/** One shell command with a prompt sign and a copy button. */
export function CommandLine({ command, className }: { command: string; className?: string }) {
  const code = useRef<HTMLElement>(null);
  const [manual, setManual] = useState(false);
  return (
    <div className={cx("w-full overflow-hidden rounded-xl bg-paper text-left shadow-[var(--shadow-card)]", className)}>
      <div className="flex h-11 items-center gap-3 pr-1.5 pl-4">
        <span aria-hidden className="font-mono text-[0.8667rem] text-subtle select-none">$</span>
        <code ref={code} className="min-w-0 flex-1 overflow-x-auto font-mono text-[0.8667rem] whitespace-nowrap text-ink">
          {command}
        </code>
        <CopyButton text={command} label="Copy command" onFail={() => { setManual(true); selectContents(code.current); }} />
      </div>
      {manual && <ManualCopyNote />}
    </div>
  );
}

/** Short code inside a sentence: commands and identifiers only. */
export function InlineCode({ children }: { children: string }) {
  return <code className="rounded-md bg-hover px-1.5 py-0.5 font-mono text-[0.8rem] text-ink-soft">{children}</code>;
}

/** Table classes for the legacy wall page, in the console's list style. */
export const TABLE = {
  wrap: "overflow-x-auto rounded-2xl bg-paper shadow-[var(--shadow-card)]",
  table: "w-full border-collapse text-left",
  headRow: "border-b border-line text-[0.8rem] text-subtle",
  th: "px-5 py-2.5 font-normal",
  row: "border-b border-line last:border-b-0 align-top",
  td: "px-5 py-3",
};
