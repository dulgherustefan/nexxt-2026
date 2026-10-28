import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentEvent } from "./types";

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
 * SSE prin EventSource, cu reconectare proprie (backoff 1 s → 10 s).
 * Nu ne bazăm pe reconectarea implicită a browserului, ca să putem raporta starea și să oprim curat.
 */
export function openEventStream(url: string, { onEvent, onStatus }: StreamHandlers): () => void {
  let es: EventSource | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    onStatus?.(attempt === 0 ? "connecting" : "reconnecting");
    try {
      es = new EventSource(url);
    } catch {
      schedule();
      return;
    }
    es.onopen = () => {
      attempt = 0;
      onStatus?.("open");
    };
    es.onmessage = (msg) => {
      try {
        const parsed: unknown = JSON.parse(msg.data);
        if (isAgentEvent(parsed)) onEvent(parsed);
      } catch {
        /* mesaj care nu e JSON (heartbeat, comentariu): îl ignorăm */
      }
    };
    es.onerror = () => {
      es?.close();
      es = null;
      schedule();
    };
  };

  const schedule = () => {
    if (closed) return;
    attempt += 1;
    onStatus?.("reconnecting");
    const delay = Math.min(10_000, 1000 * 2 ** Math.min(attempt - 1, 4));
    timer = setTimeout(connect, delay);
  };

  connect();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    es?.close();
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
