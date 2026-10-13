#!/usr/bin/env bash
# run_wsb_scoring_v2.sh - safe post-generation scoring pipeline (v2).
#
# Replaces run_wsb_scoring.sh (v1). v1 hazards fixed here:
#   H1 broad `pkill -f "sglang serve"`            -> run-owned identity receipt
#      + verified exact-PID SIGINT/SIGTERM (scripts/server_identity.py);
#      never pkill/killall/fuser -k; never SIGKILL; BLOCKED state on refusal.
#   H2 unconditional "PIPELINE COMPLETE" after    -> explicit state machine;
#      failed pushes                                 remote SHA verified via
#      ls-remote before EVIDENCE_REMOTE_VERIFIED /
#      PIPELINE_COMPLETE; push failure => LOCAL_COMPLETE_REMOTE_PENDING.
#   H3 no duplicate-pipeline protection           -> pid-verified lockdir;
#      completed stages skipped on resume; official completeness flags
#      (summary.complete + full_192_*_coverage) gate the skips.
#   H4 no in-flight request check before stop     -> driver-exit wait + port
#      drain (require-idle) before any signal.
#   H5 v1 scheduler could still be alive at 384   -> hard refusal (exit 9)
#      if any run_wsb_scoring.sh (v1) process is detected at the boundary.
#   H6 snapshot/commit failures were silent       -> snapshot generation and
#      git add are fatal; branch asserted before commit.
# This scheduler NEVER generates candidates and NEVER rewrites run config.
set -uo pipefail
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNS="${1:?usage: run_wsb_scoring_v2.sh <wsb_full dir>}"
[ -d "$RUNS" ] || { echo "FATAL: run dir not found: $RUNS" >&2; exit 1; }
RUNS="$(realpath "$RUNS")"
RUN_ID="$(python3 -c "import json;print(json.load(open('$RUNS/run_config.json'))['run_id'])" 2>/dev/null || echo unknown)"
STATE_DIR="$RUNS/run-state"           # sidecar metadata; NOT in frozen config
RECEIPT="$STATE_DIR/server-identity.json"
STATE_FILE="$STATE_DIR/scoring_v2_state.json"
LOCKDIR="$STATE_DIR/scoring_v2.lock"
LOG="$WS/logs/scoring_pipeline.log"
BRANCH="validation/gfx1100-rocm7141"
REPO="$WS/evidence-repo"
MENV="$WS/environments/yue2-gfx1100"
VENV_METRICS="$WS/benchmark/wsb_metrics/.venvs/metrics/bin/python"
MODEL_PATH="$WS/models/YuE2-3B"
PORT=31000
IDTOOL="$WS/scripts/server_identity.py"
STAGECHK="$WS/scripts/scoring_stage_check.py"

