# Built-in recipes

VMAN ships built-in YAML recipes under `backend/vman/recipes/builtin`.
Each recipe follows the Task 13 recipe schema (`schema_version: 1`) and
contains preflight, steps, verify, and policy metadata. High-risk recipes
set `policy.requires_approval: true`.

## Pack added in Task 24

- `small-vps-cleanup`
- `install-docker`
- `install-caddy`
- `install-nginx`
- `install-nodejs`
- `install-python-uv`
- `install-cloudflare-tunnel`
- `install-9router`
- `install-openwebui`
- `install-open-terminal`
- `basic-hardening`
- `create-sudo-user`
- `setup-ssh-key`
- `disable-password-login`
- `change-ssh-port`
- `setup-ufw`
- `add-swap`
- `set-timezone`
- `setup-fail2ban`
- `unattended-upgrades`
- `reboot-safely`
- `check-failed-services`
- `disk-usage`
- `journal-cleanup`
- `ssl-cert-check`

## Safety notes

- Review high-risk recipes before approval, especially SSH access changes and reboots.
- Recipes are designed for Debian/Ubuntu targets unless noted in their YAML metadata.
- Variables are rendered by the VMAN recipe engine using safe token substitution.
- Keep provider firewalls and out-of-band console access in mind before changing SSH ports or disabling password login.
