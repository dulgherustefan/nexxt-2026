import {
  ArrowSquareOut,
  BookOpenText,
  ChartLineUp,
  DeviceMobile,
  FileMagnifyingGlass,
  List,
  ListMagnifyingGlass,
  Plugs,
  QrCode,
  Scales,
  Tray,
  Warning,
  X,
  type Icon,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useApi, useResource, useRuntime } from "../api/runtime";
import { cx, Dot } from "../ui/kit";
import { Logo, LogoMark } from "../ui/Logo";
import { ThemeToggle } from "../ui/ThemeToggle";
import { PhoneDemoDialog } from "./PhoneDemo";

interface NavItem {
  to: string;
  label: string;
  icon: Icon;
  end?: boolean;
}

const CLIENT_NAV: NavItem[] = [
  { to: "/cases", label: "Cases", icon: Tray },
  { to: "/rules", label: "Rules", icon: Scales },
  { to: "/knowledge", label: "Knowledge", icon: BookOpenText },
  { to: "/evaluation", label: "Evaluation", icon: ChartLineUp },
  { to: "/mcp", label: "MCP", icon: Plugs },
];

const AML_NAV: NavItem[] = [
  { to: "/", label: "Leads", icon: ListMagnifyingGlass, end: true },
  { to: "/osint", label: "OSINT check", icon: FileMagnifyingGlass },
  { to: "/zid", label: "Access log", icon: Scales },
  { to: "/knowledge", label: "Knowledge", icon: BookOpenText },
];

/** What is answering right now, in words: a live model, recorded answers, or rules only. */
function SystemStatus() {
  const { meta, mode, mockReason } = useRuntime();
  const llm = meta.llm?.mode ?? "offline";
  const s =
    mode === "mock"
      ? mockReason === "forced"
        ? { tone: "neutral" as const, title: "Demo data", detail: "No server (?mock=1)" }
        : { tone: "danger" as const, title: "Server not reachable", detail: "Showing demo data" }
      : llm === "live"
        ? { tone: "ok" as const, title: "Live", detail: `Claude on Amazon Bedrock · ${meta.llm?.region ?? "us-east-1"}` }
        : llm === "replay"
          ? { tone: "neutral" as const, title: "Replay", detail: "Recorded model answers" }
          : { tone: "neutral" as const, title: "Offline", detail: "Rules and templates, no model" };
  return (
    <div className="rounded-xl px-3 py-2.5">
      <p className="flex items-center gap-2 text-[0.8667rem] font-medium">
        <Dot tone={s.tone} />
        {s.title}
      </p>
      <p className="mt-0.5 pl-4 text-[0.8rem] leading-snug text-muted">{s.detail}</p>
      {mode === "mock" && (
        <button
          type="button"
          onClick={async () => {
            const { resetMock } = await import("../mocks/store");
            resetMock();
            window.location.reload();
          }}
          className="mt-1 ml-4 text-[0.8rem] font-medium text-ink-soft underline underline-offset-2 hover:text-ink"
        >
          Reset demo data
        </button>
      )}
    </div>
  );
}

function NeedsYou({ active }: { active: boolean }) {
  const api = useApi();
  const { zone } = useRuntime();
  const stats = useResource(zone === "client" ? () => api.stats() : null, [zone], { pollMs: 8000 });
  const n = stats.data?.awaiting_human ?? 0;
  if (!n) return null;
  return (
    <span className={cx("tnum ml-auto grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[0.75rem] font-semibold", active ? "bg-on-yellow text-yellow" : "bg-yellow text-on-yellow")} title={`${n} waiting for approval`}>
      {n}
    </span>
  );
}

