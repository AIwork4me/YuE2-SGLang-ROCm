#!/usr/bin/env bash
# watch_milestones.sh - poll a running WSB run and fire the milestone pipeline
# at 10/50/100/192/300/384 verified-complete candidates.
# Usage: watch_milestones.sh <run_dir> [mode]
set -uo pipefail
RUNS="$(realpath "$1")"
MODE="${2:-full}"
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MILESTONES="10 50 100 192 300 384"
FIRED=""

count_complete() {
  python3 - "$RUNS" <<'PY'
import json, sys
from pathlib import Path
m = Path(sys.argv[1]) / "generation_manifest.jsonl"
if not m.is_file():
    print(0); raise SystemExit
seen = {}
for line in m.read_text().splitlines():
    r = json.loads(line)
    if r.get("status", "").startswith("complete"):
        seen[r["id"]] = r  # last record wins (resume-safe)
print(len(seen))
PY
}

while true; do
  n=$(count_complete)
  for th in $MILESTONES; do
    if [ "$n" -ge "$th" ] && ! [[ " $FIRED " == *" m$th "* ]]; then
      echo "[watch] milestone $th reached ($n complete) $(date -u +%T)"
      bash "$WS/scripts/checkpoint_milestone.sh" "$RUNS" "m${th}" "$MODE" \
        >> "$WS/logs/milestones.log" 2>&1 || echo "[watch] milestone $th pipeline rc=$?"
      FIRED="$FIRED m$th"
    fi
  done
  if [ "$n" -ge 384 ]; then
    echo "[watch] full run reached 384; exiting"
    break
  fi
  if ! pgrep -f "run_wsb.py --runs $RUNS" > /dev/null; then
    # driver exited; fire a final checkpoint if below 384 and not already done
    if [ "$n" -lt 384 ]; then
      echo "[watch] driver exited at $n complete; final partial checkpoint"
      bash "$WS/scripts/checkpoint_milestone.sh" "$RUNS" "final_partial_$(date -u +%H%M)" "$MODE" \
        >> "$WS/logs/milestones.log" 2>&1 || true
    fi
    break
  fi
  sleep 120
done
