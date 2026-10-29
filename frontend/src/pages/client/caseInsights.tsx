/**
 * The case page's newer pieces: picking the disputed payment, identification, linked cases,
 * similar past cases, the legal sources behind the drafts and the number check.
 * Each one stays quiet until it has something to say.
 */
import { CaretDown, Check, Warning, X } from "@phosphor-icons/react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { dateTime, money, pct, plural, statusLabel, toMoney, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { AgentEvent, CaseDetail, Decision, DecisionReason, GroundingEntry, KbHit, NumericCheck, Precedent, StandardRecord, TxCandidate } from "../../api/types";
import { Banner, Button, cx, ErrorNote, IdTag, Panel, Skeleton } from "../../ui/kit";
import { CandidateList, NONE } from "./intakeUi";
import { HitList, HitRow, PassageSheet } from "./knowledgeUi";

// ---------------------------------------------------------------- helpers

/** The plain-language reason for one decision: same verdict code, preferably one of its rules. */
export function reasonFor(d: Decision | undefined, reasons: DecisionReason[] | undefined): DecisionReason | undefined {
  if (!d || !reasons?.length) return undefined;
  const same = reasons.filter((r) => r.decision === d.decision || r.decision === d.question);
  return same.find((r) => d.rule_ids?.includes(r.rule_id)) ?? same[0];
}

/** The payments to pick from: the interrupt's own list, its payload, the live event, then the match. */
export function pickCandidates(d: CaseDetail, events: AgentEvent[]): TxCandidate[] {
  const it = d.interrupt;
  if (it?.candidates?.length) return it.candidates;
  if (it?.payload?.candidates?.length) return it.payload.candidates;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type !== "CUSTOM" || e.name !== "interrupt") continue;
    const data = (e.data ?? {}) as { kind?: string; candidates?: TxCandidate[]; payload?: { kind?: string; candidates?: TxCandidate[] } };
    const list = data.candidates ?? data.payload?.candidates;
    if ((data.kind ?? data.payload?.kind) === "pick_transaction" && list?.length) return list;
  }
  return d.match?.candidates ?? [];
}

export function isPickPending(d: CaseDetail): boolean {
  const it = d.interrupt;
  return Boolean(it?.pending && (it.kind === "pick_transaction" || it.payload?.kind === "pick_transaction"));
}

const USED_IN: Record<string, string> = { letter: "the letter", debate: "the arguments", rts: "the report" };

export function usedInLabel(v: string): string {
  return USED_IN[v] ?? v;
}

// ---------------------------------------------------------------- the person picks the payment

export function PickPaymentBanner({ d, caseId, events, onDone }: { d: CaseDetail; caseId: string; events: AgentEvent[]; onDone: () => Promise<void> }) {
  const api = useApi();
  const candidates = pickCandidates(d, events);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = busy || Boolean(d.interrupt?.resuming);
  async function submit() {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      await api.approve(caseId, { action: "pick_transaction", tx_id: value === NONE ? null : value, approver: "OPERATOR-01" });
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The choice wasn’t recorded");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Banner tone="now" title={d.interrupt?.prompt ?? "Which payment does the customer dispute?"}>
      <p>{d.match?.reason ?? "More than one payment could match the message."} The agents continue with the payment you pick.</p>
      <div className="mt-3 max-w-[44rem] text-ink">
        <CandidateList
          name="pick-payment"
          legend="The disputed payment"
          candidates={candidates}
          value={value}
          onChange={setValue}
          disabled={locked}
          none={{ label: "None of these", hint: "VersoML asks the customer which payment it is. The refund deadline keeps running." }}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="primary" busy={busy} disabled={!value || locked} onClick={submit}>
          {value === NONE ? "Ask the customer" : "Use this payment"}
        </Button>
        {d.interrupt?.resuming && <span className="text-muted">Choice received. Continuing…</span>}
        {error && <span className="font-medium text-danger">{error}.</span>}
      </div>
    </Banner>
  );
}

// ---------------------------------------------------------------- identification

