/**
 * Thin wrapper around the VMAN jobs HTTP API.
 *
 * The backend mounts job routes at ``/api/jobs`` (see
 * ``backend/vman/api/routes_jobs.py``). The global ``ApiClient``
 * default base is ``/api/v1`` for forward compatibility, so we
 * explicitly point this module at the right path.
 *
 * SECURITY: this module never carries secret material. The
 * ``command_summary`` returned by the server is the user-typed
 * command, which we display verbatim but never ship elsewhere.
 *
 * The log stream is a Server-Sent Events endpoint; we open it
 * with the same cookie credentials as the REST calls and parse
 * the frames with a small helper. The helper is exposed
 * (``parseSseFrame``) so unit tests can exercise it without
 * needing a real network.
 */

import { ApiClient, ApiError } from "@/lib/api";
import type { Job, JobDetail, JobLog } from "@/lib/jobs";

const JOBS_BASE = "";

const client = new ApiClient({ baseUrl: JOBS_BASE });

export class JobApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "JobApiError";
    this.status = status;
    this.detail = detail;
  }
}

function toJobError(err: unknown): never {
  if (err instanceof ApiError) {
    throw new JobApiError(err.status, err.message);
  }
  if (err instanceof Error) {
    throw new JobApiError(0, err.message);
  }
  throw new JobApiError(0, "Unknown job API error");
}

export interface ListJobsOptions {
  limit?: number;
  offset?: number;
  hostId?: string;
  status?: string;
}

export async function listJobs(options: ListJobsOptions = {}): Promise<Job[]> {
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.hostId) params.set("host_id", options.hostId);
  if (options.status) params.set("status", options.status);
  const qs = params.toString();
  const path = qs ? `/api/jobs?${qs}` : "/api/jobs";
  try {
    return await client.get<Job[]>(path);
  } catch (err) {
    toJobError(err);
  }
}

export async function getJob(id: string): Promise<JobDetail> {
  try {
    return await client.get<JobDetail>(
      `/api/jobs/${encodeURIComponent(id)}`,
    );
  } catch (err) {
    toJobError(err);
  }
}

export async function getJobLogs(
  id: string,
  options: { limit?: number } = {},
): Promise<JobLog[]> {
  const qs = options.limit ? `?limit=${options.limit}` : "";
  try {
    return await client.get<JobLog[]>(
      `/api/jobs/${encodeURIComponent(id)}/logs${qs}`,
    );
  } catch (err) {
    toJobError(err);
  }
}

export async function createCommandJob(payload: {
  host_id: string;
  command: string;
  timeout_seconds?: number;
  risk_level?: string;
  approval_required?: boolean;
  idempotency_key?: string;
}): Promise<Job> {
  try {
    return await client.post<Job>("/api/jobs/command", { json: payload });
  } catch (err) {
    toJobError(err);
  }
}

export async function cancelJob(id: string): Promise<Job> {
  try {
    return await client.post<Job>(
      `/api/jobs/${encodeURIComponent(id)}/cancel`,
    );
  } catch (err) {
    toJobError(err);
  }
}

export async function retryJob(id: string): Promise<Job> {
  try {
    return await client.post<Job>(
      `/api/jobs/${encodeURIComponent(id)}/retry`,
    );
  } catch (err) {
    toJobError(err);
  }
}

export async function approveJob(id: string): Promise<Job> {
  try {
    return await client.post<Job>(
      `/api/jobs/${encodeURIComponent(id)}/approve`,
    );
  } catch (err) {
    toJobError(err);
  }
}

export async function denyJob(id: string, reason: string): Promise<Job> {
  try {
    return await client.post<Job>(
      `/api/jobs/${encodeURIComponent(id)}/deny`,
      { json: { reason } },
    );
  } catch (err) {
    toJobError(err);
  }
}

// --------------------------------------------------------------------------- //
// SSE log stream
// --------------------------------------------------------------------------- //

export type SseEventKind = "log" | "status" | "heartbeat";

