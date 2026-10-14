# Phase 2 — Independent Evidence Reconciliation (omni-http gfx1100)

Auditor: independent, read-only (writes confined to /tmp/opencode/).
Toolchain: /opt/venv/bin/python3 (soundfile 0.13.1, numpy 2.1.2 — verified installed).
Date: 2026-10-13. Raw artifacts under /workspace/yue2-omni-pr/http-e2e/; evidence repo /workspace/yue2-sglang-rocm-w7900/evidence-repo, branch evidence/omni-http-gfx1100.

## 1. Independent recomputation vs claims (raw bodies)

### response.body (short)
| Metric | Claim | Recomputed | Match |
|---|---|---|---|
| HTTP status | 200 | headers: `HTTP/1.1 200 OK` | YES |
| SHA256 | 358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed | identical | YES (exact) |
| bytes | 3,931,948 | 3,931,948 | YES |
| content-length | — | 3931948 = file size | YES |
| sample rate / ch | 48000 / stereo | 48000 / 2 | YES |
| frames | 982,976 | 982,976 | YES |
| duration | 20.479 s | 20.478667 s | YES |
| RMS | 0.08595326886256857 | 0.08595326886256857 | YES (exact, 17 digits) |
| peak | 0.711090087890625 | 0.711090087890625 | YES (exact) |

RIFF header genuine: `RIFF`/`WAVE`, fmt chunk size 16, audio format **1 (PCM)**, 2 ch, 48000 Hz, byterate 192000, blockalign 4, **16-bit**; `data` chunk size 3,931,904. Byte math: 44 + 982976 × 2ch × 2B = 3,931,948 = content-length = file size. No truncation, no padding.

### full_response.body (full config)
| Metric | Claim | Recomputed | Match |
|---|---|---|---|
| HTTP status | 200 | `HTTP/1.1 200 OK` | YES |
| SHA256 | 218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd | identical | YES (exact) |
| bytes | 9,069,868 | 9,069,868 | YES |
| frames | 2,267,456 | 2,267,456 | YES |
| duration | 47.239 s | 47.238667 s | YES |
| RMS | 0.147005 | 0.14700527320346468 | YES (claim is truncation) |
| peak | 0.776245 | 0.776245117187500 | YES (claim is truncation) |

RIFF header genuine PCM16 stereo 48 kHz; 44 + 2267456 × 4 = 9,069,868 = content-length = file size.

Both bodies finite (np.isfinite all true). Waveforms distinct: lengths differ; on the common 982,976-frame span max|Δ| = 0.9702, corr = 0.4322 → **not cached output** despite identical seed 831001. (HTTP_E2E_REVIEW.md states corr=0.40 — minor methodological difference, immaterial to the distinctness conclusion.)

## 2. Headers, logs, IDs, timings
- Headers: both `content-type: audio/wav`, `content-disposition: attachment; filename="speech.wav"`, `x-finish-reason: stop` (supports natural-EOS claim), `server: uvicorn`, `x-request-id` present.
- x-request-id ↔ server.log (verbatim match, both requests):
  - short `speech-9b3177ff-0f68-4b97-abfd-cf0e37a60490` — preprocessing 08:12:17.592 (seed=831001, semantic_max_tokens=512) → synth done 08:12:32.846 **samples=982976 duration=20.48s elapsed=15.25s**.
  - full `speech-ac6f8565-ee83-45a1-8085-84703b799659` — preprocessing 08:19:02.979 (seed=831001, semantic_max_tokens=9000) → synth done 08:19:41.094 **samples=2267456 duration=47.24s elapsed=38.11s**.
- Cross-checks: sample counts 982,976 / 2,267,456 ✓; elapsed 15.25 s / 38.11 s ✓; seed 831001 ✓ (both requests and both request.json bodies).
- client.log wall clocks: 08:12:17→08:12:32 (15 s; matches corrected request_wall_s=15 in smoke_response.json) and 08:19:02→08:19:41 (39 s); curl_rc=0 both.
- server.log placement: GPU 0 'AMD Radeon Pro W7900D' 47.98 GiB; /health 200; /v1/models 200; launch.sh matches the documented command (SGLANG_YUE2_BATCH_MAX_SIZE=1, VAE_DIR YuE2-Vae-legacy, port 32100).

