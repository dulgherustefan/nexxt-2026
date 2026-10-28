/**
 * „Azi”: ce are operatorul de făcut azi, cât s-a returnat, ce e în risc și ce fac agenții acum.
 */
import { ArrowRight, Hand, MonitorPlay, Plus, Radio } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { clock, duration, money, toMoney } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { AgentEvent, CaseSummary } from "../../api/types";
import { Button, cx, Dot, EmptyState, ErrorNote, IdTag, SectionBoundary, Skeleton, useNowTick } from "../../ui/kit";
import { Bar, BigStat, Ring, slaTone, TONE_STROKE } from "../../ui/viz";
import { NewCaseSheet } from "./CasesPage";
import { caseStatus, scenarioLabel, StatusLine } from "./caseUi";
import { get } from "./evalReport";

const DAY = 86_400_000;

function windowFraction(c: CaseSummary, now: number): number | null {
  if (!c.deadline) return null;
  const end = new Date(c.deadline).getTime();
  const start = c.received_at ? new Date(c.received_at).getTime() : end - DAY;
  const span = end - start;
  if (!(span > 0)) return null;
  return Math.max(0, Math.min(1, (end - now) / span));
}

function countdown(deadline: string | null, now: number): string {
  if (!deadline) return "—";
  const s = Math.round((new Date(deadline).getTime() - now) / 1000);
  if (s <= 0) return "depășit";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

const isClosed = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human).group === "closed";
const needsYou = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human).group === "you";

