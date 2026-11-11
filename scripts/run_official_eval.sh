#!/usr/bin/env bash
# Official WildSongBench scoring for a COMPLETE (384/384 verified) run.
#
# Executes the frozen evaluator exactly per the dataset README, with the
# disclosed ROCm portability patches (0006/0007) active via
# WSB_ROCM_TORCH_OVERRIDE=1. Scoring formulas and selection are untouched.
#
# Issue B hardening (publication-readiness mission):
#   * no machine-specific default paths: the workspace resolves through the
#     single contract (scripts/yue2_workspace.py): $YUE2_WORKSPACE, repo
#     root, historical layout — in that order.
#   * the run directory is canonicalized to an absolute path BEFORE any cd.
#   * the evaluator venv is discovered (override with YUE2_EVAL_VENV);
#     both historical names (yue2, yue2-gfx1100) are probed.
#   * the evaluator tree location is probed (tarball extraction layouts).
#
# Usage: [YUE2_WORKSPACE=...] bash scripts/run_official_eval.sh <runs-dir>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WS="$(python3 "$SCRIPT_DIR/yue2_workspace.py" 2>/dev/null || true)"
if [ -z "${WS}" ] && [ -n "${YUE2_WORKSPACE:-}" ]; then WS="${YUE2_WORKSPACE}"; fi
if [ -z "${WS}" ]; then
  echo "FATAL: cannot resolve the YuE2 workspace (set YUE2_WORKSPACE or see scripts/yue2_workspace.py)" >&2
  exit 2
fi
WS="$(cd "${WS}" && pwd)"

RUNS_ARG="${1:?usage: run_official_eval.sh <runs-dir>}"
RUNS="$(cd "${RUNS_ARG}" && pwd)"   # canonical absolute path BEFORE any cd

if [ -n "${YUE2_EVAL_VENV:-}" ]; then
  VENV="${YUE2_EVAL_VENV}"
else
  VENV=""
  for cand in "$WS/environments/yue2-gfx1100" "$WS/environments/yue2"; do
    [ -x "$cand/bin/python" ] && VENV="$cand" && break
  done
fi
if [ -z "${VENV}" ] || [ ! -x "$VENV/bin/python" ]; then
  echo "FATAL: no evaluator venv found (looked in $WS/environments/{yue2-gfx1100,yue2}; override with YUE2_EVAL_VENV)" >&2
  exit 2
fi

WSB="$WS/benchmark/WildSongBench"
WSB_EVAL="$WSB/wsb_metrics"
[ -f "$WSB_EVAL/wsb_eval.py" ] || WSB_EVAL="$WSB/evaluation/wsb_metrics"
if [ ! -f "$WSB_EVAL/wsb_eval.py" ]; then
  echo "FATAL: frozen evaluator not found under $WSB (probed wsb_metrics and evaluation/wsb_metrics)" >&2
  exit 2
fi

echo "workspace: $WS"
echo "evaluator venv: $VENV"
echo "evaluator tree: $WSB_EVAL"
echo "run (canonical): $RUNS"

# Gate: refuse to score anything but a FULL-verified run (standard mode
# demands all 384 anyway; this gives a clearer failure up front).
"$VENV/bin/python" "$SCRIPT_DIR/verify_wsb_artifacts.py" --runs "$RUNS" --mode full

source "$VENV/bin/activate"
export WSB_ROCM_TORCH_OVERRIDE=1
cd "$WSB_EVAL/.."   # evaluator is invoked from its parent (README layout)

python "$WSB_EVAL/wsb_eval.py" score \
  --input "$RUNS/evaluation_inputs.jsonl" \
  --output "$RUNS/scores" \
  --mode standard --metrics per,songbench

python "$WSB_EVAL/wsb_eval.py" score \
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
