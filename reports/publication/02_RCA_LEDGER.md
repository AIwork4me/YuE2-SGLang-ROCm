# 02 — Root-Cause Audit Ledger (Phase 2)

Format per mission §2.2: severity, reproduction, root cause, fix, tests, evidence, residual risk.
Status legend: FIXED / MITIGATED / DOCUMENTED / OPEN.

---

## RCA-1 — Inconsistent workspace resolution (mission Issue A)

- **Severity:** High (breaks every fresh-clone workflow)
- **Reproduction (baseline):** `python -c "import scripts.run_wsb"` from a standalone clone → `WS` silently becomes the directory ABOVE the repo; any manifest read fails or, worse, writes to unintended paths. Baseline `pytest tests/test_verify_wsb_artifacts.py` → collection-time `FileNotFoundError` (observed live this mission).
- **Root cause:** module-level `Path(__file__).resolve().parents[2]` assumed the historical `<ws>/<repo>/scripts/` nesting; in a standalone clone `parents[2]` escapes the repository. Five call sites.
- **Fix:** single contract `scripts/yue2_workspace.py` (env override → repo root if it holds assets → historical layout), strict re-resolution inside `main()`, import-safe for unit tests. All five call sites migrated; `download_pins.py` bootstrap semantics documented.
- **Tests:** `tests/test_workspace_resolution.py` (9 tests incl. a documented historical-defect regression and arbitrary-CWD execution).
- **Evidence:** 63 passed / 24 honest skips pre-push; commit `6f87469`.
- **Residual risk:** LOW — historical layout verified equivalent when it exists.

## RCA-2 — Scoring environment mismatch (Issue B)

- **Severity:** High (official scoring unrunnable on W7900)
- **Reproduction (baseline):** `bash scripts/run_official_eval.sh <runs>` defaults `WS=/home/amd/Desktop/YuE2` (absent here) and hardcodes venv `environments/yue2`, while the W7900 installer creates `environments/yue2-gfx1100`.
- **Root cause:** machine-specific defaults from the gfx1151 campaign leaked into the shared entry point; relative `cd` before resolving the run directory.
- **Fix:** workspace-contract default; `RUNS` canonicalized to an absolute path before any `cd`; evaluator venv discovery (`yue2-gfx1100`/`yue2`, `YUE2_EVAL_VENV` override); evaluator-tree location probe; auditor invoked from the repo's scripts dir.
- **Tests:** bash -n; live execution during pilot scoring (this mission).
- **Residual risk:** LOW.

## RCA-3 — CUDA-torch replacement hazard (Issue C)

- **Severity:** Critical if undetected (silently swaps the compute backend)
- **Reproduction (live, this mission):** `pip install --no-deps -e <sglang>` inside the ROCm venv triggered pip BUILD ISOLATION, which downloaded sglang's build requirements including **torch==2.14.1 CUDA + the entire CUDA toolkit wheel set** (failed only because /tmp tmpfs filled: `OSError: [Errno 28] No space left on device`). The real venv stayed clean (verified: torch 2.12.0+rocm7.14.1 intact).
- **Root cause:** `--no-deps` constrains the install graph but NOT pip's isolated build environment; sglang's `pyproject.toml` build requirements pin CUDA torch.
- **Fix:** `--no-build-isolation` (+ TMPDIR on the large volume) in `scripts/setup_sglang_gfx1100.sh` with an explanatory comment; torch-stack guard retained before/after.
- **Tests:** installer guard asserts exact torch version before and after; live rerun installed sglang cleanly.
- **Residual risk:** LOW — documented pattern for all future editable installs.

## RCA-4 — Incomplete CI coverage + stale test API drift (Issue D)

- **Severity:** High (release gate credibility)
- **Reproduction (baseline):** CI ran 2 of 8 test files; `test_verify_wsb_artifacts.py` could not even be collected outside the historical machine; committed tests targeted an auditor API one generation older than the committed auditor (missing `classification`/`identity_reverified`, `--mode subset` vs `pilot`).
- **Root cause:** the campaign machine's auditor evolved (v2→campaign schema) but only a simplified v2 was committed; tests were never re-run in CI.
- **Fix:** auditor v3 restores the campaign receipt schema (cross-checked against `evidence/final_generation_audit.json`: classification, identity_reverified=384, expected_prompt_indices=192) plus identity-recompute forgery detection and driver-journal cross-check; test file aligned; CI expanded (compile scripts+supervisor, shellcheck errors-blocking, full CPU suite, docs contract, protocol-lock consistency). Manifest-dependent tests SKIP with actionable messages, never silently pass.
- **Tests:** 63 passed / 24 honest skips on a pristine checkout; 59+ with workspace materialized.
- **Evidence:** commits `6f87469`, `3bd848c`, `dd18a61`.
- **Residual risk:** MEDIUM-LOW — GPU/live-server tests remain hardware-only by design (CI never claims them).

## RCA-5 — Download/extraction safety (Issue E)

