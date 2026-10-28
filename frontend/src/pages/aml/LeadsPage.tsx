import { Search, Waypoints } from "lucide-react";
import { lazy, Suspense, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { dateTime, money, relative, scenarioLabel, toMoney, verdictLabel } from "../../api/format";
import { useApi, useResource, type Resource } from "../../api/runtime";
import type { LeadSummary, Referral } from "../../api/types";
import { Button, EmptyState, ErrorNote, IdTag, PageHeader, SectionBoundary, Skeleton, Tabs, useNowTick } from "../../ui/kit";
import { Bar, BigStat } from "../../ui/viz";
import { GROUP_ORDER, leadStatus, maskAccount, typologyLabel, type LeadGroup } from "./aml";
import { Account, LeadStatusText, rowClick, ScoreText, SkeletonRows, StaleNote, TableFrame, TD, TH } from "./ui";

const MoneyGraph = lazy(() => import("../../graph/MoneyGraph"));

/** Imaginea de ansamblu a zonei AML: cifrele, campaniile și rețeaua conturilor semnalate. */
function AmlOverview() {
  const api = useApi();
  const stats = useResource(() => api.amlStats(), [api], { pollMs: 5000 });
  const campaigns = useResource(() => api.amlCampaigns(), [api], { pollMs: 8000 });
  const network = useResource(() => api.amlGraph(), [api], { pollMs: 10000 });
  const s = stats.data;
  const list = Array.isArray(campaigns.data) ? campaigns.data : [];
  const max = Math.max(1, ...list.map((c) => toMoney(c.amount_total)?.value ?? 0));
  return (
    <div className="mb-6 flex flex-col gap-6">
      <section aria-label="Cifrele zonei AML" className="grid gap-px overflow-hidden rounded-xl border-2 border-ink bg-ink sm:grid-cols-3 xl:grid-cols-6">
        {[
          ["Contestații primite", s?.referrals, "prin diodă, fără identitatea victimei"],
          ["Piste", s?.leads, "conturi legate între ele"],
          ["Conturi semnalate", s?.accounts_flagged, "scor M5 ≥ 0,70"],
          ["Bani în risc", s ? money(s.amount_at_risk) : undefined, "suma contestată"],
          ["Ciorne RTS", s?.rts_drafts, "le depune doar analistul"],
          ["Comunități", s?.communities, "Louvain pe graful banilor"],
        ].map(([label, value, sub]) => (
          <div key={String(label)} className="bg-paper px-4 py-3.5">
            {s ? <BigStat label={label} value={value ?? "—"} sub={sub} /> : <Skeleton className="h-16" />}
          </div>
        ))}
      </section>
      <div className="grid items-start gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <section aria-label="Campanii" className="rounded-xl border border-line bg-paper p-4">
          <h2 className="font-bold">Campanii</h2>
          <p className="text-[0.8667rem] text-muted">Victime legate prin același domeniu, IBAN sau telefon.</p>
          {list.length === 0 ? (
            <p className="mt-3 text-[0.9333rem] text-muted">Nicio campanie încă.</p>
          ) : (
            <ul className="mt-3 flex flex-col gap-3">
              {list.map((c) => {
                const amount = toMoney(c.amount_total)?.value ?? 0;
                const n = Array.isArray(c.cases) ? c.cases.length : Number(c.cases);
                return (
                  <li key={c.campaign_id}>
                    <div className="flex items-baseline justify-between gap-2">
                      <IdTag>{c.campaign_id}</IdTag>
                      <span className="font-black tabular-nums">{money(amount)}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2"><Bar value={amount / max} tone="danger" height={10} /><span className="shrink-0 text-[0.8rem] text-muted">{n === 1 ? "o victimă" : `${n} victime`}</span></div>
                    <p className="mt-1 flex flex-wrap gap-1.5 text-[0.75rem]">
                      {(c.shared.domains ?? []).map((d) => <span key={d} className="rounded-sm bg-danger-soft px-1.5 py-0.5 font-mono text-danger">{d}</span>)}
                      {(c.shared.ibans ?? []).map((d) => <span key={d} className="rounded-sm bg-canvas px-1.5 py-0.5 font-mono">{d}</span>)}
                      {(c.shared.phones ?? []).map((d) => <span key={d} className="rounded-sm bg-canvas px-1.5 py-0.5 font-mono">{d}</span>)}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <SectionBoundary label="Rețeaua">
          <Suspense fallback={<Skeleton className="h-80 rounded-xl" />}>
            {network.data && (network.data.edges?.length ?? 0) > 0 ? (
              <MoneyGraph graph={network.data} title="Rețeaua conturilor semnalate" height={380} />
            ) : (
              <EmptyState title="Rețeaua apare după prima pistă.">Graful unește toate pistele: victime, conturile urmărite și ieșirile spre cripto sau numerar.</EmptyState>
            )}
          </Suspense>
        </SectionBoundary>
      </div>
    </div>
  );
}

type TabId = "asteapta" | "analiza" | "inchise" | "toate";
const TAB_GROUP: Record<Exclude<TabId, "toate">, LeadGroup> = { asteapta: "waiting", analiza: "active", inchise: "closed" };
const isTab = (v: string | null): v is TabId => v === "asteapta" || v === "analiza" || v === "inchise" || v === "toate";

interface LeadRow {
  lead: LeadSummary;
  group: LeadGroup;
  account: string | null;
  cases: number;
  amount: number | null;
  updated: number;
}

function leadHref(id: string) {
  return `/aml/piste/${encodeURIComponent(id)}`;
}

/** Contul principal și suma contestată: din contestațiile primite pentru pista respectivă. */
function enrich(leads: LeadSummary[], refs: Referral[]): LeadRow[] {
  const byLead = new Map<string, Referral[]>();
  for (const r of refs) {
    if (!r?.lead_id) continue;
    const list = byLead.get(r.lead_id) ?? [];
    list.push(r);
    byLead.set(r.lead_id, list);
  }
  return leads
    .filter((l) => l && typeof l.lead_id === "string")
    .map((lead) => {
      const mine = byLead.get(lead.lead_id) ?? [];
      const counts = new Map<string, number>();
      for (const r of mine) if (r.beneficiary_iban_masked) counts.set(r.beneficiary_iban_masked, (counts.get(r.beneficiary_iban_masked) ?? 0) + 1);
      const account = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
      const amount = mine.length ? mine.reduce((s, r) => s + (toMoney(r.amount)?.value ?? 0), 0) : null;
      const caseIds = Array.isArray(lead.case_ids) ? lead.case_ids : [];
      return {
        lead,
        group: leadStatus(lead.status)?.group ?? "active",
        account,
        cases: caseIds.length || mine.length,
        amount,
        updated: new Date(lead.updated_at ?? 0).getTime() || 0,
      };
    })
    .sort((a, b) => GROUP_ORDER[a.group] - GROUP_ORDER[b.group] || (b.lead.top_score ?? 0) - (a.lead.top_score ?? 0) || b.updated - a.updated);
}

function Typologies({ items }: { items: string[] | null | undefined }) {
  const list = (Array.isArray(items) ? items : []).filter(Boolean).map((t) => typologyLabel(t));
  if (!list.length) return <span className="text-muted">—</span>;
  const shown = list.slice(0, 2);
  const rest = list.length - shown.length;
  return (
    <span title={list.join(", ")} className="whitespace-nowrap">
      {shown.join(", ")}
      {rest > 0 && <span className="ml-1 text-muted">+{rest}</span>}
    </span>
  );
}

function OsintSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = q.trim();
    if (t) navigate(`/aml/osint?q=${encodeURIComponent(t)}`);
  };
  return (
    <form role="search" aria-label="Verifică un identificator" onSubmit={submit} className="flex w-full items-center gap-2 sm:w-auto">
      <div className="relative min-w-0 flex-1 sm:w-72 sm:flex-none">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Identificator de verificat: domeniu, URL, telefon, CUI, IBAN sau firmă"
          placeholder="Verifică un identificator"
          className="h-10 w-full rounded-md border border-line-strong bg-paper pr-3 pl-9 text-[0.9333rem]"
        />
      </div>
      <Button type="submit">Verifică</Button>
    </form>
  );
}

function LeadsTable({ rows, loading, now }: { rows: LeadRow[]; loading: boolean; now: number }) {
  const navigate = useNavigate();
  return (
    <TableFrame label="Piste AML" minWidth={980}>
      <thead>
        <tr>
          <th scope="col" className={TH}>Pistă</th>
          <th scope="col" className={TH}>Cont principal</th>
          <th scope="col" className={TH}>Contestații</th>
          <th scope="col" className={TH}>Scor M5</th>
          <th scope="col" className={TH}>Tipologii</th>
          <th scope="col" className={TH}>Recomandare</th>
          <th scope="col" className={TH}>Stare</th>
          <th scope="col" className={TH}>Actualizat</th>
        </tr>
      </thead>
      <tbody>
        {loading && !rows.length ? (
          <SkeletonRows cols={8} />
        ) : (
          rows.map((r) => {
            const s = leadStatus(r.lead.status);
            const notScored = !r.lead.top_score && (s?.key === "NOU" || s?.key === "IN_ANALIZA");
            return (
              <tr key={r.lead.lead_id} onClick={rowClick(() => navigate(leadHref(r.lead.lead_id)))} className="cursor-pointer hover:bg-hover">
                <td className={TD}>
                  <Link to={leadHref(r.lead.lead_id)} aria-label={`Deschide pista ${r.lead.lead_id}`} className="rounded-sm">
                    <IdTag tone={r.group === "waiting" ? "now" : "neutral"}>{r.lead.lead_id}</IdTag>
                  </Link>
                </td>
                <td className={TD}>
                  <Account value={r.account} />
                </td>
                <td className={TD}>
                  <span className="tabular-nums">{r.cases || "—"}</span>
                  {r.amount !== null && <span className="ml-2 text-[0.8667rem] tabular-nums text-muted">{money(r.amount)}</span>}
                </td>
                <td className={TD}>
                  <ScoreText score={r.lead.top_score} unknown={notScored} />
                </td>
                <td className={TD}>
                  <Typologies items={r.lead.typologies} />
                </td>
                <td className={TD}>{r.lead.recommendation ? verdictLabel(r.lead.recommendation) : <span className="text-muted">—</span>}</td>
                <td className={TD}>
                  <LeadStatusText status={r.lead.status} />
                </td>
                <td className={`${TD} whitespace-nowrap text-muted`} title={dateTime(r.lead.updated_at)}>
                  {relative(r.lead.updated_at, now)}
                </td>
              </tr>
            );
          })
        )}
      </tbody>
    </TableFrame>
  );
}

function ReferralsSection({ refs, now }: { refs: Resource<Referral[]>; now: number }) {
  const navigate = useNavigate();
  const rows = useMemo(
    () =>
      (Array.isArray(refs.data) ? refs.data : [])
        .filter((r) => r && typeof r.case_id === "string")
        .slice()
        .sort((a, b) => (new Date(b.received_at).getTime() || 0) - (new Date(a.received_at).getTime() || 0)),
    [refs.data],
  );
  return (
    <section aria-labelledby="dioda-titlu" className="mt-10">
      <div className="mb-3">
        <h2 id="dioda-titlu" className="text-[1.0667rem] font-semibold">Contestații primite prin diodă</h2>
        <p className="mt-0.5 text-[0.9333rem] text-muted">
          Zona client trimite aici, într-un singur sens, doar faptele plății și ale beneficiarului. Identitatea victimei nu trece.
        </p>
      </div>
      {refs.error && !refs.data ? (
        <ErrorNote error={refs.error} what="contestațiile primite" onRetry={() => void refs.reload()} />
      ) : !refs.loading && !rows.length ? (
        <EmptyState title="Nicio contestație primită încă.">
          Când un operator decide un caz de fraudă în zona client, faptele lui apar aici în câteva secunde.
        </EmptyState>
      ) : (
        <>
          <StaleNote error={refs.data ? refs.error : undefined} every="4 s" />
          <TableFrame label="Contestații primite prin diodă" minWidth={760}>
            <thead>
              <tr>
                <th scope="col" className={TH}>Caz</th>
                <th scope="col" className={TH}>Primită</th>
                <th scope="col" className={`${TH} text-right`}>Sumă</th>
                <th scope="col" className={TH}>Cont beneficiar</th>
                <th scope="col" className={TH}>Scenariu</th>
                <th scope="col" className={TH}>Pistă</th>
              </tr>
            </thead>
            <tbody>
              {refs.loading && !rows.length ? (
                <SkeletonRows rows={3} cols={6} />
              ) : (
                rows.map((r) => (
                  <tr
                    key={r.case_id}
                    onClick={r.lead_id ? rowClick(() => navigate(leadHref(r.lead_id!))) : undefined}
                    className={r.lead_id ? "cursor-pointer hover:bg-hover" : undefined}
                  >
                    <td className={TD}>
                      <IdTag>{r.case_id}</IdTag>
                    </td>
                    <td className={`${TD} whitespace-nowrap text-muted`} title={dateTime(r.received_at)}>
                      {relative(r.received_at, now)}
                    </td>
                    <td className={`${TD} text-right tabular-nums`}>{money(r.amount)}</td>
                    <td className={TD}>
                      <span className="font-mono text-[0.8667rem] whitespace-nowrap">{maskAccount(r.beneficiary_iban_masked)}</span>
                    </td>
                    <td className={TD}>{scenarioLabel(r.scenario)}</td>
                    <td className={TD}>
                      {r.lead_id ? (
                        <Link to={leadHref(r.lead_id)} aria-label={`Deschide pista ${r.lead_id}`} className="rounded-sm">
                          <IdTag>{r.lead_id}</IdTag>
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </TableFrame>
        </>
      )}
    </section>
  );
}

export default function LeadsPage() {
  const api = useApi();
  const [params, setParams] = useSearchParams();
  const now = useNowTick(30_000);
  const leads = useResource(() => api.amlLeads(), [api], { pollMs: 4000 });
  // o singură sondare: tabelul de jos și, pentru fiecare pistă, contul principal și suma contestată
  const refs = useResource(() => api.amlReferrals(), [api], { pollMs: 4000 });

  const rows = useMemo(() => enrich(Array.isArray(leads.data) ? leads.data : [], Array.isArray(refs.data) ? refs.data : []), [leads.data, refs.data]);
  const counts = useMemo(
    () => ({
      asteapta: rows.filter((r) => r.group === "waiting").length,
      analiza: rows.filter((r) => r.group === "active").length,
      inchise: rows.filter((r) => r.group === "closed").length,
      toate: rows.length,
    }),
    [rows],
  );
  const asked = params.get("stare");
  const tab: TabId = isTab(asked) ? asked : counts.asteapta > 0 ? "asteapta" : "toate";
  const visible = tab === "toate" ? rows : rows.filter((r) => r.group === TAB_GROUP[tab]);
  const setTab = (id: TabId) => {
    const next = new URLSearchParams(params);
    next.set("stare", id);
    setParams(next, { replace: true });
  };

  const empty: Record<TabId, { title: string; body: string }> = {
    asteapta: { title: "Nicio pistă nu așteaptă decizia ta.", body: "Când agenții termină o pistă, o găsești aici, cu recomandarea regulilor." },
    analiza: { title: "Nicio pistă în analiză acum.", body: "Pistele noi intră aici cât timp agenții strâng probele." },
    inchise: { title: "Nicio pistă închisă încă.", body: "Aici ajung pistele după decizia ta: RTS depus, închisă sau HOLD emis." },
    toate: { title: "Nicio pistă încă.", body: "" },
  };

  return (
    <div>
      <PageHeader
        title="Piste AML"
        description="Conturile care au primit bani din contestațiile de fraudă. Agenții strâng probele și propun; decizia e a ta."
        actions={<OsintSearch />}
      />
      <SectionBoundary label="Imaginea de ansamblu"><AmlOverview /></SectionBoundary>

      <SectionBoundary label="Piste">
        {leads.error && !leads.data ? (
          <ErrorNote error={leads.error} what="pistele" onRetry={() => void leads.reload()} />
        ) : !leads.loading && rows.length === 0 ? (
          <EmptyState icon={<Waypoints aria-hidden className="size-5" />} title="Nicio pistă încă.">
            Pistele apar când zona client trimite prin diodă faptele unei contestații: contul beneficiar, suma și domeniul atacului. Victima
            apare doar ca pseudonim.
          </EmptyState>
        ) : (
          <>
            <div className="mb-4">
              <Tabs<TabId>
                label="Filtrează pistele după stare"
                value={tab}
                onChange={setTab}
                tabs={[
                  { id: "asteapta", label: "Te așteaptă", count: counts.asteapta },
                  { id: "analiza", label: "În analiză", count: counts.analiza },
                  { id: "inchise", label: "Închise", count: counts.inchise },
                  { id: "toate", label: "Toate", count: counts.toate },
                ]}
              />
            </div>
            <StaleNote error={leads.data ? leads.error : undefined} every="4 s" />
            {!leads.loading && visible.length === 0 ? (
              <EmptyState
                title={empty[tab].title}
                action={
                  <Button size="sm" variant="ghost" onClick={() => setTab("toate")}>
                    Vezi toate pistele
                  </Button>
                }
              >
                {empty[tab].body}
              </EmptyState>
            ) : (
              <LeadsTable rows={visible} loading={leads.loading} now={now} />
            )}
          </>
        )}
      </SectionBoundary>

      <SectionBoundary label="Contestații primite prin diodă">
        <ReferralsSection refs={refs} now={now} />
      </SectionBoundary>
    </div>
  );
}
