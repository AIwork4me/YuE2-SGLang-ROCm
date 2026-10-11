#!/usr/bin/env bash
# Official WildSongBench scoring for a COMPLETE (384/384 verified) run.
#
# Executes the frozen evaluator exactly per the dataset README, with the
# disclosed ROCm portability patches (0006/0007) active via
# WSB_ROCM_TORCH_OVERRIDE=1. Scoring formulas and selection are untouched.
#
# Usage: WS=... bash run_official_eval.sh runs/wsb_full
set -euo pipefail
WS="${WS:-/home/amd/Desktop/YuE2}"
RUNS="${1:?usage: run_official_eval.sh <runs-dir>}"
VENV="$WS/environments/yue2"

# Gate: refuse to score anything but a FULL-verified run (standard mode
# demands all 384 anyway; this gives a clearer failure up front).
"$VENV/bin/python" "$WS/scripts/verify_wsb_artifacts.py" --runs "$RUNS" --mode full

source "$VENV/bin/activate"
export WSB_ROCM_TORCH_OVERRIDE=1
cd "$WS/benchmark/WildSongBench"

python wsb_metrics/wsb_eval.py score \
  --input "$RUNS/evaluation_inputs.jsonl" \
  --output "$RUNS/scores" \
  --mode standard --metrics per,songbench

python wsb_metrics/wsb_eval.py score \
  --input "$RUNS/evaluation_inputs.jsonl" \
  --per-results "$RUNS/scores/per_song.jsonl" \
  --output "$RUNS/additional" \
  --metrics mulan,allmusiccaps

echo "selected means:"
python - "$RUNS/scores/summary.json" "$RUNS/additional/summary.json" <<'PY'
import json, sys
for path in sys.argv[1:]:
    d = json.load(open(path))
    g = d.get("standard_selected", {}).get("groups", {}).get("all", {})
    print(path)
    for metric, value in g.items():
        if isinstance(value, dict):
            print(f"  {metric}: {value.get('means') or {k: v for k, v in value.items() if not isinstance(v, (dict, list))}}")
PY
