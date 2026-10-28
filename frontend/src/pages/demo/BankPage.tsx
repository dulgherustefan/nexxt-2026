import { ArrowDownLeft, ArrowUpRight, CircleAlert, CircleCheck, Info, Loader2, ShieldAlert, User, WifiOff, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { clock, normalizeRo } from "../../api/format";
import { useApi, usePrefersReducedMotion, useResource, useRuntime } from "../../api/runtime";
import type { BankNotification, BankState, BankTransaction, CaseDetail } from "../../api/types";
import { ApiError } from "../../api/client";
import { Button, cx, IdTag, Skeleton, StepIcon, useNowTick } from "../../ui/kit";
import {
  amount2,
  canDispute,
  clientFrom,
  dayLabel,
  FINAL,
  isDisputed,
  isOut,
  isRecent,
  isRefundTx,
  loadTracked,
  plainWhen,
  saveTracked,
  shortWhen,
  signedLei,
  stepsFor,
  type Step,
  type TrackedDispute,
} from "./bankModel";

type SheetState = { tx: BankTransaction; mode: "details" | "confirm" } | null;

export default function BankPage() {
  const api = useApi();
  const { mode } = useRuntime();
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
    document.title = "Banca Demo";
  }, []);

  const [sheet, setSheet] = useState<SheetState>(null);
  const data = bank.data;
  const txs = useMemo(() => (Array.isArray(data?.transactions) ? data.transactions : []), [data]);
  const notes = useMemo(
    () => (Array.isArray(data?.notifications) ? [...data.notifications] : []).sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()),
    [data],
  );

  function onDisputed(d: TrackedDispute) {
    setTracked((list) => [d, ...list.filter((x) => x.case_id !== d.case_id)].slice(0, 5));
    setSheet(null);
    main.current?.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
    void bank.reload();
  }

  const notFound = bank.error instanceof ApiError && bank.error.status === 404;

  return (
    <div className="min-h-dvh bg-canvas sm:flex sm:items-center sm:justify-center sm:p-6">
      <div className="relative mx-auto flex h-dvh w-full max-w-[480px] flex-col overflow-hidden bg-paper sm:h-[min(844px,calc(100dvh-3rem))] sm:w-[390px] sm:rounded-[2.75rem] sm:border-[10px] sm:border-ink">
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="grid size-9 place-items-center rounded-lg bg-ink text-[0.9333rem] font-bold text-paper">BD</span>
            <p className="font-bold">Banca Demo</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[0.8667rem] font-medium">
            <User aria-hidden className="size-3.5" />
            {data?.customer_alias ?? (bank.error ? "—" : "…")}
          </span>
        </header>

        <main ref={main} className="flex-1 overflow-y-auto">
          {mode === "mock" && (
            <p className="flex items-start gap-2 border-b border-line bg-canvas px-4 py-2 text-[0.8667rem] text-muted">
              <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              Mod demonstrativ: serverul nu răspunde, așa că datele sunt simulate pe acest dispozitiv.
            </p>
          )}
          {bank.error && data && (
            <p role="status" className="flex items-start gap-2 border-b border-danger-line bg-danger-soft px-4 py-2 text-[0.8667rem] text-danger">
              <WifiOff aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              <span>
                Fără legătură cu banca. Afișăm datele de la {lastOk ? shortWhen(new Date(lastOk).toISOString(), Date.now()) : "ultima citire"}; reîncercăm automat.
              </span>
            </p>
          )}

          {!data ? (
            bank.error ? (
              <BootError notFound={notFound} refName={ref} message={bank.error.message} onRetry={() => void bank.reload()} />
            ) : (
              <div className="flex flex-col gap-3 p-4">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-10 w-52" />
                <Skeleton className="h-4 w-44" />
                <Skeleton className="mt-4 h-16" />
                <Skeleton className="h-14" />
                <Skeleton className="h-14" />
              </div>
            )
          ) : (
            <>
              <Balance state={data} />
              {tracked.length > 0 && (
                <section aria-label="Contestațiile tale" className="flex flex-col gap-3 px-4 pb-2">
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
                now={now}
                onOpen={(tx) => setSheet({ tx, mode: "details" })}
                onDispute={(tx) => setSheet({ tx, mode: "confirm" })}
              />
              <footer className="border-t border-line px-4 py-4 text-[0.8667rem] text-muted">
                <p>Banca Demo e o bancă fictivă. Toate datele sunt sintetice.</p>
                <p className="mt-1">
                  Client demo:{" "}
                  {["CUST-DEMO-01", "CUST-DEMO-02"].map((c, i) => (
                    <span key={c}>
                      {i > 0 && " · "}
                      {c === ref ? <span className="font-semibold text-ink">{i + 1}</span> : <Link className="underline" to={`/banca?client=${c}`}>{i + 1}</Link>}
                    </span>
                  ))}
                </p>
              </footer>
            </>
          )}
        </main>

        {sheet && (
          <TxSheet
            key={`${sheet.tx.id}-${sheet.mode}`}
            refName={ref}
            tx={sheet.tx}
            mode={sheet.mode}
            disputed={isDisputed(sheet.tx, tracked)}
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

// ------------------------------------------------------------------ stări de pornire

function BootError({ notFound, refName, message, onRetry }: { notFound: boolean; refName: string; message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 p-5">
      <CircleAlert aria-hidden className="size-6 text-danger" />
      {notFound ? (
        <>
          <p className="text-[1.0667rem] font-semibold">Clientul {refName} nu există în Banca Demo.</p>
          <p className="text-muted">Deschide unul dintre clienții de demonstrație:</p>
          <div className="flex gap-2">
            <Link to="/banca?client=CUST-DEMO-01" className="inline-flex h-10 items-center rounded-md border border-line-strong px-4 font-semibold hover:bg-hover">Clientul 1</Link>
            <Link to="/banca?client=CUST-DEMO-02" className="inline-flex h-10 items-center rounded-md border border-line-strong px-4 font-semibold hover:bg-hover">Clientul 2</Link>
          </div>
        </>
      ) : (
        <>
          <p className="text-[1.0667rem] font-semibold">Nu ne putem conecta la Banca Demo.</p>
          <p className="text-muted">Motiv: {message || "serverul nu a răspuns."} Verifică Wi-Fi-ul și încearcă din nou.</p>
          <Button variant="primary" onClick={onRetry}>Încearcă din nou</Button>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ sold

function Balance({ state }: { state: BankState }) {
  const prev = useRef(state.balance);
  const [flash, setFlash] = useState(0);
  useEffect(() => {
    if (typeof state.balance === "number" && state.balance > prev.current) setFlash((n) => n + 1);
    prev.current = state.balance;
  }, [state.balance]);
  const ok = typeof state.balance === "number" && Number.isFinite(state.balance);
  return (
    <section aria-label="Contul curent" className="px-4 pt-5 pb-4">
      <p className="text-[0.9333rem] text-muted">Sold disponibil</p>
      <p key={flash} className={cx("mt-1 inline-block rounded-md text-[2.2rem] leading-tight font-bold tabular-nums", flash > 0 && "animate-flash")}>
        {ok ? amount2(state.balance) : "—"}
        <span className="ml-1.5 text-[1.2rem] font-semibold">lei</span>
      </p>
      <p className="mt-1 text-[0.9333rem] text-muted tabular-nums">{state.iban_masked || "IBAN indisponibil"}</p>
    </section>
  );
}

// ------------------------------------------------------------------ contestația

function stepIcon(s: Step): ReactNode {
  if (s.state === "ok") {
    return (
      <span className="grid size-5 place-items-center rounded-full bg-ok text-paper">
        <CircleCheck aria-hidden className="size-4" strokeWidth={2.5} />
      </span>
    );
  }
  if (s.state === "info") {
    return (
      <span className="grid size-5 place-items-center rounded-full border border-line-strong bg-paper">
        <Info aria-hidden className="size-3.5" />
      </span>
    );
  }
  return (
    <span className="grid size-5 place-items-center">
      <StepIcon status={s.state === "done" ? "done" : s.state === "now" ? "running" : "idle"} />
    </span>
  );
}

function DisputeCard({ d, tx, refund, now, onHide }: {
  d: TrackedDispute; tx?: BankTransaction; refund?: BankTransaction; now: number; onHide: () => void;
}) {
  const api = useApi();
  const cache = useRef<CaseDetail | null>(null);
  const res = useResource<CaseDetail>(async () => {
    // o dată ajunsă într-o stare finală, nu mai întrebăm serverul
    if (cache.current && FINAL.has(String(cache.current.summary?.status))) return cache.current;
    const v = await api.caseDetail(d.case_id);
    cache.current = v;
    return v;
  }, [api, d.case_id], { pollMs: 2000 });

  const summary = res.data?.summary;
  const status = String(summary?.status ?? "");
  const steps = stepsFor(res.data ? status : "NOU", summary?.verdict);
  const gone = res.error instanceof ApiError && res.error.status === 404 && !res.data;
  const deadline = plainWhen(summary?.deadline ?? res.data?.clock?.t1_deadline, now);
  const answerBy = plainWhen(res.data?.clock?.answer_deadline, now);
  const amount = tx ? `${amount2(tx.amount)} lei` : summary?.amount ? `${amount2(summary.amount.value)} lei` : null;

  let foot: ReactNode = null;
  if (status === "RAMBURSAT") {
    foot = (
      <p className="font-medium text-ok">
        Ți-am returnat {amount ?? "banii"}{refund ? ` la ${shortWhen(refund.ts, now)}` : ""}. Banii sunt deja în sold.
      </p>
    );
  } else if (status === "TRASEU_APP") {
    foot = <p>Cerem băncii beneficiarului banii înapoi. {answerBy ? `Îți răspundem în scris cel târziu ${answerBy}.` : "Îți răspundem în scris."}</p>;
  } else if (FINAL.has(status)) {
    foot = <p>Îți trimitem explicația în scris{answerBy ? `, cel târziu ${answerBy}` : ""}.</p>;
  } else if (deadline) {
    foot = <p>Dacă nu ai autorizat plata, banii îți revin cel târziu {deadline}.</p>;
  }

  return (
    <article className={cx("rounded-xl border bg-paper p-4", status === "RAMBURSAT" ? "border-ok-line" : "border-line-strong")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold">Contestația ta</h2>
          <p className="mt-0.5 truncate text-[0.8667rem] text-muted">
            {tx?.description ?? "Plata contestată"}
            {amount ? ` · ${amount}` : ""}
          </p>
        </div>
        <IdTag>{d.case_id}</IdTag>
      </div>

      {gone ? (
        <div className="mt-3 text-[0.9333rem]">
          <p>Nu mai găsim contestația pe server; poate a fost repornit. Plata rămâne contestată în evidențele băncii.</p>
          <button type="button" onClick={onHide} className="mt-2 font-semibold underline">Ascunde</button>
        </div>
      ) : (
        <>
          <ol className="mt-3 flex flex-col gap-2.5" aria-live="polite">
            {steps.map((s, i) => (
              <li key={`${s.label}-${i}`} className="flex items-start gap-2.5">
                <span className="mt-0.5 shrink-0">{stepIcon(s)}</span>
                <span className={cx(s.state === "todo" ? "text-muted" : "font-medium", s.state === "now" && "font-semibold", s.state === "ok" && "font-semibold text-ok")}>
                  {s.label}
                </span>
              </li>
            ))}
          </ol>
          {foot && <div className="mt-3 border-t border-line pt-3 text-[0.9333rem]">{foot}</div>}
          {res.error && !gone && (
            <p className="mt-2 flex items-center gap-1.5 text-[0.8667rem] text-danger">
              <WifiOff aria-hidden className="size-3.5" />
              Nu putem verifica acum starea; reîncercăm automat.
            </p>
          )}
          {!res.data && !res.error && (
            <p className="mt-2 flex items-center gap-1.5 text-[0.8667rem] text-muted">
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
              Citim starea contestației…
            </p>
          )}
        </>
      )}
    </article>
  );
}

// ------------------------------------------------------------------ notificări

function noteKind(n: BankNotification): "refund" | "money" | "security" | "info" {
  const k = String(n.kind ?? "").toLowerCase();
  if (k === "refund" || k === "rambursare" || /returnat|rambursa/i.test(n.text ?? "")) return "refund";
  if (k === "debit" || k === "tranzactie" || k === "credit") return "money";
  if (k === "securitate" || k === "security") return "security";
  return "info";
}

function Notifications({ notes, now }: { notes: BankNotification[]; now: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? notes : notes.slice(0, 3);
  return (
    <section aria-labelledby="bank-notes" className="px-4 py-3">
      <h2 id="bank-notes" className="text-[0.9333rem] font-semibold text-muted">Notificări</h2>
      {notes.length === 0 ? (
        <p className="mt-2 text-[0.9333rem] text-muted">Nicio notificare nouă.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {shown.map((n, i) => {
            const k = noteKind(n);
            return (
              <li
                key={`${n.ts}-${i}`}
                className={cx("flex items-start gap-2.5 rounded-lg border px-3 py-2.5", k === "refund" ? "border-ok-line bg-ok-soft" : "border-line bg-paper")}
              >
                <span className="mt-0.5 shrink-0">
                  {k === "refund" ? (
                    <CircleCheck aria-hidden className="size-4 text-ok" />
                  ) : k === "security" ? (
                    <ShieldAlert aria-hidden className="size-4 text-muted" />
                  ) : k === "money" ? (
                    <ArrowUpRight aria-hidden className="size-4 text-muted" />
                  ) : (
                    <Info aria-hidden className="size-4 text-muted" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={cx("block text-[0.9333rem]", k === "refund" && "font-semibold")}>{n.text}</span>
                  <span className="block text-[0.8667rem] text-muted">{shortWhen(n.ts, now)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {notes.length > 3 && (
        <button type="button" className="mt-2 text-[0.9333rem] font-semibold underline" onClick={() => setAll((v) => !v)}>
          {all ? "Arată mai puține" : `Arată toate (${notes.length})`}
        </button>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ tranzacții

function Transactions({ txs, tracked, now, onOpen, onDispute }: {
  txs: BankTransaction[];
  tracked: TrackedDispute[];
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

  return (
    <section aria-labelledby="bank-tx" className="pt-3 pb-2">
      <h2 id="bank-tx" className="px-4 text-[0.9333rem] font-semibold text-muted">Tranzacții</h2>
      {sorted.length === 0 ? (
        <p className="px-4 py-3 text-[0.9333rem] text-muted">Nicio tranzacție încă.</p>
      ) : (
        groups.map((g) => (
          <div key={g.day} className="mt-2">
            <p className="bg-canvas px-4 py-1.5 text-[0.8667rem] font-semibold text-muted">{g.day}</p>
            <ul>
              {g.items.map((t) => {
                const out = isOut(t);
                const refund = isRefundTx(t);
                const disputed = isDisputed(t, tracked);
                const refunded = /rambursat/i.test(t.status ?? "");
                const inline = canDispute(t, tracked) && isRecent(t, now);
                return (
                  <li key={t.id} className="border-b border-line last:border-b-0">
                    <button type="button" onClick={() => onOpen(t)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-hover">
                      <span
                        aria-hidden
                        className={cx("grid size-9 shrink-0 place-items-center rounded-full", refund ? "bg-ok-soft text-ok" : "bg-canvas text-ink-soft")}
                      >
                        {refund ? <CircleCheck className="size-4" /> : out ? <ArrowUpRight className="size-4" /> : <ArrowDownLeft className="size-4" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{t.description || "Tranzacție"}</span>
                        <span className="block text-[0.8667rem] text-muted">
                          {clock(t.ts, false)}
                          {refunded ? " · Rambursată" : disputed ? " · Contestată" : ""}
                        </span>
                      </span>
                      <span className={cx("shrink-0 font-semibold whitespace-nowrap tabular-nums", refund && "text-ok")}>{signedLei(t)}</span>
                    </button>
                    {inline && (
                      <div className="-mt-1 px-4 pb-3 pl-16">
                        <Button size="sm" onClick={() => onDispute(t)}>Nu am făcut eu plata</Button>
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

// ------------------------------------------------------------------ foaia de jos: detalii și contestare

function TxSheet({ refName, tx, mode, disputed, disputable, onMode, onClose, onDisputed }: {
  refName: string;
  tx: BankTransaction;
  mode: "details" | "confirm";
  disputed: boolean;
  disputable: boolean;
  onMode: (m: "details" | "confirm") => void;
  onClose: () => void;
  onDisputed: (d: TrackedDispute) => void;
}) {
  const api = useApi();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // focusul merge pe foaie, nu pe câmpul de text: pe telefon tastatura ar acoperi butonul de trimitere
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.bankDispute(refName, { transaction_id: tx.id, text: normalizeRo(text.trim()) });
      if (!out?.case_id) throw new Error("Serverul nu a întors numărul contestației.");
      onDisputed({ case_id: out.case_id, transaction_id: tx.id, at: Date.now() });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const when = new Date(tx.ts);
  const whenText = Number.isNaN(when.getTime())
    ? "—"
    : new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }).format(when);

  return (
    <div className="absolute inset-0 z-30 flex flex-col justify-end" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
      <button type="button" aria-label="Închide" className="absolute inset-0 bg-ink/40" onClick={() => !busy && onClose()} />
      <div ref={panel} tabIndex={-1} className="relative max-h-[88%] overflow-y-auto rounded-t-2xl bg-paper px-4 pt-3 pb-6 outline-none animate-enter">
        <span aria-hidden className="mx-auto mb-3 block h-1 w-10 rounded-full bg-line-strong" />
        <div className="flex items-start justify-between gap-3">
          <h2 id="sheet-title" className="text-[1.2rem] font-bold">{mode === "confirm" ? "Contestă plata" : "Detaliile plății"}</h2>
          <button type="button" aria-label="Închide" onClick={onClose} disabled={busy} className="grid size-8 place-items-center rounded-md hover:bg-hover">
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <div className="mt-3 rounded-lg border border-line bg-canvas px-3 py-2.5">
          <p className="font-medium">{tx.description || "Tranzacție"}</p>
          <p className="mt-0.5 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[0.8667rem] text-muted">{whenText}</span>
            <span className="text-[1.0667rem] font-bold tabular-nums">{signedLei(tx)}</span>
          </p>
        </div>

        {mode === "details" ? (
          <div className="mt-4 flex flex-col gap-3">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[0.9333rem]">
              <dt className="text-muted">Tip</dt>
              <dd>{isOut(tx) ? "Plată din cont" : "Bani primiți"}</dd>
              <dt className="text-muted">Stare</dt>
              <dd>{disputed ? "Contestată" : /rambursat/i.test(tx.status) ? "Rambursată" : "Efectuată"}</dd>
              <dt className="text-muted">Referință</dt>
              <dd className="font-mono text-[0.8667rem] break-all">{tx.id}</dd>
            </dl>
            {disputable ? (
              <Button className="w-full" onClick={() => onMode("confirm")}>Nu am făcut eu plata</Button>
            ) : disputed ? (
              <p className="text-[0.9333rem] text-muted">Plata e deja contestată. Starea apare sus, la „Contestația ta”.</p>
            ) : null}
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="font-medium">Ce s-a întâmplat? <span className="font-normal text-muted">(opțional)</span></span>
              <textarea
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={1000}
                placeholder="De exemplu: am primit un SMS de la un curier și am introdus datele cardului."
                className="rounded-md border border-line-strong bg-paper px-3 py-2"
              />
            </label>
            <p className="text-[0.9333rem] text-ink-soft">
              Dacă nu ai autorizat plata, legea ne obligă să îți returnăm banii până la sfârșitul zilei lucrătoare următoare.
            </p>
            {error && (
              <p role="alert" className="flex items-start gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-[0.9333rem] text-danger">
                <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                <span>Contestația nu a plecat. Motiv: {error} Încearcă din nou.</span>
              </p>
            )}
            <Button variant="primary" className="w-full" busy={busy} onClick={submit}>Trimite contestația</Button>
            <Button variant="ghost" className="w-full" disabled={busy} onClick={onClose}>Renunță</Button>
          </div>
        )}
      </div>
    </div>
  );
}