log() { echo "[$(date -u +%FT%TZ)] [v2] $*" | tee -a "$LOG"; }
state() { # state <NAME> -> persist; log transition only if write succeeded
  if python3 - "$STATE_FILE" "$1" "$RUN_ID" <<'STPY'
import json, sys, time, pathlib
p, name, rid = sys.argv[1:4]
d = {"state": name, "run_id": rid,
     "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
pathlib.Path(p).write_text(json.dumps(d, indent=1) + "\n")
STPY
  then log "STATE: $1"
  else log "WARN: state-file write failed (transition: $1)"
  fi
}
die() { log "FATAL: $1"; exit "${2:-1}"; }

# ---- 0) single-instance lock (pid-verified, stale-safe, race-hardened) ------
mkdir -p "$STATE_DIR"
LOCK_ACQUIRED=0
for ATTEMPT in 1 2 3 4 5; do
  if mkdir "$LOCKDIR" 2>/dev/null; then LOCK_ACQUIRED=1; break; fi
  OLD=$(cat "$LOCKDIR/pid" 2>/dev/null || true)
  if [ -n "$OLD" ] && [ -d "/proc/$OLD" ]; then
    die "another scoring_v2 scheduler alive (pid $OLD) - refusing duplicate pipeline" 6
  fi
  log "stale lock (pid ${OLD:-none} not alive) - reclaiming (attempt $ATTEMPT)"
  # move aside atomically, then remove; never blind rm -rf of a live lock
  STALE_ASIDE="$LOCKDIR.stale.$$.$ATTEMPT"
  mv "$LOCKDIR" "$STALE_ASIDE" 2>/dev/null || true
  rm -rf "$STALE_ASIDE" 2>/dev/null || true
  sleep 2
done
[ "$LOCK_ACQUIRED" = 1 ] || die "cannot acquire lock after retries" 6
echo $$ > "$LOCKDIR/pid"
trap 'log "scheduler exiting"; rm -rf "$LOCKDIR"' EXIT

already_done() { [ -f "$STATE_FILE" ] && grep -q "\"$1\"" "$STATE_FILE" 2>/dev/null; }

count_complete() {
  python3 - "$RUNS" <<'CNTpy'
import json, sys
from pathlib import Path
m = Path(sys.argv[1]) / "generation_manifest.jsonl"
if not m.is_file(): print(0); raise SystemExit
seen = set()
for line in m.read_text().splitlines():
    try:
        r = json.loads(line)
    except ValueError:
        continue  # tolerate partial trailing write while driver appends
    if r.get("status", "").startswith("complete"): seen.add(r["id"])
print(len(seen))
CNTpy
}

# idempotent resume: fully complete pipeline for this run -> exit 0
if already_done PIPELINE_COMPLETE; then
  log "PIPELINE_COMPLETE already recorded for run $RUN_ID - nothing to do"
  exit 0
fi

cd "$REPO" || die "evidence repo missing" 1
state WAITING_FOR_384

# ---- 1) wait for 384 verified-complete --------------------------------------
while true; do
  n=$(count_complete)
  [ "$n" -ge 384 ] && { log "384 complete ($n)"; break; }
  if ! pgrep -f "run_wsb.py --runs $RUNS" > /dev/null; then
    log "DRIVER EXITED below 384 ($n complete) - NOT scoring; partial evidence preserved"
    bash "$WS/scripts/checkpoint_milestone.sh" "$RUNS" "driver_exit_${n}of384" full >> "$LOG" 2>&1
    exit 1
  fi
  sleep 300
done

# ---- 1a) H5: refuse if the unsafe v1 scheduler is still alive ---------------
if V1PIDS=$(pgrep -f "run_wsb_scoring\\.sh" 2>/dev/null) && [ -n "$V1PIDS" ]; then
  die "v1 scheduler still alive (pid(s): $(echo $V1PIDS | tr '\n' ' ')) - it contains unsafe broad pkill at its stage 3; stop it via its exact PID before this pipeline may proceed. NOT proceeding." 9
fi

# ---- 1b) let the driver exit naturally (finalizers, summaries) --------------
log "waiting for generation driver to exit (max 1800s)..."
D_WAIT=0
while pgrep -f "run_wsb.py --runs $RUNS" > /dev/null; do
  [ "$D_WAIT" -ge 1800 ] && { log "driver still alive after 1800s - proceeding to audit"; break; }
  sleep 30; D_WAIT=$((D_WAIT+30))
done
[ "$D_WAIT" -lt 1800 ] && log "driver exited cleanly after ${D_WAIT}s"

# match v1 execution environment for everything below
source "$MENV/bin/activate" 2>/dev/null || die "cannot activate $MENV" 1
export YUE2_WORKSPACE="$WS"

# ---- 2) capture run-owned server identity (server MUST still be alive) ------
if [ ! -f "$RECEIPT" ]; then
  if ! python3 "$IDTOOL" capture --run-state "$STATE_DIR" --model "$MODEL_PATH" \
        --host 127.0.0.1 --port "$PORT" >> "$LOG" 2>&1; then
    die "server identity capture FAILED - will NOT signal or score; inspect $LOG" 4
  fi
else
  log "existing identity receipt found: $RECEIPT"
fi

# ---- 3) strict audit: verdict must be FULL ----------------------------------
if [ ! -f "$RUNS/audit.json" ] || ! python3 -c "
import json;a=json.load(open('$RUNS/audit.json'));raise SystemExit(0 if a.get('verdict')=='FULL' and a.get('verified_complete')==384 else 1)" 2>/dev/null; then
  if ! python scripts/verify_wsb_artifacts.py --runs "$RUNS" --mode full >> "$LOG" 2>&1; then
    log "STRICT AUDIT NOT FULL - refusing to score officially (audit.json retained)"
    exit 2
  fi
else
  log "strict audit already FULL (audit.json) - reusing"
fi
state STRICT_AUDIT_PASS

# ---- 4) stop the generation server (verified identity only) -----------------
if python3 - "$RECEIPT" <<'RCPTpy'
import json, sys, pathlib
r = json.loads(pathlib.Path(sys.argv[1]).read_text())
raise SystemExit(0 if pathlib.Path(f"/proc/{r['pid']}").is_dir() else 1)
RCPTpy
then
  # bounded drain of in-flight requests before signaling
  for i in $(seq 1 60); do
    EST=$(python3 - "$PORT" <<'ESTpy'
import sys
p, n = hex(int(sys.argv[1]))[2:].upper().zfill(4), 0
for f in ('/proc/net/tcp','/proc/net/tcp6'):
    try: lines = open(f).read().splitlines()[1:]
    except FileNotFoundError: continue
    for l in lines:
        parts = l.split()
        if len(parts) < 4: continue
        if (parts[1].endswith(':'+p) or parts[2].endswith(':'+p)) and parts[3]=='01':
            n += 1
print(n)
ESTpy
)
    [ "$EST" -eq 0 ] && { log "port $PORT idle (no ESTABLISHED conns)"; break; }
    [ "$i" -eq 60 ] && log "WARN: $EST conns still on port $PORT after 600s"
    sleep 10
  done
  if python3 "$IDTOOL" stop --receipt "$RECEIPT" --require-idle --timeout 120 >> "$LOG" 2>&1; then
    state GENERATION_SERVER_STOPPED
  else
    RC=$?
    case "$RC" in
      5) die "BLOCKED: verified server survived SIGINT+SIGTERM; GPU unsafe; NOT scoring" 5 ;;
      6) die "BLOCKED: requests still in flight on port $PORT; NOT scoring" 6 ;;
      *) die "server identity verification failed (rc=$RC) - NOT signaling, NOT scoring" "$RC" ;;
    esac
  fi
