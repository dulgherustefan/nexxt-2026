import { Inbox, Menu, MonitorPlay, RotateCcw, Search, Settings2, Waypoints, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { useRuntime } from "../api/runtime";
import { cx, Dot, Segmented } from "../ui/kit";
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
  match: (p: string) => boolean;
}

const OPERATOR_NAV: NavItem[] = [
  { to: "/", label: "Contestații", icon: <Inbox className="size-4" />, match: (p) => p === "/" || p.startsWith("/cazuri") },
  { to: "/sistem", label: "Sistem", icon: <Settings2 className="size-4" />, match: (p) => p.startsWith("/sistem") },
];

const AML_NAV: NavItem[] = [
  { to: "/aml", label: "Piste", icon: <Waypoints className="size-4" />, match: (p) => p === "/aml" || p.startsWith("/aml/piste") },
  { to: "/aml/osint", label: "Verificare OSINT", icon: <Search className="size-4" />, match: (p) => p.startsWith("/aml/osint") },
  { to: "/aml/sistem", label: "Sistem", icon: <Settings2 className="size-4" />, match: (p) => p.startsWith("/aml/sistem") },
];

/** Comutatorul de rol: o aplicație, două vederi. Vederea AML citește direct din procesul AML. */
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
  return (
    <Segmented<Role>
      className={className}
      label="Rolul"
      value={role}
      onChange={go}
      options={[
        { id: "operator", label: "Operator" },
        { id: "aml", label: "Analist AML", disabled: !amlApi, title: amlApi ? undefined : "Procesul AML nu e configurat (urls.aml lipsește din /api/meta)" },
      ]}
    />
  );
}

function SystemStatus() {
  const { meta, mode, mockReason } = useRuntime();
  const llm = meta.llm?.mode ?? "offline";
  const s =
    mode === "mock"
      ? { tone: mockReason === "forced" ? ("neutral" as const) : ("danger" as const), title: mockReason === "forced" ? "Date demo" : "Fără server", detail: "Datele sunt simulate în browser." }
      : llm === "live"
        ? { tone: "ok" as const, title: "Live", detail: `Claude pe Bedrock, ${meta.llm?.region ?? ""}` }
        : llm === "replay"
          ? { tone: "neutral" as const, title: "Replay", detail: "Răspunsuri LLM înregistrate." }
          : { tone: "neutral" as const, title: "Offline", detail: "Doar reguli și șabloane, fără LLM." };
  return (
    <span className="inline-flex items-center gap-2 text-[0.8667rem] text-ink-soft" title={s.detail}>
      <Dot tone={s.tone} live={s.tone === "ok"} />
      <span className="hidden sm:inline">{s.title}</span>
      {mode === "mock" && (
        <button type="button" title="Resetează datele demo" aria-label="Resetează datele demo" className="grid size-7 place-items-center rounded-md text-muted hover:bg-hover hover:text-ink"
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

function Nav({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const { pathname } = useLocation();
  const nav = role === "aml" ? AML_NAV : OPERATOR_NAV;
  return (
    <nav aria-label="Navigare" className="flex flex-col gap-0.5 p-3">
      {nav.map((n) => {
        const active = n.match(pathname);
        return (
          <Link key={n.to} to={n.to} onClick={onNavigate} aria-current={active ? "page" : undefined}
            className={cx(
              "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-[0.9333rem] transition-colors",
              active ? "bg-yellow-soft font-semibold text-ink" : "font-medium text-ink-soft hover:bg-hover hover:text-ink",
            )}>
            <span className={active ? "text-ink" : "text-muted"}>{n.icon}</span>
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand({ to }: { to: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded-md" aria-label="VersoML, pagina de start">
      <span aria-hidden className="grid size-7 place-items-center rounded-md bg-ink text-[0.85rem] font-bold text-yellow">V</span>
      <span className="text-[1rem] font-semibold tracking-[-0.01em]">VersoML</span>
    </Link>
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
  const onDemo = location.pathname.startsWith("/demo");
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-line bg-paper px-3 sm:px-4">
        <button type="button" aria-label="Deschide meniul" onClick={() => setOpen(true)} className="grid size-9 place-items-center rounded-md text-ink-soft hover:bg-hover lg:hidden">
          <Menu className="size-5" />
        </button>
        <Brand to={role === "aml" ? "/aml" : "/"} />
        <span aria-hidden className="mx-1 hidden h-5 w-px bg-line sm:block" />
        <span className="hidden sm:block"><RoleSwitch /></span>
        <div className="ml-auto flex items-center gap-3">
          <SystemStatus />
          <Link to="/demo" aria-current={onDemo ? "page" : undefined}
            className={cx("inline-flex h-8 items-center gap-2 rounded-md border px-3 text-[0.8667rem] font-semibold transition-colors",
              onDemo ? "border-yellow-line bg-yellow-soft" : "border-line-strong bg-paper hover:bg-hover")}>
            <MonitorPlay className="size-4" /> Demo
          </Link>
        </div>
      </header>
      {role === "aml" && <HazardBand className="sticky top-14 z-30">Zona AML · date separate</HazardBand>}
      <div className="flex flex-1">
        {!wide && (
          <aside className={cx("sticky hidden w-56 shrink-0 border-r border-line bg-canvas lg:block", role === "aml" ? "top-[5.7rem] h-[calc(100dvh-5.7rem)]" : "top-14 h-[calc(100dvh-3.5rem)]")}>
            <Nav role={role} />
          </aside>
        )}
        <main id="main" className={cx("min-w-0 flex-1 px-4 py-6 sm:px-8", wide ? "" : "pb-16")}>
          <div className="mb-4 sm:hidden"><RoleSwitch /></div>
          <div className={wide ? "mx-auto max-w-[1600px]" : "mx-auto max-w-[1200px]"}>
            <Outlet context={{ openQr: () => setPhones(true) }} />
          </div>
        </main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Meniu">
          <button type="button" aria-label="Închide meniul" className="absolute inset-0 bg-ink/25" onClick={() => setOpen(false)} />
          <div className="animate-enter absolute inset-y-0 left-0 w-64 border-r border-line bg-canvas shadow-[var(--shadow-overlay)]">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              <Brand to={role === "aml" ? "/aml" : "/"} />
              <button type="button" aria-label="Închide" onClick={() => setOpen(false)} className="grid size-8 place-items-center rounded-md hover:bg-hover">
                <X className="size-4" />
              </button>
            </div>
            <Nav role={role} onNavigate={() => setOpen(false)} />
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
        <span aria-hidden className="grid size-8 place-items-center rounded-md bg-ink text-[0.9rem] font-bold text-yellow">V</span>
        <p className="text-muted">Mă conectez la server…</p>
      </div>
    </div>
  );
}
