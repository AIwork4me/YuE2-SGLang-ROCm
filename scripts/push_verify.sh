#!/usr/bin/env bash
# push_verify.sh - push an evidence branch and VERIFY the remote SHA.
# Exit 0: remote branch verified at local HEAD.
# Exit 7: LOCAL_COMPLETE_REMOTE_PENDING (push or verification failed).
# Never reports success without a matching ls-remote SHA.
set -uo pipefail
BRANCH="${1:?usage: push_verify.sh <branch>}"
LOG="${LOG:-/dev/stdout}"
ATTEMPTS="${PUSH_ATTEMPTS:-5}"

log() { echo "[$(date -u +%FT%TZ)] [push_verify] $*" | tee -a "$LOG" >/dev/null 2>&1 || echo "$*"; }

LOCAL_SHA=$(git rev-parse HEAD) || { log "cannot resolve local HEAD"; exit 7; }
PUSH_OK=0
for i in $(seq 1 "$ATTEMPTS"); do
  if git push origin "$BRANCH" >> "$LOG" 2>&1; then PUSH_OK=1; break; fi
  log "push attempt $i/$ATTEMPTS failed (proxy flake?) - retrying"
  sleep "${PUSH_SLEEP:-20}"
done
REMOTE_SHA=""
if [ "$PUSH_OK" = 1 ]; then
  for i in $(seq 1 "$ATTEMPTS"); do
    REMOTE_SHA=$(timeout "${LSREMOTE_TIMEOUT:-30}" git ls-remote origin "refs/heads/$BRANCH" 2>/dev/null | awk '{print $1}')
    [ -n "$REMOTE_SHA" ] && break
    log "ls-remote attempt $i/$ATTEMPTS failed"
    sleep "${PUSH_SLEEP:-10}"
  done
fi
if [ -n "$REMOTE_SHA" ] && [ "$REMOTE_SHA" = "$LOCAL_SHA" ]; then
  log "remote branch $BRANCH verified at $REMOTE_SHA"
  exit 0
fi
log "LOCAL_COMPLETE_REMOTE_PENDING (push_ok=$PUSH_OK remote=${REMOTE_SHA:-none} local=$LOCAL_SHA)"
exit 7