else
  log "receipt pid not alive (server already stopped) - nothing to stop"
  state GENERATION_SERVER_STOPPED
fi
sleep 5

# ---- 5) official scoring: PER + SongBench (skip only if OFFICIALLY complete) -
SKIP_PER=0
if python3 "$STAGECHK" per "$RUNS" 2>/dev/null; then
  SKIP_PER=1
  N_PER=$(python3 "$STAGECHK" per_song_rows "$RUNS")
fi
if [ "$SKIP_PER" = 1 ]; then
  log "PER+SongBench officially complete (complete=true, full_192_standard_candidate_coverage=true, ${N_PER} rows) - skipping (no duplicate scoring)"
else
  cd "$WS/benchmark/wsb_metrics"
  log "scoring per,songbench (standard mode) ..."
  if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
       python wsb_eval.py score \
         --input "$RUNS/evaluation_inputs.jsonl" \
         --output "$RUNS/scores" --mode standard --metrics per,songbench >> "$LOG" 2>&1; then
    log "PER/SongBench scoring FAILED - see log"; exit 3
  fi
fi
state PER_SONGBENCH_COMPLETE

# ---- 6) MuLan + AllMusicCaps with the SAME official PER-based selection -----
SKIP_ADD=0
if python3 "$STAGECHK" additional "$RUNS" 2>/dev/null; then SKIP_ADD=1; fi
if [ "$SKIP_ADD" = 1 ]; then
  log "MuLan+AllMusicCaps officially complete (complete=true, full_192_selected_coverage=true) - skipping (no duplicate scoring)"
