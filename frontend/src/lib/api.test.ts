import { describe, it, expect } from "vitest";
import { ApiClient, ApiError } from "@/lib/api";

describe("api client", () => {
  it("builds URLs relative to the base path", async () => {
    let observedUrl = "";
    const client = new ApiClient({ baseUrl: "/api/v1" });
    const fetchMock = async (
      input: RequestInfo | URL,
      _init?: RequestInit,
    ): Promise<Response> => {
      observedUrl = String(input);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      const data = await client.get<{ ok: boolean }>("health");
      expect(data.ok).toBe(true);
      expect(observedUrl).toBe("/api/v1/health");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("throws ApiError on non-2xx responses", async () => {
    const client = new ApiClient({ baseUrl: "/api/v1" });
    const fetchMock = async (): Promise<Response> =>
      new Response(JSON.stringify({ detail: "nope" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    try {
      await expect(client.get("x")).rejects.toBeInstanceOf(ApiError);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
