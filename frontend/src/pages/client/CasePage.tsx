import {
  ArrowLeft,
  ArrowSquareOut,
  ArrowsCounterClockwise,
  Bank,
  Check,
  CheckCircle,
  CreditCard,
  Gavel,
  Hand,
  ShieldWarning,
  SealCheck,
  SealWarning,
  ShieldCheck,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router";
import { channelLabel, dateTime, hasAmount, money, questionLabel, shortHash, verdictLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { useEventStream } from "../../api/sse";
import type { CaseDetail, CounterfactualResult, Decision, Fact, FilterResult, KbHit, LedgerResponse, VerifyResult } from "../../api/types";
import {
  Badge, Banner, Button, cx, DeadlineText, EmptyState, ErrorNote, IdTag, Panel, PanelHeadingLevel, SectionBoundary, Skeleton, Status,
} from "../../ui/kit";
import {
  IdentificationPanel, isPickPending, LegalSourcesPanel, LinkedCasesPanel, NumericCheckItem, NumericMismatches, PickPaymentBanner, PrecedentsPanel,
  ReasonLine, reasonFor, usedInNote,
} from "./caseInsights";
import { AgentStatus, scenarioLabel, Sheet, StatusLine, StepList, useRouting, useStepRows, verdictSentence } from "./caseUi";
import { PassageSheet, SourceChips } from "./knowledgeUi";
import { QrCode, verifyUrl } from "../../ui/QrCode";

type OpenPassage = (hit: KbHit, usedIn?: string[]) => void;

const RELOAD_ON = new Set(["decision", "interrupt", "refund", "ledger_seal", "hold_signal", "wall_block", "diode", "match", "routing"]);

/** The page follows the case: what the customer said, the refund, the recovery, the letter, the evidence file. */
type SectionId = "claim" | "refund" | "recovery" | "letter" | "evidence";
const SECTIONS: SectionId[] = ["claim", "refund", "recovery", "letter", "evidence"];

/** How many evidence items show before "Show all". */
const EVIDENCE_PREVIEW = 6;

export default function CasePage() {
  const { id = "" } = useParams();
  const api = useApi();
  const detail = useResource(() => api.caseDetail(id), [api, id], { pollMs: 2500 });
  const source = useMemo(() => api.caseEvents(id), [api, id]);
  const stream = useEventStream(source, id);
  const [flash, setFlash] = useState<string | null>(null);
  const [allEvidence, setAllEvidence] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [passage, setPassage] = useState<{ hit: KbHit; usedIn?: string[] } | null>(null);
  const openPassage: OpenPassage = (hit, usedIn) => setPassage({ hit, usedIn });
  const d = detail.data;
  const sign = useSignature(d, id, detail.reload);
  const banner = useRef<HTMLDivElement>(null);
  const bannerInView = useInView(banner, Boolean(d?.interrupt?.pending));
  const active = useActiveSection(Boolean(d));

  useEffect(() => {
    const e = stream.last;
    if (!e) return;
    if (e.type === "RUN_FINISHED" || e.type === "RUN_ERROR" || (e.type === "CUSTOM" && RELOAD_ON.has(String(e.name)))) void detail.reload();
  }, [stream.last]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = `${id} · VersoML`;
  }, [id]);

  const cite = (factId: string) => {
    const at = (d?.facts ?? []).findIndex((f) => f.fact_id === factId);
    if (at >= EVIDENCE_PREVIEW) setAllEvidence(true);
    setFlash(factId);
    window.setTimeout(() => document.getElementById(`fact-${factId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  };
  const showRules = () => {
    setRulesOpen(true);
    window.setTimeout(() => document.getElementById("case-rules")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  if (detail.error && !d) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <ErrorNote error={detail.error} what={`case ${id}`} onRetry={detail.reload} />
      </div>
    );
  }
  if (!d) return <CaseSkeleton />;

  const pending = Boolean(d.interrupt?.pending) && !isPickPending(d);
  const agents = <SectionBoundary label="Agents"><LiveSteps d={d} events={stream.events} streamStatus={stream.status} /></SectionBoundary>;

  return (
    <div className="flex flex-col gap-5">
      <CaseHeader d={d} />
      <div ref={banner} className="flex flex-col gap-3 empty:hidden">
        {isPickPending(d)
          ? <PickPaymentBanner d={d} caseId={id} events={stream.events} onDone={detail.reload} />
          : pending && <SignatureBanner d={d} sign={sign} />}
        {d.summary.status === "REFUZAT" && <DeclinedBanner d={d} />}
        {!d.interrupt?.pending && d.letter?.filter?.passed === false && (
          <Banner
            tone="danger"
            icon={<Warning size={20} className="text-danger" />}
            title="The letter check stopped the letter to the customer."
            actions={<Button onClick={() => jumpTo("letter")}>See what was stopped</Button>}
          >
            {d.letter.filter.blocked_terms?.length
              ? <>It contains {d.letter.filter.blocked_terms.map((t) => `“${t}”`).join(", ")}, which can’t go to the customer. </>
              : <>The check found something that can’t go to the customer. </>}
            The refund isn’t affected. The letter only goes out after a person fixes it.
          </Banner>
        )}
      </div>

      <CaseJourney
        steps={journey(d)}
        active={active}
        action={pending && !bannerInView ? <div className="hidden sm:block"><CompactSignature sign={sign} /></div> : null}
      />
      {/* on a phone the step bar has no room for buttons: they sit at the bottom of the screen instead */}
      {/* portalled: the page wrapper's enter animation would otherwise pin a fixed bar to the page, not the screen */}
      {pending && !bannerInView && createPortal(
        <div className="fixed inset-x-0 bottom-0 z-30 flex justify-end border-t border-line bg-paper/90 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md sm:hidden">
          <CompactSignature sign={sign} both />
        </div>,
        document.body,
      )}

      <div className="xl:hidden">{agents}</div>

      <div className="grid items-start gap-x-8 gap-y-10 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <PanelHeadingLevel.Provider value={3}>
          <div className="flex min-w-0 flex-col gap-12">
            <CaseSection id="claim" n={1} title="What the customer reported" meta={d.complaint?.received_at ? `Received ${dateTime(d.complaint.received_at)}` : undefined}>
              <div className="grid items-start gap-4 lg:grid-cols-2">
                <SectionBoundary label="Customer's message"><ComplaintPanel d={d} /></SectionBoundary>
                <SectionBoundary label="Customer and payment"><IdentificationPanel d={d} /></SectionBoundary>
              </div>
              <SectionBoundary label="Linked cases"><div className="mt-4 empty:hidden"><LinkedCasesPanel d={d} /></div></SectionBoundary>
            </CaseSection>

            <CaseSection id="refund" n={2} title="Refund decision" meta={<RefundMeta d={d} />}>
              <SectionBoundary label="Decision"><DecisionPanel d={d} onCite={cite} onRules={showRules} onPassage={openPassage} /></SectionBoundary>
              <details
                id="case-rules"
                open={rulesOpen}
                onToggle={(e) => setRulesOpen((e.currentTarget as HTMLDetailsElement).open)}
                className="group mt-4 scroll-mt-40 lg:scroll-mt-28"
              >
                <summary className="flex w-fit cursor-pointer list-none items-center gap-2 rounded-md text-[0.9333rem] font-medium text-ink-soft transition-colors hover:text-ink">
                  <span aria-hidden className="grid size-5 place-items-center rounded-full bg-hover text-[0.75rem] transition-transform duration-200 group-open:rotate-90">›</span>
                  Rules and deadlines
                  <span className="tnum text-muted">{d.rules?.hits?.length ?? 0}</span>
                </summary>
                <div className="pt-4">
                  <SectionBoundary label="Rules"><RulesTab d={d} onPassage={openPassage} /></SectionBoundary>
                </div>
              </details>
            </CaseSection>

            <CaseSection id="recovery" n={3} title="Getting the money back" meta="Drafts only. A person sends each one.">
              <SectionBoundary label="Recovery"><RecoveryPanel d={d} /></SectionBoundary>
            </CaseSection>

            <CaseSection id="letter" n={4} title="Letter to the customer">
              <SectionBoundary label="Letter"><LetterTab d={d} caseId={id} onCite={cite} onPassage={openPassage} /></SectionBoundary>
            </CaseSection>

            <CaseSection id="evidence" n={5} title="Evidence file" meta="Each item is hashed when collected.">
              <SectionBoundary label="Evidence">
                <EvidenceFile d={d} caseId={id} flash={flash} all={allEvidence} onShowAll={() => setAllEvidence(true)} />
              </SectionBoundary>
            </CaseSection>
          </div>
        </PanelHeadingLevel.Provider>

        <aside aria-label="Case tools" className="flex flex-col gap-4 xl:sticky xl:top-28">
          <div className="hidden xl:block">{agents}</div>
          <SectionBoundary label="Change a fact"><CounterfactualPanel d={d} caseId={id} /></SectionBoundary>
          <SectionBoundary label="Similar past cases"><PrecedentsPanel caseId={id} /></SectionBoundary>
        </aside>
      </div>
      {detail.error && <p className="text-[0.8667rem] text-danger">Updates from the server stopped. Showing the last state received.</p>}
      {passage && <PassageSheet hit={passage.hit} onClose={() => setPassage(null)} note={passage.usedIn?.length ? usedInNote(passage.usedIn) : undefined} />}
    </div>
  );
}

// ---------------------------------------------------------------- the journey: five steps, each a section of the page

type StepState = "done" | "now" | "running" | "stopped" | "todo";
interface JourneyStep { id: SectionId; label: string; state: StepState; note: string }

const CLOSED = ["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"];

/** Where the case stands on each of its five parts, read from the case itself. */
function journey(d: CaseDetail): JourneyStep[] {
  const status = String(d.summary.status);
  // a sealed case is finished even when its status stays open (missing details, the normal complaint route)
  const working = (status === "IN_ANALIZA" || status === "NOU") && !d.ledger?.sealed;
  const pick = isPickPending(d);
  const signing = Boolean(d.interrupt?.pending) && !pick;
  const refund = d.decisions?.find((x) => x.question === "rambursare_t1");
  const r = d.recovery;
  const fraudster = d.decisions?.find((x) => x.question === "recuperare_escroc");
  const facts = d.facts?.length ?? 0;
  const later = (fallback: string): Pick<JourneyStep, "state" | "note"> =>
    signing || pick ? { state: "todo", note: "After your decision" } : working ? { state: "running", note: fallback } : { state: "todo", note: "Not needed" };

  const steps: JourneyStep[] = [
    {
      id: "claim", label: "Claim",
      ...(pick ? { state: "now", note: "Pick the payment" }
        : d.complaint ? { state: "done", note: d.match && !d.match.tx_id ? "Payment not found" : "Read and matched" }
          : { state: "running", note: "Reading" }),
    },
    {
      id: "refund", label: "Refund",
      ...(signing ? { state: "now", note: "Needs your approval" }
        : status === "RAMBURSAT" ? { state: "done", note: "Refunded" }
          : status === "RESPINS" ? { state: "done", note: "Rejected" }
            : status === "EXCEPTIE" ? { state: "done", note: "Exception signed" }
              : status === "TRASEU_APP" ? { state: "done", note: "Recall route" }
                : status === "REFUZAT" ? { state: "done", note: "Declined" }
                : refund ? { state: "done", note: verdictLabel(refund.decision, refund.question) }
                  : pick ? { state: "todo", note: "After the payment is picked" }
                    : working ? { state: "running", note: "Applying the rules" } : { state: "todo", note: "Not yet" }),
    },
    {
      id: "recovery", label: "Recovery",
      ...(r?.chargeback?.eligible ? { state: "done", note: "Chargeback drafted" }
        : r?.recall ? { state: "done", note: "Recall drafted" }
          : r?.dnsc_report ? { state: "done", note: "Report drafted" }
            // before the signature the rules may have answered "recover?", but nothing is filed yet
            : (fraudster || r) && !signing && !pick ? { state: "done", note: "Nothing to file" }
              : later("Preparing drafts")),
    },
    {
      id: "letter", label: "Letter",
      ...(d.letter ? (d.letter.filter?.passed === false ? { state: "stopped", note: "Stopped by the check" } : { state: "done", note: "Passed the check" })
        : status === "REFUZAT" ? { state: "done", note: "Left to the person" }
          : later("Writing")),
    },
    {
      id: "evidence", label: "Evidence",
      ...(d.ledger?.sealed ? { state: "done", note: `${facts} items, sealed` }
        : facts ? { state: working ? "running" : "done", note: `${facts} item${facts === 1 ? "" : "s"}` }
          : working ? { state: "running", note: "Collecting" } : { state: "todo", note: "None yet" }),
    },
  ];
  if (status === "EROARE") {
    const first = steps.find((s) => s.state !== "done");
    if (first) Object.assign(first, { state: "stopped", note: "Failed: restart the case" });
  }
  return steps;
}

function jumpTo(id: SectionId) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(`case-${id}`)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

/** The section the reader is in: the first one crossing a band near the top of the screen. */
function useActiveSection(ready: boolean): SectionId {
  const [active, setActive] = useState<SectionId>("claim");
  useEffect(() => {
    if (!ready) return;
    const seen = new Map<string, boolean>();
    const obs = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target.id.slice(5), e.isIntersecting);
      const first = SECTIONS.find((s) => seen.get(s));
      if (first) setActive(first);
    }, { rootMargin: "-160px 0px -55% 0px" });
    for (const s of SECTIONS) {
      const el = document.getElementById(`case-${s}`);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
  }, [ready]);
  return active;
}

function useInView(ref: React.RefObject<HTMLElement | null>, enabled: boolean): boolean {
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!enabled || !el) return;
    const obs = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin: "-64px 0px 0px 0px" });
    obs.observe(el);
    return () => obs.disconnect();
  }, [ref, enabled]);
  return inView;
}

const BAR: Record<StepState, string> = {
  done: "bg-ink",
  now: "bg-yellow",
  running: "bg-ink/25",
  stopped: "bg-danger",
  todo: "bg-transparent",
};

/** Sticky under the header: five steps, each one jumps to its section and says where that part stands. */
function CaseJourney({ steps, active, action }: { steps: JourneyStep[]; active: SectionId; action: ReactNode }) {
  return (
    <nav
      aria-label="Case sections"
      className="sticky top-14 z-20 -mx-5 border-b border-line bg-paper px-5 sm:-mx-8 sm:px-8 lg:top-0 lg:-mx-10 lg:px-10"
    >
      <div className="flex items-center gap-5">
        <ol className="grid min-w-0 flex-1 grid-cols-5 gap-1 py-2 sm:gap-1.5">
          {steps.map((s, i) => {
            const here = active === s.id;
            return (
              <li key={s.id} className="min-w-0">
                <button
                  type="button"
                  onClick={() => jumpTo(s.id)}
                  aria-current={here ? "location" : undefined}
                  className={cx(
                    "group flex w-full min-w-0 flex-col gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors duration-150",
                    here ? "bg-yellow-tint ring-1 ring-inset ring-yellow-line" : "hover:bg-hover/60",
                  )}
                >
                  <span aria-hidden className="relative block h-1 overflow-hidden rounded-full bg-line">
                    <span
                      className={cx(
                        "absolute inset-0 origin-left rounded-full transition-[transform,background-color] duration-500 ease-[var(--ease-out)]",
                        BAR[s.state],
                        s.state === "todo" ? "scale-x-0" : "scale-x-100",
                      )}
                    />
                    {s.state === "running" && <span className="absolute inset-y-0 left-0 w-1/3 animate-[bar-run_1.4s_var(--ease-in-out)_infinite] rounded-full bg-ink/60" />}
                  </span>
                  <span className={cx(
                    "flex min-w-0 items-center gap-1.5 text-[0.8rem] transition-colors sm:text-[0.8667rem]",
                    here ? "font-semibold text-ink" : "font-medium text-ink-soft group-hover:text-ink",
                  )}>
                    <span aria-hidden className={cx("tnum hidden text-[0.75rem] sm:inline", here ? "text-ink" : "text-subtle")}>{i + 1}</span>
                    <span className="truncate">{s.label}</span>
                  </span>
                  <span className={cx(
                    "hidden truncate text-[0.75rem] sm:block",
                    s.state === "now" ? "font-medium text-ink" : s.state === "stopped" ? "text-danger" : "text-muted",
                  )}>
                    {s.note}
                  </span>
                  <span className="sr-only">: {s.note}</span>
                </button>
              </li>
            );
          })}
        </ol>
        {action}
      </div>
    </nav>
  );
}

/** The yellow number ties each section to its step in the bar above, so the page reads as five zones. */
function StepNumber({ n, className }: { n: number; className?: string }) {
  return (
    <span aria-hidden className={cx("tnum grid shrink-0 place-items-center rounded-md bg-yellow font-semibold text-on-yellow", className)}>{n}</span>
  );
}

function CaseSection({ id, n, title, meta, children }: { id: SectionId; n: number; title: string; meta?: ReactNode; children: ReactNode }) {
  return (
    <section id={`case-${id}`} aria-labelledby={`case-${id}-title`} className="scroll-mt-40 lg:scroll-mt-28">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h2 id={`case-${id}-title`} className="flex items-center gap-2.5 text-[1.1rem] font-semibold tracking-[-0.015em]">
          <StepNumber n={n} className="size-6 text-[0.8rem]" />
          {title}
        </h2>
        {meta && <div className="text-[0.8667rem] text-muted">{meta}</div>}
      </div>
      {children}
    </section>
  );
}

function RefundMeta({ d }: { d: CaseDetail }) {
  const deadline = d.clock?.t1_deadline ?? d.summary.deadline;
  if (!deadline) return null;
  if (CLOSED.includes(String(d.summary.status))) return <span>Deadline was {dateTime(deadline)}</span>;
  return <DeadlineText deadline={deadline} />;
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
  const closed = ["RAMBURSAT", "RESPINS", "INCHIS", "EXCEPTIE", "TRASEU_APP"].includes(String(s.status)) || s.verdict === "NU_SE_APLICA_T1";
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9333rem] text-muted">
            <span className="font-medium text-ink-soft">{s.customer_alias}</span>
            <span aria-hidden>·</span>
            <span>{(!isPickPending(d) && s.scenario_phrase) || scenarioLabel(s.scenario)}</span>
            <span aria-hidden>·</span>
            <span className="id-text text-[0.8667rem] text-subtle">{s.case_id}</span>
          </p>
          <h1 className="mt-1.5 text-[2.1rem] leading-tight font-semibold tracking-[-0.03em]">
            {hasAmount(s.amount) ? (
              <>{money(s.amount)} <span className="font-normal text-subtle">{channelLabel(s.channel).toLowerCase()}</span></>
            ) : isPickPending(d) || (d.match && !d.match.tx_id) ? (
              <span className="font-normal text-subtle">{isPickPending(d) ? "Payment to be picked" : "Payment not identified"}</span>
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
            <dd className="mt-1 text-[0.9333rem] font-medium"><StatusLine status={String(s.status)} requiresHuman={s.requires_human} verdict={s.verdict} /></dd>
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

/** After "Decline": VersoML has stopped, and the legal deadline is now the person's to meet. */
function DeclinedBanner({ d }: { d: CaseDetail }) {
  const who = d.summary.rejected_by ?? d.interrupt?.answer?.approver ?? "A person";
  const deadline = d.clock?.t1_deadline ?? d.summary.deadline;
  return (
    <Banner tone="neutral" icon={<Hand size={20} className="text-ink-soft" />} title={`${who} declined the refund${d.summary.rejected_at ? ` on ${dateTime(d.summary.rejected_at)}` : ""}. VersoML stopped here.`}>
      No money went out and no letter was written; the person handling the case writes to the customer.
      {deadline ? <> The deadline still applies: by {dateTime(deadline)} the bank refunds, or reports suspected fraud to the authorities (DSP-05).</> : null}
    </Banner>
  );
}

const SIGN_COPY: Record<string, { yes: string; no: string; consequence: string }> = {
  RAMBURSEAZA_CU_APROBARE: { yes: "Approve refund", no: "Decline", consequence: "When you approve, the rules engine issues the refund right away." },
  RESPINGE_TARDIV: { yes: "Confirm rejection", no: "Don’t confirm, refund", consequence: "The customer gets a rejection letter with the legal basis and how to appeal." },
  EXCEPTIE_FRAUDA_CLIENT: { yes: "Confirm exception", no: "Don’t confirm, refund", consequence: "No refund for now. Only use this if the authorities have been notified." },
};

interface Signature {
  copy: { yes: string; no: string; consequence: string };
  busy: "approve" | "reject" | null;
  locked: boolean;
  resuming: boolean;
  error: string | null;
  act: (action: "approve" | "reject") => Promise<void>;
}

/** One signature state, shared by the banner and the compact buttons in the step bar. */
function useSignature(d: CaseDetail | undefined, caseId: string, onDone: () => Promise<void>): Signature {
  const api = useApi();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const it = d?.interrupt;
  const copy = SIGN_COPY[String(it?.verdict)] ?? { yes: "Approve", no: "Decline", consequence: "The decision applies right away." };
  const resuming = Boolean(it?.resuming);
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
  return { copy, busy, locked: resuming || busy !== null, resuming, error, act };
}

function SignatureBanner({ d, sign }: { d: CaseDetail; sign: Signature }) {
  const it = d.interrupt!;
  return (
    <Banner
      tone="now"
      title={it.prompt ?? "This decision needs your approval."}
      actions={<>
        <Button busy={sign.busy === "reject"} disabled={sign.locked} onClick={() => sign.act("reject")}>{sign.copy.no}</Button>
        <Button variant="primary" busy={sign.busy === "approve"} disabled={sign.locked} onClick={() => sign.act("approve")}>{sign.copy.yes}</Button>
      </>}
    >
      {sign.resuming ? "Signature received. Applying the decision…" : sign.copy.consequence}
      {it.rule_ids?.length ? <span className="ml-1 text-muted">Rules: {it.rule_ids.join(", ")}.</span> : null}
      {sign.error && <span className="mt-1 block font-medium text-danger">{sign.error}.</span>}
    </Banner>
  );
}

/** The same two buttons, in the step bar, once the banner has scrolled away. */
function CompactSignature({ sign, both = false }: { sign: Signature; both?: boolean }) {
  return (
    <div className="flex shrink-0 animate-enter items-center gap-2">
      <Button size="sm" className={both ? undefined : "hidden md:inline-flex"} busy={sign.busy === "reject"} disabled={sign.locked} onClick={() => sign.act("reject")}>{sign.copy.no}</Button>
      <Button size="sm" variant="primary" busy={sign.busy === "approve"} disabled={sign.locked} onClick={() => sign.act("approve")}>{sign.copy.yes}</Button>
    </div>
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
  const answer = d.interrupt?.pending ? undefined : d.interrupt?.answer;
  const approver = (answer && answer.action !== "pick_transaction" ? answer.approver : undefined) ?? d.summary.approved_by ?? undefined;
  if (approver) return ` · signed by ${approver}${d.summary.approved_at ? `, ${dateTime(d.summary.approved_at)}` : ""}`;
  if (refund.decided_by === "rules+human" || refund.requires_human) return d.interrupt?.pending ? " · waiting for your signature" : " · a person signs off";
  return "";
}

function DecisionPanel({ d, onCite, onRules, onPassage }: { d: CaseDetail; onCite: (id: string) => void; onRules: () => void; onPassage: OpenPassage }) {
  const decisions = d.decisions ?? [];
  const refund = decisions.find((x) => x.question === "rambursare_t1");
  const answer = d.interrupt?.answer?.action === "pick_transaction" ? undefined : d.interrupt?.answer;
  const sentence = verdictSentence(refund, d.summary.amount, {
    status: String(d.summary.status),
    action: d.interrupt?.pending ? undefined : answer?.action,
    approver: answer?.approver ?? d.summary.approved_by ?? undefined,
  });
  // while the decision is open, the rules engine's own sentence explains it; once it is final, the outcome does
  const final = ["RAMBURSAT", "RESPINS", "EXCEPTIE", "REFUZAT"].includes(String(d.summary.status)) || answer?.action === "reject";
  const reason = reasonFor(refund, d.reasons);
  const others = decisions.filter((x) => x.question !== "rambursare_t1" && x.question !== "pista_aml" && x.question !== "rts");
  return (
    <section aria-label="Decision" className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-5 border-b border-yellow-line bg-yellow-tint px-6 pt-5 pb-5">
        <div className="min-w-0 max-w-[72ch]">
          <p className="flex items-center gap-2 text-[0.8667rem] text-ink-soft">
            {refund ? (
              <><Gavel size={16} /> Rules engine decision{signOff(refund, d)}</>
            ) : (
              <Status tone="dark" live>Working on it</Status>
            )}
          </p>
          <h3 className="mt-2 text-[1.4rem] leading-snug font-semibold tracking-[-0.02em]">{sentence.title}</h3>
          <p className="mt-1 text-ink-soft">
            {!final && reason?.sentence ? reason.sentence : sentence.detail}
            {!final && reason?.rule_id && !refund?.rule_ids?.slice(0, 3).includes(reason.rule_id) ? <span className="id-text ml-1.5 text-[0.7667rem] text-subtle">{reason.rule_id}</span> : null}
          </p>
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
              {reasonFor(o, d.reasons)
                ? <ReasonLine reason={reasonFor(o, d.reasons)} className="mt-1" />
                : o.rule_ids?.length ? <p className="id-text mt-1 text-[0.7667rem] text-subtle">{o.rule_ids.slice(0, 3).join(" · ")}</p> : null}
            </div>
          ))}
        </div>
      )}
      {d.debate?.ran ? <DebateDetails d={d} onCite={onCite} onPassage={onPassage} /> : <div className="h-6" />}
    </section>
  );
}

function DebateDetails({ d, onCite, onPassage }: { d: CaseDetail; onCite: (id: string) => void; onPassage: OpenPassage }) {
  const debate = d.debate!;
  const sources = (d.grounding ?? []).filter((g) => g.used_in === "debate").map((g) => g.hit);
  return (
    <details className="group mt-2 border-t border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-3.5 text-[0.9333rem] transition-colors hover:bg-canvas">
        <span><span className="font-medium">Arguments on repaying</span> <span className="text-muted">· one model argues for recovery, one for the customer; a person decides</span></span>
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
        {sources.length > 0 && (
          <p className="text-[0.9333rem] lg:col-span-2">
            <SourceChips hits={sources} onOpen={(h) => onPassage(h, ["debate"])} label="Legal sources:" />
          </p>
        )}
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
    ? <Status tone="warn">Customer, untrusted</Status>
    : <Status tone="ok">Bank systems</Status>;
}

function EvidenceFile({ d, caseId, flash, all, onShowAll }: { d: CaseDetail; caseId: string; flash: string | null; all: boolean; onShowAll: () => void }) {
  const facts = d.facts ?? [];
  if (!facts.length) return <EmptyState title="No evidence yet">The collectors add evidence here as they find it, each item with its source, time and hash.</EmptyState>;
  const shown = all ? facts : facts.slice(0, EVIDENCE_PREVIEW);
  const untrusted = facts.filter((f) => f.labels?.trust === "untrusted").length;
  return (
    <div className="overflow-hidden rounded-xl bg-paper shadow-[var(--shadow-card)]">
      <SealStrip caseId={caseId} sealed={Boolean(d.ledger?.sealed)} root={d.ledger?.root} count={d.ledger?.count ?? facts.length} untrusted={untrusted} />
      <div className="hidden grid-cols-[5.5rem_minmax(0,1fr)_9rem_7rem] gap-4 border-y border-line bg-canvas px-5 py-2 text-[0.8rem] text-subtle sm:grid">
        <span>ID</span><span>What it shows</span><span>Source</span><span>Hash</span>
      </div>
      <ul className="divide-y divide-line">
        {shown.map((f) => (
          <li
            key={f.fact_id}
            id={`fact-${f.fact_id}`}
            className={cx("grid scroll-mt-40 grid-cols-[5.5rem_minmax(0,1fr)] gap-x-4 gap-y-1 px-5 py-3.5 sm:grid-cols-[5.5rem_minmax(0,1fr)_9rem_7rem]", flash === f.fact_id && "animate-flash")}
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
      {!all && facts.length > EVIDENCE_PREVIEW && (
        <button
          type="button"
          onClick={onShowAll}
          className="flex w-full items-center justify-center gap-1.5 border-t border-line px-5 py-3 text-[0.9333rem] font-medium text-ink-soft transition-colors hover:bg-canvas hover:text-ink"
        >
          Show all {facts.length} items
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- rules and deadlines

const CONFIDENCE: Record<string, string> = { P: "Official text", S: "Secondary source", U: "Unverified parameter", V: "Verified" };

function RulesTab({ d, onPassage }: { d: CaseDetail; onPassage: OpenPassage }) {
  const hits = d.rules?.hits ?? [];
  const deadlines = d.rules?.deadlines ?? [];
  if (!hits.length && !deadlines.length) return <EmptyState title="The rules haven’t run yet">The rules engine starts once the collectors finish.</EmptyState>;
  const legal = <LegalSourcesPanel grounding={d.grounding} onOpen={onPassage} />;
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
      {legal}
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

function LetterTab({ d, caseId, onCite, onPassage }: { d: CaseDetail; caseId: string; onCite: (id: string) => void; onPassage: OpenPassage }) {
  const sources = (d.grounding ?? []).filter((g) => g.used_in === "letter").map((g) => g.hit);
  const api = useApi();
  const letter = d.letter;
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState<FilterResult | null>(null);
  const [checked, setChecked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkOpen, setCheckOpen] = useState(false);
  const blocked = letter?.filter?.passed === false;
  const letterSpans = blocked && letter
    ? (letter.filter?.term_spans?.length ? letter.filter.term_spans : spansFromTerms(letter.body, letter.filter?.blocked_terms))
    : undefined;
  function editLetter() {
    if (!letter) return;
    setDraft(letter.body);
    setResult(null);
    setCheckOpen(true);
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
        d.summary.status === "REFUZAT"
          ? <EmptyState title="No letter: the refund was declined">A letter now would promise money nobody approved. The person handling the case writes to the customer.</EmptyState>
          : <EmptyState title="The letter isn’t ready">The letter writer drafts it after the decision and the recovery step, then the letter check reads it.</EmptyState>
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
            <NumericCheckItem check={d.numeric_check} />
            {letter.cites?.length ? <span className="inline-flex flex-wrap items-center gap-y-1 text-muted"><span className="whitespace-nowrap">Based on</span><Cites ids={letter.cites.slice(0, 6)} onCite={onCite} /></span> : null}
          </div>
          {sources.length > 0 && (
            <p className="mt-3 text-[0.9333rem]"><SourceChips hits={sources} onOpen={(h) => onPassage(h, ["letter"])} label="Legal sources:" /></p>
          )}
          <NumericMismatches check={d.numeric_check} />
        </Panel>
      )}

      <details open={checkOpen} onToggle={(e) => setCheckOpen((e.currentTarget as HTMLDetailsElement).open)} className="group">
        <summary className="flex w-fit cursor-pointer list-none items-center gap-2 rounded-md text-[0.9333rem] font-medium text-ink-soft transition-colors hover:text-ink">
          <span aria-hidden className="grid size-5 place-items-center rounded-full bg-hover text-[0.75rem] transition-transform duration-200 group-open:rotate-90">›</span>
          Check another text before it goes out
        </summary>
      <Panel className="mt-4" description="Catches personal data and words that must not reach the customer.">
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
      </details>
    </div>
  );
}

// ---------------------------------------------------------------- right column

function LiveSteps({ d, events, streamStatus }: { d: CaseDetail; events: Parameters<typeof useStepRows>[1]; streamStatus: string }) {
  const routing = useRouting(d.routing, events);
  const rows = useStepRows(d.pipeline?.nodes, events, routing);
  const [trace, setTrace] = useState(false);
  const lastRun = [...events].reverse().find((e) => e.type === "RUN_STARTED" || e.type === "RUN_FINISHED" || e.type === "RUN_ERROR");
  // a pending signature only pauses the run: the steps after it are not "not needed"
  const waiting = Boolean(d.interrupt?.pending);
  const settled = !waiting && (lastRun ? lastRun.type !== "RUN_STARTED" : Boolean(d.ledger?.sealed));
  return (
    <div>
      <AgentStatus rows={rows} settled={settled} waiting={waiting} waitingLabel={isPickPending(d) ? "Waiting for your pick" : undefined} onOpenTrace={() => setTrace(true)} />
      {(streamStatus === "reconnecting" || streamStatus === "closed") && (
        <p className="mt-1.5 text-[0.8rem] text-muted">The live feed dropped. Refreshing every few seconds.</p>
      )}
      {trace && (
        <Sheet title="Agent trace" description="Each step, its model, how long it took, and why the router ran it or not." onClose={() => setTrace(false)}>
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

function RecoveryRow({ icon, title, children, aside }: { icon: ReactNode; title: ReactNode; children?: ReactNode; aside?: ReactNode }) {
  return (
    <li className="flex gap-4 px-5 py-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-hover text-ink-soft">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <p className="font-medium">{title}</p>
          {aside}
        </div>
        {children}
      </div>
    </li>
  );
}

const draft = <Badge tone="now">Draft</Badge>;

function RecoveryPanel({ d }: { d: CaseDetail }) {
  const r = d.recovery;
  const fraudster = d.decisions?.find((x) => x.question === "recuperare_escroc");
  if (!fraudster && !r?.chargeback && !r?.recall && !r?.dnsc_report) {
    return (
      <EmptyState title={d.interrupt?.pending ? "Waiting for the refund decision" : "Nothing drafted yet"}>
        After the refund, VersoML picks the route that can win: a card chargeback, a recall from the payee’s bank, and a phishing report.
      </EmptyState>
    );
  }
  const cb = r?.chargeback;
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-xl bg-paper shadow-[var(--shadow-card)]">
      {fraudster && (
        <RecoveryRow
          icon={<ArrowsCounterClockwise size={18} />}
          title={verdictLabel(fraudster.decision, fraudster.question)}
          aside={fraudster.rule_ids?.length ? <span className="id-text text-[0.7667rem] text-subtle">{fraudster.rule_ids.join(" · ")}</span> : null}
        >
          <ReasonLine reason={reasonFor(fraudster, d.reasons)} className="mt-0.5" />
        </RecoveryRow>
      )}
      {cb && (
        <RecoveryRow
          icon={<CreditCard size={18} />}
          title={cb.eligible ? `File a chargeback${cb.reason_code ? `, reason ${cb.reason_code}` : ""}` : "Don’t file a chargeback"}
          aside={cb.eligible ? draft : null}
        >
          {cb.explanation && <p className="mt-0.5 text-[0.9333rem] text-muted">{cb.explanation}</p>}
          {cb.eligible ? <div className="mt-3 max-w-[28rem]"><ChargebackStages current={1} /></div> : null}
        </RecoveryRow>
      )}
      {r?.recall && (
        <RecoveryRow icon={<Bank size={18} />} title={RECALL_KIND[String(r.recall.kind)] ?? r.recall.kind} aside={draft}>
          {r.recall.note && <p className="mt-0.5 text-[0.9333rem] text-muted">{r.recall.note}</p>}
          {r.recall.xml && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[0.8667rem] font-medium text-ink-soft underline decoration-line-strong underline-offset-2 hover:text-ink">The camt.056 message</summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-xl bg-canvas p-3 text-[0.72rem] leading-snug">{r.recall.xml}</pre>
            </details>
          )}
        </RecoveryRow>
      )}
      {r?.dnsc_report && (
        <RecoveryRow icon={<ShieldWarning size={18} />} title={r.dnsc_report.title || "Phishing report for DNSC"} aside={draft}>
          <details className="mt-1">
            <summary className="cursor-pointer text-[0.8667rem] font-medium text-ink-soft underline decoration-line-strong underline-offset-2 hover:text-ink">Read the report</summary>
            <p className="mt-2 max-w-[70ch] text-[0.9333rem] whitespace-pre-wrap text-muted">{r.dnsc_report.text}</p>
          </details>
        </RecoveryRow>
      )}
    </ul>
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
                <li key={a.question} className={cx("rounded-lg px-3 py-2", changed ? "bg-yellow-tint ring-1 ring-inset ring-yellow-line" : "bg-canvas")}>
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

/**
 * The evidence file's seal, on yellow: the proof the bank stands behind. Once sealed, the QR code opens the public
 * check page, which anyone can scan to have the server run every check again.
 */
function SealStrip({ caseId, sealed, root, count, untrusted }: { caseId: string; sealed: boolean; root?: string | null; count: number; untrusted: number }) {
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
  const link = sealed && root ? verifyUrl(caseId, root) : null;
  return (
    <div className={cx("flex flex-wrap items-start gap-x-6 gap-y-4 px-5 py-5", sealed ? "bg-yellow-tint" : "bg-canvas")}>
      <div className="min-w-[16rem] flex-1">
        <div className="flex items-start gap-3">
          <span className={cx("grid size-10 shrink-0 place-items-center rounded-full", sealed ? "bg-yellow text-on-yellow" : "bg-hover text-muted")}>
            <SealCheck size={20} weight={sealed ? "fill" : "regular"} />
          </span>
          <p className="min-w-0 leading-tight">
            <span className="block font-semibold">{sealed ? "Sealed and signed" : "Not sealed yet"}</span>
            <span className="mt-1 block text-[0.8667rem] text-ink-soft">
              <span className="tnum">{count}</span> items{untrusted ? <> · <span className="tnum">{untrusted}</span> from the customer, marked untrusted</> : null}
              {sealed ? " · Merkle root signed with Ed25519" : " · the seal goes on when the case closes"}
            </span>
          </p>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 pl-[3.25rem]">
          <Button size="sm" busy={busy} onClick={check}>Verify integrity</Button>
          {link && (
            <a href={link} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[0.8667rem] font-medium text-ink-soft underline decoration-yellow-line underline-offset-4 transition-colors hover:text-ink hover:decoration-ink">
              Open the public check <ArrowSquareOut aria-hidden size={14} />
            </a>
          )}
        </div>
        {error && <p className="mt-3 pl-[3.25rem] text-[0.9333rem] text-danger">{error}.</p>}
        {verify && (
          <div className="mt-4 ml-[3.25rem] animate-enter rounded-xl bg-paper px-4 py-3 shadow-[var(--shadow-card)]" role="status">
            <p className={cx("flex items-center gap-2 font-medium", verify.valid ? "text-ok" : "text-danger")}>
              {verify.valid ? <><SealCheck size={18} /> File intact</> : <><SealWarning size={18} /> {sealed ? "Doesn’t verify" : "Not sealed yet"}</>}
            </p>
            <ul className="mt-2 grid gap-1 text-[0.8667rem] sm:grid-cols-2">
              {verify.checks.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5" title={c.detail}>
                  {c.ok ? <CheckCircle size={15} weight="fill" className="mt-0.5 shrink-0 text-ok" /> : <X size={15} className="mt-0.5 shrink-0 text-danger" />}
                  <span className="text-ink-soft">{c.name}</span>
                </li>
              ))}
            </ul>
            {ledger?.seal && <p className="mt-2 text-[0.8rem] text-muted">Root <span className="font-mono" title={ledger.seal.root}>{shortHash(ledger.seal.root, 12)}</span></p>}
          </div>
        )}
      </div>
      {link && (
        <a href={link} target="_blank" rel="noreferrer" className="group flex shrink-0 flex-col items-center gap-2 rounded-xl" aria-label="Open the public check of this evidence file">
          <QrCode text={link} label="QR code that opens the public check of this evidence file" className="size-32 rounded-lg ring-1 ring-yellow-line transition-transform duration-150 group-hover:scale-[1.02]" />
          <span className="text-[0.8rem] text-ink-soft">Scan to check on a phone</span>
        </a>
      )}
    </div>
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
