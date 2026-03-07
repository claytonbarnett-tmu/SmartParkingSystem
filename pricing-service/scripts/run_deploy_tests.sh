#!/usr/bin/env bash
# ------------------------------------------------------------------
# run_smoke_tests.sh
#
# Build the pricing-service container, start it alongside Postgres,
# seed a test lot, run gRPC smoke tests, then tear everything down.
#
# Usage:  ./scripts/run_smoke_tests.sh
# ------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

cleanup() {
    echo ""
    echo "Tearing down containers…"
    docker compose down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Building and starting services…"
docker compose up -d --build

echo "==> Waiting for pricing service to become healthy…"
MAX_WAIT=60
ELAPSED=0
until docker compose ps pricing --format '{{.Health}}' 2>/dev/null | grep -qi healthy; do
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "ERROR: pricing service did not become healthy within ${MAX_WAIT}s"
        docker compose logs pricing
        exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    printf "  waited %ds…\r" "$ELAPSED"
done
echo "  pricing service healthy after ${ELAPSED}s"

echo "==> Seeding test lot…"
docker compose exec -T pricing python -c "
from pricing.service import initialize_lot
count = initialize_lot(lot_id=1, base_price=5.00)
print(f'Seeded {count} arms for lot 1')
"

echo "==> Running smoke tests…"
echo "==> Running deploy tests…"
if [ -x "${PROJECT_DIR}/../.venv/bin/python" ]; then
    VENV_PY="${PROJECT_DIR}/../.venv/bin/python"
else
    VENV_PY="python"
fi
"$VENV_PY" tests/deploy_test.py

echo "==> Done."