function Sidebar({ onNavigate, onPhoneDemo }: { onNavigate?: () => void; onPhoneDemo: () => void }) {
  const { zone } = useRuntime();
  const aml = zone === "aml";
  const nav = aml ? AML_NAV : CLIENT_NAV;
  const item = "flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[0.9333rem] transition-colors";
  return (
    <div className="flex h-full flex-col gap-7 bg-canvas px-3 pt-4 pb-3">
      <div className="px-2">
        <Link to={aml ? "/" : "/"} onClick={onNavigate} className="inline-flex rounded-md text-[1.05rem]" aria-label="VersoML home">
          <Logo />
        </Link>
        <p className="mt-1 text-[0.8rem] text-muted">{aml ? "AML zone" : "Demo Bank · Disputes"}</p>
      </div>

      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {nav.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(item, isActive ? "bg-yellow font-medium text-on-yellow" : "text-muted hover:bg-hover hover:text-ink")
            }
          >
            {({ isActive }) => (
              <>
                <it.icon size={17} weight={isActive ? "fill" : "regular"} className={isActive ? "text-on-yellow" : "text-subtle"} />
                {it.label}
                {it.to === "/cases" && <NeedsYou active={isActive} />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {!aml && (
        <div className="flex flex-col gap-0.5">
          <p className="px-2.5 pb-1 text-[0.8rem] text-subtle">Try it</p>
          <a className={cx(item, "text-muted hover:bg-hover hover:text-ink")} href="/bank" target="_blank" rel="noreferrer">
            <DeviceMobile size={17} className="text-subtle" /> Demo Bank app
            <ArrowSquareOut aria-hidden size={14} className="ml-auto text-subtle" />
          </a>
          <a className={cx(item, "text-muted hover:bg-hover hover:text-ink")} href="/demo/delivery" target="_blank" rel="noreferrer">
            <Warning size={17} className="text-subtle" /> Fake courier page
            <ArrowSquareOut aria-hidden size={14} className="ml-auto text-subtle" />
          </a>
          <button type="button" onClick={onPhoneDemo} className={cx(item, "text-left text-muted hover:bg-hover hover:text-ink")}>
            <QrCode size={17} className="text-subtle" /> QR codes for the jury
          </button>
        </div>
      )}

      <div className="mt-auto flex flex-col gap-1">
        <div className="flex items-start justify-between gap-1">
          <SystemStatus />
          <ThemeToggle className="mt-1 text-muted hover:bg-hover hover:text-ink" />
        </div>
        <p className="px-3 text-[0.75rem] text-subtle">Synthetic data. Demo Bank is not a real bank.</p>
      </div>
    </div>
  );
}

const PAGE_TITLES: Record<string, string> = {
  "/cases": "Cases", "/cases/new": "New case", "/rules": "Rules", "/knowledge": "Knowledge", "/evaluation": "Evaluation", "/mcp": "MCP",
};

export function AppShell() {
  const [open, setOpen] = useState(false);
  // `?qr=1` opens the QR codes directly, so the presenter can put them on the projector from a link
  const [phones, setPhones] = useState(() => new URLSearchParams(window.location.search).has("qr"));
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    const page = PAGE_TITLES[location.pathname];
    if (page) document.title = `${page} · VersoML`;   // a case page sets its own title
  }, [location.pathname]);
  return (
    <div className="flex min-h-dvh bg-paper">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-line lg:block">
        <Sidebar onPhoneDemo={() => setPhones(true)} />
      </aside>
      <div className="min-w-0 flex-1">
        <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur lg:hidden">
          <Link to="/" aria-label="VersoML home"><Logo /></Link>
          <div className="flex items-center gap-1">
            <ThemeToggle className="text-muted hover:bg-hover hover:text-ink" />
            <button type="button" aria-label="Open menu" onClick={() => setOpen(true)} className="grid size-9 place-items-center rounded-full hover:bg-hover">
              <List size={20} />
            </button>
          </div>
        </div>
        <main id="main" className="mx-auto w-full max-w-[1240px] px-5 py-7 sm:px-8 lg:px-10 lg:py-9">
          {/* a short fade when the page changes; keyed so every route enters the same way */}
          <div key={location.pathname} className="animate-enter"><Outlet /></div>
        </main>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 animate-[drawer-in_280ms_var(--ease-drawer)] shadow-[var(--shadow-overlay)]">
            <button type="button" aria-label="Close" onClick={() => setOpen(false)} className="absolute top-3 right-3 z-10 grid size-8 place-items-center rounded-full hover:bg-hover">
              <X size={16} />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} onPhoneDemo={() => { setOpen(false); setPhones(true); }} />
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
      <div className="flex items-center gap-3 text-muted">
        <LogoMark className="size-6 text-ink" />
        <span className="text-[0.9333rem]">Connecting to the server…</span>
      </div>
    </div>
  );
}
