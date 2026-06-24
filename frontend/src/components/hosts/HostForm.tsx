import { useEffect, useState } from "react";
import {
  Box,
  Flex,
  Text,
  Button,
  Input,
  Textarea,
  Select,
  FormControl,
  FormLabel,
  FormHelperText,
  SimpleGrid,
  HStack,
  Icon,
  Badge,
} from "@chakra-ui/react";
import { AlertTriangle } from "lucide-react";
import {
  AUTH_METHODS,
  SUDO_MODES,
  ENVIRONMENTS,
  type AuthMethod,
  type Environment,
  type Host,
  type HostCreatePayload,
  type SudoMode,
} from "@/lib/hosts";
import { listCredentials } from "@/lib/credentialsApi";

// ─── Types ────────────────────────────────────────────────────────────────

export interface HostFormValues {
  name: string;
  hostname_or_ip: string;
  ssh_port: number;
  username: string;
  auth_method: AuthMethod;
  credential_id: string;
  sudo_mode: SudoMode;
  environment: Environment;
  provider: string;
  region: string;
  tags: string;
  notes: string;
}

export interface HostFormProps {
  initial?: Host | null;
  submitLabel: string;
  busy?: boolean;
  errorMessage?: string | null;
  onSubmit: (payload: HostCreatePayload) => void;
  onCancel?: () => void;
}

const DEFAULTS: HostFormValues = {
  name: "",
  hostname_or_ip: "",
  ssh_port: 22,
  username: "root",
  auth_method: "key",
  credential_id: "",
  sudo_mode: "root",
  environment: "experiment",
  provider: "",
  region: "",
  tags: "",
  notes: "",
};

function fromHost(host: Host | null | undefined): HostFormValues {
  if (!host) return { ...DEFAULTS };
  return {
    name: host.name,
    hostname_or_ip: host.hostname_or_ip,
    ssh_port: host.ssh_port,
    username: host.username,
    auth_method: host.auth_method,
    credential_id: host.credential_id ?? "",
    sudo_mode: host.sudo_mode,
    environment: host.environment,
    provider: host.provider ?? "",
    region: host.region ?? "",
    tags: host.tags.join(", "),
    notes: host.notes ?? "",
  };
}

function parseTags(raw: string): string[] {
  return raw.split(",").map((t) => t.trim()).filter((t) => t.length > 0);
}

function validate(values: HostFormValues): string | null {
  if (!values.name.trim()) return "Name is required.";
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(values.name.trim()))
    return "Name must start with a letter or digit, then [a-zA-Z0-9_.-], max 64 chars.";
  if (!values.hostname_or_ip.trim()) return "Hostname or IP is required.";
  if (values.ssh_port < 1 || values.ssh_port > 65535 || !Number.isInteger(values.ssh_port))
    return "SSH port must be an integer between 1 and 65535.";
  if (!values.username.trim()) return "SSH username is required.";
  if (!values.credential_id.trim())
    return "A credential reference is required. Add one in the vault first.";
  return null;
}

// ─── Field styles ────────────────────────────────────────────────────────

