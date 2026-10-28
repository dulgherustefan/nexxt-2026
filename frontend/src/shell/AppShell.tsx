import {
  BookOpenCheck,
  ExternalLink,
  FileStack,
  Gauge,
  Inbox,
  Menu,
  Plug,
  QrCode,
  RotateCcw,
  Search,
  ShieldCheck,
  Smartphone,
  TriangleAlert,
  Waypoints,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { useRuntime } from "../api/runtime";
import { cx, Dot } from "../ui/kit";
import { PhoneDemoDialog } from "./PhoneDemo";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

const CLIENT_NAV: NavItem[] = [
  { to: "/", label: "Contestații", icon: <Inbox className="size-4" />, end: true },
  { to: "/zid", label: "Zidul", icon: <ShieldCheck className="size-4" /> },
  { to: "/reguli", label: "Reguli", icon: <BookOpenCheck className="size-4" /> },
  { to: "/evaluare", label: "Evaluare", icon: <Gauge className="size-4" /> },
  { to: "/mcp", label: "MCP", icon: <Plug className="size-4" /> },
];

const AML_NAV: NavItem[] = [
  { to: "/", label: "Piste", icon: <Waypoints className="size-4" />, end: true },
  { to: "/osint", label: "Verificare OSINT", icon: <Search className="size-4" /> },
  { to: "/zid", label: "Jurnal de acces", icon: <FileStack className="size-4" /> },
];

/** Starea sistemului, în cuvinte: ce model răspunde și dacă datele vin de la server. */
function SystemStatus({ dark }: { dark: boolean }) {
  const { meta, mode, mockReason } = useRuntime();
  const llm = meta.llm?.mode ?? "offline";
  const lines =
    mode === "mock"
      ? mockReason === "forced"
        ? { tone: "neutral" as const, title: "Date demonstrative", detail: "Fără server (?mock=1)" }
        : { tone: "danger" as const, title: "Fără server", detail: "Serverul nu răspunde; afișez date demonstrative" }
      : llm === "live"
        ? { tone: "ok" as const, title: "Live", detail: `Claude pe Bedrock · ${meta.llm?.region ?? "us-east-1"}` }
        : llm === "replay"
          ? { tone: "neutral" as const, title: "Replay", detail: "Răspunsuri LLM înregistrate" }
          : { tone: "neutral" as const, title: "Offline", detail: "Reguli și șabloane, fără LLM" };
  return (
    <div className={cx("rounded-md border px-3 py-2.5", dark ? "border-white/15 bg-white/5" : "border-line bg-paper")}>
      <p className="flex items-center gap-2 text-[0.8667rem] font-semibold">
        <Dot tone={lines.tone} />
        {lines.title}
      </p>
      <p className={cx("mt-0.5 text-[0.8rem] leading-snug", dark ? "text-white/70" : "text-muted")}>{lines.detail}</p>
      {mode === "mock" && (
        <button
          type="button"
          onClick={async () => {
            const { resetMock } = await import("../mocks/store");
            resetMock();
            window.location.reload();
          }}
          className={cx("mt-1.5 inline-flex items-center gap-1.5 text-[0.8rem] font-medium underline", dark ? "text-white/80 hover:text-paper" : "text-ink-soft hover:text-ink")}
        >
          <RotateCcw aria-hidden className="size-3" /> Resetează datele demo
        </button>
      )}
    </div>
  );
}

function Sidebar({ onNavigate, onPhoneDemo }: { onNavigate?: () => void; onPhoneDemo: () => void }) {
  const { zone, meta } = useRuntime();
  const aml = zone === "aml";
  const nav = aml ? AML_NAV : CLIENT_NAV;
  const otherUrl = aml ? meta.urls?.client : meta.urls?.aml;
  const linkBase = "flex h-9 items-center gap-2.5 rounded-md px-2.5 font-medium";
  return (
    <div className={cx("flex h-full flex-col gap-6 px-3 py-4", aml ? "bg-ink text-paper" : "bg-canvas text-ink")}>
      <div className="flex items-center gap-2.5 px-1.5">
        <span aria-hidden className="grid size-8 place-items-center rounded-md border border-ink bg-yellow text-[1.05rem] font-black text-ink">V</span>
        <div className="leading-tight">
          <p className="font-bold">VersoML</p>
          <p className={cx("text-[0.8rem]", aml ? "text-yellow" : "text-muted")}>{aml ? "Zona AML" : "Contestații de plată"}</p>
        </div>
      </div>

      <nav aria-label="Navigare principală" className="flex flex-col gap-0.5">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                linkBase,
                isActive
                  ? aml ? "bg-yellow text-ink" : "border border-ink bg-yellow text-ink"
                  : aml ? "text-white/80 hover:bg-white/10 hover:text-paper" : "text-ink-soft hover:bg-hover",
              )
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {!aml && (
        <div className="flex flex-col gap-0.5">
          <p className="px-2.5 pb-1 text-[0.8rem] font-semibold text-muted">Demo pe telefon</p>
          <button type="button" onClick={onPhoneDemo} className={cx(linkBase, "text-left text-ink-soft hover:bg-hover")}>
            <QrCode className="size-4" /> Coduri QR pentru jurați
          </button>
          <a className={cx(linkBase, "text-ink-soft hover:bg-hover")} href="/banca" target="_blank" rel="noreferrer">
            <Smartphone className="size-4" /> Banca Demo <ExternalLink aria-hidden className="ml-auto size-3.5 text-subtle" />
          </a>
          <a className={cx(linkBase, "text-ink-soft hover:bg-hover")} href="/demo/livrare" target="_blank" rel="noreferrer">
            <TriangleAlert className="size-4" /> Pagina falsă <ExternalLink aria-hidden className="ml-auto size-3.5 text-subtle" />
          </a>
        </div>
      )}

      <div className="mt-auto flex flex-col gap-2">
        {otherUrl && (
          <a
            href={otherUrl}
            className={cx(linkBase, "border", aml ? "border-white/20 text-paper hover:bg-white/10" : "border-line bg-paper hover:bg-hover")}
          >
            {aml ? <Inbox className="size-4" /> : <Waypoints className="size-4" />}
            {aml ? "Consola client" : "Consola AML"}
            <ExternalLink aria-hidden className="ml-auto size-3.5 opacity-60" />
          </a>
        )}
        <SystemStatus dark={aml} />
      </div>
    </div>
  );
}

