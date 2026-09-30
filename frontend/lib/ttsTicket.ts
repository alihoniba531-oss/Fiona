import { apiFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/config";

export type TtsBackoff = { until: number };

// HTTP-date accepts IMF-fixdate plus the two obsolete forms allowed by HTTP.
const HTTP_DATE = /^(?:[a-z]{3}, \d{2} [a-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT|[a-z]+, \d{2}-[a-z]{3}-\d{2} \d{2}:\d{2}:\d{2} GMT|[a-z]{3} [a-z]{3} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4})$/i;

interface TtsTicketRequestOptions {
  text: string;
  signal: AbortSignal;
  backoff: TtsBackoff;
  isStale: () => boolean;
  onWait: (until: number) => void;
  onWaitEnd: () => void;
}

export function retryAfterMs(response: Response, body: unknown): number {
  const header = response.headers.get("Retry-After")?.trim();
  let seconds: number | null = null;

  if (header) {
    if (/^\d+$/.test(header)) {
      const value = Number(header);
      if (Number.isFinite(value)) seconds = value;
    } else if (HTTP_DATE.test(header)) {
      const date = Date.parse(header);
      if (Number.isFinite(date)) seconds = (date - Date.now()) / 1000;
    }
  }

  if (seconds === null && body && typeof body === "object" && "retry_after" in body) {
    const value = body.retry_after;
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) seconds = value;
  }

  return Math.min(60_000, Math.max(1_000, (seconds ?? 5) * 1_000));
}

function waitUntil(until: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    if (signal.aborted || until <= Date.now()) {
      resolve();
      return;
    }

    const onAbort = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      resolve();
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, until - Date.now());
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function requestTtsTicket({
  text, signal, backoff, isStale, onWait, onWaitEnd,
}: TtsTicketRequestOptions): Promise<string | null> {
  const cancelled = () => signal.aborted || isStale();
  let hasWaited = false;

  try {
    while (!cancelled()) {
      if (backoff.until > Date.now()) {
        hasWaited = true;
        onWait(backoff.until);
        await waitUntil(backoff.until, signal);
        if (cancelled()) return null;
        continue;
      }

      const response = await apiFetch(`${API_BASE}/tts/ticket`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: "longxiaoxia_v2", speech_rate: 1.15 }),
        signal,
      });
      if (cancelled()) return null;

      if (response.status === 429) {
        let body: unknown = null;
        try {
          body = await response.json();
        } catch {
          // A missing or invalid body still gets the Retry-After/default delay.
        }
        if (cancelled()) return null;
        backoff.until = Math.max(backoff.until, Date.now() + retryAfterMs(response, body));
        continue;
      }

      if (!response.ok) return null;
      const data: unknown = await response.json();
      if (cancelled()) return null;
      if (!data || typeof data !== "object" || !("ticket" in data)) return null;
      return typeof data.ticket === "string" && data.ticket ? data.ticket : null;
    }
    return null;
  } catch {
    return null;
  } finally {
    if (hasWaited) onWaitEnd();
  }
}
