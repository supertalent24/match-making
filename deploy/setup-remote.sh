#!/bin/bash
#
# One-time setup for the remote server.
# Run this ON the remote server after cloning / pulling the repo.
#
# Usage:
#   cd /root/match-making
#   bash deploy/setup-remote.sh
#
# What it does:
#   1. Checks Docker is available
#   2. Ensures .env file exists
#   3. Restores DB dump if present
#   4. Builds and starts the full stack via Docker Compose

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "============================================"
echo "  Remote Server Setup"
echo "============================================"
echo ""

# ── 1. Check Docker ─────────────────────────────────────────────────────────

echo "[1/4] Checking Docker..."

if ! command -v docker &> /dev/null; then
    echo "  ERROR: Docker is not installed."
    echo "  Install it: https://docs.docker.com/engine/install/ubuntu/"
    exit 1
fi

docker compose version > /dev/null 2>&1 || {
    echo "  ERROR: Docker Compose plugin not found."
    exit 1
}

echo "       Docker is ready."

# ── 2. Environment file ─────────────────────────────────────────────────────

echo "[2/4] Checking .env file..."

if [ ! -f .env ]; then
    cp env.example .env
    echo ""
    echo "  *** Created .env from env.example ***"
    echo "  *** Edit it now with your production values: ***"
    echo "      nano $PROJECT_DIR/.env"
    echo ""
    echo "  Then re-run this script."
    exit 1
fi

source .env

# ── 3. Start PostgreSQL and restore dump ────────────────────────────────────

echo "[3/4] Starting PostgreSQL..."

docker compose -f docker-compose.prod.yml up -d postgres

echo "       Waiting for PostgreSQL to become healthy..."
until docker exec talent_matching_db pg_isready -U "${POSTGRES_USER:-talent}" -d "${POSTGRES_DB:-talent_matching}" > /dev/null 2>&1; do
    sleep 2
done
echo "       PostgreSQL is ready."

if [ -f db_dump.sql.gz ]; then
    echo "       Restoring database from dump..."
    gunzip -c db_dump.sql.gz | docker exec -i talent_matching_db \
        psql -U "${POSTGRES_USER:-talent}" -d "${POSTGRES_DB:-talent_matching}"
    rm -f db_dump.sql.gz
    echo "       Database restored."
fi

# ── 4. Build and start the full stack ────────────────────────────────────────

echo "[4/4] Building and starting Dagster stack..."

docker compose -f docker-compose.prod.yml up --build -d

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
docker compose -f docker-compose.prod.yml ps
echo ""
echo "  Useful commands:"
echo "    docker compose -f docker-compose.prod.yml logs -f"
echo "    docker compose -f docker-compose.prod.yml ps"
echo ""
echo "  From your local machine:"
echo "    poetry run remote-ui"
echo ""
