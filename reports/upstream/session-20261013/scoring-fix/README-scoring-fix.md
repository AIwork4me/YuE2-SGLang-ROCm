#!/usr/bin/env bash
# run_wsb_scoring.sh — PID-scoped variant (DRAFT FIX, NOT DEPLOYED)
#
# Purpose: replace the broad `pkill -f "sglang serve"` in stage 3 with a
# narrowly scoped stop that only touches the generation server owned by this
# benchmark run. The live script at
# /workspace/yue2-sglang-rocm-w7900/scripts/run_wsb_scoring.sh must NOT be
# hot-edited while a bash process is executing it (PID 494132); deployment
# procedure is documented in reports/upstream/YUE2_ROCM_MINIMAL_MERGE_CLOSURE.md.
#
# Change vs original (stage 3 only):
#   - Resolve the server PID from the run's own server.pid artifact and verify
#     its cmdline matches this run's model/port before signaling.
#   - Fallback: if no PID artifact exists, match on the run's exact model path
#     and port instead of the generic "sglang serve" pattern.
#
# NOTE: full file is not reproduced here; this is a surgical patch context.
# Apply with:
#   patch -p1 < pid-scoped-server-stop.patch
# (see sibling file) after the current run reaches a safe boundary and the
# running scheduler instance (bash PID) has exited, then relaunch:
#   nohup bash scripts/run_wsb_scoring.sh <RUNS> ... &
# (relaunch does NOT restart generation; it only resumes the wait loop.)
