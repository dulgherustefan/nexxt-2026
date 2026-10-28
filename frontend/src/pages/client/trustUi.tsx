/**
 * Piese comune pentru paginile de încredere (Zidul, Reguli, Evaluare, MCP):
 * plurale în română, copiere cu rezervă, bloc de cod, căutare fără diacritice.
 */
import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { num } from "../../api/format";
import { cx } from "../../ui/kit";

/** 1 regulă · 3 reguli · 20 de reguli · 101 reguli · 120 de reguli. */
export function ro(n: number, one: string, many: string): string {
  if (n === 1) return `1 ${one}`;
  const rest = Math.abs(n) % 100;
  const de = n !== 0 && (rest === 0 || rest >= 20);
  return `${num(n)} ${de ? "de " : ""}${many}`;
}

/** Pentru căutare: fără diacritice, litere mici, cedila tratată ca virgula. */
export function fold(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Clipboard API când există (context securizat), altfel `execCommand("copy")`. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* trecem la varianta veche */
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

/** Bloc de cod copiabil. Dacă browserul refuză copierea, textul rămâne selectat pentru Ctrl+C. */
export function CodeBlock({ code, label, className }: { code: string; label?: string; className?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  const pre = useRef<HTMLPreElement>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => setState("idle"), [code]);

  async function onCopy() {
    const ok = await copyText(code);
    window.clearTimeout(timer.current);
    if (ok) {
      setState("copied");
      timer.current = window.setTimeout(() => setState("idle"), 2000);
    } else {
      setState("manual");
      selectContents(pre.current);
    }
  }

  return (
    <div className={cx("overflow-hidden rounded-md border border-line bg-canvas", className)}>
      <div className="flex min-h-10 items-center justify-between gap-3 border-b border-line bg-paper px-3 py-1.5">
        <span className="text-[0.8667rem] font-semibold text-muted">{label}</span>
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-paper px-2.5 text-[0.8667rem] font-semibold hover:bg-hover"
        >
          {state === "copied" ? <Check aria-hidden className="size-3.5 text-ok" /> : <Copy aria-hidden className="size-3.5" />}
          <span aria-live="polite">{state === "copied" ? "Copiat" : "Copiază"}</span>
        </button>
      </div>
      <pre ref={pre} className="overflow-x-auto px-3 py-2.5 font-mono text-[0.8667rem] leading-relaxed whitespace-pre text-ink">{code}</pre>
      {state === "manual" && (
        <p className="border-t border-line bg-paper px-3 py-1.5 text-[0.8667rem] text-muted">
          Browserul nu permite copierea automată aici. Textul e selectat: apasă Ctrl+C (⌘C pe Mac).
        </p>
      )}
    </div>
  );
}

/** Cod scurt în text: doar pentru comenzi și identificatori. */
export function InlineCode({ children }: { children: string }) {
  return <code className="rounded-sm border border-line bg-canvas px-1 py-px font-mono text-[0.8667rem]">{children}</code>;
}

/** Tabel standard, aliniat cu lista de contestații. */
export const TABLE = {
  wrap: "overflow-x-auto rounded-lg border border-line bg-paper",
  table: "w-full border-collapse text-left",
  headRow: "border-b border-line bg-canvas text-[0.8667rem] text-muted",
  th: "px-4 py-2.5 font-semibold",
  row: "border-b border-line last:border-b-0 align-top",
  td: "px-4 py-3",
};
