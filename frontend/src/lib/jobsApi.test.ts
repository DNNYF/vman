import { describe, it, expect, afterEach } from "vitest";
import {
  JobApiError,
  cancelJob,
  createCommandJob,
  denyJob,
  getJob,
  listJobs,
  parseSseFrame,
  retryJob,
  approveJob,
  getJobLogs,
} from "@/lib/jobsApi";
import type { Job } from "@/lib/jobs";

const sampleJob: Job = {
  id: "j1",
  host_id: "h1",
  recipe_name: "healthcheck",
  command_summary: "echo ok",
  requested_by_user_id: "u1",
  status: "queued",
  risk_level: "low",
  approval_status: "not_required",
  approval_requested_at: null,
  approved_by_user_id: null,
  approved_at: null,
  started_at: null,
  finished_at: null,
  timeout_seconds: 60,
  exit_code: null,
  error_summary_redacted: null,
  idempotency_key: null,
  created_at: "2026-06-23T00:00:00Z",
  updated_at: "2026-06-23T00:00:00Z",
};

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetchOnce(body: unknown, status = 200): void {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as unknown as typeof fetch;
}

function mockFetchObserve(
  responder: (url: string, init?: RequestInit) => Response,
): { getLast: () => { url: string; init?: RequestInit } } {
  let last: { url: string; init?: RequestInit } = { url: "" };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : String(input);
    last = { url, init };
    return responder(url, init);
  }) as unknown as typeof fetch;
  return {
    getLast: () => last,
  };
}

describe("jobsApi listJobs", () => {
  it("returns parsed payload from /api/jobs", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify([sampleJob]), { status: 200 }),
    );
    const rows = await listJobs();
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("j1");
    expect(obs.getLast().url).toBe("/api/jobs");
  });

  it("encodes query parameters as expected", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify([]), { status: 200 }),
    );
    await listJobs({ hostId: "h1", status: "running", limit: 50 });
    const url = obs.getLast().url;
    expect(url).toContain("host_id=h1");
    expect(url).toContain("status=running");
    expect(url).toContain("limit=50");
  });

  it("wraps ApiError into JobApiError", async () => {
    mockFetchOnce({ detail: "boom" }, 500);
    await expect(listJobs()).rejects.toBeInstanceOf(JobApiError);
  });
});

describe("jobsApi getJob", () => {
  it("fetches /api/jobs/{id} and returns the detail payload", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify({ ...sampleJob, logs: [] }), {
        status: 200,
      }),
    );
    const detail = await getJob("j1");
    expect(detail.id).toBe("j1");
    expect(detail.logs).toEqual([]);
    expect(obs.getLast().url).toBe("/api/jobs/j1");
  });

  it("encodes special characters in the job id", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify(sampleJob), { status: 200 }),
    );
    await getJob("a b/");
    expect(obs.getLast().url).toBe("/api/jobs/a%20b%2F");
  });
});

describe("jobsApi mutating endpoints", () => {
  it("createCommandJob POSTs to /api/jobs/command", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify(sampleJob), { status: 201 }),
    );
    const job = await createCommandJob({
      host_id: "h1",
      command: "echo hi",
    });
    expect(job.id).toBe("j1");
    expect(obs.getLast().url).toBe("/api/jobs/command");
    expect(obs.getLast().init?.method).toBe("POST");
  });

  it("cancelJob POSTs to /api/jobs/{id}/cancel", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify({ ...sampleJob, status: "cancelled" }), {
        status: 200,
      }),
    );
    const next = await cancelJob("j1");
    expect(next.status).toBe("cancelled");
    expect(obs.getLast().url).toBe("/api/jobs/j1/cancel");
  });

  it("retryJob POSTs to /api/jobs/{id}/retry", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify({ ...sampleJob, id: "j2" }), {
        status: 201,
      }),
    );
    const next = await retryJob("j1");
    expect(next.id).toBe("j2");
    expect(obs.getLast().url).toBe("/api/jobs/j1/retry");
  });

  it("approveJob POSTs to /api/jobs/{id}/approve", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify({ ...sampleJob, approval_status: "approved" }), {
        status: 200,
      }),
    );
    const next = await approveJob("j1");
    expect(next.approval_status).toBe("approved");
    expect(obs.getLast().url).toBe("/api/jobs/j1/approve");
  });

  it("denyJob POSTs reason as JSON body", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify({ ...sampleJob, approval_status: "denied" }), {
        status: 200,
      }),
    );
    await denyJob("j1", "out of scope");
    expect(obs.getLast().url).toBe("/api/jobs/j1/deny");
    expect(String(obs.getLast().init?.body ?? "")).toContain(
      '"reason":"out of scope"',
    );
  });

  it("getJobLogs forwards limit as a query string", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify([]), { status: 200 }),
    );
    await getJobLogs("j1", { limit: 25 });
    expect(obs.getLast().url).toBe("/api/jobs/j1/logs?limit=25");
  });
});

describe("parseSseFrame", () => {
  it("parses a log frame into a typed SseLogEvent", () => {
    const frame =
      'event: log\n' +
      'id: 7\n' +
      'data: {"kind":"log","job_id":"j1","seq":7,"timestamp":1.5,' +
      '"data":{"id":7,"stream":"stdout","line_redacted":"hello",' +
      '"line_hash":"abc","timestamp":"2026-06-23T00:00:00Z"}}\n' +
      "\n";
    const ev = parseSseFrame(frame);
    expect(ev).not.toBeNull();
    expect(ev?.kind).toBe("log");
    if (ev?.kind === "log") {
      expect(ev.data.line_redacted).toBe("hello");
      expect(ev.seq).toBe(7);
    }
  });

  it("parses a status frame", () => {
    const frame =
      'event: status\n' +
      'id: 11\n' +
      'data: {"kind":"status","job_id":"j1","seq":11,"timestamp":2.0,' +
      '"data":{"id":"j1","status":"success","approval_status":"not_required",' +
      '"exit_code":0,"started_at":"2026-06-23T00:00:00Z",' +
      '"finished_at":"2026-06-23T00:00:01Z","error_summary_redacted":null}}\n' +
      "\n";
    const ev = parseSseFrame(frame);
    expect(ev?.kind).toBe("status");
    if (ev?.kind === "status") {
      expect(ev.data.status).toBe("success");
      expect(ev.data.exit_code).toBe(0);
    }
  });

  it("returns null on malformed JSON", () => {
    const frame = "event: log\ndata: not-json\n\n";
    expect(parseSseFrame(frame)).toBeNull();
  });

  it("returns null on missing event/data fields", () => {
    expect(parseSseFrame("event: ping\n\n")).toBeNull();
  });

  it("returns null on an unrecognised event kind", () => {
    const frame =
      'event: unknown\n' +
      'data: {"kind":"unknown","job_id":"j1","seq":1,"timestamp":1.0,"data":{}}\n' +
      "\n";
    expect(parseSseFrame(frame)).toBeNull();
  });

  it("ignores leading space after the colon (per the SSE spec)", () => {
    const frame =
      "event: log\n" +
      'data: {"kind":"log","job_id":"j1","seq":1,"timestamp":1.0,' +
      '"data":{"id":1,"stream":"stdout","line_redacted":"hi",' +
      '"line_hash":null,"timestamp":""}}\n' +
      "\n";
    const ev = parseSseFrame(frame);
    expect(ev).not.toBeNull();
  });
});
