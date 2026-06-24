import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Flex,
  Text,
  Heading,
  Button,
  Select,
  Input,
  Textarea,
  FormControl,
  FormLabel,
  FormHelperText,
  HStack,
  VStack,
  Badge,
  Spinner,
  Icon,
  IconButton,
  Tooltip,
  SimpleGrid,
  useToast,
} from "@chakra-ui/react";
import {
  Plus,
  Trash2,
  Key,
  ShieldAlert,
  ArrowLeft,
  Lock,
  RefreshCcw,
  XCircle,
} from "lucide-react";
import { listCredentials, createCredential, deleteCredential, type Credential } from "@/lib/credentialsApi";

// ─── helpers ───────────────────────────────────────────────────────────────

function getKindStyle(kind: string): { color: string; bg: string; border: string; label: string } {
  if (kind.includes("key"))      return { color: "#A78BFA", bg: "rgba(167,139,250,0.1)", border: "rgba(167,139,250,0.25)", label: kind.replace(/_/g, " ") };
  if (kind.includes("password")) return { color: "#00F0FF", bg: "rgba(0,240,255,0.08)",  border: "rgba(0,240,255,0.2)",   label: kind.replace(/_/g, " ") };
  if (kind.includes("sudo"))     return { color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)", label: kind.replace(/_/g, " ") };
  return { color: "#9CA3AF", bg: "rgba(107,114,128,0.1)", border: "rgba(107,114,128,0.2)", label: kind.replace(/_/g, " ") };
}

// ─── Delete confirm modal ─────────────────────────────────────────────────

function DeleteModal({
  onConfirm,
  onCancel,
  deleting,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}) {
  return (
    <Box position="fixed" inset={0} zIndex={50} bg="rgba(0,0,0,0.75)"
      display="flex" alignItems="center" justifyContent="center" p={4}>
      <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border"
        borderRadius="lg" p={6} w="full" maxW="420px" boxShadow="0 0 40px rgba(0,0,0,0.6)">
        <HStack spacing={3} mb={3}>
          <Icon as={XCircle} color="#FF3131" w={5} h={5} />
          <Text fontWeight="bold" color="white" fontSize="sm" fontFamily="mono">
            Delete Credential?
          </Text>
        </HStack>
        <Text fontSize="xs" color="obsidian.onSurfaceVariant" mb={6}>
          This action is permanent and cannot be undone. Any hosts referencing this
          credential may fail to connect.
        </Text>
        <HStack justify="flex-end" spacing={3}>
          <Button size="sm" variant="outline" borderColor="obsidian.border"
            color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs"
            _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            isDisabled={deleting} onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" bg="rgba(255,49,49,0.15)" color="#F87171"
            border="1px solid rgba(255,49,49,0.3)" fontFamily="mono" fontSize="xs"
            _hover={{ bg: "rgba(255,49,49,0.25)" }}
            isLoading={deleting} onClick={onConfirm}>
            Delete Credential
          </Button>
        </HStack>
      </Box>
    </Box>
  );
}

// ─── List page ─────────────────────────────────────────────────────────────

