# 04 — SGLang Validation (Phase 4, interim)

**Date:** 2026-11-12 (interim; updated as acceptance completes) · **Hardware:** W7900D gfx1100 · **Stack:** SGLang PR #42106 @ `ced0ef7d` + patches 0001-0005, 0008 · torch 2.12.0+rocm7.14.1

## Verified this session

| Item | Result | Evidence |
|---|---|---|
| Environment install (`setup_gfx1100_rocm7141.sh` + `setup_sglang_gfx1100.sh`) | PASS (guards held; CUDA-torch build-isolation hazard caught+mitigated) | /data/yue2/logs/setup_gfx1100.log, RCA-3 |
| Server startup + readiness (`/health`) | PASS (127.0.0.1:31000) | serve log |
| Short generation (12 s audio) | PASS: 48 kHz stereo, finite, RMS 0.155, full artifact bundle (plan/abc/prefix/semantic/latent/flac) | /data/yue2-runs/sglang_smoke |
| Full-song generation under official budget | PASS ×22+ (campaign in flight; ~246 s median/candidate) | armB progress.jsonl |
| Long-lyrics input | IN PROGRESS via campaign (official prompts include the longest lyrics in the bench) | pending full-run receipts |
| Repeated requests / determinism | PASS historically; fresh seed-determinism check scheduled with campaign samples | historical evidence + pending |
| Concurrent clients | PENDING (post-campaign window) | — |
| Interruption/restart | PASS (driver restart + verified resume observed live during RCA-9) | campaign2 log |
| Malformed requests | PASS (test_server_yue2_rocm.py invalid-field matrix executed historically; fresh run scheduled) | tests/ |
| Output integrity | PASS (official verify_result over every candidate) | campaign journal |
| Model identity | PASS (sha256-asserted at load; run_config pins) | run_config.json |
| VRAM accounting | idle ~11 GiB observed; generating peak re-measurement pending | rocm-smi receipts |
| Shutdown/cleanup | PENDING (chained after campaign) | — |

## prompt-164 long-lyrics field-limit regression

Scheduled against the current tree during the post-campaign acceptance
window (historical validation exists; mission requires re-validation on the
fresh stack). No temporary exemptions.

## Omni secondary path

sglang-omni #2540 regression (incl. `/v1/audio/speech`) queued behind the
primary campaigns; historical 384/384 evidence remains on the validation
branch.
