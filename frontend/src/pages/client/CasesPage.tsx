import { Play, Plus, Smartphone } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { money, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { CaseSummary, ScenarioInfo } from "../../api/types";
import { Button, cx, DeadlineText, EmptyState, ErrorNote, IdTag, PageHeader, Skeleton, Tabs } from "../../ui/kit";
import { caseStatus, scenarioLabel, Sheet, StatusLine } from "./caseUi";

type Filter = "you" | "running" | "today" | "closed" | "all";

// o singură sursă pentru grupuri: aceeași funcție care dă eticheta stării
const group = (c: CaseSummary) => caseStatus(String(c.status), c.requires_human).group;
const needsYou = (c: CaseSummary) => group(c) === "you";
const isClosed = (c: CaseSummary) => group(c) === "closed";

function dueToday(c: CaseSummary): boolean {
  if (!c.deadline || isClosed(c)) return false;
  return new Date(c.deadline).getTime() - Date.now() < 24 * 3600 * 1000;
}

function byUrgency(a: CaseSummary, b: CaseSummary): number {
  const rank = (c: CaseSummary) => (needsYou(c) ? 0 : isClosed(c) ? 2 : 1);
  const r = rank(a) - rank(b);
  if (r) return r;
  const da = a.deadline ? new Date(a.deadline).getTime() : Infinity;
  const db = b.deadline ? new Date(b.deadline).getTime() : Infinity;
  return da - db;
}

export default function CasesPage() {
  const api = useApi();
  const navigate = useNavigate();
  const cases = useResource(() => api.cases(), [api], { pollMs: 3000 });
  const [filter, setFilter] = useState<Filter>("all");
  const [sheet, setSheet] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const list = useMemo(() => [...(cases.data ?? [])].sort(byUrgency), [cases.data]);
  const counts = useMemo(() => ({
    you: list.filter(needsYou).length,
    running: list.filter((c) => group(c) === "running").length,
    today: list.filter(dueToday).length,
    closed: list.filter(isClosed).length,
    all: list.length,
  }), [list]);
  const visible = list.filter((c) =>
    filter === "all" ? true
      : filter === "you" ? needsYou(c)
        : filter === "running" ? group(c) === "running"
          : filter === "today" ? dueToday(c)
            : isClosed(c));

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
      <PageHeader
        title="Contestații"
        description="Agenții strâng probele, motorul de reguli decide, iar tu semnezi doar ce cere legea. Cele mai urgente sunt primele."
        actions={
          <>
            <Button icon={<Play className="size-4" />} busy={starting} onClick={() => startCase("demo_t1")}>Pornește demo-ul</Button>
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setSheet(true)}>Contestație nouă</Button>
          </>
        }
      />
      {startError && <div className="mb-4"><ErrorNote error={startError} what="cazul nou" onRetry={() => startCase("demo_t1")} /></div>}

      <Tabs<Filter>
        label="Filtrează contestațiile"
        value={filter}
        onChange={setFilter}
        tabs={[
          { id: "all", label: "Toate", count: counts.all },
          { id: "you", label: "Te așteaptă", count: counts.you },
          { id: "running", label: "În lucru", count: counts.running },
          { id: "today", label: "Termen în 24 h", count: counts.today },
          { id: "closed", label: "Închise", count: counts.closed },
        ]}
      />

      <div className="mt-4">
        {cases.error && !cases.data ? (
          <ErrorNote error={cases.error} what="contestațiile" onRetry={cases.reload} />
        ) : !cases.data ? (
          <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Smartphone className="size-6" />}
            title="Nicio contestație încă."
            action={<div className="flex flex-wrap gap-2">
              <Button variant="primary" icon={<Play className="size-4" />} busy={starting} onClick={() => startCase("demo_t1")}>Pornește demo-ul</Button>
              <a className="inline-flex h-10 items-center rounded-md border border-line-strong px-4 font-semibold hover:bg-hover" href="/banca" target="_blank" rel="noreferrer">Deschide Banca Demo</a>
            </div>}
          >
            Pornește cazul demonstrativ sau deschide Banca Demo pe telefon: o plată contestată acolo apare aici în câteva secunde.
          </EmptyState>
        ) : visible.length === 0 ? (
          <EmptyState title="Nimic în această listă.">Alege alt filtru sau „Toate”.</EmptyState>
        ) : (
          <CasesTable cases={visible} onOpen={(id) => navigate(`/cazuri/${encodeURIComponent(id)}`)} />
        )}
      </div>
      {cases.error && cases.data && (
        <p className="mt-3 text-[0.8667rem] text-danger">Nu mai primesc actualizări de la server; afișez ultima listă primită.</p>
      )}

      {sheet && <NewCaseSheet onClose={() => setSheet(false)} onStart={startCase} busy={starting} />}
    </>
  );
}

function CasesTable({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <>
      <CasesList cases={cases} onOpen={onOpen} />
      <CasesGrid cases={cases} onOpen={onOpen} />
    </>
  );
}

