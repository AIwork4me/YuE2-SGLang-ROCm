# PHASE 4 Independent Review — First End-to-End Audio Generation

**Reviewer:** independent verification subagent
**Date:** 2026-10-11
**Scope:** `reports/PHASE4_FIRST_AUDIO.md` and all Phase 4 artifacts
**Method:** every check below was re-executed from scratch by this reviewer (fresh
hashes, fresh soundfile decode, fresh pytest run, fresh HTTP probe). Nothing was
taken on trust from the implementer's own numbers except where explicitly noted.

## Verdict

# PASS

## Independent verification results

### 1. Hashes and determinism — PASS

Recomputed `sha256sum` over all four wavs; comparison with
`evidence/first_audio.sha256`:

| File | Recomputed sha256 | Matches evidence |
|---|---|---|
| full1.wav | `17860c64cb1cb8a13f4c5d5127e8a25fe8f3e19b006ea2b420851caedb1d81d2` | yes |
| full1_repeat.wav | `17860c64cb1cb8a13f4c5d5127e8a25fe8f3e19b006ea2b420851caedb1d81d2` | yes |
| smoke1.wav | `b204a0556b9696ea4b76fc8566595f81a64e73eb26528f99407491bb76692882` | yes |
| alias1.wav | `fb6b2eea50212ab0f11f2b72bff277ff0945c35a3d034be00e5fdf0f61f210fc` | yes |

`cmp full1.wav full1_repeat.wav` → byte-identical (also confirmed by the
identical digests). Same-seed identity claim reproduced.

### 2. Independent audio decode (soundfile, yue2 venv) — PASS

| File | sr | ch | duration (s) | rms | peak | finite | clipfrac | samples > 0.1 |
|---|---|---|---|---|---|---|---|---|
| smoke1 | 48000 | 2 | 11.9987 | 0.0957 | 0.6239 | yes | 0.0 | 284,040 |
| full1 | 48000 | 2 | 68.7587 | 0.1088 | 0.7131 | yes | 0.0 | 1,841,945 |
| full1_repeat | 48000 | 2 | 68.7587 | 0.1088 | 0.7131 | yes | 0.0 | 1,841,945 |
| alias1 | 48000 | 2 | 3.9987 | 0.0507 | 0.3254 | yes | 0.0 | 21,412 |

- Sample rate 48000 and 2 channels: all four. ✓
- Finite (no NaN/Inf), zero clipping (max |x| = 0.7131 ≤ 0.999), positive
  durations. ✓
- RMS in the reported 0.051–0.109 range (0.0507–0.1088 measured). ✓

### 3. plan.json content — PASS

`runs/phase4/full1_artifacts/plan.json`:
- `request.seed == 831001`, `request.cot == "full"`, top-level
  `truncated == false`. ✓
- `timing.abc`: seconds 20.673, output_tokens 607, `sampler=reference`,
  `execution=cuda_graph`, `attention=flash`, truncated false. ✓
- `timing.semantic`: seconds 82.259, output_tokens 1720 (content 1719),
  same sampler/execution/attention triple, transition_seconds present. ✓
- Token/duration consistency: 1720 tokens ÷ 25 fps = 68.80 s vs measured wav
  duration 68.7587 s → |Δ| = 0.041 s, well within the 2 s tolerance. ✓
- Cross-checked against `.npy` payloads: `semantic.npy` (1719, int32),
  `abc_tokens.npy` (606, int32), `prefix.npy` (736, int32),
  `latent.npy` (1719×64 float32, finite) — all match plan token counts
  (output_tokens include the terminal token). ✓

### 4. plan_manifest.json hashes — PASS

Recomputed and compared (`sha256sum` in `full1_artifacts/`):

| File | Manifest | Recomputed | Match |
|---|---|---|---|
| plan.json | `ebeb0b04…598aa` | `ebeb0b0458dd554e8fb97ed078f7d3babae668a73a490d67d71cd24902b598aa` | yes |
| abc_tokens.npy | `eff8cd3a…f670` | `eff8cd3a16733ad9d6ae55ace50b294ba42c3cb183eac149a9675effd698f670` | yes |
| prefix.npy | `8525f81b…8bdae` | `8525f81bad5e5c507849d775f1a66b9e47f7bf8c394f68722ee620ae7e78bdae` | yes |

### 5. Test suite — PASS

`python -m pytest tests/test_first_audio.py -v` (yue2 venv): **6/6 passed**
in 0.24 s. The tests read the real server-produced files (absolute paths, no
fixtures) and assert the same properties verified manually above, including
the 25 fps duration consistency and the sampler/execution/attention triple.

