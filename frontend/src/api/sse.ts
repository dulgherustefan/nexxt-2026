import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentEvent } from "./types";

/** The public demo reaches this server through an ngrok tunnel; this header skips ngrok's browser warning page. */
export const TUNNEL_HEADERS: Record<string, string> = { "ngrok-skip-browser-warning": "1" };

export type StreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface StreamHandlers {
  onEvent: (e: AgentEvent) => void;
  onStatus?: (s: StreamStatus) => void;
}

/** O sursă de evenimente: întoarce funcția care o închide. Aceeași formă pentru SSE real și pentru simulare. */
export type StreamSource = (h: StreamHandlers) => () => void;

/**
 * Cheia de de-duplicare. Serverul retrimite tot istoricul la fiecare conectare (docs/06 §6),
 * deci la reconectare vin aceleași `seq`. Dacă `seq` lipsește (implicit 0), cădem pe conținut.
 */
export function eventKey(e: AgentEvent): string {
  if (typeof e.seq === "number" && e.seq > 0) return `${e.run_id}:${e.seq}`;
  return `${e.run_id}:${e.type}:${e.step ?? ""}:${e.name ?? ""}:${e.ts}:${e.message ?? ""}`;
}

function isAgentEvent(x: unknown): x is AgentEvent {
  return typeof x === "object" && x !== null && "type" in x && typeof (x as { type: unknown }).type === "string";
}

/**
 * SSE read with fetch, with our own reconnect (backoff 1 s → 10 s). Fetch rather than EventSource so every
 * request can carry TUNNEL_HEADERS (EventSource cannot send headers) and so we can report status and stop cleanly.
 */
/** `auth` adds headers per connection (the operator session), read again on every reconnect. */
export function openEventStream(url: string, { onEvent, onStatus }: StreamHandlers,
                                auth?: () => Promise<Record<string, string>>): () => void {
  let ctrl: AbortController | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const handleBlock = (block: string) => {
    const lines = block.split(/\r?\n/);
    const event = lines.find((l) => l.startsWith("event:"))?.slice(6).trim();
    if (event && event !== "message") return; // named events were never handled here
    const data = lines.filter((l) => l.startsWith("data:")).map((l) => l.slice(5).replace(/^ /, "")).join("\n");
    if (!data) return; // heartbeat or comment
    try {
      const parsed: unknown = JSON.parse(data);
      if (isAgentEvent(parsed)) onEvent(parsed);
    } catch {
      /* not JSON: ignore */
    }
  };

  const connect = async () => {
    if (closed) return;
    onStatus?.(attempt === 0 ? "connecting" : "reconnecting");
    ctrl = new AbortController();
    try {
      const res = await fetch(url, {
        headers: { Accept: "text/event-stream", ...TUNNEL_HEADERS, ...(auth ? await auth() : {}) },
        cache: "no-store",
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body || !(res.headers.get("content-type") ?? "").includes("text/event-stream")) throw new Error(String(res.status));
      attempt = 0;
      onStatus?.("open");
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        let cut: RegExpExecArray | null;
        while ((cut = /\r?\n\r?\n/.exec(buffer))) {
          handleBlock(buffer.slice(0, cut.index));
          buffer = buffer.slice(cut.index + cut[0].length);
        }
      }
    } catch {
      /* network error, abort or a non-SSE answer: reconnect below unless closed */
    }
    if (!closed) schedule();
  };

  const schedule = () => {
    if (closed) return;
    attempt += 1;
    onStatus?.("reconnecting");
    const delay = Math.min(10_000, 1000 * 2 ** Math.min(attempt - 1, 4));
    timer = setTimeout(() => void connect(), delay);
  };

  void connect();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ctrl?.abort();
    onStatus?.("closed");
  };
}

function insertSorted(list: AgentEvent[], e: AgentEvent): AgentEvent[] {
  const seq = typeof e.seq === "number" ? e.seq : 0;
  const last = list[list.length - 1];
  if (!last || seq === 0 || (typeof last.seq === "number" ? last.seq : 0) <= seq) return [...list, e];
  const next = [...list];
  let i = next.length - 1;
  while (i >= 0 && (next[i].seq ?? 0) > seq) i--;
  next.splice(i + 1, 0, e);
  return next;
}

export interface EventStreamState {
  events: AgentEvent[];
  status: StreamStatus;
  last: AgentEvent | null;
  reset: () => void;
}

/**
 * Hook-ul de evenimente: de-duplicare după `seq`, ordine stabilă, reconectare.
 * `key` schimbat = flux nou (alt caz sau altă pistă).
 */
export function useEventStream(
  source: StreamSource | null,
  key: string | null,
  onEvent?: (e: AgentEvent, isReplay: boolean) => void,
): EventStreamState {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const seen = useRef<Set<string>>(new Set());
  const handler = useRef(onEvent);
  handler.current = onEvent;
  const openedAt = useRef(0);

  useEffect(() => {
    seen.current = new Set();
    setEvents([]);
    if (!source || !key) {
      setStatus("idle");
      return;
    }
    openedAt.current = Date.now();
    const close = source({
      onEvent: (e) => {
        const k = eventKey(e);
        if (seen.current.has(k)) return;
        seen.current.add(k);
        setEvents((prev) => insertSorted(prev, e));
        // Evenimentele retrimise la conectare sosesc în primele ~400 ms: nu le animăm ca „live".
        const isReplay = Date.now() - openedAt.current < 400 && Date.now() - new Date(e.ts).getTime() > 2000;
        handler.current?.(e, isReplay);
      },
      onStatus: setStatus,
    });
    return close;
  }, [source, key]);

  const reset = useCallback(() => {
    seen.current = new Set();
    setEvents([]);
  }, []);

  return { events, status, last: events.length ? events[events.length - 1] : null, reset };
}
