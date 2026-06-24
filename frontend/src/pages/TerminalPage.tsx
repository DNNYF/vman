import { useEffect, useRef, useState } from "react";
import {
  Box,
  Flex,
  Select,
  Text,
  Heading,
  VStack,
  HStack,
  Button,
  Icon,
} from "@chakra-ui/react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import { Server, Terminal as TerminalIcon, Power } from "lucide-react";
import { ApiClient } from "@/lib/api";
import "xterm/css/xterm.css";

const client = new ApiClient({ baseUrl: "" });

interface Host {
  id: string;
  name: string;
  hostname_or_ip: string;
  ssh_port: number;
}

export function TerminalPage() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [selectedHostId, setSelectedHostId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [, setConnected] = useState<boolean>(false);
  const [, setErrorMsg] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch hosts list
  useEffect(() => {
    client.get<Host[]>("/api/hosts")
      .then((data) => {
        setHosts(data);
        setLoading(false);
      })
      .catch(() => {
        setHosts([]);
        setLoading(false);
      });
  }, []);

  // Initialize terminal instance once
  useEffect(() => {
    if (!containerRef.current) return;

    // Create terminal with Obsidian styles
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 14,
      theme: {
        background: "#0A0A0C",
        foreground: "#b9cacb",
        cursor: "#00F0FF",
        black: "#000000",
        red: "#FF3131",
        green: "#39FF14",
        yellow: "#FFD700",
        blue: "#00F0FF",
        magenta: "#DA70D6",
        cyan: "#00F0FF",
        white: "#FFFFFF",
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    fitAddon.fit();

    terminalRef.current = term;
    fitAddonRef.current = fitAddon;

    // Handle resize
    const handleResize = () => {
      try {
        fitAddon.fit();
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: "resize",
            cols: term.cols,
            rows: term.rows,
          }));
        }
      } catch (e) {
        // Ignore
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
  }, []);

  // Handle host selection change and connect WebSocket
  useEffect(() => {
    if (!selectedHostId) {
      if (wsRef.current) {
        wsRef.current.close();
      }
      setConnected(false);
      return;
    }

    const term = terminalRef.current;
    if (!term) return;

    term.reset();
    term.write("\r\n\x1b[1;36mConnecting to SSH remote shell...\x1b[0m\r\n");

    // Close existing websocket
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Determine WS protocol/host
    const isDev = window.location.port === "5173";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = isDev ? "localhost:8000" : window.location.host;
    const wsUrl = `${protocol}//${host}/api/terminal/ws/${selectedHostId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    setConnected(false);
    setErrorMsg(null);

    // Terminal data -> WebSocket
    const onDataDisposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    ws.onopen = () => {
      setConnected(true);
      term.write("\x1b[1;32mConnection established.\x1b[0m\r\n");
      // Trigger a resize event to set the backend terminal dimensions
      try {
        if (fitAddonRef.current) {
          fitAddonRef.current.fit();
        }
        ws.send(JSON.stringify({
          type: "resize",
          cols: term.cols,
          rows: term.rows,
        }));
      } catch (e) {
        // Ignore
      }
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onerror = () => {
      setErrorMsg("WebSocket connection error.");
      term.write("\r\n\x1b[1;31mWebSocket connection error.\x1b[0m\r\n");
    };

    ws.onclose = (event) => {
      setConnected(false);
      onDataDisposable.dispose();
      term.write(`\r\n\x1b[1;31mSession closed (code: ${event.code}).\x1b[0m\r\n`);
    };

    return () => {
      ws.close();
      onDataDisposable.dispose();
    };
  }, [selectedHostId]);

  const disconnectHost = () => {
    setSelectedHostId("");
  };

  return (
    <Flex direction="column" gap={6} h="calc(100vh - 120px)">
      {/* Title & Dropdown */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={4}>
        <VStack align="start" spacing={1}>
          <Heading as="h1" size="lg" fontWeight="bold" color="white" letterSpacing="-0.02em">
            Interactive Terminal
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            Execute commands directly on remote fleet instances.
          </Text>
        </VStack>

        <HStack spacing={3}>
          <Flex align="center" gap={2}>
            <Icon as={Server} color="obsidian.cyan" />
            <Select
              placeholder={loading ? "Loading hosts..." : "Select remote host..."}
              value={selectedHostId}
              onChange={(e) => setSelectedHostId(e.target.value)}
              isDisabled={loading}
              bg="obsidian.surface"
              borderColor="obsidian.border"
              color="white"
              _hover={{ borderColor: "obsidian.borderHigh" }}
              _focus={{ borderColor: "obsidian.cyan", boxShadow: "0 0 0 1px #00F0FF" }}
              minW="220px"
              size="sm"
            >
              {hosts.map((host) => (
                <option key={host.id} value={host.id} style={{ background: "#121214" }}>
                  {host.name} ({host.hostname_or_ip}:{host.ssh_port})
                </option>
              ))}
            </Select>
          </Flex>

          {selectedHostId && (
            <Button
              leftIcon={<Power size={14} />}
              colorScheme="red"
              bg="obsidian.red"
              color="white"
              size="sm"
              onClick={disconnectHost}
              _hover={{ opacity: 0.9 }}
            >
              Disconnect
            </Button>
          )}
        </HStack>
      </Flex>

      {/* Terminal View Container */}
      <Box
        flex={1}
        bg="#0A0A0C"
        border="1px solid"
        borderColor="obsidian.border"
        p={4}
        borderRadius="md"
        position="relative"
        overflow="hidden"
        boxShadow="inset 0 0 10px rgba(0,0,0,0.5)"
      >
        <div
          ref={containerRef}
          style={{ width: "100%", height: "100%", outline: "none" }}
        />
        {!selectedHostId && (
          <Flex
            position="absolute"
            top={0}
            left={0}
            right={0}
            bottom={0}
            align="center"
            justify="center"
            bg="rgba(10, 10, 12, 0.9)"
            backdropFilter="blur(2px)"
          >
            <VStack spacing={3}>
              <Icon as={TerminalIcon} w={8} h={8} color="obsidian.cyan" opacity={0.6} />
              <Text color="gray.500" fontSize="sm" fontFamily="mono">
                No active terminal session. Select a host to connect.
              </Text>
            </VStack>
          </Flex>
        )}
      </Box>
    </Flex>
  );
}
