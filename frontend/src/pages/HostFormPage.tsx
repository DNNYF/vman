import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Server, AlertTriangle } from "lucide-react";
import {
  Box,
  Flex,
  Text,
  Heading,
  Button,
  Icon,
  Spinner,
  HStack,
  VStack,
} from "@chakra-ui/react";
import { HostForm } from "@/components/hosts/HostForm";
import { ApiError } from "@/lib/api";
import { createHost, getHost, HostApiError, updateHost } from "@/lib/hostsApi";
import type { Host, HostCreatePayload, HostUpdatePayload } from "@/lib/hosts";

interface PageProps {
  mode: "create" | "edit";
}

export function HostFormPage({ mode }: PageProps) {
  const { hostId } = useParams<{ hostId: string }>();
  const navigate = useNavigate();
  const [host, setHost] = useState<Host | null>(null);
  const [loading, setLoading] = useState(mode === "edit");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== "edit" || !hostId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getHost(hostId)
      .then((row) => { if (!cancelled) setHost(row); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof HostApiError) setError(err.detail);
        else if (err instanceof ApiError) setError(err.message);
        else if (err instanceof Error) setError(err.message);
        else setError("Failed to load host.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode, hostId]);

  const handleSubmit = async (payload: HostCreatePayload) => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        const created = await createHost(payload);
        navigate(`/hosts/${created.id}`, { replace: true });
        return;
      }
      if (!hostId) return;
      const updatePayload: HostUpdatePayload = payload;
      const updated = await updateHost(hostId, updatePayload);
      setHost(updated);
      navigate(`/hosts/${updated.id}`, { replace: true });
    } catch (err) {
      if (err instanceof HostApiError) setError(err.detail);
      else if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error) setError(err.message);
      else setError("Failed to save host.");
      setBusy(false);
    }
  };

  const isCreate = mode === "create";

  return (
    <Flex direction="column" gap={6}>
      {/* ── Header ── */}
      <Flex align="center" gap={4}>
        <Button
          leftIcon={<Icon as={ArrowLeft} w={4} h={4} />}
          size="sm"
          variant="outline"
          borderColor="obsidian.border"
          color="obsidian.onSurfaceVariant"
          fontFamily="mono"
          fontSize="xs"
          h="32px"
          _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
          onClick={() => navigate(isCreate ? "/hosts" : (hostId ? `/hosts/${hostId}` : "/hosts"))}
        >
          {isCreate ? "Back to hosts" : "Back to host"}
        </Button>
        <VStack align="start" spacing={0}>
          <Heading as="h1" size="md" color="white" fontWeight="bold" letterSpacing="-0.02em">
            {isCreate ? "Add Host" : `Edit: ${host?.name ?? "…"}`}
          </Heading>
          <Text fontSize="xs" color="obsidian.onSurfaceVariant">
            {isCreate
              ? "Register a new target VPS. Secrets are never displayed — only vault references."
              : "Update metadata for this host. Rotate secrets separately in the vault."}
          </Text>
        </VStack>
      </Flex>

      {/* ── Error banner ── */}
      {error && !loading && (
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)"
          borderRadius="md" p={4}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F87171" w={4} h={4} />
            <Text fontSize="xs" color="#F87171" fontFamily="mono">{error}</Text>
          </HStack>
        </Box>
      )}

      {/* ── Content ── */}
      {isCreate ? (
        <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
          {/* Card header */}
          <Flex px={6} py={4} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10" align="center" gap={3}>
            <Box w="28px" h="28px" borderRadius="md" bg="rgba(0,240,255,0.08)"
              border="1px solid rgba(0,240,255,0.15)" display="flex" alignItems="center" justifyContent="center">
              <Icon as={Server} w={4} h={4} color="obsidian.cyan" />
            </Box>
            <VStack align="start" spacing={0}>
              <Text fontSize="sm" fontWeight="bold" color="white" fontFamily="mono">New Host</Text>
              <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                You will need a credential ID from the encrypted vault.
              </Text>
            </VStack>
          </Flex>
          <Box p={6}>
            <HostForm
              submitLabel="Create Host"
              onSubmit={handleSubmit}
              busy={busy}
              errorMessage={null}
              onCancel={() => navigate("/hosts")}
            />
          </Box>
        </Box>
      ) : loading ? (
        <Flex align="center" justify="center" h="40vh" gap={3}>
          <Spinner size="lg" color="obsidian.cyan" thickness="3px" />
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">Loading host…</Text>
        </Flex>
      ) : host ? (
        <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
          {/* Card header */}
          <Flex px={6} py={4} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10" align="center" justify="space-between">
            <Flex align="center" gap={3}>
              <Box w="28px" h="28px" borderRadius="md" bg="rgba(0,240,255,0.08)"
                border="1px solid rgba(0,240,255,0.15)" display="flex" alignItems="center" justifyContent="center">
                <Icon as={Server} w={4} h={4} color="obsidian.cyan" />
              </Box>
              <VStack align="start" spacing={0}>
                <Text fontSize="sm" fontWeight="bold" color="white" fontFamily="mono">{host.name}</Text>
                <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                  {host.hostname_or_ip}:{host.ssh_port}
                </Text>
              </VStack>
            </Flex>
            <Button
              size="xs"
              variant="ghost"
              color="obsidian.cyan"
              fontFamily="mono"
              fontSize="10px"
              _hover={{ bg: "rgba(0,240,255,0.06)" }}
              onClick={() => navigate(`/hosts/${host.id}`)}
            >
              View detail →
            </Button>
          </Flex>
          <Box p={6}>
            <HostForm
              initial={host}
              submitLabel="Save Changes"
              onSubmit={handleSubmit}
              busy={busy}
              errorMessage={null}
              onCancel={() => navigate(`/hosts/${host.id}`)}
            />
          </Box>
        </Box>
      ) : (
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)" borderRadius="md" p={6}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F87171" w={5} h={5} />
            <VStack align="start" spacing={0}>
              <Text fontSize="sm" fontWeight="bold" color="#F87171" fontFamily="mono">Host not found</Text>
              <Text fontSize="xs" color="obsidian.onSurfaceVariant">The host you are trying to edit no longer exists.</Text>
            </VStack>
          </HStack>
        </Box>
      )}
    </Flex>
  );
}