### 6. Not silence / not corruption — PASS

- Far more than 1000 samples above 0.1 amplitude in every file (21,412 –
  1,841,945). ✓
- File sizes exactly match PCM16-stereo expectations for their durations
  (e.g. full1: 13,201,708 B = 44 + 3,300,416×4). ✓
- Spectral centroids (reviewer-computed STFT): means 1.5–3.4 kHz with wide
  per-window spread (≈0.4–13.7 kHz) — broadband, music-like content, not
  tone/noise/corruption signatures. ✓

### 7. Server log inspection — PASS

`logs/server_yue2.log` contains exactly four generation requests in the Phase 4
window, all `200 OK`:
- 19:24:51 `POST /v1/audio/generations` (smoke1; VAE decode 42.87 s; total 64.25 s)
- 19:30:44 `POST /v1/audio/generations` (full1; AR 82.31 s, NAR 27.50 s,
  VAE 228.07 s, total 337.89 s — matches report/plan within rounding)
- 19:33:13 `POST /v1/audio/generations` (full1_repeat)
- 19:33:35 `POST /v1/audio/music/generations` (alias1)

`grep -ic error` → 0 hits. Warnings present are benign and disclosed:
MIOpen `IsEnoughWorkspace` notes, startup skips of unrelated pipelines
(hunyuan3d/ming/pi05; missing `cv2`/`sgl_kernel`), and a torch `weight_norm`
FutureWarning. File mtimes line up with the logged request completions.

### 8. Serve script and quality-parameter hygiene — PASS

`scripts/serve_yue2_rocm.sh`:
- `VAE_PATH` defaults to `$WS/models/YuE2-Vae-legacy`; `protocol_lock.json`
  pins it to `m-a-p/YuE2-Vae-legacy` (sha256 verified) and explicitly notes it
  is NOT the non-legacy `m-a-p/YuE2-Vae`. ✓
- Exports only the Phase 3 ROCm correctness flags (`FAST_SAMPLER / STEP_GRAPH /
  FUSED_DECODE / FAST_NAR / FA3 / BATCHED_AR = 0`, `SESSION=1`, `GRAPH_POOL=1`).
  No `ode_steps`, sampling, token-budget, or VAE quality defaults are set at
  the server level; the full1 log shows `infer_steps: 32` arriving per-request,
  and `request.json`/`plan.json` carry no budget overrides. Server defaults
  untouched. ✓

### 9. Live probe request — PASS

Server `/health` up. Sent one minimal request (`ode_steps=2`,
`semantic_max_tokens=50`, `abc_max_tokens=64`, `vae_core_frames=256`,
`cot=full`, seed 424242, `output_file_name=review_probe.wav`):
- HTTP **200** in 10.57 s; response reported `sample_rate: 48000`.
- Output `runs/phase4/review_probe.wav`: 48 kHz, stereo, 1.9987 s, rms 0.1156,
  peak 0.5933, finite, clipfrac 0.0, 60,576 samples > 0.1,
  sha256 `1ce12dce7eb15a0c251452431301728e3acfbf5e8da54c6af35375e67a6e88db`.
- Response also reproduced the disclosed upstream gap: `peak_memory_mb: 0.0`.

## Issues

- **P0:** none.
- **P1:** none.
- **P2:** none.
- **P3-1:** Report §3 prose says "NAR+VAE ≈ remaining ~235 s of full1 wall";
  the log gives 27.50 + 228.07 = 255.6 s (337.89 − 82.31). The ~20 s
  understatement is cosmetic — metadata JSON and server log carry correct
  values — but the sentence should read ~256 s.
- **P3-2:** `plan.json` records an identical `prefill_seconds`
  (0.18240326400155027) for both the abc and semantic stages, which looks like
  a reused/cumulative measurement rather than two independent prefills. Does
  not affect any gated metric (seconds and token counts verified against the
  server log), worth a one-line upstream note.
- **P3-3:** `peak_memory_mb` always returns 0.0 (not wired in the PR build) —
  correctly disclosed in report and metadata; reviewer's probe reproduced it.
  Report's "peaks ≤ 0.71" is a rounding of the exact 0.7131 in
  `first_audio_metadata.json`.

## Conclusion

Every claim in `PHASE4_FIRST_AUDIO.md` that this reviewer could recompute was
reproduced: hashes, byte-identical repeat, audio validity metrics, artifact
bundle integrity, test results, HTTP 200s on both routes, backend triple
(reference/cuda_graph/flash), benchmark VAE, and a fresh live probe. Only three
P3-level documentation/measurement nits were found. **PASS.**
