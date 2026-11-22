# RC4 M5.2 — CI & GPU Regression Results

Local execution on the RC4 branch (W7900D host). Status vocabulary:
PASS / FAIL / SKIPPED / NOT_TESTED / BLOCKED_EXTERNAL.

## CPU suites

| Suite | Command | Result |
|---|---|---|
| CI-scope canonical | `pytest tests -q --ignore=test_yue2_rocm_fallbacks --ignore=test_server_yue2_rocm --ignore=test_first_audio` | **367 passed, 0 failed**, 26 skipped (honest manifest skips) |
| Manifest-dependent (with `YUE2_WORKSPACE=/data/rc4/ws`) | `pytest tests/test_verify_wsb_artifacts.py tests/test_wsb_full_mode.py` | **26 passed** |
| Resume/crash-safety | `pytest tests/test_wsb_resume.py` | **7 passed** (after the finalize-interpreter fix) |
| Provenance | `pytest tests/test_c2_provenance.py` | **35 passed** |
| Selection tie (new) | `pytest tests/test_selection_tie_semantics.py` | **5 passed** (incl. frozen 192/192 identity check) |
| compileall changed scripts | `python -m py_compile scripts/rc4_*.py scripts/run_wsb.py scripts/verify_wsb_artifacts.py scripts/server_identity.py scripts/fetch_eval_assets_hub.py scripts/per_cross_arm_analysis.py scripts/rc2_per_length_analysis.py` | PASS |
| Shell syntax | `bash -n` on every changed/added shell script | PASS |
| Whitespace/conflict | `git diff --check` | PASS |

## Public evidence guards (final tree)

- Tier-1 `public_evidence_guard.py`: **PASS**
- Tier-2 `evidence_lyrics_detector.py --ref HEAD`: **PASS** (408 files, 1813 windows)

## W7900 physical (GPU) regression evidence

| Item | Result | Evidence |
|---|---|---|
| GPU smoke (fixed script) | PASS | 01_COMMAND_RECEIPTS step 7 |
| Native full songs ×2 + SGLang full songs ×2 (fresh workspace) | PASS (4/4 complete, audited PILOT 0 problems) | pilot run dirs + audits |
| Interruption/resume ×3 live | PASS (quarantine + verified resume-skip) | 02_RUNTIME_RCA |
| R3 memory lifecycle 5 cycles | PASS (non-cumulative) | 02_MEMORY_LIFECYCLE.csv |
| Reliability matrix battery | PASS with documented exceptions (2 invalid-input hangs = defect candidate) | 02_RELIABILITY_MATRIX.csv |
| Child-worker SIGKILL fault injection | EXECUTED (evidence: health blind spot; no respawn) | mini_window/sigkill*.json |
| Server restart cycles ×3 | PASS (30 s boot each) | window_server_state/restart*/cold_boot.json |
| Pilot scoring (official frozen evaluator, shard mode) | per+songbench complete both arms; mulan+amc executed post-ArmA-window (see update below) | run dirs scores/ |
| Frozen-evidence integrity (end-of-mission recheck) | see FINAL_REPORT_ZH § | frozen manifests re-hash |

## Remote CI (exact HEAD)

Filled after push in `05_GITHUB_HANDOFF.md`. Local suites above are NOT a
substitute for the exact-HEAD remote check.

### Update (post-final-runs)

- Arm A fresh perf: 5/6 candidates complete (run `rc4_perf_armA`, walls
  620–692 s); 1 worker exhibited a suspected **silent CPU-only fallback**
  under external-GPU-tenant pressure (no KFD context, 191% CPU, 46 min, 0%
  GPU; replacement worker immediately re-acquired GPU at 99%) — evidence
  `/data/yue2-runs/rc4_evidence/cpu_fallback_suspect_wsb_001_r1.txt`;
  recorded as follow-up (fail-loud guard belongs upstream in yue2_infer).
- mulan+amc shard scoring for both pilots: **rc=0 both arms, complete=true**
  (muLan means A 0.4345 / B 0.4660; AMC A 0.4550 / B 0.4765).
- Frozen-evidence end-of-mission recheck: **all receipt-level and score
  hashes identical** to the M0 manifests (armA + armB).
