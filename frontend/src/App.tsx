import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { RuntimeProvider, useRuntime } from "./api/runtime";
import { AppShell, BootScreen } from "./shell/AppShell";
import { Loading, SectionBoundary } from "./ui/kit";
import NotFound from "./pages/NotFound";

const CasesPage = lazy(() => import("./pages/client/CasesPage"));
const CasePage = lazy(() => import("./pages/client/CasePage"));
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

function ZoneRoutes() {
  const { zone } = useRuntime();
  if (zone === "aml") {
    return (
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<S label="Piste"><LeadsPage /></S>} />
          <Route path="piste/:leadId" element={<S label="Pistă"><LeadPage /></S>} />
          <Route path="osint" element={<S label="Verificare OSINT"><OsintPage /></S>} />
          <Route path="zid" element={<S label="Jurnal de acces"><AccessLogPage /></S>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="banca" element={<S label="Banca Demo"><BankPage /></S>} />
      <Route path="demo/livrare" element={<S label="Pagina falsă"><FakePage /></S>} />
      <Route element={<AppShell />}>
        <Route index element={<S label="Contestații"><CasesPage /></S>} />
        <Route path="cazuri" element={<Navigate to="/" replace />} />
        <Route path="cazuri/:id" element={<S label="Caz"><CasePage /></S>} />
        <Route path="zid" element={<S label="Zidul"><WallPage /></S>} />
        <Route path="reguli" element={<S label="Reguli"><RulesPage /></S>} />
        <Route path="evaluare" element={<S label="Evaluare"><EvalPage /></S>} />
        <Route path="mcp" element={<S label="MCP"><McpPage /></S>} />
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
