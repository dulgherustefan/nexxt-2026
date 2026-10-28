/**
 * Contestații: coada de lucru a operatorului. Trei cifre, trei file, un tabel.
 * Cele mai urgente sunt primele: întâi ce așteaptă semnătura, apoi termenul cel mai apropiat.
 */
import { ChevronRight, MonitorPlay, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { money, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { CaseSummary, ScenarioInfo } from "../../api/types";
import { Button, cx, DeadlineText, Dialog, dueText, EmptyState, ErrorNote, Skeleton, StatStrip, Tabs, useNowTick } from "../../ui/kit";
import { caseStatus, scenarioLabel, StatusPill } from "./caseUi";

type TabId = "todo" | "sign" | "done";

const group = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human).group;
const isClosed = (c: CaseSummary) => group(c) === "closed";
const needsYou = (c: CaseSummary) => group(c) === "you";

const TZ = "Europe/Bucharest";
const dayKey = (t: number | string) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(t));

function byUrgency(a: CaseSummary, b: CaseSummary): number {
  const rank = (c: CaseSummary) => (needsYou(c) ? 0 : isClosed(c) ? 2 : 1);
  const r = rank(a) - rank(b);
  if (r) return r;
  if (isClosed(a) && isClosed(b)) return new Date(b.received_at).getTime() - new Date(a.received_at).getTime();
  const da = a.deadline ? new Date(a.deadline).getTime() : Infinity;
  const db = b.deadline ? new Date(b.deadline).getTime() : Infinity;
  return da - db;
}

export default function QueuePage() {
  const api = useApi();
  const navigate = useNavigate();
  const cases = useResource(() => api.cases(), [api], { pollMs: 3000 });
  const now = useNowTick(30_000);
  const [tab, setTab] = useState<TabId | null>(null);
  const [dialog, setDialog] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const list = useMemo(() => [...(cases.data ?? [])].sort(byUrgency), [cases.data]);
  const open = list.filter((c) => !isClosed(c));
  const sign = list.filter(needsYou);
  const done = list.filter(isClosed);
  const today = dayKey(now);
  const refundedToday = done.filter((c) => c.status === "RAMBURSAT" && dayKey(c.received_at) === today);
  const refundedSum = refundedToday.reduce((s, c) => s + (c.amount?.value ?? 0), 0);
  const nextDue = open.map((c) => c.deadline).filter(Boolean).sort()[0] ?? null;

  const active: TabId = tab ?? (sign.length ? "sign" : "todo");
  const visible = active === "todo" ? open : active === "sign" ? sign : done;

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

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[1.4rem] leading-tight font-semibold">Contestații</h1>
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setDialog(true)}>Caz nou</Button>
      </div>

      {startError && <div className="mb-4"><ErrorNote error={startError} what="cazul nou" /></div>}

      {cases.data && list.length > 0 && (
        <div className="mb-8">
          <StatStrip items={[
            { label: "De rezolvat azi", value: open.length, sub: nextDue ? `primul termen: ${dueText(nextDue, now)}` : undefined },
            { label: "Așteaptă semnătura ta", value: sign.length, tone: sign.length ? "now" : "ink" },
            { label: "Rambursat azi", value: money(refundedSum), sub: refundedToday.length === 1 ? "un caz" : `${refundedToday.length} cazuri`, tone: refundedSum > 0 ? "ok" : "ink" },
          ]} />
        </div>
      )}

      {cases.error && !cases.data ? (
        <ErrorNote error={cases.error} what="contestațiile" onRetry={cases.reload} />
      ) : !cases.data ? (
        <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={<MonitorPlay className="size-5" />}
          title="Nicio contestație încă."
          action={<div className="flex flex-wrap gap-2">
            <Link to="/demo" className="inline-flex h-10 items-center gap-2 rounded-md border border-yellow-line bg-yellow px-4 text-[0.9333rem] font-semibold hover:bg-yellow-hover"><MonitorPlay className="size-4" /> Deschide Demo</Link>
            <Button onClick={() => setDialog(true)}>Caz nou</Button>
          </div>}
        >
          Demo-ul trece prin tot fluxul: SMS-ul fals, contestația din aplicație, decizia și banii înapoi.
        </EmptyState>
      ) : (
        <>
          <Tabs<TabId>
            label="Filtrează contestațiile"
            value={active}
            onChange={setTab}
            tabs={[
              { id: "todo", label: "De făcut", count: open.length },
              { id: "sign", label: "Așteaptă semnătura", count: sign.length },
              { id: "done", label: "Rezolvate", count: done.length },
            ]}
          />
          <div className="mt-4">
            {visible.length === 0 ? (
              <EmptyState title={active === "sign" ? "Nimic de semnat." : active === "todo" ? "Nimic deschis." : "Niciun caz rezolvat încă."}>
                {active === "done" ? "Cazurile închise apar aici." : "Cazurile noi apar aici în câteva secunde."}
              </EmptyState>
            ) : (
              <CasesTable cases={visible} onOpen={(id) => navigate(`/cazuri/${encodeURIComponent(id)}`)} />
            )}
          </div>
          {cases.error && <p className="mt-3 text-[0.8667rem] text-danger">Nu mai primesc actualizări de la server. Afișez ultima listă primită.</p>}
        </>
      )}

      {dialog && <NewCaseDialog onClose={() => setDialog(false)} onStart={startCase} busy={starting} />}
    </>
  );
}

