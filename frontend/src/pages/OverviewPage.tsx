import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Activity,
  Server,
  KeyRound,
  ShieldCheck,
  Plus,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";
import {
  Box,
  Flex,
  Text,
  Heading,
  Grid,
  GridItem,
  Badge,
  Button,
  VStack,
  HStack,
  Icon,
  Progress,
  Spinner,
} from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { ApiClient } from "@/lib/api";

const client = new ApiClient({ baseUrl: "" });

const pulseKeyframe = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(0, 240, 255, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(0, 240, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 240, 255, 0); }
`;

interface HealthStatus {
  status: string;
}

export function OverviewPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [hostsCount, setHostsCount] = useState<number>(0);
  const [jobsCount, setJobsCount] = useState<number>(0);
  const [auditCount, setAuditCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      try {
        const [healthRes, hostsRes, jobsRes, auditRes] = await Promise.all([
          client.get<HealthStatus>("/api/health").catch(() => null),
          client.get<any[]>("/api/hosts").catch(() => []),
          client.get<any[]>("/api/jobs").catch(() => []),
          client.get<any[]>("/api/audit").catch(() => []),
        ]);

        if (!cancelled) {
          setHealth(healthRes);
          setHostsCount(hostsRes.length);
          setJobsCount(jobsRes.filter((j) => j.status === "running").length);
          setAuditCount(auditRes.length);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadData();

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <Flex h="60vh" align="center" justify="center">
        <Spinner size="xl" color="obsidian.cyan" thickness="3px" />
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={8}>
      {/* Header and Title */}
      <Flex justify="space-between" align="end">
        <VStack align="start" spacing={1}>
          <Heading as="h1" size="lg" fontWeight="bold" color="white" letterSpacing="-0.02em">
            Fleet Summary
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            System initialized. Awaiting host connections.
          </Text>
        </VStack>
        <Button
          as={RouterLink}
          to="/hosts/new"
          bg="obsidian.cyan"
          color="black"
          fontSize="xs"
          fontFamily="mono"
          px={5}
          borderRadius="md"
          _hover={{ bg: "brand.200" }}
          leftIcon={<Icon as={Plus} size={14} />}
          boxShadow="inset 0 -2px 0 rgba(0,0,0,0.2)"
          _active={{ boxShadow: "inset 0 2px 0 rgba(0,0,0,0.2)" }}
        >
          Add Host
        </Button>
      </Flex>

      {/* Metric Cards Grid */}
      <Grid templateColumns={{ base: "1fr", md: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }} gap={6}>
        {/* Total Hosts */}
        <GridItem>
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            p={5}
            h="120px"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            position="relative"
            overflow="hidden"
            _hover={{ borderColor: "obsidian.cyan" }}
            transition="all 0.2s"
          >
            <Flex justify="space-between" align="start">
              <Text fontSize="10px" fontWeight="bold" color="obsidian.onSurfaceVariant" fontFamily="mono" letterSpacing="widest" textTransform="uppercase">
                Total Hosts
              </Text>
              <Icon as={Server} w={4} h={4} color="obsidian.onSurfaceVariant" />
            </Flex>
            <HStack spacing={2} align="baseline">
              <Text fontSize="3xl" fontWeight="bold" color="white" fontFamily="mono" lineHeight="none">
                {hostsCount}
              </Text>
              <Box w={2} h={2} borderRadius="full" bg="obsidian.onSurfaceVariant" />
            </HStack>
          </Box>
        </GridItem>

        {/* Active Jobs */}
        <GridItem>
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            p={5}
            h="120px"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            position="relative"
            overflow="hidden"
            _hover={{ borderColor: "obsidian.cyan" }}
            transition="all 0.2s"
          >
            <Flex justify="space-between" align="start">
              <Text fontSize="10px" fontWeight="bold" color="obsidian.onSurfaceVariant" fontFamily="mono" letterSpacing="widest" textTransform="uppercase">
                Active Jobs
              </Text>
              <Icon as={Activity} w={4} h={4} color="obsidian.onSurfaceVariant" />
            </Flex>
            <HStack spacing={2} align="baseline">
              <Text fontSize="3xl" fontWeight="bold" color="white" fontFamily="mono" lineHeight="none">
                {jobsCount}
              </Text>
              <Box
                w={2}
                h={2}
                borderRadius="full"
                bg="obsidian.cyan"
                animation={`${pulseKeyframe} 2s infinite`}
              />
            </HStack>
          </Box>
        </GridItem>

        {/* Vault Status */}
        <GridItem>
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            p={5}
            h="120px"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            position="relative"
            overflow="hidden"
            _hover={{ borderColor: "obsidian.cyan" }}
            transition="all 0.2s"
          >
            <Flex justify="space-between" align="start">
              <Text fontSize="10px" fontWeight="bold" color="obsidian.onSurfaceVariant" fontFamily="mono" letterSpacing="widest" textTransform="uppercase">
                Vault Status
              </Text>
              <Icon as={KeyRound} w={4} h={4} color="obsidian.cyan" />
            </Flex>
            <Box>
              <Badge
                variant="subtle"
                bg="rgba(57, 255, 20, 0.1)"
                color="obsidian.green"
                border="1px solid rgba(57, 255, 20, 0.2)"
                px={2.5}
                py={1}
                borderRadius="sm"
                fontSize="10px"
                fontFamily="mono"
              >
                AES-256-GCM SECURED
              </Badge>
            </Box>
          </Box>
        </GridItem>

        {/* Audit Events */}
        <GridItem>
          <Box
            bg="obsidian.surface"
            border="1px solid"
            borderColor="obsidian.border"
            borderRadius="md"
            p={5}
            h="120px"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            position="relative"
            overflow="hidden"
            _hover={{ borderColor: "obsidian.cyan" }}
            transition="all 0.2s"
          >
            <Flex justify="space-between" align="start">
              <Text fontSize="10px" fontWeight="bold" color="obsidian.onSurfaceVariant" fontFamily="mono" letterSpacing="widest" textTransform="uppercase">
                Audit Events
              </Text>
              <Icon as={ShieldCheck} w={4} h={4} color="obsidian.onSurfaceVariant" />
            </Flex>
            <HStack spacing={2} align="baseline">
              <Text fontSize="3xl" fontWeight="bold" color="white" fontFamily="mono" lineHeight="none">
                {auditCount}
              </Text>
              <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">
                events recorded
              </Text>
            </HStack>
          </Box>
        </GridItem>
      </Grid>

      {/* Main Bento Grid */}
      <Grid templateColumns={{ base: "1fr", lg: "repeat(12, 1fr)" }} gap={6}>
        {/* Workflow steps (Spans 8 cols) */}
        <GridItem colSpan={{ base: 1, lg: 8 }}>
          <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" overflow="hidden">
            <Flex bg="#161619" px={6} py={4} borderBottom="1px solid" borderColor="obsidian.border" justify="space-between" align="center">
              <HStack spacing={2}>
                <Icon as={Activity} color="obsidian.cyan" w={4} h={4} />
                <Text fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider" textTransform="uppercase" mb={0}>
                  Deployment Workflow
                </Text>
              </HStack>
              <Text fontSize="9px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                PHASE: INITIALIZATION
              </Text>
            </Flex>
            <Box p={6}>
              <Box position="relative">
                {/* Connecting vertical line */}
                <Box position="absolute" left="23px" top="10" bottom="10" w="1px" bg="obsidian.border" />

                {/* Step 1 */}
                <Flex gap={6} mb={8} position="relative">
                  <Flex
                    w="12"
                    h="12"
                    borderRadius="full"
                    bg="rgba(0, 240, 255, 0.1)"
                    border="1px solid rgba(0, 240, 255, 0.3)"
                    align="center"
                    justify="center"
                    shrink={0}
                    zIndex={1}
                    position="relative"
                  >
                    <Icon as={KeyRound} color="obsidian.cyan" />
                    <Box
                      position="absolute"
                      inset={0}
                      borderRadius="full"
                      border="1px solid"
                      borderColor="obsidian.cyan"
                      animation={`${pulseKeyframe} 2s infinite`}
                    />
                  </Flex>
                  <Box
                    flex="1"
                    bg="#0E0E10"
                    border="1px solid"
                    borderColor="obsidian.border"
                    borderRadius="md"
                    p={4}
                    _hover={{ borderColor: "obsidian.cyan" }}
                    transition="colors 0.2s"
                    cursor="pointer"
                  >
                    <Text fontSize="sm" fontWeight="bold" color="white" mb={1} fontFamily="heading">
                      Configure Master Key
                    </Text>
                    <Text fontSize="xs" color="obsidian.onSurfaceVariant" mb={3}>
                      Initialize the encrypted vault to secure credentials and automation secrets.
                    </Text>
                    <Flex
                      fontFamily="mono"
                      fontSize="10px"
                      bg="#0A0A0C"
                      border="1px solid"
                      borderColor="obsidian.border"
                      p={2}
                      borderRadius="sm"
                      justify="space-between"
                      align="center"
                      color="obsidian.onSurfaceVariant"
                    >
                      <Text as="code">vman vault init --key-type rsa4096</Text>
                      <Icon as={ExternalLink} cursor="pointer" _hover={{ color: "white" }} />
                    </Flex>
                  </Box>
                </Flex>

                {/* Step 2 */}
                <Flex gap={6} mb={8} position="relative">
                  <Flex
                    w="12"
                    h="12"
                    borderRadius="full"
                    bg="#1A1A1E"
                    border="1px solid"
                    borderColor="obsidian.border"
                    align="center"
                    justify="center"
                    shrink={0}
                    zIndex={1}
                  >
                    <Icon as={Server} color="obsidian.onSurfaceVariant" />
                  </Flex>
                  <Box
                    flex="1"
                    bg="#0A0A0C"
                    border="1px solid"
                    borderColor="obsidian.border"
                    borderRadius="md"
                    p={4}
                    opacity={0.6}
                  >
                    <Text fontSize="sm" fontWeight="bold" color="white" mb={1}>
                      Provision First Node
                    </Text>
                    <Text fontSize="xs" color="obsidian.onSurfaceVariant">
                      Add a target VPS with its credential to begin secure agentless orchestration.
                    </Text>
                  </Box>
                </Flex>

                {/* Step 3 */}
                <Flex gap={6} position="relative">
                  <Flex
                    w="12"
                    h="12"
                    borderRadius="full"
                    bg="#1A1A1E"
                    border="1px solid"
                    borderColor="obsidian.border"
                    align="center"
                    justify="center"
                    shrink={0}
                    zIndex={1}
                  >
                    <Icon as={ShieldCheck} color="obsidian.onSurfaceVariant" />
                  </Flex>
                  <Box
                    flex="1"
                    bg="#0A0A0C"
                    border="1px solid"
                    borderColor="obsidian.border"
                    borderRadius="md"
                    p={4}
                    opacity={0.6}
                  >
                    <Text fontSize="sm" fontWeight="bold" color="white" mb={1}>
                      Apply Base Topology
                    </Text>
                    <Text fontSize="xs" color="obsidian.onSurfaceVariant">
                      Execute the default healthcheck or security recipes across your connected fleet.
                    </Text>
                  </Box>
                </Flex>
              </Box>
            </Box>
          </Box>
        </GridItem>

        {/* Health status and quick action (Spans 4 cols) */}
        <GridItem colSpan={{ base: 1, lg: 4 }}>
          <Flex direction="column" gap={6} h="100%">
            <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" p={4} flex="1">
              <Text fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider" textTransform="uppercase" mb={4}>
                Control Plane Health
              </Text>
              <VStack align="stretch" spacing={3}>
                <Flex justify="space-between" align="center">
                  <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">API Server</Text>
                  <Badge variant="subtle" bg={health ? "rgba(57, 255, 20, 0.1)" : "rgba(255, 49, 49, 0.1)"} color={health ? "obsidian.green" : "obsidian.red"} border="1px solid" borderColor={health ? "rgba(57, 255, 20, 0.2)" : "rgba(255, 49, 49, 0.2)"} borderRadius="sm" fontSize="9px" px={2}>
                    {health ? "ONLINE" : "OFFLINE"}
                  </Badge>
                </Flex>
                <Flex justify="space-between" align="center">
                  <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">Scheduler</Text>
                  <Badge variant="subtle" bg="rgba(57, 255, 20, 0.1)" color="obsidian.green" border="1px solid rgba(57, 255, 20, 0.2)" borderRadius="sm" fontSize="9px" px={2}>
                    ACTIVE
                  </Badge>
                </Flex>
                <Flex justify="space-between" align="center">
                  <Text fontSize="xs" color="obsidian.onSurfaceVariant" fontFamily="mono">Vault Engine</Text>
                  <Badge variant="subtle" bg="rgba(0, 240, 255, 0.1)" color="obsidian.cyan" border="1px solid rgba(0, 240, 255, 0.2)" borderRadius="sm" fontSize="9px" px={2}>
                    UNSEALED
                  </Badge>
                </Flex>

                <Box mt={4} pt={4} borderTop="1px solid" borderColor="obsidian.border">
                  <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono" mb={1}>
                    System API load (connected sessions)
                  </Text>
                  <Progress value={25} size="xs" colorScheme="cyan" bg="#0A0A0C" borderRadius="sm" />
                </Box>
              </VStack>
            </Box>

            <Box bg="obsidian.surface" border="1px solid" borderColor="obsidian.border" borderRadius="md" p={4}>
              <HStack spacing={2} mb={2}>
                <Icon as={AlertTriangle} color="obsidian.cyan" />
                <Text fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" letterSpacing="wider">
                  Quick Action
                </Text>
              </HStack>
              <Text fontSize="xs" color="obsidian.onSurfaceVariant" mb={4}>
                Vault is currently unsealed. Automation jobs and SSH keys can be fully initialized.
              </Text>
              <Button
                w="full"
                variant="outline"
                borderColor="obsidian.border"
                color="white"
                fontFamily="mono"
                fontSize="xs"
                h="36px"
                borderRadius="md"
                _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
                bg="#1A1A1E"
              >
                Seal Vault
              </Button>
            </Box>
          </Flex>
        </GridItem>
      </Grid>
    </Flex>
  );
}