export function CredentialsListPage() {
  const [creds, setCreds] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const navigate = useNavigate();
  const toast = useToast();

  const fetchCreds = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listCredentials();
      setCreds(data);
    } catch (err: any) {
      setError(err.message || "Failed to load credentials.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchCreds(); }, []);

  const handleDeleteConfirm = async () => {
    if (!deleteId) return;
    try {
      setDeleting(true);
      await deleteCredential(deleteId);
      toast({ title: "Credential deleted", status: "success", duration: 3000, isClosable: true });
      setDeleteId(null);
      fetchCreds();
    } catch (err: any) {
      toast({ title: "Error", description: err.detail || err.message, status: "error", duration: 5000, isClosable: true });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Flex direction="column" gap={6}>
      {/* ── Header ── */}
      <Flex justify="space-between" align="flex-end" wrap="wrap" gap={3}>
        <VStack align="start" spacing={0.5}>
          <Heading as="h1" size="lg" color="white" fontWeight="bold" letterSpacing="-0.02em">
            Encrypted Credentials
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant">
            Securely store SSH passwords, private keys, and API tokens.
          </Text>
        </VStack>
        <HStack spacing={2}>
          <Button
            leftIcon={<Icon as={RefreshCcw} w={3.5} h={3.5} />}
            size="sm" variant="outline" borderColor="obsidian.border"
            color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs" h="36px"
            _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            onClick={fetchCreds} isLoading={loading}>
            Refresh
          </Button>
          <Button
            leftIcon={<Icon as={Plus} w={4} h={4} />}
            bg="obsidian.cyan" color="black" fontFamily="mono" fontSize="xs"
            fontWeight="bold" px={5} h="36px" borderRadius="md"
            _hover={{ bg: "cyan.300" }} _active={{ transform: "scale(0.97)" }}
            onClick={() => navigate("/credentials/new")}>
            Add Credential
          </Button>
        </HStack>
      </Flex>

      {/* ── Security info banner ── */}
      <Box bg="linear-gradient(135deg, #0E1117 0%, #111318 100%)" border="1px solid"
        borderColor="obsidian.border" borderRadius="md" p={4} position="relative" overflow="hidden">
        <Box position="absolute" top={0} left={0} right={0} h="1px"
          bg="linear-gradient(90deg, transparent, rgba(0,240,255,0.4), transparent)" />
        <HStack spacing={3}>
          <Box w="32px" h="32px" borderRadius="md" bg="rgba(0,240,255,0.08)"
            border="1px solid rgba(0,240,255,0.15)" display="flex" alignItems="center" justifyContent="center" flexShrink={0}>
            <Icon as={Lock} w={4} h={4} color="obsidian.cyan" />
          </Box>
          <VStack align="start" spacing={0}>
            <Text fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider">
              AES-256-GCM ENCRYPTED VAULT
            </Text>
            <Text fontSize="11px" color="obsidian.onSurfaceVariant">
              All secrets are envelope-encrypted at rest. Plain-text never persists to disk or returns to the UI after creation.
            </Text>
          </VStack>
        </HStack>
      </Box>

      {/* ── Error ── */}
      {error && (
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)"
          borderRadius="md" p={3} fontSize="xs" color="#F87171" fontFamily="mono">
          ⚠ {error}
        </Box>
      )}

      {/* ── Loading ── */}
      {loading ? (
        <Flex align="center" justify="center" py={16}>
          <Spinner size="lg" color="obsidian.cyan" thickness="3px" />
        </Flex>
      ) : creds.length === 0 ? (
        /* ── Empty state ── */
        <Flex direction="column" align="center" justify="center" py={16} gap={4}
          border="1px dashed" borderColor="obsidian.border" borderRadius="md">
          <Box w="48px" h="48px" borderRadius="full" bg="rgba(0,240,255,0.06)"
            border="1px solid rgba(0,240,255,0.12)" display="flex" alignItems="center" justifyContent="center">
            <Icon as={Key} w={6} h={6} color="obsidian.onSurfaceVariant" />
          </Box>
          <VStack spacing={1}>
            <Text fontWeight="semibold" color="white" fontFamily="mono">No credentials found</Text>
            <Text fontSize="sm" color="obsidian.onSurfaceVariant">
              Add your first password or SSH private key to link with hosts.
            </Text>
          </VStack>
          <Button leftIcon={<Icon as={Plus} w={4} h={4} />}
            bg="obsidian.cyan" color="black" fontFamily="mono" fontSize="xs"
            fontWeight="bold" px={5} h="36px" _hover={{ bg: "cyan.300" }}
            onClick={() => navigate("/credentials/new")}>
            Add Credential
          </Button>
        </Flex>
      ) : (
        /* ── Table card ── */
        <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border"
          borderRadius="md" overflow="hidden">
          {/* Table header */}
          <Flex px={5} py={2.5} borderBottom="1px solid" borderColor="obsidian.border" bg="#0A0A0C">
            {[
              { label: "NAME",        w: "25%" },
              { label: "TYPE",        w: "18%" },
              { label: "FINGERPRINT", w: "30%" },
              { label: "CREATED",     w: "20%" },
              { label: "",            w: "7%"  },
            ].map((col) => (
              <Box key={col.label} w={col.w} flexShrink={0}>
                <Text fontSize="10px" fontWeight="bold" color="obsidian.onSurfaceVariant"
                  fontFamily="mono" letterSpacing="widest" textTransform="uppercase">
                  {col.label}
                </Text>
              </Box>
            ))}
          </Flex>

          {/* Rows */}
          {creds.map((cred) => {
            const kindStyle = getKindStyle(cred.kind);
            return (
              <Flex key={cred.id} px={5} py={3.5} borderBottom="1px solid"
                borderColor="obsidian.border" align="center"
                _hover={{ bg: "rgba(255,255,255,0.02)" }} transition="background 0.15s">

                {/* NAME */}
                <Box w="25%" flexShrink={0}>
                  <HStack spacing={2.5}>
                    <Box w="22px" h="22px" borderRadius="4px" flexShrink={0}
                      bg="rgba(0,240,255,0.08)" border="1px solid rgba(0,240,255,0.15)"
                      display="flex" alignItems="center" justifyContent="center">
                      <Icon as={Key} w={3} h={3} color="obsidian.cyan" />
                    </Box>
                    <Text fontSize="xs" fontWeight="semibold" color="white" fontFamily="mono">
                      {cred.name}
                    </Text>
                  </HStack>
                </Box>

                {/* KIND */}
                <Box w="18%" flexShrink={0}>
                  <Badge px={2} py={0.5} borderRadius="sm" fontSize="9px" fontFamily="mono"
                    fontWeight="bold" letterSpacing="wider"
                    bg={kindStyle.bg} color={kindStyle.color}
                    border="1px solid" borderColor={kindStyle.border}>
                    {kindStyle.label.toUpperCase()}
                  </Badge>
                </Box>

                {/* FINGERPRINT */}
                <Box w="30%" flexShrink={0} pr={4}>
                  <Text fontSize="11px" fontFamily="mono" color="obsidian.onSurfaceVariant"
                    noOfLines={1} wordBreak="break-all">
                    {cred.fingerprint || "—"}
                  </Text>
                </Box>

                {/* CREATED */}
                <Box w="20%" flexShrink={0}>
                  <Text fontSize="xs" fontFamily="mono" color="obsidian.onSurfaceVariant">
                    {new Date(cred.created_at).toLocaleString()}
                  </Text>
                </Box>

                {/* ACTION */}
                <Box w="7%" flexShrink={0} display="flex" justifyContent="flex-end">
                  <Tooltip label="Delete credential" placement="top" hasArrow>
                    <IconButton
                      aria-label="Delete credential"
                      icon={<Icon as={Trash2} w={3.5} h={3.5} />}
                      size="xs" variant="ghost" color="obsidian.onSurfaceVariant"
                      _hover={{ color: "#F87171", bg: "rgba(239,68,68,0.08)" }}
                      onClick={() => setDeleteId(cred.id)}
                    />
                  </Tooltip>
                </Box>
              </Flex>
            );
          })}
        </Box>
      )}

      {/* ── Delete modal ── */}
      {deleteId && (
        <DeleteModal
          deleting={deleting}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteId(null)}
        />
      )}
    </Flex>
  );
}

