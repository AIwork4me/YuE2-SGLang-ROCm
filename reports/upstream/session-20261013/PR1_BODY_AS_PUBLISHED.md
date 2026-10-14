YuE2 now passes real SGLang-Omni HTTP music-generation tests on AMD Radeon PRO W7900 using ROCm, while the patch preserves the NVIDIA CUDA fast paths. Real `sgl-omni serve` + `POST /v1/audio/speech` returned HTTP 200 with valid 48 kHz stereo WAV audio on gfx1100 (ROCm 7.14.1, torch 2.12.0+rocm7.14.1) at commit 50c91c0, on top of this branch's `add_yue2` — with a pristine, unpatched upstream SGLang checkout.

## 1. Problem / why this patch exists

On a ROCm host (verified live on gfx1100):

- `current_platform.is_cuda()` is `False` (`RocmSRTPlatform`), so `create_synth_executor` raises "YuE2 requires a CUDA backend" — the model never loads (`stages.py`).
- PyTorch HIP names devices `"cuda"`, so the surviving `device.type == "cuda"` gates do **not** protect the CUDA-only paths:
  - `song.py` would enter the fused decode+sample Step Graph, whose in-graph sampler calls the DeepSelect TopK kernel (CUDA-only, SM 9x/10x).
  - `fastpath.fast_sampler_available()` treats `torch.cuda.is_available()` (true on HIP) plus mere importability of the pure-Python `sglang.kernels.ops.deep_select` wrapper as kernel support.
  - `fa3.py` would import `sglang.kernels.ops.attention.flash_attention.flash_attn_varlen_func` (importable on ROCm, but it dispatches to CUDA-only FA3 kernels) instead of the validated native ATen varlen path.

## 2. Minimal changes (4 YuE2 files + 1 test file, +30/−6 in sources)

1. `stages.py` — accept `is_cuda() or is_rocm()`; default `SGLANG_YUE2_BATCH_MAX_SIZE` to `1` on ROCm (env override still honored; NVIDIA default `4` untouched).
2. `song.py` — bypass the CUDA-only fused decode+sample Step Graph when `current_platform.is_rocm()`; ROCm uses the existing looped AR generator. The pooled GraphAR/HIP-graph decode sessions are NOT disabled — only the DeepSelect-dependent sampler graph is bypassed. `SGLANG_YUE2_STEP_GRAPH` keeps its exact NVIDIA semantics.
3. `fastpath.py` — `fast_sampler_available()` returns `False` on ROCm (reference `distribution()` sampler runs); NVIDIA chain (env flag → backend → `torch.cuda.is_available()`) unchanged.
4. `fa3.py` — on ROCm skip the shared FA3 varlen op and use `torch.ops.aten._flash_attention_forward` (the exact pre-existing fallback, `seqused_k`/GQA semantics intact). NVIDIA dispatch (`SGLANG_YUE2_FA3=1` default → shared op, `ver=3`) unchanged.

## 3. Real AMD ROCm E2E results (W7900 / gfx1100, 48 GB)

Real Omni server (`sgl-omni serve`, endpoint `POST /v1/audio/speech`, seed 831001, cot=full):

| Test | Result |
|---|---|
| SHORT (smoke params: ode 8, vae_core 256) | **HTTP 200**, `audio/wav`, 48,000 Hz stereo, **20.479 s**, RMS 0.0860, SHA256 `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed` |
| FULL CONFIG (abc 4096 / semantic 9000 / ode 32 / vae_core 1024) | **HTTP 200**, `audio/wav`, 48,000 Hz stereo, **47.239 s**, RMS 0.1470, SHA256 `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd` |

- Both bodies independently decoded (soundfile): genuine RIFF PCM16 stereo 48 kHz, finite, byte math exact; the two waveforms are distinct (same seed, different budgets — not cached output).
- Full-config token limits are upper bounds: generation stopped at **natural EOS**. This is not a long-form endurance or stress claim.
- Real gfx1100 execution: rocm-smi GPU util 0→100% bracketing the full-config request window, VRAM 21→35%; server log `YuE2 synth done … samples=2267456 duration=47.24s`. (GPU trace covers the full-config window; the short window's utilization is inferential from the same server instance's synth elapsed 15.25 s.)
- Execution paths on ROCm: looped reference AR sampling; native ATen varlen attention; DeepSelect / fast sampler / step graph gated off; NAR velocity graph via the HIP graph API; real on-device VAE decode. **No CUDA execution is claimed.**
- Runtime stack: `m-a-p/YuE2-3B@1a96eca` (628/628 tensors), `YuE2-Vae-legacy@b54118f0`, ROCm 7.14.1 / HIP 7.14.60850.

