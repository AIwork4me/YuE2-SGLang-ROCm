# Known Limitations (honest list)

## Platform (gfx1100 / ROCm)

1. **No accelerated kernels**: DeepSelect topk, sgl_kernel fused decode/NAR,
   batched-AR are CUDA-only. YuE2 runs the reference paths (correctness
   validated; speed cost quantified in the performance baseline). Do not try
   to force-enable the env flags — the capability gates exist for a reason.
2. **HTTP telemetry gaps**: `peak_memory_mb` reports 0.0 and
   `yue2_stage_seconds` nulls on ROCm (probe backend absent). Memory truth:
   rocm-smi; stage truth: server log.
3. **Q3O NOT RUN**: requires flash-attn 2.8.3 (CUDA-only) and an 80 GB GPU
   per official docs. W7900 (48 GB) does not attempt it; gfx1151 likewise.
4. **Cross-GPU byte-identity not expected**: equal seeds on different GPU
   architectures produce different waveforms (GPU RNG/kernel math). The
   request/config/weights identity hash IS reproducible (verified
   gfx1151↔gfx1100 byte-identical identities).
5. **W7900D naming**: some W7900 parts report as "W7900D" (same gfx1100 die,
   48 GB); tooling must match on gcnArchName, not marketing string.

## Evaluator portability (disclosed, not hidden)

6. **PER ASR backend**: vLLM 0.14.0 has no ROCm build; PER runs the same
   Qwen3-ASR-1.7B checkpoint through qwen_asr's transformers backend
   (greedy, same chunking/phonemization/scoring). Parity study included in
   the evidence; where the reference backend cannot run, reports say
   "evaluator backend parity not yet established".
7. **torch-family substitution in evaluator venvs** under
   `WSB_ROCM_TORCH_OVERRIDE=1` (receipt records actuals; everything else
   matches the frozen lock; scoring math untouched).

## Harness

8. Validator requires the real frozen manifest for unit tests (skips with
   instructions otherwise — by design: no synthetic protocol files).
9. `watch_milestones.sh` checkpoints count *verified-complete* candidates from
   the manifest journal (never directory listings), but milestone commits are
   only as current as the poll interval (120 s).

## Environment-specific (this rig)

10. Egress proxy intermittently drops github.com HTTPS CONNECTs and GitHub
    release assets; workarounds documented (http transport / REST API /
    python.org builds). hf-mirror used per machine policy with hash
    verification of every artifact.


---

## Additions (2026-11 publication-readiness mission)

- **Q3O: NOT TESTED on 48 GB GPUs.** The official protocol requires an 80 GB
  GPU; the W7900 cannot run it. Never included in "all metrics" claims.
- **PER evaluator backend substitution (carried over, re-confirmed):** all
  published PER uses the qwen_asr transformers backend on ROCm (patch 0007,
  env-gated). Cross-backend equivalence with the official vLLM backend is
  NOT claimed. Fresh evidence (2026-11-12): the substituted evaluator scores
  official-range PER (6.5%) on one strong-audio pilot. This does NOT prove
  evaluator-backend equivalence. The 17% aggregates include capped ASR,
  empty transcripts, and weak candidates; causal attribution versus the
  official 8.44% remains OPEN until same-audio cross-evaluator controls.
- **Official `--backend torch` (graph capture) is broken on ROCm**
  (`mha_varlen_fwd: seqused_k must be nullopt`); the benchmark Arm A uses
  the official `torch-eager` backend (public SDPA). Disclosed as DEV-1 in
  `configs/benchmark.lock.yaml`.
- **Evaluator `--mode standard` rejects `backend: torch-eager` configs**
  (upstream allowlist gap) — patch 0010 (allowlist admission only) applied
  under the same env gate; prepared for upstream handoff.
- **Single-GPU serialization:** benchmark arms run sequentially on one GPU;
  concurrent evaluation during generation is not attempted (VRAM
  contention).

---

## Additions (W7900-RC4, 2026-11-22)

- **SGLang scheduler idle busy-loop (R1-class):** after a completed request
  batch, the `sgl_diffusion::scheduler` child has been observed spinning one
  CPU core at ~99% with 0% GPU utilization for hours while the HTTP frontend
  stays healthy (live capture 2026-11-22 04:51–13:36Z, ~8.7 h, 22.7 GB VRAM
  retained; evidence `reports/w7900_rc4/02_RUNTIME_RCA.md` R1-E1). Related
  launcher defect (resume pilot exited without stopping its server) is
  documented there as R1-L1. The historical ~1/300 in-request hang is NOT
  claimed fixed; no statistical claim is made from RC4 sample sizes.
- **Scheduler-stack diagnostics blocked in-container:** py-spy/gdb cannot
  attach (yama ptrace_scope=1, no CAP_SYS_PTRACE) — Python-level stack traces
  of a spinning scheduler are unavailable on this rig.
- **Native close() memory (R3, refined):** `YuE2Pipeline.close()` releases
  torch device allocations (346→80 MB in 5 measured cycles); the residual
  ~80 MB allocator baseline plus host RSS retention is bounded and
  non-cumulative — not a leak. The RC1 "memory cleanup unresolved" item is
  narrowed to this bounded residual.
- **Host HF_* env overrides:** system-wide `HF_HOME`/`HF_HUB_CACHE` silently
  redirect caches on this rig (see QUICKSTART §0 note); unset-friendly
  behavior is not assumed.
- **uv through the egress proxy stalls on large PyPI wheels** (evaluator
  venv builds); the documented workaround is plain `pip` (or retrying uv),
  with identical hash-gated results.

## RC4.1 additions (2026-11-23)

- **SGLang diffusion scheduler idles at ~100% of one CPU core** (upstream
  defect at sglang ced0ef7d, `scheduler.py event_loop` — no sleep on the
  empty-queue path; deterministic reproduction in
  reports/w7900_rc4_1/02_IDLE_SPIN_REPRODUCER.md). Mitigation:
  session-scoped servers (`scripts/campaign_ops/run_with_server.sh`).
  Fix belongs upstream; not patched here.
- **`/health` 200 does NOT mean generation-ready**: a scheduler-worker
  SIGKILL leaves HTTP healthy while requests hang. Use
  `scripts/server_readiness.py check --receipt <server-identity.json>`
  (reports/w7900_rc4_1/02_HEALTH_RCA.md).
- **Unbudgeted ad-hoc generation requests default to full-song budgets**
  (semantic_max_tokens=9000, ode_steps=32): a small-but-valid payload is a
  multi-minute GPU job by design. Precheck degenerate/ad-hoc inputs with
  `scripts/input_budget.py` (reports/w7900_rc4_1/03_INPUT_RCA.md). The
  frozen WildSongBench protocol path is unaffected and is not routed
  through the precheck.
- **RC4 CPU-fallback suspect remains SUSPECT_UNCONFIRMED** (mechanism not
  proven; no stack was capturable); the blind spot is closed by
  `scripts/gpu_identity.py` fail-loud receipts
  (reports/w7900_rc4_1/01_GPU_FALLBACK_RCA.md).
