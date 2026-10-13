#!/usr/bin/env bash
# run_wsb_scoring.sh - the post-generation closed loop (Phase 7 -> 8):
#   wait for 384 -> strict audit (must be FULL) -> stop generation server
#   -> official PER+SongBench -> MuLan+AllMusicCaps (same PER selection)
#   -> performance baseline -> GPU-arm PER parity -> commit+push evidence
# Every stage logs to $WS/logs/scoring_pipeline.log; aborts loudly on any
# non-FULL verdict so a partial run can never be scored as official.
set -uo pipefail
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNS="${1:?usage: run_wsb_scoring.sh <wsb_full dir>}"
RUNS="$(realpath "$RUNS")"
REPO="$WS/evidence-repo"
BRANCH="validation/gfx1100-rocm7141"
LOG="$WS/logs/scoring_pipeline.log"
MENV="$WS/environments/yue2-gfx1100"
VENV_METRICS="$WS/benchmark/wsb_metrics/.venvs/metrics/bin/python"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

count_complete() {
  python3 - "$RUNS" <<'PY'
import json, sys
from pathlib import Path
m = Path(sys.argv[1]) / "generation_manifest.jsonl"
if not m.is_file(): print(0); raise SystemExit
seen = set()
for line in m.read_text().splitlines():
    r = json.loads(line)
    if r.get("status", "").startswith("complete"): seen.add(r["id"])
print(len(seen))
PY
}

cd "$REPO"
log "pipeline started for $RUNS"

# ---- 1) wait for the driver to finish and 384 to be verified-complete ----
while true; do
  n=$(count_complete)
  if [ "$n" -ge 384 ]; then log "384 complete ($n)"; break; fi
  if ! pgrep -f "run_wsb.py --runs $RUNS" > /dev/null; then
    log "DRIVER EXITED below 384 ($n complete) - NOT scoring; partial evidence preserved"
    bash "$WS/scripts/checkpoint_milestone.sh" "$RUNS" "driver_exit_${n}of384" full >> "$LOG" 2>&1
    exit 1
  fi
  sleep 300
done

# ---- 2) strict audit: verdict must be FULL --------------------------------
source "$MENV/bin/activate"
export YUE2_WORKSPACE="$WS"
if ! python scripts/verify_wsb_artifacts.py --runs "$RUNS" --mode full >> "$LOG" 2>&1; then
  log "STRICT AUDIT NOT FULL - refusing to score officially (audit.json retained)"
  exit 2
fi
log "strict audit: FULL (384/384, 192 prompts, seeds verified)"

# ---- 3) free the GPU: gracefully stop the generation server ---------------
if pgrep -f "sglang serve" > /dev/null; then
  pkill -INT -f "sglang serve" 2>/dev/null || true
  for i in $(seq 1 24); do
    pgrep -f "sglang serve" > /dev/null || break
    sleep 5
  done
  pkill -f "sglang serve" 2>/dev/null || true
  log "generation server stopped (SIGINT, then cleanup)"
fi
sleep 10

# ---- 4) official scoring: PER + SongBench ----------------------------------
cd "$WS/benchmark/wsb_metrics"
log "scoring per,songbench (standard mode) ..."
if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
     python wsb_eval.py score \
       --input "$RUNS/evaluation_inputs.jsonl" \
       --output "$RUNS/scores" --mode standard --metrics per,songbench >> "$LOG" 2>&1; then
  log "PER/SongBench scoring FAILED - see log"
  exit 3
fi
log "per,songbench done"

# ---- 5) MuLan + AllMusicCaps with the same PER-based selection -------------
if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
     python wsb_eval.py score \
       --input "$RUNS/evaluation_inputs.jsonl" \
       --per-results "$RUNS/scores/per_song.jsonl" \
       --output "$RUNS/additional" --metrics mulan,allmusiccaps >> "$LOG" 2>&1; then
  log "mulan/allmusiccaps scoring FAILED - see log"
  exit 4
fi
log "mulan,allmusiccaps done"

# ---- 6) performance baseline + GPU-arm parity ------------------------------
cd "$REPO"
python scripts/collect_performance.py --runs "$RUNS" \
  --server-log "$WS/logs/server_yue2_gfx1100.log" >> "$LOG" 2>&1 || log "perf collect rc=$?"
WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
  "$VENV_METRICS" scripts/per_parity_study.py --runs "$RUNS" --samples 6 >> "$LOG" 2>&1 \
  || log "parity GPU arm rc=$?"

# ---- 7) evidence snapshot + push --------------------------------------------
python3 - "$RUNS" <<'PY' >> "$LOG" 2>&1
import json, sys, pathlib
runs = pathlib.Path(sys.argv[1])
snap = {}
for name in ("scores/summary.json", "additional/summary.json", "scores/per_song.jsonl"):
    p = runs / name
    if p.is_file():
        snap[name] = json.loads(p.read_text()) if name.endswith(".json") else \
            [json.loads(l) for l in p.read_text().splitlines() if l.strip()][:5]
out = pathlib.Path("evidence/gfx1100/scoring_snapshot.json")
out.write_text(json.dumps(snap, indent=1, ensure_ascii=False)[:200000] + "\n")
print("scoring snapshot ->", out)
PY
git add evidence/gfx1100
git commit -qm "feat(gfx1100): official WSB scoring complete (per,songbench,mulan,allmusiccaps) + perf baseline + parity" >> "$LOG" 2>&1
for i in $(seq 1 10); do git push origin "$BRANCH" >/dev/null 2>&1 && break; log "push retry $i"; sleep 20; done
log "PIPELINE COMPLETE"
