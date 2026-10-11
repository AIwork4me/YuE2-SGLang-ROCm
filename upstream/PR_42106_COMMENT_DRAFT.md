# DRAFT — PR #42106 comment (YuE2 on AMD ROCm gfx1151)

> **STATUS: DRAFT — NOT PUBLISHED.** Owner approval required before posting.
> Placeholders `<PENDING:…>` are filled from the verified full-run results;
> nothing below may be posted with placeholders remaining.

---

Thanks for this PR — sharing an independent reproduction of the YuE2 pipeline
on an AMD APU, in case ROCm portability is useful signal for the reviewers.

## Hardware / software

- CPU/GPU: AMD Ryzen AI MAX+ PRO 395 (Strix Halo), integrated Radeon 8060S,
  **gfx1151**, 32 GiB dedicated VRAM (BIOS carveout) + GTT unified pool
- OS: Ubuntu 24.04.4, kernel 6.17.0-1033-oem, in-tree amdgpu; host ROCm
  userspace 7.2.1 untouched; compute via AMD wheels
  **torch 2.12.0+rocm7.14.1 / torchvision 0.27.0 / torchaudio 2.11.0**
  (repo.amd.com multi-arch, `device-gfx1151` extras)
- SGLang: this PR @ `ced0ef7d` installed editable (`--no-deps`; the metadata
  pins torch==2.14.1 CUDA + CUDA-only extras)
- Models: `m-a-p/YuE2-3B` @ `1a96eca6` and `m-a-p/YuE2-Vae-legacy` @
  `b54118f0` (weight SHA-256s verified against the official
  WildSongBench pins)

## Compatibility findings (patches linked, minimal)

1. **aiter import guards (3 files).** `if _is_hip:` module-level `aiter`
   imports crash on any non-Instinct HIP device (aiter ships only for
   gfx94x/gfx95x). Guards mirror the existing non-HIP `= None` fallbacks.
2. **DeepSelect gating.** `sglang.kernels.ops.deep_select` is importable
   everywhere, but the kernel is CUDA-only (SM 9.0/10.0/10.3);
   `fast_sampler_available()` only checked importability + cuda-available, so
   on ROCm the FastSampler/step-graph path entered and raised at call time
   (mid-decode / during graph capture). Gate on `is_deepselect_supported()`.
3. **fa3 fallback.** With the shared varlen wrapper importable-but-failing at
   call time on ROCm (no `flash_attn` package), fall through to
   `torch.ops.aten._flash_attention_forward` — present with `seqused_k` in
   its schema on this stack and numerically validated against an fp32 manual
   reference (max|diff| ≈ 4e-3, varlen + GQA + bf16).
4. **What worked natively:** HIP CUDA-graph capture/replay (session GraphAR),
   the reference sampler, the reference NAR (SDPA→MATH), and the bf16 model
   itself. Same-seed repeated requests produced byte-identical WAVs in our
   configuration.

## WildSongBench reproduction

Official protocol: 192 prompts × 2 candidates, `cot=full`, official budgets,
frozen evaluator, PER-based best-of-2 selection; benchmark decoder
`YuE2-Vae-legacy`. Candidate artifacts verified against the frozen evaluator
schema (`verify_result` + `validate_generation`) for every candidate.

<PENDING:FULL_TABLE>

| Metric | Native YuE2 (authors) | SGLang PR (H800) | gfx1151 (this run) |
|---|---:|---:|---:|
| SongBench Global Avg ↑ | 6.7360 | 6.7146 | <PENDING> |
| SongBench Musicality ↑ | 5.9197 | 5.8896 | <PENDING> |
| PER ↓ | 8.6087% | 8.1471% | <PENDING> |
| MuLan ↑ | 0.49958 | 0.49960 | <PENDING> |
| AllMusicCaps ↑ | 0.39475 | 0.40825 | <PENDING> |

Coverage: <PENDING: 384/384 or exact accounting>; truncated outputs retained
(<PENDING:count>); selection audited for all 192 prompts.

**Disclosed evaluation-environment deltas (important):**
- The frozen WSB evaluator pins CUDA-only torch (2.9.1/2.7.0) and vLLM; on
  this host it ran with torch 2.10.0+rocm7.14.1 and PER ASR through
  qwen_asr's transformers backend (vLLM has no ROCm build). Scoring formulas,
  selection and aggregation are untouched (3-file diff, hash-covered).
- Same-audio checks: the ASR backend is exactly reproducible for a fixed
  candidate set (10/10 bit-identical across independent passes) but sensitive
  to batch composition (one transcript shifted by 4 edits between a 2-file
  and 10-file batch). Cross-backend (transformers-ROCm vs vLLM-CUDA)
  equivalence is **not claimed** — it would need a same-audio comparison on a
  CUDA host.
- One empty-transcript ASR failure mode was observed (candidate retained,
  PER 1.0, disclosed and counted).
- Q3O: not run (requires flash_attn 2.8.3 + an 80 GB GPU).

## Performance observations (not an H800 comparison)

<PENDING: wall-clock/RTF/stage-timing table + memory.> Batch-1 full songs on
an iGPU are ~6–25 min depending on length; the AR stage runs through HIP
graphs + ATen flash, NAR runs the reference SDPA path (Phase-9 optimization
headroom). These are shared for completeness, not as matched-speedup claims.

## Reproduction

Full evidence, scripts, patches and per-phase reviews:
https://github.com/AIwork4me/YuE2-SGLang-ROCm (patches `0001-0005` for
SGLang, `0006-0007` for the WSB evaluator on ROCm, audit trail in
`patches/EVALUATOR_PATCH_AUDIT.md`).

Would love maintainer feedback on whether the DeepSelect runnability gate and
the fa3 call-time fallback are acceptable upstream; happy to split them into
separate PRs if preferred.
