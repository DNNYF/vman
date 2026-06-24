import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Play,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import {
  Box,
  Flex,
  Text,
  Button,
  Input,
  Select,
  Badge,
  Icon,
  HStack,
  VStack,
  FormControl,
  FormLabel,
  Checkbox,
  Spinner,
} from "@chakra-ui/react";
import {
  defaultVarValue,
  describeVars,
  emptyRecipeRunForm,
  recipeRequiresApproval,
  type RecipeDetail,
  type RecipeRunFormValues,
  type RecipeVarSpec,
} from "@/lib/recipes";
import { type Host } from "@/lib/hosts";
import { ApiError } from "@/lib/api";
import { buildRunPayload, RecipeApiError, runRecipe } from "@/lib/recipesApi";

// ─── Field Styles ──────────────────────────────────────────────────────────

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

export interface RecipeRunFormProps {
  recipe: RecipeDetail;
  hosts: Host[];
  defaultHostId?: string;
}

/**
 * The run-recipe form.  Reads the recipe's ``vars`` schema and
 * generates one input per variable.  Surfaces policy warnings
 * (forbidden environments, requires_approval) and refuses to
 * submit until the user has acknowledged the approval prompt.
 */
export function RecipeRunForm({
  recipe,
  hosts,
  defaultHostId,
}: RecipeRunFormProps) {
  const navigate = useNavigate();
  const initialHost = defaultHostId ?? hosts[0]?.id ?? "";
  const initialVars = useMemo<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const [name, spec] of Object.entries(recipe.vars)) {
      out[name] = defaultVarValue(spec);
    }
    return out;
  }, [recipe.vars]);

  const [form, setForm] = useState<RecipeRunFormValues>(() => ({
    ...emptyRecipeRunForm(initialHost),
    vars: initialVars,
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep form.vars in sync if the recipe changes
  useEffect(() => {
    setForm((prev) => ({
      ...prev,
      vars: { ...prev.vars, ...initialVars },
    }));
  }, [initialVars]);

  const host = hosts.find((h) => h.id === form.host_id);
  const requiresApproval = recipeRequiresApproval(recipe.policy);
  const forbiddenEnvs = recipe.policy.forbidden_on_environments ?? [];
  const forbiddenForHost =
    host && forbiddenEnvs.length > 0
      ? forbiddenEnvs.includes(host.environment)
      : false;

  const missingRequired = useMemo(() => {
    const missing: string[] = [];
    for (const [name, spec] of Object.entries(recipe.vars)) {
      if (!spec.required) continue;
      const raw = form.vars[name] ?? "";
      if (raw.trim() === "") missing.push(name);
    }
    return missing;
  }, [recipe.vars, form.vars]);

  const hostOptions = hosts.map((h) => ({
    value: h.id,
    label: h.disabled_at
      ? `${h.name} — ${h.hostname_or_ip} (disabled)`
      : `${h.name} — ${h.hostname_or_ip}`,
    disabled: Boolean(h.disabled_at),
  }));

  const canSubmit =
    !submitting &&
    hosts.length > 0 &&
    form.host_id !== "" &&
    missingRequired.length === 0 &&
    (!requiresApproval || form.acknowledged_approval) &&
    !forbiddenForHost;

  const updateVar = (name: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      vars: { ...prev.vars, [name]: value },
    }));
  };

  const updateField = <K extends keyof RecipeRunFormValues>(
    name: K,
    value: RecipeRunFormValues[K],
  ) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload = buildRunPayload(form, recipe);
      const result = await runRecipe(payload);
      navigate(`/jobs/${result.job_id}`);
    } catch (err) {
      if (err instanceof RecipeApiError) {
        setError(err.detail);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to start recipe run.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      bg="obsidian.surface"
      border="1px solid"
      borderColor="obsidian.border"
      borderRadius="md"
      overflow="hidden"
      as="form"
      onSubmit={handleSubmit}
    >
      <Box bg="#0E0E10" px={5} py={3.5} borderBottom="1px solid" borderColor="obsidian.border">
        <HStack spacing={2}>
          <Icon as={Wrench} color="obsidian.cyan" w={4} h={4} />
          <Text fontFamily="mono" fontSize="11px" fontWeight="bold" letterSpacing="wider" color="white" textTransform="uppercase">
            Run {recipe.name}
          </Text>
        </HStack>
        <Text fontSize="11px" color="obsidian.onSurfaceVariant" mt={1}>
          Submit this recipe against one of your hosts. All command output is audited.
        </Text>
      </Box>

      <VStack spacing={4} align="stretch" p={5}>
        {error && (
          <Box bg="rgba(255,49,49,0.08)" border="1px solid rgba(255,49,49,0.2)" borderRadius="md" p={3}>
            <HStack spacing={2} mb={1}>
              <Icon as={AlertTriangle} color="#FF3131" w={4} h={4} />
              <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="#FF3131">
                COULD NOT START THE RECIPE
              </Text>
            </HStack>
            <Text fontSize="xs" color="gray.300">
              {error}
            </Text>
          </Box>
        )}

        {hosts.length === 0 && (
          <Box bg="rgba(245,158,11,0.08)" border="1px solid rgba(245,158,11,0.2)" borderRadius="md" p={3}>
            <HStack spacing={2} mb={1}>
              <Icon as={AlertTriangle} color="#F59E0B" w={4} h={4} />
              <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="#F59E0B">
                NO HOSTS AVAILABLE
              </Text>
            </HStack>
            <Text fontSize="xs" color="gray.300">
              Add at least one host before you can run a recipe. The inventory lives under the Hosts tab.
            </Text>
          </Box>
        )}

        {forbiddenForHost && host && (
          <Box bg="rgba(255,49,49,0.08)" border="1px solid rgba(255,49,49,0.2)" borderRadius="md" p={3}>
            <HStack spacing={2} mb={1}>
              <Icon as={AlertTriangle} color="#FF3131" w={4} h={4} />
              <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="#FF3131">
                RECIPE FORBIDDEN ON {host.environment.toUpperCase()}
              </Text>
            </HStack>
            <Text fontSize="xs" color="gray.300">
              The recipe policy blocks running on {forbiddenEnvs.join(", ")} environments. Pick a different host to continue.
            </Text>
          </Box>
        )}

        <PolicyWarning
          recipe={recipe}
          hostEnvironment={host?.environment ?? null}
          requiresApproval={requiresApproval}
          forbiddenEnvs={forbiddenEnvs}
        />

        {/* Host Selection */}
        <FormControl isRequired>
          <FormLabel sx={labelStyle}>Host</FormLabel>
          <Select
            id="recipe-host"
            value={form.host_id}
            onChange={(e) => updateField("host_id", e.target.value)}
            placeholder={hostOptions.length === 0 ? "No hosts available" : "Select target host..."}
            sx={selectStyle}
          >
            {hostOptions.map((opt) => (
              <option
                key={opt.value}
                value={opt.value}
                disabled={opt.disabled}
                style={{ background: "#0A0A0C", color: opt.disabled ? "#6b7280" : "white" }}
              >
                {opt.label}
              </option>
            ))}
          </Select>
          {host && (
            <Text fontSize="10px" fontFamily="mono" color="obsidian.onSurfaceVariant" mt={1.5}>
              ENVIRONMENT: <Text as="span" color="white">{host.environment.toUpperCase()}</Text>
            </Text>
          )}
        </FormControl>

        {/* Timeout input */}
        <FormControl isRequired>
          <FormLabel sx={labelStyle}>Timeout (seconds)</FormLabel>
          <Input
            id="recipe-timeout"
            type="number"
            min={1}
            max={86400}
            value={String(form.timeout_seconds)}
            onChange={(e) => {
              const next = Number(e.target.value);
              updateField(
                "timeout_seconds",
                Number.isFinite(next) && next > 0 ? Math.trunc(next) : 1,
              );
            }}
            sx={inputStyle}
          />
        </FormControl>

        {/* Variables Inputs Section */}
        {Object.keys(recipe.vars).length > 0 && (
          <Box
            p={4}
            borderRadius="md"
            border="1px dashed"
            borderColor="obsidian.border"
            bg="rgba(255,255,255,0.005)"
          >
            <Flex align="center" justify="between" mb={4}>
              <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="white" letterSpacing="wide">
                RECIPE VARIABLES
              </Text>
              <Text fontSize="10px" fontFamily="mono" color="obsidian.onSurfaceVariant">
                {describeVars(recipe.vars)}
              </Text>
            </Flex>

            <VStack spacing={4} align="stretch">
              {Object.entries(recipe.vars).map(([name, spec]) => (
                <VarInput
                  key={name}
                  name={name}
                  spec={spec}
                  value={form.vars[name] ?? ""}
                  onChange={(val) => updateVar(name, val)}
                />
              ))}
            </VStack>
          </Box>
        )}

        {missingRequired.length > 0 && (
          <Box bg="rgba(255,49,49,0.08)" border="1px solid rgba(255,49,49,0.2)" borderRadius="md" p={3}>
            <HStack spacing={2} mb={1}>
              <Icon as={AlertTriangle} color="#FF3131" w={4} h={4} />
              <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="#FF3131">
                MISSING REQUIRED VARIABLES
              </Text>
            </HStack>
            <Text fontSize="xs" color="gray.300">
              Please fill in the following values to execute: {missingRequired.join(", ")}.
            </Text>
          </Box>
        )}

        {/* Acknowledge Approval Checkbox */}
        {requiresApproval && (
          <Box
            p={3}
            borderRadius="md"
            bg="rgba(245,158,11,0.05)"
            border="1px solid"
            borderColor="rgba(245,158,11,0.2)"
          >
            <Checkbox
              colorScheme="yellow"
              isChecked={form.acknowledged_approval}
              onChange={(e) => updateField("acknowledged_approval", e.target.checked)}
              alignItems="flex-start"
            >
              <Text fontSize="xs" color="gray.300" mt="-1px" ml={1}>
                <Icon as={ShieldAlert} color="orange.400" w={3.5} h={3.5} mr={1} verticalAlign="middle" />
                This recipe requires secondary authorization. The run will sit in the queue until approved. I acknowledge and submit for review.
              </Text>
            </Checkbox>
          </Box>
        )}

        {/* Actions */}
        <Flex justify="end" gap={2} pt={2}>
          <Button
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            onClick={() => navigate(-1)}
            disabled={submitting}
            _hover={{ bg: "rgba(255,255,255,0.05)" }}
            fontFamily="mono"
            fontSize="xs"
            size="sm"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!canSubmit}
            bg="obsidian.cyan"
            color="black"
            _hover={{ bg: "#00D8E6" }}
            _disabled={{ bg: "rgba(0,240,255,0.15)", color: "rgba(0,0,0,0.5)", cursor: "not-allowed" }}
            leftIcon={submitting ? <Spinner size="xs" /> : <Icon as={Play} />}
            fontFamily="mono"
            fontSize="xs"
            size="sm"
          >
            {submitting ? "Starting…" : "Run recipe"}
          </Button>
        </Flex>
      </VStack>
    </Box>
  );
}

