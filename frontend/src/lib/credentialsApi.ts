import { ApiClient, ApiError } from "@/lib/api";

const CREDENTIALS_BASE = "";
const client = new ApiClient({ baseUrl: CREDENTIALS_BASE });

export interface Credential {
  id: string;
  name: string;
  kind: "ssh_password" | "ssh_private_key" | "ssh_private_key_passphrase" | "sudo_password" | "api_token";
  fingerprint: string;
  metadata_json: Record<string, any>;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CredentialCreatePayload {
  name: string;
  kind: string;
  plaintext: string;
}

export class CredentialApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "CredentialApiError";
    this.status = status;
    this.detail = detail;
  }
}

function toCredentialError(err: unknown): never {
  if (err instanceof ApiError) {
    throw new CredentialApiError(err.status, err.message);
  }
  if (err instanceof Error) {
    throw new CredentialApiError(0, err.message);
  }
  throw new CredentialApiError(0, "Unknown credential API error");
}

export async function listCredentials(): Promise<Credential[]> {
  try {
    return await client.get<Credential[]>("/api/credentials");
  } catch (err) {
    toCredentialError(err);
  }
}

export async function createCredential(payload: CredentialCreatePayload): Promise<Credential> {
  try {
    return await client.post<Credential>("/api/credentials", { json: payload });
  } catch (err) {
    toCredentialError(err);
  }
}

export async function deleteCredential(id: string): Promise<void> {
  try {
    await client.delete<{ status: string }>(`/api/credentials/${encodeURIComponent(id)}`);
  } catch (err) {
    toCredentialError(err);
  }
}