## 3. GPU trace
gpu_trace.log spans 08:18:37 → 08:20:34 and **fully brackets the full-config window** (08:19:02.979 → 08:19:41.094): util 7% at 08:19:02 → 97–100% sustained through 08:19:40 → 12% at 08:19:43 → 0% by 08:19:47. VRAM 21% baseline → 35% during generation (VAE decode), persists at 35% (cache retention) — consistent with claims. **The trace does NOT cover the 08:12 short-request window** (monitor restarted 08:18:37 after tooling fault — honestly disclosed in smoke_response.json gpu_trace_note; short-window GPU utilization is inferential from server.log synth elapsed on the same server instance).

## 4. Environment & source (independently re-verified live)
- Live torch check in env-omni-rocm venv: torch 2.12.0+rocm7.14.1; cuda.is_available() True (HIP aliasing); version.hip 7.14.60850; version.cuda None; device0 "AMD Radeon Pro W7900D"; capability (11,0) gfx1100 — matches environment.json exactly.
- omni repo: HEAD 50c91c0888312ae784d3c42d9536665aa517dd9d, parent 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9 ✓; worktree clean ✓; diff vs base = 5 files, +237/−6 (matches UPSTREAM_REVIEW) ✓.
- sglang-src: HEAD ccae40c, `git diff` empty → **pristine, no source patch** ✓.
- Code gates verified in source at cited locations: song.py ~41–56 (step-graph requires `not current_platform.is_rocm()`; ROCm → looped reference AR); fa3.py:31–33 (skips shared FA3/flash_attn op on ROCm); fastpath.py:75 (fast sampler / DeepSelect off on ROCm); stages.py:46,59 (`is_cuda() or is_rocm()`, batch default "1" on ROCm / "4" CUDA).
- python-multipart: environment.json records pip install only, no code change — platform-neutral, consistent with brief.

## 5. Benchmark artifacts (§7 support)
- runs/gfx1100/wsbfull20261012T0041Z/wsb_full/audit.json: **verified_complete = 312** ✓ (claim 312/384).
- Immutable config hashes recomputed: run_config.json → 806eb07511d9f7ab6eb08046b0f14b9c27331ce38bd5b36d9e3da4b83aac2361 ✓; evaluation_inputs.jsonl → a906ab391bf80992549fafd4b1261ec335963736d67fd790d30c39d588ac100 ✓ (exact match to benchmark_pause.json).
- validation/gfx1100-rocm7141 tip = 41427c7ae6769568bb3c4eea29490e5c328bec97 ✓ (remote_checkpoint_sha).
- Resume: benchmark_resume.json documents venv-relaunch incident + [313/384] wsb_156_r0 ok after resume — internally consistent with commit dd09618 message.

## 6. Commit-citation question (dd09618 vs tip f000a85)
- `git rev-parse dd09618` = dd09618783400c35f976b2f3fe1bdf97ff12f37e — the SHA cited in PR1_HANDOFF_SUMMARY.md is accurate and resolves.
- Branch tip f000a85 ("docs(omni-http): public-safe PR #1 handoff summary") changed exactly one file: +39 lines, PR1_HANDOFF_SUMMARY.md itself.
- **Determination: NOT a material inconsistency.** Every artifact the summary cites (JSONs, report, reviews) already exists at dd09618; the tip commit adds only the summary. A document cannot contain the hash of the commit that introduces it without an amend loop. Classification: stale-by-one self-reference, cosmetic. Optional correction before PR body update: annotate "(evidence through dd09618; this summary added in f000a85)" or bump citation on next evidence commit.

## 7. Claim-by-claim verdicts

### GFX1100_HTTP_E2E.md §5 (audio decode)
| Claim | Verdict |
|---|---|
| short: 48000 Hz, stereo, 20.479 s | SUPPORTED (exact recompute) |
| full: 48000 Hz, stereo, 47.239 s | SUPPORTED |
| RMS 0.0860 / 0.1470 | SUPPORTED (0.08595… / 0.14700527…) |
| peak 0.7111 / 0.7762 | SUPPORTED (0.711090… / 0.77624511…) |
| finite yes/yes | SUPPORTED |
| SHA256s (both) | SUPPORTED (bit-exact) |
| short vs full waveforms differ (not cached) | SUPPORTED (max|Δ|=0.97, corr=0.43, lengths differ) |