const inputStyle = {
  bg: "#0A0A0C",
  border: "1px solid",
  borderColor: "obsidian.border",
  color: "white",
  fontSize: "sm",
  fontFamily: "mono",
  h: "36px",
  borderRadius: "md",
  _placeholder: { color: "obsidian.onSurfaceVariant" },
  _focus: { borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" },
  _hover: { borderColor: "rgba(255,255,255,0.2)" },
};

const selectStyle = {
  bg: "#0A0A0C",
  border: "1px solid",
  borderColor: "obsidian.border",
  color: "white",
  fontSize: "sm",
  fontFamily: "mono",
  h: "36px",
  borderRadius: "md",
  _focus: { borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px rgba(0,240,255,0.3)" },
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

const helperStyle = {
  fontSize: "11px",
  color: "obsidian.onSurfaceVariant",
  mt: 1.5,
  fontFamily: "mono",
};

// ─── Section divider ────────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Flex align="center" gap={3} mb={4}>
        <Text fontSize="10px" fontWeight="bold" color="obsidian.cyan" fontFamily="mono"
          letterSpacing="widest" textTransform="uppercase">
          {label}
        </Text>
        <Box flex={1} h="1px" bg="obsidian.border" />
      </Flex>
      {children}
    </Box>
  );
}

// ─── Main component ────────────────────────────────────────────────────────

export function HostForm({ initial, submitLabel, busy = false, errorMessage, onSubmit, onCancel }: HostFormProps) {
  const [values, setValues] = useState<HostFormValues>(() => fromHost(initial));
  const [credsList, setCredsList] = useState<{ value: string; label: string }[]>([]);
  const [touched, setTouched] = useState(false);

  useEffect(() => { setValues(fromHost(initial)); }, [initial]);

  useEffect(() => {
    listCredentials()
      .then((data) => setCredsList(data.map((c) => ({ value: c.id, label: `${c.name} (${c.kind.replace(/_/g, " ")})` }))))
      .catch(() => {});
  }, []);

  const update = <K extends keyof HostFormValues>(key: K, value: HostFormValues[K]) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setTouched(true);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const err = validate(values);
    if (err) return;
    const payload: HostCreatePayload = {
      name: values.name.trim(),
      hostname_or_ip: values.hostname_or_ip.trim(),
      ssh_port: values.ssh_port,
      username: values.username.trim(),
      auth_method: values.auth_method,
      credential_id: values.credential_id.trim(),
      sudo_mode: values.sudo_mode,
      environment: values.environment,
      provider: values.provider.trim() || null,
      region: values.region.trim() || null,
      tags: parseTags(values.tags),
      notes: values.notes,
    };
    onSubmit(payload);
  };

  const validationError = validate(values);
  const showInlineError = touched && validationError;

  return (
    <Box as="form" onSubmit={handleSubmit} display="flex" flexDirection="column" gap={8}>
      {/* API error */}
      {errorMessage && (
        <Box bg="rgba(239,68,68,0.08)" border="1px solid rgba(239,68,68,0.25)" borderRadius="md" p={3}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F87171" w={4} h={4} />
            <Text fontSize="xs" color="#F87171" fontFamily="mono">{errorMessage}</Text>
          </HStack>
        </Box>
      )}

      {/* Inline validation hint */}
      {showInlineError && (
        <Box bg="rgba(245,158,11,0.08)" border="1px solid rgba(245,158,11,0.2)" borderRadius="md" p={3}>
          <HStack spacing={2}>
            <Icon as={AlertTriangle} color="#F59E0B" w={3.5} h={3.5} />
            <Text fontSize="xs" color="#F59E0B" fontFamily="mono">{validationError}</Text>
          </HStack>
        </Box>
      )}

      {/* ── IDENTITY ── */}
      <Section label="Identity">
        <SimpleGrid columns={{ base: 1, md: 2 }} gap={5}>
          <FormControl isRequired>
            <FormLabel sx={labelStyle}>Name</FormLabel>
            <Input
              id="host-name"
              value={values.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="sg-1gb-01"
              autoComplete="off"
              sx={inputStyle}
            />
            <FormHelperText sx={helperStyle}>
              Short label. Letters, digits, dot, dash, underscore.
            </FormHelperText>
          </FormControl>

          <FormControl isRequired>
            <FormLabel sx={labelStyle}>Environment</FormLabel>
            <Select
              id="host-env"
              value={values.environment}
              onChange={(e) => update("environment", e.target.value as Environment)}
              sx={selectStyle}
            >
              {ENVIRONMENTS.map((e) => (
                <option key={e.value} value={e.value} style={{ background: "#0A0A0C" }}>
                  {e.label}
                </option>
              ))}
            </Select>
            <FormHelperText sx={helperStyle}>
              Production hosts require extra confirmation on risky jobs.
            </FormHelperText>
          </FormControl>
        </SimpleGrid>
      </Section>

      {/* ── CONNECTION ── */}
      <Section label="Connection">
        <SimpleGrid columns={{ base: 1, md: 2 }} gap={5}>
          <FormControl isRequired>
            <FormLabel sx={labelStyle}>Hostname or IP</FormLabel>
            <Input
              id="host-host"
              value={values.hostname_or_ip}
              onChange={(e) => update("hostname_or_ip", e.target.value)}
              placeholder="10.0.0.1 or vps.example.com"
              autoComplete="off"
              sx={inputStyle}
            />
          </FormControl>

          <FormControl isRequired>
            <FormLabel sx={labelStyle}>SSH Port</FormLabel>
            <Input
              id="host-port"
              type="number"
              min={1}
              max={65535}
              value={values.ssh_port}
              onChange={(e) => update("ssh_port", Number(e.target.value) || 0)}
              sx={inputStyle}
            />
          </FormControl>

          <FormControl isRequired>
            <FormLabel sx={labelStyle}>SSH Username</FormLabel>
            <Input
              id="host-user"
              value={values.username}
              onChange={(e) => update("username", e.target.value)}
              placeholder="root or ubuntu"
              autoComplete="off"
              sx={inputStyle}
            />
          </FormControl>

          <FormControl isRequired>
            <FormLabel sx={labelStyle}>Auth Method</FormLabel>
            <Select
              id="host-auth"
              value={values.auth_method}
              onChange={(e) => update("auth_method", e.target.value as AuthMethod)}
              sx={selectStyle}
            >
              {AUTH_METHODS.map((m) => (
                <option key={m.value} value={m.value} style={{ background: "#0A0A0C" }}>
                  {m.label}
                </option>
              ))}
            </Select>
            <FormHelperText sx={helperStyle}>
              {AUTH_METHODS.find((m) => m.value === values.auth_method)?.hint}
            </FormHelperText>
          </FormControl>
        </SimpleGrid>
      </Section>

      {/* ── CREDENTIALS ── */}
      <Section label="Security">
        <SimpleGrid columns={{ base: 1, md: 2 }} gap={5}>
          <FormControl isRequired>
            <FormLabel sx={labelStyle}>Credential Reference</FormLabel>
            <Select
              id="host-credential"
              value={values.credential_id}
              onChange={(e) => update("credential_id", e.target.value)}
              sx={selectStyle}
            >
              <option value="" style={{ background: "#0A0A0C" }}>Select a credential…</option>
              {credsList.map((c) => (
                <option key={c.value} value={c.value} style={{ background: "#0A0A0C" }}>
                  {c.label}
                </option>
              ))}
            </Select>
            <FormHelperText sx={helperStyle}>
              Choose an encrypted credential from the vault.{" "}
              <Box as="a" href="/credentials" target="_blank" rel="noopener noreferrer"
                color="obsidian.cyan" _hover={{ textDecoration: "underline" }}>
                Create one here →
              </Box>
            </FormHelperText>
          </FormControl>

          <FormControl>
            <FormLabel sx={labelStyle}>Sudo Mode</FormLabel>
            <Select
              id="host-sudo"
              value={values.sudo_mode}
              onChange={(e) => update("sudo_mode", e.target.value as SudoMode)}
              sx={selectStyle}
            >
              {SUDO_MODES.map((m) => (
                <option key={m.value} value={m.value} style={{ background: "#0A0A0C" }}>
                  {m.label}
                </option>
              ))}
            </Select>
            <FormHelperText sx={helperStyle}>
              {SUDO_MODES.find((m) => m.value === values.sudo_mode)?.hint}
            </FormHelperText>
          </FormControl>
        </SimpleGrid>
      </Section>

      {/* ── METADATA ── */}
      <Section label="Metadata">
        <SimpleGrid columns={{ base: 1, md: 2 }} gap={5}>
          <FormControl>
            <FormLabel sx={labelStyle}>Provider (optional)</FormLabel>
            <Input
              id="host-provider"
              value={values.provider}
              onChange={(e) => update("provider", e.target.value)}
              placeholder="Contabo, Vultr, DO, …"
              autoComplete="off"
              sx={inputStyle}
            />
          </FormControl>

          <FormControl>
            <FormLabel sx={labelStyle}>Region (optional)</FormLabel>
            <Input
              id="host-region"
              value={values.region}
              onChange={(e) => update("region", e.target.value)}
              placeholder="sg-1, fra-1, nyc-3, …"
              autoComplete="off"
              sx={inputStyle}
            />
          </FormControl>

          <FormControl gridColumn={{ md: "span 2" }}>
            <FormLabel sx={labelStyle}>Tags</FormLabel>
            <Input
              id="host-tags"
              value={values.tags}
              onChange={(e) => update("tags", e.target.value)}
              placeholder="singapore, 1gb, experiment"
              autoComplete="off"
              sx={inputStyle}
            />
            <FormHelperText sx={helperStyle}>
              Comma separated. Used for filtering and bulk actions.
            </FormHelperText>
            {/* Tag preview */}
            {values.tags && (
              <Flex mt={2} gap={1.5} flexWrap="wrap">
                {parseTags(values.tags).map((tag) => (
                  <Badge key={tag} px={2} py={0.5} borderRadius="sm" fontSize="10px" fontFamily="mono"
                    bg="rgba(0,240,255,0.08)" color="obsidian.cyan"
                    border="1px solid rgba(0,240,255,0.2)">
                    {tag}
                  </Badge>
                ))}
              </Flex>
            )}
          </FormControl>

          <FormControl gridColumn={{ md: "span 2" }}>
            <FormLabel sx={labelStyle}>Notes</FormLabel>
            <Textarea
              id="host-notes"
              value={values.notes}
              onChange={(e) => update("notes", e.target.value)}
              placeholder="Anything the next operator should know about this box."
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
              _hover={{ borderColor: "rgba(255,255,255,0.2)" }}
            />
            <FormHelperText sx={helperStyle}>
              Free-form. Secrets are redacted in the audit log.
            </FormHelperText>
          </FormControl>
        </SimpleGrid>
      </Section>

      {/* ── Actions ── */}
      <Flex justify="flex-end" gap={3} pt={2} borderTop="1px solid" borderColor="obsidian.border">
        {onCancel && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            borderColor="obsidian.border"
            color="obsidian.onSurfaceVariant"
            fontFamily="mono"
            fontSize="xs"
            h="36px"
            px={6}
            _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            onClick={onCancel}
            isDisabled={busy}
          >
            Cancel
          </Button>
        )}
        <Button
          type="submit"
          size="sm"
          bg="obsidian.cyan"
          color="black"
          fontFamily="mono"
          fontSize="xs"
          fontWeight="bold"
          h="36px"
          px={6}
          borderRadius="md"
          _hover={{ bg: "cyan.300" }}
          _active={{ transform: "scale(0.97)" }}
          isLoading={busy}
          isDisabled={busy || validationError !== null}
        >
          {submitLabel}
        </Button>
      </Flex>
    </Box>
  );
}