## 4. NVIDIA behavior and regression evidence

Every changed expression reduces to the original when `is_rocm()` is false and `torch.version.hip is None` (the factory's new error message is unreachable on a working NVIDIA host because `is_cuda()` short-circuits):

| site | original | with patch, on NVIDIA |
|---|---|---|
| stages gate | `not is_cuda()` | `not (is_cuda() or False)` ≡ identical |
| batch default | `"4"` | `"4"` |
| song step-graph gate | `cfg/cot/env/device` | same `and not False` no-op |
| fast_sampler_available | env → backend → cuda | same, ROCm branch skipped |
| fa3 `_load_varlen` | env → try import | same `and not False` no-op |

No seeds, logits arithmetic, temperature, top-p, top-k, repetition penalty, token budgets, weights, or kernels are touched. Tests: **12/12 platform dispatch tests** (this PR's test file; 11/12 fail on unpatched base), **37/37 model-capability tests**, and an executable **51-case simulated CUDA A/B matrix** (env/cfg/cot/device/platform permutations) of base vs patched modules with byte-identical outputs on simulated CUDA. The platform tests explicitly assert the NVIDIA branch of every gate, including batch default 4 and env overrides. Three independent code reviews: zero P0/P1 findings.

**Not claimed:** no NVIDIA run was executed by our team; audio is not expected to be bit-identical across GPU vendors; no performance/quality parity claim beyond the author's own evaluation of the base PR.

## 5. Dependency requirements

- SGLang: a **pristine upstream checkout** (empty diff) worked at runtime for this Omni YuE2 path — no SGLang source patch is needed for it on gfx1100.
- One environment-only install was needed on the test host: `python-multipart==0.0.32`, because omni's Form/File HTTP routes (`openai_api.py`, `speech_to_text.py`) import it but no packaging target declares it. This is a **platform-neutral packaging gap**, not a ROCm dependency, and is intentionally out of scope for this PR (a separate upstream note/PR may follow).

## 6. Remaining H800 verification

The CUDA fast path is unchanged **by construction** and by the simulated A/B matrix, but a real NVIDIA run of this exact commit has not been performed by our team. Suggested minimal check on H800 (isolated worktree of `add_yue2` + this commit):

```bash
# isolated test worktree — your active checkout is untouched
git fetch origin add_yue2 fix/yue2-rocm-reference
git worktree add --detach /tmp/yue2-h800-check origin/add_yue2
git -C /tmp/yue2-h800-check merge --no-ff origin/fix/yue2-rocm-reference
python -m pytest tests/unit_test/models/test_yue2_platform_gates.py -v
SGLANG_YUE2_VAE_DIR=/path/YuE2-Vae-legacy sgl-omni serve --model-path /path/YuE2-3B --port 8000
curl -w '\nHTTP %{http_code}\n' http://127.0.0.1:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"YuE2-3B","voice":"default","input":"{\"style\":\"melodic electronic pop\",\"lyrics\":\"[verse]\\nhello night\\n[chorus]\\nrun with me\",\"cot\":\"full\",\"seed\":831001}"}' \
  --output song.wav
# PASS looks like: HTTP 200, valid 48 kHz stereo wav, log "YuE2 synth done request=… samples=… duration=…s",
# DeepSelect/fast-sampler/step-graph active per the same gates. Remove with: git worktree remove /tmp/yue2-h800-check
```

Identical audio SHA256 is **not** expected across GPU vendors.

## 7. Known limitations

- ROCm uses reference paths only: no DeepSelect, no shared FA3 op, no fused decode — by design; performance optimization is explicitly out of scope for this patch.
- Pre-existing P2 (not this patch's scope, unchanged behavior): `batched.py` builds the batched DeepSelect sampler when an operator overrides `SGLANG_YUE2_BATCH_MAX_SIZE>=2` on ROCm; per-request fallback keeps outputs correct. A follow-up platform gate can close this.
- Verified on W7900 (gfx1100) only; other ROCm targets untested.

## 8. Request

Once the H800 check passes (or if the author prefers to verify during integration), please merge this small PR into `add_yue2` so dual-vendor support rides sgl-project/sglang-omni#2540. Happy to rebase, split, or adjust naming if you prefer a different integration shape.

