# W7900 (gfx1100) — SGLang-Omni YuE2 REAL HTTP E2E

Date: 2026-10-13 | Operator mission: safe GPU takeover → real HTTP E2E → upstream handoff

## Verdict

| Test | Result |
|---|---|
| GPU release (takeover) | **PASS** |
| SHORT_HTTP (smoke params) | **PASS** |
| FULL_CONFIG_HTTP | **PASS** |

## 1. GPU takeover (benchmark → mission)

- Benchmark: WildSongBench full run `wsbfull20261012T0041Z`, verified PARTIAL **311/384** pre-takeover (established verifier `verify_wsb_artifacts.py --mode full`).
- `kill -INT 404144` (driver) at 07:40:06Z → graceful handler finished in-flight candidate **[312/384] `wsb_155_r1_s831174` ok (277.91 s)**, `stopped_by_signal: true`, failed=0, pending=72.
- Supervisors finalized naturally: watcher + scheduler each committed a CPU-only checkpoint (`41427c7ae6769568bb3c4eea29490e5c328bec97` on `validation/gfx1100-rocm7141`); the scheduler's broad `pkill "sglang serve"` stage was **never reached** (requires 384/384 + FULL audit; run was 312/384).
- `kill -INT 70945` (old `sglang serve` YuE2-3B @127.0.0.1:31000) at 07:46:28Z → exited <45 s with its resource_tracker child.
- VRAM: **21,258 MiB → 26.7 MiB**; GPU util 100% → 0%. No GPU reset, no SIGKILL, no broad pkill, unrelated `watch rocm-smi` session untouched.

## 2. Environment

- GPU: AMD Radeon Pro W7900D, gfx1100, 47.98 GiB; ROCm 7.14.1 (hip 7.14.60850).
- torch 2.12.0+rocm7.14.1 / torchvision 0.27.0+rocm7.14.1 / torchaudio 2.11.0+rocm7.14.1; `torch.version.cuda is None`.
- Omni source: `AIwork4me/sglang-omni` @ **50c91c0888312ae784d3c42d9536665aa517dd9d** (= PR #1 patch) on author commit **85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9** (`add_yue2`).
- SGLang: **pristine upstream checkout (ccae40c, empty diff)** — the previous closure's finding holds: no SGLang compatibility patches are needed at runtime.
- Model `m-a-p/YuE2-3B@1a96eca`, VAE `YuE2-Vae-legacy@b54118f0` (local pinned copies).
- One environment-only fix: `pip install python-multipart` (undeclared dep required by omni's Form/File routes at import; packaging note for upstream, out of PR #1 scope).

## 3. Real server

```
SGLANG_YUE2_BATCH_MAX_SIZE=1 SGLANG_YUE2_VAE_DIR=.../YuE2-Vae-legacy \
sgl-omni serve --model-path .../YuE2-3B --host 127.0.0.1 --port 32100 --log-level info
```

`GET /health` → 200; `GET /v1/models` → YuE2-3B; placement log: `yue2_synth` on GPU 0 (W7900D).

## 4. HTTP requests (POST /v1/audio/speech)

Outer contract: `{model, voice:"default", input:<JSON-encoded YuE2 params>, response_format:"wav"}`.

### Short (smoke parameters)
seed 831001, cot full, cfg 1.0, abc 256, semantic 512, ode 8, vae_core 256, halo 16.
→ **HTTP 200, `audio/wav`**, 3,931,948 B, `x-finish-reason: stop`, wall ~30 s (synth elapsed 15.25 s).

### Full configuration
abc 4096, semantic 9000, ode 32, vae_core 1024, halo 16 (same seed/prompt).
→ **HTTP 200, `audio/wav`**, 9,069,868 B, wall 39 s (synth elapsed 38.11 s).
Note: token limits are upper bounds; the short prompt reached EOS naturally (47.24 s audio).

## 5. Independent audio decode (soundfile)

| | short | full |
|---|---|---|
| sample rate | 48,000 Hz | 48,000 Hz |
| channels | 2 (stereo) | 2 (stereo) |
| duration | 20.479 s | 47.239 s |
| RMS | 0.0860 | 0.1470 |
| peak | 0.7111 | 0.7762 |
| finite | yes | yes |
| SHA256 | `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed` | `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd` |

Short vs full waveforms differ (not cached output).

## 6. Real gfx1100 execution evidence

- rocm-smi trace: util 0→**100%** exactly spanning each request window; VRAM 21% loaded, 35% peak during generation.
- Server log: `YuE2 preprocessing request=… seed=831001 semantic_max_tokens=…` → `YuE2 synth done request=… samples=2267456 duration=47.24s elapsed=38.11s`.
- Code-path gates (patch 50c91c08): AR = looped reference generator (`song.py:44-51` disables DeepSelect step graph on ROCm); fast sampler off (`fastpath.py:75`); attention = native ATen varlen (`fa3.py:31-33` skips CUDA-only shared FA3 op); NAR = velocity graph via torch HIP graph API (executed ode_steps=32); VAE = real on-device decode.
- `torch.cuda` API on this box is HIP (device `AMD Radeon Pro W7900D`); no CUDA execution is claimed.

## 7. Benchmark preservation & resume

Safely paused at 312/384 (see `benchmark_pause.json`); immutable config hashes recorded; remote checkpoint `41427c7`. Resume prerequisites documented; hazard note: the scoring scheduler pkills `sglang serve` **by design** once 384/384 is reached — no unrelated sglang-serve may be running then.

## 8. Reviews

`reviews/omni_http/GPU_SAFETY_REVIEW.md`, `HTTP_E2E_REVIEW.md`, `UPSTREAM_REVIEW.md` — all **PASS**, zero P0/P1.