/** Pe telefon: un rând pe caz, cu ce contează întâi (starea, timpul rămas, suma). */
function CasesList({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line md:hidden">
      {cases.map((c) => {
        const s = caseStatus(String(c.status), c.requires_human);
        return (
          <li key={c.case_id}>
            <button type="button" onClick={() => onOpen(c.case_id)}
              className={cx("flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-yellow-tint", s.group === "you" && "bg-yellow-tint/60")}>
              <span className="flex items-center justify-between gap-3">
                <span className="font-medium"><StatusLine status={String(c.status)} requiresHuman={c.requires_human} /></span>
                <span className="whitespace-nowrap text-[0.8667rem]"><DeadlineText deadline={c.deadline} done={isClosed(c)} /></span>
              </span>
              <span><span className="font-semibold tabular-nums">{money(c.amount)}</span> <span className="text-muted">· {c.customer_alias}</span></span>
              <span className="text-[0.8667rem] text-ink-soft">{scenarioLabel(c.scenario)} · <span className="font-mono text-[0.8rem] text-muted">{c.case_id}</span></span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function CasesGrid({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <div className="hidden overflow-x-auto rounded-lg border border-line md:block">
      <table className="w-full min-w-[56rem] border-collapse text-left">
        <thead>
          <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
            <th scope="col" className="px-4 py-2.5 font-semibold">Timp rămas</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Caz</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Client</th>
            <th scope="col" className="px-4 py-2.5 text-right font-semibold">Sumă</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Ce s-a întâmplat</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Decizie</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">Stare</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => {
            const s = caseStatus(String(c.status), c.requires_human);
            const closed = isClosed(c);
            return (
              <tr
                key={c.case_id}
                tabIndex={0}
                aria-label={`Deschide cazul ${c.case_id}`}
                onClick={() => onOpen(c.case_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onOpen(c.case_id);
                  if (e.key === "ArrowDown") (e.currentTarget.nextElementSibling as HTMLElement | null)?.focus();
                  if (e.key === "ArrowUp") (e.currentTarget.previousElementSibling as HTMLElement | null)?.focus();
                }}
                className={cx(
                  "cursor-pointer border-b border-line last:border-b-0 hover:bg-yellow-tint focus-visible:bg-yellow-tint",
                  s.group === "you" && "bg-yellow-tint/60",
                )}
              >
                <td className="whitespace-nowrap px-4 py-3"><DeadlineText deadline={c.deadline} done={closed} /></td>
                <td className="whitespace-nowrap px-4 py-3"><IdTag>{c.case_id}</IdTag></td>
                <td className="whitespace-nowrap px-4 py-3">{c.customer_alias}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums">{money(c.amount)}</td>
                <td className="px-4 py-3 text-ink-soft">{scenarioLabel(c.scenario)}</td>
                <td className="px-4 py-3">{c.verdict ? verdictLabel(c.verdict) : <span className="text-muted">în lucru</span>}</td>
                <td className="whitespace-nowrap px-4 py-3 font-medium"><StatusLine status={String(c.status)} requiresHuman={c.requires_human} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function NewCaseSheet({ onClose, onStart, busy }: { onClose: () => void; onStart: (id: string) => void; busy: boolean }) {
  const api = useApi();
  const scenarios = useResource(() => api.scenarios(), [api]);
  const [choice, setChoice] = useState<string>("demo_t1");
  return (
    <Sheet
      title="Contestație nouă"
      onClose={onClose}
      footer={<>
        <Button onClick={onClose}>Renunță</Button>
        <Button variant="primary" busy={busy} disabled={!choice} onClick={() => onStart(choice)}>Deschide și pornește cazul</Button>
      </>}
    >
      <p className="text-muted">Alege o situație sintetică. Cazul pornește imediat, iar agenții încep să strângă probele.</p>
      {scenarios.error && !scenarios.data ? (
        <div className="mt-4"><ErrorNote error={scenarios.error} what="scenariile" onRetry={scenarios.reload} /></div>
      ) : !scenarios.data ? (
        <div className="mt-4 flex flex-col gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : (
        <fieldset className="mt-4 flex flex-col gap-2">
          <legend className="sr-only">Situația</legend>
          {scenarios.data.map((s: ScenarioInfo) => (
            <label key={s.id} className={cx(
              "flex cursor-pointer gap-3 rounded-md border px-3 py-2.5",
              choice === s.id ? "border-ink bg-yellow-tint" : "border-line hover:bg-hover",
            )}>
              <input type="radio" name="scenario" value={s.id} checked={choice === s.id} onChange={() => setChoice(s.id)} className="mt-1 accent-ink" />
              <span className="min-w-0">
                <span className="block font-semibold">{s.title || scenarioLabel(s.id)}</span>
                {s.description && <span className="block text-[0.8667rem] text-muted">{s.description}</span>}
                {s.expected_verdict && <span className="mt-0.5 block text-[0.8667rem] text-ink-soft">Rezultat așteptat: {verdictLabel(String(s.expected_verdict))}</span>}
              </span>
            </label>
          ))}
        </fieldset>
      )}
    </Sheet>
  );
}
