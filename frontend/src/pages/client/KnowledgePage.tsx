import { BookOpenText, CaretDown, MagnifyingGlass, Warning } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { dateTime, num, plural } from "../../api/format";
import { useApi, useResource, useRuntime } from "../../api/runtime";
import type { KbAnswer, KbHit, KbStats } from "../../api/types";
import { Button, cx, EmptyState, ErrorNote, PageHeader, Skeleton, Tabs } from "../../ui/kit";
import { CitedText, HitList, HitRow, PassageSheet } from "./knowledgeUi";

type Mode = "ask" | "search";

const KINDS: Array<[string, string]> = [
  ["rule", "Rules"],
  ["law", "Law"],
  ["guidance", "Guidance"],
  ["typology", "Typologies"],
  ["case_study", "Case studies"],
  ["precedent", "Past cases"],
];

const KIND_PLURAL: Record<string, [string, string]> = {
  rule: ["rule", "rules"],
  law: ["law passage", "law passages"],
  guidance: ["guidance note", "guidance notes"],
  typology: ["typology", "typologies"],
  case_study: ["case study", "case studies"],
  precedent: ["past case", "past cases"],
};

const CLIENT_QUESTIONS = [
  "Can the bank delay the refund if the customer was grossly negligent?",
  "By when must we refund an unauthorized payment?",
  "What must the answer to a complaint include?",
  "Clientul a aprobat plata după un apel de la „bancă”. Rambursăm?",
];

const AML_QUERIES = ["How long is a transaction held after a report?", "Money mule account signals", "AML-04"];

const MODE_LABEL: Record<string, string> = {
  live: "Answered by the live model",
  replay: "Recorded answer (replay)",
  offline: "Built from the passages, without a model",
};

const FIELD = "h-10 w-full rounded-md bg-paper text-[0.9333rem] ring-1 ring-inset ring-line-strong transition-shadow outline-none focus:ring-2 focus:ring-ink";
const LINK = "text-left font-medium text-ink-soft underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink hover:decoration-ink";

