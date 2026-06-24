import { useEffect, useState } from "react";
import {
  Box,
  Flex,
  Heading,
  Text,
  Input,
  InputGroup,
  InputLeftElement,
  Button,
  VStack,
  HStack,
  Icon,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Collapse,
  Badge,
  Spinner,
  Grid,
  GridItem,
} from "@chakra-ui/react";
import { Shield, Search, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { ApiClient } from "@/lib/api";

const client = new ApiClient({ baseUrl: "" });

interface AuditEvent {
  id: string;
  actor_user_id: string | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, any>;
  created_at: string;
}

export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [actionPrefix, setActionPrefix] = useState<string>("");
  const [actorUserId, setActorUserId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchAuditEvents = async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (actionPrefix) params.append("action_prefix", actionPrefix);
      if (actorUserId) params.append("actor_user_id", actorUserId);
      params.append("limit", "100");

      const data = await client.get<AuditEvent[]>(`/api/audit?${params.toString()}`);
      setEvents(data);
      setLoading(false);
    } catch (err) {
      console.error("Failed to fetch audit events", err);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchAuditEvents();
  }, [actionPrefix, actorUserId]);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const formatTimestamp = (isoStr: string) => {
    if (!isoStr) return "";
    return isoStr.replace("T", " ").slice(0, 19);
  };

  const getActionBadgeColor = (action: string) => {
    if (action.includes("delete") || action.includes("revoke") || action.includes("fail")) return "red";
    if (action.includes("create") || action.includes("add") || action.includes("success")) return "green";
    if (action.includes("update") || action.includes("edit")) return "yellow";
    return "cyan";
  };

  return (
    <Flex direction="column" gap={6}>
      {/* Title & Filters Row */}
      <Flex justify="space-between" align="end" wrap="wrap" gap={4}>
        <VStack align="start" spacing={1}>
          <Heading as="h1" size="lg" fontWeight="bold" color="white" letterSpacing="-0.02em">
            Audit Trail
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            Cryptographically-sound, append-only console operation history.
          </Text>
        </VStack>
        
        <HStack spacing={3} wrap="wrap">
          {/* Action prefix filter */}
          <InputGroup w="200px" size="sm">
            <InputLeftElement pointerEvents="none" h="36px">
              <Icon as={Search} color="obsidian.onSurfaceVariant" w={4} h={4} />
            </InputLeftElement>
            <Input
              value={actionPrefix}
              onChange={(e) => setActionPrefix(e.target.value)}
              placeholder="Filter by Action..."
              bg="obsidian.surface"
              borderColor="obsidian.border"
              color="white"
              h="36px"
              borderRadius="md"
              fontSize="xs"
              _hover={{ borderColor: "obsidian.cyan" }}
              _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
            />
          </InputGroup>

          {/* Actor user id filter */}
          <InputGroup w="200px" size="sm">
            <InputLeftElement pointerEvents="none" h="36px">
              <Icon as={Search} color="obsidian.onSurfaceVariant" w={4} h={4} />
            </InputLeftElement>
            <Input
              value={actorUserId}
              onChange={(e) => setActorUserId(e.target.value)}
              placeholder="Filter by Actor User ID..."
              bg="obsidian.surface"
              borderColor="obsidian.border"
              color="white"
              h="36px"
              borderRadius="md"
              fontSize="xs"
              _hover={{ borderColor: "obsidian.cyan" }}
              _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
            />
          </InputGroup>

          {/* Refresh button */}
          <Button
            onClick={fetchAuditEvents}
            isLoading={refreshing}
            variant="outline"
            borderColor="obsidian.border"
            color="white"
            h="36px"
            px={3}
            borderRadius="md"
            _hover={{ borderColor: "obsidian.cyan", color: "obsidian.cyan" }}
            bg="obsidian.surface"
          >
            <Icon as={RefreshCw} size={14} />
          </Button>
        </HStack>
      </Flex>

      {/* Audit Table */}
      <Box
        bg="obsidian.surface"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        overflow="hidden"
      >
        {loading ? (
          <Flex align="center" justify="center" minH="300px">
            <Spinner size="lg" color="obsidian.cyan" />
          </Flex>
        ) : events.length === 0 ? (
          <Flex align="center" justify="center" minH="300px" color="obsidian.onSurfaceVariant" direction="column" gap={2}>
            <Icon as={Shield} w={8} h={8} opacity={0.3} />
            <Text fontSize="xs">No audit events found.</Text>
          </Flex>
        ) : (
          <Table variant="unstyled" size="sm">
            <Thead bg="#161619" borderBottom="1px solid" borderColor="obsidian.border">
              <Tr>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6}>Timestamp</Th>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6}>Actor (User / Type)</Th>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6}>Action</Th>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6}>Resource (Type / ID)</Th>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6}>IP Address</Th>
                <Th color="obsidian.onSurfaceVariant" fontFamily="mono" fontSize="10px" py={3} px={6} textAlign="right">Metadata</Th>
              </Tr>
            </Thead>
            <Tbody>
              {events.map((event) => {
                const isExpanded = expandedId === event.id;
                return (
                  <>
                    <Tr
                      key={event.id}
                      borderBottom="1px solid"
                      borderColor="obsidian.border"
                      _hover={{ bg: "rgba(255,255,255,0.01)" }}
                      transition="background-color 0.2s"
                    >
                      {/* Timestamp */}
                      <Td fontFamily="mono" color="white" py={3.5} px={6}>
                        {formatTimestamp(event.created_at)}
                      </Td>
                      
                      {/* Actor */}
                      <Td py={3.5} px={6}>
                        <VStack align="start" spacing={0.5}>
                          <Text fontSize="xs" fontWeight="medium" color="white" fontFamily="mono">
                            {event.actor_user_id || "system"}
                          </Text>
                          <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono">
                            {event.actor_type.toUpperCase()}
                          </Text>
                        </VStack>
                      </Td>

                      {/* Action */}
                      <Td py={3.5} px={6}>
                        <Badge
                          variant="subtle"
                          colorScheme={getActionBadgeColor(event.action)}
                          borderRadius="sm"
                          fontSize="10px"
                          fontFamily="mono"
                        >
                          {event.action}
                        </Badge>
                      </Td>

                      {/* Resource */}
                      <Td py={3.5} px={6}>
                        <VStack align="start" spacing={0.5}>
                          <Text fontSize="xs" color="white" fontFamily="mono">
                            {event.resource_type}
                          </Text>
                          <Text fontSize="10px" color="obsidian.onSurfaceVariant" fontFamily="mono" isTruncated maxW="150px">
                            {event.resource_id || "—"}
                          </Text>
                        </VStack>
                      </Td>

                      {/* IP Address */}
                      <Td fontFamily="mono" color="obsidian.onSurfaceVariant" py={3.5} px={6}>
                        {event.ip_address || "local"}
                      </Td>

                      {/* Actions */}
                      <Td py={3.5} px={6} textAlign="right">
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => toggleExpand(event.id)}
                          color="obsidian.cyan"
                          _hover={{ bg: "rgba(0, 240, 255, 0.1)" }}
                          rightIcon={<Icon as={isExpanded ? ChevronUp : ChevronDown} />}
                        >
                          Details
                        </Button>
                      </Td>
                    </Tr>
                    
                    {/* Collapsible details panel */}
                    <Tr>
                      <Td colSpan={6} p={0}>
                        <Collapse in={isExpanded} animateOpacity>
                          <Box
                            bg="#0A0A0C"
                            borderBottom="1px solid"
                            borderColor="obsidian.border"
                            p={6}
                          >
                            <Grid templateColumns="repeat(12, 1fr)" gap={6}>
                              <GridItem colSpan={{ base: 12, md: 4 }}>
                                <Text fontSize="xs" fontWeight="bold" color="white" mb={2} fontFamily="mono" textTransform="uppercase">
                                  System Context
                                </Text>
                                <VStack align="start" spacing={1.5} fontFamily="mono" fontSize="11px" color="obsidian.onSurfaceVariant">
                                  <Text><strong>Event ID:</strong> {event.id}</Text>
                                  <Text><strong>User Agent:</strong> {event.user_agent || "None"}</Text>
                                </VStack>
                              </GridItem>
                              <GridItem colSpan={{ base: 12, md: 8 }}>
                                <Text fontSize="xs" fontWeight="bold" color="white" mb={2} fontFamily="mono" textTransform="uppercase">
                                  Event Metadata
                                </Text>
                                <Box
                                  bg="#121214"
                                  border="1px solid"
                                  borderColor="obsidian.border"
                                  borderRadius="sm"
                                  p={4}
                                  maxH="200px"
                                  overflowY="auto"
                                >
                                  <Text as="pre" fontSize="11px" fontFamily="mono" color="obsidian.cyan" whiteSpace="pre-wrap">
                                    {JSON.stringify(event.metadata, null, 2)}
                                  </Text>
                                </Box>
                              </GridItem>
                            </Grid>
                          </Box>
                        </Collapse>
                      </Td>
                    </Tr>
                  </>
                );
              })}
            </Tbody>
          </Table>
        )}
      </Box>
    </Flex>
  );
}
