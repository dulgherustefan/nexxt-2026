import { AlertTriangle, ArrowLeft, Check, FileCheck2, Hand, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { channelLabel, money, questionLabel, shortHash, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { CaseDetail, CounterfactualResult, Decision, Fact, FilterResult, LedgerResponse, VerifyResult } from "../../api/types";
import {
  Badge, Banner, Button, cx, DeadlineText, Dot, EmptyState, ErrorNote, IdTag, KeyValues, Panel, SectionBoundary, Skeleton, Tabs,
} from "../../ui/kit";
import { exactTime, scenarioLabel, StatusLine, StepList, useStepRows, verdictSentence } from "./caseUi";

type TabId = "probe" | "reguli" | "scrisoare";

const RELOAD_ON = new Set(["decision", "interrupt", "refund", "ledger_seal", "hold_signal", "wall_block", "diode"]);

export default function CasePage() {
  const { id = "" } = useParams();
  const api = useApi();
  const detail = useResource(() => api.caseDetail(id), [api, id], { pollMs: 2500 });
  const source = useMemo(() => api.caseEvents(id), [api, id]);
  const stream = useEventStream(source, id);
  const [tab, setTab] = useState<TabId>("probe");
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    const e = stream.last;
    if (!e) return;
    if (e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || (e.type === "CUSTOM" && RELOAD_ON.has(String(e.name)))) void detail.reload();
  }, [stream.last]); // eslint-disable-line react-hooks/exhaustive-deps

  const cite = (factId: string) => {
    setTab("probe");
    setFlash(factId);
    window.setTimeout(() => document.getElementById(`fact-${factId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  };

  const d = detail.data;
  if (detail.error && !d) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <ErrorNote error={detail.error} what={`cazul ${id}`} onRetry={detail.reload} />
      </div>
    );
  }
  if (!d) return <CaseSkeleton />;

  return (
    <div className="flex flex-col gap-5">
      <CaseHeader d={d} />
      {d.interrupt?.pending && <SignatureBanner d={d} caseId={id} onDone={detail.reload} />}
      {!d.interrupt?.pending && d.letter?.filter?.passed === false && (
        <Banner
          tone="danger"
          icon={<ShieldAlert className="size-5 text-danger" />}
          title="Zidul a oprit scrisoarea către client."
          actions={<Button onClick={() => { setTab("scrisoare"); document.getElementById("detalii")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>Vezi fraza oprită</Button>}
        >
          {d.letter.filter.blocked_terms?.length
            ? <>Conține {d.letter.filter.blocked_terms.map((t) => `„${t}”`).join(", ")}, ce nu are voie să ajungă la client. </>
            : <>Filtrul a găsit ceva ce nu are voie să ajungă la client. </>}
          Rambursarea nu e afectată; scrisoarea pleacă doar după ce un om o corectează.
        </Banner>
      )}
      <SectionBoundary label="Decizia"><DecisionPanel d={d} onCite={cite} onRules={() => setTab("reguli")} /></SectionBoundary>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_23.5rem]">
        <div id="detalii" className="min-w-0 scroll-mt-4">
          <Tabs<TabId>
            label="Detaliile cazului"
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "probe", label: "Probe", count: d.facts?.length ?? 0 },
              { id: "reguli", label: "Reguli și termene", count: d.rules?.hits?.length ?? 0 },
              { id: "scrisoare", label: "Scrisoarea către client" },
            ]}
          />
          <div className="pt-4">
            <SectionBoundary label={tab}>
              {tab === "probe" && <EvidenceTab facts={d.facts ?? []} flash={flash} />}
              {tab === "reguli" && <RulesTab d={d} />}
              {tab === "scrisoare" && <LetterTab d={d} caseId={id} onCite={cite} />}
            </SectionBoundary>
          </div>
        </div>
        <aside className="flex flex-col gap-4">
          <SectionBoundary label="Agenții"><LiveSteps d={d} events={stream.events} streamStatus={stream.status} /></SectionBoundary>
          <SectionBoundary label="Recuperare"><RecoveryPanel d={d} /></SectionBoundary>
          <SectionBoundary label="Schimbă un fapt"><CounterfactualPanel d={d} caseId={id} /></SectionBoundary>
          <SectionBoundary label="Dosar"><LedgerPanel caseId={id} sealed={Boolean(d.ledger?.sealed)} count={d.ledger?.count ?? d.facts?.length ?? 0} /></SectionBoundary>
          <SectionBoundary label="Reclamația"><ComplaintPanel d={d} /></SectionBoundary>
        </aside>
      </div>
      {detail.error && <p className="text-[0.8667rem] text-danger">Nu mai primesc actualizări de la server; afișez ultima stare primită.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- antet

function BackLink() {
  return (
    <Link to="/" className="inline-flex w-fit items-center gap-1.5 text-[0.9333rem] font-medium text-muted hover:text-ink">
      <ArrowLeft className="size-4" /> Contestații
    </Link>
  );
}

function CaseHeader({ d }: { d: CaseDetail }) {
  const s = d.summary;
  const deadline = d.clock?.t1_deadline ?? s.deadline;
  const closed = ["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"].includes(String(s.status));
  return (
    <div className="flex flex-col gap-3">
      <BackLink />
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-4">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-muted">
            <IdTag>{s.case_id}</IdTag>
            <span>{s.customer_alias}</span>
            <span aria-hidden>·</span>
            <span>{scenarioLabel(s.scenario)}</span>
          </p>
          <h1 className="mt-2 text-[2rem] font-bold leading-tight tabular-nums">
            {money(s.amount)} <span className="font-semibold text-muted">· {channelLabel(s.channel)}</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-[0.8667rem] text-muted">Stare</p>
            <p className="font-semibold"><StatusLine status={String(s.status)} requiresHuman={s.requires_human} /></p>
          </div>
          <div>
            <p className="text-[0.8667rem] text-muted">Termen T+1 · {exactTime(deadline)}</p>
            <p className="text-[1.25rem] font-bold"><DeadlineText deadline={deadline} done={closed} /></p>
          </div>
        </div>
      </div>
    </div>
  );
}

function CaseSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Se încarcă cazul">
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-12 w-96 max-w-full" />
      <Skeleton className="h-36" />
      <div className="grid gap-4 xl:grid-cols-[1fr_23.5rem]"><Skeleton className="h-80" /><Skeleton className="h-80" /></div>
    </div>
  );
}

// ---------------------------------------------------------------- semnătura

const SIGN_COPY: Record<string, { yes: string; no: string; consequence: string }> = {
  RAMBURSEAZA_CU_APROBARE: { yes: "Aprobă rambursarea", no: "Nu aprob", consequence: "La aprobare, motorul de reguli emite imediat instrucțiunea de rambursare." },
  RESPINGE_TARDIV: { yes: "Confirm respingerea", no: "Nu confirm, rambursăm", consequence: "Clientul primește o scrisoare de respingere cu temeiul legal și căile de atac." },
  EXCEPTIE_FRAUDA_CLIENT: { yes: "Confirm excepția", no: "Nu confirm, rambursăm", consequence: "Nu rambursăm acum. Folosește excepția doar dacă autoritatea a fost notificată." },
};

function SignatureBanner({ d, caseId, onDone }: { d: CaseDetail; caseId: string; onDone: () => Promise<void> }) {
  const api = useApi();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const it = d.interrupt!;
  const copy = SIGN_COPY[String(it.verdict)] ?? { yes: "Aprobă", no: "Respinge", consequence: "Decizia se aplică imediat." };
  const locked = Boolean(it.resuming) || busy !== null;
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
    <Banner
      tone="now"
      icon={<Hand aria-hidden className="size-5" />}
      title={it.prompt ?? "Decizia cere semnătura ta."}
      actions={<>
        <Button variant="primary" busy={busy === "approve"} disabled={locked} onClick={() => act("approve")}>{copy.yes}</Button>
        <Button busy={busy === "reject"} disabled={locked} onClick={() => act("reject")}>{copy.no}</Button>
      </>}
    >
      {it.resuming ? "Semnătura a fost primită; aplic decizia…" : copy.consequence}
      {it.rule_ids?.length ? <span className="ml-1">Reguli: {it.rule_ids.join(", ")}.</span> : null}
      {error && <span className="mt-1 block font-semibold text-danger">{error}</span>}
    </Banner>
  );
}

// ---------------------------------------------------------------- decizia

function Cites({ ids, onCite }: { ids?: string[]; onCite: (id: string) => void }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((c) => <IdTag key={c} onClick={() => onCite(c)} title={`Arată proba ${c}`}>{c}</IdTag>)}
    </span>
  );
}

function DecisionPanel({ d, onCite, onRules }: { d: CaseDetail; onCite: (id: string) => void; onRules: () => void }) {
  const decisions = d.decisions ?? [];
  const t1 = decisions.find((x) => x.question === "rambursare_t1");
  const sentence = verdictSentence(t1, d.summary.amount, {
    status: String(d.summary.status),
    action: d.interrupt?.pending ? undefined : d.interrupt?.answer?.action,
    approver: d.interrupt?.answer?.approver,
  });
  const others = decisions.filter((x) => x.question !== "rambursare_t1");
  const frame = sentence.tone === "danger" ? "border-danger-line" : sentence.tone === "now" ? "border-ink" : "border-line";
  return (
    <section aria-label="Decizia" className={cx("rounded-lg border bg-paper", frame)}>
      <div className="flex flex-wrap items-start justify-between gap-4 px-5 pt-5">
        <div className="min-w-0 max-w-[72ch]">
          <p className="flex items-center gap-2 text-[0.8667rem] font-semibold text-muted">
            {t1 ? <><FileCheck2 className="size-4" /> Decizia motorului de reguli{t1.decided_by === "rules+human" ? " · cu semnătură umană" : ""}</> : <><Dot tone="now" live /> În lucru</>}
          </p>
          <h2 className="mt-1.5 text-[1.45rem] font-bold leading-snug">{sentence.title}</h2>
          <p className="mt-1 text-ink-soft">{sentence.detail}</p>
        </div>
        {t1?.rule_ids?.length ? (
          <div className="flex max-w-[22rem] flex-wrap items-center gap-1.5" aria-label="Regulile aplicate">
            {t1.rule_ids.slice(0, 4).map((r) => <IdTag key={r}>{r}</IdTag>)}
            {t1.rule_ids.length > 4 && (
              <button type="button" onClick={onRules} className="text-[0.8667rem] font-medium text-muted underline hover:text-ink">
                +{t1.rule_ids.length - 4} reguli
              </button>
            )}
          </div>
        ) : null}
      </div>

      {t1?.rationale?.length ? (
        <ul className="mt-4 flex flex-col gap-2 px-5">
          {t1.rationale.slice(0, 4).map((line, i) => (
            <li key={i} className="flex gap-2.5">
              <Check aria-hidden className="mt-1 size-4 shrink-0 text-ok" />
              <p className="min-w-0">{line.text}<Cites ids={line.cites} onCite={onCite} /></p>
            </li>
          ))}
        </ul>
      ) : !t1 ? (
        <div className="mt-4 flex flex-col gap-2 px-5"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
      ) : null}

      {others.length > 0 && (
        <div className="mt-4 grid border-t border-line sm:grid-cols-3">
          {others.map((o: Decision) => (
            <div key={o.question} className="border-line px-5 py-3 sm:border-r sm:last:border-r-0">
              <p className="text-[0.8667rem] text-muted">{questionLabel(o.question)}</p>
              <p className="mt-0.5 font-semibold">{verdictLabel(o.decision)}</p>
              <p className="mt-0.5 font-mono text-[0.8rem] text-muted">{o.rule_ids?.slice(0, 3).join(" · ")}</p>
            </div>
          ))}
        </div>
      )}
      {d.debate?.ran && <DebateDetails d={d} onCite={onCite} />}
    </section>
  );
}

function DebateDetails({ d, onCite }: { d: CaseDetail; onCite: (id: string) => void }) {
  const debate = d.debate!;
  const rec = debate.recommendation ? verdictLabel(String(debate.recommendation)) : "—";
  return (
    <details className="group border-t border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 font-semibold hover:bg-hover">
        <span>Cerem banii de la client? Argumentele pentru și contra: {rec.toLowerCase()}</span>
        <span className="text-[0.8667rem] font-normal text-muted group-open:hidden">Arată</span>
      </summary>
      <div className="grid gap-5 px-5 pb-5 lg:grid-cols-2">
        <Arguments title="Pentru recuperare (Procuror)" model={debate.models?.procuror} lines={debate.prosecutor} onCite={onCite} />
        <Arguments title="Pentru client (Avocat)" model={debate.models?.avocat} lines={debate.defender} onCite={onCite} />
        {debate.rubric?.length ? (
          <div className="lg:col-span-2">
            <p className="mb-2 font-semibold">Rubrica deterministă (decide omul, nu modelul)</p>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {debate.rubric.map((r) => (
                <li key={r.indicator} className="flex items-start gap-2">
                  {r.value ? <Check className="mt-1 size-4 shrink-0" /> : <X className="mt-1 size-4 shrink-0 text-subtle" />}
                  <span className={cx(!r.value && "text-muted")}>{r.indicator} <span className="tabular-nums text-muted">({r.weight > 0 ? "+" : ""}{r.weight})</span></span>
                </li>
              ))}
            </ul>
            {typeof debate.rejected_without_citation === "number" && (
              <p className="mt-2 text-[0.8667rem] text-muted">{debate.rejected_without_citation} afirmații fără sursă au fost respinse automat.</p>
            )}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function Arguments({ title, model, lines, onCite }: { title: string; model?: string; lines?: Array<{ text: string; cites?: string[] }>; onCite: (id: string) => void }) {
  return (
    <div>
      <p className="font-semibold">{title}{model && <span className="ml-2 text-[0.8rem] font-normal text-muted">{model.replace("anthropic.", "")}</span>}</p>
      {lines?.length ? (
        <ul className="mt-2 flex flex-col gap-2">
          {lines.map((l, i) => <li key={i} className="text-ink-soft">{l.text}<Cites ids={l.cites} onCite={onCite} /></li>)}
        </ul>
      ) : <p className="mt-2 text-muted">Fără argumente.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- probe

function trustLabel(f: Fact): ReactNode {
  return f.labels?.trust === "untrusted"
    ? <span className="inline-flex items-center gap-1.5"><AlertTriangle className="size-3.5 text-danger" /> neîncrezut</span>
    : <span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-ok" /> sistemele băncii</span>;
}

function EvidenceTab({ facts, flash }: { facts: Fact[]; flash: string | null }) {
  if (!facts.length) return <EmptyState title="Nicio probă încă.">Colectorii scriu probele aici pe măsură ce le găsesc, fiecare cu sursă, oră și hash.</EmptyState>;
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full table-fixed border-collapse text-left sm:min-w-[36rem]">
        <thead>
          <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
            <th scope="col" className="w-24 px-3 py-2.5 font-semibold">ID</th>
            <th scope="col" className="px-3 py-2.5 font-semibold">Ce arată și de unde vine</th>
            <th scope="col" className="hidden w-40 px-3 py-2.5 font-semibold sm:table-cell">Încredere</th>
            <th scope="col" className="hidden w-28 px-3 py-2.5 font-semibold sm:table-cell">Hash</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((f) => (
            <tr key={f.fact_id} id={`fact-${f.fact_id}`} className={cx("border-b border-line align-top last:border-b-0", flash === f.fact_id && "animate-flash")}>
              <td className="px-3 py-2.5"><IdTag>{f.fact_id}</IdTag></td>
              <td className="px-3 py-2.5">
                <p>{f.summary || f.kind}</p>
                <p className="mt-0.5 truncate font-mono text-[0.8rem] text-muted" title={f.source_tool}>{f.source_tool}</p>
                <p className="mt-1 text-[0.8667rem] sm:hidden">{trustLabel(f)}</p>
              </td>
              <td className="hidden px-3 py-2.5 text-[0.8667rem] whitespace-nowrap sm:table-cell">{trustLabel(f)}</td>
              <td className="hidden px-3 py-2.5 font-mono text-[0.8rem] text-muted sm:table-cell" title={f.sha256}>{shortHash(f.sha256, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- reguli și termene

const CONFIDENCE: Record<string, string> = { P: "text oficial", S: "sursă secundară", U: "parametru neverificat", V: "verificat" };

function RulesTab({ d }: { d: CaseDetail }) {
  const hits = d.rules?.hits ?? [];
  const deadlines = d.rules?.deadlines ?? [];
  if (!hits.length && !deadlines.length) return <EmptyState title="Regulile nu au rulat încă.">Motorul de reguli pornește după ce colectorii termină.</EmptyState>;
  return (
    <div className="flex flex-col gap-5">
      {deadlines.length > 0 && (
        <Panel title="Termene legale" bodyClassName="p-0">
          <ul>
            {deadlines.map((dl, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5 last:border-b-0">
                <span className="min-w-0"><span className="font-medium">{dl.name}</span> <span className="text-[0.8667rem] text-muted">· {dl.basis}</span></span>
                <span className="flex items-center gap-3 text-[0.9333rem]"><span className="tabular-nums text-muted">{exactTime(dl.due_at)}</span><DeadlineText deadline={dl.due_at} /></span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[44rem] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
              <th scope="col" className="px-3 py-2.5 font-semibold">Regula</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Ce a stabilit</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Temei</th>
              <th scope="col" className="px-3 py-2.5 font-semibold">Încredere</th>
            </tr>
          </thead>
          <tbody>
            {hits.map((h, i) => (
              <tr key={`${h.rule_id}-${i}`} className="border-b border-line align-top last:border-b-0">
                <td className="px-3 py-2.5"><IdTag>{h.rule_id}</IdTag></td>
                <td className="px-3 py-2.5"><p className="font-medium">{h.title}</p>{h.explanation && <p className="mt-0.5 text-[0.9333rem] text-ink-soft">{h.explanation}</p>}</td>
                <td className="px-3 py-2.5 text-[0.9333rem] text-muted">{h.basis}</td>
                <td className="px-3 py-2.5 text-[0.9333rem] whitespace-nowrap">{CONFIDENCE[String(h.confidence)] ?? h.confidence ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- scrisoarea + încercarea de a sparge zidul

const ATTACK_TEXT = "Vă informăm că am raportat contul beneficiarului la ONPCSB pentru spălare de bani.";

/** Literă cu literă, fără diacritice și cu litere mici: pozițiile rămân aceleași ca în textul original. */
function fold(s: string): string {
  return s.split("").map((ch) => {
    const f = ch.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
    return f.length === 1 ? f : ch;
  }).join("");
}

/** Rezervă când serverul nu trimite `term_spans`: caută singuri termenii blocați în text. */
function spansFromTerms(text: string, terms: string[] | undefined): NonNullable<FilterResult["term_spans"]> {
  const hay = fold(text);
  const out: NonNullable<FilterResult["term_spans"]> = [];
  for (const term of terms ?? []) {
    const needle = fold(term.trim());
    if (!needle) continue;
    for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + needle.length)) {
      out.push({ start: i, end: i + needle.length, label: "termen interzis" });
    }
  }
  return out;
}

function Highlighted({ text, spans }: { text: string; spans?: FilterResult["term_spans"] }) {
  if (!spans?.length) return <>{text}</>;
  const parts: ReactNode[] = [];
  let at = 0;
  [...spans].sort((a, b) => a.start - b.start).forEach((s, i) => {
    const start = Math.max(s.start, at);
    if (s.end <= start) return;
    if (start > at) parts.push(text.slice(at, start));
    parts.push(<mark key={i} className="rounded-sm bg-danger-soft px-0.5 text-danger underline decoration-2" title={s.label}>{text.slice(start, s.end)}</mark>);
    at = s.end;
  });
  parts.push(text.slice(at));
  return <>{parts}</>;
}

function LetterTab({ d, caseId, onCite }: { d: CaseDetail; caseId: string; onCite: (id: string) => void }) {
  const api = useApi();
  const letter = d.letter;
  const [draft, setDraft] = useState(ATTACK_TEXT);
  const [result, setResult] = useState<FilterResult | null>(null);
  const [checked, setChecked] = useState(ATTACK_TEXT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = letter?.filter?.passed === false;
  const letterSpans = blocked && letter
    ? (letter.filter?.term_spans?.length ? letter.filter.term_spans : spansFromTerms(letter.body, letter.filter?.blocked_terms))
    : undefined;
  function editLetter() {
    if (!letter) return;
    setDraft(letter.body);
    setResult(null);
    window.setTimeout(() => {
      const box = document.getElementById("attack") as HTMLTextAreaElement | null;
      box?.scrollIntoView({ behavior: "smooth", block: "center" });
      box?.focus({ preventScroll: true });
    }, 60);
  }
  async function check() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.letterCheck(caseId, { body: draft }));
      setChecked(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verificarea nu a răspuns.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      {!letter ? (
        <EmptyState title="Scrisoarea nu e gata.">Redactorul o scrie după decizie și după recuperare, apoi o trece prin filtrul zidului.</EmptyState>
      ) : (
        <Panel
          title={letter.subject}
          actions={blocked
            ? <Badge tone="danger" icon={<ShieldAlert className="size-3.5" />}>Blocată de zid</Badge>
            : <Badge tone="ok" icon={<ShieldCheck className="size-3.5" />}>A trecut filtrul zidului</Badge>}
        >
          {blocked && (
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3 rounded-md border border-danger-line bg-danger-soft px-4 py-3">
              <div className="min-w-[16rem] flex-1">
                <p className="font-semibold">Scrisoarea nu pleacă: fraza marcată mai jos e interzisă.</p>
                {letter.filter?.reasons?.[0] && <p className="mt-1 text-[0.9333rem] text-ink-soft">{letter.filter.reasons[0]}</p>}
              </div>
              <Button onClick={editLetter}>Corectează și verifică din nou</Button>
            </div>
          )}
          <div className="max-w-[72ch] whitespace-pre-wrap leading-relaxed"><Highlighted text={letter.body} spans={letterSpans} /></div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-3 text-[0.9333rem]">
            {(letter.cmp_checks ?? []).map((c) => (
              <span key={c.rule_id} className="inline-flex items-center gap-1.5">
                {c.outcome.toLowerCase().includes("missing") || c.outcome.toLowerCase().includes("unanswered")
                  ? <X className="size-4 text-danger" /> : <Check className="size-4 text-ok" />}
                <IdTag>{c.rule_id}</IdTag>
                {c.rule_id === "CMP-01" ? "răspunde la fiecare punct" : c.rule_id === "CMP-03" ? "include ANPC, ANAF, BNR și CSALB" : c.outcome}
              </span>
            ))}
            {letter.cites?.length ? <span className="inline-flex items-center gap-1.5 text-muted">Se sprijină pe <Cites ids={letter.cites.slice(0, 6)} onCite={onCite} /></span> : null}
          </div>
        </Panel>
      )}

      <Panel title="Verifică un text prin zid">
        <p className="text-ink-soft">Corectează scrisoarea aici sau încearcă să strecori o referire la o investigație AML. Filtrul verifică termenii interziși, tokenurile canary și datele personale.</p>
        <label htmlFor="attack" className="sr-only">Textul de verificat</label>
        <textarea id="attack" value={draft} onChange={(e) => setDraft(e.target.value)} rows={Math.min(16, Math.max(3, Math.ceil(draft.length / 90) + draft.split("\n").length - 1))}
          className="mt-3 w-full rounded-md border border-line-strong bg-paper px-3 py-2 focus:border-ink" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" busy={busy} onClick={check} disabled={!draft.trim()}>Verifică textul</Button>
          {error && <span className="text-danger">{error}</span>}
        </div>
        {result && (
          <div className={cx("mt-4 rounded-md border px-4 py-3", result.passed ? "border-ok-line bg-ok-soft" : "border-danger-line bg-danger-soft")} role="status">
            <p className="flex items-center gap-2 font-semibold">
              {result.passed ? <><ShieldCheck className="size-4 text-ok" /> Textul poate pleca: nimic interzis.</> : <><ShieldAlert className="size-4 text-danger" /> Blocat: textul nu pleacă, merge la un om.</>}
            </p>
            {!result.passed && <p className="mt-2 leading-relaxed"><Highlighted text={checked} spans={result.term_spans?.length ? result.term_spans : spansFromTerms(checked, result.blocked_terms)} /></p>}
            {result.reasons?.length ? <ul className="mt-2 list-disc pl-5 text-[0.9333rem]">{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : null}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------- coloana din dreapta

function LiveSteps({ d, events, streamStatus }: { d: CaseDetail; events: Parameters<typeof useStepRows>[1]; streamStatus: string }) {
  const rows = useStepRows(d.pipeline?.nodes, events);
  const lastRun = [...events].reverse().find((e) => e.type === "RUN_STARTED" || e.type === "RUN_FINISHED" || e.type === "RUN_ERROR");
  // la o semnătură în așteptare rularea e doar în pauză: pașii de după ea nu sunt „nu e cazul”
  const settled = !d.interrupt?.pending && (lastRun ? lastRun.type !== "RUN_STARTED" : Boolean(d.ledger?.sealed));
  return (
    <div>
      <StepList rows={rows} settled={settled} />
      {(streamStatus === "reconnecting" || streamStatus === "closed") && (
        <p className="mt-1.5 text-[0.8rem] text-muted">Fluxul live s-a întrerupt; actualizez la câteva secunde.</p>
      )}
    </div>
  );
}

const RECALL_KIND: Record<string, string> = {
  interna: "Rechemare internă (beneficiarul are cont la Banca Demo)",
  "camt.056": "Rechemare SEPA camt.056, motiv FRAD",
  rechemare_ron: "Rechemare către banca beneficiarului (RON)",
};

function RecoveryPanel({ d }: { d: CaseDetail }) {
  const r = d.recovery;
  const escroc = d.decisions?.find((x) => x.question === "recuperare_escroc");
  if (!escroc && !r?.chargeback && !r?.recall && !r?.dnsc_report && !d.aml_referral?.status) return null;
  return (
    <Panel title="Recuperarea banilor">
      <div className="flex flex-col gap-3">
        {escroc && <p><span className="font-semibold">{verdictLabel(escroc.decision)}</span> <span className="font-mono text-[0.8rem] text-muted">{escroc.rule_ids?.join(" · ")}</span></p>}
        {r?.chargeback && (
          <p className="text-[0.9333rem]">
            <span className="font-medium">Chargeback: </span>
            {r.chargeback.eligible ? `posibil, cod ${r.chargeback.reason_code ?? "—"}` : "nu e posibil"}
            {r.chargeback.explanation && <span className="block text-muted">{r.chargeback.explanation}</span>}
          </p>
        )}
        {r?.recall && (
          <div className="text-[0.9333rem]">
            <p className="font-medium">{RECALL_KIND[String(r.recall.kind)] ?? r.recall.kind}</p>
            {r.recall.note && <p className="text-muted">{r.recall.note}</p>}
            {r.recall.xml && (
              <details className="mt-1.5">
                <summary className="cursor-pointer font-medium underline">Mesajul camt.056 (ciornă)</summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-canvas p-3 text-[0.75rem] leading-snug">{r.recall.xml}</pre>
              </details>
            )}
          </div>
        )}
        {r?.dnsc_report && (
          <details className="text-[0.9333rem]">
            <summary className="cursor-pointer font-medium underline">Raport de phishing pentru DNSC (ciornă)</summary>
            <p className="mt-2 font-semibold">{r.dnsc_report.title}</p>
            <p className="mt-1 whitespace-pre-wrap text-ink-soft">{r.dnsc_report.text}</p>
          </details>
        )}
        {d.aml_referral?.status && (
          <p className="border-t border-line pt-3 text-[0.9333rem] text-muted">
            Faptele despre atac au plecat spre zona AML, într-un singur sens ({d.aml_referral.status}). Victima apare acolo doar ca <span className="font-mono">{d.aml_referral.victim_ref}</span>.
          </p>
        )}
        <p className="text-[0.8667rem] text-muted">Toate sunt ciorne: le trimite un om.</p>
      </div>
    </Panel>
  );
}

function CounterfactualPanel({ d, caseId }: { d: CaseDetail; caseId: string }) {
  const api = useApi();
  const current = Boolean(d.rule_context?.screen_showed_amount_and_payee);
  const [result, setResult] = useState<CounterfactualResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!d.rule_context) return null;
  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.counterfactual(caseId, { field: "screen_showed_amount_and_payee", value: !current }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nu am putut recalcula.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Schimbă un fapt">
      <p className="text-[0.9333rem] text-ink-soft">
        Acum: ecranul de autentificare {current ? "a afișat" : "nu a afișat"} suma și beneficiarul. Ce s-ar schimba dacă {current ? "nu le-ar fi afișat" : "le-ar fi afișat"}?
      </p>
      <Button className="mt-3" size="sm" busy={busy} onClick={run}>Recalculează cu faptul schimbat</Button>
      {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}</p>}
      {result && (
        <div className="mt-3 flex flex-col gap-2">
          <ul className="flex flex-col gap-1.5 text-[0.9333rem]">
            {result.after.map((a) => {
              const b = result.before.find((x) => x.question === a.question);
              const changed = result.changed.includes(a.question);
              return (
                <li key={a.question} className={cx("rounded-md px-2.5 py-1.5", changed ? "bg-yellow-soft" : "bg-canvas")}>
                  <span className="text-muted">{questionLabel(a.question)}: </span>
                  {changed ? <><s className="text-muted">{verdictLabel(b?.decision)}</s> <span className="font-semibold">{verdictLabel(a.decision)}</span></> : <span>{verdictLabel(a.decision)}, neschimbat</span>}
                </li>
              );
            })}
          </ul>
          <p className="text-[0.9333rem]">{result.explanation}</p>
        </div>
      )}
    </Panel>
  );
}

function LedgerPanel({ caseId, sealed, count }: { caseId: string; sealed: boolean; count: number }) {
  const api = useApi();
  const [ledger, setLedger] = useState<LedgerResponse | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function check() {
    setBusy(true);
    setError(null);
    try {
      const l = await api.ledger(caseId);
      setLedger(l);
      setVerify(l.seal ? await api.verify({ case_id: caseId, facts: l.facts, seal: l.seal }) : l.verify);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verificarea nu a răspuns.");
    } finally {
      setBusy(false);
    }
  }
  const qr = ledger?.seal?.qr_svg;
  return (
    <Panel title="Dosarul de probe">
      <KeyValues rows={[
        ["Probe", <span className="tabular-nums">{count}</span>],
        ["Sigilat", sealed ? "da, Merkle + Ed25519" : "încă nu (la final)"],
        ledger?.seal ? ["Rădăcina", <span className="font-mono text-[0.8rem]" title={ledger.seal.root}>{shortHash(ledger.seal.root, 12)}</span>] : null,
      ]} />
      <Button className="mt-3" size="sm" busy={busy} onClick={check}>Verifică integritatea</Button>
      {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}</p>}
      {verify && (
        <div className="mt-3">
          <p className={cx("flex items-center gap-2 font-semibold", verify.valid ? "text-ok" : "text-danger")}>
            {verify.valid ? <><ShieldCheck className="size-4" /> Dosar intact</> : <><ShieldAlert className="size-4" /> {sealed ? "Nu se verifică" : "Nesigilat încă"}</>}
          </p>
          <ul className="mt-1.5 flex flex-col gap-1 text-[0.8667rem]">
            {verify.checks.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">{c.ok ? <Check className="mt-0.5 size-3.5 shrink-0 text-ok" /> : <X className="mt-0.5 size-3.5 shrink-0 text-danger" />}<span>{c.name}</span></li>
            ))}
          </ul>
          {qr && <img className="mt-3 size-28" alt="Cod QR cu rădăcina semnată a dosarului" src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} />}
        </div>
      )}
    </Panel>
  );
}

function ComplaintPanel({ d }: { d: CaseDetail }) {
  const c = d.complaint;
  if (!c) return null;
  const injection = d.extracted?.injection_suspected;
  return (
    <Panel title="Reclamația clientului">
      {injection && (
        <p className="mb-3 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-[0.9333rem] text-danger">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" /> Conține instrucțiuni către sistem. Au fost tratate ca date și ignorate.
        </p>
      )}
      <details>
        <summary className="cursor-pointer list-none">
          <p className="line-clamp-3 text-ink-soft">{c.text}</p>
          <span className="mt-1 inline-block text-[0.8667rem] font-medium underline">Arată tot</span>
        </summary>
        <p className="mt-2 whitespace-pre-wrap text-ink-soft">{c.text}</p>
        {c.attachments?.map((a, i) => (
          <div key={i} className="mt-3 rounded-md bg-canvas px-3 py-2 text-[0.9333rem]">
            <p className="text-[0.8rem] font-semibold text-muted">{a.kind === "sms" ? "SMS primit" : a.kind}</p>
            <p className="whitespace-pre-wrap">{a.content}</p>
          </div>
        ))}
      </details>
      {d.extracted?.points?.length ? (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-[0.8667rem] font-semibold text-muted">Ce cere clientul</p>
          <ul className="mt-1 list-disc pl-5 text-[0.9333rem]">{d.extracted.points.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
        </div>
      ) : null}
    </Panel>
  );
}
