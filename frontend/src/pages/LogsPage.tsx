import { useEffect, useState, useRef } from "react";
import {
  Box,
  Flex,
  Heading,
  Text,
  Select,
  Input,
  InputGroup,
  InputLeftElement,
  Button,
  VStack,
  HStack,
  Icon,
  Checkbox,
} from "@chakra-ui/react";
import { ScrollText, Search, RefreshCw } from "lucide-react";
import { ApiClient } from "@/lib/api";

const client = new ApiClient({ baseUrl: "" });

interface LogRecord {
  timestamp: number;
  name: string;
  level: string;
  message: string;
}

export function LogsPage() {
  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [level, setLevel] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const consoleEndRef = useRef<HTMLDivElement | null>(null);

  const fetchLogs = async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (level) params.append("level", level);
      if (search) params.append("search", search);
      params.append("limit", "200");

      const data = await client.get<LogRecord[]>(`/api/logs?${params.toString()}`);
      setLogs(data);
    } catch (err) {
      console.error("Failed to fetch logs", err);
    } finally {
      setRefreshing(false);
    }
  };

  // Fetch logs on mount, and on level/search changes
  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [level, search]);

  // Scroll to bottom when logs update
  useEffect(() => {
    if (autoScroll && consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const getLogLevelColor = (lvl: string) => {
    switch (lvl.toUpperCase()) {
      case "INFO":
        return "obsidian.green";
      case "WARNING":
        return "orange.300";
      case "ERROR":
        return "obsidian.red";
      case "DEBUG":
        return "gray.500";
      default:
        return "white";
    }
  };

  const formatTimestamp = (unixSec: number) => {
    const d = new Date(unixSec * 1000);
    return d.toISOString().replace("T", " ").slice(0, 19);
  };

  return (
    <Flex direction="column" gap={6} h="calc(100vh - 120px)">
      {/* Title & Filters Row */}
      <Flex justify="space-between" align="end" wrap="wrap" gap={4}>
        <VStack align="start" spacing={1}>
          <Heading as="h1" size="lg" fontWeight="bold" color="white" letterSpacing="-0.02em">
            System Logs
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            Live diagnostic stream from the VMAN control plane.
          </Text>
        </VStack>
        
        <HStack spacing={3} wrap="wrap">
          {/* Severity filter */}
          <Select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            bg="obsidian.surface"
            borderColor="obsidian.border"
            color="white"
            fontSize="xs"
            w="130px"
            h="36px"
            borderRadius="md"
            _hover={{ borderColor: "obsidian.cyan" }}
            _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
          >
            <option value="">All Levels</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </Select>

          {/* Search text */}
          <InputGroup w="240px" size="sm">
            <InputLeftElement pointerEvents="none" h="36px">
              <Icon as={Search} color="obsidian.onSurfaceVariant" w={4} h={4} />
            </InputLeftElement>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search logs..."
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
            onClick={fetchLogs}
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

          {/* Auto-scroll checkbox */}
          <Checkbox
            isChecked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            colorScheme="cyan"
            fontSize="xs"
            color="obsidian.onSurfaceVariant"
            fontFamily="mono"
          >
            Auto-scroll
          </Checkbox>
        </HStack>
      </Flex>

      {/* Monospace Console Window */}
      <Box
        flex="1"
        bg="#050507"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        p={5}
        fontFamily="mono"
        fontSize="xs"
        overflowY="auto"
        whiteSpace="pre-wrap"
        boxShadow="inset 0 0 10px rgba(0,0,0,0.8)"
        position="relative"
      >
        {logs.length === 0 ? (
          <Flex align="center" justify="center" h="100%" color="obsidian.onSurfaceVariant" direction="column" gap={2}>
            <Icon as={ScrollText} w={8} h={8} opacity={0.3} />
            <Text fontSize="xs">No logs matched the current filters.</Text>
          </Flex>
        ) : (
          logs.map((log, idx) => (
            <Flex key={idx} mb={1.5} align="start" gap={3}>
              {/* Timestamp */}
              <Text as="span" color="gray.600" userSelect="none" flexShrink={0}>
                [{formatTimestamp(log.timestamp)}]
              </Text>
              
              {/* Logger name */}
              <Text as="span" color="blue.400" flexShrink={0} maxW="150px" isTruncated>
                {log.name}
              </Text>

              {/* Level */}
              <Text as="span" color={getLogLevelColor(log.level)} fontWeight="bold" flexShrink={0} w="60px">
                {log.level.toUpperCase()}
              </Text>

              {/* Message */}
              <Text as="span" color="gray.350" wordBreak="break-all">
                {log.message}
              </Text>
            </Flex>
          ))
        )}
        <div ref={consoleEndRef} />
      </Box>
    </Flex>
  );
}
