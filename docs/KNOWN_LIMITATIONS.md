# Known Limitations (honest list)

## Platform (gfx1100 / ROCm)

1. **No accelerated kernels**: DeepSelect topk, sgl_kernel fused decode/NAR,
   batched-AR are CUDA-only. YuE2 runs the reference paths (correctness
   validated; speed cost quantified in the performance baseline). Do not try
   to force-enable the env flags — the capability gates exist for a reason.
2. **HTTP telemetry gaps**: `peak_memory_mb` reports 0.0 and
   `yue2_stage_seconds` nulls on ROCm (probe backend absent). Memory truth:
   rocm-smi; stage truth: server log.
3. **Q3O (RC6 status)**: RUNS on 48 GB with the ROCm-adapted judge —
   192/192 valid (RC5.1), 34 GPU + 14 CPU MoE layers, deterministic
   tie-break. OFFICIAL equivalence NOT_ESTABLISHED (different engine:
   HF-ROCm vs vLLM-CUDA; ~18–20% of routed slots are exact boundary ties;
   no CUDA host for the same-audio comparison). Earlier "Q3O NOT RUN / NOT
   TESTED on 48 GB" statements are superseded. 24 GB cards: NOT_TESTED
   (below the measured 42.4 GiB judge peak).
4. **Cross-GPU byte-identity not expected**: equal seeds on different GPU
   architectures produce different waveforms (GPU RNG/kernel math). The
   request/config/weights identity hash IS reproducible (verified
   gfx1151↔gfx1100 byte-identical identities).
5. **W7900D naming**: some W7900 parts report as "W7900D" (same gfx1100 die,
   48 GB); tooling must match on gcnArchName, not marketing string.

## Evaluator portability (disclosed, not hidden)

6. **PER ASR backend**: vLLM 0.14.0 has no ROCm build; the FROZEN arm runs
   the same Qwen3-ASR-1.7B checkpoint through qwen_asr's transformers
   backend (greedy, same chunking/phonemization/scoring) — this substitution
   was root-caused in RC5.1 as the dominant driver of the frozen arm's PER
   gap (repetition-loop on hard candidates; vLLM escapes it). The corrected
   vLLM 0.19.1 ROCm arm reproduces the paper PER (8.4488% vs 8.44%) and is
   reported as a SEPARATE arm (never mixed into the frozen scoreboard).
   Cross-engine equivalence with the official 0.14.0 CUDA backend remains
   NOT_ESTABLISHED (no CUDA host; handoff package ready).
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

- **Q3O on 48 GB GPUs (SUPERSEDED by RC5.1/RC6):** runs with the
  ROCm-adapted judge (192/192 valid; 34 GPU + 14 CPU MoE layers). The
  official 80 GB requirement referred to the OFFICIAL engine (vLLM +
  FlashAttention CUDA); our adapted path trades engine equivalence (NOT
  ESTABLISHED) for feasibility on 48 GB. Q3O results are labelled
  ROCm-adapted and never enter "official all-metrics" claims.
- **PER evaluator backend substitution (SUPerseded note, see item 6 above):**
  RC5.1 closed the causal attribution (same-audio matrix; corrected vLLM arm
  8.4488% vs paper 8.44%); cross-backend equivalence with the official
  vLLM 0.14.0 backend remains NOT_ESTABLISHED (no CUDA host; handoff ready).
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

## RC5 additions (2026-11-24, in progress)

- **No off-machine backup**: the owner confirmed there is no backup host. The
  RC5 checkpoints (incremental every 16 candidates + full at milestones, SHA256
  manifests) are copied to a second volume on the SAME host and a restore drill
  passes, but that does not survive loss of the host
  (reports/w7900_rc5/00_STORAGE_AND_BACKUP_PLAN.md: `DISASTER_RECOVERY_BLOCKED`).
- **Upstream artifact exporter writes 16-bit WAV**: `Yue2VAEDecodeStage` calls
  `sf.write(path, audio, sr)` (soundfile default PCM_16) while the official
  `yue2-infer` writes `audio.flac` PCM_24 from float. Every sample of the
  SGLang-path audio therefore sits on the 1/32768 grid before the official MP3
  encoding. Not patched in the main run (pure-upstream policy); documented for
  the author (reports/w7900_rc5/02_UPSTREAM_DELTA_REVIEW.md, finding F3).
