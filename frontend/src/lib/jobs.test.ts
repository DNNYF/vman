import { describe, it, expect } from "vitest";
import {
  approvalStatusLabel,
  approvalStatusTone,
  formatDuration,
  isTerminalStatus,
  jobStatusLabel,
  jobStatusTone,
  logStreamLabel,
  logStreamTone,
  riskLevelLabel,
  riskLevelTone,
  TERMINAL_STATUSES,
  truncateCommand,
  type Job,
  type JobLog,
  type JobStatus,
} from "@/lib/jobs";

describe("job status helpers", () => {
  it("maps known statuses to a label and tone", () => {
    for (const s of [
      "queued",
      "running",
      "success",
      "failed",
      "cancelled",
      "denied",
    ] as JobStatus[]) {
      expect(jobStatusLabel(s)).toMatch(/.+/);
      expect(jobStatusTone(s)).toMatch(/^(info|success|warning|destructive|outline)$/);
    }
  });

  it("falls back to the raw value for unknown statuses", () => {
    expect(jobStatusLabel("weird" as unknown as JobStatus)).toBe("weird");
    expect(jobStatusTone("weird" as unknown as JobStatus)).toBe("outline");
  });

  it("treats only success/failed/cancelled/denied as terminal", () => {
    for (const s of ["queued", "running"] as JobStatus[]) {
      expect(isTerminalStatus(s)).toBe(false);
    }
    for (const s of ["success", "failed", "cancelled", "denied"] as JobStatus[]) {
      expect(isTerminalStatus(s)).toBe(true);
    }
    expect(TERMINAL_STATUSES.size).toBe(4);
  });
});

describe("approval status helpers", () => {
  it("returns a label for every approval state", () => {
    expect(approvalStatusLabel("not_required")).toBe("no approval");
    expect(approvalStatusLabel("pending")).toMatch(/awaiting/);
    expect(approvalStatusLabel("approved")).toBe("approved");
    expect(approvalStatusLabel("denied")).toBe("denied");
  });

  it("falls back to the raw value for unknown states", () => {
    expect(approvalStatusLabel("wat" as unknown as "not_required")).toBe("wat");
    expect(approvalStatusTone("wat" as unknown as "not_required")).toBe("info");
  });
});

describe("risk level helpers", () => {
  it("labels null as a dash", () => {
    expect(riskLevelLabel(null)).toBe("—");
  });

  it("marks high and critical as destructive", () => {
    expect(riskLevelTone("high")).toBe("destructive");
    expect(riskLevelTone("critical")).toBe("destructive");
  });

  it("marks medium as warning and low as info", () => {
    expect(riskLevelTone("medium")).toBe("warning");
    expect(riskLevelTone("low")).toBe("info");
  });
});

describe("log stream helpers", () => {
  it("labels all three streams", () => {
    expect(logStreamLabel("stdout")).toBe("stdout");
    expect(logStreamLabel("stderr")).toBe("stderr");
    expect(logStreamLabel("system")).toBe("system");
  });

  it("tones stderr as warning and system as info", () => {
    expect(logStreamTone("stderr")).toBe("warning");
    expect(logStreamTone("system")).toBe("info");
    expect(logStreamTone("stdout")).toBe("outline");
  });
});

describe("truncateCommand", () => {
  it("returns the string unchanged when shorter than the limit", () => {
    expect(truncateCommand("echo hi", 80)).toBe("echo hi");
  });

  it("truncates and adds an ellipsis when too long", () => {
    const out = truncateCommand("a".repeat(120), 10);
    expect(out.length).toBe(10);
    expect(out.endsWith("…")).toBe(true);
  });
});

describe("formatDuration", () => {
  it("returns a dash when no start time is given", () => {
    expect(formatDuration(null, null)).toBe("—");
  });

  it("renders milliseconds under one second", () => {
    const t0 = new Date("2026-06-23T00:00:00Z").toISOString();
    const t1 = new Date("2026-06-23T00:00:00.500Z").toISOString();
    expect(formatDuration(t0, t1)).toBe("500ms");
  });

  it("renders minutes and seconds", () => {
    const t0 = new Date("2026-06-23T00:00:00Z").toISOString();
    const t1 = new Date("2026-06-23T00:02:05Z").toISOString();
    expect(formatDuration(t0, t1)).toBe("2m05s");
  });
});

describe("Job and JobLog shapes", () => {
  it("round-trips a sample job object", () => {
    const job: Job = {
      id: "j1",
      host_id: "h1",
      recipe_name: "healthcheck",
      command_summary: "echo ok",
      requested_by_user_id: "u1",
      status: "running",
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
    expect(job.id).toBe("j1");
    const log: JobLog = {
      id: 1,
      stream: "stdout",
      line_redacted: "ok",
      line_hash: "abc",
      timestamp: "2026-06-23T00:00:00Z",
    };
    expect(log.stream).toBe("stdout");
  });
});
