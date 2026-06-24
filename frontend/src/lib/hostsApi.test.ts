import { describe, it, expect, afterEach } from "vitest";
import { HostApiError, listHosts, createHost, testConnection } from "@/lib/hostsApi";
import type { Host } from "@/lib/hosts";

const sampleHost: Host = {
  id: "h1",
  name: "sg-1gb-01",
  hostname_or_ip: "10.0.0.1",
  ssh_port: 22,
  username: "root",
  auth_method: "key",
  credential_id: "cred-1",
  sudo_mode: "root",
  host_key_fingerprint: null,
  host_key_algorithm: null,
  os_family: null,
  os_name: null,
  os_version: null,
  package_manager: null,
  arch: null,
  cpu_cores: null,
  ram_mb: null,
  disk_total_mb: null,
  provider: null,
  region: null,
  environment: "experiment",
  risk_level: null,
  tags: [],
  notes: "",
  last_seen_at: null,
  disabled_at: null,
  created_at: "2026-06-23T08:00:00Z",
  updated_at: "2026-06-23T08:00:00Z",
};

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetchOnce(body: unknown, status = 200): void {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as unknown as typeof fetch;
}

describe("hostsApi", () => {
  it("listHosts returns parsed payload and hits /api/hosts", async () => {
    let observedUrl = "";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      observedUrl = String(input);
      return new Response(JSON.stringify([sampleHost]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;
    const rows = await listHosts();
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("h1");
    expect(observedUrl).toBe("/api/hosts");
  });

  it("listHosts forwards include_disabled as a query string", async () => {
    let observedUrl = "";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      observedUrl = String(input);
      return new Response(JSON.stringify([]), { status: 200 });
    }) as unknown as typeof fetch;
    await listHosts({ includeDisabled: true });
    expect(observedUrl).toBe("/api/hosts?include_disabled=true");
  });

  it("createHost posts JSON to /api/hosts and returns the new host", async () => {
    let observedUrl = "";
    let observedBody = "";
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      observedUrl = String(input);
      observedBody = String(init?.body ?? "");
      return new Response(JSON.stringify(sampleHost), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;
    const created = await createHost({
      name: "sg-1gb-01",
      hostname_or_ip: "10.0.0.1",
      ssh_port: 22,
      username: "root",
      auth_method: "key",
      credential_id: "cred-1",
      sudo_mode: "root",
      environment: "experiment",
      provider: null,
      region: null,
      tags: [],
      notes: "",
    });
    expect(created.id).toBe("h1");
    expect(observedUrl).toBe("/api/hosts");
    expect(observedBody).toContain('"name":"sg-1gb-01"');
    // The plaintext form must not leak a password or key through the API.
    expect(observedBody).not.toMatch(/-----BEGIN/);
    expect(observedBody).not.toMatch(/password/i);
  });

  it("listHosts wraps ApiError into HostApiError", async () => {
    mockFetchOnce({ detail: "boom" }, 500);
    await expect(listHosts()).rejects.toBeInstanceOf(HostApiError);
  });

  it("testConnection returns a synthetic placeholder on 404", async () => {
    mockFetchOnce({ detail: "not found" }, 404);
    const result = await testConnection("h1");
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/not implemented/i);
    expect(result.tested_at).toMatch(/T/);
  });

  it("testConnection returns the backend payload when present", async () => {
    mockFetchOnce({
      ok: true,
      reached: true,
      authenticated: true,
      host_key_fingerprint: "SHA256:abc",
      host_key_algorithm: "ed25519",
      latency_ms: 42,
      message: "ok",
      tested_at: "2026-06-23T09:00:00Z",
    });
    const result = await testConnection("h1");
    expect(result.ok).toBe(true);
    expect(result.reached).toBe(true);
    expect(result.latency_ms).toBe(42);
  });
});