interface VarInputProps {
  name: string;
  spec: RecipeVarSpec;
  value: string;
  onChange: (value: string) => void;
}

function VarInput({ name, spec, value, onChange }: VarInputProps) {
  const labelId = `var-${name}-label`;
  const helpId = `var-${name}-help`;
  const required = spec.required;

  return (
    <FormControl isRequired={required}>
      <Flex align="center" gap={2} mb={1.5}>
        <FormLabel id={labelId} htmlFor={`var-${name}`} sx={labelStyle} m={0}>
          {name}
        </FormLabel>
        <Badge
          px={1.5}
          borderRadius="sm"
          fontSize="8px"
          fontFamily="mono"
          bg="rgba(255,255,255,0.02)"
          color="gray.400"
          border="1px solid"
          borderColor="obsidian.border"
        >
          {spec.type}
        </Badge>
        {required && (
          <Badge
            px={1.5}
            borderRadius="sm"
            fontSize="8px"
            fontFamily="mono"
            bg="rgba(255,49,49,0.08)"
            color="#F87171"
            border="1px solid"
            borderColor="rgba(255,49,49,0.15)"
          >
            required
          </Badge>
        )}
      </Flex>

      {spec.type === "bool" ? (
        <Select
          id={`var-${name}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          sx={selectStyle}
        >
          <option value="true" style={{ background: "#0A0A0C" }}>true</option>
          <option value="false" style={{ background: "#0A0A0C" }}>false</option>
        </Select>
      ) : (
        <Input
          id={`var-${name}`}
          type={spec.type === "int" || spec.type === "number" ? "number" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={spec.description ? helpId : undefined}
          sx={inputStyle}
        />
      )}

      {spec.description && (
        <Text id={helpId} fontSize="11px" color="obsidian.onSurfaceVariant" mt={1.5}>
          {spec.description}
        </Text>
      )}
    </FormControl>
  );
}

interface PolicyWarningProps {
  recipe: RecipeDetail;
  hostEnvironment: string | null | undefined;
  requiresApproval: boolean;
  forbiddenEnvs: string[];
}

function PolicyWarning({
  recipe,
  hostEnvironment,
  requiresApproval,
  forbiddenEnvs,
}: PolicyWarningProps) {
  if (!requiresApproval && forbiddenEnvs.length === 0) {
    return null;
  }
  return (
    <Box
      p={3}
      borderRadius="md"
      bg="rgba(245,158,11,0.05)"
      border="1px solid"
      borderColor="rgba(245,158,11,0.2)"
    >
      <HStack spacing={2} align="start">
        <Icon as={AlertTriangle} color="orange.400" w={4} h={4} mt={0.5} />
        <VStack align="stretch" spacing={1}>
          <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="orange.400">
            POLICY ADVISORY
          </Text>
          {requiresApproval && (
            <Text fontSize="xs" color="gray.300">
              Recipe <strong>{recipe.name}</strong> is subject to secondary authentication before deployment.
            </Text>
          )}
          {forbiddenEnvs.length > 0 && (
            <Text fontSize="xs" color="gray.300">
              Forbidden on: {forbiddenEnvs.join(", ").toUpperCase()}.
              {hostEnvironment && ` Target host environment is ${hostEnvironment.toUpperCase()}.`}
            </Text>
          )}
        </VStack>
      </HStack>
    </Box>
  );
}
