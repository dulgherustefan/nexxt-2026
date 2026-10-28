import { ChevronRight, Search, Waypoints } from "lucide-react";
import { lazy, Suspense, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { dateTime, money, relative, scenarioLabel, toMoney, verdictLabel } from "../../api/format";
import { useApi, useResource, type Resource } from "../../api/runtime";
import type { LeadSummary, Referral } from "../../api/types";
import { Button, Collapsible, EmptyState, ErrorNote, IdTag, SectionBoundary, Skeleton, StatStrip, Tabs, useNowTick } from "../../ui/kit";
import { Bar } from "../../ui/viz";
import { GROUP_ORDER, leadStatus, maskAccount, type LeadGroup } from "./aml";
import { Account, LeadStatusBadge, rowClick, ScoreText, SkeletonRows, StaleNote, TableFrame, TD, TH } from "./ui";

const MoneyGraph = lazy(() => import("../../graph/MoneyGraph"));

/** Campaniile și rețeaua conturilor semnalate: la cerere, sub tabel. */
function AmlNetwork() {
  const api = useApi();
  const campaigns = useResource(() => api.amlCampaigns(), [api], { pollMs: 8000 });
  const network = useResource(() => api.amlGraph(), [api], { pollMs: 10000 });
  const list = Array.isArray(campaigns.data) ? campaigns.data : [];
  const max = Math.max(1, ...list.map((c) => toMoney(c.amount_total)?.value ?? 0));
  return (
    <div className="grid items-start gap-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <section aria-label="Campanii">
        <p className="mb-2 text-[0.8667rem] text-muted">Victime legate prin același domeniu, IBAN sau telefon.</p>
        {list.length === 0 ? (
          <p className="text-[0.9333rem] text-muted">Nicio campanie încă.</p>
        ) : (
          <ul className="flex flex-col gap-4">
            {list.map((c) => {
              const amount = toMoney(c.amount_total)?.value ?? 0;
              const n = Array.isArray(c.cases) ? c.cases.length : Number(c.cases);
              return (
                <li key={c.campaign_id}>
                  <div className="flex items-baseline justify-between gap-2 text-[0.9333rem]">
                    <span className="font-mono text-[0.8rem] text-muted">{c.campaign_id}</span>
                    <span className="font-semibold tabular-nums">{money(amount)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2"><Bar value={amount / max} tone="ink" /><span className="shrink-0 text-[0.8rem] text-muted">{n === 1 ? "o victimă" : n + " victime"}</span></div>
                  <p className="mt-1 truncate font-mono text-[0.75rem] text-muted">{[...(c.shared.domains ?? []), ...(c.shared.ibans ?? []), ...(c.shared.phones ?? [])].join(" · ")}</p>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <SectionBoundary label="Rețeaua">
        <Suspense fallback={<Skeleton className="h-80 rounded-lg" />}>
          {network.data && (network.data.edges?.length ?? 0) > 0 ? (
            <MoneyGraph graph={network.data} title="Rețeaua conturilor semnalate" height={380} />
          ) : (
            <EmptyState title="Rețeaua apare după prima pistă." />
          )}
        </Suspense>
      </SectionBoundary>
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

function LeadsTable({ rows, loading }: { rows: LeadRow[]; loading: boolean }) {
  const navigate = useNavigate();
  return (
    <TableFrame label="Piste AML" minWidth={860}>
      <thead>
        <tr>
          <th scope="col" className={TH}>Cont</th>
          <th scope="col" className={TH}>Victime</th>
          <th scope="col" className={TH + " text-right"}>Sumă</th>
          <th scope="col" className={TH}>Scor</th>
          <th scope="col" className={TH}>Recomandare</th>
          <th scope="col" className={TH}>Stare</th>
          <th scope="col" className={TH + " w-px"}><span className="sr-only">Acțiune</span></th>
        </tr>
      </thead>
      <tbody>
        {loading && !rows.length ? (
          <SkeletonRows cols={7} />
        ) : (
          rows.map((r) => {
            const s = leadStatus(r.lead.status);
            const notScored = !r.lead.top_score && (s?.key === "NOU" || s?.key === "IN_ANALIZA");
            return (
              <tr key={r.lead.lead_id} onClick={rowClick(() => navigate(leadHref(r.lead.lead_id)))} className="cursor-pointer transition-colors hover:bg-canvas">
                <td className={TD}>
                  <Link to={leadHref(r.lead.lead_id)} aria-label={"Deschide pista " + r.lead.lead_id} className="block rounded-sm">
                    <Account value={r.account} className="text-[0.9333rem] text-ink" />
                    <span className="block font-mono text-[0.75rem] text-muted">{r.lead.lead_id}</span>
                  </Link>
                </td>
                <td className={TD + " tabular-nums"}>{r.cases || "—"}</td>
                <td className={TD + " text-right font-semibold whitespace-nowrap tabular-nums"}>{r.amount !== null ? money(r.amount) : "—"}</td>
                <td className={TD}><ScoreText score={r.lead.top_score} unknown={notScored} /></td>
                <td className={TD + " text-[0.9333rem]"}>{r.lead.recommendation ? verdictLabel(r.lead.recommendation) : <span className="text-muted">—</span>}</td>
                <td className={TD}><LeadStatusBadge status={r.lead.status} /></td>
                <td className={TD + " text-right"}><ChevronRight aria-hidden className="size-4 text-muted" /></td>
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
  const refs = useResource(() => api.amlReferrals(), [api], { pollMs: 4000 });
  const stats = useResource(() => api.amlStats(), [api], { pollMs: 5000 });

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
  const s = stats.data;
  const refCount = Array.isArray(refs.data) ? refs.data.length : null;

  const empty: Record<TabId, { title: string; body: string }> = {
    asteapta: { title: "Nicio pistă nu așteaptă decizia ta.", body: "Când agenții termină o pistă, apare aici, cu recomandarea regulilor." },
    analiza: { title: "Nicio pistă în analiză acum.", body: "Pistele noi stau aici cât timp agenții strâng probele." },
    inchise: { title: "Nicio pistă închisă încă.", body: "Aici ajung pistele după decizia ta." },
    toate: { title: "Nicio pistă încă.", body: "" },
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[1.4rem] leading-tight font-semibold">Piste</h1>
        <OsintSearch />
      </div>

      {rows.length > 0 && (
        <div className="mb-8">
          <StatStrip items={[
            { label: "Așteaptă decizia ta", value: counts.asteapta, tone: counts.asteapta ? "now" : "ink" },
            { label: "Bani în risc", value: s ? money(s.amount_at_risk) : "—", sub: s ? (s.referrals === 1 ? "o contestație" : s.referrals + " contestații") : undefined },
            { label: "Conturi semnalate", value: s?.accounts_flagged ?? "—", sub: "scor peste 0,70" },
          ]} />
        </div>
      )}

      <SectionBoundary label="Piste">
        {leads.error && !leads.data ? (
          <ErrorNote error={leads.error} what="pistele" onRetry={() => void leads.reload()} />
        ) : !leads.loading && rows.length === 0 ? (
          <EmptyState icon={<Waypoints aria-hidden className="size-5" />} title="Nicio pistă încă.">
            O pistă apare când zona client trimite faptele unei contestații: contul beneficiar, suma și domeniul atacului.
          </EmptyState>
        ) : (
          <>
            <Tabs<TabId>
              className="mb-4"
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
            <StaleNote error={leads.data ? leads.error : undefined} every="4 s" />
            {!leads.loading && visible.length === 0 ? (
              <EmptyState title={empty[tab].title} action={<Button size="sm" onClick={() => setTab("toate")}>Vezi toate pistele</Button>}>
                {empty[tab].body}
              </EmptyState>
            ) : (
              <LeadsTable rows={visible} loading={leads.loading} />
            )}
          </>
        )}
      </SectionBoundary>

      <div className="mt-8 border-y border-line">
        <Collapsible title="Contestații primite din zona client" meta={refCount !== null ? String(refCount) : undefined}>
          <SectionBoundary label="Contestații primite prin diodă"><ReferralsSection refs={refs} now={now} /></SectionBoundary>
        </Collapsible>
        <Collapsible title="Rețeaua și campaniile" meta={s ? s.communities + (s.communities === 1 ? " comunitate" : " comunități") : undefined}>
          <SectionBoundary label="Rețeaua"><AmlNetwork /></SectionBoundary>
        </Collapsible>
      </div>
    </div>
  );
}
