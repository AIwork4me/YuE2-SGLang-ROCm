#!/usr/bin/env bash
# rc5_real_gpu_controls.sh — REAL-GPU readiness negative controls, run INSIDE
# a lifecycle session as the wrapped command (RC5 M1.3):
#
#   bash scripts/campaign_ops/run_with_server.sh --log-dir D -- \
#        bash scripts/campaign_ops/rc5_real_gpu_controls.sh <report.json>
#
# The server is the one this session owns; its pids come from the session's
# identity receipt and the child table. See rc5_real_gpu_controls.py.
set -uo pipefail
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WS="${YUE2_WORKSPACE:-/data/yue2}"
PY_B="${YUE2_VENV:-$WS/environments/yue2-gfx1100}/bin/python"
[ -x "$PY_B" ] || PY_B="$(command -v python3)"
OUT="${1:?report json}"
LOG_DIR="${RWS_LOG_DIR:-$WS/logs}"
RECEIPT="$LOG_DIR/rws_server_identity/server-identity.json"
URL="http://${RWS_HOST:-127.0.0.1}:${RWS_PORT:-31000}"
MODEL="${MODEL_PATH:-$WS/models/YuE2-3B}"

SERVER_PID="$("$PY_B" -c "import json,sys;print(json.load(open(sys.argv[1]))['pid'])" "$RECEIPT")"
SCHED_PID=""
for p in /proc/[0-9]*; do
  pp="$(awk '{print $4}' "$p/stat" 2>/dev/null || echo 0)"
  if [ "$pp" = "$SERVER_PID" ] && tr '\0' ' ' < "$p/cmdline" 2>/dev/null | grep -q "sgl_diffusion"; then
    SCHED_PID="$(basename "$p")"; break
  fi
done
[ -n "$SCHED_PID" ] || { echo "FATAL: scheduler worker of server $SERVER_PID not found" >&2; exit 2; }
echo "[rgc] server pid=$SERVER_PID scheduler pid=$SCHED_PID"
"$PY_B" "$REPO/scripts/rc5_real_gpu_controls.py" --out "$OUT" --receipt "$RECEIPT" \
  --url "$URL" --log-dir "$LOG_DIR" --model "$MODEL" --server-pid "$SERVER_PID" \
  --scheduler-pid "$SCHED_PID" --repo "$REPO" --python "$PY_B"
rc=$?
echo "[rgc] controls rc=$rc — the session cleanup now stops a server whose worker is dead"
exit $rc
