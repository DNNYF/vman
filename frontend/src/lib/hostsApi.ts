/**
 * Thin wrapper around the VMAN host HTTP API.
 *
 * The backend mounts host routes at ``/api/hosts`` (see
 * ``backend/vman/api/routes_hosts.py``). The global ``ApiClient``
 * default base is ``/api/v1`` for forward compatibility, so we
 * explicitly point this module at the right path.
 *
 * SECURITY: this module never carries secret material. The forms that
 * collect credentials POST to the vault directly; here we only ever
 * pass ``credential_id`` references around.
 */

import { ApiClient, ApiError } from "@/lib/api";
import type {
  ConnectionTestResult,
  Host,
  HostCreatePayload,
  HostUpdatePayload,
} from "@/lib/hosts";

const HOSTS_BASE = "";

const client = new ApiClient({ baseUrl: HOSTS_BASE });

export class HostApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "HostApiError";
    this.status = status;
    this.detail = detail;
  }
}

function toHostError(err: unknown): never {
  if (err instanceof ApiError) {
    throw new HostApiError(err.status, err.message);
  }
  if (err instanceof Error) {
    throw new HostApiError(0, err.message);
  }
  throw new HostApiError(0, "Unknown host API error");
}

export async function listHosts(options: { includeDisabled?: boolean } = {}): Promise<Host[]> {
  try {
    const query = options.includeDisabled ? "?include_disabled=true" : "";
    return await client.get<Host[]>(`/api/hosts${query}`);
  } catch (err) {
    toHostError(err);
  }
}

export async function getHost(id: string): Promise<Host> {
  try {
    return await client.get<Host>(`/api/hosts/${encodeURIComponent(id)}`);
  } catch (err) {
    toHostError(err);
  }
}

export async function createHost(payload: HostCreatePayload): Promise<Host> {
  try {
    return await client.post<Host>("/api/hosts", { json: payload });
  } catch (err) {
    toHostError(err);
  }
}

export async function updateHost(
  id: string,
  payload: HostUpdatePayload,
): Promise<Host> {
  try {
    return await client.patch<Host>(
      `/api/hosts/${encodeURIComponent(id)}`,
      { json: payload },
    );
  } catch (err) {
    toHostError(err);
  }
}

export async function deleteHost(id: string): Promise<void> {
  try {
    await client.delete<{ status: string }>(
      `/api/hosts/${encodeURIComponent(id)}`,
    );
  } catch (err) {
    toHostError(err);
  }
}

/**
 * Trigger a connectivity / auth check on the target. The backend
 * endpoint is not yet implemented in this milestone; if the request
 * 404s we return a synthetic, clearly-labelled "endpoint missing"
 * result so the UI does not crash. This keeps the dashboard usable
 * while the worker is being built.
 */
export async function testConnection(id: string): Promise<ConnectionTestResult> {
  const now = new Date().toISOString();
  try {
    return await client.post<ConnectionTestResult>(
      `/api/hosts/${encodeURIComponent(id)}/test`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return {
        ok: false,
        reached: false,
        authenticated: false,
        host_key_fingerprint: null,
        host_key_algorithm: null,
        latency_ms: null,
        message:
          "Connection test endpoint is not implemented in this build. The host record was saved but could not be probed.",
        tested_at: now,
      };
    }
    toHostError(err);
  }
}

export const HOSTS_API_BASE = HOSTS_BASE;
