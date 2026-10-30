import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router";
import { probeMeta } from "./api/client";
import { RuntimeProvider, useRuntime } from "./api/runtime";
import { AppShell, BootScreen } from "./shell/AppShell";
import { SHOWCASE } from "./ui/ShowcaseBanner";
import { Loading, SectionBoundary } from "./ui/kit";
import NotFound from "./pages/NotFound";
import HomePage from "./pages/home/HomePage";

const CasesPage = lazy(() => import("./pages/client/CasesPage"));
const CasePage = lazy(() => import("./pages/client/CasePage"));
const RulesPage = lazy(() => import("./pages/client/RulesPage"));
const EvalPage = lazy(() => import("./pages/client/EvalPage"));
const McpPage = lazy(() => import("./pages/client/McpPage"));
const NewCasePage = lazy(() => import("./pages/client/NewCasePage"));
const KnowledgePage = lazy(() => import("./pages/client/KnowledgePage"));
const BankPage = lazy(() => import("./pages/demo/BankPage"));
const FakePage = lazy(() => import("./pages/demo/FakePage"));
const VerifyPage = lazy(() => import("./pages/demo/VerifyPage"));
const LeadsPage = lazy(() => import("./pages/aml/LeadsPage"));
const LeadPage = lazy(() => import("./pages/aml/LeadPage"));
const OsintPage = lazy(() => import("./pages/aml/OsintPage"));
const AccessLogPage = lazy(() => import("./pages/aml/AccessLogPage"));

// Fetch the console pages once the browser is idle, so the first click never waits on a chunk.
if (typeof window !== "undefined") {
  const warm = () => {
    void import("./pages/client/CasesPage");
    void import("./pages/client/CasePage");
    void import("./pages/client/RulesPage");
    void import("./pages/client/EvalPage");
    void import("./pages/client/NewCasePage");
    void import("./pages/client/KnowledgePage");
  };
  if ("requestIdleCallback" in window) window.requestIdleCallback(warm, { timeout: 4000 });
  else setTimeout(warm, 2500);
}

/** Each page has its own error boundary: one broken page never takes the navigation down. */
const S = ({ children, label }: { children: ReactNode; label: string }) => (
  <SectionBoundary label={label}>
    <Suspense fallback={<Loading />}>{children}</Suspense>
  </SectionBoundary>
);

/** Old Romanian paths keep working, query string included (the QR codes printed for the jury use `?client=`). */
function Moved({ to }: { to: string }) {
  return <Navigate to={{ pathname: to, search: window.location.search }} replace />;
}

function LegacyCase() {
  const { id } = useParams();
  return <Navigate to={`/cases/${id ?? ""}`} replace />;
}

function ZoneRoutes() {
  const { zone } = useRuntime();
  if (zone === "aml") {
    return (
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<S label="Leads"><LeadsPage /></S>} />
          <Route path="piste/:leadId" element={<S label="Lead"><LeadPage /></S>} />
          <Route path="osint" element={<S label="OSINT"><OsintPage /></S>} />
          <Route path="zid" element={<S label="Access log"><AccessLogPage /></S>} />
          <Route path="knowledge" element={<S label="Knowledge"><KnowledgePage /></S>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="bank" element={<S label="Demo Bank"><BankPage /></S>} />
      <Route path="demo/delivery" element={<S label="Demo courier page"><FakePage /></S>} />
      <Route path="verify/:id" element={<S label="Evidence check"><VerifyPage /></S>} />
      <Route element={<AppShell />}>
        <Route path="cases" element={<S label="Cases"><CasesPage /></S>} />
        <Route path="cases/new" element={<S label="New case"><NewCasePage /></S>} />
        <Route path="cases/:id" element={<S label="Case"><CasePage /></S>} />
        <Route path="rules" element={<S label="Rules"><RulesPage /></S>} />
        <Route path="knowledge" element={<S label="Knowledge"><KnowledgePage /></S>} />
        <Route path="evaluation" element={<S label="Evaluation"><EvalPage /></S>} />
        <Route path="mcp" element={<S label="MCP"><McpPage /></S>} />
        <Route path="*" element={<NotFound />} />
      </Route>
      {/* old Romanian paths, kept so printed QR codes and bookmarks still work */}
      <Route path="banca" element={<Moved to="/bank" />} />
      <Route path="demo/livrare" element={<Moved to="/demo/delivery" />} />
      <Route path="cazuri" element={<Navigate to="/cases" replace />} />
      <Route path="cazuri/:id" element={<LegacyCase />} />
      <Route path="reguli" element={<Navigate to="/rules" replace />} />
      <Route path="evaluare" element={<Navigate to="/evaluation" replace />} />
      <Route path="zid" element={<Navigate to="/cases" replace />} />
    </Routes>
  );
}

function Console() {
  return (
    <RuntimeProvider fallback={<BootScreen />}>
      <ZoneRoutes />
    </RuntimeProvider>
  );
}

/**
 * "/" is the homepage and paints without waiting for the server. The AML zone serves the same
 * bundle, so a quiet background check swaps in its console when this page is served from there.
 */
function Root() {
  const [aml, setAml] = useState(false);
  useEffect(() => {
    if (SHOWCASE) return;
    let alive = true;
    void probeMeta(1500).then((m) => alive && setAml(m?.zone === "aml"));
    return () => {
      alive = false;
    };
  }, []);
  if (aml) return <Console />;
  return <HomePage />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route index element={<Root />} />
        <Route path="*" element={<Console />} />
      </Routes>
    </BrowserRouter>
  );
}