export interface SseLogEvent {
  kind: "log";
  job_id: string;
  seq: number;
  timestamp: number;
  data: JobLog;
}

export interface SseStatusEvent {
  kind: "status";
  job_id: string;
  seq: number;
  timestamp: number;
  data: {
    id: string;
    status: string;
    approval_status: string;
    exit_code: number | null;
    started_at: string | null;
    finished_at: string | null;
    error_summary_redacted: string | null;
  };
}

export interface SseHeartbeat {
  kind: "heartbeat";
}

export type SseEvent = SseLogEvent | SseStatusEvent | SseHeartbeat;

/**
 * Parse a single SSE frame into a typed event. Returns ``null`` if
 * the frame is a comment (heartbeat) or otherwise unparseable. The
 * format is the standard one used by the backend:
 *
 *     event: log\n
 *     id: 17\n
 *     data: {"kind":"log","job_id":"...","seq":17,"timestamp":..., "data":{...}}\n
 *     \n
 */
export function parseSseFrame(text: string): SseEvent | null {
  let eventName: string | null = null;
  let dataLine: string | null = null;
  // Split on the SSE field separator.  The frame ends with a blank
  // line which the caller is expected to strip.
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith(":")) {
      // Comment frame; ignore.
      continue;
    }
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    else if (field === "data") dataLine = value;
  }
  if (eventName === null || dataLine === null) return null;
  let payload: {
    kind: string;
    job_id: string;
    seq: number;
    timestamp: number;
    data: Record<string, unknown>;
  };
  try {
    payload = JSON.parse(dataLine) as typeof payload;
  } catch {
    return null;
  }
  if (payload.kind === "log") {
    const log = payload.data as unknown as JobLog;
    return {
      kind: "log",
      job_id: payload.job_id,
      seq: payload.seq,
      timestamp: payload.timestamp,
      data: log,
    };
  }
  if (payload.kind === "status") {
    return {
      kind: "status",
      job_id: payload.job_id,
      seq: payload.seq,
      timestamp: payload.timestamp,
      data: payload.data as SseStatusEvent["data"],
    };
  }
  return null;
}

export interface LogStreamHandle {
  /** Close the underlying EventSource / fetch. */
  close(): void;
}

/**
 * Open a server-sent log stream for ``jobId``.  Returns a handle
 * whose ``close()`` method tears down the connection.
 *
 * The ``onEvent`` callback is invoked for every parsed event.  The
 * browser's native ``EventSource`` would be simpler, but it does not
 * support custom headers or ``credentials: include`` quirks on some
 * browsers, so we use ``fetch`` + a streaming reader.  This also makes
 * the behaviour easier to mock in unit tests.
 */
export function openLogStream(
  jobId: string,
  onEvent: (event: SseEvent) => void,
  onError?: (err: Error) => void,
): LogStreamHandle {
  const controller = new AbortController();
  // We deliberately hit the same API base.  The CSRF token cookie is
  // automatically attached for GET because the ApiClient only sets
  // the X-CSRF header for unsafe methods.  fetch with credentials:
  // "include" sends the session cookie.
  const url = `/api/jobs/${encodeURIComponent(jobId)}/logs/stream`;

  const run = async (): Promise<void> => {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "include",
        headers: { Accept: "text/event-stream" },
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        onError?.(
          new JobApiError(
            response.status,
            text || `stream failed with status ${response.status}`,
          ),
        );
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) {
        onError?.(new Error("response has no body"));
        return;
      }
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line.
        let sep: number;
        // eslint-disable-next-line no-cond-assign
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          if (frame.startsWith(":")) {
            // Heartbeat comment frame.
            onEvent({ kind: "heartbeat" });
            continue;
          }
          const ev = parseSseFrame(frame);
          if (ev) onEvent(ev);
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  };

  void run();

  return {
    close(): void {
      controller.abort();
    },
  };
}

export const JOBS_API_BASE = JOBS_BASE;