export default function HomePage() {
  const api = useApi();
  const navigate = useNavigate();
  const stats = useResource(() => api.stats(), [api], { pollMs: 3000 });
  const cases = useResource(() => api.cases(), [api], { pollMs: 3000 });
  const [sheet, setSheet] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const now = useNowTick(1000);

  async function startCase(scenarioId: string) {
    setStarting(true);
    setStartError(null);
    try {
      const { case_id } = await api.createCase({ scenario_id: scenarioId });
      await api.runCase(case_id);
      navigate(`/cazuri/${encodeURIComponent(case_id)}`);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Cazul nu a pornit.");
      setStarting(false);
    }
  }

  const list = cases.data ?? [];
  const due = list.filter((c) => c.deadline && new Date(c.deadline).getTime() - now < 2 * DAY);
  const dueOpen = due.filter((c) => !isClosed(c)).length;
  const dueDone = due.length - dueOpen;
  const s = stats.data;
  const refunded = toMoney(s?.amount_refunded)?.value ?? 0;
  const recoverable = toMoney(s?.amount_recoverable)?.value ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <section className="grid items-end gap-5 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <p className="text-[0.8rem] font-bold tracking-wide text-muted">AZI · {new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", weekday: "long", day: "numeric", month: "long" }).format(now).toUpperCase()}</p>
          <h1 className="display mt-1 max-w-[24ch] text-[2.4rem] leading-[1.02] font-black sm:text-[2.9rem]">
            Banii furați se întorc <span className="bg-yellow px-1.5">până mâine seară.</span>
          </h1>
          <p className="mt-3 max-w-[78ch] text-[1.05rem] text-ink-soft">
            De la CJUE C-70/25 (15.10.2026), banca rambursează o plată neautorizată până la sfârșitul zilei lucrătoare următoare, chiar dacă clientul a fost neglijent.
            VersoML face cazul în aproximativ un minut: agenții strâng probele în paralel, regulile decid cu ID, tu semnezi doar excepțiile, iar contul care a primit banii pleacă spre AML, dincolo de zid.
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link to="/demo" className="inline-flex h-12 items-center gap-2 rounded-lg border-2 border-ink bg-yellow px-5 text-[1.05rem] font-black hover:bg-yellow-hover">
            <MonitorPlay className="size-5" /> Demo ghidat
          </Link>
          <button type="button" onClick={() => setSheet(true)} className="inline-flex h-12 items-center gap-2 rounded-lg border-2 border-ink bg-paper px-5 text-[1.05rem] font-bold hover:bg-hover">
            <Plus className="size-5" /> Caz nou
          </button>
        </div>
      </section>
      {startError && <ErrorNote error={startError} what="cazul nou" onRetry={() => startCase("demo_t1")} />}

      <SectionBoundary label="Indicatori">
        <section aria-label="Indicatorii zilei" className="grid gap-px overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-2 xl:grid-cols-[1.25fr_1fr_1fr_1fr_1fr]">
          <div className="flex items-center gap-4 bg-paper px-5 py-4">
            <Ring value={due.length ? dueDone / due.length : 0} size={104} stroke={12} tone={dueOpen ? "warn" : "ok"} label="Cazuri cu termen azi și mâine rezolvate">
              <span className="flex flex-col items-center leading-none">
                <span className="display text-[1.9rem] font-black tabular-nums">{dueOpen}</span>
                <span className="mt-0.5 text-[0.7rem] font-semibold text-muted">deschise</span>
              </span>
            </Ring>
            <div>
              <p className="text-[0.8667rem] font-semibold text-muted">Termen T+1 azi și mâine</p>
              <p className="display mt-0.5 text-[1.6rem] leading-none font-black tabular-nums">{dueDone}/{due.length}</p>
              <p className="mt-1 text-[0.8667rem] text-ink-soft">rezolvate în termen</p>
            </div>
          </div>
          <div className="bg-paper px-5 py-4">{s ? <BigStat label="Rambursat" value={money(refunded)} tone="ok" sub={`${s.refunded} cazuri, fără să aștepte poliția`} /> : <Skeleton className="h-16" />}</div>
          <div className="bg-paper px-5 py-4">{s ? <BigStat label="De recuperat" value={money(recoverable)} sub="rechemare sau chargeback pregătite" /> : <Skeleton className="h-16" />}</div>
          <div className="bg-paper px-5 py-4">{s ? <BigStat label="Timp mediu până la decizie" value={s.avg_decision_seconds ? duration(s.avg_decision_seconds) : "—"} sub="5–6 sisteme verificate în paralel" /> : <Skeleton className="h-16" />}</div>
          <div className={cx("px-5 py-4", s && s.deadlines_at_risk > 0 ? "bg-danger-soft" : "bg-paper")}>
            {s ? (
              <BigStat label="Termene în risc (< 6 h)" value={s.deadlines_at_risk} tone={s.deadlines_at_risk > 0 ? "danger" : "ink"}
                sub={s.awaiting_human ? <span className="inline-flex items-center gap-1 font-semibold"><Hand className="size-3.5" /> {s.awaiting_human} așteaptă semnătura ta</span> : "nimic nu te așteaptă"} />
            ) : <Skeleton className="h-16" />}
          </div>
        </section>
      </SectionBoundary>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <SectionBoundary label="Coada">
          <Queue cases={list} loading={!cases.data && !cases.error} error={cases.error} onRetry={cases.reload} now={now} onStart={() => startCase("demo_t1")} starting={starting} />
        </SectionBoundary>
        <div className="flex flex-col gap-6">
          <SectionBoundary label="Activitatea agenților"><Ticker /></SectionBoundary>
          <SectionBoundary label="Campanii"><Campaigns cases={list} /></SectionBoundary>
        </div>
      </div>
      {sheet && <NewCaseSheet onClose={() => setSheet(false)} onStart={startCase} busy={starting} />}
    </div>
  );
}

// ------------------------------------------------------------------ coada, după termen

