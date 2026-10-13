## YuE2 ROCm E2E PASS — request H800 confirmation and add_yue2 integration

Hi! Quick status on this small PR (https://github.com/yiakwy-xpu-ml-framework-team/sglang-omni/pull/1): it now has **real AMD ROCm end-to-end evidence** behind it.

**W7900 (gfx1100, ROCm 7.14.1, torch 2.12.0+rocm7.14.1) real HTTP results** — real `sgl-omni serve`, `POST /v1/audio/speech`, seed 831001, cot=full:

- Short config: **HTTP 200**, 48 kHz stereo WAV, 20.479 s, SHA256 `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed`
- Full config (abc 4096 / semantic 9000 / ode 32 / vae_core 1024): **HTTP 200**, 48 kHz stereo WAV, 47.239 s, SHA256 `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd`
- Token limits were upper bounds — generation stopped at natural EOS (not a long-form stress test).
- Ran on a pristine upstream SGLang checkout: no SGLang source patches were needed for this Omni YuE2 path.

**The patch is intentionally minimal** — 4 source files (`stages.py`, `song.py`, `fastpath.py`, `fa3.py`, +30/−6) plus one test file:

- 12/12 platform dispatch tests pass on the ROCm host (11/12 fail on the unpatched base); tests assert both branches of every gate.
- 37/37 model-capability tests pass.
- 51-case simulated CUDA A/B matrix (base vs patched, env/cfg/cot/device/platform permutations): byte-identical on simulated CUDA.
- The CUDA fast path is **unchanged by construction**: every gate reduces to the original expression when `is_rocm()` is false; NVIDIA batch default stays 4, `SGLANG_YUE2_STEP_GRAPH` / `SGLANG_YUE2_FA3` semantics untouched.

**What's still missing: a real NVIDIA confirmation.** We have no H800, so an actual run of this exact commit on NVIDIA is outstanding. If you're willing, a minimal isolated check:

1. Isolated test worktree (`git worktree add --detach` of `add_yue2`, then merge this PR's commit) — your active checkout and branches stay untouched.
2. Start `sgl-omni serve` on H800 (with `SGLANG_YUE2_VAE_DIR` set).
3. `POST /v1/audio/speech` with the same request schema (seed 831001, cot=full — exact curl in the PR body).
4. Confirm HTTP 200 and a valid 48 kHz stereo WAV; confirm DeepSelect / fast sampler / step graph stay active in the logs (they should — the gates are no-ops on CUDA).
5. Confirm no new exceptions; share your environment SHA + test output.

No need to match the audio SHA256 — different GPU/kernel stacks are not expected to produce bit-identical waveforms.

One environment note (not ROCm-specific): our test host needed `pip install python-multipart` because omni's Form/File routes import it but it isn't declared in packaging — a platform-neutral gap we'll raise separately, kept out of this PR.

Once you confirm the H800 test, could you please merge this small PR into your `add_yue2` branch so the fix becomes part of #2540? Happy to adjust anything (rebase, naming, split) if you prefer a different shape. Thanks!

