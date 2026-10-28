import { Check, FileStack, X } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { clock, dateTime, relative } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { PolicyDecision } from "../../api/types";
import { EmptyState, ErrorNote, IdTag, PageHeader, SectionBoundary, Tabs, useNowTick } from "../../ui/kit";
import { SkeletonRows, StaleNote, TableFrame, TD, TH } from "./ui";

type Filter = "toate" | "refuzate" | "permise";
const isFilter = (v: string | null): v is Filter => v === "toate" || v === "refuzate" || v === "permise";

function isDecision(x: unknown): x is PolicyDecision {
  return Boolean(x) && typeof x === "object" && typeof (x as PolicyDecision).allowed === "boolean" && typeof (x as PolicyDecision).action === "string";
}

/** Mock: o listă. Backend: `{decisions: [...], denials: [...]}` (refuzurile pot apărea în ambele). */
function normalize(data: unknown): PolicyDecision[] {
  const raw: unknown[] = Array.isArray(data)
    ? data
    : data && typeof data === "object"
      ? [
          ...(Array.isArray((data as { decisions?: unknown }).decisions) ? (data as { decisions: unknown[] }).decisions : []),
          ...(Array.isArray((data as { denials?: unknown }).denials) ? (data as { denials: unknown[] }).denials : []),
        ]
      : [];
  const seen = new Set<string>();
  const out: PolicyDecision[] = [];
  for (const d of raw) {
    if (!isDecision(d)) continue;
    const key = `${d.at ?? ""}|${d.principal}|${d.action}|${d.resource}|${d.allowed}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(d);
  }
  return out.sort((a, b) => (new Date(b.at ?? 0).getTime() || 0) - (new Date(a.at ?? 0).getTime() || 0));
}

/** `Agent::"Investigator/OSINT"` → „Investigator/OSINT”. */
function entityName(v: string | null | undefined): string {
  if (!v) return "—";
  const m = v.match(/^[A-Za-z_]+::"?(.+?)"?$/);
  return m ? m[1] : v;
}

function zoneOf(resource: string | null | undefined): { text: string; code: boolean } {
  const m = (resource ?? "").match(/zone::?"?([a-z_-]+)"?/i);
  if (m) {
    const z = m[1].toLowerCase();
    if (z === "aml") return { text: "Zona AML", code: false };
    if (z === "client") return { text: "Zona client", code: false };
    return { text: z, code: true };
  }
  return { text: resource || "—", code: Boolean(resource) };
}

function Outcome({ allowed }: { allowed: boolean }) {
  return allowed ? (
    <span className="inline-flex items-center gap-1.5 font-semibold whitespace-nowrap text-ok">
      <Check aria-hidden className="size-4" strokeWidth={2.5} />
      Permis
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 font-semibold whitespace-nowrap text-danger">
      <X aria-hidden className="size-4" strokeWidth={2.5} />
      Refuzat
    </span>
  );
}

export default function AccessLogPage() {
  const api = useApi();
  const [params, setParams] = useSearchParams();
  const now = useNowTick(30_000);
  const res = useResource(() => api.amlWall(), [api], { pollMs: 5000 });
  const rows = useMemo(() => normalize(res.data), [res.data]);
  const denied = rows.filter((r) => !r.allowed).length;
  const asked = params.get("filtru");
  const filter: Filter = isFilter(asked) ? asked : "toate";
  const visible = filter === "toate" ? rows : rows.filter((r) => (filter === "refuzate" ? !r.allowed : r.allowed));
  const setFilter = (f: Filter) => {
    const next = new URLSearchParams(params);
    next.set("filtru", f);
    setParams(next, { replace: true });
  };

  return (
    <div>
      <PageHeader
        title="Jurnal de acces"
        description="Fiecare apel al unui agent sau al unui om din zona AML trece prin politicile de acces. Ce nu e permis explicit e refuzat."
      />
      <SectionBoundary label="Jurnal de acces">
        {res.error && !res.data ? (
          <ErrorNote error={res.error} what="jurnalul de acces" onRetry={() => void res.reload()} />
        ) : !res.loading && !rows.length ? (
          <EmptyState icon={<FileStack aria-hidden className="size-5" />} title="Nicio decizie de acces încă.">
            Apar aici imediat ce agenții sau analiștii apelează un tool în zona AML: ce s-a cerut, cine a cerut și de ce s-a permis sau refuzat.
          </EmptyState>
        ) : (
          <>
            <div className="mb-4">
              <Tabs<Filter>
                label="Filtrează deciziile"
                value={filter}
                onChange={setFilter}
                tabs={[
                  { id: "toate", label: "Toate", count: rows.length },
                  { id: "refuzate", label: "Refuzate", count: denied },
                  { id: "permise", label: "Permise", count: rows.length - denied },
                ]}
              />
            </div>
            <StaleNote error={res.data ? res.error : undefined} every="5 s" />
            {!res.loading && !visible.length ? (
              <EmptyState title={filter === "refuzate" ? "Niciun refuz în jurnal." : "Nicio cerere permisă în jurnal."}>
                Jurnalul se actualizează la 5 secunde.
              </EmptyState>
            ) : (
              <TableFrame label="Decizii de acces" minWidth={920}>
                <thead>
                  <tr>
                    <th scope="col" className={TH}>Ora</th>
                    <th scope="col" className={TH}>Cine</th>
                    <th scope="col" className={TH}>Acțiune</th>
                    <th scope="col" className={TH}>Zona</th>
                    <th scope="col" className={TH}>Rezultat</th>
                    <th scope="col" className={TH}>Motiv</th>
                  </tr>
                </thead>
                <tbody>
                  {res.loading && !rows.length ? (
                    <SkeletonRows cols={6} />
                  ) : (
                    visible.map((d, i) => {
                      const zone = zoneOf(d.resource);
                      return (
                        <tr key={`${d.at ?? i}-${d.action}-${i}`} className="hover:bg-hover">
                          <td className={`${TD} whitespace-nowrap`} title={dateTime(d.at)}>
                            <span className="tabular-nums">{clock(d.at)}</span>
                            <span className="block text-[0.8667rem] text-muted">{relative(d.at, now)}</span>
                          </td>
                          <td className={TD} title={d.principal}>
                            {entityName(d.principal)}
                          </td>
                          <td className={TD}>
                            <span className="font-mono text-[0.8667rem] break-all">{d.action}</span>
                          </td>
                          <td className={TD}>{zone.code ? <span className="font-mono text-[0.8667rem]">{zone.text}</span> : zone.text}</td>
                          <td className={TD}>
                            <Outcome allowed={d.allowed} />
                          </td>
                          <td className={`${TD} max-w-[34rem]`}>
                            {d.reason ? <p className="line-clamp-2 text-[0.9333rem]" title={d.reason}>{d.reason}</p> : <span className="text-muted">—</span>}
                            {Array.isArray(d.policy_ids) && d.policy_ids.length > 0 && (
                              <span className="mt-1 flex flex-wrap gap-1">
                                {d.policy_ids.map((p) => (
                                  <IdTag key={p}>{p}</IdTag>
                                ))}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </TableFrame>
            )}
          </>
        )}
      </SectionBoundary>
    </div>
  );
}
