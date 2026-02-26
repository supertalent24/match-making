#!/bin/bash
#
# Run the Dagster dashboard locally while computation happens on a remote server.
#
# Sets up SSH tunnels to the remote PostgreSQL and gRPC code server, then starts
# dagster-webserver on your local machine. The result: a fast, local UI with full
# control over jobs/sensors/schedules that execute on the remote.
#
# Architecture:
#   LOCAL (your machine)                REMOTE (SSH server)
#   ┌──────────────────┐    SSH tunnel  ┌──────────────────────────┐
#   │ dagster-webserver │◄──5432───────►│ PostgreSQL (pgvector)    │
#   │   localhost:3000  │◄──4266───────►│ dagster-code (gRPC)      │
#   └──────────────────┘                │ dagster-daemon           │
#                                       └──────────────────────────┘
#
# Prerequisites:
#   - poetry install (deps are managed via pyproject.toml / poetry.lock)
#   - Remote server set up (bash deploy/setup-remote.sh)
#   - SSH access to the remote server
#   - .env file in the project root with DB credentials matching the remote
#
# Usage:
#   poetry remote-ui                          # uses REMOTE_HOST from .env
#   ./scripts/dagster-remote-ui.sh            # uses REMOTE_HOST from .env
#   ./scripts/dagster-remote-ui.sh user@host  # override

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

REMOTE_HOST="${1:-${REMOTE_HOST:-}}"
if [ -z "$REMOTE_HOST" ]; then
    echo "Error: No remote host specified."
    echo "Set REMOTE_HOST in .env or pass it as an argument."
    echo "Usage: $0 [ssh_user@remote_host]"
    exit 1
fi

WORKSPACE_FILE="$PROJECT_ROOT/docker/workspace-local.yaml"
DAGSTER_YAML="$PROJECT_ROOT/dagster.yaml"

LOCAL_PG_PORT=15432
LOCAL_GRPC_PORT=4266
LOCAL_WEB_PORT=3000

REMOTE_PG_PORT="${POSTGRES_PORT:-5432}"

cleanup() {
    echo ""
    echo "Shutting down..."
    [ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null
    echo "SSH tunnels closed."
}
trap cleanup EXIT INT TERM

echo "============================================"
echo "  Dagster Remote UI"
echo "============================================"
echo ""
echo "  Remote:  $REMOTE_HOST"
echo "  Tunnels: PG $REMOTE_PG_PORT → localhost:$LOCAL_PG_PORT"
echo "           gRPC 4266 → localhost:$LOCAL_GRPC_PORT"
echo "  UI:      http://localhost:$LOCAL_WEB_PORT"
echo ""

# ── Open SSH tunnels ────────────────────────────────────────────────────────

echo "[1/2] Opening SSH tunnels..."

ssh -N -f \
    -L "$LOCAL_PG_PORT:localhost:$REMOTE_PG_PORT" \
    -L "$LOCAL_GRPC_PORT:localhost:4266" \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    "$REMOTE_HOST"

TUNNEL_PID=$(pgrep -f "ssh -N -f.*$REMOTE_HOST" | tail -1)
echo "       Tunnels open (PID: $TUNNEL_PID)"

# ── Start dagster-webserver ─────────────────────────────────────────────────

echo "[2/2] Starting dagster-webserver on http://localhost:$LOCAL_WEB_PORT ..."
echo ""

export POSTGRES_HOST=localhost
export POSTGRES_PORT="$LOCAL_PG_PORT"
export DAGSTER_HOME="$PROJECT_ROOT"

# Dagster's webserver loads .env from CWD with override=True, which
# clobbers our POSTGRES_PORT. Hide the project .env so the webserver
# uses the shell-exported values pointing at the SSH tunnel.
if [ -f "$PROJECT_ROOT/.env" ]; then
    mv "$PROJECT_ROOT/.env" "$PROJECT_ROOT/.env.remote-bak"
fi
trap 'mv "$PROJECT_ROOT/.env.remote-bak" "$PROJECT_ROOT/.env" 2>/dev/null; cleanup' EXIT INT TERM

cd "$PROJECT_ROOT"
poetry run dagster-webserver \
    -h 0.0.0.0 \
    -p "$LOCAL_WEB_PORT" \
    -w "$WORKSPACE_FILE"
