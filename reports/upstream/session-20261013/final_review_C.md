# REVIEWER C — Evidence / Release Integrity (Final Independent Audit)

Date: 2026-10-13 | Mode: read-only (no benchmark process touched, no device init)

---

## 1. HTTP evidence chain — VERDICT: PASS

**client.log (short):** window 2026-10-13T08:12:17Z → 08:12:32Z (~15 s wall), `curl_rc=0`, 3839k received ≈ 3,931,948 bytes body.
**full_client.log:** window 08:19:02Z → 08:19:41Z (~39 s wall), `curl_rc=0`, 8857k received ≈ 9,069,868 bytes body.

**content-length == file size == audio bytes (exact):**
- `response.headers` content-length `3931948` == `response.body` size 3,931,948 == WAV frames 982,976 × (2ch × 2B) + 44 header = 3,931,948. RIFF parsed: 48,000 Hz, stereo, PCM16, 982,976 frames.
- `full_response.headers` content-length `9069868` == `full_response.body` size 9,069,868 == 2,267,456 × 4 + 44 = 9,069,868.

**x-request-id ↔ server.log:**
- `speech-9b3177ff-0f68-4b97-abfd-cf0e37a60490` → server.log:45,47 (preprocess 08:12:17.592; synth done 08:12:32.846, **samples=982976 elapsed=15.25s**), POST 200.
- `speech-ac6f8565-ee83-45a1-8085-84703b799659` → server.log:49,50 (preprocess 08:19:02.979; synth done 08:19:41.094, **samples=2267456 elapsed=38.11s**), POST 200.
- Request IDs and timestamps bracket-consistent with both client logs.

**gpu_trace.log:** samples 08:18:37–08:20:34 fully bracket the full-config window (08:19:02–08:19:41): util 0%→7% (08:19:02)→100% sustained 08:19:06–08:19:40→12% (08:19:43)→0%; VRAM 21%→35% at decode handoff. Real synth, real GPU.

## 2. Audio checksums — VERDICT: PASS

Recomputed now:
- `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed  response.body`
- `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd  full_response.body`

Both match `audio_validation.json` / `full_audio_validation.json` and the PR #1 body verbatim. Distinct files: sizes 3,931,948 vs 9,069,868; distinct MD5 (238cbc… vs 67e86c…); distinct RMS/peak. Not cached/duplicated output.

## 3. ROCm stack provenance — VERDICT: PASS

`env-omni-rocm/bin/python -c "import torch; print(torch.__version__, torch.version.hip)"` →
`2.12.0+rocm7.14.1 7.14.60850` — exactly as claimed. Plain attribute access only; no CUDA/HIP device init, no tensor ops (benchmark untouched).

## 4. Public/private artifact boundaries — VERDICT: PASS

Live PR #1 body contains zero links to private repos (grep for AIwork4me / YuE2-SGLang-ROCm / github.com URLs: none; only a localhost curl example). Essential evidence is IN the body: both full SHA256s, 20.479 s / 47.239 s durations, 48,000 Hz stereo rates, RMS 0.0860 / 0.1470. GPU-trace limitation for the short window honestly framed as inferential.

## 5. Missing-dependency disclosure — VERDICT: PASS

- PR body §5: `python-multipart==0.0.32` disclosed as **platform-neutral packaging gap**, intentionally out of scope.
- Posted comment (AIwork4me, 2026-10-13T11:38:28Z): same disclosure ("platform-neutral gap we'll raise separately, kept out of this PR").
- Local-only fix branch: worktree `/tmp/opencode/packaging-fix` at `daf1a1135d4d235218cae80e59c86ea8926402b1` ("fix(packaging): declare python-multipart runtime dependency…", author AIwork4me). Not on any origin remote (worktree `branch -r` shows no multipart branch).
- `gh api repos/AIwork4me/sglang-omni/branches/fix/declare-python-multipart` → **404 Branch not found**. Confirmed NOT pushed.

## 6. Benchmark safety — VERDICT: PASS

- All 4 processes alive and untouched: 493545 (`run_wsb.py`, elapsed 02:57:35), 487670 (env python, 03:22:05), 494130 (`watch_milestones.sh`), 494132 (`run_wsb_scoring.sh`).
- Live script md5 `c2384466607667cebd51a3a8b2f317b8` — unchanged (matches expected).
- Isolated fix present at `/tmp/opencode/scoring-fix/`: `pid-scoped-server-stop.patch`, `run_wsb_scoring.sh.fixed`, `run_wsb_scoring.sh.orig`, `README-scoring-fix.md`. Live script untouched.
- `generation_manifest.jsonl`: 1,297 lines, **364 unique ids**; latest-status complete/complete(resumed) = **345** (33 complete + 312 complete(resumed); 19 skipped(disk)). Matches the earlier verified count of 345 — no regression, no tampering.

## 7. GitHub remote status — VERDICT: PASS

- `evidence/omni-http-gfx1100` tip = `f000a8596af91f9ed102f42ddbe3fc5f3ff1d180` ("docs(omni-http): public-safe PR #1 handoff summary") — exact match.
- `repos/AIwork4me/YuE2-SGLang-ROCm` `.private` == `true` — evidence repo is PRIVATE.

## 8. Source provenance and copyright metadata — VERDICT: PASS

- `git log -1 --format='%an %ae' 50c91c08` → `AIwork4me AIwork4me@users.noreply.github.com`.
- `git show 50c91c08 | grep -i copyright` → empty (no copyright headers added; none introduced anywhere in the diff).
- `LICENSE` present at repo root (11,352 bytes).

---

## REVIEWER_C_VERDICT

| Section | Verdict |
|---|---|
| 1. HTTP evidence chain | PASS |
| 2. Audio checksums | PASS |
| 3. ROCm provenance | PASS |
| 4. Public/private boundaries | PASS |
| 5. Missing-dep disclosure | PASS |
| 6. Benchmark safety | PASS |
| 7. GitHub remote status | PASS |
| 8. Source provenance/copyright | PASS |

**REVIEWER_C_VERDICT: PASS** (overall, 8/8 sections)
