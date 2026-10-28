import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router";
import { ApiScope, RuntimeProvider, useRuntime } from "./api/runtime";
import { AppShell, BootScreen } from "./shell/AppShell";
import { EmptyState, Loading, SectionBoundary } from "./ui/kit";
import NotFound from "./pages/NotFound";

const HomePage = lazy(() => import("./pages/client/HomePage"));
const CasesPage = lazy(() => import("./pages/client/CasesPage"));
const CaseRoomPage = lazy(() => import("./pages/client/CaseRoom"));
const GuidedDemo = lazy(() => import("./pages/demo/GuidedDemo"));
const WallPage = lazy(() => import("./pages/client/WallPage"));
const RulesPage = lazy(() => import("./pages/client/RulesPage"));
const EvalPage = lazy(() => import("./pages/client/EvalPage"));
const McpPage = lazy(() => import("./pages/client/McpPage"));
const BankPage = lazy(() => import("./pages/demo/BankPage"));
const FakePage = lazy(() => import("./pages/demo/FakePage"));
const LeadsPage = lazy(() => import("./pages/aml/LeadsPage"));
const LeadPage = lazy(() => import("./pages/aml/LeadPage"));
const OsintPage = lazy(() => import("./pages/aml/OsintPage"));
const AccessLogPage = lazy(() => import("./pages/aml/AccessLogPage"));

/** Fiecare pagină are limita ei de eroare: o pagină căzută nu dărâmă navigarea. */
const S = ({ children, label }: { children: ReactNode; label: string }) => (
  <SectionBoundary label={label}>
    <Suspense fallback={<Loading />}>{children}</Suspense>
  </SectionBoundary>
);

/** Vederea AML: tot ce e dedesubt vorbește doar cu procesul AML (alt port, altă bază de date). */
export function AmlScope({ children }: { children: ReactNode }) {
  const { amlApi } = useRuntime();
  if (!amlApi) {
    return (
      <EmptyState title="Procesul AML nu e configurat.">
        Serverul zonei client nu a trimis adresa zonei AML (urls.aml în /api/meta). Pornește ambele procese cu „versoml up”.
      </EmptyState>
    );
  }
  return <ApiScope api={amlApi}>{children}</ApiScope>;
}

/** Rolul de operator nu are API pe portul zonei AML: îl trimitem la consola client. */
function OperatorOnly({ children }: { children: ReactNode }) {
  const { clientApi } = useRuntime();
  if (!clientApi) return <Navigate to="/aml" replace />;
  return <ApiScope api={clientApi}>{children}</ApiScope>;
}

function OldLeadLink() {
  const { leadId = "" } = useParams();
  return <Navigate to={`/aml/piste/${encodeURIComponent(leadId)}`} replace />;
}

function ZoneRoutes() {
  return (
    <Routes>
      <Route path="banca" element={<OperatorOnly><S label="Banca Demo"><BankPage /></S></OperatorOnly>} />
      <Route path="demo/livrare" element={<OperatorOnly><S label="Pagina falsă"><FakePage /></S></OperatorOnly>} />
      <Route element={<AppShell wide />}>
        <Route path="demo" element={<OperatorOnly><S label="Demo ghidat"><GuidedDemo /></S></OperatorOnly>} />
      </Route>
      <Route element={<AppShell />}>
        <Route index element={<OperatorOnly><S label="Azi"><HomePage /></S></OperatorOnly>} />
        <Route path="cazuri" element={<OperatorOnly><S label="Contestații"><CasesPage /></S></OperatorOnly>} />
        <Route path="cazuri/:id" element={<OperatorOnly><S label="Caz"><CaseRoomPage /></S></OperatorOnly>} />
        <Route path="zid" element={<OperatorOnly><S label="Zidul"><WallPage /></S></OperatorOnly>} />
        <Route path="reguli" element={<OperatorOnly><S label="Reguli"><RulesPage /></S></OperatorOnly>} />
        <Route path="evaluare" element={<OperatorOnly><S label="Evaluare"><EvalPage /></S></OperatorOnly>} />
        <Route path="mcp" element={<OperatorOnly><S label="MCP"><McpPage /></S></OperatorOnly>} />
        <Route path="aml" element={<AmlScope><S label="Piste"><LeadsPage /></S></AmlScope>} />
        <Route path="aml/piste/:leadId" element={<AmlScope><S label="Pistă"><LeadPage /></S></AmlScope>} />
        <Route path="aml/osint" element={<AmlScope><S label="Verificare OSINT"><OsintPage /></S></AmlScope>} />
        <Route path="aml/jurnal" element={<AmlScope><S label="Jurnal de acces"><AccessLogPage /></S></AmlScope>} />
        <Route path="piste/:leadId" element={<OldLeadLink />} />
        <Route path="osint" element={<Navigate to="/aml/osint" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <RuntimeProvider fallback={<BootScreen />}>
      <BrowserRouter>
        <ZoneRoutes />
      </BrowserRouter>
    </RuntimeProvider>
  );
}
