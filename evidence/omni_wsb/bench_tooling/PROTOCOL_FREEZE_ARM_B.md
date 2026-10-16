# ARM-B PROTOCOL FREEZE — SGLang-Omni WSB on W7900 (gfx1100)

Frozen: 2026-10-14 (before any arm-B generation). No field below may change
after the first candidate is generated; the generation driver enforces this
via immutable run_config.json / write-once evaluation_inputs.jsonl.

## Purpose

Independent 384-candidate WildSongBench run served by the real
sgl-omni server (patched Omni branch), scoring with the same frozen official
evaluator used for arm A. Arm A (original SGLang endpoint, commit ced0ef7d,
run wsbfull20261012T0041Z) is COMPLETE and will NOT be repeated.

## Frozen identities (refreshed 2026-10-14, live GitHub verification)

| Item | Value | Verified |
|---|---|---|
| Omni PR #1 head (yiakwy fork) | 50c91c0888312ae784d3c42d9536665aa517dd9d | unchanged (fork fetch 2026-10-14) |
| Author base add_yue2 | 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9 | unchanged (origin fetch + PR #2540 API: open, head 85ae4b73, not merged) |
| Arm-A SGLang commit (reference) | ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f | sgl-project/sglang#42106 head |
| Benchmark tree | bench/omni-wsb @ c4841f0c667f76f2cbe83f8268b1b9bf5d6feab5 = 50c91c08 + 91dccda1 (comment-only) + bench-only artifacts export | git rev-parse |
| Dataset | m-a-p/WildSongBench@e361b85a (reproduction_manifest.jsonl sha256 859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0) | frozen auditor pin |
| Model | m-a-p/YuE2-3B@1a96eca688d6ae5d7f0feb88573fec89920fcd19 (local, weights_manifest verified per-candidate by model_identity) | arm-A pin |
| VAE/decoder | m-a-p/YuE2-Vae-legacy@b54118f0fc462f08999d1ec07e88817f4ee3f770 (benchmark decoder, matching the previous official evaluation) | arm-A pin |
| Evaluator | benchmark/wsb_metrics tree (patches through 0009; frozen metrics env; ASR Qwen3-ASR-1.7B) | scores/protocol.json chain from arm A |

## Frozen generation protocol (identical to arm A)

- 192 prompts x 2 candidates = 384; candidate j uses candidate_ar_seeds[j] of
  the frozen manifest (seeds 831001..831192 family); NAR seed = AR seed.
- cot=full, cfg_scale=1.0 (single-branch), abc_max_tokens=4096,
  semantic_max_tokens=9000, ode_steps=32, vae_core_frames=1024,
  vae_halo_frames=16. Style and lyrics verbatim from the dataset rows.
- Selection: official PER best-of-2 per prompt, same selected set reused for
  SongBench/MuLan/AllMusicCaps selected-arm metrics.

## Arm-B protocol differences from arm A (all disclosed, none hidden)

1. Serving stack: sgl-omni serve (OpenAI /v1/audio/speech, nested YuE2 JSON)
   instead of sglang serve /v1/audio/generations. Same model weights, same
   VAE, same frozen settings, same seeds, same dataset text.
2. Bench-only instrumentation commit c4841f0c (local branch bench/omni-wsb,
   NEVER pushed): adds optional artifacts_dir export hooking the author's own
   MIGRATION.md TODO (yue2_artifacts_dir). 3 files, +35 lines, zero model-math
   changes; no-op for requests without artifacts_dir. Unit gates 12/12 pass.
   Audio path byte-identical to PR #1 head.
3. WAV from the Omni endpoint is 16-bit PCM 48 kHz stereo; arm A returned
   FLOAT WAV. The official finalizer reads float64, clips [-1,1] and writes
   the same lossless FLAC PCM_24 artifact; 16-bit -> float64 -> PCM_24 is a
   lossless repack of the delivered PCM (no resampling, no filtering).
4. result.json runtime_sha256 hashes sglang_omni/models/yue2/*.py (the code
   that actually ran) instead of the SGLang tree; serving_stack=sglang-omni.
   request.id is the constant "song" (Omni SongRequest carries no request id);
   per-candidate identity remains unique via style/lyrics/seed/config hashes.
5. x-finish-reason header recorded per candidate (Omni always reports "stop";
   natural EOS vs truncated is recorded from the AR timing dict into
   plan.json/result.json truncated field, as in arm A).

## Isolation and safety

- GPU gfx1100 verified free before start: rocm-smi 0% / 28 MiB used, no KFD
  processes (stale sysfs counter on the phantom second 0x744b card ignored;
  rocm-smi is authoritative).
- Server bound to 127.0.0.1:32100; single experiment; no other active runs.
- Driver refuses to start if the omni tree is dirty or not at c4841f0c.
- Resumable; atomic finalization; per-candidate SHA256; failure journal;
  disk guard >= 20 GiB; VRAM/GTT polling; graceful SIGINT/SIGTERM.

## Pilot gate (Phase 1)

10 prompts x 2 candidates (5 zh indices 0-4 + 5 en from the frozen en set),
then strict pilot audit + official PER scoring of the pilot. Pilot scores are
workflow-integrity evidence ONLY and will not be published as WSB results.
Full 384 generation starts only on pilot PASS.
