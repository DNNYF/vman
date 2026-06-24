import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Clipboard,
  Clock,
  Code2,
  Cpu,
  Globe2,
  RefreshCcw,
  ShieldAlert,
} from "lucide-react";
import {
  Box,
  Flex,
  Text,
  Heading,
  Button,
  Badge,
  Spinner,
  Icon,
  HStack,
  VStack,
  Grid,
  Textarea,
  Link,
} from "@chakra-ui/react";
import {
  describeVars,
  recipeRequiresApproval,
  type RecipeDetail,
} from "@/lib/recipes";
import { ApiError } from "@/lib/api";
import { getRecipe, RecipeApiError } from "@/lib/recipesApi";
import { listHosts, HostApiError } from "@/lib/hostsApi";
import { type Host } from "@/lib/hosts";
import { RecipeRunForm } from "@/components/recipes/RecipeRunForm";

// ─── Helpers ───────────────────────────────────────────────────────────────

function getRiskStyle(risk: string): { color: string; bg: string; border: string } {
  switch (risk) {
    case "critical": return { color: "#FF3131", bg: "rgba(255,49,49,0.1)",   border: "rgba(255,49,49,0.25)" };
    case "high":     return { color: "#F87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.25)" };
    case "medium":   return { color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)" };
    default:         return { color: "#39FF14", bg: "rgba(57,255,20,0.1)",   border: "rgba(57,255,20,0.25)" };
  }
}

function PhaseSummary({ recipe }: { recipe: RecipeDetail }) {
  const phases: { label: string; present: boolean }[] = [
    { label: "preflight", present: recipe.has_preflight },
    { label: "steps",     present: recipe.step_count > 0 },
    { label: "verify",    present: recipe.has_verify },
    { label: "rollback",  present: recipe.has_rollback },
  ];
  return (
    <HStack spacing={1} flexWrap="wrap">
      {phases.map((p) => (
        <Badge
          key={p.label}
          px={1.5}
          py={0.5}
          borderRadius="sm"
          fontSize="9px"
          fontFamily="mono"
          bg={p.present ? "rgba(0,240,255,0.08)" : "rgba(107,114,128,0.08)"}
          color={p.present ? "obsidian.cyan" : "obsidian.onSurfaceVariant"}
          border="1px solid"
          borderColor={p.present ? "rgba(0,240,255,0.2)" : "rgba(107,114,128,0.15)"}
          opacity={p.present ? 1 : 0.45}
          textDecoration={p.present ? "none" : "line-through"}
        >
          {p.label}
        </Badge>
      ))}
    </HStack>
  );
}

function describeSupportedOs(spec: RecipeDetail["supported_os"]): string {
  const families = spec.families ?? [];
  const names = spec.names ?? [];
  if (families.length === 0 && names.length === 0) {
    return "any";
  }
  return [...families, ...names].join(", ");
}

// ─── Main Component ────────────────────────────────────────────────────────

