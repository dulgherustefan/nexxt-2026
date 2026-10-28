import {
  ArrowLeft,
  Check,
  CheckCircle,
  Gavel,
  SealCheck,
  SealWarning,
  ShieldCheck,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { channelLabel, dateTime, hasAmount, money, questionLabel, shortHash, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { CaseDetail, CounterfactualResult, Decision, Fact, FilterResult, LedgerResponse, VerifyResult } from "../../api/types";
import {
  Badge, Banner, Button, cx, DeadlineText, EmptyState, ErrorNote, IdTag, KeyValues, Panel, SectionBoundary, Skeleton, Status, Tabs,
} from "../../ui/kit";
import { AgentStatus, scenarioLabel, Sheet, StatusLine, StepList, useStepRows, verdictSentence } from "./caseUi";

type TabId = "evidence" | "rules" | "letter";

const RELOAD_ON = new Set(["decision", "interrupt", "refund", "ledger_seal", "hold_signal", "wall_block", "diode"]);

export default function CasePage() {
  const { id = "" } = useParams();
  const api = useApi();
  const detail = useResource(() => api.caseDetail(id), [api, id], { pollMs: 2500 });
  const source = useMemo(() => api.caseEvents(id), [api, id]);
  const stream = useEventStream(source, id);
  const [tab, setTab] = useState<TabId>("evidence");
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    const e = stream.last;
    if (!e) return;
    if (e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || (e.type === "CUSTOM" && RELOAD_ON.has(String(e.name)))) void detail.reload();
  }, [stream.last]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = `${id} · VersoML`;
  }, [id]);

  const cite = (factId: string) => {
    setTab("evidence");
    setFlash(factId);
    window.setTimeout(() => document.getElementById(`fact-${factId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  };

  const d = detail.data;
  if (detail.error && !d) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <ErrorNote error={detail.error} what={`case ${id}`} onRetry={detail.reload} />
      </div>
    );
  }
  if (!d) return <CaseSkeleton />;

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader d={d} />
      {d.interrupt?.pending && <SignatureBanner d={d} caseId={id} onDone={detail.reload} />}
      {!d.interrupt?.pending && d.letter?.filter?.passed === false && (
        <Banner
          tone="danger"
          icon={<Warning size={20} className="text-danger" />}
          title="The letter check stopped the letter to the customer."
          actions={<Button onClick={() => { setTab("letter"); document.getElementById("details")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>See what was stopped</Button>}
        >
          {d.letter.filter.blocked_terms?.length
            ? <>It contains {d.letter.filter.blocked_terms.map((t) => `“${t}”`).join(", ")}, which can’t go to the customer. </>
            : <>The check found something that can’t go to the customer. </>}
          The refund isn’t affected. The letter only goes out after a person fixes it.
        </Banner>
      )}
      <SectionBoundary label="Decision"><DecisionPanel d={d} onCite={cite} onRules={() => setTab("rules")} /></SectionBoundary>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22.5rem]">
        <div id="details" className="min-w-0 scroll-mt-4">
          <Tabs<TabId>
            label="Case details"
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "evidence", label: "Evidence", count: d.facts?.length ?? 0 },
              { id: "rules", label: "Rules and deadlines", count: d.rules?.hits?.length ?? 0 },
              { id: "letter", label: "Letter to the customer" },
            ]}
          />
          <div className="pt-5">
            <SectionBoundary label={tab}>
              {tab === "evidence" && <EvidenceTab facts={d.facts ?? []} flash={flash} />}
              {tab === "rules" && <RulesTab d={d} />}
              {tab === "letter" && <LetterTab d={d} caseId={id} onCite={cite} />}
            </SectionBoundary>
          </div>
        </div>
        <aside className="flex flex-col gap-4">
          <SectionBoundary label="Agents"><LiveSteps d={d} events={stream.events} streamStatus={stream.status} /></SectionBoundary>
          <SectionBoundary label="Recovery"><RecoveryPanel d={d} /></SectionBoundary>
          <SectionBoundary label="Change a fact"><CounterfactualPanel d={d} caseId={id} /></SectionBoundary>
          <SectionBoundary label="Evidence file"><LedgerPanel caseId={id} sealed={Boolean(d.ledger?.sealed)} count={d.ledger?.count ?? d.facts?.length ?? 0} /></SectionBoundary>
          <SectionBoundary label="Customer's message"><ComplaintPanel d={d} /></SectionBoundary>
        </aside>
      </div>
      {detail.error && <p className="text-[0.8667rem] text-danger">Updates from the server stopped. Showing the last state received.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- header

function BackLink() {
  return (
    <Link to="/cases" className="inline-flex w-fit items-center gap-1.5 rounded-md text-[0.9333rem] font-medium text-muted transition-colors hover:text-ink">
      <ArrowLeft size={16} /> Cases
    </Link>
  );
}

function CaseHeader({ d }: { d: CaseDetail }) {
  const s = d.summary;
  const deadline = d.clock?.t1_deadline ?? s.deadline;
  const closed = ["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"].includes(String(s.status));
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9333rem] text-muted">
            <span className="font-medium text-ink-soft">{s.customer_alias}</span>
            <span aria-hidden>·</span>
            <span>{scenarioLabel(s.scenario)}</span>
            <span aria-hidden>·</span>
            <span className="id-text text-[0.8667rem] text-subtle">{s.case_id}</span>
          </p>
          <h1 className="mt-1.5 text-[2.1rem] leading-tight font-semibold tracking-[-0.03em]">
            {hasAmount(s.amount) ? (
              <>{money(s.amount)} <span className="font-normal text-subtle">{channelLabel(s.channel).toLowerCase()}</span></>
            ) : (
              <>
                <span className="sr-only">Loading the payment</span>
                <span aria-hidden className="inline-block h-[0.9em] w-56 animate-pulse rounded-md bg-hover align-[-0.12em]" />
              </>
            )}
          </h1>
        </div>
        <dl className="flex flex-wrap items-end gap-x-10 gap-y-3">
          <div>
            <dt className="text-[0.8rem] text-muted">Status</dt>
            <dd className="mt-1 text-[0.9333rem] font-medium"><StatusLine status={String(s.status)} requiresHuman={s.requires_human} /></dd>
          </div>
          <div>
            <dt className="text-[0.8rem] text-muted">Refund due {deadline ? `· ${dateTime(deadline)}` : ""}</dt>
            <dd className="mt-1 text-[1.05rem] font-medium"><DeadlineText deadline={deadline} done={closed} /></dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function CaseSkeleton() {
  return (
    <div className="flex flex-col gap-5" role="status" aria-label="Loading the case">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-10 w-80 max-w-full" />
      <Skeleton className="h-40 rounded-2xl" />
      <div className="grid gap-5 xl:grid-cols-[1fr_22.5rem]"><Skeleton className="h-80 rounded-2xl" /><Skeleton className="h-80 rounded-2xl" /></div>
    </div>
  );
}

// ---------------------------------------------------------------- signature

const SIGN_COPY: Record<string, { yes: string; no: string; consequence: string }> = {
  RAMBURSEAZA_CU_APROBARE: { yes: "Approve refund", no: "Decline", consequence: "When you approve, the rules engine issues the refund right away." },
  RESPINGE_TARDIV: { yes: "Confirm rejection", no: "Don’t confirm, refund", consequence: "The customer gets a rejection letter with the legal basis and how to appeal." },
  EXCEPTIE_FRAUDA_CLIENT: { yes: "Confirm exception", no: "Don’t confirm, refund", consequence: "No refund for now. Only use this if the authorities have been notified." },
};

function SignatureBanner({ d, caseId, onDone }: { d: CaseDetail; caseId: string; onDone: () => Promise<void> }) {
  const api = useApi();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const it = d.interrupt!;
  const copy = SIGN_COPY[String(it.verdict)] ?? { yes: "Approve", no: "Decline", consequence: "The decision applies right away." };
  const locked = Boolean(it.resuming) || busy !== null;
  async function act(action: "approve" | "reject") {
    setBusy(action);
    setError(null);
    try {
      await api.approve(caseId, { action, approver: "OPERATOR-01" });
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The signature wasn’t recorded");
    } finally {
      setBusy(null);
    }
  }
  return (
    <Banner
      tone="now"
      title={it.prompt ?? "This decision needs your approval."}
      actions={<>
        <Button busy={busy === "reject"} disabled={locked} onClick={() => act("reject")}>{copy.no}</Button>
        <Button variant="primary" busy={busy === "approve"} disabled={locked} onClick={() => act("approve")}>{copy.yes}</Button>
      </>}
    >
      {it.resuming ? "Signature received. Applying the decision…" : copy.consequence}
      {it.rule_ids?.length ? <span className="ml-1 text-muted">Rules: {it.rule_ids.join(", ")}.</span> : null}
      {error && <span className="mt-1 block font-medium text-danger">{error}.</span>}
    </Banner>
  );
}

// ---------------------------------------------------------------- decision

function Cites({ ids, onCite }: { ids?: string[]; onCite: (id: string) => void }) {
  if (!ids?.length) return null;
  return (
    <span className="ml-1.5 inline-flex flex-wrap gap-1 align-baseline">
      {ids.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onCite(c)}
          title={`Show evidence ${c}`}
          className="id-text rounded text-[0.7667rem] text-subtle underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink"
        >
          {c}
        </button>
      ))}
    </span>
  );
}

/** Who still has to sign, or who signed: "rules+human" only says a person must sign off. */
function signOff(refund: Decision, d: CaseDetail): string {
  const approver = d.interrupt?.pending ? undefined : d.interrupt?.answer?.approver;
  if (approver) return ` · signed by ${approver}`;
  if (refund.decided_by === "rules+human" || refund.requires_human) return d.interrupt?.pending ? " · waiting for your signature" : " · a person signs off";
  return "";
}

function DecisionPanel({ d, onCite, onRules }: { d: CaseDetail; onCite: (id: string) => void; onRules: () => void }) {
  const decisions = d.decisions ?? [];
  const refund = decisions.find((x) => x.question === "rambursare_t1");
  const sentence = verdictSentence(refund, d.summary.amount, {
    status: String(d.summary.status),
    action: d.interrupt?.pending ? undefined : d.interrupt?.answer?.action,
    approver: d.interrupt?.answer?.approver,
  });
  const others = decisions.filter((x) => x.question !== "rambursare_t1" && x.question !== "pista_aml" && x.question !== "rts");
  return (
    <section aria-label="Decision" className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-5 px-6 pt-6">
        <div className="min-w-0 max-w-[72ch]">
          <p className="flex items-center gap-2 text-[0.8667rem] text-muted">
            {refund ? (
              <><Gavel size={16} /> Rules engine decision{signOff(refund, d)}</>
            ) : (
              <Status tone="dark" live>Working on it</Status>
            )}
          </p>
          <h2 className="mt-2 text-[1.45rem] leading-snug font-semibold tracking-[-0.02em]">{sentence.title}</h2>
          <p className="mt-1 text-muted">{sentence.detail}</p>
        </div>
        {refund?.rule_ids?.length ? (
          <div className="flex max-w-[20rem] flex-wrap items-center gap-1.5" aria-label="Rules applied">
            {refund.rule_ids.slice(0, 3).map((r) => <IdTag key={r}>{r}</IdTag>)}
            {refund.rule_ids.length > 3 && (
              <button type="button" onClick={onRules} className="text-[0.8667rem] font-medium text-muted underline underline-offset-2 hover:text-ink">
                +{refund.rule_ids.length - 3} more
              </button>
            )}
          </div>
        ) : null}
      </div>

      {refund?.rationale?.length ? (
        <ul className="mt-5 flex flex-col gap-2.5 px-6">
          {refund.rationale.slice(0, 4).map((line, i) => (
            <li key={i} className="flex gap-3">
              <Check size={16} weight="bold" className="mt-1 shrink-0 text-ok" />
              <p className="min-w-0 text-ink-soft">{line.text}<Cites ids={line.cites} onCite={onCite} /></p>
            </li>
          ))}
        </ul>
      ) : !refund ? (
        <div className="mt-5 flex flex-col gap-2 px-6"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
      ) : null}

      {others.length > 0 && (
        <div className="mt-6 grid border-t border-line sm:grid-cols-3">
          {others.map((o: Decision) => (
            <div key={o.question} className="border-line px-6 py-4 sm:border-r sm:last:border-r-0">
              <p className="text-[0.8rem] text-muted">{questionLabel(o.question)}</p>
              <p className="mt-1 font-medium">{verdictLabel(o.decision, o.question)}</p>
              {o.rule_ids?.length ? <p className="id-text mt-1 text-[0.7667rem] text-subtle">{o.rule_ids.slice(0, 3).join(" · ")}</p> : null}
            </div>
          ))}
        </div>
      )}
      {d.debate?.ran ? <DebateDetails d={d} onCite={onCite} /> : <div className="h-6" />}
    </section>
  );
}

function DebateDetails({ d, onCite }: { d: CaseDetail; onCite: (id: string) => void }) {
  const debate = d.debate!;
  const rec = debate.recommendation ? verdictLabel(String(debate.recommendation)) : "—";
  return (
    <details className="group mt-2 border-t border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-3.5 text-[0.9333rem] transition-colors hover:bg-canvas">
        <span><span className="font-medium">Ask the customer to repay?</span> <span className="text-muted">Arguments for and against · {rec}</span></span>
        <span className="text-[0.8667rem] text-muted group-open:hidden">Show</span>
        <span className="hidden text-[0.8667rem] text-muted group-open:inline">Hide</span>
      </summary>
      <div className="grid gap-6 px-6 pb-6 lg:grid-cols-2">
        <Arguments title="For recovery (prosecutor)" model={debate.models?.procuror} lines={debate.prosecutor} onCite={onCite} />
        <Arguments title="For the customer (defender)" model={debate.models?.avocat} lines={debate.defender} onCite={onCite} />
        {debate.rubric?.length ? (
          <div className="lg:col-span-2">
            <p className="mb-2 font-medium">Fixed rubric <span className="font-normal text-muted">· a person decides, not the model</span></p>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {debate.rubric.map((r) => (
                <li key={r.indicator} className="flex items-start gap-2 text-[0.9333rem]">
                  {r.value ? <Check size={16} className="mt-0.5 shrink-0" /> : <X size={16} className="mt-0.5 shrink-0 text-subtle" />}
                  <span className={cx(!r.value && "text-muted")}>{r.indicator} <span className="tnum text-subtle">({r.weight > 0 ? "+" : ""}{r.weight})</span></span>
                </li>
              ))}
            </ul>
            {typeof debate.rejected_without_citation === "number" && (
              <p className="mt-3 text-[0.8667rem] text-muted">{debate.rejected_without_citation} claim{debate.rejected_without_citation === 1 ? " was" : "s were"} dropped for having no source.</p>
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
      <p className="font-medium">{title}{model && <span className="ml-2 text-[0.8rem] font-normal text-subtle">{model.replace("anthropic.", "")}</span>}</p>
      {lines?.length ? (
        <ul className="mt-2 flex flex-col gap-2">
          {lines.map((l, i) => <li key={i} className="text-[0.9333rem] text-ink-soft">{l.text}<Cites ids={l.cites} onCite={onCite} /></li>)}
        </ul>
      ) : <p className="mt-2 text-muted">No arguments.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- evidence

function TrustLabel({ f }: { f: Fact }) {
  return f.labels?.trust === "untrusted"
    ? <Status tone="warn">Untrusted</Status>
    : <Status tone="ok">Bank systems</Status>;
}

function EvidenceTab({ facts, flash }: { facts: Fact[]; flash: string | null }) {
  if (!facts.length) return <EmptyState title="No evidence yet">The collectors add evidence here as they find it, each item with its source, time and hash.</EmptyState>;
  return (
    <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <div className="hidden grid-cols-[5.5rem_minmax(0,1fr)_9rem_7rem] gap-4 border-b border-line px-5 py-2.5 text-[0.8rem] text-subtle sm:grid">
        <span>ID</span><span>What it shows</span><span>Trust</span><span>Hash</span>
      </div>
      <ul className="divide-y divide-line">
        {facts.map((f) => (
          <li
            key={f.fact_id}
            id={`fact-${f.fact_id}`}
            className={cx("grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-4 gap-y-1 px-5 py-3.5 sm:grid-cols-[5.5rem_minmax(0,1fr)_9rem_7rem]", flash === f.fact_id && "animate-flash")}
          >
            <span className="id-text text-[0.8rem] leading-6 font-medium text-subtle">{f.fact_id}</span>
            <div className="min-w-0">
              <p className="text-[0.9333rem]">{f.summary || f.kind}</p>
              <p className="mt-0.5 truncate font-mono text-[0.72rem] text-subtle" title={f.source_tool}>{f.source_tool}</p>
              <p className="mt-1.5 sm:hidden"><TrustLabel f={f} /></p>
            </div>
            <span className="hidden pt-0.5 sm:block"><TrustLabel f={f} /></span>
            <span className="hidden pt-1 font-mono text-[0.72rem] text-subtle sm:block" title={f.sha256}>{shortHash(f.sha256, 8)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- rules and deadlines

const CONFIDENCE: Record<string, string> = { P: "Official text", S: "Secondary source", U: "Unverified parameter", V: "Verified" };

function RulesTab({ d }: { d: CaseDetail }) {
  const hits = d.rules?.hits ?? [];
  const deadlines = d.rules?.deadlines ?? [];
  if (!hits.length && !deadlines.length) return <EmptyState title="The rules haven’t run yet">The rules engine starts once the collectors finish.</EmptyState>;
  return (
    <div className="flex flex-col gap-5">
      {deadlines.length > 0 && (
        <Panel title="Legal deadlines" bodyClassName="px-0 pb-1 pt-0">
          <ul className="divide-y divide-line">
            {deadlines.map((dl, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <span className="min-w-0"><span className="font-medium">{dl.name}</span> <span className="text-[0.8667rem] text-muted">· {dl.basis}</span></span>
                <span className="flex items-center gap-4 text-[0.9333rem]"><span className="tnum text-muted">{dateTime(dl.due_at)}</span><DeadlineText deadline={dl.due_at} /></span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
        <div className="hidden grid-cols-[6rem_minmax(0,1fr)_minmax(0,0.7fr)_8rem] gap-4 border-b border-line px-5 py-2.5 text-[0.8rem] text-subtle md:grid">
          <span>Rule</span><span>What it found</span><span>Legal basis</span><span>Source</span>
        </div>
        <ul className="divide-y divide-line">
          {hits.map((h, i) => (
            <li key={`${h.rule_id}-${i}`} className="grid gap-x-4 gap-y-1 px-5 py-3.5 md:grid-cols-[6rem_minmax(0,1fr)_minmax(0,0.7fr)_8rem]">
              <span><IdTag>{h.rule_id}</IdTag></span>
              <div className="min-w-0">
                <p className="font-medium">{h.title}</p>
                {h.explanation && <p className="mt-0.5 text-[0.9333rem] text-muted">{h.explanation}</p>}
              </div>
              <p className="text-[0.8667rem] text-muted">{h.basis}</p>
              <p className="text-[0.8667rem] text-muted">{CONFIDENCE[String(h.confidence)] ?? h.confidence ?? "—"}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- letter + letter check

/** Letter by letter, without accents and in lower case: positions stay the same as in the original text. */
function fold(s: string): string {
  return s.split("").map((ch) => {
    const f = ch.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
    return f.length === 1 ? f : ch;
  }).join("");
}

/** Fallback when the server sends no `term_spans`: find the blocked terms in the text ourselves. */
function spansFromTerms(text: string, terms: string[] | undefined): NonNullable<FilterResult["term_spans"]> {
  const hay = fold(text);
  const out: NonNullable<FilterResult["term_spans"]> = [];
  for (const term of terms ?? []) {
    const needle = fold(term.trim());
    if (!needle) continue;
    for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + needle.length)) {
      out.push({ start: i, end: i + needle.length, label: "blocked term" });
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

const CMP_LABEL: Record<string, string> = {
  "CMP-01": "answers every point",
  "CMP-02": "within the reply deadline",
  "CMP-03": "names ANPC, ANAF, BNR and CSALB",
};

function LetterTab({ d, caseId, onCite }: { d: CaseDetail; caseId: string; onCite: (id: string) => void }) {
  const api = useApi();
  const letter = d.letter;
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState<FilterResult | null>(null);
  const [checked, setChecked] = useState("");
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
      const box = document.getElementById("letter-check") as HTMLTextAreaElement | null;
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
      setError(e instanceof Error ? e.message : "The check didn’t respond");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      {!letter ? (
        <EmptyState title="The letter isn’t ready">The letter writer drafts it after the decision and the recovery step, then the letter check reads it.</EmptyState>
      ) : (
        <Panel
          title={letter.subject}
          actions={blocked
            ? <Badge tone="danger" icon={<Warning size={14} />}>Stopped by the letter check</Badge>
            : <Badge tone="ok" icon={<ShieldCheck size={14} />}>Passed the letter check</Badge>}
        >
          {blocked && (
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3 rounded-xl bg-danger-soft px-4 py-3">
              <div className="min-w-[16rem] flex-1">
                <p className="font-medium">This letter doesn’t go out: the marked phrase isn’t allowed.</p>
                {letter.filter?.reasons?.[0] && <p className="mt-1 text-[0.9333rem] text-ink-soft">{letter.filter.reasons[0]}</p>}
              </div>
              <Button onClick={editLetter}>Fix and check again</Button>
            </div>
          )}
          <div className="max-w-[70ch] text-[0.9667rem] leading-relaxed whitespace-pre-wrap"><Highlighted text={letter.body} spans={letterSpans} /></div>
          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-4 text-[0.9333rem]">
            {(letter.cmp_checks ?? []).map((c) => {
              const bad = c.outcome.toLowerCase().includes("missing") || c.outcome.toLowerCase().includes("unanswered");
              return (
                <span key={c.rule_id} className="inline-flex items-center gap-1.5">
                  {bad ? <X size={16} className="text-danger" /> : <Check size={16} weight="bold" className="text-ok" />}
                  <IdTag>{c.rule_id}</IdTag>
                  <span className="text-ink-soft">{CMP_LABEL[c.rule_id] ?? c.outcome}</span>
                </span>
              );
            })}
            {letter.cites?.length ? <span className="inline-flex items-center text-muted">Based on<Cites ids={letter.cites.slice(0, 6)} onCite={onCite} /></span> : null}
          </div>
        </Panel>
      )}

      <Panel title="Check a text before it goes out" description="Catches personal data and words that must not reach the customer.">
        <label htmlFor="letter-check" className="sr-only">Text to check</label>
        <textarea
          id="letter-check"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Paste a sentence or the whole letter."
          rows={Math.min(14, Math.max(3, Math.ceil(draft.length / 90) + draft.split("\n").length - 1))}
          className="w-full rounded-xl bg-canvas px-4 py-3 text-[0.9333rem] ring-1 ring-line transition-shadow outline-none focus:bg-paper focus:ring-2 focus:ring-ink"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" busy={busy} onClick={check} disabled={!draft.trim()}>Check text</Button>
          {error && <span className="text-danger">{error}.</span>}
        </div>
        {result && (
          <div className={cx("mt-4 rounded-xl px-4 py-3", result.passed ? "bg-ok-soft" : "bg-danger-soft")} role="status">
            <p className="flex items-center gap-2 font-medium">
              {result.passed
                ? <><ShieldCheck size={18} className="text-ok" /> Good to send: nothing blocked.</>
                : <><Warning size={18} className="text-danger" /> Stopped: this text goes to a person instead.</>}
            </p>
            {!result.passed && <p className="mt-2 leading-relaxed"><Highlighted text={checked} spans={result.term_spans?.length ? result.term_spans : spansFromTerms(checked, result.blocked_terms)} /></p>}
            {result.reasons?.length ? <ul className="mt-2 list-disc pl-5 text-[0.9333rem]">{result.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : null}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------- right column

function LiveSteps({ d, events, streamStatus }: { d: CaseDetail; events: Parameters<typeof useStepRows>[1]; streamStatus: string }) {
  const rows = useStepRows(d.pipeline?.nodes, events);
  const [trace, setTrace] = useState(false);
  const lastRun = [...events].reverse().find((e) => e.type === "RUN_STARTED" || e.type === "RUN_FINISHED" || e.type === "RUN_ERROR");
  // a pending signature only pauses the run: the steps after it are not "not needed"
  const waiting = Boolean(d.interrupt?.pending);
  const settled = !waiting && (lastRun ? lastRun.type !== "RUN_STARTED" : Boolean(d.ledger?.sealed));
  return (
    <div>
      <AgentStatus rows={rows} settled={settled} waiting={waiting} onOpenTrace={() => setTrace(true)} />
      {(streamStatus === "reconnecting" || streamStatus === "closed") && (
        <p className="mt-1.5 text-[0.8rem] text-muted">The live feed dropped. Refreshing every few seconds.</p>
      )}
      {trace && (
        <Sheet title="Agent trace" description="Each step, its model and how long it took." onClose={() => setTrace(false)}>
          <StepList rows={rows} settled={settled} />
        </Sheet>
      )}
    </div>
  );
}

const RECALL_KIND: Record<string, string> = {
  interna: "Internal recall (the payee banks with Demo Bank)",
  "camt.056": "SEPA recall camt.056, reason FRAD",
  rechemare_ron: "Recall to the payee’s bank (RON)",
};

const STAGES = ["Eligibility", "Draft", "Filed", "Merchant response", "Arbitration"] as const;

function ChargebackStages({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-1.5" aria-label="Chargeback stages">
      {STAGES.map((s, i) => (
        <li key={s} className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span aria-hidden className={cx("block h-1 rounded-full", i < current ? "bg-ink" : i === current ? "bg-yellow" : "bg-line")} />
          <span className={cx("truncate text-[0.7rem]", i === current ? "font-medium text-ink" : "text-subtle")}>{s}</span>
        </li>
      ))}
    </ol>
  );
}

function RecoveryPanel({ d }: { d: CaseDetail }) {
  const r = d.recovery;
  const fraudster = d.decisions?.find((x) => x.question === "recuperare_escroc");
  if (!fraudster && !r?.chargeback && !r?.recall && !r?.dnsc_report) return null;
  const cb = r?.chargeback;
  return (
    <Panel title="Recovery" description="Drafts only. A person sends each one.">
      <div className="flex flex-col gap-4">
        {fraudster && (
          <p className="text-[0.9333rem]">
            <span className="font-medium">{verdictLabel(fraudster.decision, fraudster.question)}</span>
            {fraudster.rule_ids?.length ? <span className="id-text ml-2 text-[0.7667rem] text-subtle">{fraudster.rule_ids.join(" · ")}</span> : null}
          </p>
        )}
        {cb && (
          <div className="flex flex-col gap-2.5">
            <p className="text-[0.9333rem]">
              <span className="font-medium">{cb.eligible ? `File chargeback${cb.reason_code ? ` ${cb.reason_code}` : ""}` : "Don’t file a chargeback"}</span>
              {cb.explanation && <span className="mt-0.5 block text-muted">{cb.explanation}</span>}
            </p>
            {cb.eligible ? <ChargebackStages current={1} /> : null}
          </div>
        )}
        {r?.recall && (
          <div className="border-t border-line pt-3.5 text-[0.9333rem]">
            <p className="font-medium">{RECALL_KIND[String(r.recall.kind)] ?? r.recall.kind}</p>
            {r.recall.note && <p className="mt-0.5 text-muted">{r.recall.note}</p>}
            {r.recall.xml && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[0.8667rem] font-medium text-ink-soft underline underline-offset-2">camt.056 message (draft)</summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded-xl bg-canvas p-3 text-[0.72rem] leading-snug">{r.recall.xml}</pre>
              </details>
            )}
          </div>
        )}
        {r?.dnsc_report && (
          <details className="border-t border-line pt-3.5 text-[0.9333rem]">
            <summary className="cursor-pointer font-medium">Phishing report for DNSC (draft)</summary>
            {r.dnsc_report.title && <p className="mt-2 font-medium">{r.dnsc_report.title}</p>}
            <p className="mt-1 whitespace-pre-wrap text-muted">{r.dnsc_report.text}</p>
          </details>
        )}
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
      setError(e instanceof Error ? e.message : "Couldn’t recalculate");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Change a fact">
      <p className="text-[0.9333rem] text-muted">
        Today the approval screen {current ? "showed" : "didn’t show"} the amount and the payee. What changes if it {current ? "hadn’t" : "had"}?
      </p>
      <Button className="mt-3" size="sm" busy={busy} onClick={run}>Recalculate</Button>
      {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}.</p>}
      {result && (
        <div className="mt-4 flex flex-col gap-2.5">
          <ul className="flex flex-col gap-1.5 text-[0.9333rem]">
            {result.after.map((a) => {
              const b = result.before.find((x) => x.question === a.question);
              const changed = result.changed.includes(a.question);
              return (
                <li key={a.question} className={cx("rounded-lg px-3 py-2", changed ? "bg-yellow-tint ring-1 ring-inset ring-[#f1dc5c]" : "bg-canvas")}>
                  <span className="text-muted">{questionLabel(a.question)} </span>
                  {changed
                    ? <><s className="text-subtle">{verdictLabel(b?.decision, a.question)}</s> <span className="font-medium">{verdictLabel(a.decision, a.question)}</span></>
                    : <span>{verdictLabel(a.decision, a.question)} <span className="text-subtle">· unchanged</span></span>}
                </li>
              );
            })}
          </ul>
          <p className="text-[0.9333rem] text-ink-soft">{result.explanation}</p>
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
      setError(e instanceof Error ? e.message : "The check didn’t respond");
    } finally {
      setBusy(false);
    }
  }
  // segno writes inline SVG without a namespace; an <img> needs one to render it
  const qrSvg = ledger?.seal?.qr_svg;
  const qr = qrSvg && !qrSvg.includes("xmlns=") ? qrSvg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ') : qrSvg;
  return (
    <Panel title="Evidence file">
      <KeyValues rows={[
        ["Items", <span className="tnum">{count}</span>],
        ["Sealed", sealed ? "Yes, Merkle root signed with Ed25519" : "Not yet (when the case closes)"],
        ledger?.seal ? ["Root", <span className="font-mono text-[0.75rem]" title={ledger.seal.root}>{shortHash(ledger.seal.root, 12)}</span>] : null,
      ]} />
      <Button className="mt-4" size="sm" busy={busy} onClick={check}>Verify integrity</Button>
      {error && <p className="mt-2 text-[0.9333rem] text-danger">{error}.</p>}
      {verify && (
        <div className="mt-4">
          <p className={cx("flex items-center gap-2 font-medium", verify.valid ? "text-ok" : "text-danger")}>
            {verify.valid ? <><SealCheck size={18} /> File intact</> : <><SealWarning size={18} /> {sealed ? "Doesn’t verify" : "Not sealed yet"}</>}
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-[0.8667rem]">
            {verify.checks.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">
                {c.ok ? <CheckCircle size={15} weight="fill" className="mt-0.5 shrink-0 text-ok" /> : <X size={15} className="mt-0.5 shrink-0 text-danger" />}
                <span className="text-ink-soft">{c.name}</span>
              </li>
            ))}
          </ul>
          {qr && <img className="mt-3 size-28 rounded-lg bg-paper ring-1 ring-line" alt="QR code with the signed root of the evidence file" src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} />}
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
    <Panel title="Customer’s message">
      {injection && (
        <p className="mb-3 flex items-start gap-2 rounded-xl bg-warn-soft px-3 py-2.5 text-[0.9333rem] text-warn">
          <Warning size={18} className="mt-0.5 shrink-0" /> It contains instructions aimed at the system. They were treated as data and ignored.
        </p>
      )}
      <details className="group">
        <summary className="cursor-pointer list-none">
          <p className="line-clamp-3 text-[0.9333rem] text-ink-soft group-open:hidden">{c.text}</p>
          <span className="mt-1.5 inline-block text-[0.8667rem] font-medium text-ink-soft underline underline-offset-2 group-open:hidden">Show all</span>
        </summary>
        <p className="text-[0.9333rem] whitespace-pre-wrap text-ink-soft">{c.text}</p>
        {c.attachments?.map((a, i) => (
          <div key={i} className="mt-3 rounded-xl bg-canvas px-3 py-2.5 text-[0.9333rem]">
            <p className="text-[0.8rem] font-medium text-muted">{a.kind === "sms" ? "Text message received" : a.kind === "email" ? "Email" : a.kind}</p>
            <p className="whitespace-pre-wrap">{a.content}</p>
          </div>
        ))}
      </details>
      {d.extracted?.points?.length ? (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-[0.8rem] font-medium text-muted">What the customer asks for</p>
          <ul className="mt-1.5 list-disc pl-5 text-[0.9333rem] text-ink-soft">{d.extracted.points.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
        </div>
      ) : null}
    </Panel>
  );
}