- **Severity:** Medium
- **Reproduction:** `download_pins.py` used `tarfile.extractall()` without member validation (pre-3.12 semantics).
- **Root cause:** predates Python 3.12 `filter="data"`; source is a pinned codeload tarball (hash-recorded) but extraction hardening was still due.
- **Fix:** explicit member/link path-traversal rejection + `filter="data"` (commit `6f87469`).
- **Tests:** unit test for the contract file set; live extraction performed during this mission's SGLang tree build.
- **Residual risk:** LOW.

## RCA-6 — Official torch backend broken on ROCm (new, Phase 3 blocker → root-caused)

- **Severity:** High (blocks the official benchmark Arm A)
- **Reproduction (live):** `code/generate.py --backend torch --prompt-index 0` → `RuntimeError: [ROCm] mha_varlen_fwd: seqused_k must be nullopt` (both candidates failed identically).
- **Root cause (smallest explanation):** `yue2/cuda_graph.py` selects attention_backend="flash" when `torch.ops.aten._flash_attention_forward` exposes `seqused_k` in its schema — true on ROCm builds — but the underlying HIP kernel does not implement it. Capability probe checks schema presence, not kernel capability.
- **Fix:** none required for the benchmark: `--backend torch-eager` is an official CLI choice that uses the public-SDPA path documented for AMD ROCm in official docs/hardware.md. Pilot then completed 2/2 candidates (191.3s + 154.8s audio, no truncation). DEV-1 disclosure recorded in `configs/benchmark.lock.yaml`. Minimal upstream patch idea (runtime probe call) prepared for owner-approved upstream submission.
- **Tests:** pilot generation receipt `/data/yue2-runs/armA_pilot0/generation_report.json` (complete=true).
- **Residual risk:** MEDIUM — kernel-selection numerics differ from CUDA graph path; disclosed, not hidden.

## RCA-7 — Evaluator asset downloader vs egress proxy (new, environment)

- **Severity:** Medium (blocks scoring on this host class)
- **Reproduction (live):** `wsb_eval.py prepare --download huggingface` → 40/43 pinned files fail with `Tunnel connection failed: 503`; the hf-mirror path stalls outright. Same proxy intermittency observed for git pushes (503 on CONNECT).
- **Root cause:** evaluator downloader uses raw `urllib` without retry/range support; the site egress proxy rejects or stalls large CDN responses, while `huggingface_hub` (requests + resume + chunking) succeeds through the same proxy (proven by the 7.3 GB model snapshot).
- **Fix:** `scripts/fetch_eval_assets_hub.py` — hub-based fetch honoring the exact pinned inventory (repo/revision/file/sha256/bytes) into the evaluator's expected paths; evaluator code untouched; `verify_assets()` re-run afterwards.
- **Tests:** file-level sha256 verification is the test; receipt written to the evaluator's validation dir.
- **Residual risk:** LOW — retry-tolerant path documented for this host class.

## RCA-8 — Historical evidence retention (Issue F)

- **Severity:** High if violated
- **Status:** SATISFIED / GUARDED — historical `evidence/` trees byte-identical (git diff clean vs `main`); all new mission evidence under `evidence/publication/`, `reports/publication/`; per-song analysis this mission read historical JSONL read-only.
- **Residual risk:** LOW (enforced by review + git).

---

### Open items (tracked, not fixed yet)

| # | Item | Plan |
|---|---|---|
| O-1 | `/tmp` 4GB tmpfs too small for pip builds | TMPDIR=/data/tmp documented in installers; not a repo fix |
| O-2 | proxy 503 intermittency for git push | retry pattern; pushes batched |
| O-3 | prompt-164 long-lyrics Omni field limit re-validation | scheduled with Omni regression pass |

---

## RCA-10 — SGLang server AR-stage hang (fresh stack, this mission)

- **Severity:** High (campaign stalls; GPU idle with VRAM held)
- **Reproduction (live):** candidate wsb_017_r0 generation: server AR stage started 03:26:47Z and never advanced (>75 min; GPU use 0%, VRAM 39% held); driver timed out and retried into the same hung server. Historical campaigns show analogous interruptions (milestone_driver_exit receipts), which is why the supervisor infrastructure exists.
- **Root cause:** not yet isolated — requires the server-side stack around the hang (captured in server_yue2_gfx1100.log); candidate hypotheses: HIP graph replay stall, scheduler queue deadlock, or a rare sampling-path edge on ROCm. NOT a kernel numerics issue (34 candidates before/after succeeded byte-consistently).
- **Fix (operational):** stall-guard added to the campaign chain — no progress for 45 min ⇒ PID-scoped driver+server restart, GPU freed, health-verified resume. Campaign is resume-safe (verified skip of 42/42 completed candidates).
- **Tests:** the supervisor's restart matrix (test_scoring_v2) already covers safe-stop semantics; the stall guard is ops-layer (chain script), documented here.
- **Evidence:** /data/yue2/logs/{armB_campaign2.log,server_yue2_gfx1100.log,campaign_chain.log}
- **Residual risk:** MEDIUM — recurrence auto-recovers but costs wall time; upstream RCA deferred until campaign completion (server log preserved).
