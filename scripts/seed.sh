#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

API_URL="${API_URL:-http://localhost:8000}"
FIXTURES_DIR="$REPO_ROOT/apps/api/tests/fixtures/synthetic"

echo "→ Waiting for API to be ready..."
for i in $(seq 1 30); do
  if curl -sf "$API_URL/health" > /dev/null 2>&1; then
    echo "  API ready."
    break
  fi
  echo "  Attempt $i/30..."
  sleep 2
done

echo "→ Running database migrations..."
(cd apps/api && uv run alembic upgrade head)

echo "→ Seeding vendor master..."
(cd apps/api && uv run python scripts/seed_vendors.py)

echo "→ Generating synthetic invoices..."
(cd apps/api && uv run python scripts/generate_synthetic_invoices.py --output-dir "$FIXTURES_DIR")

echo "→ Processing synthetic invoices through pipeline..."
(cd apps/api && uv run python scripts/seed_invoices.py --fixtures-dir "$FIXTURES_DIR" --api-url "$API_URL")

echo ""
echo "✓ Seed complete. Open $API_URL/../ or http://localhost:3000 to start reviewing."
