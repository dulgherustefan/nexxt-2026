/**
 * Camera cazului, ca o poveste în trei coloane:
 * stânga „Ce s-a întâmplat” (cronologia din probe + domeniul fals), centru graful agenților live și ceasul T+1,
 * dreapta decizia în cuvinte simple, cu regulile, probele citate, semnătura omului și „dacă ar fi fost altfel”.
 * Dedesubt: probele, dezbaterea, recuperarea, scrisoarea (cu zidul), registrul și regulile.
 */
import {
  ArrowLeft, ArrowRight, BadgeCheck, Banknote, Check, FileCheck2, Flag, Globe, KeyRound, Lock, Mail, MessageSquareWarning,
  MousePointerClick, Play, ShieldAlert, ShieldCheck, Smartphone, Split, X,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { channelLabel, clock, duration, money, pct, questionLabel, shortHash, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { AgentEvent, CaseDetail, CounterfactualResult, Fact, StoryItem } from "../../api/types";
import { Badge, Button, cx, Dot, EmptyState, ErrorNote, IdTag, SectionBoundary, Skeleton, Tabs, useNowTick } from "../../ui/kit";
import { Bar, Gauge, ModelBadge, Ring, slaTone, TONE_STROKE } from "../../ui/viz";
import { Arguments, Cites, ComplaintPanel, LedgerPanel, LetterTab, RecoveryPanel, RulesTab, SignatureBanner } from "./caseParts";
import { scenarioLabel, StatusLine, verdictSentence, whenPhrase } from "./caseUi";
import { get } from "./evalReport";

const AgentGraph = lazy(() => import("../../graph/AgentGraph"));

const RELOAD_ON = new Set(["decision", "interrupt", "refund", "ledger_seal", "hold_signal", "wall_block", "diode", "clock", "rule_hit"]);
const CLOSED = new Set(["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"]);

type TabId = "probe" | "dezbatere" | "recuperare" | "scrisoare" | "registru" | "reguli";

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
  const api = useApi();
  const { detail, events, streamStatus } = useCaseLive(caseId);
  const [tab, setTab] = useState<TabId>("probe");
  const [flash, setFlash] = useState<{ id: string; n: number } | null>(null);
  const [starting, setStarting] = useState(false);

  const cite = useCallback((factId: string) => {
    setFlash((f) => ({ id: factId, n: (f?.n ?? 0) + 1 }));
    window.setTimeout(() => {
      const story = document.getElementById(`story-${factId}`);
      const ev = document.getElementById(`fact-${factId}`);
      (story ?? ev)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 40);
  }, []);
  const citeToEvidence = useCallback((factId: string) => {
    setTab("probe");
    setFlash((f) => ({ id: factId, n: (f?.n ?? 0) + 1 }));
    window.setTimeout(() => document.getElementById(`fact-${factId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  }, []);
  const openTab = (t: TabId) => {
    setTab(t);
    window.setTimeout(() => document.getElementById("case-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 40);
  };

  const d = detail.data;
  if (detail.error && !d) {
    return (
      <div className="flex flex-col gap-4">
        {!compact && <BackLink />}
        <ErrorNote error={detail.error} what={`cazul ${caseId}`} onRetry={detail.reload} />
      </div>
    );
  }
  if (!d) return <RoomSkeleton />;

  const status = String(d.summary.status);
  const settled = CLOSED.has(status) && !d.interrupt?.pending;
  const start = async () => {
    setStarting(true);
    try {
      await api.runCase(caseId);
      await detail.reload();
    } finally {
      setStarting(false);
    }
  };

  const graph = (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionBoundary label="Graful agenților">
        <Suspense fallback={<Skeleton className="h-[560px] rounded-xl" />}>
          <AgentGraph
            nodes={d.pipeline?.nodes ?? []}
            edges={d.pipeline?.edges ?? []}
            events={events}
            settled={settled}
            height={compact ? 440 : 520}
            title="Agenții Judecătorului, live"
          />
        </Suspense>
      </SectionBoundary>
      {(status === "NOU" || status === "EROARE") && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-ink bg-yellow-soft px-4 py-3">
          <p className="flex-1 font-semibold">{status === "NOU" ? "Cazul așteaptă agenții." : "Rularea s-a oprit cu o eroare."}</p>
          <Button variant="primary" icon={<Play className="size-4" />} busy={starting} onClick={start}>{status === "NOU" ? "Pornește agenții" : "Pornește din nou"}</Button>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)]">
        <T1Clock d={d} />
        <LiveFeed events={events} streamStatus={streamStatus} />
      </div>
    </div>
  );

  const decision = <DecisionCard d={d} caseId={caseId} onCite={cite} onDone={detail.reload} onRules={() => openTab("reguli")} />;
  const story = (
    <div className="flex min-w-0 flex-col gap-4">
      <StoryTimeline d={d} flash={flash} onCite={citeToEvidence} />
      <PhishingCard facts={d.facts ?? []} onCite={citeToEvidence} />
      <SectionBoundary label="Reclamația"><ComplaintPanel d={d} /></SectionBoundary>
    </div>
  );
  const tabs = <CaseTabs d={d} caseId={caseId} tab={tab} setTab={setTab} flash={flash} onCite={citeToEvidence} />;

  return (
    <div className="flex flex-col gap-5">
      <RoomHeader d={d} compact={compact} />
      {compact ? (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
          {graph}
          {decision}
          <div className="xl:col-span-2 grid items-start gap-5 lg:grid-cols-[20rem_minmax(0,1fr)]">
            {story}
            {tabs}
          </div>
        </div>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_24rem] xl:grid-cols-[18rem_minmax(0,1fr)_22rem] 2xl:grid-cols-[21rem_minmax(0,1fr)_26rem]">
          <div className="order-3 lg:col-span-2 xl:order-1 xl:col-span-1">{story}</div>
          <div className="order-2 flex min-w-0 flex-col gap-5 xl:order-2">{graph}{tabs}</div>
          <div className="order-1 lg:order-2 xl:sticky xl:top-[4.5rem] xl:order-3 xl:max-h-[calc(100dvh-5.5rem)] xl:overflow-y-auto xl:rounded-xl">{decision}</div>
        </div>
      )}
      {detail.error && <p className="text-[0.8667rem] text-danger">Nu mai primesc actualizări de la server; afișez ultima stare primită.</p>}
    </div>
  );
}

// ================================================================== antet

function BackLink() {
  return (
    <Link to="/cazuri" className="inline-flex w-fit items-center gap-1.5 text-[0.9333rem] font-medium text-muted hover:text-ink">
      <ArrowLeft className="size-4" /> Toate contestațiile
    </Link>
  );
}

function RoomHeader({ d, compact }: { d: CaseDetail; compact: boolean }) {
  const s = d.summary;
  return (
    <div className="flex flex-col gap-2">
      {!compact && <BackLink />}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b-2 border-ink pb-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-[0.9333rem] text-muted">
            <IdTag>{s.case_id}</IdTag>
            <span className="font-medium text-ink">{s.customer_alias}</span>
            <span aria-hidden>·</span>
            <span>{scenarioLabel(s.scenario)}</span>
            <span aria-hidden>·</span>
            <span>{channelLabel(s.channel)}</span>
          </p>
          <h1 className={cx("display mt-1 font-black leading-none tabular-nums", compact ? "text-[2rem]" : "text-[2.6rem]")}>{money(s.amount)}</h1>
        </div>
        <div className="flex items-center gap-4 text-[1rem] font-semibold">
          <StatusLine status={String(s.status)} requiresHuman={s.requires_human} />
          {d.decision_seconds ? <Badge tone="dark">decis în {duration(d.decision_seconds)}</Badge> : null}
          {d.llm_mode && <Badge tone="neutral" title="Modul modelelor de limbaj pentru acest caz">LLM {d.llm_mode}</Badge>}
        </div>
      </div>
    </div>
  );
}

function RoomSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Se încarcă cazul">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-12 w-72" />
      <div className="grid gap-5 2xl:grid-cols-[21rem_1fr_26rem]">
        <Skeleton className="h-[34rem] rounded-xl" />
        <Skeleton className="h-[34rem] rounded-xl" />
        <Skeleton className="h-[34rem] rounded-xl" />
      </div>
    </div>
  );
}

// ================================================================== stânga: ce s-a întâmplat

const STORY_ICON: Record<string, ReactNode> = {
  sms: <MessageSquareWarning className="size-4" />,
  click: <MousePointerClick className="size-4" />,
  device: <Smartphone className="size-4" />,
  auth: <KeyRound className="size-4" />,
  payment: <Banknote className="size-4" />,
  dispute: <Flag className="size-4" />,
  aml: <Split className="size-4" />,
  refund: <BadgeCheck className="size-4" />,
  letter: <Mail className="size-4" />,
  seal: <Lock className="size-4" />,
};

/** Momentele atacului (roșu) vs. ale băncii (negru / verde). */
const ATTACK_KINDS = new Set(["sms", "click", "device", "auth", "payment"]);

function gap(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `+${s} s`;
  if (s < 3600) return `+${Math.round(s / 60)} min`;
  if (s < 86400) return `+${Math.round(s / 3600)} h`;
  return `+${Math.round(s / 86400)} zile`;
}

interface StoryRow extends StoryItem {
  t: number | null;
}

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
  if (sms) rows.unshift({ ts: "", kind: "sms", title: "SMS de la „curier”", detail: sms.content, fact_id: "EV-001", t: null });
  return rows;
}

function StoryTimeline({ d, flash, onCite }: { d: CaseDetail; flash: { id: string; n: number } | null; onCite: (id: string) => void }) {
  const rows = useMemo(() => buildStory(d), [d]);
  const click = rows.find((r) => r.kind === "click")?.t;
  const pay = rows.find((r) => r.kind === "payment")?.t;
  const refund = rows.find((r) => r.kind === "refund")?.t;
  const dispute = rows.find((r) => r.kind === "dispute")?.t;
  return (
    <section aria-label="Ce s-a întâmplat" className="rounded-xl border border-line bg-paper">
      <header className="border-b border-line px-4 py-3">
        <h2 className="font-bold">Ce s-a întâmplat</h2>
        <p className="text-[0.8667rem] text-muted">Din probele din registru, în ordine. Apasă pe un ID ca să vezi proba.</p>
      </header>
      {(click && pay) || (dispute && refund) ? (
        <div className="grid grid-cols-2 border-b border-line">
          {click && pay ? (
            <div className="border-r border-line px-4 py-2.5">
              <p className="display text-[1.6rem] font-black leading-none text-danger tabular-nums">{Math.round((pay - click) / 1000)} s</p>
              <p className="mt-1 text-[0.8rem] text-ink-soft">de la click la plată</p>
            </div>
          ) : <div />}
          {dispute && refund ? (
            <div className="px-4 py-2.5">
              <p className="display text-[1.6rem] font-black leading-none text-ok tabular-nums">{duration(Math.max(1, (refund - dispute) / 1000))}</p>
              <p className="mt-1 text-[0.8rem] text-ink-soft">de la contestație la bani returnați</p>
            </div>
          ) : <div />}
        </div>
      ) : null}
      {rows.length === 0 ? (
        <div className="p-4"><EmptyState title="Cronologia apare pe măsură ce colectorii găsesc probe." /></div>
      ) : (
        <ol className="relative px-4 py-3">
          {rows.map((r, i) => {
            const prev = rows.slice(0, i).reverse().find((x) => x.t !== null)?.t;
            const attack = ATTACK_KINDS.has(r.kind);
            const lit = flash && r.fact_id === flash.id;
            return (
              <li key={`${r.kind}-${i}`} id={r.fact_id ? `story-${r.fact_id}` : undefined}
                className={cx("relative grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 pb-3 last:pb-0", lit && "animate-flash rounded-md")}>
                {i < rows.length - 1 && <span aria-hidden className="absolute top-8 bottom-0 left-[15px] w-0.5 bg-line" />}
                <span className={cx(
                  "relative z-[1] grid size-8 place-items-center rounded-full border-2",
                  attack ? "border-danger bg-danger-soft text-danger" : r.kind === "refund" ? "border-ok bg-ok text-paper" : r.kind === "aml" ? "hazard-thin border-ink text-ink" : "border-ink bg-paper",
                )}>
                  {r.kind === "aml" ? <span className="grid size-5 place-items-center rounded-full bg-ink text-yellow">{STORY_ICON.aml}</span> : STORY_ICON[r.kind] ?? <Dot />}
                </span>
                <div className="min-w-0 pt-0.5">
                  <p className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-semibold">{r.title}</span>
                  </p>
                  {r.detail && <p className={cx("text-[0.8667rem] text-ink-soft", r.kind === "sms" ? "mt-1 rounded-md bg-canvas px-2 py-1.5 italic" : "break-all")}>{r.detail}</p>}
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[0.8rem] text-muted">
                    {r.t !== null ? <span className="font-mono tabular-nums">{clock(r.t)}</span> : <span>înainte de plată</span>}
                    {r.t !== null && prev ? <span className="tabular-nums">{gap(r.t - prev)}</span> : null}
                    {r.fact_id && <IdTag onClick={() => onCite(r.fact_id!)} title="Arată proba">{r.fact_id}</IdTag>}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

const ASK_LABEL: Record<string, string> = { card_number: "numărul cardului", cvv: "CVV", expiry: "expirarea", otp: "codul SMS", password: "parola" };

function factOf(facts: Fact[], kind: string): Fact | undefined {
  return facts.find((f) => f.kind === kind);
}

function PhishingCard({ facts, onCite }: { facts: Fact[]; onCite: (id: string) => void }) {
  const rdap = factOf(facts, "domain.rdap");
  const look = factOf(facts, "domain.lookalike");
  const sim = factOf(facts, "domain.similarity");
  const page = factOf(facts, "domain.page");
  const ct = factOf(facts, "domain.ct");
  const op = factOf(facts, "domain.openphish");
  if (!rdap && !look && !sim) return null;
  const domain = String(get(rdap?.content, "data", "domain") ?? get(look?.content, "data", "domain") ?? get(rdap?.content, "args", "domain") ?? "domeniu necunoscut");
  const age = Number(get(rdap?.content, "data", "age_hours"));
  const certAge = Number(get(ct?.content, "data", "cert_age_hours"));
  const scores = get(look?.content, "data", "brand_scores");
  const lookScore = scores && typeof scores === "object" ? Math.max(...Object.values(scores as Record<string, number>).filter((x) => typeof x === "number")) : Number(get(look?.content, "data", "score"));
  const brand = String(get(look?.content, "data", "closest_brand") ?? "");
  const similarity = Number(get(sim?.content, "score"));
  const asks = (get(page?.content, "data", "asks") as string[] | undefined) ?? [];
  const listed = get(op?.content, "data", "listed");
  return (
    <section aria-label="Domeniul fals" className="overflow-hidden rounded-xl border border-danger-line bg-paper">
      <header className="flex items-center gap-2 border-b border-danger-line bg-danger-soft px-4 py-2.5">
        <Globe className="size-4 text-danger" />
        <h2 className="font-bold">Pagina falsă</h2>
      </header>
      <div className="flex flex-col gap-3 px-4 py-3">
        <p className="break-all font-mono text-[0.9333rem] font-semibold">{domain}</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col items-center rounded-lg bg-canvas px-2 py-2">
            <Gauge value={Number.isFinite(lookScore) ? lookScore : null} size={118} label="scor de sosie" sub={brand ? `vs ${brand}` : undefined} />
            {look && <IdTag onClick={() => onCite(look.fact_id)}>{look.fact_id}</IdTag>}
          </div>
          <div className="flex flex-col items-center justify-between rounded-lg bg-canvas px-2 py-2">
            <Ring value={Number.isFinite(similarity) ? similarity : 0} size={86} stroke={9} tone="danger" label="asemănarea cu pagina băncii">
              <span className="display text-[1.3rem] font-black">{Number.isFinite(similarity) ? pct(similarity) : "—"}</span>
            </Ring>
            <p className="text-center text-[0.8rem] font-semibold leading-tight">seamănă cu pagina de login a băncii</p>
            {sim && <IdTag onClick={() => onCite(sim.fact_id)}>{sim.fact_id}</IdTag>}
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[0.9333rem]">Domeniu creat acum</span>
            <span className="display text-[1.3rem] font-black text-danger tabular-nums">{Number.isFinite(age) ? `${age} h` : "—"}</span>
          </div>
          <Bar value={Number.isFinite(age) ? 1 - Math.min(age, 72) / 72 : 0} tone="danger" title="Cu cât e mai nou, cu atât bara e mai plină (scară 72 h)" />
          <p className="flex flex-wrap items-center gap-1.5 text-[0.8rem] text-muted">
            {Number.isFinite(certAge) && <span>certificat TLS de {certAge} h ·</span>}
            {listed === false && <span>încă nelistat în OpenPhish ·</span>}
            {rdap && <IdTag onClick={() => onCite(rdap.fact_id)}>{rdap.fact_id}</IdTag>}
          </p>
        </div>
        {asks.length > 0 && (
          <div>
            <p className="text-[0.8667rem] font-semibold">Pagina cere:</p>
            <p className="mt-1 flex flex-wrap gap-1.5">
              {asks.map((a) => <span key={a} className="rounded-sm border border-danger-line bg-danger-soft px-1.5 py-0.5 text-[0.8rem] font-semibold text-danger">{ASK_LABEL[a] ?? a}</span>)}
              {page && <IdTag onClick={() => onCite(page.fact_id)}>{page.fact_id}</IdTag>}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

// ================================================================== centru: ceasul T+1 și fluxul live

function T1Clock({ d }: { d: CaseDetail }) {
  const now = useNowTick(1000);
  const deadline = d.clock?.t1_deadline ?? d.summary.deadline;
  const start = d.clock?.notified_at ?? d.summary.received_at;
  const status = String(d.summary.status);
  const refundTs = (d.story ?? []).find((s) => s.kind === "refund")?.ts;
  const end = deadline ? new Date(deadline).getTime() : NaN;
  const begin = start ? new Date(start).getTime() : NaN;
  const left = end - now;
  const windowMs = end - begin;
  const frac = Number.isFinite(left) && windowMs > 0 ? Math.max(0, Math.min(1, left / windowMs)) : 0;
  const done = status === "RAMBURSAT";
  const tone = slaTone(frac, done);
  const h = Math.floor(Math.max(0, left) / 3_600_000);
  const m = Math.floor((Math.max(0, left) % 3_600_000) / 60_000);
  const s = Math.floor((Math.max(0, left) % 60_000) / 1000);
  const margin = done && refundTs ? end - new Date(refundTs).getTime() : null;
  return (
    <section aria-label="Termenul T+1" className="flex items-center gap-4 rounded-xl border border-line bg-paper px-4 py-3">
      <Ring value={done ? 1 : frac} size={132} stroke={13} tone={tone} label="Timpul rămas până la termenul T+1">
        {done ? (
          <span className="flex flex-col items-center"><Check className="size-7 text-ok" strokeWidth={3} /><span className="text-[0.8rem] font-bold text-ok">rambursat</span></span>
        ) : deadline ? (
          <span className="flex flex-col items-center leading-none">
            <span className="display text-[1.45rem] font-black tabular-nums" style={{ color: TONE_STROKE[tone] }}>{h}:{String(m).padStart(2, "0")}</span>
            <span className="mt-1 font-mono text-[0.8rem] text-muted tabular-nums">:{String(s).padStart(2, "0")} rămase</span>
          </span>
        ) : <span className="text-muted">—</span>}
      </Ring>
      <div className="min-w-0">
        <p className="text-[0.8rem] font-bold tracking-wide text-muted">TERMEN T+1 · C-70/25</p>
        <p className="mt-0.5 text-[1.15rem] font-bold">{deadline ? whenPhrase(deadline, now) : "—"}</p>
        <p className="mt-1 max-w-[30ch] text-[0.8667rem] text-ink-soft">
          {done && margin !== null && margin > 0
            ? `Banii au plecat cu ${Math.floor(margin / 3_600_000)} h înainte de termen.`
            : "Sfârșitul zilei lucrătoare de după notificare, chiar dacă clientul a fost neglijent."}
        </p>
      </div>
    </section>
  );
}

function feedLine(e: AgentEvent): { tag: string; text: string; tone: "ink" | "ok" | "danger" | "muted" } | null {
  const who = (e.agent ?? "").split("/").pop() || "Sistem";
  if (e.type === "TOOL_CALL_START") return { tag: who, text: `apelează ${e.name ?? e.data?.tool ?? "un tool"}`, tone: "muted" };
  if (e.type === "CUSTOM") {
    if (e.name === "rule_hit") return { tag: "Reguli", text: e.message ?? "", tone: "ink" };
    if (e.name === "decision") return { tag: "Decizie", text: e.message ?? "", tone: "ink" };
    if (e.name === "refund") return { tag: "Bani", text: e.message ?? "Rambursare", tone: "ok" };
    if (e.name === "wall_block" || e.name === "policy_denied") return { tag: "Zid", text: e.message ?? "", tone: "danger" };
    if (e.name === "fact") return { tag: who, text: e.message ?? "", tone: "muted" };
    return { tag: who, text: e.message ?? String(e.name), tone: "ink" };
  }
  if (e.type === "STEP_FINISHED") return { tag: who, text: e.message ?? "gata", tone: "ink" };
  if (e.type === "RUN_FINISHED") return { tag: "Gata", text: e.message ?? "", tone: "ok" };
  if (e.type === "RUN_ERROR") return { tag: "Eroare", text: e.message ?? "", tone: "danger" };
  return null;
}

function LiveFeed({ events, streamStatus }: { events: AgentEvent[]; streamStatus: string }) {
  const lines = useMemo(() => events.map((e) => ({ e, l: feedLine(e) })).filter((x) => x.l).slice(-7).reverse(), [events]);
  return (
    <section aria-label="Fluxul live" className="min-w-0 rounded-xl border border-line bg-paper">
      <header className="flex items-center justify-between border-b border-line px-4 py-2">
        <h2 className="text-[0.9333rem] font-bold">Ce fac agenții</h2>
        <span className="flex items-center gap-1.5 text-[0.8rem] text-muted">
          <Dot tone={streamStatus === "open" ? "ok" : "neutral"} live={streamStatus === "open"} /> {streamStatus === "open" ? "live" : "reconectez"}
        </span>
      </header>
      {lines.length === 0 ? (
        <p className="px-4 py-3 text-[0.8667rem] text-muted">Evenimentele apar aici imediat ce pornește rularea.</p>
      ) : (
        <ul className="flex flex-col px-2 py-1.5">
          {lines.map(({ e, l }, i) => (
            <li key={`${e.run_id}-${e.seq}-${i}`} className={cx("flex min-w-0 items-baseline gap-2 rounded-md px-2 py-0.5 text-[0.8667rem]", i === 0 && "animate-ticker-in")}>
              <span className="shrink-0 font-mono text-[0.75rem] text-subtle tabular-nums">{clock(e.ts)}</span>
              <span className={cx("shrink-0 font-semibold", l!.tone === "ok" && "text-ok", l!.tone === "danger" && "text-danger")}>{l!.tag}</span>
              <span className={cx("min-w-0 truncate", l!.tone === "muted" ? "text-muted" : "text-ink-soft")}>{l!.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ================================================================== dreapta: decizia

function DecisionCard({ d, caseId, onCite, onDone, onRules }: { d: CaseDetail; caseId: string; onCite: (id: string) => void; onDone: () => Promise<void>; onRules: () => void }) {
  const decisions = d.decisions ?? [];
  const t1 = decisions.find((x) => x.question === "rambursare_t1");
  const sentence = verdictSentence(t1, d.summary.amount, {
    status: String(d.summary.status),
    action: d.interrupt?.pending ? undefined : d.interrupt?.answer?.action,
    approver: d.interrupt?.answer?.approver,
  });
  const titles = new Map((d.rules?.hits ?? []).map((h) => [h.rule_id, h.title]));
  const others = decisions.filter((x) => x.question !== "rambursare_t1");
  const frame = sentence.tone === "danger" ? "border-danger" : sentence.tone === "now" ? "border-ink" : sentence.tone === "ok" ? "border-ok" : "border-line";
  return (
    <section aria-label="Decizia" className={cx("flex flex-col overflow-hidden rounded-xl border-2 bg-paper", frame)}>
      <div className={cx("px-5 pt-4 pb-4", sentence.tone === "ok" ? "bg-ok-soft" : sentence.tone === "now" ? "bg-yellow-soft" : sentence.tone === "danger" ? "bg-danger-soft" : "bg-paper")}>
        <p className="flex items-center gap-2 text-[0.8rem] font-bold tracking-wide text-muted">
          {t1 ? <><FileCheck2 className="size-4" /> DECIZIA MOTORULUI DE REGULI{t1.decided_by === "rules+human" ? " · SEMNATĂ DE UN OM" : ""}</> : <><Dot tone="now" live /> AGENȚII LUCREAZĂ</>}
        </p>
        <h2 className="display mt-2 text-[1.75rem] leading-[1.1] font-black">{sentence.title}</h2>
        <p className="mt-2 text-[0.9333rem] text-ink-soft">{sentence.detail}</p>
        {t1?.rule_ids?.length ? (
          <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Regulile aplicate">
            {t1.rule_ids.map((r) => (
              <button key={r} type="button" onClick={onRules} title={titles.get(r) ?? r}
                className="inline-flex h-6 items-center rounded-sm border border-ink bg-paper px-1.5 font-mono text-[0.8rem] font-semibold hover:bg-yellow">
                {r}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {d.interrupt?.pending && (
        <div className="border-t-2 border-ink p-3">
          <SignatureBanner d={d} caseId={caseId} onDone={onDone} />
        </div>
      )}

      {t1?.rationale?.length ? (
        <div className="border-t border-line px-5 py-4">
          <p className="mb-2 text-[0.8rem] font-bold tracking-wide text-muted">DE CE</p>
          <ul className="flex flex-col gap-2.5">
            {t1.rationale.map((line, i) => (
              <li key={i} className="flex gap-2.5 text-[0.9333rem]">
                <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" strokeWidth={3} />
                <p className="min-w-0">{line.text}<Cites ids={line.cites} onCite={onCite} /></p>
              </li>
            ))}
          </ul>
        </div>
      ) : !t1 ? (
        <div className="flex flex-col gap-2 border-t border-line px-5 py-4"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /><Skeleton className="h-4 w-3/4" /></div>
      ) : null}

      {d.rule_context && <Counterfactual d={d} caseId={caseId} />}

      {others.length > 0 && (
        <div className="border-t border-line px-5 py-3">
          <p className="mb-1.5 text-[0.8rem] font-bold tracking-wide text-muted">ȘI MAI DEPARTE</p>
          <ul className="flex flex-col divide-y divide-line">
            {others.map((o) => (
              <li key={o.question} className="flex items-center justify-between gap-3 py-1.5 text-[0.9333rem]">
                <span className="text-ink-soft">{questionLabel(o.question)}</span>
                <span className="flex items-center gap-2 text-right font-semibold">
                  {verdictLabel(o.decision)}
                  {o.requires_human && <span title="Trimite un om" className="rounded-sm bg-yellow px-1 text-[0.7rem] font-bold">om</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

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
    <div className="border-t border-line px-5 py-4">
      <p className="mb-2 text-[0.8rem] font-bold tracking-wide text-muted">DACĂ AR FI FOST ALTFEL?</p>
      <button type="button" role="switch" aria-checked={shown} onClick={toggle} disabled={busy}
        className={cx("flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left", on ? "border-ink bg-yellow-soft" : "border-line-strong hover:bg-hover", busy && "opacity-60")}>
        <span className={cx("relative h-6 w-11 shrink-0 rounded-full border border-ink transition-colors", shown ? "bg-ink" : "bg-paper")}>
          <span className={cx("absolute top-0.5 size-[18px] rounded-full transition-all", shown ? "left-[22px] bg-yellow" : "left-0.5 bg-ink")} />
        </span>
        <span className="min-w-0">
          <span className="block font-semibold">Ecranul a afișat suma și beneficiarul</span>
          <span className="block text-[0.8rem] text-muted">{on ? "ipoteză: faptul e schimbat" : `în realitate: ${actual ? "da" : "nu"}`}</span>
        </span>
      </button>
      {error && <p className="mt-2 text-[0.8667rem] text-danger">{error}</p>}
      {result && on && (
        <div className="mt-3 flex flex-col gap-1.5 animate-enter">
          {result.after.map((a) => {
            const b = result.before.find((x) => x.question === a.question);
            const changed = result.changed.includes(a.question);
            return (
              <div key={a.question} className={cx("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2.5 py-1.5 text-[0.8667rem]", changed ? "bg-yellow" : "bg-canvas")}>
                <span className="text-ink-soft">{questionLabel(a.question)}</span>
                <span className="flex items-center gap-1.5 text-right font-semibold">
                  {changed ? <><s className="font-normal text-muted">{verdictLabel(b?.decision)}</s><ArrowRight className="size-3.5" />{verdictLabel(a.decision)}</> : <>{verdictLabel(a.decision)} <span className="font-normal text-muted">=</span></>}
                </span>
              </div>
            );
          })}
          <p className="mt-1 text-[0.9333rem]">{result.explanation}</p>
        </div>
      )}
    </div>
  );
}

// ================================================================== filele de jos

function CaseTabs({ d, caseId, tab, setTab, flash, onCite }: {
  d: CaseDetail; caseId: string; tab: TabId; setTab: (t: TabId) => void; flash: { id: string; n: number } | null; onCite: (id: string) => void;
}) {
  return (
    <section id="case-tabs" className="min-w-0 scroll-mt-4 rounded-xl border border-line bg-paper">
      <div className="px-2">
        <Tabs<TabId>
          label="Detaliile cazului"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "probe", label: "Probe", count: d.facts?.length ?? 0 },
            { id: "dezbatere", label: "Dezbatere" },
            { id: "recuperare", label: "Recuperare" },
            { id: "scrisoare", label: "Scrisoare" },
            { id: "registru", label: "Registru" },
            { id: "reguli", label: "Reguli", count: d.rules?.hits?.length ?? 0 },
          ]}
        />
      </div>
      <div className="p-4">
        <SectionBoundary label={tab}>
          {tab === "probe" && <EvidenceCards facts={d.facts ?? []} flash={flash} />}
          {tab === "dezbatere" && <DebateTab d={d} onCite={onCite} />}
          {tab === "recuperare" && <RecoveryTab d={d} />}
          {tab === "scrisoare" && <LetterTab d={d} caseId={caseId} onCite={onCite} />}
          {tab === "registru" && <LedgerPanel caseId={caseId} sealed={Boolean(d.ledger?.sealed)} count={d.ledger?.count ?? d.facts?.length ?? 0} />}
          {tab === "reguli" && <RulesTab d={d} />}
        </SectionBoundary>
      </div>
    </section>
  );
}

const CONF_LABEL: Record<string, string> = { client: "zona client", aml: "zona AML", "aml-only": "doar AML", public: "public" };

function EvidenceCards({ facts, flash }: { facts: Fact[]; flash: { id: string; n: number } | null }) {
  const [filter, setFilter] = useState<"all" | "trusted" | "untrusted">("all");
  if (!facts.length) return <EmptyState title="Nicio probă încă.">Colectorii scriu probele aici pe măsură ce le găsesc, fiecare cu sursă, oră și hash.</EmptyState>;
  const trusted = facts.filter((f) => f.labels?.trust !== "untrusted").length;
  const list = facts.filter((f) => filter === "all" || (filter === "untrusted" ? f.labels?.trust === "untrusted" : f.labels?.trust !== "untrusted"));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-2.5 min-w-[12rem] flex-1 overflow-hidden rounded-full" aria-hidden>
          <span className="bg-ink" style={{ width: `${(trusted / facts.length) * 100}%` }} />
          <span className="bg-danger-line" style={{ width: `${((facts.length - trusted) / facts.length) * 100}%` }} />
        </div>
        <div role="radiogroup" aria-label="Filtrează probele" className="inline-flex rounded-md border border-line p-0.5 text-[0.8667rem]">
          {([["all", `Toate ${facts.length}`], ["trusted", `Sistemele băncii ${trusted}`], ["untrusted", `Neîncrezute ${facts.length - trusted}`]] as const).map(([k, l]) => (
            <button key={k} type="button" role="radio" aria-checked={filter === k} onClick={() => setFilter(k)}
              className={cx("rounded-[5px] px-2.5 py-1 font-medium", filter === k ? "bg-ink text-paper" : "text-muted hover:text-ink")}>{l}</button>
          ))}
        </div>
      </div>
      <ul className="grid gap-2 md:grid-cols-2">
        {list.map((f) => (
          <li key={f.fact_id + (flash?.id === f.fact_id ? flash.n : "")} id={`fact-${f.fact_id}`}
            className={cx("flex flex-col gap-1.5 rounded-lg border px-3 py-2.5", f.labels?.trust === "untrusted" ? "border-danger-line" : "border-line", flash?.id === f.fact_id && "animate-flash")}>
            <div className="flex items-center justify-between gap-2">
              <IdTag tone={flash?.id === f.fact_id ? "now" : "neutral"}>{f.fact_id}</IdTag>
              <span className="truncate font-mono text-[0.75rem] text-muted" title={f.source_tool}>{f.source_tool}</span>
            </div>
            <p className="text-[0.9333rem]">{f.summary || f.kind}</p>
            <div className="flex flex-wrap items-center gap-1.5 text-[0.75rem]">
              {f.labels?.trust === "untrusted"
                ? <span className="inline-flex items-center gap-1 rounded-sm bg-danger-soft px-1.5 py-0.5 font-semibold text-danger"><ShieldAlert className="size-3" /> neîncrezut</span>
                : <span className="inline-flex items-center gap-1 rounded-sm bg-ok-soft px-1.5 py-0.5 font-semibold text-ok"><ShieldCheck className="size-3" /> sistemele băncii</span>}
              {f.labels?.conf && <span className="rounded-sm bg-canvas px-1.5 py-0.5 font-medium">{CONF_LABEL[f.labels.conf] ?? f.labels.conf}</span>}
              {f.labels?.sinks?.length ? <span className="text-muted">poate merge spre: {f.labels.sinks.join(", ")}</span> : null}
              <span className="ml-auto font-mono text-subtle" title={f.sha256}>{shortHash(f.sha256, 8)}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DebateTab({ d, onCite }: { d: CaseDetail; onCite: (id: string) => void }) {
  const debate = d.debate;
  if (!debate?.ran) {
    return <EmptyState title="Dezbaterea nu a rulat încă.">După rambursare, Procurorul (Opus) și Avocatul (Sonnet) argumentează dacă banca poate cere banii înapoi de la client; o rubrică deterministă cântărește, iar decizia o ia un om.</EmptyState>;
  }
  const rubric = debate.rubric ?? [];
  const maxW = Math.max(1, ...rubric.map((r) => Math.abs(r.weight)));
  const score = typeof debate.score === "number" ? debate.score : rubric.reduce((acc, r) => acc + (r.value ? r.weight : 0), 0);
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-line p-3">
          <p className="mb-2 flex items-center gap-2 font-bold">Procurorul <ModelBadge model={debate.models?.procuror ?? "opus"} /> <span className="text-[0.8667rem] font-normal text-muted">pentru recuperare</span></p>
          <Arguments title="" lines={debate.prosecutor} onCite={onCite} />
        </div>
        <div className="rounded-lg border border-line p-3">
          <p className="mb-2 flex items-center gap-2 font-bold">Avocatul <ModelBadge model={debate.models?.avocat ?? "sonnet"} /> <span className="text-[0.8667rem] font-normal text-muted">pentru client</span></p>
          <Arguments title="" lines={debate.defender} onCite={onCite} />
        </div>
      </div>
      {rubric.length > 0 && (
        <div className="rounded-lg border border-ink p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-bold">Rubrica deterministă (Cântăritorul)</p>
            <p className="text-[0.9333rem]">Scor <span className="display text-[1.3rem] font-black tabular-nums">{score > 0 ? "+" : ""}{score}</span> → <span className="font-semibold">{verdictLabel(String(debate.recommendation ?? debate.rubric_recommendation ?? ""))}</span></p>
          </div>
          <ul className="flex flex-col gap-2">
            {rubric.map((r) => (
              <li key={r.indicator} className="grid grid-cols-[1.25rem_minmax(0,1fr)_8rem_2.5rem] items-center gap-2 text-[0.9333rem]">
                {r.value ? <Check className="size-4 text-ink" strokeWidth={3} /> : <X className="size-4 text-subtle" />}
                <span className={cx("min-w-0", !r.value && "text-muted")}>{r.indicator}{r.cites?.length ? <Cites ids={r.cites} onCite={onCite} /> : null}</span>
                <Bar value={Math.abs(r.weight) / maxW} tone={!r.value ? "muted" : r.weight >= 0 ? "ink" : "ok"} />
                <span className={cx("text-right font-mono tabular-nums", !r.value && "text-subtle")}>{r.weight > 0 ? "+" : ""}{r.weight}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[0.8667rem] text-muted">
            Contează doar indicatorii bifați. {typeof debate.rejected_without_citation === "number" ? `${debate.rejected_without_citation} afirmații fără sursă au fost respinse automat. ` : ""}Recomandarea o semnează un om, nu modelul.
          </p>
        </div>
      )}
    </div>
  );
}

function RecoveryTab({ d }: { d: CaseDetail }) {
  const cb = d.recovery?.chargeback;
  const recall = d.recovery?.recall;
  const dnsc = d.recovery?.dnsc_report;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Flagged on={Boolean(cb?.eligible)} title="Chargeback" detail={cb ? (cb.eligible ? `posibil, cod ${cb.reason_code ?? "—"}` : cb.reason_code ? `nu (cod ${cb.reason_code})` : "nu se aplică") : "nu se aplică"} />
        <Flagged on={Boolean(recall)} title="Rechemare" detail={recall ? (recall.kind === "camt.056" ? "SEPA camt.056 · FRAD" : recall.kind === "interna" ? "internă, beneficiar la noi" : String(recall.kind)) : "nu"} />
        <Flagged on={Boolean(dnsc)} title="Raport DNSC" detail={dnsc ? dnsc.status ?? "ciornă" : "nu"} />
      </div>
      <RecoveryPanel d={d} />
    </div>
  );
}

function Flagged({ on, title, detail }: { on: boolean; title: string; detail: string }) {
  return (
    <div className={cx("rounded-lg border-2 px-3 py-2.5", on ? "border-ink bg-yellow-soft" : "border-line bg-canvas")}>
      <p className="flex items-center gap-2 font-bold">{on ? <Check className="size-4" strokeWidth={3} /> : <X className="size-4 text-subtle" />}{title}</p>
      <p className="mt-0.5 text-[0.8667rem] text-ink-soft">{detail}</p>
    </div>
  );
}
