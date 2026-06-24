import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  CheckCircle2,
  Clock,
  Pause,
  PlayCircle,
  Power,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  ShieldOff,
  Terminal,
  XCircle,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  Box,
  Flex,
  Text,
  Heading,
  Button,
  Badge,
  Icon,
  Spinner,
  HStack,
  VStack,
  Grid,
  GridItem,
  Textarea,
} from "@chakra-ui/react";
import { ApiError } from "@/lib/api";
import {
  approveJob,
  cancelJob,
  denyJob,
  getJob,
  JobApiError,
  openLogStream,
  retryJob,
  type LogStreamHandle,
  type SseEvent,
} from "@/lib/jobsApi";
import {
  formatDuration,
  isTerminalStatus,
  jobStatusLabel,
  logStreamLabel,
  riskLevelLabel,
  truncateCommand,
  type Job,
  type JobLog,
  type JobStatus,
} from "@/lib/jobs";

// ─── helpers ─────────────────────────────────────────────────────────────

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? iso : t.toLocaleString();
}

function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  return n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`;
}

function isLikelySecret(text: string): boolean {
  return /-----BEGIN/.test(text);
}

function getStatusStyle(status: JobStatus) {
  switch (status) {
    case "running":   return { color: "#00F0FF", bg: "rgba(0,240,255,0.1)",   border: "rgba(0,240,255,0.25)",   icon: Clock };
    case "success":   return { color: "#39FF14", bg: "rgba(57,255,20,0.1)",   border: "rgba(57,255,20,0.25)",   icon: CheckCircle2 };
    case "failed":    return { color: "#FF3131", bg: "rgba(255,49,49,0.1)",   border: "rgba(255,49,49,0.25)",   icon: XCircle };
    case "queued":    return { color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)",  icon: Clock };
    case "cancelled": return { color: "#6B7280", bg: "rgba(107,114,128,0.1)", border: "rgba(107,114,128,0.25)", icon: Ban };
    case "denied":    return { color: "#F87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.25)", icon: XCircle };
    default:          return { color: "#6B7280", bg: "rgba(107,114,128,0.1)", border: "rgba(107,114,128,0.25)", icon: Clock };
  }
}

function getRiskStyle(risk: string) {
  switch (risk) {
    case "critical": return { color: "#FF3131", bg: "rgba(255,49,49,0.1)",   border: "rgba(255,49,49,0.25)" };
    case "high":     return { color: "#F87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.25)" };
    case "medium":   return { color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)" };
    default:         return { color: "#39FF14", bg: "rgba(57,255,20,0.1)",   border: "rgba(57,255,20,0.25)" };
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────

function InfoCard({ title, icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
      <Flex px={4} py={3} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10" align="center" gap={2}>
        <Icon as={icon} color="obsidian.cyan" w={3.5} h={3.5} />
        <Text fontSize="11px" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider" textTransform="uppercase">
          {title}
        </Text>
      </Flex>
      <Box p={4}>{children}</Box>
    </Box>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <Flex justify="space-between" align="center" py={1.5} borderBottom="1px solid" borderColor="rgba(255,255,255,0.04)">
      <Text fontSize="11px" color="obsidian.onSurfaceVariant" fontFamily="mono">{label}</Text>
      <Text fontSize="11px" color="white" fontFamily={mono ? "mono" : "body"} textAlign="right" maxW="60%"
        wordBreak="break-all">
        {value}
      </Text>
    </Flex>
  );
}

function LogLineRow({ line }: { line: JobLog }) {
  const suspicious = isLikelySecret(line.line_redacted);
  const streamColor =
    line.stream === "stderr" ? "#F59E0B" :
    line.stream === "system" ? "#00F0FF" : "#E2E8F0";
  const streamBg =
    line.stream === "stderr" ? "rgba(245,158,11,0.06)" :
    line.stream === "system" ? "rgba(0,240,255,0.04)" : "transparent";

  return (
    <Flex
      align="flex-start"
      gap={3}
      py={0.5}
      px={1}
      borderBottom="1px solid rgba(255,255,255,0.03)"
      bg={streamBg}
      _hover={{ bg: "rgba(255,255,255,0.02)" }}
      data-testid="log-line"
      data-stream={line.stream}
    >
      <Text w="45px" flexShrink={0} fontSize="9px" textTransform="uppercase" color="obsidian.onSurfaceVariant" fontFamily="mono" mt={0.5}>
        {logStreamLabel(line.stream)}
      </Text>
      <Text w="80px" flexShrink={0} fontSize="9px" color="obsidian.onSurfaceVariant" fontFamily="mono" mt={0.5}>
        {line.timestamp ? new Date(line.timestamp).toLocaleTimeString() : ""}
      </Text>
      <Text flex={1} fontSize="12px" fontFamily="mono" color={suspicious ? "#FF3131" : streamColor}
        wordBreak="break-all" lineHeight="tall">
        {suspicious ? `[REDACTION FAILED] ${line.line_redacted}` : (line.line_redacted || "\u00A0")}
      </Text>
    </Flex>
  );
}

// ─── Main component ───────────────────────────────────────────────────────

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [job, setJob] = useState<Job | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [denyReason, setDenyReason] = useState("");
  const [denyOpen, setDenyOpen] = useState(false);
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [liveStatus, setLiveStatus] = useState<JobStatus | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [paused, setPaused] = useState(false);

  const pausedRef = useRef(paused);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  const streamRef = useRef<LogStreamHandle | null>(null);

  useEffect(() => { pausedRef.current = paused; }, [paused]);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    setInitialLoading(true);
    setLoadError(null);
    try {
      const detail = await getJob(jobId);
      setJob(detail);
      setLogs(detail.logs ?? []);
    } catch (err) {
      const msg =
        err instanceof JobApiError ? err.detail :
        err instanceof ApiError ? err.message :
        err instanceof Error ? err.message : "Failed to load job.";
      setLoadError(msg);
    } finally {
      setInitialLoading(false);
    }
  }, [jobId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const currentStatus: JobStatus = liveStatus ?? job?.status ?? "queued";

  useEffect(() => {
    if (!jobId) return;
    streamRef.current?.close();
    streamRef.current = null;
    setStreamConnected(false);
    setStreamError(null);

    const handle = openLogStream(jobId, (event: SseEvent) => {
      setStreamConnected(true);
      if (event.kind === "log") {
        if (pausedRef.current) return;
        setLogs((prev) => {
          if (prev.some((p) => p.id === event.data.id)) return prev;
          return [...prev, event.data];
        });
      } else if (event.kind === "status") {
        const next = event.data.status as JobStatus;
        setLiveStatus(next);
        setJob((prev) => prev ? {
          ...prev,
          status: next,
          approval_status: event.data.approval_status as Job["approval_status"],
          exit_code: event.data.exit_code,
          started_at: event.data.started_at ?? prev.started_at,
          finished_at: event.data.finished_at ?? prev.finished_at,
          error_summary_redacted: event.data.error_summary_redacted ?? prev.error_summary_redacted,
        } : prev);
      }
    }, (err) => {
      setStreamConnected(false);
      setStreamError(err.message);
    });
    streamRef.current = handle;
    return () => { handle.close(); };
  }, [jobId]);

  useEffect(() => {
    if (!autoScroll) return;
    const el = logBoxRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs, autoScroll]);

  useEffect(() => {
    if (!liveStatus) return;
    if (isTerminalStatus(liveStatus)) void refresh();
  }, [liveStatus, refresh]);

  const doAction = async (key: string, fn: () => Promise<Job>) => {
    setActionPending(key);
    setActionError(null);
    try {
      const next = await fn();
      setJob(next);
      setLiveStatus(next.status);
    } catch (err) {
      setActionError(err instanceof JobApiError ? err.detail : err instanceof Error ? err.message : "Action failed.");
    } finally {
      setActionPending(null);
    }
  };

  const handleCancel  = () => doAction("cancel",  () => cancelJob(job!.id));
  const handleApprove = () => doAction("approve", () => approveJob(job!.id));
  const handleRetry   = async () => {
    setActionPending("retry");
    setActionError(null);
    try {
      const next = await retryJob(job!.id);
      navigate(`/jobs/${next.id}`, { replace: true });
    } catch (err) {
      setActionError(err instanceof JobApiError ? err.detail : err instanceof Error ? err.message : "Retry failed.");
      setActionPending(null);
    }
  };
  const handleDeny = async () => {
    setActionPending("deny");
    setActionError(null);
    try {
      const next = await denyJob(job!.id, denyReason.trim());
      setJob(next);
      setLiveStatus(next.status);
      setDenyOpen(false);
      setDenyReason("");
    } catch (err) {
      setActionError(err instanceof JobApiError ? err.detail : err instanceof Error ? err.message : "Deny failed.");
    } finally {
      setActionPending(null);
    }
  };

  const stats = useMemo(() => {
    const byStream: Record<JobLog["stream"], number> = { stdout: 0, stderr: 0, system: 0 };
    let totalBytes = 0;
    for (const l of logs) {
      byStream[l.stream] = (byStream[l.stream] ?? 0) + 1;
      totalBytes += l.line_redacted.length;
    }
    return { byStream, totalBytes };
  }, [logs]);

  // ── Loading / error states ──
  if (initialLoading) {
    return (
      <Flex align="center" justify="center" h="50vh" gap={3}>
        <Spinner size="xl" color="obsidian.cyan" thickness="3px" />
        <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">Loading job…</Text>
      </Flex>
    );
  }

  if (loadError || !job) {
    return (
      <Flex direction="column" gap={4}>
        <Button leftIcon={<Icon as={ArrowLeft} w={4} h={4} />} size="sm" variant="outline"
          borderColor="obsidian.border" color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs"
          w="fit-content" _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
          onClick={() => navigate("/jobs")}>
          Back to jobs
        </Button>
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)" borderRadius="md" p={4}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F87171" w={5} h={5} />
            <VStack align="start" spacing={0}>
              <Text fontSize="sm" fontWeight="bold" color="#F87171" fontFamily="mono">
                {loadError ? "Could not load job" : "Job not found"}
              </Text>
              <Text fontSize="xs" color="obsidian.onSurfaceVariant">
                {loadError ?? "The job you requested no longer exists."}
              </Text>
            </VStack>
          </HStack>
        </Box>
      </Flex>
    );
  }

  const canCancel  = !isTerminalStatus(currentStatus) && currentStatus !== "cancelled";
  const canRetry   = isTerminalStatus(currentStatus);
  const canApprove = job.approval_status === "pending";
  const st         = getStatusStyle(currentStatus);
  const risk       = getRiskStyle(job.risk_level ?? "low");

  return (
    <Flex direction="column" gap={6}>

      {/* ── Header ── */}
      <Flex justify="space-between" align="flex-start" wrap="wrap" gap={4}>
        <Flex align="flex-start" gap={4}>
          <Button leftIcon={<Icon as={ArrowLeft} w={4} h={4} />} size="sm" variant="outline"
            borderColor="obsidian.border" color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs"
            h="32px" flexShrink={0} _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            onClick={() => navigate("/jobs")}>
            Jobs
          </Button>
          <VStack align="start" spacing={1}>
            <Heading as="h1" size="md" color="white" fontWeight="bold" letterSpacing="-0.02em" lineHeight="short">
              {job.recipe_name ?? truncateCommand(job.command_summary, 60)}
            </Heading>
            <HStack spacing={2} flexWrap="wrap">
              <Badge px={2} py={0.5} borderRadius="sm" fontSize="9px" fontFamily="mono" fontWeight="bold"
                letterSpacing="wider" bg={st.bg} color={st.color} border="1px solid" borderColor={st.border}>
                <HStack spacing={1}>
                  <Icon as={st.icon} w={2.5} h={2.5} />
                  <Text>{jobStatusLabel(currentStatus).toUpperCase()}</Text>
                </HStack>
              </Badge>
              <Badge px={2} py={0.5} borderRadius="sm" fontSize="9px" fontFamily="mono" fontWeight="bold"
                letterSpacing="wider" bg={risk.bg} color={risk.color} border="1px solid" borderColor={risk.border}>
                RISK: {riskLevelLabel(job.risk_level).toUpperCase()}
              </Badge>
              {job.approval_status && (
                <Badge px={2} py={0.5} borderRadius="sm" fontSize="9px" fontFamily="mono"
                  bg="rgba(107,114,128,0.1)" color="#9CA3AF" border="1px solid rgba(107,114,128,0.2)">
                  {job.approval_status.toUpperCase()}
                </Badge>
              )}
            </HStack>
            <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
              id: {job.id}
            </Text>
          </VStack>
        </Flex>

        {/* Actions */}
        <HStack spacing={2} flexWrap="wrap">
          <Button leftIcon={<Icon as={RefreshCw} w={3.5} h={3.5} />} size="sm" variant="outline"
            borderColor="obsidian.border" color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs"
            h="32px" _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            onClick={refresh} isLoading={initialLoading}>
            Refresh
          </Button>
          {canApprove && (
            <>
              <Button leftIcon={<Icon as={ShieldCheck} w={3.5} h={3.5} />} size="sm"
                bg="rgba(57,255,20,0.1)" color="#39FF14" border="1px solid rgba(57,255,20,0.25)"
                fontFamily="mono" fontSize="xs" h="32px"
                _hover={{ bg: "rgba(57,255,20,0.18)" }}
                isLoading={actionPending === "approve"} isDisabled={actionPending !== null}
                onClick={handleApprove}>
                Approve
              </Button>
              <Button leftIcon={<Icon as={ShieldOff} w={3.5} h={3.5} />} size="sm"
                bg="rgba(255,49,49,0.1)" color="#FF3131" border="1px solid rgba(255,49,49,0.25)"
                fontFamily="mono" fontSize="xs" h="32px"
                _hover={{ bg: "rgba(255,49,49,0.18)" }}
                isDisabled={actionPending !== null} onClick={() => setDenyOpen(true)}>
                Deny
              </Button>
            </>
          )}
          {canCancel && (
            <Button leftIcon={<Icon as={Ban} w={3.5} h={3.5} />} size="sm"
              bg="rgba(107,114,128,0.1)" color="#9CA3AF" border="1px solid rgba(107,114,128,0.2)"
              fontFamily="mono" fontSize="xs" h="32px" _hover={{ bg: "rgba(107,114,128,0.18)" }}
              isLoading={actionPending === "cancel"} isDisabled={actionPending !== null}
              onClick={handleCancel}>
              Cancel
            </Button>
          )}
          {canRetry && (
            <Button leftIcon={<Icon as={PlayCircle} w={3.5} h={3.5} />} size="sm"
              bg="obsidian.cyan" color="black" fontFamily="mono" fontSize="xs" h="32px"
              fontWeight="bold" _hover={{ bg: "cyan.300" }}
              isLoading={actionPending === "retry"} isDisabled={actionPending !== null}
              onClick={handleRetry}>
              Retry
            </Button>
          )}
        </HStack>
      </Flex>

      {/* Action error */}
      {actionError && (
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)" borderRadius="md" p={3}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F87171" w={4} h={4} />
            <Text fontSize="xs" color="#F87171" fontFamily="mono">{actionError}</Text>
          </HStack>
        </Box>
      )}

      {/* ── Info cards ── */}
      <Grid templateColumns={{ base: "1fr", lg: "repeat(3, 1fr)" }} gap={4}>
        {/* Status card */}
        <GridItem>
          <InfoCard title="Status" icon={Power}>
            <VStack align="stretch" spacing={0}>
              <DetailRow label="Status"    value={jobStatusLabel(currentStatus)} />
              <DetailRow label="Exit code" value={job.exit_code != null ? String(job.exit_code) : "—"} />
              <DetailRow label="Duration"  value={formatDuration(job.started_at, job.finished_at)} />
              <DetailRow label="Timeout"   value={`${job.timeout_seconds}s`} />
              <DetailRow label="Started"   value={formatTime(job.started_at)} />
              <DetailRow label="Finished"  value={formatTime(job.finished_at)} />
              <DetailRow label="Created"   value={formatTime(job.created_at)} />
            </VStack>
            {job.error_summary_redacted && (
              <Box mt={3} bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.2)" borderRadius="md" p={3}>
                <HStack spacing={2} mb={1}>
                  <Icon as={AlertTriangle} color="#F87171" w={3.5} h={3.5} />
                  <Text fontSize="10px" fontWeight="bold" color="#F87171" fontFamily="mono">Error (redacted)</Text>
                </HStack>
                <Text fontSize="11px" color="#F87171" fontFamily="mono">{job.error_summary_redacted}</Text>
              </Box>
            )}
          </InfoCard>
        </GridItem>

        {/* Approval card */}
        <GridItem>
          <InfoCard title="Approval" icon={ShieldCheck}>
            <VStack align="stretch" spacing={0}>
              <DetailRow label="Approval"            value={job.approval_status ?? "—"} />
              <DetailRow label="Risk"                value={riskLevelLabel(job.risk_level)} />
              <DetailRow label="Requested by"        value={job.requested_by_user_id ?? "system"} mono />
              <DetailRow label="Approved by"         value={job.approved_by_user_id ?? "—"} mono />
              <DetailRow label="Approved at"         value={formatTime(job.approved_at)} />
              <DetailRow label="Approval requested"  value={formatTime(job.approval_requested_at)} />
              <DetailRow label="Host"                value={job.host_id ?? "(none)"} mono />
              {job.idempotency_key && (
                <DetailRow label="Idempotency key" value={job.idempotency_key} mono />
              )}
            </VStack>
          </InfoCard>
        </GridItem>

        {/* Live stream card */}
        <GridItem>
          <InfoCard title="Live Stream" icon={Terminal}>
            <VStack align="stretch" spacing={3}>
              {/* Stream status */}
              <HStack spacing={2}>
                <Icon as={streamConnected ? Wifi : WifiOff}
                  w={3.5} h={3.5} color={streamConnected ? "#39FF14" : "#6B7280"} />
                <Text fontSize="11px" fontFamily="mono"
                  color={streamConnected ? "#39FF14" : "#6B7280"}>
                  {streamConnected ? "SSE Connected" : streamError ? `Offline: ${streamError}` : "Connecting…"}
                </Text>
              </HStack>

              {/* Stream counters */}
              <HStack spacing={2} flexWrap="wrap">
                {[
                  { label: "stdout", count: stats.byStream.stdout, color: "#E2E8F0" },
                  { label: "stderr", count: stats.byStream.stderr, color: "#F59E0B" },
                  { label: "system", count: stats.byStream.system, color: "#00F0FF" },
                ].map(({ label, count, color }) => (
                  <Badge key={label} px={2} py={0.5} borderRadius="sm" fontSize="10px" fontFamily="mono"
                    bg="rgba(255,255,255,0.05)" color={color} border="1px solid rgba(255,255,255,0.08)">
                    {label}: {count}
                  </Badge>
                ))}
              </HStack>

              {/* Controls */}
              <HStack spacing={2}>
                <Button leftIcon={<Icon as={ScrollText} w={3} h={3} />} size="xs"
                  variant="outline" fontFamily="mono" fontSize="10px" h="26px"
                  borderColor={autoScroll ? "obsidian.cyan" : "obsidian.border"}
                  color={autoScroll ? "obsidian.cyan" : "obsidian.onSurfaceVariant"}
                  _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
                  onClick={() => setAutoScroll((v) => !v)}>
                  {autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
                </Button>
                <Button leftIcon={<Icon as={paused ? PlayCircle : Pause} w={3} h={3} />} size="xs"
                  variant="outline" fontFamily="mono" fontSize="10px" h="26px"
                  borderColor="obsidian.border" color="obsidian.onSurfaceVariant"
                  _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
                  onClick={() => setPaused((v) => !v)}>
                  {paused ? "Resume" : "Pause"}
                </Button>
              </HStack>

              <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                {formatBytes(stats.totalBytes)} redacted · secrets never reach the dashboard
              </Text>
            </VStack>
          </InfoCard>
        </GridItem>
      </Grid>

      {/* ── Log viewer ── */}
      <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
        <Flex px={5} py={3} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10"
          align="center" justify="space-between">
          <HStack spacing={2}>
            <Icon as={ScrollText} color="obsidian.cyan" w={4} h={4} />
            <Text fontSize="11px" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider" textTransform="uppercase">
              Output Log
            </Text>
            <Badge fontSize="10px" fontFamily="mono" bg="rgba(0,240,255,0.08)" color="obsidian.cyan"
              border="1px solid rgba(0,240,255,0.15)" px={2} py={0.5} borderRadius="sm">
              {logs.length} lines
            </Badge>
          </HStack>
          <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
            {paused ? "⏸ PAUSED" : autoScroll ? "▼ AUTO-SCROLL" : "MANUAL"}
          </Text>
        </Flex>

        <Box
          ref={logBoxRef}
          maxH="480px"
          overflowY="auto"
          bg="#060608"
          px={4}
          py={3}
          data-testid="log-viewer"
          sx={{
            "&::-webkit-scrollbar": { width: "6px" },
            "&::-webkit-scrollbar-track": { background: "transparent" },
            "&::-webkit-scrollbar-thumb": { background: "rgba(255,255,255,0.1)", borderRadius: "3px" },
          }}
        >
          {logs.length === 0 ? (
            <Flex align="center" justify="center" py={12} direction="column" gap={2}>
              <Icon as={Terminal} w={6} h={6} color="obsidian.onSurfaceVariant" opacity={0.4} />
              <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">
                No output yet. Lines appear here as the worker emits them.
              </Text>
            </Flex>
          ) : (
            logs.map((line) => <LogLineRow key={line.id} line={line} />)
          )}
        </Box>
      </Box>

      {/* ── Command card ── */}
      <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
        <Flex px={5} py={3} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10" align="center" gap={2}>
          <Icon as={Terminal} color="obsidian.cyan" w={3.5} h={3.5} />
          <Text fontSize="11px" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider" textTransform="uppercase">
            Command
          </Text>
        </Flex>
        <Box p={4}>
          <Box bg="#060608" border="1px solid" borderColor="obsidian.border" borderRadius="md"
            p={4} maxH="200px" overflowY="auto">
            <Text fontSize="12px" fontFamily="mono" color="#E2E8F0" whiteSpace="pre-wrap" wordBreak="break-all">
              {job.command_summary || "(empty)"}
            </Text>
          </Box>
        </Box>
      </Box>

      {/* ── Deny modal ── */}
      {denyOpen && (
        <Box position="fixed" inset={0} zIndex={50} bg="rgba(0,0,0,0.75)"
          display="flex" alignItems="center" justifyContent="center" p={4}>
          <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border"
            borderRadius="lg" p={6} w="full" maxW="440px" boxShadow="0 0 40px rgba(0,0,0,0.6)">
            <HStack spacing={3} mb={3}>
              <Icon as={ShieldOff} color="#FF3131" w={5} h={5} />
              <Text fontWeight="bold" color="white" fontSize="sm" fontFamily="mono">Deny Job</Text>
            </HStack>
            <Text fontSize="xs" color="obsidian.onSurfaceVariant" mb={4}>
              Provide a short reason. The text is run through the redaction engine before being persisted.
            </Text>
            <Textarea
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
              placeholder="Why is this job being denied?"
              maxLength={2000}
              rows={4}
              bg="#0A0A0C"
              border="1px solid"
              borderColor="obsidian.border"
              color="white"
              fontSize="sm"
              fontFamily="mono"
              borderRadius="md"
              resize="vertical"
              _placeholder={{ color: "obsidian.onSurfaceVariant" }}
              _focus={{ borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" }}
              mb={4}
            />
            <HStack justify="flex-end" spacing={3}>
              <Button size="sm" variant="outline" borderColor="obsidian.border" color="obsidian.onSurfaceVariant"
                fontFamily="mono" fontSize="xs" _hover={{ borderColor: "obsidian.cyan" }}
                isDisabled={actionPending !== null} onClick={() => setDenyOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" bg="rgba(255,49,49,0.15)" color="#F87171"
                border="1px solid rgba(255,49,49,0.3)" fontFamily="mono" fontSize="xs"
                _hover={{ bg: "rgba(255,49,49,0.25)" }}
                isLoading={actionPending === "deny"} isDisabled={actionPending !== null}
                onClick={handleDeny}>
                Deny Job
              </Button>
            </HStack>
          </Box>
        </Box>
      )}
    </Flex>
  );
}

// keep unused icon imports quiet
export { CheckCircle2 };
