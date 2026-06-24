import { useRouteError, isRouteErrorResponse, Link as RouterLink } from "react-router-dom";
import {
  Box,
  Flex,
  Text,
  Heading,
  Button,
  VStack,
} from "@chakra-ui/react";

export function NotFoundPage() {
  return (
    <Flex minH="60vh" align="center" justify="center" p={4}>
      <Box
        w="full"
        maxW="md"
        bg="obsidian.surface"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        overflow="hidden"
        textAlign="center"
        p={8}
      >
        <VStack spacing={4}>
          <Heading size="md" color="white" fontFamily="mono" textTransform="uppercase" letterSpacing="wider">
            404 — PAGE NOT FOUND
          </Heading>
          <Text fontSize="sm" color="obsidian.onSurfaceVariant" fontFamily="mono">
            THE PAGE YOU ARE REQUESTING DOES NOT EXIST OR HAS BEEN MOVED.
          </Text>
          <Button
            as={RouterLink}
            to="/"
            bg="obsidian.cyan"
            color="black"
            _hover={{ bg: "#00D8E6" }}
            size="sm"
            fontFamily="mono"
            fontSize="xs"
            mt={2}
          >
            Back to dashboard
          </Button>
        </VStack>
      </Box>
    </Flex>
  );
}

export function RouteErrorPage() {
  const error = useRouteError();
  let title = "Something went wrong";
  let message = "An unexpected error occurred while rendering this page.";

  if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`;
    message =
      typeof error.data === "string"
        ? error.data
        : "The route returned an error response.";
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <Flex minH="60vh" align="center" justify="center" p={4}>
      <Box
        w="full"
        maxW="lg"
        bg="obsidian.surface"
        border="1px solid"
        borderColor="obsidian.border"
        borderRadius="md"
        overflow="hidden"
        textAlign="center"
        p={8}
      >
        <VStack spacing={4}>
          <Heading size="md" color="red.400" fontFamily="mono" textTransform="uppercase" letterSpacing="wider">
            {title.toUpperCase()}
          </Heading>
          <Text fontSize="sm" color="gray.300" fontFamily="mono">
            {message}
          </Text>
          <Button
            as={RouterLink}
            to="/"
            bg="obsidian.cyan"
            color="black"
            _hover={{ bg: "#00D8E6" }}
            size="sm"
            fontFamily="mono"
            fontSize="xs"
            mt={2}
          >
            Back to dashboard
          </Button>
        </VStack>
      </Box>
    </Flex>
  );
}
