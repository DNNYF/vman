import { describe, it, expect } from "vitest";
import {
  authMethodLabel,
  describeOs,
  environmentLabel,
  sudoModeLabel,
  AUTH_METHODS,
  ENVIRONMENTS,
  SUDO_MODES,
  type Host,
} from "@/lib/hosts";

const baseHost: Host = {
  id: "h1",
  name: "sg-1gb-01",
  hostname_or_ip: "10.0.0.1",
  ssh_port: 22144,
  username: "root",
  auth_method: "key",
  credential_id: "cred-1",
  sudo_mode: "root",
  host_key_fingerprint: null,
  host_key_algorithm: null,
  os_family: null,
  os_name: "Ubuntu",
  os_version: "24.04",
  package_manager: "apt",
  arch: "x86_64",
  cpu_cores: 2,
  ram_mb: 1024,
  disk_total_mb: 20_480,
  provider: "Contabo",
  region: "sg-1",
  environment: "production",
  risk_level: "medium",
  tags: ["singapore", "1gb", "experiment"],
  notes: "Test host",
  last_seen_at: "2026-06-23T08:00:00Z",
  disabled_at: null,
  created_at: "2026-06-22T08:00:00Z",
  updated_at: "2026-06-23T08:00:00Z",
};

describe("host label helpers", () => {
  it("returns a human label for known auth methods", () => {
    expect(authMethodLabel("key")).toMatch(/SSH key/i);
    expect(authMethodLabel("password")).toMatch(/Password/i);
    expect(authMethodLabel("key_with_passphrase")).toMatch(/passphrase/i);
  });

  it("falls back to the raw value for unknown auth methods", () => {
    // Force an unknown value through the helper to make sure the
    // fallback path is exercised.
    expect(authMethodLabel("magic" as unknown as "key")).toBe("magic");
  });

  it("returns a label for known sudo modes", () => {
    expect(sudoModeLabel("root")).toMatch(/Root login/i);
    expect(sudoModeLabel("passwordless_sudo")).toMatch(/Passwordless sudo/i);
    expect(sudoModeLabel("sudo_password")).toMatch(/password/i);
  });

  it("returns a label for environments", () => {
    expect(environmentLabel("production")).toBe("Production");
    expect(environmentLabel("staging")).toBe("Staging");
    expect(environmentLabel("experiment")).toBe("Experiment");
  });

  it("does not contain any secret-shaped strings in the option lists", () => {
    for (const m of AUTH_METHODS) {
      expect(m.label).not.toMatch(/-----BEGIN/);
      expect(m.hint).not.toMatch(/-----BEGIN/);
    }
    for (const m of SUDO_MODES) {
      expect(m.label).not.toMatch(/-----BEGIN/);
      expect(m.hint).not.toMatch(/-----BEGIN/);
    }
    for (const e of ENVIRONMENTS) {
      expect(e.label).not.toMatch(/-----BEGIN/);
    }
  });
});

describe("describeOs", () => {
  it("combines name, version and arch when present", () => {
    expect(describeOs(baseHost)).toBe("Ubuntu • 24.04 • x86_64");
  });

  it("returns a dash when no fields are present", () => {
    expect(
      describeOs({ ...baseHost, os_name: null, os_version: null, arch: null }),
    ).toBe("—");
  });

  it("renders whatever subset is available", () => {
    expect(
      describeOs({ ...baseHost, os_name: "Debian", os_version: null, arch: null }),
    ).toBe("Debian");
  });
});
