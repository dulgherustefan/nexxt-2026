import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createHttpApi, probeMeta, type Api } from "./client";
import type { Meta, Zone } from "./types";

export interface Runtime {
  /** API-ul procesului care a servit pagina. */
  api: Api;
  /** Zona client (contestații). Null când pagina e servită de zona AML: rolul de operator trimite atunci la urls.client. */
  clientApi: Api | null;
  /** Zona AML, proces separat. Rolul de operator nu îl folosește niciodată. */
  amlApi: Api | null;
  meta: Meta;
  mode: "live" | "mock";
  zone: Zone;
  /** De ce suntem în mock: forțat (VITE_MOCK=1, ?mock=1) sau backend-ul nu a răspuns. */
  mockReason?: "forced" | "unreachable";
}

const Ctx = createContext<Runtime | null>(null);
/** Un subarbore (vederea AML) poate folosi alt API decât cel al paginii. */
const ScopeCtx = createContext<Api | null>(null);

function sameOrigin(url: string): boolean {
  try {
    return new URL(url).origin === window.location.origin;
  } catch {
    return false;
  }
}

export function ApiScope({ api, children }: { api: Api; children: ReactNode }) {
  return <ScopeCtx.Provider value={api}>{children}</ScopeCtx.Provider>;
}

async function boot(): Promise<Runtime> {
  const params = new URLSearchParams(window.location.search);
  const forced = import.meta.env.VITE_MOCK === "1" || params.get("mock") === "1";
  if (!forced) {
    const meta = await probeMeta();
    if (meta) {
      const own = createHttpApi();
      if (meta.zone === "aml") return { api: own, clientApi: null, amlApi: own, meta, mode: "live", zone: "aml" };
      const amlBase = meta.urls?.aml && !sameOrigin(meta.urls.aml) ? meta.urls.aml : "";
      return { api: own, clientApi: own, amlApi: amlBase ? createHttpApi(amlBase) : null, meta, mode: "live", zone: "client" };
    }
  }
  const { createMockApi, mockZoneFromUrl } = await import("../mocks/mockApi");
  const zone = mockZoneFromUrl();
  const clientApi = createMockApi("client");
  const amlApi = createMockApi("aml");
  const api = zone === "aml" ? amlApi : clientApi;
  const meta = await api.meta();
  return { api, clientApi, amlApi, meta, mode: "mock", zone, mockReason: forced ? "forced" : "unreachable" };
}

export function RuntimeProvider({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const [rt, setRt] = useState<Runtime | null>(null);
  useEffect(() => {
    let alive = true;
    void boot().then((r) => {
      if (alive) setRt(r);
    });
    return () => {
      alive = false;
    };
  }, []);
  if (!rt) return <>{fallback}</>;
  return <Ctx.Provider value={rt}>{children}</Ctx.Provider>;
}

export function useRuntime(): Runtime {
  const rt = useContext(Ctx);
  if (!rt) throw new Error("RuntimeProvider lipsește");
  return rt;
}

export function useApi(): Api {
  const scoped = useContext(ScopeCtx);
  const rt = useRuntime();
  return scoped ?? rt.api;
}

export interface Resource<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => Promise<void>;
}

/**
 * Încărcare simplă de date: păstrează datele vechi la reîncărcare (fără pâlpâit),
 * ignoră răspunsurile întârziate, poate sonda la interval.
 */
export function useResource<T>(fetcher: (() => Promise<T>) | null, deps: unknown[], opts: { pollMs?: number } = {}): Resource<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [loading, setLoading] = useState<boolean>(Boolean(fetcher));
  const ticket = useRef(0);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  const reload = useCallback(async () => {
    const f = fetchRef.current;
    if (!f) return;
    const my = ++ticket.current;
    try {
      const v = await f();
      if (my !== ticket.current) return;
      setData(v);
      setError(undefined);
    } catch (e) {
      if (my !== ticket.current) return;
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      if (my === ticket.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(Boolean(fetchRef.current));
    setData(undefined);
    setError(undefined);
    void reload();
    if (!opts.pollMs) return;
    const t = setInterval(() => void reload(), opts.pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, opts.pollMs, reload]);

  return { data, error, loading, reload };
}

/** Ceas de o secundă pentru numărătorile inverse. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}
