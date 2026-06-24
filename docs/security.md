# VMAN Security Checklist

VMAN is designed as a high-security control plane for SSH-managed VPS targets. Review this checklist before connecting real credentials or exposing the dashboard.

## Browser and API hardening

- Set `VMAN_ENV=production` outside local development.
- Set `VMAN_ALLOWED_ORIGINS` to explicit HTTPS origins only, for example `https://vman.example.com`.
- Do not use `*` for CORS. VMAN rejects wildcard or insecure HTTP origins in production.
- Serve the dashboard only behind HTTPS or a trusted tunnel such as Cloudflare Tunnel.
- Keep session cookies HttpOnly, SameSite=Lax, and Secure in production.
- Mutating API requests must include the `X-CSRF-Token` header matching the `vman_csrf` cookie.
- Set `VMAN_TRUSTED_PROXY_HOPS=1` only when a trusted reverse proxy sanitizes `X-Forwarded-For`; otherwise leave it at `0` so clients cannot spoof rate-limit identity.

## Authentication

- Generate a strong `VMAN_SESSION_SECRET` and never commit it.
- Use a strong owner password; enable TOTP/passkeys when available.
- Login failures are rate-limited by both source IP and username to slow password guessing and distributed spray attempts.
- Revoke old sessions after deployment, recovery, or suspected compromise.

## Credential vault

- Generate `VMAN_MASTER_KEY` with `python scripts/generate-master-key.py`.
- Store the master key only in the production environment file or secret manager.
- Do not include the master key in normal backups unless the backup destination is equally protected.
- Prefer SSH keys over passwords; remove or disable password credentials after bootstrap when practical.

## Backup and restore

- Create encrypted SQLite backups with `vmanctl backup create --output backups/vman.vmanbak`.
- Create encrypted host inventory exports with `vmanctl export hosts --output backups/hosts.vmanexport`; exports include host metadata and credential IDs/fingerprints, but never credential ciphertext or plaintext payloads.
- Validate artifacts with `vmanctl backup inspect backups/vman.vmanbak` before moving them off-host.
- Restore into a new SQLite file with `vmanctl restore database backups/vman.vmanbak --output restored.db`, then point `VMAN_DATABASE_URL` at the restored file after review.
- Backup and restore require the same `VMAN_MASTER_KEY` used by the credential vault. The key fingerprint in backup metadata is only for operator comparison; the key itself is never embedded.
- Store encrypted backup files away from runtime `.env`, session, and deployment secrets. Export the master key separately only through your normal secret-manager or break-glass process.

## Audit and logs

- Sensitive actions must produce audit events.
- Audit metadata and job logs are redacted before persistence.
- Audit events include a SHA-256 hash chain (`previous_hash` and `event_hash`) so tampering can be detected by `AuditService.verify_hash_chain()`.
- Export and review audit logs before and after risky maintenance.
- Treat remote command output as untrusted text; do not paste it into other privileged tools without review.

## Policy and remote execution

- High-risk and critical commands must require approval.
- Production-tagged hosts require stronger approval for medium+ risk tasks.
- Do not pipe unreviewed network scripts into shell in built-in recipes.
- Verify SSH host fingerprints before executing commands.
- Keep target hosts agentless: only SSH and standard shell/coreutils are assumed.

## Release gate

Before a release tag:

- `python -m pytest -q` passes.
- `ruff check backend tests scripts` passes.
- `python -m mypy backend/vman` passes.
- Dependency lockfile is refreshed.
- Security CI is green or exceptions are documented.
- Deployment smoke test reaches `/api/health`.
