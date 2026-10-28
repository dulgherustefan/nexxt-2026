/**
 * Shared pieces for identification: the candidate payments a person picks from (new case and
 * case page), and the words for languages, contact channels and match strength.
 */
import type { ReactNode } from "react";
import { channelLabel, dateTime, money, pct } from "../../api/format";
import type { TxCandidate } from "../../api/types";
import { cx } from "../../ui/kit";

const LANG_FALLBACK: Record<string, string> = { ro: "Romanian", en: "English", de: "German", hu: "Hungarian", fr: "French", es: "Spanish", it: "Italian" };

/** "ro" → "Romanian". Unknown codes stay as they are, in capitals. */
export function languageName(code: string | null | undefined): string {
  if (!code) return "Not detected";
  const c = code.toLowerCase().split(/[-_]/)[0];
  try {
    const name = new Intl.DisplayNames(["en"], { type: "language" }).of(c);
    if (name && name.toLowerCase() !== c) return name;
  } catch {
    /* older browsers */
  }
  return LANG_FALLBACK[c] ?? code.toUpperCase();
}

const CONTACT: Record<string, string> = {
  sms: "Text message",
  apel: "Phone call",
  call: "Phone call",
  phone: "Phone call",
  email: "Email",
  mesagerie: "Messaging app",
  chat: "Messaging app",
  site: "Website",
  website: "Website",
};

export function contactLabel(v: string | null | undefined): string | null {
  if (!v || v === "necunoscut" || v === "unknown") return null;
  return CONTACT[v.toLowerCase()] ?? v;
}

/** A customer match, in words. */
export function matchStrength(confidence: number | null | undefined): string {
  const c = confidence ?? 0;
  if (c >= 0.9) return "Strong match";
  if (c >= 0.7) return "Likely match";
  return "Weak match";
}

/** "AUTO" for "let VersoML decide", "NONE" for "none of these". */
export const AUTO = "__auto__";
export const NONE = "__none__";

function Option({ name, value, checked, onChange, disabled, children }: {
  name: string; value: string; checked: boolean; onChange: (v: string) => void; disabled?: boolean; children: ReactNode;
}) {
  return (
    <label
      className={cx(
        "flex gap-3 rounded-xl px-4 py-3 transition-colors",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        checked ? "bg-canvas ring-1 ring-inset ring-ink" : "ring-1 ring-inset ring-line hover:bg-canvas",
      )}
    >
      <input type="radio" name={name} value={value} checked={checked} disabled={disabled} onChange={() => onChange(value)} className="mt-1 accent-ink" />
      <span className="min-w-0 flex-1">{children}</span>
    </label>
  );
}

/**
 * The payments that could be the disputed one, best first. With `auto`, the first option leaves the
 * choice to VersoML; with `none`, the last one says none of them is right.
 */
export function CandidateList({ name, candidates, value, onChange, best, auto, none, disabled, legend }: {
  name: string;
  candidates: TxCandidate[];
  value: string;
  onChange: (v: string) => void;
  best?: string | null;
  auto?: { label: string; hint: string };
  none?: { label: string; hint: string };
  disabled?: boolean;
  legend: string;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5" disabled={disabled}>
      <legend className="sr-only">{legend}</legend>
      {auto && (
        <Option name={name} value={AUTO} checked={value === AUTO} onChange={onChange} disabled={disabled}>
          <span className="block font-medium">{auto.label}</span>
          <span className="mt-0.5 block text-[0.8667rem] text-muted">{auto.hint}</span>
        </Option>
      )}
      {candidates.map((c) => (
        <Option key={c.tx_id} name={name} value={c.tx_id} checked={value === c.tx_id} onChange={onChange} disabled={disabled}>
          <span className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate font-medium">{c.payee}</span>
            <span className="tnum shrink-0 font-medium">{money({ value: c.amount, currency: c.currency ?? "RON" })}</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-baseline justify-between gap-x-3 text-[0.8rem] text-muted">
            <span>
              {channelLabel(c.channel ?? undefined)} · <span className="tnum">{dateTime(c.ts)}</span> · <span className="id-text text-subtle">{c.tx_id}</span>
            </span>
            <span className="tnum" title="How well the payment matches the message">
              {best === c.tx_id && <span className="mr-1.5 font-medium text-ink-soft">Best match ·</span>}
              {pct(c.score)} match
            </span>
          </span>
          {c.reasons?.length ? <span className="mt-1 block text-[0.8rem] text-ink-soft">{c.reasons.join(" · ")}</span> : null}
        </Option>
      ))}
      {none && (
        <Option name={name} value={NONE} checked={value === NONE} onChange={onChange} disabled={disabled}>
          <span className="block font-medium">{none.label}</span>
          <span className="mt-0.5 block text-[0.8667rem] text-muted">{none.hint}</span>
        </Option>
      )}
    </fieldset>
  );
}
