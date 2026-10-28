/**
 * Pagina unui caz: o singură coloană.
 * Sus: suma, clientul, termenul și starea. Apoi decizia (o propoziție, cine a decis, semnătura, trei motive),
 * cronologia „Ce s-a întâmplat” și secțiunile care se deschid la cerere. Graful agenților stă într-un sertar.
 */
import { ArrowRight, Check, ChevronDown, CircleAlert, Hand, Loader2, Play, ShieldAlert, ShieldCheck, Workflow, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router";
import { clock, duration, money, questionLabel, shortHash, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { CaseDetail, CounterfactualResult, Fact, StoryItem } from "../../api/types";
import {
  Breadcrumb, Button, Collapsible, cx, DeadlineText, Drawer, ErrorNote, IdTag, Segmented, SectionBoundary, Skeleton, type Tone,
} from "../../ui/kit";
import { Bar, ModelBadge } from "../../ui/viz";
import { Arguments, Cites, ComplaintBlock, LedgerSection, LetterSection, RecoverySection, RulesList } from "./caseParts";
import { caseStatus, plainReasons, scenarioLabel, StatusPill, StepList, useStepRows, verdictSentence } from "./caseUi";
import { get } from "./evalReport";

const AgentGraph = lazy(() => import("../../graph/AgentGraph"));

const RELOAD_ON = new Set(["decision", "interrupt", "refund", "ledger_seal", "hold_signal", "wall_block", "diode", "clock", "rule_hit"]);
const CLOSED = new Set(["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"]);

type SectionId = "probe" | "scrisoare" | "recuperare" | "analiza" | "contrafactual" | "registru";

// ================================================================== datele vii ale cazului

export function useCaseLive(id: string) {
  const api = useApi();
  const detail = useResource(id ? () => api.caseDetail(id) : null, [api, id], { pollMs: 2500 });
  const source = useMemo(() => (id ? api.caseEvents(id) : null), [api, id]);
  const reloadRef = useRef(detail.reload);
  reloadRef.current = detail.reload;
  const timer = useRef<number | null>(null);
  const stream = useEventStream(source, id || null, (e, replay) => {
    if (replay) return;
    const hit = e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || e.type === "STEP_FINISHED" || (e.type === "CUSTOM" && RELOAD_ON.has(String(e.name)));
    if (!hit || timer.current !== null) return;
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void reloadRef.current();
    }, 300);
  });
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);
  return { detail, events: stream.events, streamStatus: stream.status };
}

// ================================================================== pagina

export default function CaseRoomPage() {
  const { id = "" } = useParams();
  return <CaseRoom caseId={id} />;
}

