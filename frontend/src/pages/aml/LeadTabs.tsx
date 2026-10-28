import { FileText, Search, ShieldCheck } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { clock, dateTime, shortHash } from "../../api/format";
import type { LeadDetail, OsintFinding } from "../../api/types";
import { Badge, cx, EmptyState, IdTag, KeyValues, Tabs } from "../../ui/kit";
import { capitalize, factKindLabel, humanizeKey, maskAccount, typologyLabel, type FactRow } from "./aml";
import { OsintGroups } from "./ui";

export type LeadTab = "rts" | "osint" | "probe";

type Cite = (id: string) => void;
type FactTitle = (id: string) => string | undefined;

// ------------------------------------------------------------------ ciorna RTS

function FieldValue({ k, v }: { k: string; v: unknown }) {
  if (v === null || v === undefined || v === "") return <span className="text-muted">—</span>;
  if (Array.isArray(v)) {
    const items = v.filter((x) => x !== null && x !== undefined && x !== "").map((x) => (typeof x === "string" ? x : JSON.stringify(x)));
    if (!items.length) return <span className="text-muted">—</span>;
    if (k === "conturi") {
      return (
        <span className="flex flex-wrap gap-1.5">
          {items.map((x) => (
            <span key={x} className="font-mono text-[0.8667rem]">
              {maskAccount(x)}
            </span>
          ))}
        </span>
      );
    }
    if (k === "tipologii") return <>{items.map((x) => typologyLabel(x)).join(", ")}</>;
    return (
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    );
  }
  if (typeof v === "object") return <span className="font-mono text-[0.8667rem] break-all">{JSON.stringify(v)}</span>;
  const s = String(v);
  if (k === "referinta_interna") return <span className="font-mono text-[0.8667rem] break-all">{s}</span>;
  return <>{s}</>;
}

