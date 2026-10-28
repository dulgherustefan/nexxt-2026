import {
  BookOpenCheck,
  BrickWall,
  FileStack,
  Gauge,
  Inbox,
  LayoutDashboard,
  Menu,
  MonitorPlay,
  Plug,
  QrCode,
  RotateCcw,
  Search,
  Smartphone,
  TriangleAlert,
  Waypoints,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useRuntime } from "../api/runtime";
import { cx, Dot } from "../ui/kit";
import { HazardBand } from "../ui/viz";
import { PhoneDemoDialog } from "./PhoneDemo";

export type Role = "operator" | "aml";

export function roleOf(pathname: string): Role {
  return pathname === "/aml" || pathname.startsWith("/aml/") ? "aml" : "operator";
}

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

const OPERATOR_NAV: NavItem[] = [
  { to: "/", label: "Azi", icon: <LayoutDashboard className="size-5" />, end: true },
  { to: "/cazuri", label: "Contestații", icon: <Inbox className="size-5" /> },
  { to: "/demo", label: "Demo ghidat", icon: <MonitorPlay className="size-5" /> },
  { to: "/zid", label: "Zidul", icon: <BrickWall className="size-5" /> },
  { to: "/reguli", label: "Reguli", icon: <BookOpenCheck className="size-5" /> },
  { to: "/evaluare", label: "Evaluare", icon: <Gauge className="size-5" /> },
  { to: "/mcp", label: "MCP", icon: <Plug className="size-5" /> },
];

const AML_NAV: NavItem[] = [
  { to: "/aml", label: "Piste", icon: <Waypoints className="size-5" />, end: true },
  { to: "/aml/osint", label: "OSINT live", icon: <Search className="size-5" /> },
  { to: "/aml/jurnal", label: "Jurnal acces", icon: <FileStack className="size-5" /> },
];

/** Comutatorul de rol: o singură aplicație, două vederi. Vederea AML citește direct din procesul AML. */
export function RoleSwitch({ className }: { className?: string }) {
  const { zone, meta, amlApi } = useRuntime();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const role = roleOf(pathname);
  const go = (r: Role) => {
    if (r === role) return;
    if (r === "operator") {
      if (zone === "aml" && meta.urls?.client) window.location.href = meta.urls.client;
      else navigate("/");
    } else navigate("/aml");
  };
  const amlOff = !amlApi;
  return (
    <div role="radiogroup" aria-label="Rolul" className={cx("inline-flex rounded-lg border-2 border-ink bg-paper p-0.5", className)}>
      <button type="button" role="radio" aria-checked={role === "operator"} onClick={() => go("operator")}
        className={cx("h-9 rounded-md px-3.5 text-[0.9333rem] font-bold whitespace-nowrap", role === "operator" ? "bg-yellow text-ink" : "text-ink-soft hover:bg-hover")}>
        Operator contestații
      </button>
      <button type="button" role="radio" aria-checked={role === "aml"} onClick={() => go("aml")} disabled={amlOff}
        title={amlOff ? "Procesul AML nu e configurat (urls.aml lipsește din /api/meta)" : "Vederea analistului AML: alt proces, altă bază de date"}
        className={cx("h-9 rounded-md px-3.5 text-[0.9333rem] font-bold whitespace-nowrap disabled:opacity-40", role === "aml" ? "bg-ink text-yellow" : "text-ink-soft hover:bg-hover")}>
        Analist AML
      </button>
    </div>
  );
}

function SystemStatus() {
  const { meta, mode, mockReason } = useRuntime();
  const llm = meta.llm?.mode ?? "offline";
  const s =
    mode === "mock"
      ? { tone: mockReason === "forced" ? ("neutral" as const) : ("danger" as const), title: mockReason === "forced" ? "Date demonstrative" : "Fără server", detail: "simulat în browser" }
      : llm === "live"
        ? { tone: "ok" as const, title: "Live", detail: `Claude pe Bedrock · ${meta.llm?.region ?? ""}` }
        : llm === "replay"
          ? { tone: "neutral" as const, title: "Replay", detail: "răspunsuri LLM înregistrate" }
          : { tone: "neutral" as const, title: "Offline", detail: "reguli și șabloane" };
  return (
    <span className="hidden items-center gap-2 rounded-full border border-line bg-paper px-3 py-1 text-[0.8667rem] md:inline-flex" title={s.detail}>
      <Dot tone={s.tone} live={s.tone === "ok"} />
      <span className="font-semibold">{s.title}</span>
      <span className="hidden text-muted xl:inline">{s.detail}</span>
      {mode === "mock" && (
        <button type="button" title="Resetează datele demo" className="text-muted hover:text-ink"
          onClick={async () => {
            const { resetMock } = await import("../mocks/store");
            resetMock();
            window.location.reload();
          }}>
          <RotateCcw className="size-3.5" />
        </button>
      )}
    </span>
  );
}

