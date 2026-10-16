# 05 — NVIDIA H800 focused acceptance checklist (patched-commit regression)

**Purpose.** The author's existing NVIDIA evidence covers commits `85ae4b73`
(Omni) and `ced0ef7d` (SGLang) — not the post-integration commit that would
carry the ROCm platform gates. This is the smallest test plan that closes
that gap. It is a **smoke + dispatch-evidence** test, NOT a request for a new
WildSongBench run and NOT a byte-parity test.

**Non-goals (explicit):** no identical-WAV requirement across NVIDIA/AMD; no
new full dataset runs; no benchmark repetition; no sampling-equivalence
math proofs.

## Preconditions

1. Integrated source = author's `add_yue2` after merging PR#1 (`eca7770f`)
   and (optionally) PR#2 (`4c089d19`), plus the style commit `ae11c6ad`
   (optional for function, needed for lint).
2. Record the exact tested `git rev-parse HEAD` in the receipt below.
3. Use the author's existing CUDA PyTorch environment unchanged (the same
   env that produced the original single-shot test). Do NOT install ROCm
   packages, do not upgrade torch/flashinfer/sgl-kernel for this test.

## Test 1 — unit gates (CPU-runnable, ~1 min)

```bash
cd <author's sglang-omni checkout at the integrated commit>
python -m pytest tests/unit_test/models/test_yue2_platform_gates.py \
                 tests/unit_test/models/test_yue2_speech_input_cap.py \
                 tests/unit_test/models/test_model_capabilities.py -q
# expect: 62 passed (12 platform gates + 13 input-cap + 37 capabilities)
```

Expected specifically: all CUDA-dispatch invariants hold (fast paths selected
when platform is CUDA; ROCm gates dormant on an H800 box).

## Test 2 — real serve + deterministic song (GPU, ~2–5 min)

1. Launch the server exactly as in the PR body script
   (`sglang_omni.cli serve --config configs/yue2.yaml`, port 30065,
   `SGLANG_YUE2_FA3=1`, `SGLANG_YUE2_VAE_DIR` set). Capture the boot log.
2. Issue the PR body's curl example verbatim (seed 831001, `cot=full`,
   `ode_steps 32`, budgets 9000/4096, `vae_core_frames 1024`).
3. Verify and journal:

| Check | Pass criterion |
|---|---|
| HTTP | 200 |
| WAV | valid RIFF/WAVE header |
| Rate/channels | 48 kHz stereo where expected |
| Duration | in the same range as the author's prior run of the same input (not byte-parity) |
| Finish | AR + NAR + VAE completed (log stages present, `x-finish-reason` recorded) |
| Exceptions | no new tracebacks vs the author's baseline log |
| CUDA fast sampler | log/config evidence DeepSelect/FastSampler active (dispatch lines present) |
| CUDA graph path | graph capture/reuse messages present (author's original supported path) |
| FA3 | active when `SGLANG_YUE2_FA3=1` (log line or dispatch evidence) |

4. Backend/dispatch evidence: retain the server log section showing which
   attention/sampler branches were selected (this is the "CUDA regression
   = none" receipt).

## Test 3 — existing targeted CUDA unit test (original SGLang side only)

If validating sgl-project/sglang#42106's integrated commit
(`ced0ef7d` + AMD-sglang-benchmark-fork#1 `def437fb`), run the author's own
command from that PR body:

```bash
SGLANG_TEST_YUE2=1 SGLANG_TEST_YUE2_MODEL=/raid/yiakwy/YuE2-3B \
  pytest python/sglang/multimodal_gen/test/server/test_server_yue2.py
```

## Receipt template (paste into the PR thread or evidence branch)

```
H800 patched-commit regression — <date>
repo/commit: <URL + full SHA>
env: torch <x.y.z+cuNNN>, flashinfer <v>, sgl-kernel <v or JIT>, driver <v>
GPU: H800 x<N>
T1 unit gates: <n> passed
T2 serve: HTTP 200, wav 48kHz stereo, <dur>s, finish-reason <...>,
   fast-sampler <active?>, cuda-graph <captured?>, FA3 <active?>,
   new exceptions: none
T3 (SGLang side): <result or n/a>
operator: <author>
```

## Integrity rules

- Do not report success without the actual log excerpts; logs are the
  receipt, summaries are not.
- If anything genuinely changed in the CUDA execution path beyond platform
  gates (it should not — tree-level diff vs `eca7770f` is the gates + tests),
  stop and report before retrying.
- This checklist adds no workload beyond one short song; it does not replace
  the author's existing dataset evidence, which remains the accuracy
  reference for the CUDA path.

## Gate

`H800_HANDOFF_READY` — executable as written; every command references real
files/remotes (author's own PR-body scripts, our published commit SHAs); no
fabricated hardware results included or implied.
