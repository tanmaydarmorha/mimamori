import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "./client";
import { CASE_EVENT_TYPES, type CaseEvent } from "./types";

/**
 * Subscribe to `GET /cases/{id}/events` (SSE; `event:` = type, `id:` = seq). The server replays from
 * `Last-Event-ID`, which EventSource sends by itself on reconnect, so the list never has gaps.
 * `onEvent` runs for every new event; the consumer usually just refetches the case.
 */
export function useCaseEvents(caseId: string | null, onEvent?: (e: CaseEvent) => void): CaseEvent[] {
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    setEvents([]);
    if (!caseId || typeof EventSource === "undefined") return;
    const es = new EventSource(eventsUrl(caseId));
    const seen = new Set<number>();
    const handle = (m: MessageEvent) => {
      let e: CaseEvent;
      try {
        e = JSON.parse(m.data) as CaseEvent;
      } catch {
        return;
      }
      if (seen.has(e.seq)) return;
      seen.add(e.seq);
      setEvents((prev) => [...prev, e].sort((a, b) => a.seq - b.seq));
      cb.current?.(e);
    };
    for (const t of CASE_EVENT_TYPES) es.addEventListener(t, handle as EventListener);
    return () => es.close();
  }, [caseId]);

  return events;
}