function Rail({ role, onNavigate, onPhones }: { role: Role; onNavigate?: () => void; onPhones: () => void }) {
  const nav = role === "aml" ? AML_NAV : OPERATOR_NAV;
  const dark = role === "aml";
  const item = "flex flex-col items-center gap-1 rounded-lg px-1 py-2 text-center text-[0.75rem] font-semibold leading-tight";
  return (
    <nav aria-label="Navigare" className={cx("flex h-full flex-col gap-1 px-2 py-3", dark ? "bg-ink text-paper" : "bg-canvas text-ink")}>
      {nav.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} onClick={onNavigate}
          className={({ isActive }) => cx(item, isActive ? (dark ? "bg-yellow text-ink" : "bg-yellow text-ink ring-2 ring-ink") : dark ? "text-white/75 hover:bg-white/10 hover:text-paper" : "text-ink-soft hover:bg-hover")}>
          {n.icon}
          {n.label}
        </NavLink>
      ))}
      {role === "operator" && (
        <div className="mt-auto flex flex-col gap-1 border-t border-line pt-2">
          <button type="button" onClick={onPhones} className={cx(item, "text-ink-soft hover:bg-hover")}><QrCode className="size-5" />QR jurați</button>
          <a href="/banca" target="_blank" rel="noreferrer" className={cx(item, "text-ink-soft hover:bg-hover")}><Smartphone className="size-5" />Banca Demo</a>
          <a href="/demo/livrare" target="_blank" rel="noreferrer" className={cx(item, "text-ink-soft hover:bg-hover")}><TriangleAlert className="size-5" />Pagina falsă</a>
        </div>
      )}
      {role === "aml" && <p className="mt-auto px-1 text-center text-[0.7rem] leading-snug text-yellow/80">Nimic de aici nu ajunge la client</p>}
    </nav>
  );
}

export function AppShell({ wide = false }: { wide?: boolean }) {
  const [open, setOpen] = useState(false);
  const [phones, setPhones] = useState(() => new URLSearchParams(window.location.search).has("qr"));
  const location = useLocation();
  const role = roleOf(location.pathname);
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    document.title = role === "aml" ? "VersoML · Analist AML" : "VersoML · Contestații";
  }, [role]);
  const navigate = useNavigate();
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className={cx("sticky top-0 z-40 flex h-14 items-center gap-3 border-b-2 px-3 sm:px-4", role === "aml" ? "border-ink bg-paper" : "border-ink bg-paper")}>
        <button type="button" aria-label="Deschide meniul" onClick={() => setOpen(true)} className="grid size-9 place-items-center rounded-md hover:bg-hover lg:hidden">
          <Menu className="size-5" />
        </button>
        <button type="button" onClick={() => navigate(role === "aml" ? "/aml" : "/")} className="flex items-center gap-2" aria-label="VersoML, pagina de start">
          <span aria-hidden className="grid size-8 place-items-center rounded-md border-2 border-ink bg-yellow text-[1.05rem] font-black">V</span>
          <span className="display hidden text-[1.2rem] font-black sm:inline">VersoML</span>
        </button>
        <RoleSwitch className="ml-1 hidden sm:inline-flex" />
        <span className="hidden rounded-sm bg-canvas px-2 py-0.5 text-[0.75rem] font-semibold text-muted 2xl:inline">Date sintetice · Banca Demo nu e o bancă reală</span>
        <div className="ml-auto flex items-center gap-2">
          <SystemStatus />
          {role === "operator" && (
            <NavLink to="/demo" className="hidden h-9 items-center gap-2 rounded-md border-2 border-ink bg-yellow px-3 text-[0.9333rem] font-bold hover:bg-yellow-hover md:inline-flex">
              <MonitorPlay className="size-4" /> Demo ghidat
            </NavLink>
          )}
        </div>
      </header>
      {role === "aml" && <HazardBand className="sticky top-14 z-30">Zona AML · proces și bază de date separate · nimic de aici nu ajunge la client</HazardBand>}
      <div className="flex flex-1">
        <aside className={cx("sticky hidden w-[92px] shrink-0 border-r lg:block", role === "aml" ? "top-[5.25rem] h-[calc(100dvh-5.25rem)] border-ink" : "top-14 h-[calc(100dvh-3.5rem)] border-line")}>
          <Rail role={role} onPhones={() => setPhones(true)} />
        </aside>
        <main id="main" className={cx("min-w-0 flex-1 px-4 py-5 sm:px-6", !wide && "mx-auto max-w-[1720px]")}>
          <div className="mb-3 sm:hidden"><RoleSwitch /></div>
          <Outlet />
        </main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Meniu">
          <button type="button" aria-label="Închide meniul" className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[120px] shadow-[var(--shadow-overlay)]">
            <button type="button" aria-label="Închide" onClick={() => setOpen(false)} className="absolute top-2 -right-10 z-10 grid size-8 place-items-center rounded-md bg-paper">
              <X className="size-4" />
            </button>
            <Rail role={role} onNavigate={() => setOpen(false)} onPhones={() => { setOpen(false); setPhones(true); }} />
          </div>
        </div>
      )}
      {phones && <PhoneDemoDialog onClose={() => setPhones(false)} />}
    </div>
  );
}

export function BootScreen() {
  return (
    <div role="status" className="grid min-h-dvh place-items-center bg-paper">
      <div className="flex items-center gap-3">
        <span aria-hidden className="grid size-9 place-items-center rounded-md border-2 border-ink bg-yellow font-black">V</span>
        <p className="text-muted">Mă conectez la server…</p>
      </div>
    </div>
  );
}

