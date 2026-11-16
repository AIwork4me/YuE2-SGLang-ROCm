#!/usr/bin/env bash
# armA_watchdog.sh — liveness guard for the Arm A campaign.
# NO auto-restart, NO pkill: logs diagnostics if the journal stalls >90 min.
# Resume is a manual/one-command operation (run_armA_campaign.sh is idempotent).
set -u
JOURNAL=/data/yue2-runs/armA_wsb_full/generation_manifest.jsonl
STATE=/data/yue2/logs/armA_watchdog_state
while true; do
  sleep 600
  # driver alive?
  if ! pgrep -f "run_wsb_torch.py --runs /data/yue2-runs/armA_wsb_full" > /dev/null; then
    echo "$(date -u +%FT%TZ) driver not running (finished or exited; journal is resume-safe)" >> $STATE.log
    exit 0
  fi
  NOW=$(date +%s)
  MT=$(stat -c %Y "$JOURNAL" 2>/dev/null || echo $NOW)
  AGE=$(( NOW - MT ))
  echo "$(date -u +%FT%TZ) journal_age_s=$AGE" >> $STATE.log
  if [ $AGE -gt 5400 ]; then
    {
      echo "=== STALL SUSPECTED $(date -u +%FT%TZ) journal idle ${AGE}s ==="
      ps -eo pid,etime,%cpu,%mem,cmd | grep -E "run_wsb_torch|_gen_worker" | grep -v grep
      for p in $(pgrep -f "_gen_worker.py"); do
        echo "--- /proc/$p/stack (kernel) ---"; cat /proc/$p/stack 2>/dev/null | head -5
        echo "--- py stack ---"; timeout 30 /opt/venv/bin/python -m psutil 2>/dev/null || true
      done
      echo "--- GPU ---"; rocm-smi --showuse --showmeminfo vram 2>/dev/null | head -12
      echo "--- memory.current vs max ---"
      cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current
    } >> /data/yue2/logs/armA_stall_diagnostics.log 2>&1
  fi
done
