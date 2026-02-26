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
#   - Remote stack running (docker compose -f docker-compose.prod.yml up -d)
#   - SSH access to the remote server
#   - .env file in the project root with DB credentials matching the remote
#
# Usage:
#   ./scripts/dagster-remote-ui.sh <ssh_user@remote_host>
#
# Example:
#   ./scripts/dagster-remote-ui.sh deploy@192.168.1.100

set -euo pipefail

REMOTE_HOST="${1:?Usage: $0 <ssh_user@remote_host>}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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

cd "$PROJECT_ROOT"
poetry run dagster-webserver \
    -h 0.0.0.0 \
    -p "$LOCAL_WEB_PORT" \
    -w "$WORKSPACE_FILE"
