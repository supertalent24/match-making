#!/bin/bash
#
# Migrate the full Dagster talent-matching stack (app + PostgreSQL data)
# from the local Docker environment to a remote SSH server.
#
# Prerequisites:
#   - Local docker-compose dev stack is running (talent_matching_db container)
#   - Remote server has Docker & Docker Compose installed
#   - SSH access to the remote server
#
# Usage:
#   ./scripts/migrate-to-remote.sh <ssh_user@remote_host> [remote_project_dir]
#   ./scripts/migrate-to-remote.sh --resume <ssh_user@remote_host> [remote_project_dir]
#
# Options:
#   --resume   Skip dump and upload (steps 1-3), go straight to DB restore
#              and stack startup. Use when files are already on the remote.
#
# Example:
#   ./scripts/migrate-to-remote.sh deploy@192.168.1.100
#   ./scripts/migrate-to-remote.sh --resume deploy@myserver.com /opt/talent-matching

set -euo pipefail

RESUME=false
if [ "${1:-}" = "--resume" ]; then
    RESUME=true
    shift
fi

REMOTE_HOST="${1:?Usage: $0 [--resume] <ssh_user@remote_host> [remote_project_dir]}"
REMOTE_DIR="${2:-/opt/talent-matching}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_CONTAINER="talent_matching_db"
DUMP_FILE="$PROJECT_ROOT/db_dump.sql.gz"

DB_USER="${POSTGRES_USER:-talent}"
DB_NAME="${POSTGRES_DB:-talent_matching}"

echo "============================================"
echo "  Talent Matching - Remote Migration"
echo "============================================"
echo ""
echo "  Source:  local Docker ($DB_CONTAINER)"
echo "  Target:  $REMOTE_HOST:$REMOTE_DIR"
echo "  DB:      $DB_NAME (user: $DB_USER)"
if $RESUME; then
echo "  Mode:    RESUME (skipping dump & upload)"
fi
echo ""

if $RESUME; then
    echo "[1/5] Skipped (--resume)"
    echo "[2/5] Skipped (--resume)"
    echo "[3/5] Skipped (--resume)"
else

# ── Step 1: Dump the local PostgreSQL database ──────────────────────────────

echo "[1/5] Dumping local PostgreSQL database..."

docker exec "$DB_CONTAINER" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
  | gzip > "$DUMP_FILE"

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "       Dump created: $DUMP_FILE ($DUMP_SIZE)"

# ── Step 2: Create remote project directory ─────────────────────────────────

echo "[2/5] Preparing remote directory ($REMOTE_DIR)..."

ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"

# ── Step 3: Transfer project files and DB dump ──────────────────────────────

echo "[3/5] Transferring project files to remote server..."

rsync -avz --progress \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.dagster' \
  --exclude 'storage' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '.env' \
  --exclude 'node_modules' \
  --exclude 'db_dump.sql.gz' \
  --exclude '.mypy_cache' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  "$PROJECT_ROOT/" "$REMOTE_HOST:$REMOTE_DIR/"

echo "       Transferring database dump..."
scp "$DUMP_FILE" "$REMOTE_HOST:$REMOTE_DIR/db_dump.sql.gz"

fi

# ── Step 4: Set up and restore on remote ────────────────────────────────────

echo "[4/5] Setting up database and restoring data on remote..."

ssh "$REMOTE_HOST" bash <<REMOTE_SCRIPT
set -euo pipefail
cd "$REMOTE_DIR"

if [ ! -f .env ]; then
  echo ""
  echo "WARNING: No .env file found at $REMOTE_DIR/.env"
  echo "Copy env.example and fill in your production values:"
  echo "  cp env.example .env && nano .env"
  echo ""
  echo "Then re-run with: $0 --resume $REMOTE_HOST $REMOTE_DIR"
  echo ""
  exit 1
fi

docker compose -f docker-compose.prod.yml up -d postgres
echo "       Waiting for PostgreSQL to become healthy..."
until docker exec $DB_CONTAINER pg_isready -U $DB_USER -d $DB_NAME > /dev/null 2>&1; do
  sleep 2
done
echo "       PostgreSQL is ready."

echo "       Restoring database from dump..."
gunzip -c db_dump.sql.gz | docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME

echo "       Database restored successfully."

rm -f db_dump.sql.gz
REMOTE_SCRIPT

# ── Step 5: Start the full stack on remote ──────────────────────────────────

echo "[5/5] Starting full Dagster stack on remote..."

ssh "$REMOTE_HOST" bash <<REMOTE_SCRIPT
set -euo pipefail
cd "$REMOTE_DIR"
docker compose -f docker-compose.prod.yml up --build -d
echo ""
echo "Services started. Checking status..."
docker compose -f docker-compose.prod.yml ps
REMOTE_SCRIPT

# ── Cleanup local dump ──────────────────────────────────────────────────────

rm -f "$DUMP_FILE"

echo ""
echo "============================================"
echo "  Migration complete!"
echo "============================================"
echo ""
echo "  Connect with:  ./scripts/dagster-remote-ui.sh $REMOTE_HOST"
echo ""
echo "  Useful commands on the remote server:"
echo "    ssh $REMOTE_HOST"
echo "    cd $REMOTE_DIR"
echo "    docker compose -f docker-compose.prod.yml logs -f"
echo "    docker compose -f docker-compose.prod.yml ps"
echo ""
