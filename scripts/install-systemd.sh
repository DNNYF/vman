#!/usr/bin/env bash
set -euo pipefail

# Install VMAN systemd services.
#
# The script is intentionally idempotent and configurable so operators can run
# it on a VPS, while tests can exercise it in a temporary directory:
#
#   VMAN_SYSTEMD_DIR=/tmp/systemd \
#   VMAN_CONFIG_DIR=/tmp/etc-vman \
#   VMAN_VARLIB_DIR=/tmp/lib-vman \
#   VMAN_SKIP_SYSTEMCTL=1 \
#   bash scripts/install-systemd.sh

REPO_ROOT="${VMAN_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SYSTEMD_DIR="${VMAN_SYSTEMD_DIR:-/etc/systemd/system}"
VMCONF_DIR="${VMAN_CONFIG_DIR:-/etc/vman}"
VARLIB_DIR="${VMAN_VARLIB_DIR:-/var/lib/vman}"
ENV_FILE="${VMAN_ENV_FILE:-${VMCONF_DIR}/vman.env}"
API_SERVICE="${SYSTEMD_DIR}/vman-api.service"
WORKER_SERVICE="${SYSTEMD_DIR}/vman-worker.service"
SKIP_SYSTEMCTL="${VMAN_SKIP_SYSTEMCTL:-0}"
START_SERVICES="${VMAN_START_SERVICES:-1}"
HEALTH_URL="${VMAN_HEALTH_URL:-http://127.0.0.1:8765/api/health}"

log() { printf '[vman-install] %s\n' "$*"; }
fatal() { printf '[vman-install] ERROR: %s\n' "$*" >&2; exit 1; }

require_file() {
    local path="$1"
    [[ -f "${path}" ]] || fatal "required file not found: ${path}"
}

write_file_if_changed() {
    local path="$1"
    local tmp
    tmp="$(mktemp)"
    cat > "${tmp}"
    if [[ -f "${path}" ]] && cmp -s "${tmp}" "${path}"; then
        rm -f "${tmp}"
        log "unchanged: ${path}"
        return 0
    fi
    install -m 0644 "${tmp}" "${path}"
    rm -f "${tmp}"
    log "wrote: ${path}"
}

cd "${REPO_ROOT}" || fatal "cannot cd to ${REPO_ROOT}"
require_file "${REPO_ROOT}/.env.example"

install -d -m 0755 "${SYSTEMD_DIR}"
install -d -m 0750 "${VMCONF_DIR}" "${VARLIB_DIR}" "${REPO_ROOT}/data"

if [[ ! -f "${ENV_FILE}" ]]; then
    install -m 0600 "${REPO_ROOT}/.env.example" "${ENV_FILE}"
    # Production-safe defaults for systemd installs. Operators must replace the
    # secret placeholders before using the service for real target credentials.
    python3 - "${ENV_FILE}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
replacements = {
    "VMAN_ENV=development": "VMAN_ENV=production",
    "VMAN_DATABASE_URL=sqlite:///./data/vman.db": "VMAN_DATABASE_URL=sqlite:////var/lib/vman/vman.db",
    "VMAN_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173": "VMAN_ALLOWED_ORIGINS=https://vman.example.com",
    "VMAN_MASTER_KEY=replace-with-32-byte-urlsafe-base64-key": "VMAN_MASTER_KEY=CHANGEME-GENERATE-WITH-python-scripts-generate-master-key-py",
    "VMAN_SESSION_SECRET=replace-with-long-random-secret": "VMAN_SESSION_SECRET=CHANGEME-GENERATE-WITH-python-secrets-token-urlsafe-64",
}
for old, new in replacements.items():
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
PY
    chmod 0600 "${ENV_FILE}"
    log "created env template: ${ENV_FILE}"
else
    chmod 0600 "${ENV_FILE}"
    log "env file exists, left contents unchanged: ${ENV_FILE}"
fi

if id -u vman >/dev/null 2>&1; then
    SERVICE_USER="vman"
    SERVICE_GROUP="vman"
elif id -u www-data >/dev/null 2>&1; then
    SERVICE_USER="www-data"
    SERVICE_GROUP="www-data"
else
    SERVICE_USER="nobody"
    SERVICE_GROUP="nogroup"
fi

if [[ -x "${REPO_ROOT}/.venv/bin/vman-api" && -x "${REPO_ROOT}/.venv/bin/vman-worker" ]]; then
    API_EXEC="${REPO_ROOT}/.venv/bin/vman-api"
    WORKER_EXEC="${REPO_ROOT}/.venv/bin/vman-worker"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    API_EXEC="${REPO_ROOT}/.venv/bin/python -m uvicorn vman.main:app --host 127.0.0.1 --port 8765"
    WORKER_EXEC="${REPO_ROOT}/.venv/bin/python -m vman.worker"
else
    API_EXEC="/usr/bin/env python3 -m uvicorn vman.main:app --host 127.0.0.1 --port 8765"
    WORKER_EXEC="/usr/bin/env python3 -m vman.worker"
fi

write_file_if_changed "${API_SERVICE}" <<EOF
[Unit]
Description=VMAN API service
Documentation=https://github.com/alamakmak/vman
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${REPO_ROOT}
ExecStart=${API_EXEC}
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${VARLIB_DIR} ${REPO_ROOT}/data

[Install]
WantedBy=multi-user.target
EOF

write_file_if_changed "${WORKER_SERVICE}" <<EOF
[Unit]
Description=VMAN worker service
Documentation=https://github.com/alamakmak/vman
After=network-online.target vman-api.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${REPO_ROOT}
ExecStart=${WORKER_EXEC}
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${VARLIB_DIR} ${REPO_ROOT}/data

[Install]
WantedBy=multi-user.target
EOF

if [[ "${SKIP_SYSTEMCTL}" == "1" ]]; then
    log "VMAN_SKIP_SYSTEMCTL=1; not running systemctl"
else
    systemctl daemon-reload
    systemctl enable vman-api.service vman-worker.service
    if [[ "${START_SERVICES}" == "1" ]]; then
        systemctl restart vman-api.service vman-worker.service
        log "services started"
        log "health check: curl -fsS ${HEALTH_URL}"
    else
        log "VMAN_START_SERVICES=0; services enabled but not started"
    fi
fi

log "installation complete"
log "status: systemctl status vman-api vman-worker --no-pager"
log "health: curl -fsS ${HEALTH_URL}"
log "edit ${ENV_FILE}, then restart: systemctl restart vman-api vman-worker"
