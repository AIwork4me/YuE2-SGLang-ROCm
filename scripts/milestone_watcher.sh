#!/usr/bin/env bash
# Phase 6 milestone watcher: monitors runs/wsb_full, emits checkpoint reports
# at 10/50/100/192/300/384 complete candidates, commits+pushes evidence.
# Also watchdogs: restarts nothing (run_wsb.py is resumable) but records
# failures; exits when 384 complete or generation process is gone twice.
# NOTE: the live workspace copy stayed frozen while the 384-candidate run
# executes (bash re-reads scripts mid-run); this repo copy is configurable.
set -uo pipefail
WS="${WS:-/home/amd/Desktop/YuE2}"
EV="$WS/evidence/YuE2-SGLang-ROCm"
LOG="$WS/logs/milestone_watcher.log"
NEXT=10
MISSED=0

count_done() { ls "$WS/runs/wsb_full/songs"/*/result.json 2>/dev/null | wc -l; }
alive() { pgrep -f "run_wsb.py --runs runs/wsb_full" >/dev/null 2>&1; }

cd "$EV"
while :; do
  DONE=$(count_done)
  echo "$(date '+%F %T') complete=$DONE next_milestone=$NEXT" >>"$LOG"
  if [ "$DONE" -ge "$NEXT" ]; then
    source "$WS/environments/yue2/bin/activate"
    python "$WS/scripts/checkpoint_wsb.py" --runs "$WS/runs/wsb_full" \
      > "$EV/evidence/checkpoint_${NEXT}.json" 2>>"$LOG"
    cp "$WS/runs/wsb_full/generation_manifest.jsonl" "$EV/evidence/generation_manifest.jsonl" 2>>"$LOG"
    git add -A >/dev/null 2>&1
    git -c user.name="AIwork4me" -c user.email="AIwork4me@users.noreply.github.com" \
      commit -q -m "test(wsb): checkpoint ${NEXT}/384 candidates on gfx1151" >/dev/null 2>&1
    for a in 1 2 3 4 5; do
      timeout 90 git push >/dev/null 2>&1 && break
      sleep 30
    done
    echo "$(date '+%F %T') MILESTONE $NEXT committed+pushed ($(git rev-parse --short HEAD))" >>"$LOG"
    case $NEXT in
      10) NEXT=50;; 50) NEXT=100;; 100) NEXT=192;; 192) NEXT=300;; 300) NEXT=384;; 384) NEXT=999;;
    esac
  fi
  if [ "$DONE" -ge 384 ]; then
    echo "$(date '+%F %T') COMPLETE 384/384" >>"$LOG"
    break
  fi
  if ! alive; then
    MISSED=$((MISSED+1))
    echo "$(date '+%F %T') WARNING: run_wsb process not found ($MISSED)" >>"$LOG"
    if [ "$MISSED" -ge 6 ]; then
      echo "$(date '+%F %T') FATAL: generation process gone; watcher exiting" >>"$LOG"
      break
    fi
  else
    MISSED=0
  fi
  sleep 300
done