export default function KnowledgePage() {
  const api = useApi();
  const { zone } = useRuntime();
  const aml = zone === "aml";
  const [mode, setMode] = useState<Mode>(aml ? "search" : "ask");
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [answer, setAnswer] = useState<KbAnswer | null>(null);
  const [hits, setHits] = useState<{ q: string; kind: string; list: KbHit[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ mode: Mode; message: string } | null>(null);
  const [flash, setFlash] = useState<number | null>(null);
  const [passage, setPassage] = useState<KbHit | null>(null);
  const stats = useResource(aml ? null : () => api.kbStats(), [api, aml]);
  const inputRef = useRef<HTMLInputElement>(null);
  const ticket = useRef(0);

  useEffect(() => {
    document.title = "Knowledge · VersoML";
  }, []);

  async function run(nextMode: Mode, text: string, nextKind = kind) {
    const query = text.trim();
    if (!query) {
      inputRef.current?.focus();
      return;
    }
    const my = ++ticket.current;
    setBusy(true);
    setError(null);
    try {
      if (nextMode === "ask") {
        const a = await api.kbAsk({ question: query, k: 4 });
        if (my === ticket.current) setAnswer(a);
      } else {
        const list = aml ? await api.amlKbSearch({ q: query, k: 8 }) : await api.kbSearch({ q: query, k: 8, kind: nextKind || undefined });
        if (my === ticket.current) setHits({ q: query, kind: nextKind, list: Array.isArray(list) ? list : [] });
      }
    } catch (e) {
      if (my === ticket.current) setError({ mode: nextMode, message: e instanceof Error ? e.message : "The knowledge base didn't answer" });
    } finally {
      if (my === ticket.current) setBusy(false);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(mode, q);
  };

  function goToCitation(n: number) {
    setFlash(null);
    window.requestAnimationFrame(() => {
      setFlash(n);
      document.getElementById(`citation-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    window.setTimeout(() => setFlash((f) => (f === n ? null : f)), 1700);
  }

  const suggestions = aml ? AML_QUERIES : CLIENT_QUESTIONS;
  const showSuggestions = mode === "ask" ? !answer : !hits;

  return (
    <>
      <PageHeader
        title="Knowledge"
        description={aml
          ? "The AML law, typologies and case studies the investigators use. Search the passages."
          : "The laws, rules and guidance behind every decision. Ask a question, or search the passages."}
      />

      {!aml && (
        <Tabs<Mode>
          label="Ask or search"
          value={mode}
          onChange={(m) => {
            setMode(m);
            setError(null);
          }}
          tabs={[{ id: "ask", label: "Ask" }, { id: "search", label: "Search" }]}
        />
      )}

      <form role="search" aria-label={mode === "ask" ? "Ask the knowledge base" : "Search the knowledge base"} onSubmit={submit} className={cx("flex flex-col gap-2.5 sm:flex-row sm:items-center", !aml && "mt-5")}>
        <div className="relative min-w-0 flex-1">
          <MagnifyingGlass aria-hidden size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" />
          <label htmlFor="kb-query" className="sr-only">{mode === "ask" ? "Question" : "Search terms"}</label>
          <input
            ref={inputRef}
            id="kb-query"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={mode === "ask" ? "Ask about a rule, a deadline or a type of scam" : "Search by words, a rule ID such as PAY-03, or an article"}
            autoComplete="off"
            className={cx(FIELD, "pr-3 pl-9 placeholder:text-subtle [&::-webkit-search-cancel-button]:appearance-none")}
          />
        </div>
        {mode === "search" && !aml && (
          <span className="relative inline-flex sm:w-44">
            <label htmlFor="kb-kind" className="sr-only">Kind of passage</label>
            <select
              id="kb-kind"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                if (hits) void run("search", q || hits.q, e.target.value);
              }}
              className={cx(FIELD, "appearance-none truncate pr-9 pl-3")}
            >
              <option value="">All kinds</option>
              {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <CaretDown aria-hidden size={14} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-subtle" />
          </span>
        )}
        <Button type="submit" variant="primary" busy={busy} className="h-10">{mode === "ask" ? "Ask" : "Search"}</Button>
      </form>

      {showSuggestions && (
        <p className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1.5 text-[0.8667rem] text-muted">
          <span>Try:</span>
          {suggestions.map((s) => (
            <button key={s} type="button" className={LINK} onClick={() => { setQ(s); void run(mode, s); }}>{s}</button>
          ))}
        </p>
      )}

      <div className="mt-6" aria-live="polite">
        {error && error.mode === mode ? (
          <ErrorNote error={error.message} what={mode === "ask" ? "an answer" : "the passages"} onRetry={() => run(mode, q)} />
        ) : busy && ((mode === "ask" && !answer) || (mode === "search" && !hits)) ? (
          <ResultSkeleton ask={mode === "ask"} />
        ) : mode === "ask" ? (
          answer && <AnswerView answer={answer} flash={flash} onMarker={goToCitation} onOpen={setPassage} dim={busy} />
        ) : (
          hits && <SearchView hits={hits} onOpen={setPassage} dim={busy} onAll={() => { setKind(""); void run("search", hits.q, ""); }} />
        )}
      </div>

      {!aml && <StatsLine stats={stats.data} />}
      {passage && <PassageSheet hit={passage} onClose={() => setPassage(null)} />}
    </>
  );
}

function AnswerView({ answer, flash, onMarker, onOpen, dim }: {
  answer: KbAnswer; flash: number | null; onMarker: (n: number) => void; onOpen: (h: KbHit) => void; dim: boolean;
}) {
  const cites = answer.citations ?? [];
  return (
    <div className={cx("flex flex-col gap-6 transition-opacity", dim && "opacity-60")}>
      <section aria-label="Answer" className="rounded-2xl bg-paper px-6 py-5 shadow-[var(--shadow-card)]">
        <p className="text-[0.8rem] text-muted">{MODE_LABEL[answer.mode] ?? answer.mode} · {answer.question}</p>
        <p className="mt-2 max-w-[72ch] text-[1.05rem] leading-relaxed">
          <CitedText text={answer.answer} onMarker={onMarker} titles={cites.map((c) => c.title)} />
        </p>
        {!answer.grounded && (
          <p className="mt-4 flex items-start gap-2 rounded-xl bg-warn-soft px-3 py-2.5 text-[0.9333rem] text-warn">
            <Warning size={18} className="mt-0.5 shrink-0" />
            {cites.length ? "Not every sentence is backed by a source. Read the passages before you rely on it." : "No passage supports an answer. Try other words, or search the passages."}
          </p>
        )}
      </section>
      {cites.length > 0 && (
        <section aria-labelledby="kb-sources">
          <h2 id="kb-sources" className="mb-3 text-[0.9333rem] font-semibold">Sources <span className="tnum font-normal text-muted">{cites.length}</span></h2>
          <HitList label="Sources">
            {cites.map((h, i) => <HitRow key={`${h.id}-${i}`} hit={h} index={i + 1} flash={flash === i + 1} onOpen={onOpen} />)}
          </HitList>
        </section>
      )}
    </div>
  );
}

function SearchView({ hits, onOpen, dim, onAll }: { hits: { q: string; kind: string; list: KbHit[] }; onOpen: (h: KbHit) => void; dim: boolean; onAll: () => void }) {
  if (!hits.list.length) {
    return (
      <EmptyState
        icon={<BookOpenText size={20} />}
        title={`Nothing matches “${hits.q}”${hits.kind ? ` in ${KINDS.find(([v]) => v === hits.kind)?.[1].toLowerCase() ?? hits.kind}` : ""}`}
        action={hits.kind ? <Button size="sm" onClick={onAll}>Search all kinds</Button> : undefined}
      >
        Try other words, a rule ID such as PAY-03, or an article such as art. 173.
      </EmptyState>
    );
  }
  return (
    <div className={cx("transition-opacity", dim && "opacity-60")}>
      <p className="mb-3 text-[0.8667rem] text-muted">
        {plural(hits.list.length, "passage", "passages")} for “{hits.q}”, best first. Ranked by keyword and by meaning, then fused.
      </p>
      <HitList label="Passages">
        {hits.list.map((h) => <HitRow key={h.id} hit={h} onOpen={onOpen} />)}
      </HitList>
    </div>
  );
}

function ResultSkeleton({ ask }: { ask: boolean }) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-4">
      {ask && <Skeleton className="h-28 rounded-2xl" />}
      <div className="overflow-hidden rounded-2xl bg-paper shadow-[var(--shadow-card)]">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex flex-col gap-2 border-b border-line px-5 py-4 last:border-b-0">
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function StatsLine({ stats }: { stats?: KbStats }) {
  const split = stats?.by_kind ?? (typeof stats?.chunks === "object" ? stats.chunks : undefined);
  if (!stats || !split) return null;
  const entries = Object.entries(split).filter(([, n]) => typeof n === "number" && n > 0);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  const parts = entries.map(([k, n]) => {
    const [one, many] = KIND_PLURAL[k] ?? [k.replace(/_/g, " "), k.replace(/_/g, " ")];
    return plural(n, one, many);
  });
  return (
    <p className="mt-12 text-[0.8rem] leading-relaxed text-subtle">
      {num(total)} passages: {parts.join(", ")}.{" "}
      {(stats.dense_available ?? stats.dense) === false ? "Keyword search only." : `Search by keyword and by meaning${stats.embedding_model ? ` (${stats.embedding_model})` : ""}.`}
      {stats.built_at ? ` Index built ${dateTime(stats.built_at)}.` : ""}
    </p>
  );
}
