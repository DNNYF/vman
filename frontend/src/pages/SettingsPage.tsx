import { useEffect, useState } from "react";
import {
  Box,
  Flex,
  Heading,
  Text,
  Input,
  Select,
  Button,
  VStack,
  HStack,
  Icon,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  FormControl,
  FormLabel,
  useToast,
  Spinner,
} from "@chakra-ui/react";
import { Save } from "lucide-react";
import { ApiClient } from "@/lib/api";

const client = new ApiClient({ baseUrl: "" });

interface AppSettings {
  env: "development" | "production";
  api_host: string;
  api_port: number;
  database_url: string;
  log_level: string;
  log_retention_days: number;
  metrics_retention_days: number;
  uvicorn_workers: number;
  worker_concurrency: number;
  ssh_connect_timeout_seconds: number;
  ssh_command_timeout_seconds: number;
}

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const toast = useToast();

  const fetchSettings = async () => {
    try {
      const data = await client.get<AppSettings>("/api/settings");
      setSettings(data);
      setLoading(false);
    } catch (err: any) {
      toast({
        title: "Error loading settings",
        description: err?.message || "Failed to retrieve configuration.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleInputChange = (field: keyof AppSettings, value: any) => {
    if (!settings) return;
    setSettings({
      ...settings,
      [field]: value,
    });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await client.post<AppSettings>("/api/settings", { json: settings });
      setSettings(updated);
      toast({
        title: "Settings Saved",
        description: "Application configuration updated and .env file reloaded.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    } catch (err: any) {
      toast({
        title: "Save Failed",
        description: err?.message || "Failed to update configuration settings.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Flex align="center" justify="center" minH="300px">
        <Spinner size="lg" color="obsidian.cyan" />
      </Flex>
    );
  }

  if (!settings) return null;

  return (
    <Flex direction="column" gap={6} maxW="800px">
      <VStack align="start" spacing={1}>
        <Heading as="h1" size="lg" fontWeight="bold" color="white" letterSpacing="-0.02em">
          Application Settings
        </Heading>
        <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
          Configure runtime environment, agentless operations, and resource profiles.
        </Text>
      </VStack>

      <Box
        as="form"
        onSubmit={handleSave}
        bg="obsidian.surface"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        p={6}
      >
        <Tabs colorScheme="cyan" variant="line">
          <TabList borderColor="obsidian.border" mb={6}>
            <Tab
              color="obsidian.onSurfaceVariant"
              fontSize="sm"
              fontWeight="medium"
              _selected={{ color: "obsidian.cyan", borderColor: "obsidian.cyan" }}
              _hover={{ color: "white" }}
            >
              General
            </Tab>
            <Tab
              color="obsidian.onSurfaceVariant"
              fontSize="sm"
              fontWeight="medium"
              _selected={{ color: "obsidian.cyan", borderColor: "obsidian.cyan" }}
              _hover={{ color: "white" }}
            >
              SSH Settings
            </Tab>
            <Tab
              color="obsidian.onSurfaceVariant"
              fontSize="sm"
              fontWeight="medium"
              _selected={{ color: "obsidian.cyan", borderColor: "obsidian.cyan" }}
              _hover={{ color: "white" }}
            >
              Worker Settings
            </Tab>
            <Tab
              color="obsidian.onSurfaceVariant"
              fontSize="sm"
              fontWeight="medium"
              _selected={{ color: "obsidian.cyan", borderColor: "obsidian.cyan" }}
              _hover={{ color: "white" }}
            >
              Retention
            </Tab>
          </TabList>

          <TabPanels>
            {/* General Tab */}
            <TabPanel p={0}>
              <VStack spacing={5} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Environment
                  </FormLabel>
                  <Select
                    value={settings.env}
                    onChange={(e) => handleInputChange("env", e.target.value)}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  >
                    <option value="development">development</option>
                    <option value="production">production</option>
                  </Select>
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    API Host
                  </FormLabel>
                  <Input
                    value={settings.api_host}
                    onChange={(e) => handleInputChange("api_host", e.target.value)}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    API Port
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.api_port}
                    onChange={(e) => handleInputChange("api_port", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Database URL
                  </FormLabel>
                  <Input
                    value={settings.database_url}
                    onChange={(e) => handleInputChange("database_url", e.target.value)}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Log Level
                  </FormLabel>
                  <Select
                    value={settings.log_level}
                    onChange={(e) => handleInputChange("log_level", e.target.value)}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  >
                    <option value="DEBUG">DEBUG</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </Select>
                </FormControl>
              </VStack>
            </TabPanel>

            {/* SSH Settings Tab */}
            <TabPanel p={0}>
              <VStack spacing={5} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    SSH Connect Timeout (Seconds)
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.ssh_connect_timeout_seconds}
                    onChange={(e) => handleInputChange("ssh_connect_timeout_seconds", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    SSH Command Timeout (Seconds)
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.ssh_command_timeout_seconds}
                    onChange={(e) => handleInputChange("ssh_command_timeout_seconds", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>
              </VStack>
            </TabPanel>

            {/* Worker Settings Tab */}
            <TabPanel p={0}>
              <VStack spacing={5} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Uvicorn Workers
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.uvicorn_workers}
                    onChange={(e) => handleInputChange("uvicorn_workers", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Worker Concurrency
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.worker_concurrency}
                    onChange={(e) => handleInputChange("worker_concurrency", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>
              </VStack>
            </TabPanel>

            {/* Retention Tab */}
            <TabPanel p={0}>
              <VStack spacing={5} align="stretch">
                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Log Retention (Days)
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.log_retention_days}
                    onChange={(e) => handleInputChange("log_retention_days", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>

                <FormControl isRequired>
                  <FormLabel fontSize="xs" fontWeight="bold" color="white" fontFamily="mono" textTransform="uppercase">
                    Metrics Retention (Days)
                  </FormLabel>
                  <Input
                    type="number"
                    value={settings.metrics_retention_days}
                    onChange={(e) => handleInputChange("metrics_retention_days", parseInt(e.target.value, 10))}
                    bg="obsidian.bg"
                    borderColor="obsidian.border"
                    color="white"
                    _hover={{ borderColor: "obsidian.cyan" }}
                    _focus={{ borderColor: "obsidian.cyan", boxShadow: "none" }}
                  />
                </FormControl>
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>

        <HStack justify="end" mt={8} pt={4} borderTop="1px solid" borderColor="obsidian.border">
          <Button
            type="submit"
            isLoading={saving}
            leftIcon={<Icon as={Save} size={16} />}
            bg="obsidian.cyan"
            color="black"
            _hover={{ bg: "#00dbe9" }}
            _active={{ bg: "#006970" }}
            fontWeight="bold"
            fontSize="sm"
            borderRadius="md"
            h="40px"
            px={6}
          >
            Save Configuration
          </Button>
        </HStack>
      </Box>
    </Flex>
  );
}
