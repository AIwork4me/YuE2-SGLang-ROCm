# 04 — Runtime RCA & reliability (INTERIM — GPU windows queued behind Arm B campaign)

Status 2026-11-19: **historical evidence reviewed; fresh re-validation
NOT_TESTED (GPU occupied by Arm B campaign until ~2026-11-20T23:00Z)**.
This file defines the exact protocols so the post-campaign GPU windows are
mechanical. No root-cause claim below is upgraded without fresh evidence.

## M4.1 — SGLang AR-stage hang

Historical: ~1/300 full-song requests hang in autoregressive generation
(RCA-10). Watchdog restart = operational mitigation, NOT a fix.

**Planned protocol (isolated window, server under verified identity):**
1. Bounded request generator: N=100 full-song requests, per-request wall
   timeout 1800 s, structured stage-level traces (server log timestamps +
   driver journal), VRAM/GTT telemetry (existing MemoryPoller).
2. On hang: capture `rocm-smi`, `/proc/<pid>/stack` + `wchan`, server
   scheduler state (SGLang decode/AR metrics endpoint), thread dump
   (py-spy attach if available), then identity-verified stop.
3. Attribution matrix: scheduler vs sampling/termination vs kernel vs
   sync vs resource exhaustion — each with a discriminating observation.
4. Positive control: same request replayed post-restart must complete.

## M4.2 — HIP illegal memory access (concurrent gen+ASR)

Historical: crash when evaluator shares GPU with generator; solo clean.
Safe serialized path already proven by two full campaigns.

**Planned protocol (dedicated window ONLY, never during evidence runs):**
bounded reproducer = Arm A driver (small pilot subset) + metrics venv ASR
scoring launched concurrently; escalation ladder single-tenant → shared.
Capture: dmesg/amdgpu ring dumps, py-sigtools rocm crash report,
`amd hipcc --version` context. Keep the causal claim within evidence:
if serialization is the only supported configuration, we document and
ENFORCE the boundary (gpu_lock already does) — we do NOT claim the
driver/kernel defect is fixed.

## M4.3 — Native PyTorch close() device-memory behavior

Historical (PYTORCH_API_ACCEPTANCE #13): ~10.2 GiB device memory before
close(); ~0.34 GiB released pre-exit.

**Planned protocol:** instrument allocated vs reserved (torch.cuda.memory_
{allocated,reserved,max_allocated}), nvidia-smi-equivalent (rocm-smi
--showmeminfo vram,gtt) before/after close()+gc+empty_cache; repeat
load→generate(short)→close × 5 for steady-state growth; verify full release
at process exit. Distinguish caching vs live references vs pipeline-owned
buffers. If our layer owns the defect → fix here; else minimal upstream
issue with proof (owner-gated submission).

## M4.4 — Reliability regression matrix (post-campaign)

Pre-registered workload sizes (failure-rate justified, resource-bounded):
- short requests × 50 (valid), 10 invalid-input, 5 cancel-mid-generation
- full-song × 10 bounded; one long-lyrics request; one oversized request
- server restart × 3; worker kill (SIGKILL child) × 2; launcher SIGINT/SIGTERM
  (already covered live in tests/test_armB_lifecycle.py — re-run on physical)
- load/unload cycle × 5 (cold/warm), gpu_lock contention, orphan scan
- verdicts per case + no silent fallback / no corrupt completed artifact /
  no unbounded retry (journal-inspected)

"Zero observed failures" will be reported as exactly that — never as a
failure-probability claim.