else
  cd "$WS/benchmark/wsb_metrics"
  if ! WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
       python wsb_eval.py score \
         --input "$RUNS/evaluation_inputs.jsonl" \
         --per-results "$RUNS/scores/per_song.jsonl" \
         --output "$RUNS/additional" --metrics mulan,allmusiccaps >> "$LOG" 2>&1; then
    log "mulan/allmusiccaps scoring FAILED - see log"; exit 4
  fi
fi
state MULAN_ALLMUSICCAPS_COMPLETE

# ---- 7) performance baseline + GPU-arm parity (non-fatal) -------------------
cd "$REPO"
python scripts/collect_performance.py --runs "$RUNS" \
  --server-log "$WS/logs/server_yue2_gfx1100.log" >> "$LOG" 2>&1 || log "perf collect rc=$?"
WSB_ROCM_TORCH_OVERRIDE=1 YUE2_WORKSPACE="$WS" HF_HOME="$WS/.cache/huggingface" \
  "$VENV_METRICS" scripts/per_parity_study.py --runs "$RUNS" --samples 6 >> "$LOG" 2>&1 \
  || log "parity GPU arm rc=$?"

# ---- 8) evidence snapshot + local commit (failures are fatal: H6) -----------
SNAP_FILE="evidence/gfx1100/scoring_snapshot.json"
python3 - "$RUNS" <<'SNAPpy' >> "$LOG" 2>&1 || die "evidence snapshot generation FAILED - refusing to commit/push incomplete evidence" 8
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
SNAPpy
[ -s "$SNAP_FILE" ] || die "snapshot $SNAP_FILE missing/empty after generation" 8
# assert we commit to the evidence branch, not whatever happens to be checked out
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CUR_BRANCH" != "$BRANCH" ]; then
  if [ -z "$(git status --porcelain)" ]; then
    log "evidence repo on '$CUR_BRANCH' (clean) - switching to $BRANCH"
    git checkout -q "$BRANCH" >> "$LOG" 2>&1 || die "cannot checkout $BRANCH in evidence repo" 8
  else
    die "evidence repo on '$CUR_BRANCH' with local changes - refusing to commit to wrong branch; resolve manually" 8
  fi
fi
# fast-forward to remote first: milestone checkpoints may have advanced it
git fetch -q origin "$BRANCH" >> "$LOG" 2>&1 || die "cannot fetch origin/$BRANCH" 8
git pull --ff-only origin "$BRANCH" >> "$LOG" 2>&1 \
  || die "evidence branch $BRANCH cannot fast-forward to origin (diverged?); resolve manually" 8
git add evidence/gfx1100 >> "$LOG" 2>&1 || die "git add evidence/gfx1100 failed" 8
if git diff --cached --quiet; then
  log "nothing new to commit (idempotent re-run)"
else
  git commit -qm "feat(gfx1100): official WSB scoring complete (per,songbench,mulan,allmusiccaps) + perf baseline + parity" >> "$LOG" 2>&1 \
    || die "evidence commit failed" 8
fi
LOCAL_SHA=$(git rev-parse HEAD) || die "cannot resolve local HEAD" 8
log "local evidence commit: $LOCAL_SHA"
state EVIDENCE_LOCAL_COMMITTED

# ---- 9) push + VERIFY remote SHA before claiming completion -----------------
if LOG="$LOG" bash "$WS/scripts/push_verify.sh" "$BRANCH"; then
  state EVIDENCE_REMOTE_VERIFIED
  state PIPELINE_COMPLETE
  log "PIPELINE COMPLETE (all mandatory stages succeeded and remote verified)"
  exit 0
else
  state LOCAL_COMPLETE_REMOTE_PENDING
  die "push/verify incomplete - re-run this script to retry idempotently" 7
fi