export function RtsTab({ rts, onCite, factTitle, running }: { rts: LeadDetail["rts"]; onCite: Cite; factTitle: FactTitle; running: boolean }) {
  const narrative = Array.isArray(rts?.narrative) ? rts!.narrative.filter((l) => l && typeof l.text === "string") : [];
  const fields = rts?.fields && typeof rts.fields === "object" ? Object.entries(rts.fields) : [];
  if (!rts || (!narrative.length && !fields.length)) {
    return (
      <EmptyState icon={<FileText aria-hidden className="size-5" />} title={running ? "Agenții lucrează la ciorna RTS." : "Nu există o ciornă RTS pentru această pistă."}>
        {rts?.status && !running ? `Starea ciornei: ${rts.status}. ` : ""}
        Ciorna se scrie doar când regulile AML recomandă raportarea; fiecare frază trebuie să citeze o probă.
      </EmptyState>
    );
  }
  const rejected = typeof rts.rejected_without_citation === "number" ? rts.rejected_without_citation : 0;
  const status = rts.status ? capitalize(rts.status) : null;
  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[1rem] font-semibold">{rts.title || "Ciornă RTS"}</h3>
          {status && <Badge tone={/depus|depunere/i.test(status) ? "dark" : "neutral"}>{status}</Badge>}
        </div>
        <p className="mt-1 text-[0.8667rem] text-muted">Scrisă de agent, citită de tine. Agentul nu depune nimic; raportul îl trimite un om.</p>
      </div>
      {narrative.length > 0 && (
        <ol className="space-y-3">
          {narrative.map((l, i) => {
            const cites = Array.isArray(l.cites) ? l.cites.filter((c): c is string => typeof c === "string") : [];
            return (
              <li key={i} className="grid grid-cols-[1.5rem_1fr] gap-x-2">
                <span className="pt-px text-[0.8667rem] tabular-nums text-muted">{i + 1}.</span>
                <div>
                  <p>{l.text}</p>
                  {cites.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {cites.map((c) => (
                        <IdTag key={c} onClick={() => onCite(c)} title={factTitle(c) ?? `Deschide proba ${c}`}>
                          {c}
                        </IdTag>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {rejected > 0 && (
        <p className="text-[0.8667rem] text-muted">
          {rejected === 1 ? "O frază fără sursă a fost eliminată" : `${rejected} fraze fără sursă au fost eliminate`} din ciornă.
        </p>
      )}
      {fields.length > 0 && (
        <div className="border-t border-line pt-4">
          <h4 className="mb-3 text-[0.9333rem] font-semibold">Câmpurile formularului</h4>
          <KeyValues rows={fields.map(([k, v]) => [humanizeKey(k), <FieldValue key={k} k={k} v={v} />])} />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ OSINT

export function OsintTab({ findings, summary, onCite, factTitle, running }: { findings: OsintFinding[]; summary?: string | null; onCite: Cite; factTitle: FactTitle; running: boolean }) {
  if (!findings.length) {
    return (
      <EmptyState icon={<Search aria-hidden className="size-5" />} title={running ? "Pasul OSINT interoghează sursele." : "Nicio verificare OSINT încă."}>
        Agentul caută doar identificatori publici ai beneficiarului: firma, domeniul, telefonul, IBAN-ul. Niciodată date despre victime.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-4">
      {summary && <p className="max-w-[75ch]">{summary}</p>}
      <OsintGroups findings={findings} onCite={onCite} factTitle={factTitle} />
      <p className="text-[0.8667rem] text-muted">
        Vrei să verifici alt identificator?{" "}
        <Link to="/aml/osint" className="font-semibold text-ink underline">
          Deschide verificarea OSINT
        </Link>
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ probele

export function ProbeTab({ facts, highlight, ledger }: { facts: FactRow[]; highlight: { id: string; n: number } | null; ledger: LeadDetail["ledger"] }) {
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!highlight) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-fact="${CSS.escape(highlight.id)}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [highlight]);
  const missing = highlight && !facts.some((f) => f.fact_id === highlight.id) ? highlight.id : null;

  return (
    <div className="space-y-3">
      {ledger?.sealed && (
        <p className="flex flex-wrap items-center gap-2 text-[0.9333rem]">
          <ShieldCheck aria-hidden className="size-4 text-ok" />
          <span className="font-semibold text-ok">Dosar sigilat</span>
          {typeof ledger.count === "number" && <span>· {ledger.count} probe</span>}
          {ledger.root && (
            <span className="text-muted">
              · rădăcina{" "}
              <span className="font-mono text-[0.8667rem]" title={ledger.root}>
                {shortHash(ledger.root, 12)}
              </span>
            </span>
          )}
        </p>
      )}
      {missing && (
        <p role="status" className="text-[0.8667rem] text-muted">
          Proba <span className="font-mono">{missing}</span> nu e încă în lista de mai jos; apare când registrul se actualizează.
        </p>
      )}
      {!facts.length ? (
        <EmptyState icon={<ShieldCheck aria-hidden className="size-5" />} title="Nicio probă încă.">
          Fiecare pas al agenților scrie aici ce a aflat, cu hash; ciorna RTS poate cita doar aceste probe.
        </EmptyState>
      ) : (
        <ul ref={listRef} className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {facts.map((f) => {
            const lit = highlight?.id === f.fact_id;
            const kind = factKindLabel(f.kind);
            return (
              <li
                key={lit ? `${f.fact_id}-${highlight!.n}` : f.fact_id}
                data-fact={f.fact_id}
                className={cx("grid gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[6.5rem_1fr_auto]", lit && "animate-flash")}
              >
                <span>
                  <IdTag tone={lit ? "now" : "neutral"}>{f.fact_id}</IdTag>
                </span>
                <div className="min-w-0">
                  <p className="break-words">{f.summary || <span className="text-muted">Fără rezumat</span>}</p>
                  {(kind || f.kind || f.source_tool) && (
                    <p className="mt-0.5 text-[0.8667rem] text-muted">
                      {kind ?? <span className="font-mono">{f.kind}</span>}
                      {f.source_tool && (
                        <>
                          {" · "}
                          <span className="font-mono">{f.source_tool}</span>
                        </>
                      )}
                    </p>
                  )}
                </div>
                <div className="text-[0.8667rem] text-muted sm:text-right">
                  {f.sha256 && (
                    <p className="font-mono" title={`sha256 ${f.sha256}`}>
                      {shortHash(f.sha256, 10)}
                    </p>
                  )}
                  {f.retrieved_at && (
                    <p className="tabular-nums" title={dateTime(f.retrieved_at)}>
                      {clock(f.retrieved_at)}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ taburile

export function LeadTabs({ tab, onTab, detail, facts, highlight, onCite, factTitle, running }: {
  tab: LeadTab;
  onTab: (t: LeadTab) => void;
  detail: LeadDetail;
  facts: FactRow[];
  highlight: { id: string; n: number } | null;
  onCite: Cite;
  factTitle: FactTitle;
  running: boolean;
}) {
  const findings = Array.isArray(detail.osint) ? detail.osint.filter(Boolean) : [];
  return (
    <section aria-label="Ciorna RTS, OSINT și probe" className="rounded-lg border border-line bg-paper">
      <div className="px-4 pt-1">
        <Tabs<LeadTab>
          label="Detaliile pistei"
          value={tab}
          onChange={onTab}
          tabs={[
            { id: "rts", label: "Ciornă RTS" },
            { id: "osint", label: "OSINT", count: findings.length },
            { id: "probe", label: "Probe", count: facts.length },
          ]}
        />
      </div>
      <div role="tabpanel" aria-label={tab === "rts" ? "Ciornă RTS" : tab === "osint" ? "OSINT" : "Probe"} className="p-4">
        {tab === "rts" && <RtsTab rts={detail.rts} onCite={onCite} factTitle={factTitle} running={running} />}
        {tab === "osint" && <OsintTab findings={findings} summary={detail.osint_summary} onCite={onCite} factTitle={factTitle} running={running} />}
        {tab === "probe" && <ProbeTab facts={facts} highlight={highlight} ledger={detail.ledger} />}
      </div>
    </section>
  );
}
