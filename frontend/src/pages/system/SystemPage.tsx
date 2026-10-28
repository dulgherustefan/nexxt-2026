/**
 * Sistem: tot ce explică de ce poți avea încredere în VersoML, într-o singură pagină cu file.
 * Zidul, Reguli, Evaluare și MCP citesc din zona client; Jurnalul de acces (doar pentru analist) din zona AML.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import { ApiScope, useRuntime } from "../../api/runtime";
import { EmbeddedPage, EmptyState, Loading, SectionBoundary, Tabs } from "../../ui/kit";
import { PhoneQr } from "../../shell/PhoneDemo";

const WallPage = lazy(() => import("../client/WallPage"));
const RulesPage = lazy(() => import("../client/RulesPage"));
const EvalPage = lazy(() => import("../client/EvalPage"));
const McpPage = lazy(() => import("../client/McpPage"));
const AccessLogPage = lazy(() => import("../aml/AccessLogPage"));

type TabId = "zid" | "reguli" | "evaluare" | "mcp" | "qr" | "jurnal";

const LABEL: Record<TabId, string> = { zid: "Zidul", reguli: "Reguli", evaluare: "Evaluare", mcp: "MCP", qr: "Coduri QR", jurnal: "Jurnal de acces" };

export default function SystemPage({ role }: { role: "operator" | "aml" }) {
  const { tab: raw } = useParams();
  const navigate = useNavigate();
  const { clientApi, amlApi } = useRuntime();
  const tabs: TabId[] = role === "aml" ? ["zid", "reguli", "evaluare", "mcp", "qr", "jurnal"] : ["zid", "reguli", "evaluare", "mcp", "qr"];
  const tab: TabId = (tabs as string[]).includes(raw ?? "") ? (raw as TabId) : "zid";
  const base = role === "aml" ? "/aml/sistem" : "/sistem";

  const client = (node: ReactNode) =>
    clientApi ? <ApiScope api={clientApi}>{node}</ApiScope> : (
      <EmptyState title="Fila asta citește din zona client.">Pagina e servită de procesul AML, care nu vede zona client. Deschide consola pe portul zonei client.</EmptyState>
    );

  return (
    <>
      <h1 className="mb-4 text-[1.4rem] leading-tight font-semibold">Sistem</h1>
      <Tabs<TabId> label="Secțiunile sistemului" value={tab} onChange={(t) => navigate(`${base}/${t}`, { replace: true })}
        tabs={tabs.map((t) => ({ id: t, label: LABEL[t] }))} className="mb-6" />
      <EmbeddedPage.Provider value>
        <SectionBoundary label={LABEL[tab]}>
          <Suspense fallback={<Loading />}>
            {tab === "zid" && client(<WallPage />)}
            {tab === "reguli" && client(<RulesPage />)}
            {tab === "evaluare" && client(<EvalPage />)}
            {tab === "mcp" && client(<McpPage />)}
            {tab === "qr" && (
              <div>
                <p className="mb-6 max-w-[72ch] text-[0.9333rem] text-muted">Pune codurile pe proiector. Primul deschide pagina falsă, al doilea Banca Demo; contestația apare în coadă în câteva secunde.</p>
                <PhoneQr />
              </div>
            )}
            {tab === "jurnal" && (amlApi ? <ApiScope api={amlApi}><AccessLogPage /></ApiScope> : <EmptyState title="Procesul AML nu e configurat." />)}
          </Suspense>
        </SectionBoundary>
      </EmbeddedPage.Provider>
    </>
  );
}