### GFX1100_HTTP_E2E.md §6 (gfx1100 execution)
| Claim | Verdict |
|---|---|
| rocm-smi util 0→100% "exactly spanning **each** request window" | **PARTIALLY SUPPORTED / OVERSTATED** — trace brackets the FULL window only; short window not traced (INFERENTIAL for short; disclosed in smoke_response.json, not in this report) |
| VRAM 21% loaded, 35% peak during generation | SUPPORTED |
| server.log synth lines (samples, durations, elapsed) | SUPPORTED (verbatim) |
| code-path gates: looped AR, fast sampler off, ATen varlen, HIP graph NAR ode_steps=32, real VAE decode | SUPPORTED (source lines verified; ode_steps=32 in request + executed per server log) |
| torch.cuda API is HIP on this box; no CUDA execution claimed | SUPPORTED (live recheck: version.cuda None, device W7900D) |

### GFX1100_HTTP_E2E.md §7 (benchmark preservation)
| Claim | Verdict |
|---|---|
| safely paused 312/384, benchmark_pause.json | SUPPORTED (audit.json verified_complete=312) |
| immutable config hashes recorded | SUPPORTED (recomputed, exact) |
| remote checkpoint 41427c7 | SUPPORTED (branch tip matches) |
| resume prerequisites documented | SUPPORTED (pause + resume JSONs; [313/384] ok) |
| hazard note (scheduler pkills sglang serve at 384/384) | SUPPORTED (warning field present) |

### PR1_HANDOFF_SUMMARY.md
| Claim | Verdict |
|---|---|
| prior work 12/12 platform, 37/37 capability, 51-case CUDA A/B equivalent, pristine import chain | INFERENTIAL (recorded on validation branch/prior reviews; not re-executed this audit; no contradicting evidence found) |
| server sgl-omni serve, POST /v1/audio/speech | SUPPORTED |
| patch 50c91c08 on author base 85ae4b73 | SUPPORTED (git) |
| SGLang pristine, no runtime patches | SUPPORTED (empty diff) |
| short: 200 audio/wav, 48 kHz stereo, 20.479 s, RMS 0.086, SHA 358ffc66…2feed | SUPPORTED |
| full: 200, 47.239 s, RMS 0.147, SHA 218634d4…26bd; distinct waveforms | SUPPORTED |
| gfx1100 proven: GPU util 0→100% bracketing requests, rocm-smi trace, synth logs, code gates, no CUDA claim | SUPPORTED for full window; short window INFERENTIAL (trace gap — same overstatement caveat as §6) |
| three reviews PASS, zero P0/P1 | SUPPORTED (three review files read; verdicts PASS; only P2/info findings) |
| H800 smoke outstanding (no NVIDIA run claimed) | SUPPORTED (consistent with allowed-claims: H800 NOT VERIFIED, no bit-identical claim anywhere) |
| python-multipart undeclared omni dep note | SUPPORTED (environment.json; platform-neutral) |
| evidence commit citation dd09618 (tip is f000a85) | NOT an inconsistency — stale-by-one self-reference; optional annotation (see §6 above) |

## 8. Discrepancies found
1. §6 wording "util 0→100% exactly spanning each request window" overstates: trace covers only the full-config window. Disclosed in smoke_response.json and HTTP_E2E_REVIEW.md, but GFX1100_HTTP_E2E.md itself does not carry the caveat. → Correction: add "(full-config window; smoke window inferential)" in §6 / PR body.
2. HTTP_E2E_REVIEW.md reports corr=0.40 vs my 0.4322 (different method/rounding) — immaterial informational stat.
3. dd09618 citation vs tip f000a85 — stale-by-one self-reference, cosmetic (see §6).
No numeric mismatches in any claimed metric: every SHA256, byte count, frame count, RMS, peak, duration, request-id, sample count, elapsed, seed, and config hash reconciles exactly.

## PHASE2_VERDICT: PASS

Rationale: all quantitative claims in GFX1100_HTTP_E2E.md §5–§7 and PR1_HANDOFF_SUMMARY.md reconcile bit-exactly against independent recomputation from raw bodies, live environment checks, source-tree state, and benchmark artifacts; the three reviews are genuinely recorded as PASS with zero P0/P1; claims posture (W7900 verified, simulated-CUDA equivalence only, H800 not verified, no bit-identical claim) is accurately stated.
Corrections required before PR body update (both cosmetic, non-blocking):
1. Qualify the GPU-trace claim as covering the full-config window only (smoke-window utilization inferential) wherever "each request window" / "bracketing requests" appears.
2. Optionally annotate the evidence-commit citation (evidence through dd09618; summary added in f000a85).
