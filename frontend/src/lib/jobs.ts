/**
 * Shared TypeScript types and small helpers for the jobs dashboard.
 *
 * The fields mirror the backend Pydantic schemas (see
 * ``backend/vman/api/routes_jobs.py``) but the wire shape is kept
 * narrow on purpose: the UI never receives plaintext credentials,
 * and the only command-related text we display is the redacted
 * command summary.
 */

export type JobStatus =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "cancelled"
  | "denied";

export type ApprovalStatus =
  | "not_required"
  | "pending"
  | "approved"
  | "denied";

export type JobRiskLevel = "low" | "medium" | "high" | "critical" | null;

export type LogStream = "stdout" | "stderr" | "system";

export interface Job {
  id: string;
  host_id: string | null;
  recipe_name: string | null;
  command_summary: string;
  requested_by_user_id: string | null;
  status: JobStatus;
  risk_level: JobRiskLevel;
  approval_status: ApprovalStatus;
  approval_requested_at: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  timeout_seconds: number;
  exit_code: number | null;
  error_summary_redacted: string | null;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * A redacted log line. The backend has already scrubbed secrets via
 * the redaction engine (see ``backend/vman/security/redaction.py``);
 * the UI MUST treat the text as already-safe and MUST NOT re-render
 * the raw value through any kind of "formatting" that could undo
 * redaction.
 */
export interface JobLog {
  id: number;
  stream: LogStream;
  line_redacted: string;
  line_hash: string | null;
  timestamp: string;
}

/**
 * Job detail response that includes the last N log lines.
 * The UI uses this as the initial render before the SSE stream
 * catches up with any new lines.
 */
export interface JobDetail extends Job {
  logs: JobLog[];
}

export const JOB_STATUSES: { value: JobStatus; label: string; tone: JobTone }[] = [
  { value: "queued", label: "queued", tone: "info" },
  { value: "running", label: "running", tone: "info" },
  { value: "success", label: "success", tone: "success" },
  { value: "failed", label: "failed", tone: "destructive" },
  { value: "cancelled", label: "cancelled", tone: "warning" },
  { value: "denied", label: "denied", tone: "destructive" },
];

export const APPROVAL_STATUSES: {
  value: ApprovalStatus;
  label: string;
  tone: JobTone;
}[] = [
  { value: "not_required", label: "no approval", tone: "info" },
  { value: "pending", label: "awaiting approval", tone: "warning" },
  { value: "approved", label: "approved", tone: "success" },
  { value: "denied", label: "denied", tone: "destructive" },
];

export type JobTone = "info" | "success" | "warning" | "destructive" | "outline";

export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  "success",
  "failed",
  "cancelled",
  "denied",
]);

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function jobStatusLabel(status: JobStatus): string {
  return JOB_STATUSES.find((s) => s.value === status)?.label ?? status;
}

export function jobStatusTone(status: JobStatus): JobTone {
  return JOB_STATUSES.find((s) => s.value === status)?.tone ?? "outline";
}

export function approvalStatusLabel(status: ApprovalStatus): string {
  return (
    APPROVAL_STATUSES.find((s) => s.value === status)?.label ?? status
  );
}

export function approvalStatusTone(status: ApprovalStatus): JobTone {
  return APPROVAL_STATUSES.find((s) => s.value === status)?.tone ?? "info";
}

export function riskLevelLabel(level: JobRiskLevel): string {
  if (!level) return "—";
  return level;
}

export function riskLevelTone(level: JobRiskLevel): JobTone {
  if (level === "critical" || level === "high") return "destructive";
  if (level === "medium") return "warning";
  return "info";
}

/**
 * A short, single-line preview of the command summary that fits in
 * a table cell. The backend may have stored up to 2048 characters; we
 * truncate aggressively and add an ellipsis.
 */
export function truncateCommand(command: string, max = 80): string {
  if (command.length <= max) return command;
  return `${command.slice(0, max - 1)}…`;
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const s = new Date(start).getTime();
  if (Number.isNaN(s)) return start;
  const finish = end ? new Date(end).getTime() : Date.now();
  const ms = Math.max(0, finish - s);
  if (ms < 1000) return `${ms}ms`;
  const s_total = Math.floor(ms / 1000);
  if (s_total < 60) return `${s_total}s`;
  const m = Math.floor(s_total / 60);
  const r = s_total % 60;
  return `${m}m${r.toString().padStart(2, "0")}s`;
}

export function logStreamLabel(stream: LogStream): string {
  if (stream === "stdout") return "stdout";
  if (stream === "stderr") return "stderr";
  return "system";
}

export function logStreamTone(stream: LogStream): JobTone {
  if (stream === "stderr") return "warning";
  if (stream === "system") return "info";
  return "outline";
}