export function IdentificationPanel({ d }: { d: CaseDetail }) {
  const m = d.match;
  if (!m) return null;
  const chosen = m.candidates?.find((c) => c.tx_id === m.tx_id);
  const others = (m.candidates ?? []).filter((c) => c.tx_id !== m.tx_id);
  const pending = isPickPending(d);
  return (
    <Panel title="Customer and payment">
      <dl className="flex flex-col gap-3 text-[0.9333rem]">
        <div>
          <dt className="text-[0.8rem] text-muted">Customer</dt>
          {m.customer_ref ? (
            <dd className="mt-0.5">
              <span className="font-medium">{d.summary.customer_alias}</span> <span className="id-text text-[0.8rem] text-subtle">{m.customer_ref}</span>
              {m.customer_match_reason && <span className="mt-0.5 block text-[0.8667rem] text-muted">{m.customer_match_reason}</span>}
            </dd>
          ) : (
            <dd className="mt-0.5">
              <span className="font-medium">Not identified</span>
              <span className="mt-0.5 block text-[0.8667rem] text-muted">VersoML asks the customer to confirm who they are.</span>
            </dd>
          )}
        </div>
        <div>
          <dt className="text-[0.8rem] text-muted">Payment</dt>
          {m.tx_id ? (
            <dd className="mt-0.5">
              <span className="id-text font-medium">{m.tx_id}</span>
              {chosen && <span className="tnum text-ink-soft"> · {money({ value: chosen.amount, currency: chosen.currency ?? "RON" })}</span>}
              <span className="mt-0.5 block text-[0.8667rem] text-muted">{m.reason}{m.confidence && m.confidence < 1 ? ` Match score ${pct(m.confidence)}.` : ""}</span>
            </dd>
          ) : (
            <dd className="mt-0.5">
              <span className="font-medium">{pending ? "Waiting for a person to pick it" : "Not identified"}</span>
              <span className="mt-0.5 block text-[0.8667rem] text-muted">{m.reason}</span>
            </dd>
          )}
        </div>
      </dl>
      {others.length > 0 && !pending && (
        <details className="group mt-3">
          <summary className="cursor-pointer list-none text-[0.8667rem] font-medium text-ink-soft underline decoration-line-strong underline-offset-2 hover:text-ink">
            <span className="group-open:hidden">Other candidates ({others.length})</span>
            <span className="hidden group-open:inline">Hide other candidates</span>
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {others.map((c) => (
              <li key={c.tx_id} className="rounded-lg bg-canvas px-3 py-2 text-[0.8667rem]">
                <p className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate font-medium">{c.payee}</span>
                  <span className="tnum shrink-0">{money({ value: c.amount, currency: c.currency ?? "RON" })}</span>
                </p>
                <p className="mt-0.5 text-[0.8rem] text-muted">
                  <span className="id-text">{c.tx_id}</span> · <span className="tnum">{pct(c.score)}</span> match{c.reasons?.length ? ` · ${c.reasons.join(" · ")}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- linked cases

const INDICATOR: Record<string, string> = {
  payee_account: "Payee account",
  iban: "Payee account",
  beneficiary_iban: "Payee account",
  domain: "Website",
  url: "Link",
  phone: "Phone number",
  sms_sender: "Text sender",
};

export function LinkedCasesPanel({ d }: { d: CaseDetail }) {
  const c = d.campaign;
  const [all, setAll] = useState(false);
  const others = (c?.case_ids ?? []).filter((id) => id !== d.summary.case_id);
  if (!c || !others.length) return null;
  return (
    <Panel title="Linked cases" description={`The same scam as ${plural(others.length, "other dispute", "other disputes")}.`}>
      <dl className="flex flex-col gap-2 text-[0.9333rem]">
        {(c.shared_indicators ?? []).map((si, i) => (
          <div key={i}>
            <dt className="text-[0.8rem] text-muted">{INDICATOR[si.kind] ?? si.kind.replace(/_/g, " ")}</dt>
            <dd className="tnum mt-0.5 break-all">{si.value_masked}</dd>
          </div>
        ))}
      </dl>
      <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Linked cases">
        {(all ? others : others.slice(0, 8)).map((id) => (
          <li key={id}>
            <Link to={`/cases/${encodeURIComponent(id)}`} className="id-text inline-flex h-[1.375rem] items-center rounded-md bg-paper px-1.5 text-[0.7667rem] font-medium text-muted ring-1 ring-inset ring-line transition-colors hover:text-ink hover:ring-line-strong">
              {id}
            </Link>
          </li>
        ))}
        {!all && others.length > 8 && (
          <li>
            <button type="button" onClick={() => setAll(true)} className="inline-flex h-[1.375rem] items-center rounded-md px-1.5 text-[0.8rem] font-medium text-muted underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink">
              +{others.length - 8} more
            </button>
          </li>
        )}
      </ul>
      <p className="mt-3 text-[0.8rem] text-muted">
        Grouped as campaign <span className="id-text">{c.campaign_id}</span> · the shared details match <span className="tnum">{pct(c.similarity)}</span>
      </p>
    </Panel>
  );
}

// ---------------------------------------------------------------- the standard record

const PAYMENT_TYPE: Record<StandardRecord["payment_type"], string> = {
  card: "Card payment", credit_transfer: "Credit transfer", instant_credit_transfer: "Instant credit transfer",
};
const CONTACT: Record<string, string> = { sms: "Text message", call: "Phone call", email: "Email", messaging: "Messaging app", website: "Website", unknown: "Not stated" };
const SCA_METHOD: Record<string, string> = { app_push: "approval in the app", sms_otp: "SMS code", biometric: "biometrics", password: "password" };
const THREE_DS: Record<string, string> = { authenticated: "3-D Secure authenticated", attempted: "3-D Secure attempted", not_authenticated: "no 3-D Secure" };

/**
 * The case in published codes, the same shape for every case: what a supervisor, another bank or a model reads
 * without knowing VersoML. Built by the rules step from facts, never from free text.
 */
export function StandardRecordPanel({ d }: { d: CaseDetail }) {
  const r = d.standard;
  const [copied, setCopied] = useState(false);
  if (!r) return null;
  async function copy() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(r, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }
  const how = r.sca_method ? `, ${SCA_METHOD[r.sca_method] ?? r.sca_method.replace(/_/g, " ")}` : "";
  const auth = r.authentication === "sca"
    ? r.sca_step === "device_enrollment" ? `SCA only to enrol a new device${how}; none for the payment` : `SCA done${how}`
    : r.authentication === "no_sca" ? "No SCA" : "Not in the log";
  const rows: Array<[string, ReactNode, string?]> = [
    ["Fraud type", r.fraud_type_label ?? "Not fraud: a dispute about the payment itself", r.fraud_type ? "EBA/GL/2018/05" : undefined],
    ["Payment", <>{PAYMENT_TYPE[r.payment_type]}{r.amount ? <> · <span className="tnum">{money(r.amount)}</span></> : null}</>, "ISO 4217"],
    ["Paid, then reported", <>{dateTime(r.executed_at)} → {dateTime(r.reported_at)}{r.days_to_report != null ? <span className="text-muted"> · {r.days_to_report === 0 ? "same day" : `${plural(r.days_to_report, "day", "days")} later`}</span> : null}</>, "ISO 8601"],
    ["Authentication", <>{auth}{r.card_scheme ? <span className="text-muted"> · {r.card_scheme === "visa" ? "Visa" : "Mastercard"}{r.eci ? `, ECI ${r.eci}` : ""}{r.three_ds ? `, ${THREE_DS[r.three_ds]}` : ""}</span> : null}</>],
  ];
  if (r.payee_iban) rows.push(["Payee account", <><span className="tnum">{r.payee_iban}</span>{r.payee_iban_valid != null && <span className={r.payee_iban_valid ? "text-muted" : "text-danger"}> · {r.payee_iban_valid ? "check digits valid" : "check digits wrong"}</span>}</>, "ISO 13616"]);
  if (r.merchant_mcc) rows.push(["Merchant category", <span className="tnum">MCC {r.merchant_mcc}</span>, "ISO 18245"]);
  if (r.contact_channel) rows.push(["First contact", CONTACT[r.contact_channel] ?? r.contact_channel]);
  if (r.websites.length || r.phones.length) {
    rows.push(["Indicators", (
      <span className="flex flex-wrap gap-1.5">
        {r.websites.map((w) => <IdTag key={w}>{w}</IdTag>)}
        {r.phones.map((p) => <IdTag key={p}>{p}</IdTag>)}
      </span>
    ), "E.164, IDNA"]);
  }
  return (
    <Panel
      title="Standard record"
      description="The same codes for every case, so reports and other systems read it without VersoML."
      actions={<Button size="sm" onClick={copy}>{copied ? <><Check size={14} weight="bold" /> Copied</> : "Copy JSON"}</Button>}
    >
      <dl className="grid gap-x-6 gap-y-3 text-[0.9333rem] sm:grid-cols-[10rem_minmax(0,1fr)]">
        {rows.map(([label, value, standard]) => (
          <div key={label} className="contents">
            <dt className="text-[0.8rem] text-muted sm:pt-0.5">{label}{standard && <span className="block text-[0.7rem] text-subtle">{standard}</span>}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      {r.issues.length > 0 && (
        <ul className="mt-4 flex flex-col gap-1.5 rounded-xl bg-warn-soft px-4 py-3 text-[0.8667rem] text-ink-soft" aria-label="What the data didn't let VersoML read">
          {r.issues.map((i) => (
            <li key={i} className="flex gap-2"><Warning size={16} className="mt-0.5 shrink-0 text-warn" />{i}</li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-[0.75rem] text-subtle"><span className="id-text">{r.schema_version}</span> · sealed with the evidence file</p>
    </Panel>
  );
}

// ---------------------------------------------------------------- similar past cases (information only)

function outcomeParts(o: Record<string, unknown>): string[] {
  const out: string[] = [];
  if (typeof o.decision === "string") out.push(verdictLabel(o.decision));
  else if (typeof o.status === "string") out.push(statusLabel(o.status));
  if (typeof o.refund_days === "number") out.push(`refunded in ${plural(o.refund_days, "business day", "business days")}`);
  const rec = toMoney(o.recovered as never);
  if (rec) out.push(rec.value > 0 ? `recovered ${money(rec)}` : "nothing recovered");
  if (typeof o.note === "string" && o.note) out.push(o.note.replace(/\.$/, ""));
  return out;
}

const KNOWN_OUTCOME = new Set(["decision", "status", "refund_days", "recovered", "note", "amount"]);

export function PrecedentsPanel({ caseId }: { caseId: string }) {
  const api = useApi();
  const [open, setOpen] = useState(false);
  const res = useResource(open ? () => api.precedents(caseId) : null, [open, caseId]);
  const [hit, setHit] = useState<Precedent | null>(null);
  const list = Array.isArray(res.data) ? res.data : [];
  return (
    <section aria-label="Similar past cases" className="rounded-xl bg-paper shadow-[var(--shadow-card)]">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="flex w-full items-start justify-between gap-3 rounded-xl px-5 py-4 text-left transition-colors hover:bg-canvas">
        <span className="min-w-0">
          <span className="block text-[0.9333rem] font-semibold">Similar past cases</span>
          <span className="mt-0.5 block text-[0.8667rem] text-muted">For information only. The rules don’t use them.</span>
        </span>
        <CaretDown aria-hidden size={16} className={cx("mt-1 shrink-0 text-subtle transition-transform duration-150", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-5 pb-4">
          {res.error && !res.data ? (
            <ErrorNote error={res.error} what="similar cases" onRetry={res.reload} />
          ) : !res.data ? (
            <div className="flex flex-col gap-2"><Skeleton className="h-12 rounded-lg" /><Skeleton className="h-12 rounded-lg" /></div>
          ) : list.length === 0 ? (
            <p className="text-[0.9333rem] text-muted">No closed case looks like this one yet.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-line">
              {list.map((p, i) => (
                <li key={p.hit?.id ?? i} className="py-3 first:pt-0 last:pb-0">
                  <button type="button" onClick={() => setHit(p)} className="text-left text-[0.9333rem] font-medium leading-snug hover:underline hover:underline-offset-2">
                    {p.hit?.title ?? p.case_id_masked}
                  </button>
                  {outcomeParts(p.outcome ?? {}).length > 0 && <p className="mt-0.5 text-[0.8667rem] text-ink-soft">{outcomeParts(p.outcome ?? {}).join(" · ")}</p>}
                  <p className="mt-0.5 text-[0.8rem] text-muted">
                    <span className="id-text">{p.case_id_masked}</span>
                    {p.hit?.source ? ` · ${p.hit.source}` : ""}
                    {typeof p.hit?.score === "number" && p.hit.score <= 1 ? ` · ${pct(p.hit.score)} similar` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {hit?.hit && (
        <PassageSheet
          hit={hit.hit}
          onClose={() => setHit(null)}
          note={
            <>
              A past case, shown for information. The rules don’t read past cases, so nothing here changes this decision.
              {Object.entries(hit.outcome ?? {}).filter(([k]) => !KNOWN_OUTCOME.has(k)).map(([k, v]) => (
                <span key={k} className="mt-1 block text-[0.8667rem] text-muted">{k.replace(/_/g, " ")}: {typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              ))}
            </>
          }
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------- legal sources (grounding)

/** One row per passage, with where the drafts used it. */
export function groupGrounding(grounding: GroundingEntry[] | undefined): Array<{ hit: KbHit; usedIn: string[] }> {
  const by = new Map<string, { hit: KbHit; usedIn: string[] }>();
  for (const g of grounding ?? []) {
    if (!g?.hit?.id) continue;
    const cur = by.get(g.hit.id) ?? { hit: g.hit, usedIn: [] };
    if (!cur.usedIn.includes(g.used_in)) cur.usedIn.push(g.used_in);
    by.set(g.hit.id, cur);
  }
  return [...by.values()];
}

export function LegalSourcesPanel({ grounding, onOpen }: { grounding: GroundingEntry[] | undefined; onOpen: (hit: KbHit, usedIn: string[]) => void }) {
  const rows = useMemo(() => groupGrounding(grounding), [grounding]);
  if (!rows.length) return null;
  return (
    <section aria-labelledby="legal-sources">
      <div className="mb-3">
        <h3 id="legal-sources" className="text-[0.9333rem] font-semibold">Legal sources</h3>
        <p className="mt-0.5 text-[0.8667rem] text-muted">The passages the letter and the arguments rely on. Open one to read it.</p>
      </div>
      <HitList label="Legal sources">
        {rows.map((r) => (
          <HitRow
            key={r.hit.id}
            hit={r.hit}
            onOpen={(h) => onOpen(h, r.usedIn)}
            extra={<span className="text-[0.8rem] text-muted">Used in {r.usedIn.map(usedInLabel).join(" and ")}</span>}
          />
        ))}
      </HitList>
    </section>
  );
}

export function usedInNote(usedIn: string[]): string {
  return `Cited in ${usedIn.map(usedInLabel).join(" and ")}. The decision itself comes from the rules engine, not from this text.`;
}


// ---------------------------------------------------------------- the number check

/** The check's one-line result, for the strip of checks under the letter. */
export function NumericCheckItem({ check }: { check: NumericCheck | null | undefined }) {
  if (!check) return null;
  const n = check.mismatches?.length ?? 0;
  if (check.passed && n === 0) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Check size={16} weight="bold" className="text-ok" />
        <span className="text-ink-soft">Numbers match the evidence <span className="tnum text-muted">({check.checked} checked)</span></span>
      </span>
    );
  }
  if (check.passed) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <Warning size={16} className="text-warn" />
        <span className="text-ink-soft">{plural(n, "number was", "numbers were")} corrected <span className="tnum text-muted">({check.checked} checked)</span></span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <X size={16} className="text-danger" />
      <span className="text-danger">{plural(n, "number doesn’t", "numbers don’t")} match the evidence</span>
    </span>
  );
}

/** The mismatches themselves, when there are any. */
export function NumericMismatches({ check }: { check: NumericCheck | null | undefined }) {
  const list = check?.mismatches ?? [];
  if (!check || !list.length) return null;
  return (
    <div className={cx("mt-4 rounded-xl px-4 py-3 text-[0.9333rem]", check.passed ? "bg-warn-soft" : "bg-danger-soft")}>
      <p className="font-medium">
        {check.passed && check.rewritten
          ? "The letter writer used a number the evidence doesn’t support, so the letter was rewritten."
          : "These numbers don’t match the evidence. A person checks the letter before it goes out."}
      </p>
      <ul className="mt-1.5 flex flex-col gap-1">
        {list.map((m, i) => (
          <li key={i} className="text-ink-soft">
            <span className="tnum font-medium text-ink"><s>{m.value}</s> → {m.expected}</span>
            {m.where ? <span className="text-muted"> · in {usedInLabel(m.where)}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The decision's plain-language reason, with its rule. */
export function ReasonLine({ reason, className }: { reason: DecisionReason | undefined; className?: string }) {
  if (!reason?.sentence) return null;
  return (
    <p className={cx("text-[0.8667rem] text-ink-soft", className)}>
      {reason.sentence}{" "}
      {/* the sentence often names its rule already, as "(REC-03)": no second tag then */}
      {reason.rule_id && reason.rule_id !== "—" && !reason.sentence.includes(reason.rule_id) && <IdTag>{reason.rule_id}</IdTag>}
    </p>
  );
}