// ─── Create page ───────────────────────────────────────────────────────────

const inputStyle = {
  bg: "#0A0A0C",
  border: "1px solid",
  borderColor: "obsidian.border",
  color: "white",
  fontSize: "sm",
  fontFamily: "mono",
  borderRadius: "md",
  _placeholder: { color: "obsidian.onSurfaceVariant" },
  _focus: { borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" },
  _hover: { borderColor: "rgba(255,255,255,0.2)" },
};

const labelStyle = {
  fontSize: "11px",
  fontWeight: "bold",
  color: "obsidian.onSurfaceVariant",
  fontFamily: "mono",
  letterSpacing: "wider",
  textTransform: "uppercase" as const,
  mb: 1.5,
};

const KIND_OPTIONS = [
  { value: "ssh_password",            label: "SSH Password" },
  { value: "ssh_private_key",         label: "SSH Private Key" },
  { value: "ssh_private_key_passphrase", label: "SSH Key Passphrase" },
  { value: "sudo_password",           label: "Sudo Password" },
  { value: "api_token",               label: "API Token" },
];

export function CredentialCreatePage() {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("ssh_password");
  const [plaintext, setPlaintext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !plaintext.trim()) {
      setError("Please fill out all fields.");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await createCredential({ name: name.trim(), kind, plaintext: plaintext.trim() });
      toast({ title: "Credential created", status: "success", duration: 3000, isClosable: true });
      navigate("/credentials");
    } catch (err: any) {
      setError(err.detail || err.message || "Failed to create credential.");
    } finally {
      setSubmitting(false);
    }
  };

  const selectedKindStyle = getKindStyle(kind);

  return (
    <Flex direction="column" gap={6}>
      {/* ── Header ── */}
      <Flex align="center" gap={4}>
        <Button leftIcon={<Icon as={ArrowLeft} w={4} h={4} />} size="sm" variant="outline"
          borderColor="obsidian.border" color="obsidian.onSurfaceVariant" fontFamily="mono"
          fontSize="xs" h="32px" _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
          onClick={() => navigate("/credentials")}>
          Back
        </Button>
        <VStack align="start" spacing={0}>
          <Heading as="h1" size="md" color="white" fontWeight="bold" letterSpacing="-0.02em">
            Add Credential
          </Heading>
          <Text fontSize="xs" color="obsidian.onSurfaceVariant">
            Create a new envelope-encrypted secret in the secure database.
          </Text>
        </VStack>
      </Flex>

      {/* ── Form card ── */}
      <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border"
        borderRadius="md" overflow="hidden" maxW="680px">
        {/* Card header */}
        <Flex px={6} py={4} borderBottom="1px solid" borderColor="obsidian.border" bg="#0E0E10" align="center" gap={3}>
          <Box w="28px" h="28px" borderRadius="md" bg="rgba(0,240,255,0.08)"
            border="1px solid rgba(0,240,255,0.15)" display="flex" alignItems="center" justifyContent="center">
            <Icon as={Key} w={4} h={4} color="obsidian.cyan" />
          </Box>
          <VStack align="start" spacing={0}>
            <Text fontSize="sm" fontWeight="bold" color="white" fontFamily="mono">New Secret</Text>
            <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
              Payload is AES-256-GCM encrypted before writing to disk.
            </Text>
          </VStack>
          {kind && (
            <Badge ml="auto" px={2} py={0.5} borderRadius="sm" fontSize="9px" fontFamily="mono"
              fontWeight="bold" letterSpacing="wider"
              bg={selectedKindStyle.bg} color={selectedKindStyle.color}
              border="1px solid" borderColor={selectedKindStyle.border}>
              {selectedKindStyle.label.toUpperCase()}
            </Badge>
          )}
        </Flex>

        <Box as="form" onSubmit={handleSubmit} p={6}>
          <SimpleGrid columns={{ base: 1, md: 2 }} gap={5} mb={5}>
            {/* Name */}
            <FormControl isRequired>
              <FormLabel sx={labelStyle}>Display Name</FormLabel>
              <Input
                placeholder="e.g. staging-server-key"
                value={name}
                onChange={(e) => setName(e.target.value)}
                sx={inputStyle}
              />
              <FormHelperText fontSize="11px" color="obsidian.onSurfaceVariant" fontFamily="mono" mt={1.5}>
                Friendly label used in host assignment.
              </FormHelperText>
            </FormControl>

            {/* Kind */}
            <FormControl isRequired>
              <FormLabel sx={labelStyle}>Credential Type</FormLabel>
              <Select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                bg="#0A0A0C" border="1px solid" borderColor="obsidian.border"
                color="white" fontSize="sm" fontFamily="mono" borderRadius="md"
                _focus={{ borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" }}
              >
                {KIND_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} style={{ background: "#0A0A0C" }}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </FormControl>
          </SimpleGrid>

          {/* Payload */}
          <FormControl isRequired mb={5}>
            <FormLabel sx={labelStyle}>Secret Payload</FormLabel>
            <Textarea
              placeholder={
                kind === "ssh_private_key"
                  ? "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
                  : "Enter your secure password or token"
              }
              rows={kind === "ssh_private_key" ? 8 : 4}
              value={plaintext}
              onChange={(e) => setPlaintext(e.target.value)}
              bg="#0A0A0C"
              border="1px solid"
              borderColor="obsidian.border"
              color="white"
              fontSize="sm"
              fontFamily={kind === "ssh_private_key" ? "mono" : "body"}
              borderRadius="md"
              resize="vertical"
              _placeholder={{ color: "obsidian.onSurfaceVariant" }}
              _focus={{ borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" }}
              _hover={{ borderColor: "rgba(255,255,255,0.2)" }}
            />
          </FormControl>

          {/* Security notice */}
          <Box bg="rgba(245,158,11,0.06)" border="1px solid rgba(245,158,11,0.2)"
            borderRadius="md" p={3} mb={6}>
            <HStack spacing={3}>
              <Icon as={ShieldAlert} w={4} h={4} color="#F59E0B" flexShrink={0} />
              <Text fontSize="11px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                This payload is encrypted using AES-256-GCM before writing to disk. The plain-text never
                leaks to the database or UI after submission.
              </Text>
            </HStack>
          </Box>

          {/* Error */}
          {error && (
            <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)"
              borderRadius="md" p={3} mb={4}>
              <HStack spacing={2}>
                <Icon as={XCircle} color="#F87171" w={4} h={4} />
                <Text fontSize="xs" color="#F87171" fontFamily="mono">{error}</Text>
              </HStack>
            </Box>
          )}

          {/* Actions */}
          <Flex justify="flex-end" gap={3} pt={2} borderTop="1px solid" borderColor="obsidian.border">
            <Button size="sm" variant="outline" borderColor="obsidian.border"
              color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="xs" h="36px" px={6}
              _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
              isDisabled={submitting} onClick={() => navigate("/credentials")}>
              Cancel
            </Button>
            <Button type="submit" size="sm" bg="obsidian.cyan" color="black"
              fontFamily="mono" fontSize="xs" fontWeight="bold" h="36px" px={6}
              borderRadius="md" _hover={{ bg: "cyan.300" }} _active={{ transform: "scale(0.97)" }}
              isLoading={submitting} isDisabled={!name.trim() || !plaintext.trim()}>
              Save Credential
            </Button>
          </Flex>
        </Box>
      </Box>
    </Flex>
  );
}
