import { CircleCheck, CircleMinus, CircleX, FileQuestion, RefreshCw } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { dateTime, relative, statusLabel } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import { Badge, Button, cx, EmptyState, ErrorNote, KeyValues, PageHeader, Panel, SectionBoundary, Skeleton, useNowTick } from "../../ui/kit";
import {
  APPROX_TOLERANCE,
  get,
  isObj,
  normalizeEval,
  outcome,
  pct,
  showMetric,
  showTarget,
  showValue,
  type EvalRow,
  type Obj,
  type Outcome,
} from "./evalReport";
import { CodeBlock, InlineCode, TABLE } from "./trustUi";
import { EvalVisuals } from "./EvalVisuals";

const LLM_MODE: Record<string, string> = {
  live: "LLM live (Claude pe Bedrock)",
  replay: "LLM în replay (răspunsuri înregistrate)",
  offline: "fără LLM (reguli și șabloane)",
};

export default function EvalPage() {
  const api = useApi();
  const res = useResource(() => api.evalReport(), [api]);
  const model = useMemo(() => (res.data ? normalizeEval(res.data) : null), [res.data]);
  const now = useNowTick(60_000);

  const reloadButton = (
    <Button icon={<RefreshCw aria-hidden className="size-4" />} busy={res.loading && Boolean(res.data)} onClick={() => void res.reload()}>
      Reîncarcă raportul
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Evaluare"
        description="Ce am măsurat pe date sintetice: regulile pe setul de aur, zidul, confidențialitatea, injecțiile și modelele ML."
        actions={model?.kind === "report" ? reloadButton : undefined}
      >
        {model?.kind === "report" && (
          <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9333rem]">
            <span>
              Generat <span className="font-semibold">{dateTime(model.at)}</span>
              {model.at && <span className="text-muted"> ({relative(model.at, now)})</span>}
            </span>
            <span aria-hidden className="text-subtle">·</span>
            <span>{model.llmMode ? LLM_MODE[model.llmMode] ?? `LLM: ${model.llmMode}` : "mod LLM nespecificat"}</span>
            {model.simulated && <Badge>Raport simulat, mod demonstrativ</Badge>}
          </p>
        )}
      </PageHeader>

      {res.error && !res.data ? (
        <ErrorNote error={res.error} what="raportul de evaluare" onRetry={res.reload} />
      ) : !model ? (
        <div className="flex flex-col gap-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-11" />)}</div>
      ) : model.kind === "missing" ? (
        <Missing onRetry={() => void res.reload()} busy={res.loading} />
      ) : (
        <>
          {res.error && <p className="mb-3 text-[0.8667rem] text-danger">Nu am putut reîncărca raportul; afișez ultima versiune primită.</p>}
          <SectionBoundary label="Imaginea evaluării">
            <EvalVisuals sections={model.sections} />
          </SectionBoundary>
          <SectionBoundary label="Sinteza">
            <Summary rows={model.rows} />
          </SectionBoundary>
          <div className="mt-6 grid gap-4 xl:grid-cols-2">
            <SectionBoundary label="Reguli">
              <RulesSection golden={model.sections.rules_golden} generated={model.sections.rules_generated} />
            </SectionBoundary>
            <SectionBoundary label="Zid și neinterferență">
              <NonInterference data={model.sections.noninterference} />
            </SectionBoundary>
            <SectionBoundary label="Filtrul de scrisori">
              <LetterFilter data={model.sections.letter_filter} />
            </SectionBoundary>
            <SectionBoundary label="Confidențialitate și injecții">
              <PrivacyInjection privacy={model.sections.privacy} injection={model.sections.injection} />
            </SectionBoundary>
            <div className="xl:col-span-2">
              <SectionBoundary label="Modele ML">
                <MlSection data={model.sections.ml} />
              </SectionBoundary>
            </div>
          </div>
          <details className="mt-6 rounded-lg border border-line bg-paper">
            <summary className="cursor-pointer px-4 py-3 font-semibold">Date brute</summary>
            <pre className="max-h-[32rem] overflow-auto border-t border-line bg-canvas px-4 py-3 font-mono text-[0.8667rem] leading-relaxed">
              {JSON.stringify(model.raw, null, 2)}
            </pre>
          </details>
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ stări

function Missing({ onRetry, busy }: { onRetry: () => void; busy: boolean }) {
  return (
    <EmptyState
      icon={<FileQuestion className="size-6" />}
      title="Raportul de evaluare nu a fost generat încă."
      action={
        <div className="flex w-full max-w-xl flex-col items-start gap-3">
          <CodeBlock className="w-full" label="În terminal, în folderul proiectului" code="uv run versoml eval" />
          <p className="text-[0.9333rem] text-muted">
            Varianta rapidă, fără rulările complete ale grafului: <InlineCode>uv run versoml eval --fast</InlineCode>
          </p>
          <Button icon={<RefreshCw aria-hidden className="size-4" />} busy={busy} onClick={onRetry}>Verifică din nou</Button>
        </div>
      }
    >
      Comanda rulează regulile pe setul de aur (40 de cazuri) și pe 300 de cazuri generate, testul de neinterferență, filtrul de scrisori și modelele ML, apoi scrie raportul. Când se termină, apasă „Verifică din nou”.
    </EmptyState>
  );
}

function SectionNote({ data }: { data: unknown }): ReactNode {
  if (data === undefined || data === null) return <p className="text-[0.9333rem] text-muted">Lipsește din acest raport.</p>;
  if (isObj(data) && typeof data.status === "string") {
    return (
      <p className="text-[0.9333rem] text-danger">
        Secțiunea nu a rulat ({data.status}){typeof data.error === "string" ? `: ${data.error}` : "."}
      </p>
    );
  }
  return null;
}

// ------------------------------------------------------------------ sinteza

const OUTCOME: Record<Outcome, { word: string; icon: ReactNode; cls: string }> = {
  met: { word: "atins", icon: <CircleCheck aria-hidden className="size-4" />, cls: "text-ok" },
  below: { word: "sub țintă", icon: <CircleX aria-hidden className="size-4" />, cls: "text-danger" },
  na: { word: "n/a", icon: <CircleMinus aria-hidden className="size-4" />, cls: "text-muted" },
};

function Summary({ rows }: { rows: EvalRow[] }) {
  const results = rows.map((r) => outcome(r.value, r.target));
  const judged = results.filter((o) => o !== "na").length;
  const met = results.filter((o) => o === "met").length;
  const hasApprox = rows.some((r) => r.target?.trim().startsWith("≈"));
  return (
    <section aria-labelledby="eval-summary">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="eval-summary" className="text-[1.0667rem] font-semibold">Sinteză</h2>
        {judged > 0 && (
          <p className={cx("font-semibold", met === judged ? "text-ok" : "text-danger")}>
            {met} din {judged} ținte atinse
          </p>
        )}
      </div>
      {rows.length === 0 ? (
        <EmptyState title="Raportul nu are rânduri de sinteză.">Secțiunile de mai jos și datele brute sunt totuși disponibile.</EmptyState>
      ) : (
        <div className={TABLE.wrap}>
          <table className={cx(TABLE.table, "min-w-[40rem]")}>
            <thead>
              <tr className={TABLE.headRow}>
                <th scope="col" className={TABLE.th}>Metrică</th>
                <th scope="col" className={cx(TABLE.th, "text-right")}>Valoare</th>
                <th scope="col" className={cx(TABLE.th, "text-right")}>Țintă</th>
                <th scope="col" className={TABLE.th}>Rezultat</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const o = OUTCOME[results[i]];
                return (
                  <tr key={`${r.name}-${i}`} className={TABLE.row}>
                    <td className={TABLE.td}>{r.name}</td>
                    <td className={cx(TABLE.td, "text-right font-semibold whitespace-nowrap tabular-nums")}>{showValue(r.value, r.target)}</td>
                    <td className={cx(TABLE.td, "text-right whitespace-nowrap text-ink-soft tabular-nums")}>{showTarget(r.target, r.value)}</td>
                    <td className={cx(TABLE.td, "whitespace-nowrap")}>
                      <span className={cx("inline-flex items-center gap-1.5 font-medium", o.cls)}>
                        {o.icon}
                        {o.word}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {hasApprox && (
        <p className="mt-2 text-[0.8667rem] text-muted">
          Ținta „≈ 0” e considerată atinsă sub {pct(APPROX_TOLERANCE)}. „Comparație” marchează o linie de bază, fără țintă.
        </p>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ secțiuni

function kv(data: unknown, spec: Array<[string, string]>): Array<[ReactNode, ReactNode]> {
  if (!isObj(data)) return [];
  return spec
    .filter(([k]) => data[k] !== undefined && data[k] !== null)
    .map(([k, label]) => [label, <span key={k} className="font-medium tabular-nums">{k === "at" ? dateTime(String(data[k])) : showMetric(k, data[k])}</span>]);
}

function MetricTable({ rows, cols, first }: { rows: Array<{ label: ReactNode; data: unknown }>; cols: Array<[string, string]>; first: string }) {
  const present = rows.filter((r) => isObj(r.data));
  if (present.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full min-w-[30rem] border-collapse text-left text-[0.9333rem]">
        <thead>
          <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
            <th scope="col" className="px-3 py-2 font-semibold">{first}</th>
            {cols.map(([, label]) => <th key={label} scope="col" className="px-3 py-2 text-right font-semibold">{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {present.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-b-0">
              <td className="px-3 py-2">{r.label}</td>
              {cols.map(([k]) => (
                <td key={k} className="px-3 py-2 text-right whitespace-nowrap tabular-nums">
                  {isObj(r.data) && r.data[k] !== undefined && r.data[k] !== null ? showMetric(k, r.data[k]) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const RULE_ROWS: Array<[string, string]> = [
  ["cases", "Cazuri"],
  ["verdict_accuracy", "Verdict T+1 corect"],
  ["requires_human_accuracy", "Implicarea omului corectă"],
  ["escalation_recall", "Recall escaladări spre om"],
  ["deadline_accuracy", "Termene T+1 corecte"],
  ["recovery_accuracy", "Recuperare corectă"],
  ["ms_per_case", "Timp pe caz"],
];

function RulesSection({ golden, generated }: { golden: unknown; generated: unknown }) {
  const failures = [
    ...(Array.isArray(get(golden, "failures")) ? (get(golden, "failures") as unknown[]) : []),
    ...(Array.isArray(get(generated, "failures")) ? (get(generated, "failures") as unknown[]) : []),
  ].filter(isObj);
  const note = !isObj(golden) && !isObj(generated)
    ? <SectionNote data={undefined} />
    : isObj(golden) && typeof golden.status === "string"
      ? <SectionNote data={golden} />
      : isObj(generated) && typeof generated.status === "string"
        ? <SectionNote data={generated} />
        : null;
  return (
    <Panel title="Reguli: setul de aur și cazurile generate" className="h-full">
      {note}
      {(isObj(golden) || isObj(generated)) && (
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full min-w-[26rem] border-collapse text-left text-[0.9333rem]">
            <thead>
              <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
                <th scope="col" className="px-3 py-2 font-semibold">Indicator</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Set de aur</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Cazuri generate</th>
              </tr>
            </thead>
            <tbody>
              {RULE_ROWS.filter(([k]) => get(golden, k) !== undefined || get(generated, k) !== undefined).map(([k, label]) => (
                <tr key={k} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-2">{label}</td>
                  {[golden, generated].map((src, i) => {
                    const v = get(src, k);
                    return (
                      <td key={i} className="px-3 py-2 text-right font-medium whitespace-nowrap tabular-nums">
                        {v === undefined || v === null ? "—" : showMetric(k, v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <td className="px-3 py-2">Eșecuri</td>
                {[golden, generated].map((src, i) => {
                  const f = get(src, "failures");
                  return <td key={i} className="px-3 py-2 text-right font-medium tabular-nums">{Array.isArray(f) ? f.length : "—"}</td>;
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {failures.length > 0 && (
        <div className="mt-3">
          <p className="font-semibold text-danger">Cazuri greșite</p>
          <ul className="mt-1 flex flex-col gap-1 text-[0.9333rem]">
            {failures.slice(0, 12).map((f, i) => (
              <li key={i}>
                <code className="font-mono text-[0.8667rem]">{String(f.id ?? "—")}</code> ({String(f.scenario ?? "—")}): așteptat {String(f.expected ?? "—")}, obținut {String(f.got ?? "—")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function NonInterference({ data }: { data: unknown }) {
  const statuses = isObj(get(data, "statuses")) ? (get(data, "statuses") as Obj) : null;
  const rows = kv(data, [
    ["runs", "Rulări"],
    ["mismatches", "Decizii schimbate de zona AML"],
    ["leaks", "Scurgeri peste zid"],
    ["canaries_planted", "Canary plantate"],
    ["canary_hits_in_client_zone", "Canary găsite în zona client"],
    ["letters_failing_filter", "Scrisori care nu trec filtrul"],
    ["bytes_scanned", "Date scanate"],
    ["at", "Rulat la"],
  ]);
  return (
    <Panel title="Zid și neinterferență" className="h-full">
      <SectionNote data={data} />
      {rows.length > 0 && (
        <>
          <p className="mb-3 text-[0.9333rem] text-muted">Aceleași contestații, rulate cu zona AML goală și apoi plină de dosare cu canary.</p>
          <KeyValues rows={rows} />
        </>
      )}
      {statuses && Object.keys(statuses).length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-md border border-line">
          <table className="w-full min-w-[26rem] border-collapse text-left text-[0.9333rem]">
            <thead>
              <tr className="border-b border-line bg-canvas text-[0.8667rem] text-muted">
                <th scope="col" className="px-3 py-2 font-semibold">Scenariu</th>
                <th scope="col" className="px-3 py-2 font-semibold">AML goală</th>
                <th scope="col" className="px-3 py-2 font-semibold">AML plină</th>
                <th scope="col" className="px-3 py-2 font-semibold">Aceeași stare</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(statuses).map(([sid, pair]) => {
                const [a, b] = Array.isArray(pair) ? pair : [pair, undefined];
                const sameState = a !== undefined && a === b;
                return (
                  <tr key={sid} className="border-b border-line last:border-b-0">
                    <td className="px-3 py-2"><code className="font-mono text-[0.8667rem]">{sid}</code></td>
                    <td className="px-3 py-2">{statusLabel(a === undefined ? null : String(a))}</td>
                    <td className="px-3 py-2">{statusLabel(b === undefined ? null : String(b))}</td>
                    <td className="px-3 py-2">
                      <span className={cx("inline-flex items-center gap-1.5 font-medium", sameState ? "text-ok" : "text-danger")}>
                        {sameState ? <CircleCheck aria-hidden className="size-4" /> : <CircleX aria-hidden className="size-4" />}
                        {sameState ? "da" : "nu"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function LetterFilter({ data }: { data: unknown }) {
  const rows = kv(data, [
    ["adversarial", "Scrisori de tipping-off încercate"],
    ["blocked", "Blocate"],
    ["tipping_off_recall", "Recall tipping-off"],
    ["clean", "Scrisori curate"],
    ["false_blocks", "Scrisori curate blocate greșit"],
  ]);
  const examples = get(data, "false_block_examples");
  return (
    <Panel title="Filtrul de scrisori" className="h-full">
      <SectionNote data={data} />
      {rows.length > 0 && <KeyValues rows={rows} />}
      {Array.isArray(examples) && examples.length > 0 && (
        <div className="mt-3">
          <p className="font-semibold text-danger">Blocate greșit</p>
          <ul className="mt-1 list-disc pl-5 text-[0.9333rem]">{examples.map((e, i) => <li key={i}>{String(e)}</li>)}</ul>
        </div>
      )}
    </Panel>
  );
}

function PrivacyInjection({ privacy, injection }: { privacy: unknown; injection: unknown }) {
  const p = kv(privacy, [
    ["complaints_checked", "Reclamații verificate"],
    ["raw_pii_to_llm", "Date personale brute trimise LLM-ului"],
    ["pseudonyms_created", "Pseudonime create"],
  ]);
  const inj = kv(injection, [
    ["injection_cases", "Reclamații cu injecție"],
    ["detected", "Detectate"],
    ["detection_rate", "Rată de detecție"],
    ["false_positive_rate", "Alarme false pe reclamații curate"],
    ["decision_changed_by_injection", "Decizii schimbate de injecție"],
  ]);
  const note = get(injection, "note");
  return (
    <Panel title="Confidențialitate și injecții" className="h-full">
      <h3 className="text-[0.9333rem] font-semibold">Confidențialitate</h3>
      <div className="mt-2">{p.length > 0 ? <KeyValues rows={p} /> : <SectionNote data={privacy} />}</div>
      <h3 className="mt-4 border-t border-line pt-3 text-[0.9333rem] font-semibold">Injecții de prompt</h3>
      <div className="mt-2">{inj.length > 0 ? <KeyValues rows={inj} /> : <SectionNote data={injection} />}</div>
      {typeof note === "string" && <p className="mt-2 text-[0.9333rem] text-muted">{note}</p>}
    </Panel>
  );
}

const CLASS_COLS: Array<[string, string]> = [["accuracy", "Acuratețe"], ["macro_f1", "Macro-F1"], ["ece", "ECE"]];
const BIN_COLS: Array<[string, string]> = [["auc", "AUC"], ["pr_auc", "PR-AUC"], ["f1", "F1"], ["precision", "Precizie"], ["recall", "Recall"], ["threshold", "Prag"]];

function MlSection({ data }: { data: unknown }) {
  const status = get(data, "status");
  if (!isObj(data) || typeof status === "string") {
    return (
      <Panel title="Modele ML">
        {status === "neantrenat" ? (
          <p className="text-[0.9333rem]">
            Modelele nu sunt antrenate încă. Rulează <InlineCode>uv run versoml train</InlineCode>, apoi din nou evaluarea.
          </p>
        ) : (
          <SectionNote data={data} />
        )}
      </Panel>
    );
  }
  const m1 = get(data, "m1_classifier");
  const m2 = get(data, "m2_client_fraud");
  const m5 = get(data, "m5_mule");
  const version = (v: unknown) => (typeof v === "string" ? <code className="font-mono text-[0.8667rem]">{v}</code> : null);
  const note = get(data, "note");
  return (
    <Panel title="Modele ML">
      {typeof note === "string" && <p className="mb-4 text-[0.9333rem] text-muted">{note}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="font-semibold">M1 · clasificarea reclamației</h3>
          {isObj(m1) ? (
            <div className="mt-2 flex flex-col gap-3">
              <MetricTable
                first="Ce prezice"
                cols={CLASS_COLS}
                rows={[
                  { label: "Canalul", data: m1.channel },
                  { label: "Tipul disputei", data: m1.dispute_type },
                  { label: "Scenariul", data: m1.scenario },
                ]}
              />
              <KeyValues
                rows={[
                  m1.n_train !== undefined && ["Antrenare / test", <span key="n" className="tabular-nums">{showMetric("n", m1.n_train)} / {showMetric("n", m1.n_test)}</span>],
                  typeof m1.held_out === "string" && ["Cum am testat", <span key="h" className="text-[0.9333rem] text-ink-soft">{m1.held_out}</span>],
                  typeof m1.model_version === "string" && ["Versiune", version(m1.model_version)],
                ]}
              />
            </div>
          ) : (
            <SectionNote data={m1} />
          )}
        </div>
        <div className="min-w-0">
          <h3 className="font-semibold">M2 · semnal de fraudă a clientului</h3>
          {isObj(m2) ? (
            <div className="mt-2 flex flex-col gap-3">
              <MetricTable first="Set" cols={BIN_COLS} rows={[{ label: "Test separat", data: m2.held_out }]} />
              <KeyValues
                rows={[
                  m2.brier !== undefined && ["Brier", <span key="b" className="tabular-nums">{showMetric("brier", m2.brier)}</span>],
                  m2.fraud_rate !== undefined && ["Rata fraudei în date", <span key="f" className="tabular-nums">{showMetric("fraud_rate", m2.fraud_rate)}</span>],
                  typeof m2.note === "string" && ["Notă", <span key="n" className="text-[0.9333rem] text-ink-soft">{m2.note}</span>],
                  typeof m2.model_version === "string" && ["Versiune", version(m2.model_version)],
                ]}
              />
            </div>
          ) : (
            <SectionNote data={m2} />
          )}
        </div>
        <div className="min-w-0 lg:col-span-2">
          <h3 className="font-semibold">M5 · cont-cărăuș, față de liniile de bază</h3>
          {isObj(m5) ? (
            <div className="mt-2 flex flex-col gap-3">
              <MetricTable
                first="Model"
                cols={BIN_COLS}
                rows={[
                  { label: "Doar reguli (bază)", data: m5.rules_only },
                  { label: "GBDT fără graf", data: m5.gbdt_no_graph },
                  { label: <span className="font-semibold">GBDT pe graf</span>, data: m5.gbdt_graph ?? m5.graph_aware },
                  { label: "GBDT pe graf, prag 0,5", data: m5["gbdt_graph_at_0.5"] },
                ]}
              />
              <KeyValues
                rows={[
                  m5.n_accounts !== undefined && ["Conturi evaluate", <span key="a" className="tabular-nums">{showMetric("n", m5.n_accounts)}</span>],
                  m5.mule_rate !== undefined && ["Rata cărăușilor în date", <span key="r" className="tabular-nums">{showMetric("mule_rate", m5.mule_rate)}</span>],
                  m5.false_positive_rate_hard_negatives !== undefined && [
                    "Alarme false pe contraexemple dificile",
                    <span key="fp" className="tabular-nums">{showMetric("false_positive_rate", m5.false_positive_rate_hard_negatives)}</span>,
                  ],
                  typeof m5.cv === "string" && ["Validare", <span key="cv" className="text-[0.9333rem] text-ink-soft">{m5.cv}</span>],
                  typeof m5.model_version === "string" && ["Versiune", version(m5.model_version)],
                ]}
              />
            </div>
          ) : (
            <SectionNote data={m5} />
          )}
        </div>
      </div>
    </Panel>
  );
}
