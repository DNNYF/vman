import { useState, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Box,
  Heading,
  Text,
  Spinner,
  Alert,
  AlertIcon,
  HStack,
  Badge,
  Icon,
  Flex,
} from "@chakra-ui/react";
import { Network } from "lucide-react";
import { listHosts } from "@/lib/hostsApi";
import { listJobs } from "@/lib/jobsApi";
import type { Host } from "@/lib/hosts";
import type { Job } from "@/lib/jobs";

export function HostTopology() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [runningJobs, setRunningJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    async function fetchData() {
      try {
        const [hostsData, jobsData] = await Promise.all([
          listHosts(),
          listJobs({ status: "running" }),
        ]);
        setHosts(hostsData);
        setRunningJobs(jobsData);
      } catch (err: any) {
        setError(err.message || "Failed to load topology data.");
      } finally {
        setLoading(false);
      }
    }

    fetchData();
    // Poll every 5 seconds for live status
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (loading || error) return;

    const centerX = 400;
    const centerY = 300;
    const radius = 220;

    // 1. Central Node (VMAN Control Plane)
    const centralNodeId = "vman-control-plane";
    const newNodes: any[] = [
      {
        id: centralNodeId,
        position: { x: centerX - 90, y: centerY - 45 },
        style: {
          background: "#121214",
          color: "#e5e1e4",
          border: "2px solid #00F0FF",
          borderRadius: "4px",
          padding: "16px",
          width: "180px",
          boxShadow: "0 0 20px rgba(0, 240, 255, 0.15)",
          textAlign: "center",
        },
        data: {
          label: (
            <div>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: "4px" }}>
                <Icon as={Network} size={20} color="#00F0FF" />
              </div>
              <strong style={{ fontSize: "14px", fontFamily: "Geist" }}>VMAN Control Plane</strong>
              <div style={{ fontSize: "10px", color: "#b9cacb", fontFamily: "JetBrains Mono" }}>Host Manager</div>
            </div>
          ),
        },
      },
    ];

    const newEdges: any[] = [];

    // 2. Add Target Hosts as surrounding nodes
    hosts.forEach((host, index) => {
      const angle = (index / hosts.length) * 2 * Math.PI;
      const x = centerX + radius * Math.cos(angle) - 75;
      const y = centerY + radius * Math.sin(angle) - 45;

      // Determine status based on jobs and host parameters
      const hasActiveJob = runningJobs.some((j) => j.host_id === host.id);
      
      // Node styling
      let borderCol = "#849495"; // grey/inactive
      let shadowCol = "rgba(0, 0, 0, 0)";
      let statusText = "Ready";
      let statusColor = "#b9cacb";

      if (hasActiveJob) {
        borderCol = "#00F0FF"; // electric cyan
        shadowCol = "rgba(0, 240, 255, 0.3)";
        statusText = "Managing...";
        statusColor = "#00F0FF";
      } else if (host.disabled_at) {
        borderCol = "#FF3131"; // red
        statusText = "Disabled";
        statusColor = "#FF3131";
      } else if (host.host_key_fingerprint) {
        borderCol = "#39FF14"; // acid green
        statusText = "Healthy";
        statusColor = "#39FF14";
      }

      newNodes.push({
        id: host.id,
        position: { x, y },
        style: {
          background: "#121214",
          color: "#e5e1e4",
          border: `1px solid ${borderCol}`,
          borderRadius: "4px",
          padding: "10px",
          width: "150px",
          boxShadow: `0 0 10px ${shadowCol}`,
          textAlign: "center",
          cursor: "pointer",
        },
        data: {
          label: (
            <div>
              <div style={{ fontWeight: "bold", fontSize: "12px", fontFamily: "Geist", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {host.name}
              </div>
              <div style={{ fontSize: "10px", color: "#b9cacb", fontFamily: "JetBrains Mono", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {host.hostname_or_ip}
              </div>
              <div style={{ fontSize: "9px", color: statusColor, fontFamily: "JetBrains Mono", fontWeight: "bold", marginTop: "4px" }}>
                {statusText}
              </div>
            </div>
          ),
        },
      });

      // Edge link from VMAN to Host
      newEdges.push({
        id: `edge-${host.id}`,
        source: centralNodeId,
        target: host.id,
        animated: hasActiveJob, // animate line when a job is active
        style: {
          stroke: hasActiveJob ? "#00F0FF" : host.disabled_at ? "#FF3131" : "#39FF14",
          strokeWidth: hasActiveJob ? 3 : 1.5,
        },
      });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  }, [hosts, runningJobs, loading, error]);

  if (loading) {
    return (
      <Box p={8} display="flex" justifyContent="center" alignItems="center" minH="400px">
        <Spinner size="xl" color="obsidian.cyan" />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={8}>
        <Alert status="error" bg="rgba(255, 49, 49, 0.1)" color="obsidian.red" border="1px solid rgba(255, 49, 49, 0.2)" borderRadius="md">
          <AlertIcon color="obsidian.red" />
          {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box p={4} height="100%" display="flex" flexDirection="column" gap={6}>
      <Flex justify="space-between" align="end">
        <Box>
          <Heading size="lg" color="white" mb={1}>Host Topology</Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            Connected target hosts routing through VMAN Control Plane in real time.
          </Text>
        </Box>
        <HStack spacing={3}>
          <Badge bg="rgba(57, 255, 20, 0.1)" color="obsidian.green" border="1px solid rgba(57, 255, 20, 0.2)" px={2.5} py={1} borderRadius="sm" variant="subtle" fontSize="10px" fontFamily="mono">
            ● Healthy / Connected
          </Badge>
          <Badge bg="rgba(0, 240, 255, 0.1)" color="obsidian.cyan" border="1px solid rgba(0, 240, 255, 0.2)" px={2.5} py={1} borderRadius="sm" variant="subtle" fontSize="10px" fontFamily="mono">
            ● Active / Managing Job
          </Badge>
          <Badge bg="rgba(255, 49, 49, 0.1)" color="obsidian.red" border="1px solid rgba(255, 49, 49, 0.2)" px={2.5} py={1} borderRadius="sm" variant="subtle" fontSize="10px" fontFamily="mono">
            ● Disabled / Error
          </Badge>
        </HStack>
      </Flex>

      <Box
        flex="1"
        minH="550px"
        bg="obsidian.bg"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        overflow="hidden"
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          nodesConnectable={false}
          nodesDraggable={true}
        >
          <Background color="#1F1F23" gap={16} size={1} />
          <Controls style={{ backgroundColor: "#121214", border: "1px solid #1F1F23", color: "#e5e1e4" }} />
        </ReactFlow>
      </Box>
    </Box>
  );
}