- **HTTP timing fields are null**: at the frozen head `yue2_timing`,
  `yue2_stage_seconds` and `yue2_nar_fast` are always `null`; exact stage
  seconds are read from the server log by the RC5 driver.
- **Two upstream dispatch tests are host-dependent** (assume a non-HIP host /
  SM90): 19/21 pass on gfx1100.
- **Official PER is expensive on this engine**: with the official ASR config
  (batch 8, cap 4096) the qwen_asr transformers backend spends ~118 ms per
  decode step and a batch waits for its longest sequence; the full 384-song
  PER is estimated at 15–25 GPU-hours. The official ROCm vLLM wheel index
  (`wheels.vllm.ai`) is blocked by this host's egress proxy, so the official
  vLLM engine could not be tried locally.
- **ASR-side empty transcripts on English songs (preliminary)**: on the 12
  pilot candidates Qwen3-ASR (transformers on ROCm) returned an empty
  transcription for 4 of 8 English candidates; an unrelated reference ASR
  (Whisper) transcribes the same audio with a reference PER of 0.09–0.33. This
  points at the evaluator side, not the audio. Root cause NOT yet established
  (reports/w7900_rc5/INTERIM_STATUS_ZH.md).
- **Q3O**: the Thinker alone is 58 GiB in BF16 (> the ~44.6 GiB usable), so the
  official judge cannot be loaded as-is; a ROCm-adapted route (Thinker-only
  BF16, mixed GPU/CPU placement) is prepared but not yet validated on hardware.

## RC5.1 additions (2026-11-27, final)

1. **Q3O is ROCm-adapted, NOT official-equivalent**: the official judge is
   vLLM 0.14.0 + FlashAttention 2.8.3 on an 80 GB CUDA GPU. Our judge keeps
   the official scorer, prompts, parser, weights and greedy decoding, but
   runs the Thinker through HF transformers on ROCm (34 GPU + 14 CPU-resident
   MoE layers). **18.4–20.2% of routed token-slots sit on exact top-k
   boundary ties** whose resolution in the official kernel is unknown, so
   per-token routing parity cannot be claimed. Score 4.393986 vs paper 4.68.
2. **PER engine substitution, now root-caused**: the frozen official W7900
   PER (17.7699%) uses the qwen_asr transformers backend (vLLM 0.14 has no
   ROCm build). That backend enters a repetition loop on 10/384 candidates
   (2 more cap out) — invariant to precision/attention/batch/device; the
   same weights+audio through vLLM 0.19.1 transcribe them. The corrected arm
   scores 8.4488% selected micro PER (paper: 8.44%); it is reported as a
   SEPARATE arm — the frozen scoreboard entry is unchanged, and the other
   four metrics are bound to the original frozen selection.
3. **Off-machine backup**: BLOCKED_EXTERNAL (owner confirmed no backup host);
   same-host second-volume recovery is verified (384/384 drill) but is not
   off-machine disaster recovery.
4. **Four candidates differ from the historical run at the FLAC-container
   level only** (same codec frames/duration/truncation; −2/+2/+15/0 bytes in
   17–26 MB files): the rebuilt image's libFLAC build differs. Generation
   determinism is unaffected.
5. **Exact-HEAD CI evidence is step-level** (job-log download requires admin
   rights); local reproduction of the same suites is recorded in
   `reports/w7900_rc5/rc5_1/02_TEST_RESULTS.json`.
6. **Kernel-level trigger of the ASR loop is characterised, not traced**:
   the post-header knife-edge (identical top-5, EOS prob ~2e-5) is measured;
   which arithmetic difference flips it is OPEN. E3 (official CUDA) is
   BLOCKED_EXTERNAL with a prepared hand-off package.
7. **BatchedGpuMoeBlock is retained but not used at runtime**: it does not
   fit 48 GB as implemented (allocator fragmentation, root-caused); the
   validated path patches the stock HF loop's top-k in place.