function Queue({ cases, loading, error, onRetry, now, onStart, starting }: {
  cases: CaseSummary[]; loading: boolean; error?: Error; onRetry: () => void; now: number; onStart: () => void; starting: boolean;
}) {
  const navigate = useNavigate();
  const sorted = useMemo(() => [...cases].sort((a, b) => {
    const r = (c: CaseSummary) => (needsYou(c) ? 0 : isClosed(c) ? 2 : 1);
    const d = r(a) - r(b);
    if (d) return d;
    return (a.deadline ? new Date(a.deadline).getTime() : Infinity) - (b.deadline ? new Date(b.deadline).getTime() : Infinity);
  }), [cases]);
  const top = sorted.slice(0, 9);
  return (
    <section aria-label="Coada după termenul T+1" className="rounded-xl border border-line bg-paper">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div>
          <h2 className="text-[1.15rem] font-bold">Coada, după termenul T+1</h2>
          <p className="text-[0.8667rem] text-muted">Bara arată cât a mai rămas din fereastra legală: verde, apoi chihlimbar, apoi roșu.</p>
        </div>
        <Link to="/cazuri" className="inline-flex items-center gap-1 text-[0.9333rem] font-semibold underline">Toate <ArrowRight className="size-4" /></Link>
      </header>
      {error && !cases.length ? (
        <div className="p-4"><ErrorNote error={error} what="coada" onRetry={onRetry} /></div>
      ) : loading ? (
        <div className="flex flex-col gap-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : !top.length ? (
        <div className="p-4">
          <EmptyState title="Nicio contestație încă." action={<Button variant="primary" busy={starting} onClick={onStart}>Pornește un caz demo</Button>}>
            Pornește demo-ul ghidat sau un caz sintetic. O plată contestată din Banca Demo apare aici în câteva secunde.
          </EmptyState>
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {top.map((c) => {
            const closed = isClosed(c);
            const frac = windowFraction(c, now);
            const tone = slaTone(frac, closed);
            const you = needsYou(c);
            return (
              <li key={c.case_id}>
                <button type="button" onClick={() => navigate(`/cazuri/${encodeURIComponent(c.case_id)}`)}
                  className={cx("grid w-full grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-x-4 gap-y-1 px-5 py-3 text-left hover:bg-yellow-tint sm:grid-cols-[7.5rem_minmax(0,1fr)_8rem_11rem]", you && "bg-yellow-tint")}>
                  <span className="flex flex-col">
                    <span className="display text-[1.25rem] font-black tabular-nums" style={{ color: closed ? "var(--color-muted)" : TONE_STROKE[tone] }}>{closed ? "în termen" : countdown(c.deadline, now)}</span>
                    <Bar value={closed ? 1 : frac ?? 0} tone={tone} height={6} className="mt-1" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2"><IdTag>{c.case_id}</IdTag><span className="truncate font-medium">{c.customer_alias}</span></span>
                    <span className="mt-0.5 block truncate text-[0.8667rem] text-ink-soft">{scenarioLabel(c.scenario)}</span>
                  </span>
                  <span className="display hidden text-right text-[1.15rem] font-black tabular-nums sm:block">{money(c.amount)}</span>
                  <span className="hidden text-[0.9333rem] font-semibold sm:block"><StatusLine status={String(c.status)} requiresHuman={c.requires_human} /></span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ ticker

function tickerText(e: AgentEvent): string | null {
  if (e.type === "TOOL_CALL_END") return null;
  if (e.type === "TOOL_CALL_START") return `apelează ${e.name ?? "un tool"}`;
  return e.message ?? null;
}

function Ticker() {
  const api = useApi();
  const source = useMemo(() => api.ticker(), [api]);
  const stream = useEventStream(source, "ticker");
  const rows = stream.events.filter((e) => tickerText(e)).slice(-14).reverse();
  return (
    <section aria-label="Agenții, acum" className="rounded-xl border-2 border-ink bg-ink text-paper">
      <header className="flex items-center justify-between border-b border-white/15 px-4 py-2.5">
        <h2 className="flex items-center gap-2 font-bold"><Radio className="size-4 text-yellow" /> Agenții, acum</h2>
        <span className="flex items-center gap-1.5 text-[0.8rem] text-white/70"><Dot tone={stream.status === "open" ? "now" : "neutral"} live={stream.status === "open"} /> {stream.status === "open" ? "live" : "mă conectez"}</span>
      </header>
      {rows.length === 0 ? (
        <p className="px-4 py-4 text-[0.9333rem] text-white/70">Liniște. Pornește un caz și vezi aici fiecare agent, tool și regulă, în timp real.</p>
      ) : (
        <ul className="flex max-h-[24rem] flex-col overflow-hidden px-2 py-2">
          {rows.map((e, i) => (
            <li key={`${e.run_id}-${e.seq}-${i}`} className={cx("grid grid-cols-[3.6rem_minmax(0,1fr)] gap-2 rounded-md px-2 py-1 text-[0.8667rem]", i === 0 && "animate-ticker-in")}>
              <span className="font-mono text-[0.75rem] text-white/50 tabular-nums">{clock(e.ts)}</span>
              <span className="min-w-0">
                <span className="font-semibold text-yellow">{(e.agent ?? "Sistem").split("/").pop()}</span>{" "}
                <span className="text-white/85">{tickerText(e)}</span>{" "}
                {e.case_id?.startsWith("CT-") && <Link to={`/cazuri/${encodeURIComponent(e.case_id)}`} className="font-mono text-[0.75rem] text-white/50 underline hover:text-paper">{e.case_id}</Link>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ campanii (din datele zonei client)

function Campaigns({ cases }: { cases: CaseSummary[] }) {
  const api = useApi();
  const groups = useMemo(() => {
    const m = new Map<string, { scenario: string; cases: CaseSummary[]; amount: number }>();
    for (const c of cases) {
      const k = String(c.scenario ?? "altele");
      const g = m.get(k) ?? { scenario: k, cases: [], amount: 0 };
      g.cases.push(c);
      g.amount += toMoney(c.amount)?.value ?? 0;
      m.set(k, g);
    }
    return [...m.values()].sort((a, b) => b.amount - a.amount).slice(0, 4);
  }, [cases]);
  const sampleKey = groups.map((g) => g.cases[0]?.case_id).join(",");
  const [domains, setDomains] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    groups.slice(0, 3).forEach((g) => {
      const id = g.cases[0]?.case_id;
      if (!id || domains[g.scenario]) return;
      void api.caseDetail(id).then((d) => {
        const rdap = d.facts?.find((f) => f.kind === "domain.rdap");
        const dom = get(rdap?.content, "data", "domain");
        if (alive && typeof dom === "string") setDomains((x) => ({ ...x, [g.scenario]: dom }));
      }).catch(() => undefined);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, sampleKey]);
  const max = Math.max(1, ...groups.map((g) => g.amount));
  return (
    <section aria-label="Campanii active" className="rounded-xl border border-line bg-paper">
      <header className="border-b border-line px-4 py-2.5">
        <h2 className="font-bold">Campanii active</h2>
        <p className="text-[0.8667rem] text-muted">Același tip de atac, mai multe victime. Contul care a primit banii îl vede doar AML.</p>
      </header>
      {groups.length === 0 ? (
        <p className="px-4 py-4 text-[0.9333rem] text-muted">Nicio campanie încă.</p>
      ) : (
        <ul className="flex flex-col gap-3 px-4 py-3">
          {groups.map((g) => (
            <li key={g.scenario}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="min-w-0 truncate font-semibold">{scenarioLabel(g.scenario)}</span>
                <span className="shrink-0 font-black tabular-nums">{money(g.amount)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Bar value={g.amount / max} tone="ink" height={10} />
                <span className="shrink-0 text-[0.8rem] text-muted tabular-nums">{g.cases.length} {g.cases.length === 1 ? "victimă" : "victime"}</span>
              </div>
              {domains[g.scenario] && <p className="mt-1 truncate font-mono text-[0.75rem] text-danger">{domains[g.scenario]}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
