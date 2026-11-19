# RC2_07 — Executable quickstart & command-to-receipt matrix (DRAFT for M8.1)

**Status: command audit executed CPU-side on this host at `16cd217`; the
fresh-clone end-to-end execution (M8.1) still requires the post-campaign GPU
window.** Every command below was checked for: file exists, flags match the
actual CLI parser, bash syntax valid. GPU-touching commands are marked and
were NOT run in this session (campaign protection).

## Command → receipt matrix

| # | Command (as documented) | Verified how | Receipt produced | Status |
|---|---|---|---|---|
| 1 | `python3 scripts/check_environment.py` | `--help` parse + file exists | stdout PASS/WARN per subsystem | VALID |
| 2 | `python3 scripts/download_pins.py --workspace $WS` | `--help` parse | pin-hash verification log | VALID |
| 3 | `bash scripts/campaign_ops/build_envA.sh` | file exists; `bash -n` clean | env A venv + build log | VALID (GPU at final assert) |
| 4 | `bash scripts/campaign_ops/evaluator_install.sh` | file exists; `bash -n` | frozen evaluator tree + manifest sha | VALID |
| 5 | `bash scripts/campaign_ops/build_envB.sh` | file exists; `bash -n` | env B venv | VALID (GPU at final assert) |
| 6 | `bash scripts/run_smoke_test.sh` | file exists; `bash -n` clean | smoke log (GPU checks + imports) | VALID (fixed in guide: was `.py`) |
| 7 | `bash scripts/serve_yue2_gfx1100.sh` | reviewed + live usage evidence (campaign server) | server log + torch-stack assert | VALID (GPU) |
| 8 | `curl -s localhost:31000/health` | used by launcher health poll | n/a | VALID |
| 9 | `armb_acceptance_request.py --server --out-dir` | flags match argparse; live receipt exists | acceptance_receipt.json (sha256, RMS, duration) | VALID (GPU) |
| 10 | `server_identity.py stop --receipt … --timeout 180` | flags match argparse; fixed broken `--yes-path:` text in guide | exit code semantics 0/2/3/4/5 | VALID (fixed) |
| 11 | `run_armA_campaign.sh` / `run_armB_campaign.sh` | live usage (Arm B running now) | run_config, journal, manifest | VALID (GPU) |
| 12 | `setsid nohup python3 scripts/campaign_ops/mission_chain.py > …` | live supervisor since Nov 18 | mission_state.json + mission_chain.log | VALID |
| 13 | `verify_wsb_artifacts.py --runs … [--mode full]` | `--help` parse (guide omits `--mode`; default is full — acceptable) | audit.json verdict FULL/PARTIAL | VALID |
| 14 | `verify_provenance.py --runs …` | `--help` parse | provenance report (0 violations) | VALID |
| 15 | `python -m wsb_metrics.wsb_eval score …` (old handoff doc) | **INVALID — non-package**; corrected in RC2 kit to `python wsb_metrics/wsb_eval.py score …` from WSB root | summary.json | FIXED |

## Fresh-clone checklist for M8.1 (to execute in the GPU window)

1. Clean workspace clone at the merged RC tag; `check_environment.py` PASS.
2. `download_pins.py` — all pin hashes verified.
3. build_envA + evaluator_install + build_envB — receipts archived.
4. Smoke (`run_smoke_test.sh`) + first complete song (native + SGLang).
5. Small pilot generation + `verify_wsb_artifacts.py --mode pilot` PILOT verdict.
6. Small pilot scoring + summary complete.
7. Kill server mid-pilot → journal resume-safe (RC2 fix: resumed rows count).
8. Correct shutdown + GPU release (`server_identity.py stop`; `gpu_lock.py status`).
9. Independent executor (not the script author) — record deviations, fix
   guide in-tree, never paper over.

## Security/licensing review carry-over (RC2_07_SECURITY_LICENSE_REVIEW.md)

- Working-tree guard PASS at `16cd217` (this session).
- Tier-2 real-dataset scan: M6 PASS (2026-11-19) on the same tree content;
  re-run at the M8.1 clone.
- Historical Git-object exposure: **owner legal decision, OPEN** (options
  a/b/c in 06_SECURITY_LICENSING_PROVENANCE.md; recommendation (a) for RC).
- No public lyrics/transcripts/audio: verified by guard + tier-2 + absence
  of binary media in `git ls-files`.
- New RC2 artifacts carry hashes/ids only (bundle manifest = sha256+bytes).