export function CaseRoom({ caseId, compact = false }: { caseId: string; compact?: boolean }) {
  const { detail, events } = useCaseLive(caseId);
  const [drawer, setDrawer] = useState(false);
  const [flash, setFlash] = useState<{ id: string; n: number } | null>(null);
  const [open, setOpen] = useState<Partial<Record<SectionId, boolean>>>({});
  const d = detail.data;
  const status = d ? String(d.summary.status) : "";
  const running = status === "IN_ANALIZA" || status === "NOU";
  const steps = useStepRows(d?.pipeline?.nodes, events);
  const settled = CLOSED.has(status) && !d?.interrupt?.pending;

  // cât timp agenții lucrează, probele se văd cum sosesc
  const wasRunning = useRef(false);
  const autoOpened = useRef(false);
  useEffect(() => {
    if (running && !wasRunning.current && open.probe === undefined) {
      autoOpened.current = true;
      setOpen((o) => ({ ...o, probe: true }));
    }
    if (!running && wasRunning.current && autoOpened.current) {
      autoOpened.current = false;
      setOpen((o) => ({ ...o, probe: false }));
    }
    wasRunning.current = running;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const cite = useCallback((factId: string) => {
    autoOpened.current = false;
    setOpen((o) => ({ ...o, probe: true }));
    setFlash((f) => ({ id: factId, n: (f?.n ?? 0) + 1 }));
    window.setTimeout(() => document.getElementById(`fact-${factId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  }, []);

  if (detail.error && !d) {
    return (
      <div className="flex flex-col gap-4">
        {!compact && <Breadcrumb items={[{ label: "Contestații", to: "/" }, { label: caseId }]} />}
        <ErrorNote error={detail.error} what={`cazul ${caseId}`} onRetry={detail.reload} />
      </div>
    );
  }
  if (!d) return <RoomSkeleton />;

  const toggle = (id: SectionId) => (v: boolean) => setOpen((o) => ({ ...o, [id]: v }));
  const facts = d.facts ?? [];

  return (
    <div className={cx("mx-auto flex w-full flex-col", compact ? "max-w-none" : "max-w-[960px]")}>
      {!compact && <Breadcrumb items={[{ label: "Contestații", to: "/" }, { label: caseId }]} />}
      <CaseHeader d={d} steps={steps} running={running} onGraph={() => setDrawer(true)} />

      <SectionBoundary label="Decizia">
        <DecisionBox d={d} caseId={caseId} onCite={cite} onDone={detail.reload} />
      </SectionBoundary>

      <SectionBoundary label="Ce s-a întâmplat">
        <Story d={d} onCite={cite} />
      </SectionBoundary>

      <div className="mt-8 border-y border-line">
        <Collapsible title="Probe" meta={`${facts.length} probe · ${facts.filter((f) => f.labels?.trust === "untrusted").length} din surse neverificate`} open={Boolean(open.probe)} onToggle={toggle("probe")} id="probe">
          <SectionBoundary label="Probe"><Evidence d={d} flash={flash} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Scrisoarea către client" tone={d.letter?.filter?.passed === false ? "danger" : undefined}
          meta={!d.letter ? "încă nu e gata" : d.letter.filter?.passed === false ? "oprită de zid" : "a trecut de zid"} open={Boolean(open.scrisoare)} onToggle={toggle("scrisoare")}>
          <SectionBoundary label="Scrisoarea"><LetterSection d={d} caseId={caseId} onCite={cite} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Recuperare" meta={recoveryMeta(d)} open={Boolean(open.recuperare)} onToggle={toggle("recuperare")}>
          <SectionBoundary label="Recuperare"><RecoverySection d={d} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Analiza Procuror ↔ Avocat" meta={d.debate?.ran ? verdictLabel(String(d.debate.recommendation ?? d.debate.rubric_recommendation ?? "")) : "nu a rulat"} open={Boolean(open.analiza)} onToggle={toggle("analiza")}>
          <SectionBoundary label="Analiza"><Debate d={d} onCite={cite} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Dacă schimb un fapt" meta="recalculează decizia" open={Boolean(open.contrafactual)} onToggle={toggle("contrafactual")}>
          <SectionBoundary label="Contrafactual">{d.rule_context ? <Counterfactual d={d} caseId={caseId} /> : <p className="text-[0.9333rem] text-muted">Disponibil după ce regulile decid.</p>}</SectionBoundary>
        </Collapsible>
        <Collapsible title="Registru" meta={d.ledger?.sealed ? `sigilat · ${shortHash(d.ledger.root, 10)}` : "nesigilat încă"} open={Boolean(open.registru)} onToggle={toggle("registru")}>
          <SectionBoundary label="Registru"><LedgerSection caseId={caseId} sealed={Boolean(d.ledger?.sealed)} count={d.ledger?.count ?? facts.length} root={d.ledger?.root} /></SectionBoundary>
        </Collapsible>
      </div>

      {detail.error && <p className="mt-3 text-[0.8667rem] text-danger">Nu mai primesc actualizări de la server. Afișez ultima stare primită.</p>}

      {drawer && (
        <Drawer title="Cum a decis VersoML" onClose={() => setDrawer(false)} width={800}>
          <div className="flex flex-col gap-6 p-5">
            <SectionBoundary label="Graful agenților">
              <Suspense fallback={<Skeleton className="h-[440px] rounded-lg" />}>
                <AgentGraph nodes={d.pipeline?.nodes ?? []} edges={d.pipeline?.edges ?? []} events={events} settled={settled} height={440} title="Agenții, live" />
              </Suspense>
            </SectionBoundary>
            <div>
              <p className="mb-1 text-[0.8667rem] font-semibold text-muted">Pașii, în ordine</p>
              <StepList rows={steps} settled={settled} />
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}

function recoveryMeta(d: CaseDetail): string {
  const e = d.decisions?.find((x) => x.question === "recuperare_escroc");
  if (e) return verdictLabel(e.decision);
  if (d.recovery?.chargeback?.eligible) return "chargeback posibil";
  return "—";
}

function RoomSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[960px] flex-col gap-4" role="status" aria-label="Se încarcă cazul">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-48 rounded-lg" />
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

// ================================================================== antet

function CaseHeader({ d, steps, running, onGraph }: { d: CaseDetail; steps: Array<{ status: string }>; running: boolean; onGraph: () => void }) {
  const s = d.summary;
  const status = String(s.status);
  const closed = caseStatus(status, s.requires_human).group === "closed" && !d.interrupt?.pending;
  const done = steps.filter((x) => x.status === "done" || x.status === "skipped").length;
  const live = running || steps.some((x) => x.status === "running");
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[1.75rem] leading-tight font-semibold tabular-nums">{money(s.amount)}</h1>
          <StatusPill status={status} requiresHuman={s.requires_human} />
        </div>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9333rem] text-ink-soft">
          <span className="font-medium text-ink">{s.customer_alias}</span>
          <span aria-hidden className="text-subtle">·</span>
          <span>{scenarioLabel(s.scenario)}</span>
          <span aria-hidden className="text-subtle">·</span>
          {closed ? <span className="text-muted">rezolvat în termen</span> : <span className="inline-flex items-center gap-1">Termen: <DeadlineText deadline={d.clock?.t1_deadline ?? s.deadline} withDue /></span>}
        </p>
      </div>
      {live && steps.length > 0 ? (
        <button type="button" onClick={onGraph} className="inline-flex h-8 items-center gap-2.5 rounded-md border border-line-strong bg-paper px-3 text-[0.8667rem] font-medium hover:bg-hover">
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          Agenții lucrează · {done}/{steps.length} pași
          <span className="h-1 w-16 overflow-hidden rounded-full bg-hover" aria-hidden><span className="block h-1 rounded-full bg-ink transition-[width] duration-300" style={{ width: `${(done / Math.max(1, steps.length)) * 100}%` }} /></span>
        </button>
      ) : (
        <Button size="sm" icon={<Workflow aria-hidden className="size-4" />} onClick={onGraph}>Cum a decis VersoML</Button>
      )}
    </header>
  );
}

// ================================================================== decizia

const SIGN_COPY: Record<string, { yes: string; no: string; consequence: string }> = {
  RAMBURSEAZA_CU_APROBARE: { yes: "Aprobă rambursarea", no: "Respinge", consequence: "Când aprobi, regulile trimit instrucțiunea de rambursare." },
  RESPINGE_TARDIV: { yes: "Confirm respingerea", no: "Nu confirm, rambursăm", consequence: "Clientul primește scrisoarea de respingere, cu temeiul legal și căile de atac." },
  EXCEPTIE_FRAUDA_CLIENT: { yes: "Confirm excepția", no: "Nu confirm, rambursăm", consequence: "Confirmă doar dacă autoritatea a fost anunțată." },
};

function DecisionBox({ d, caseId, onCite, onDone }: { d: CaseDetail; caseId: string; onCite: (id: string) => void; onDone: () => Promise<void> }) {
  const api = useApi();
  const [more, setMore] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const status = String(d.summary.status);
  const decisions = d.decisions ?? [];
  const t1 = decisions.find((x) => x.question === "rambursare_t1");
  const pending = Boolean(d.interrupt?.pending);
  const v = verdictSentence(t1, d.summary.amount, {
    status,
    pending,
    action: pending ? undefined : d.interrupt?.answer?.action,
    approver: d.interrupt?.answer?.approver,
  });
  const reasons = useMemo(() => plainReasons(d), [d]);
  const ruleIds = t1?.rule_ids ?? [];
  const others = decisions.filter((x) => x.question !== "rambursare_t1");

  async function start() {
    setStarting(true);
    setStartError(null);
    try {
      await api.runCase(caseId);
      await onDone();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Cazul nu a pornit.");
    } finally {
      setStarting(false);
    }
  }

  if (status === "NOU" || status === "EROARE") {
    return (
      <section aria-label="Decizia" className="rounded-lg border border-line p-6">
        <p className="text-[1.25rem] font-semibold">{status === "NOU" ? "Cazul nu a pornit încă." : "Agenții s-au oprit cu o eroare."}</p>
        <p className="mt-1 text-[0.9333rem] text-muted">{status === "NOU" ? "Pornește agenții: strâng probele, apoi regulile decid." : "Probele strânse rămân în registru."}</p>
        <Button className="mt-4" variant="primary" icon={<Play className="size-4" />} busy={starting} onClick={start}>{status === "NOU" ? "Pornește agenții" : "Pornește din nou"}</Button>
        {startError && <p className="mt-2 text-[0.9333rem] text-danger">{startError}</p>}
      </section>
    );
  }

  const icon: Record<Tone, ReactNode> = {
    ok: <span className="grid size-5 place-items-center rounded-full bg-ok text-paper"><Check className="size-3" strokeWidth={3} /></span>,
    now: <span className="grid size-5 place-items-center rounded-full bg-yellow ring-1 ring-yellow-line"><Hand className="size-3" strokeWidth={2.5} /></span>,
    danger: <span className="grid size-5 place-items-center rounded-full bg-danger text-paper"><X className="size-3" strokeWidth={3} /></span>,
    neutral: t1 ? <span className="grid size-5 place-items-center rounded-full bg-ink text-paper"><Check className="size-3" strokeWidth={3} /></span> : <Loader2 className="size-4 animate-spin text-muted" />,
    dark: null,
  };

  return (
    <section aria-label="Decizia" className={cx("rounded-lg border bg-paper", pending ? "border-yellow-line ring-4 ring-yellow-soft/70" : "border-line")}>
      <div className="p-6">
        <p className="flex items-center gap-2 text-[0.8667rem] font-medium text-ink-soft">
          {icon[v.tone]}
          {v.who}
          {d.decision_seconds ? <span className="ml-auto font-normal text-muted">decis în {duration(d.decision_seconds)}</span> : null}
        </p>
        <h2 className="mt-3 text-[1.35rem] leading-snug font-semibold">{v.title}</h2>

        {pending && d.interrupt && <Signature d={d} caseId={caseId} onDone={onDone} />}

        {reasons.length > 0 && (
          <ul className="mt-5 flex flex-col gap-2">
            {reasons.map((r, i) => (
              <li key={i} className="flex gap-2.5 text-[0.9333rem]">
                <Check aria-hidden className="mt-1 size-3.5 shrink-0 text-muted" strokeWidth={2.5} />
                <span className="min-w-0">
                  {r.text}
                  {r.rule && <span className="ml-2 font-mono text-[0.75rem] text-muted">{r.rule}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {!t1 && <div className="mt-5 flex flex-col gap-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>}
      </div>

      {t1 && (
        <div className="border-t border-line">
          <button type="button" onClick={() => setMore((m) => !m)} aria-expanded={more}
            className="flex w-full items-center gap-2 px-6 py-3 text-left text-[0.8667rem] font-medium text-ink-soft hover:text-ink">
            <ChevronDown aria-hidden className={cx("size-4 transition-transform", !more && "-rotate-90")} />
            Vezi regulile
            {ruleIds.length > 0 && <span className="min-w-0 truncate font-mono text-[0.75rem] font-normal text-muted">({ruleIds.slice(0, 3).join(", ")}{ruleIds.length > 3 ? `, +${ruleIds.length - 3}` : ""})</span>}
          </button>
          {more && (
            <div className="animate-enter flex flex-col gap-6 px-6 pb-6">
              {t1.rationale?.length ? (
                <div>
                  <p className="mb-2 text-[0.8667rem] font-semibold text-muted">De ce, pe larg</p>
                  <ol className="flex flex-col gap-2.5">
                    {t1.rationale.map((line, i) => (
                      <li key={i} className="grid grid-cols-[1.25rem_minmax(0,1fr)] text-[0.9333rem] text-ink-soft">
                        <span className="tabular-nums text-muted">{i + 1}.</span>
                        <span>{line.text}<Cites ids={line.cites} onCite={onCite} /></span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
              <div>
                <p className="mb-2 text-[0.8667rem] font-semibold text-muted">Regulile aplicate</p>
                <RulesList d={d} />
              </div>
              {others.length > 0 && (
                <div>
                  <p className="mb-2 text-[0.8667rem] font-semibold text-muted">Celelalte decizii</p>
                  <ul className="divide-y divide-line rounded-md border border-line">
                    {others.map((o) => (
                      <li key={o.question} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-[0.9333rem]">
                        <span className="text-ink-soft">{questionLabel(o.question)}</span>
                        <span className="flex items-center gap-2 font-medium">
                          {verdictLabel(o.decision)}
                          {o.requires_human && <span className="rounded-full bg-yellow-soft px-2 text-[0.75rem] font-medium">semnează un om</span>}
                          <span className="font-mono text-[0.75rem] font-normal text-muted">{o.rule_ids?.slice(0, 2).join(", ")}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Signature({ d, caseId, onDone }: { d: CaseDetail; caseId: string; onDone: () => Promise<void> }) {
  const api = useApi();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const it = d.interrupt!;
  const copy = SIGN_COPY[String(it.verdict)] ?? { yes: "Aprobă", no: "Respinge", consequence: it.prompt ?? "Decizia se aplică imediat." };
  const resuming = Boolean(it.resuming);
  const locked = resuming || busy !== null;
  async function act(action: "approve" | "reject") {
    setBusy(action);
    setError(null);
    try {
      await api.approve(caseId, { action, approver: "OPERATOR-01" });
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Semnătura nu a fost înregistrată.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="mt-4">
      <p className="text-[0.9333rem] text-ink-soft">{resuming ? "Am primit semnătura. Aplic decizia…" : copy.consequence}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" busy={busy === "approve" || (resuming && busy === null)} disabled={locked} onClick={() => act("approve")}>{copy.yes}</Button>
        <Button busy={busy === "reject"} disabled={locked} onClick={() => act("reject")}>{copy.no}</Button>
      </div>
      {error && <p role="alert" className="mt-2 text-[0.9333rem] font-medium text-danger">{error}</p>}
    </div>
  );
}

// ================================================================== ce s-a întâmplat

interface StoryRow extends StoryItem {
  t: number | null;
}

const ATTACK_KINDS = new Set(["sms", "click", "device", "auth", "payment"]);

function buildStory(d: CaseDetail): StoryRow[] {
  const facts = new Map((d.facts ?? []).map((f) => [f.fact_id, f]));
  const rows: StoryRow[] = (d.story ?? []).map((s) => {
    const t = new Date(s.ts).getTime();
    let title = s.title;
    if (s.kind === "payment") {
      const amount = Number(get(facts.get(s.fact_id ?? "")?.content, "amount"));
      title = Number.isFinite(amount) && amount > 0 ? `Plată de ${money(amount)}` : title.replace(/\.(?=[a-zăâîșț])/gi, " ");
    }
    return { ...s, title, t: Number.isFinite(t) ? t : null };
  });
  rows.sort((a, b) => (a.t ?? 0) - (b.t ?? 0));
  const sms = d.complaint?.attachments?.find((a) => a.kind === "sms");
  if (sms) rows.unshift({ ts: "", kind: "sms", title: "SMS de la „curier”", detail: sms.content, fact_id: null, t: null });
  return rows;
}

function gap(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `+${s} s`;
  if (s < 3600) return `+${Math.round(s / 60)} min`;
  if (s < 86400) return `+${Math.round(s / 3600)} h`;
  return `+${Math.round(s / 86400)} zile`;
}

function Story({ d, onCite }: { d: CaseDetail; onCite: (id: string) => void }) {
  const rows = useMemo(() => buildStory(d), [d]);
  return (
    <section aria-labelledby="story-title" className="mt-8">
      <h2 id="story-title" className="mb-3 font-semibold">Ce s-a întâmplat</h2>
      {rows.length === 0 ? (
        <p className="text-[0.9333rem] text-muted">Cronologia apare pe măsură ce agenții găsesc probe.</p>
      ) : (
        <ol className="relative">
          {rows.map((r, i) => {
            const prev = rows.slice(0, i).reverse().find((x) => x.t !== null)?.t;
            const attack = ATTACK_KINDS.has(r.kind);
            const good = r.kind === "refund";
            return (
              <li key={`${r.kind}-${i}`} className="group relative grid grid-cols-[4.25rem_1rem_minmax(0,1fr)_auto] gap-x-3 pb-3 last:pb-0">
                <span className="pt-px text-right font-mono text-[0.8rem] tabular-nums text-muted">{r.t !== null ? clock(r.t, false) : "înainte"}</span>
                <span className="relative flex justify-center">
                  {i < rows.length - 1 && <span aria-hidden className="absolute top-3.5 -bottom-3 w-px bg-line" />}
                  <span aria-hidden className={cx("relative mt-1.5 size-2.5 rounded-full border-2", attack ? "border-danger bg-paper" : good ? "border-ok bg-ok" : "border-ink-soft bg-paper")} />
                </span>
                <div className="min-w-0">
                  <p className={cx("text-[0.9333rem]", good ? "font-semibold text-ok" : "font-medium")}>{r.title}</p>
                  {r.detail && <p className={cx("mt-0.5 text-[0.8667rem] text-muted", r.kind === "sms" ? "italic" : "break-words")}>{r.detail}</p>}
                </div>
                <span className="flex items-start gap-2 pt-px text-[0.8rem] text-muted">
                  {r.t !== null && prev ? <span className="tabular-nums">{gap(r.t - prev)}</span> : null}
                  {r.fact_id && (
                    <button type="button" onClick={() => onCite(r.fact_id!)} title="Arată proba"
                      className="font-mono text-[0.75rem] text-subtle opacity-60 group-hover:opacity-100 hover:text-ink hover:underline focus-visible:opacity-100">
                      {r.fact_id}
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

// ================================================================== probe

const CONF_LABEL: Record<string, string> = { client: "zona client", aml: "zona AML", "aml-only": "doar AML", public: "public" };

function factOf(facts: Fact[], kind: string): Fact | undefined {
  return facts.find((f) => f.kind === kind);
}

function DomainLine({ facts }: { facts: Fact[] }) {
  const rdap = factOf(facts, "domain.rdap");
  const look = factOf(facts, "domain.lookalike");
  const page = factOf(facts, "domain.page");
  if (!rdap && !look) return null;
  const domain = String(get(rdap?.content, "data", "domain") ?? get(look?.content, "data", "domain") ?? get(rdap?.content, "args", "domain") ?? "");
  const age = Number(get(rdap?.content, "data", "age_hours"));
  const scores = get(look?.content, "data", "brand_scores");
  const lookScore = scores && typeof scores === "object" ? Math.max(...Object.values(scores as Record<string, number>).filter((x) => typeof x === "number")) : Number(get(look?.content, "data", "score"));
  const asks = (get(page?.content, "data", "asks") as string[] | undefined) ?? [];
  const ASK: Record<string, string> = { card_number: "cardul", cvv: "CVV", expiry: "expirarea", otp: "codul SMS", password: "parola" };
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-danger-line bg-danger-soft px-4 py-2.5 text-[0.9333rem]">
      <span className="flex items-center gap-2 font-medium"><ShieldAlert aria-hidden className="size-4 text-danger" /> Pagina falsă: <span className="font-mono text-[0.8667rem]">{domain || "domeniu necunoscut"}</span></span>
      {Number.isFinite(age) && <span className="text-ink-soft">creată acum {age} h</span>}
      {Number.isFinite(lookScore) && <span className="text-ink-soft">seamănă cu banca: {lookScore.toFixed(2).replace(".", ",")}</span>}
      {asks.length > 0 && <span className="text-ink-soft">cere {asks.map((a) => ASK[a] ?? a).join(", ")}</span>}
    </div>
  );
}

function Evidence({ d, flash }: { d: CaseDetail; flash: { id: string; n: number } | null }) {
  const facts = d.facts ?? [];
  const [filter, setFilter] = useState<"all" | "trusted" | "untrusted">("all");
  const [complaint, setComplaint] = useState(false);
  const trusted = facts.filter((f) => f.labels?.trust !== "untrusted").length;
  const list = facts.filter((f) => filter === "all" || (filter === "untrusted" ? f.labels?.trust === "untrusted" : f.labels?.trust !== "untrusted"));
  return (
    <div>
      <DomainLine facts={facts} />
      {d.complaint && (
        <div className="mb-4">
          <button type="button" onClick={() => setComplaint((c) => !c)} aria-expanded={complaint} className="inline-flex items-center gap-1.5 text-[0.9333rem] font-medium text-ink-soft hover:text-ink">
            <ChevronDown aria-hidden className={cx("size-4 transition-transform", !complaint && "-rotate-90")} /> Reclamația clientului
          </button>
          {complaint && <div className="mt-3"><ComplaintBlock d={d} /></div>}
        </div>
      )}
      {!facts.length ? (
        <p className="text-[0.9333rem] text-muted">Nicio probă încă. Agenții le scriu aici, fiecare cu sursă, oră și hash.</p>
      ) : (
        <>
          <Segmented label="Filtrează probele" value={filter} onChange={setFilter} className="mb-3"
            options={[
              { id: "all", label: `Toate ${facts.length}` },
              { id: "trusted", label: `Sistemele băncii ${trusted}` },
              { id: "untrusted", label: `Neverificate ${facts.length - trusted}` },
            ]} />
          <ul className="divide-y divide-line rounded-md border border-line">
            {list.map((f) => {
              const lit = flash?.id === f.fact_id;
              const untrusted = f.labels?.trust === "untrusted";
              return (
                <li key={f.fact_id + (lit ? flash!.n : "")} id={`fact-${f.fact_id}`}
                  className={cx("grid scroll-mt-24 grid-cols-[4.5rem_minmax(0,1fr)_auto] items-start gap-x-3 px-3 py-2.5", lit && "animate-flash")}>
                  <span className="pt-0.5"><IdTag tone={lit ? "now" : "neutral"}>{f.fact_id}</IdTag></span>
                  <div className="min-w-0">
                    <p className="text-[0.9333rem]">{f.summary || f.kind}</p>
                    <p className="mt-0.5 truncate font-mono text-[0.75rem] text-muted" title={`${f.source_tool} · sha256 ${f.sha256}`}>{f.source_tool} · {shortHash(f.sha256, 8)}</p>
                  </div>
                  <span className="flex flex-col items-end gap-1 pt-0.5 text-[0.8rem]">
                    {untrusted
                      ? <span className="inline-flex items-center gap-1 text-danger"><CircleAlert className="size-3.5" /> neverificat</span>
                      : <span className="inline-flex items-center gap-1 text-ok"><ShieldCheck className="size-3.5" /> banca</span>}
                    {f.labels?.conf && f.labels.conf !== "client" && <span className="text-muted">{CONF_LABEL[f.labels.conf] ?? f.labels.conf}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

// ================================================================== Procuror ↔ Avocat

function Debate({ d, onCite }: { d: CaseDetail; onCite: (id: string) => void }) {
  const debate = d.debate;
  if (!debate?.ran) {
    return <p className="text-[0.9333rem] text-muted">Rulează după rambursare. Procurorul și Avocatul discută dacă banca poate cere banii de la client; o rubrică fixă cântărește, iar un om decide.</p>;
  }
  const rubric = debate.rubric ?? [];
  const maxW = Math.max(1, ...rubric.map((r) => Math.abs(r.weight)));
  const score = typeof debate.score === "number" ? debate.score : rubric.reduce((acc, r) => acc + (r.value ? r.weight : 0), 0);
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <p className="mb-2 flex items-center gap-2 font-semibold">Procurorul <ModelBadge model={debate.models?.procuror ?? "opus"} /></p>
          <p className="mb-2 text-[0.8667rem] text-muted">De ce ar putea plăti clientul</p>
          <Arguments lines={debate.prosecutor} onCite={onCite} />
        </div>
        <div>
          <p className="mb-2 flex items-center gap-2 font-semibold">Avocatul <ModelBadge model={debate.models?.avocat ?? "sonnet"} /></p>
          <p className="mb-2 text-[0.8667rem] text-muted">De ce nu ar trebui</p>
          <Arguments lines={debate.defender} onCite={onCite} />
        </div>
      </div>
      {rubric.length > 0 && (
        <div className="rounded-md border border-line p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-semibold">Rubrica fixă</p>
            <p className="text-[0.9333rem]">Scor <span className="font-semibold tabular-nums">{score > 0 ? "+" : ""}{score}</span> <ArrowRight aria-hidden className="inline size-3.5" /> {verdictLabel(String(debate.recommendation ?? debate.rubric_recommendation ?? ""))}</p>
          </div>
          <ul className="flex flex-col gap-2">
            {rubric.map((r) => (
              <li key={r.indicator} className="grid grid-cols-[1rem_minmax(0,1fr)_6rem_2.25rem] items-center gap-3 text-[0.9333rem]">
                {r.value ? <Check className="size-4" strokeWidth={2.5} /> : <X className="size-4 text-subtle" />}
                <span className={cx("min-w-0", !r.value && "text-muted")}>{r.indicator}{r.cites?.length ? <Cites ids={r.cites} onCite={onCite} /> : null}</span>
                <Bar value={Math.abs(r.weight) / maxW} tone={!r.value ? "muted" : r.weight >= 0 ? "ink" : "ok"} />
                <span className={cx("text-right font-mono text-[0.8rem] tabular-nums", !r.value && "text-subtle")}>{r.weight > 0 ? "+" : ""}{r.weight}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[0.8667rem] text-muted">
            Contează doar rândurile bifate. {typeof debate.rejected_without_citation === "number" ? `Am eliminat ${debate.rejected_without_citation} afirmații fără sursă. ` : ""}Recomandarea o semnează un om.
          </p>
        </div>
      )}
    </div>
  );
}

// ================================================================== contrafactual

function Counterfactual({ d, caseId }: { d: CaseDetail; caseId: string }) {
  const api = useApi();
  const actual = Boolean(d.rule_context?.screen_showed_amount_and_payee);
  const [on, setOn] = useState(false);
  const [result, setResult] = useState<CounterfactualResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = on ? !actual : actual;
  async function toggle() {
    if (on) {
      setOn(false);
      setResult(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await api.counterfactual(caseId, { field: "screen_showed_amount_and_payee", value: !actual });
      if ((r as unknown as { error?: string }).error) throw new Error((r as unknown as { error: string }).error);
      setResult(r);
      setOn(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nu am putut recalcula.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <button type="button" role="switch" aria-checked={shown} onClick={toggle} disabled={busy}
        className={cx("flex w-full max-w-[34rem] items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors", on ? "border-yellow-line bg-yellow-tint" : "border-line-strong hover:bg-hover", busy && "opacity-60")}>
        <span className={cx("relative h-5 w-9 shrink-0 rounded-full transition-colors", shown ? "bg-ink" : "bg-line-strong")}>
          <span className={cx("absolute top-0.5 size-4 rounded-full bg-paper transition-all", shown ? "left-[18px]" : "left-0.5")} />
        </span>
        <span className="min-w-0">
          <span className="block text-[0.9333rem] font-medium">Ecranul a arătat suma și beneficiarul</span>
          <span className="block text-[0.8rem] text-muted">{on ? "ipoteză: am schimbat faptul" : `în realitate: ${actual ? "da" : "nu"}`}</span>
        </span>
        {busy && <Loader2 aria-hidden className="ml-auto size-4 animate-spin text-muted" />}
      </button>
      {error && <p className="text-[0.9333rem] text-danger">{error}</p>}
      {result && on && (
        <div className="animate-enter flex flex-col gap-3">
          <ul className="divide-y divide-line rounded-md border border-line">
            {result.after.map((a) => {
              const b = result.before.find((x) => x.question === a.question);
              const changed = result.changed.includes(a.question);
              return (
                <li key={a.question} className={cx("flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-[0.9333rem]", changed && "bg-yellow-tint")}>
                  <span className="text-ink-soft">{questionLabel(a.question)}</span>
                  <span className="flex items-center gap-1.5 font-medium">
                    {changed
                      ? <><s className="font-normal text-muted">{verdictLabel(b?.decision)}</s><ArrowRight aria-hidden className="size-3.5" />{verdictLabel(a.decision)}</>
                      : <>{verdictLabel(a.decision)} <span className="font-normal text-muted">neschimbat</span></>}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="max-w-[70ch] text-[0.9333rem] text-ink-soft">{result.explanation}</p>
        </div>
      )}
    </div>
  );
}