export function RecipeDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [yamlCopied, setYamlCopied] = useState(false);

  const refresh = async () => {
    if (!name) return;
    setLoading(true);
    setError(null);
    try {
      const [row, hostList] = await Promise.all([
        getRecipe(name),
        listHosts({ includeDisabled: false }),
      ]);
      setRecipe(row);
      setHosts(hostList);
    } catch (err) {
      if (err instanceof RecipeApiError) {
        setError(err.detail);
      } else if (err instanceof HostApiError) {
        setError(err.detail);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load recipe.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name]);

  const copyYaml = async () => {
    if (!recipe) return;
    try {
      await navigator.clipboard.writeText(recipe.yaml);
      setYamlCopied(true);
      window.setTimeout(() => setYamlCopied(false), 1500);
    } catch {
      // Clipboard access is best-effort; ignore the failure.
    }
  };

  if (loading) {
    return (
      <Flex direction="column" gap={6} p={6}>
        <Flex align="center" gap={3}>
          <Button
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            size="sm"
            onClick={() => navigate("/recipes")}
            leftIcon={<Icon as={ArrowLeft} w={4} h={4} />}
            _hover={{ bg: "rgba(255,255,255,0.05)" }}
          >
            Back to catalogue
          </Button>
        </Flex>
        <Flex align="center" justify="center" gap={3} py={20}>
          <Spinner color="obsidian.cyan" size="md" />
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            LOADING RECIPE...
          </Text>
        </Flex>
      </Flex>
    );
  }

  if (error || !recipe) {
    return (
      <Flex direction="column" gap={6} p={6}>
        <Flex align="center" gap={3}>
          <Button
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            size="sm"
            onClick={() => navigate("/recipes")}
            leftIcon={<Icon as={ArrowLeft} w={4} h={4} />}
            _hover={{ bg: "rgba(255,255,255,0.05)" }}
          >
            Back to catalogue
          </Button>
        </Flex>
        <Box
          p={5}
          borderRadius="md"
          bg="rgba(255,49,49,0.07)"
          border="1px solid"
          borderColor="rgba(255,49,49,0.2)"
        >
          <Heading size="xs" color="#FF3131" fontFamily="mono" letterSpacing="wider" mb={2}>
            ERROR: COULD NOT LOAD RECIPE
          </Heading>
          <Text fontSize="sm" color="gray.300">
            {error ?? "Recipe not found."}
          </Text>
        </Box>
      </Flex>
    );
  }

  const riskStyle = getRiskStyle(recipe.risk_level);
  const requiresApproval = recipeRequiresApproval(recipe.policy);

  return (
    <Flex direction="column" gap={6} p={6}>
      {/* Top Header */}
      <Flex wrap="wrap" align="center" justify="space-between" gap={3}>
        <HStack spacing={4} align="center">
          <Button
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            size="sm"
            onClick={() => navigate("/recipes")}
            leftIcon={<Icon as={ArrowLeft} w={4} h={4} />}
            _hover={{ bg: "rgba(255,255,255,0.05)" }}
          >
            Catalogue
          </Button>
          <Box>
            <Heading size="md" color="white" fontFamily="mono" fontWeight="bold">
              {recipe.name}
            </Heading>
            <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono" mt={1}>
              v{recipe.version} • {recipe.step_count} step{recipe.step_count === 1 ? "" : "s"}
            </Text>
          </Box>
        </HStack>

        <HStack spacing={2} flexWrap="wrap">
          <Badge
            px={2.5}
            py={1}
            borderRadius="md"
            fontSize="10px"
            fontFamily="mono"
            bg={riskStyle.bg}
            color={riskStyle.color}
            border="1px solid"
            borderColor={riskStyle.border}
          >
            {recipe.risk_level} risk
          </Badge>

          {requiresApproval ? (
            <Badge
              px={2.5}
              py={1}
              borderRadius="md"
              fontSize="10px"
              fontFamily="mono"
              bg="rgba(255,165,0,0.1)"
              color="orange.400"
              border="1px solid"
              borderColor="rgba(255,165,0,0.25)"
            >
              requires approval
            </Badge>
          ) : (
            <Badge
              px={2.5}
              py={1}
              borderRadius="md"
              fontSize="10px"
              fontFamily="mono"
              bg="rgba(255,255,255,0.03)"
              color="gray.400"
              border="1px solid"
              borderColor="obsidian.border"
            >
              no approval
            </Badge>
          )}

          <Button
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            size="sm"
            onClick={refresh}
            leftIcon={<Icon as={RefreshCcw} w={3.5} h={3.5} />}
            _hover={{ bg: "rgba(255,255,255,0.05)" }}
          >
            Refresh
          </Button>
        </HStack>
      </Flex>

      {/* Description */}
      {recipe.description ? (
        <Box
          p={4}
          borderRadius="md"
          bg="obsidian.surface"
          border="1px solid"
          borderColor="obsidian.border"
        >
          <Text fontSize="sm" color="gray.300">
            {recipe.description}
          </Text>
        </Box>
      ) : null}

      {/* Two Column Grid */}
      <Grid templateColumns={{ base: "1fr", lg: "1fr 2fr" }} gap={6} alignItems="start">
        {/* Left Column */}
        <VStack spacing={6} align="stretch">
          {/* Overview Card */}
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            overflow="hidden"
          >
            <Box bg="#0E0E10" px={5} py={3.5} borderBottom="1px solid" borderColor="obsidian.border">
              <HStack spacing={2}>
                <Icon as={BookOpen} color="obsidian.cyan" w={4} h={4} />
                <Text fontFamily="mono" fontSize="11px" fontWeight="bold" letterSpacing="wider" color="white" textTransform="uppercase">
                  Overview
                </Text>
              </HStack>
              <Text fontSize="11px" color="obsidian.onSurfaceVariant" mt={1}>
                Static metadata and the policy attached to this recipe.
              </Text>
            </Box>
            
            <Box p={5}>
              <Grid templateColumns="120px 1fr" gap={3} rowGap={4} alignItems="center">
                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Risk Level
                </Text>
                <Box>
                  <Badge
                    px={2}
                    py={0.5}
                    borderRadius="sm"
                    fontSize="9px"
                    fontFamily="mono"
                    bg={riskStyle.bg}
                    color={riskStyle.color}
                    border="1px solid"
                    borderColor={riskStyle.border}
                  >
                    {recipe.risk_level}
                  </Badge>
                </Box>

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Steps
                </Text>
                <Text fontSize="xs" fontFamily="mono" color="white">
                  {recipe.step_count}
                </Text>

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Phases
                </Text>
                <PhaseSummary recipe={recipe} />

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Variables
                </Text>
                <Text fontSize="11px" fontFamily="mono" color="white">
                  {describeVars(recipe.vars)}
                </Text>

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Source
                </Text>
                <Text fontSize="xs" fontFamily="mono" color="white" noOfLines={1}>
                  {recipe.source}
                </Text>

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Supported OS
                </Text>
                <HStack spacing={1}>
                  <Icon as={Globe2} color="obsidian.onSurfaceVariant" w={3.5} h={3.5} />
                  <Text fontSize="xs" fontFamily="mono" color="white">
                    {describeSupportedOs(recipe.supported_os)}
                  </Text>
                </HStack>

                <Text fontSize="10px" fontFamily="mono" fontWeight="bold" color="obsidian.onSurfaceVariant" letterSpacing="widest" textTransform="uppercase">
                  Policy
                </Text>
                <Box>
                  <HStack spacing={1} mb={1}>
                    <Icon as={ShieldAlert} color="obsidian.onSurfaceVariant" w={3.5} h={3.5} />
                    <Text fontSize="xs" color="gray.300">
                      requires approval: <strong>{requiresApproval ? "yes" : "no"}</strong>
                    </Text>
                  </HStack>
                  {(recipe.policy.forbidden_on_environments ?? []).length > 0 && (
                    <Text fontSize="10px" color="red.400" fontFamily="mono">
                      FORBIDDEN ON: {(recipe.policy.forbidden_on_environments ?? []).join(", ").toUpperCase()}
                    </Text>
                  )}
                </Box>
              </Grid>
            </Box>
          </Box>

          {/* Variables Card */}
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            overflow="hidden"
          >
            <Box bg="#0E0E10" px={5} py={3.5} borderBottom="1px solid" borderColor="obsidian.border">
              <HStack spacing={2}>
                <Icon as={Cpu} color="obsidian.cyan" w={4} h={4} />
                <Text fontFamily="mono" fontSize="11px" fontWeight="bold" letterSpacing="wider" color="white" textTransform="uppercase">
                  Schema Variables
                </Text>
              </HStack>
              <Text fontSize="11px" color="obsidian.onSurfaceVariant" mt={1}>
                The form schema details and requirements for this recipe.
              </Text>
            </Box>

            <Box p={5}>
              {Object.keys(recipe.vars).length === 0 ? (
                <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">
                  THIS RECIPE DECLARES NO VARIABLES.
                </Text>
              ) : (
                <VStack spacing={3} align="stretch">
                  {Object.entries(recipe.vars).map(([varName, spec]) => (
                    <Box
                      key={varName}
                      p={3}
                      bg="rgba(255,255,255,0.01)"
                      border="1px solid"
                      borderColor="obsidian.border"
                      borderRadius="md"
                    >
                      <Flex align="center" justify="space-between" mb={2}>
                        <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="obsidian.cyan">
                          {varName}
                        </Text>
                        <HStack spacing={1.5}>
                          <Badge
                            px={1.5}
                            py={0.2}
                            borderRadius="sm"
                            fontSize="8px"
                            fontFamily="mono"
                            bg="rgba(0,240,255,0.05)"
                            color="obsidian.cyan"
                            border="1px solid"
                            borderColor="rgba(0,240,255,0.15)"
                          >
                            {spec.type}
                          </Badge>
                          {spec.required ? (
                            <Badge
                              px={1.5}
                              py={0.2}
                              borderRadius="sm"
                              fontSize="8px"
                              fontFamily="mono"
                              bg="rgba(255,49,49,0.1)"
                              color="#F87171"
                              border="1px solid"
                              borderColor="rgba(255,49,49,0.2)"
                            >
                              required
                            </Badge>
                          ) : (
                            <Badge
                              px={1.5}
                              py={0.2}
                              borderRadius="sm"
                              fontSize="8px"
                              fontFamily="mono"
                              bg="rgba(255,255,255,0.02)"
                              color="gray.400"
                              border="1px solid"
                              borderColor="obsidian.border"
                            >
                              optional
                            </Badge>
                          )}
                        </HStack>
                      </Flex>

                      {spec.description && (
                        <Text fontSize="xs" color="gray.400" mb={1}>
                          {spec.description}
                        </Text>
                      )}

                      {spec.default !== null && spec.default !== undefined && (
                        <Text fontSize="10px" fontFamily="mono" color="obsidian.onSurfaceVariant">
                          DEFAULT: <Text as="code" color="white">{String(spec.default)}</Text>
                        </Text>
                      )}
                    </Box>
                  ))}
                </VStack>
              )}
            </Box>
          </Box>
        </VStack>

        {/* Right Column */}
        <VStack spacing={6} align="stretch">
          {/* Run Form */}
          <RecipeRunForm
            recipe={recipe}
            hosts={hosts}
            defaultHostId={hosts[0]?.id}
          />

          {/* Recipe Body Card */}
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            overflow="hidden"
          >
            <Box bg="#0E0E10" px={5} py={3.5} borderBottom="1px solid" borderColor="obsidian.border">
              <Flex align="center" justify="space-between">
                <HStack spacing={2}>
                  <Icon as={Code2} color="obsidian.cyan" w={4} h={4} />
                  <Text fontFamily="mono" fontSize="11px" fontWeight="bold" letterSpacing="wider" color="white" textTransform="uppercase">
                    Recipe YAML
                  </Text>
                </HStack>
                
                <Button
                  variant="outline"
                  borderColor="obsidian.border"
                  color="white"
                  size="xs"
                  onClick={copyYaml}
                  leftIcon={yamlCopied ? <Icon as={CheckCircle2} color="green.400" /> : <Icon as={Clipboard} />}
                  _hover={{ bg: "rgba(255,255,255,0.05)" }}
                >
                  {yamlCopied ? "COPIED" : "COPY"}
                </Button>
              </Flex>
              <Text fontSize="11px" color="obsidian.onSurfaceVariant" mt={1}>
                The raw configuration structure sent to the run endpoint.
              </Text>
            </Box>

            <Box p={5}>
              <Textarea
                readOnly
                value={recipe.yaml}
                fontFamily="mono"
                fontSize="11px"
                bg="#0A0A0C"
                color="gray.300"
                borderColor="obsidian.border"
                _focus={{ borderColor: "obsidian.cyan" }}
                minH="300px"
              />
              <HStack spacing={1.5} mt={3} color="obsidian.onSurfaceVariant">
                <Icon as={Clock} w={3.5} h={3.5} />
                <Text fontSize="10px" fontFamily="mono" letterSpacing="wide">
                  READ-ONLY — CUSTOMIZE BY RE-IMPORTING RECIPES ON SERVER FILEPATH.
                </Text>
              </HStack>
            </Box>
          </Box>

          {/* Gated Alert */}
          {requiresApproval && (
            <Box
              p={4}
              borderRadius="md"
              bg="rgba(245,158,11,0.06)"
              border="1px solid"
              borderColor="rgba(245,158,11,0.2)"
            >
              <HStack spacing={2} mb={1}>
                <Icon as={AlertTriangle} color="orange.400" w={4} h={4} />
                <Text fontSize="xs" fontFamily="mono" fontWeight="bold" color="orange.400">
                  GATED BY POLICY REQUIREMENT
                </Text>
              </HStack>
              <Text fontSize="xs" color="gray.300">
                This recipe needs positive authentication / manual approval by a secondary supervisor or admin account before execution.
              </Text>
            </Box>
          )}
        </VStack>
      </Grid>

      {/* Footer Meta */}
      <Flex wrap="wrap" justify="space-between" align="center" gap={3} pt={4} borderTop="1px solid" borderColor="obsidian.border">
        <HStack spacing={1.5} color="obsidian.onSurfaceVariant">
          <Icon as={ShieldAlert} w={3.5} h={3.5} />
          <Text fontSize="10px" fontFamily="mono" letterSpacing="wide">
            VERIFICATION COMPLIANT WITH THE OBSIDIAN PROTOCOL SECURITY FRAMEWORK.
          </Text>
        </HStack>
        <Link as={RouterLink} to="/recipes" fontSize="xs" color="obsidian.cyan" fontFamily="mono" _hover={{ textDecoration: "underline" }}>
          RETURN TO CATALOGUE
        </Link>
      </Flex>
    </Flex>
  );
}
