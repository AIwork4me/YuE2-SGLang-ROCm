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