function RowAction({ c }: { c: CaseSummary }) {
  const you = needsYou(c);
  return (
    <span className={cx("inline-flex h-8 items-center gap-1 rounded-md px-2.5 text-[0.8667rem] font-semibold whitespace-nowrap", you ? "border border-line-strong bg-paper" : "text-ink-soft")}>
      {you ? "Semnează" : "Deschide"} <ChevronRight aria-hidden className="size-3.5" />
    </span>
  );
}

function CasesTable({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <>
      {/* telefon: un rând pe caz */}
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line md:hidden">
        {cases.map((c) => (
          <li key={c.case_id}>
            <button type="button" onClick={() => onOpen(c.case_id)} className="flex w-full flex-col gap-1.5 px-4 py-3 text-left hover:bg-hover">
              <span className="flex items-center justify-between gap-3">
                <span className="font-semibold tabular-nums">{money(c.amount)}</span>
                <StatusPill status={String(c.status)} requiresHuman={c.requires_human} />
              </span>
              <span className="text-[0.9333rem]">{c.customer_alias} <span className="text-muted">· {scenarioLabel(c.scenario)}</span></span>
              <span className="text-[0.8667rem]"><DeadlineText deadline={c.deadline} done={isClosed(c)} /></span>
            </button>
          </li>
        ))}
      </ul>
      {/* ecran mare: tabel */}
      <div className="relative hidden overflow-x-auto rounded-lg border border-line md:block">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line text-[0.8rem] text-muted">
              <th scope="col" className="px-4 py-2.5 font-medium">Client</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">Sumă</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Ce s-a întâmplat</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Termen</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Stare</th>
              <th scope="col" className="w-px px-4 py-2.5"><span className="sr-only">Acțiune</span></th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr
                key={c.case_id}
                tabIndex={0}
                aria-label={`Deschide cazul ${c.case_id}, ${c.customer_alias}`}
                onClick={() => onOpen(c.case_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onOpen(c.case_id);
                  if (e.key === "ArrowDown") (e.currentTarget.nextElementSibling as HTMLElement | null)?.focus();
                  if (e.key === "ArrowUp") (e.currentTarget.previousElementSibling as HTMLElement | null)?.focus();
                }}
                className="cursor-pointer border-b border-line transition-colors last:border-b-0 hover:bg-canvas focus-visible:bg-canvas focus-visible:outline-offset-[-2px]"
              >
                <td className="px-4 py-3">
                  <p className="text-[0.9333rem] font-medium">{c.customer_alias}</p>
                  <p className="font-mono text-[0.75rem] text-muted">{c.case_id}</p>
                </td>
                <td className="px-4 py-3 text-right font-semibold whitespace-nowrap tabular-nums">{money(c.amount)}</td>
                <td className="px-4 py-3 text-[0.9333rem] text-ink-soft" title={c.verdict ? `Decizie: ${verdictLabel(c.verdict)}` : undefined}>{scenarioLabel(c.scenario)}</td>
                <td className="px-4 py-3 text-[0.9333rem]"><DeadlineText deadline={c.deadline} done={isClosed(c)} /></td>
                <td className="px-4 py-3"><StatusPill status={String(c.status)} requiresHuman={c.requires_human} /></td>
                <td className="px-4 py-3 text-right"><RowAction c={c} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function NewCaseDialog({ onClose, onStart, busy }: { onClose: () => void; onStart: (id: string) => void; busy: boolean }) {
  const api = useApi();
  const scenarios = useResource(() => api.scenarios(), [api]);
  const [choice, setChoice] = useState<string>("demo_t1");
  return (
    <Dialog
      title="Caz nou"
      onClose={onClose}
      width={560}
      footer={<>
        <Button onClick={onClose}>Renunță</Button>
        <Button variant="primary" busy={busy} disabled={!choice} onClick={() => onStart(choice)}>Pornește cazul</Button>
      </>}
    >
      <p className="text-[0.9333rem] text-muted">Alege o situație. Datele sunt sintetice. Agenții pornesc imediat.</p>
      {scenarios.error && !scenarios.data ? (
        <div className="mt-4"><ErrorNote error={scenarios.error} what="scenariile" onRetry={scenarios.reload} /></div>
      ) : !scenarios.data ? (
        <div className="mt-4 flex flex-col gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : (
        <fieldset className="mt-4 flex flex-col divide-y divide-line rounded-md border border-line">
          <legend className="sr-only">Situația</legend>
          {scenarios.data.map((s: ScenarioInfo) => (
            <label key={s.id} className={cx("flex cursor-pointer gap-3 px-3 py-2.5", choice === s.id ? "bg-yellow-tint" : "hover:bg-hover")}>
              <input type="radio" name="scenario" value={s.id} checked={choice === s.id} onChange={() => setChoice(s.id)} className="mt-1 accent-ink" />
              <span className="min-w-0">
                <span className="block text-[0.9333rem] font-medium">{s.title || scenarioLabel(s.id)}</span>
                {s.description && <span className="block text-[0.8667rem] text-muted">{s.description}</span>}
              </span>
            </label>
          ))}
        </fieldset>
      )}
    </Dialog>
  );
}
