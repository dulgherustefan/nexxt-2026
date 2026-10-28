import { useMemo } from "react";
import { duration, money, num, score as fmtScore } from "../../api/format";
import type { StreamStatus } from "../../api/sse";
import type { AccountScore, Deadline, InnocentHypothesis, RationaleLine, TypologyHit } from "../../api/types";
import { cx, DeadlineText, Dot, IdTag, Panel, STEP_STATUS_LABEL, StepIcon, useNowTick } from "../../ui/kit";
import { featureLabel, maskAccount, scoreLevel, typologyLabel, type StepView } from "./aml";
import { ScoreText } from "./ui";

type Cite = (id: string) => void;
type FactTitle = (id: string) => string | undefined;

function Cites({ ids, onCite, factTitle }: { ids: string[]; onCite: Cite; factTitle: FactTitle }) {
  if (!ids.length) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {ids.map((c) => (
        <IdTag key={c} onClick={() => onCite(c)} title={factTitle(c) ?? `Deschide proba ${c}`}>
          {c}
        </IdTag>
      ))}
    </span>
  );
}

// ------------------------------------------------------------------ scorul M5

export function ScorePanel({ accounts }: { accounts: AccountScore[] | null | undefined }) {
  const list = (Array.isArray(accounts) ? accounts : []).filter((a) => a && typeof a.score === "number");
  const top = list[0];
  if (!top) {
    return (
      <p className="text-[0.9333rem] text-muted">Scorul apare după pasul „Graf + ML”.</p>
    );
  }
  const lvl = scoreLevel(top.score, top.label);
  const factors = (Array.isArray(top.top_features) ? top.top_features : [])
    .filter((f): f is [string, number] => Array.isArray(f) && typeof f[0] === "string")
    .map(([name, value]) => ({ name, value: Number(value) || 0, ...featureLabel(name) }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 3);
  const maxAbs = Math.max(1e-9, ...factors.map((f) => Math.abs(f.value)));
  const others = list.slice(1, 4);
  const high = lvl?.level === "high";
  return (
    <div>
      <div className="flex items-baseline gap-3">
        <span className={cx("text-[1.5rem] leading-none font-semibold tabular-nums", high && "text-danger")}>{fmtScore(top.score)}</span>
        {lvl && <span className={cx("font-semibold", high ? "text-danger" : "text-ink-soft")}>{lvl.word}</span>}
      </div>
      <p className="mt-1.5 text-[0.8667rem] text-muted">
        {lvl ? `${lvl.label} · ` : ""}
        <span className="font-mono">{maskAccount(top.account)}</span>
      </p>

      {factors.length > 0 && (
        <>
          <h3 className="mt-4 text-[0.9333rem] font-semibold">Ce a cântărit cel mai mult</h3>
          <ul className="mt-2 space-y-2.5">
            {factors.map((f) => (
              <li key={f.name}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className={cx("min-w-0", f.code && "font-mono text-[0.8667rem] break-all")}>{f.text}</span>
                  <span className="shrink-0 text-[0.8667rem] tabular-nums text-muted">
                    {f.value >= 0 ? "+" : "−"}
                    {num(Math.abs(f.value), 2)}
                  </span>
                </div>
                <div aria-hidden className="mt-1 h-1.5 rounded-full bg-hover">
                  <div className={cx("h-full rounded-full", f.value >= 0 ? "bg-ink" : "bg-line-strong")} style={{ width: `${Math.max(4, (Math.abs(f.value) / maxAbs) * 100)}%` }} />
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[0.8667rem] text-muted">Contribuția fiecărui factor la scor (SHAP); „+” împinge spre cărăuș.</p>
        </>
      )}

      {others.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <h3 className="text-[0.9333rem] font-semibold">Alte conturi din pistă</h3>
          <ul className="mt-2 space-y-1.5">
            {others.map((a) => (
              <li key={a.account} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate font-mono text-[0.8667rem]">{maskAccount(a.account)}</span>
                <ScoreText score={a.score} label={a.label} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-4 text-[0.8667rem] text-muted">Scorul ajută la prioritizare. Decid regulile și tu.</p>
    </div>
  );
}

// ------------------------------------------------------------------ pentru și contra (ACH)

interface Hyp {
  text: string;
  supports: string[];
  against: string[];
  cites: string[];
  check: string | null;
  split: boolean;
}

function hypotheses(detail: InnocentHypothesis[] | null | undefined, lines: RationaleLine[] | null | undefined): Hyp[] {
  const ids = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  if (Array.isArray(detail) && detail.length) {
    return detail
      .filter((h) => h && typeof h.hypothesis === "string")
      .map((h) => ({ text: h.hypothesis, supports: ids(h.supports), against: ids(h.against), cites: [], check: h.check ?? null, split: true }));
  }
  return (Array.isArray(lines) ? lines : [])
    .filter((l) => l && typeof l.text === "string")
    .map((l) => ({ text: l.text, supports: [], against: [], cites: ids(l.cites), check: null, split: false }));
}

interface Typ {
  key: string;
  label: string;
  explanation: string | null;
  ruleId: string | null;
  amount: number | null;
}

function typologies(detail: TypologyHit[] | null | undefined, names: string[] | null | undefined): Typ[] {
  if (Array.isArray(detail) && detail.length) {
    return detail
      .filter(Boolean)
      .map((t, i) => {
        const key = String(t.typology ?? t.name ?? `t${i}`);
        return {
          key: `${key}-${t.center ?? i}`,
          label: typologyLabel(t.name ?? t.typology ?? key),
          explanation: typeof t.explanation === "string" ? t.explanation : null,
          ruleId: typeof t.rule_id === "string" ? t.rule_id : null,
          amount: typeof t.amount === "number" ? t.amount : null,
        };
      });
  }
  return (Array.isArray(names) ? names : []).filter(Boolean).map((n) => ({ key: n, label: typologyLabel(n), explanation: null, ruleId: null, amount: null }));
}

export function AchPanel({ innocentDetail, innocent, typologyDetail, typologyNames, onCite, factTitle, showTypologies = true }: {
  showTypologies?: boolean;
  innocentDetail?: InnocentHypothesis[] | null;
  innocent?: RationaleLine[] | null;
  typologyDetail?: TypologyHit[] | null;
  typologyNames?: string[] | null;
  onCite: Cite;
  factTitle: FactTitle;
}) {
  const hyps = useMemo(() => hypotheses(innocentDetail, innocent), [innocentDetail, innocent]);
  const typs = useMemo(() => typologies(typologyDetail, typologyNames), [typologyDetail, typologyNames]);
  return (
    <div className="max-w-[72ch]">
      <p className="text-[0.8667rem] text-muted">Înainte de orice raport, agentul caută explicații nevinovate pentru tiparele găsite.</p>

      {showTypologies && <h3 className="mt-4 text-[0.9333rem] font-semibold">Tipare care susțin suspiciunea</h3>}
      {!showTypologies ? null : typs.length ? (
        <ul className="mt-2 space-y-2">
          {typs.map((t) => (
            <li key={t.key} className="text-[0.9333rem]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{t.label}</span>
                {t.ruleId && <IdTag>{t.ruleId}</IdTag>}
                {t.amount !== null && <span className="text-[0.8667rem] tabular-nums text-muted">{money(t.amount)}</span>}
              </div>
              {t.explanation && <p className="mt-0.5 text-[0.8667rem] text-ink-soft">{t.explanation}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-muted">Niciun tipar detectat încă.</p>
      )}

      {showTypologies && <h3 className="mt-5 text-[0.9333rem] font-semibold">Explicații nevinovate verificate</h3>}
      {hyps.length ? (
        <ol className="mt-2 space-y-3">
          {hyps.map((h, i) => (
            <li key={i} className="rounded-md border border-line p-3">
              <p className="text-[0.9333rem]">
                <span className="mr-1 font-semibold tabular-nums">I{i + 1}.</span>
                {h.text}
              </p>
              <dl className="mt-2 grid grid-cols-[4.5rem_1fr] items-start gap-x-2 gap-y-1.5 text-[0.8667rem]">
                {h.split ? (
                  <>
                    <dt className="pt-0.5 text-muted">Pentru</dt>
                    <dd>
                      <Cites ids={h.supports} onCite={onCite} factTitle={factTitle} />
                    </dd>
                    <dt className="pt-0.5 text-muted">Contra</dt>
                    <dd>
                      <Cites ids={h.against} onCite={onCite} factTitle={factTitle} />
                    </dd>
                  </>
                ) : (
                  <>
                    <dt className="pt-0.5 text-muted">Probe</dt>
                    <dd>
                      <Cites ids={h.cites} onCite={onCite} factTitle={factTitle} />
                    </dd>
                  </>
                )}
                {h.check && (
                  <>
                    <dt className="text-muted">De verificat</dt>
                    <dd className="text-ink-soft">{h.check}</dd>
                  </>
                )}
              </dl>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-1 text-muted">Avocatul nevinovăției nu a rulat încă pe această pistă.</p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ ceasurile legale

export function ClocksPanel({ clocks }: { clocks: Deadline[] | null | undefined }) {
  const list = (Array.isArray(clocks) ? clocks : [])
    .filter((c) => c && (c.due_at || c.name))
    .slice()
    .sort((a, b) => (new Date(a.due_at).getTime() || Infinity) - (new Date(b.due_at).getTime() || Infinity));
  return (
    <Panel title="Ceasuri">
      {list.length ? (
        <ul className="divide-y divide-line">
          {list.map((c, i) => (
            <li key={`${c.rule_id}-${i}`} className="py-2.5 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 text-[0.9333rem]">{c.name || "Termen"}</p>
                <DeadlineText deadline={c.due_at} className="shrink-0 text-[0.9333rem]" />
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-[0.8667rem] text-muted">
                {c.rule_id && <IdTag>{c.rule_id}</IdTag>}
                {c.basis}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">Niciun termen legal pornit pentru această pistă.</p>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------ pașii agenților

function StreamState({ status }: { status: StreamStatus }) {
  const open = status === "open";
  return (
    <span className="inline-flex items-center gap-1.5 text-[0.8667rem] text-muted" title={open ? "Pașii vin pe loc prin SSE" : "SSE indisponibil: actualizez prin polling"}>
      <Dot tone="neutral" live={open} className={open ? "bg-ink" : undefined} />
      {open ? "Live" : status === "connecting" || status === "reconnecting" ? "Reconectez · actualizez la 3 s" : "Actualizez la 3 s"}
    </span>
  );
}

export function StepsPanel({ steps, streamStatus, hasRun }: { steps: StepView[]; streamStatus: StreamStatus; hasRun: boolean }) {
  const running = steps.some((s) => s.status === "running");
  const now = useNowTick(running ? 1000 : 30_000);
  return (
    <Panel title="Pașii agenților" actions={<StreamState status={streamStatus} />}>
      {!hasRun && <p className="mb-3 text-[0.8667rem] text-muted">Nicio rulare înregistrată pentru această pistă.</p>}
      <ol className="space-y-3">
        {steps.map((s) => {
          const elapsed =
            s.status === "running" && s.startedAt
              ? duration((now - s.startedAt) / 1000)
              : s.status === "done" && s.startedAt && s.finishedAt && s.finishedAt >= s.startedAt
                ? duration((s.finishedAt - s.startedAt) / 1000)
                : null;
          const text = s.summary ?? (s.status === "idle" ? s.hint : undefined);
          return (
            <li key={s.id} className="flex gap-3" aria-current={s.status === "running" || s.status === "waiting" ? "step" : undefined}>
              <span className="mt-1 shrink-0">
                <StepIcon status={s.status} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <p className={cx("font-semibold", s.status === "idle" && "text-muted")}>{s.label}</p>
                  {elapsed && <span className="shrink-0 text-[0.8667rem] tabular-nums text-muted">{elapsed}</span>}
                </div>
                <p className="line-clamp-2 text-[0.8667rem] text-muted" title={text}>
                  <span className={cx(s.status === "waiting" && "font-semibold text-ink", s.status === "error" && "font-semibold text-danger")}>
                    {STEP_STATUS_LABEL[s.status] ?? s.status}
                  </span>
                  {text ? ` · ${text}` : ""}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