/** Banda permanentă de mediu, ca modul de test din Stripe. */
function EnvironmentBand() {
  const { zone } = useRuntime();
  return zone === "aml" ? (
    <div className="bg-ink px-4 py-1.5 text-center text-[0.8rem] font-semibold text-yellow">
      Zona AML · proces și bază de date separate · nimic de aici nu ajunge la client · date sintetice
    </div>
  ) : (
    <div className="border-b border-line bg-canvas px-4 py-1 text-center text-[0.8rem] font-semibold text-muted">
      Date sintetice · Banca Demo nu e o bancă reală
    </div>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  // `?qr=1` deschide direct codurile QR, ca prezentatorul să le pună pe proiector dintr-un link
  const [phones, setPhones] = useState(() => new URLSearchParams(window.location.search).has("qr"));
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const { zone } = useRuntime();
  return (
    <div className="flex min-h-dvh flex-col">
      <EnvironmentBand />
      <div className="flex flex-1">
        <aside className={cx("sticky top-0 hidden h-dvh w-60 shrink-0 border-r lg:block", zone === "aml" ? "border-ink" : "border-line")}>
          <Sidebar onPhoneDemo={() => setPhones(true)} />
        </aside>
        <div className="min-w-0 flex-1">
          <div className={cx("flex h-12 items-center justify-between border-b px-4 lg:hidden", zone === "aml" ? "bg-ink text-paper" : "border-line bg-canvas")}>
            <span className="font-bold">VersoML {zone === "aml" ? "· AML" : ""}</span>
            <button type="button" aria-label="Deschide meniul" onClick={() => setOpen(true)} className="grid size-9 place-items-center rounded-md hover:bg-hover/20">
              <Menu className="size-5" />
            </button>
          </div>
          <main id="main" className="mx-auto w-full max-w-[1320px] px-[18px] py-6 sm:px-6 lg:px-8 lg:py-8">
            <Outlet />
          </main>
        </div>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Meniu">
          <button type="button" aria-label="Închide meniul" className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 shadow-[var(--shadow-overlay)]">
            <button type="button" aria-label="Închide" onClick={() => setOpen(false)} className="absolute top-3 right-3 z-10 grid size-8 place-items-center rounded-md bg-paper/80">
              <X className="size-4" />
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
      <div className="flex items-center gap-3">
        <span aria-hidden className="grid size-9 place-items-center rounded-md border border-ink bg-yellow font-black">V</span>
        <p className="text-muted">Mă conectez la server…</p>
      </div>
    </div>
  );
}
