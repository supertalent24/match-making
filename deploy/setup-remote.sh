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
#   1. Installs system dependencies (Python 3.13, poetry, Docker)
#   2. Installs project Python dependencies via poetry
#   3. Starts PostgreSQL via Docker Compose
#   4. Restores DB dump if present
#   5. Installs and starts systemd services for dagster-code and dagster-daemon

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "============================================"
echo "  Remote Server Setup"
echo "============================================"
echo ""

# ── 1. System dependencies ──────────────────────────────────────────────────

echo "[1/6] Installing system dependencies..."

apt-get update -qq
apt-get install -y -qq python3.13 python3.13-venv python3.13-dev \
    libpq-dev gcc curl > /dev/null

if ! command -v poetry &> /dev/null; then
    echo "       Installing poetry..."
    curl -sSL https://install.python-poetry.org | python3.13 -
fi

export PATH="/root/.local/bin:$PATH"

poetry config virtualenvs.in-project true

# ── 2. Python dependencies ──────────────────────────────────────────────────

echo "[2/6] Installing Python dependencies..."

poetry install --with llm,parsing --no-interaction

# ── 3. Environment file ─────────────────────────────────────────────────────

echo "[3/6] Checking .env file..."

if [ ! -f .env ]; then
    cp env.example .env
    echo ""
    echo "  *** Created .env from env.example ***"
    echo "  *** Edit it now with your production values: ***"
    echo "      nano /root/match-making/.env"
    echo ""
    echo "  Then re-run this script."
    exit 1
fi

source .env

# ── 4. PostgreSQL ────────────────────────────────────────────────────────────

echo "[4/6] Starting PostgreSQL..."

docker compose -f docker-compose.prod.yml up -d postgres

echo "       Waiting for PostgreSQL to become healthy..."
until docker exec talent_matching_db pg_isready -U "${POSTGRES_USER:-talent}" -d "${POSTGRES_DB:-talent_matching}" > /dev/null 2>&1; do
    sleep 2
done
echo "       PostgreSQL is ready."

# Restore DB dump if present
if [ -f db_dump.sql.gz ]; then
    echo "       Restoring database from dump..."
    gunzip -c db_dump.sql.gz | docker exec -i talent_matching_db \
        psql -U "${POSTGRES_USER:-talent}" -d "${POSTGRES_DB:-talent_matching}"
    rm -f db_dump.sql.gz
    echo "       Database restored."
else
    echo "       Running migrations..."
    poetry run alembic upgrade head
fi

# ── 5. Install systemd services ─────────────────────────────────────────────

echo "[5/6] Installing systemd services..."

cp deploy/dagster-code.service /etc/systemd/system/
cp deploy/dagster-daemon.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable dagster-code dagster-daemon

# ── 6. Start services ───────────────────────────────────────────────────────

echo "[6/6] Starting Dagster services..."

systemctl restart dagster-code
sleep 3
systemctl restart dagster-daemon

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  Services:"
systemctl --no-pager status dagster-code dagster-daemon | grep -E "Active:|●"
echo ""
echo "  Useful commands:"
echo "    systemctl status dagster-code dagster-daemon"
echo "    journalctl -u dagster-code -f"
echo "    journalctl -u dagster-daemon -f"
echo ""
echo "  From your local machine:"
echo "    poetry run remote-ui"
echo ""
