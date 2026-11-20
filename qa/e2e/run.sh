#!/usr/bin/env bash
# Golden-path e2e against a NEO console preview. The protection-bypass secret stays out of the
# repo: pass it in NEO_BYPASS (or /tmp/neo_bypass.txt). Usage: ./run.sh <preview-url> [runs]
set -euo pipefail
BASE_URL="${1:?usage: ./run.sh <preview-url> [runs]}"
RUNS="${2:-1}"
: "${NEO_BYPASS:=$(cat /tmp/neo_bypass.txt 2>/dev/null || true)}"
export BASE_URL NEO_BYPASS
mkdir -p screens
for i in $(seq 1 "$RUNS"); do
  echo "=== golden-path run $i/$RUNS against $BASE_URL ==="
  npx playwright test golden_path.spec.ts
done
