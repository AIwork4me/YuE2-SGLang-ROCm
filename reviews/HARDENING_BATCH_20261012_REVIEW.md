# Independent Verification Review — Hardening Batch (commits 4b6f8d3 + 3c97abb)

**Reviewer:** Independent Verification Subagent (CPU-only audit; no GPU workloads, no
restarts, no file modifications outside this review file).
**Date:** 2026-10-12 07:04–07:14 +08:00
**Scope:** hardened artifact auditor + tests, script restoration/configurability,
clean-room reproduction evidence, evaluator patch audit + determinism evidence,
INCIDENT-1 disclosure, live-run non-interference.

## VERDICT: PASS

All substantive claims of the batch were independently reproduced. Every check
below was re-executed or re-derived from primary artifacts (code, logs, tarball
diff, JSONL data, on-disk run state). No P0/P1/P2 issues found; 6 P3 issues
(documentation wording, minor strictness gaps) are listed with exact fixes.

Note: repo HEAD moved 3c97abb → f63eb19 (`docs(upstream): PR comment draft…`)
while this audit was running; that commit is out of scope and the working tree
was clean apart from it.

---

## 1. Hardened auditor `scripts/verify_wsb_artifacts.py` — VERIFIED

Code reading (evidence repo = workspace copy, byte-identical):

| Claimed property | Code evidence | Confirmed |
|---|---|---|
| Full mode = exactly 384 (192 prompts × 2) from frozen manifest | `load_manifest()` hard-fails unless 192 rows with `prompt_index == 0..191`; `expected_from_manifest()` builds 384 with seed formula `831001+i / 831019+i` enforced per prompt | YES |
| `--expect` rejected in full mode | `main()`: `if args.expect is not None: raise SystemExit("--expect is not valid in full mode…")` | YES |
| Subset mode requires `--expect == len(selected)` exactly, never adjusted | `main()`: mismatch → `SystemExit("--expect N != M selected rows; the expectation is never adjusted silently")` | YES (see P3-5: `--expect` may be omitted entirely) |
| Unexpected directories rejected | `sorted(set(present) - expected_idents)` → problem `"unexpected candidate directory"` | YES |
| Duplicate-identity directories rejected | regex `wsb_(\d+)_r(\d+)_s(\d+)`; same (i,j) key under a different name → `"duplicate identity …"` problem | YES |
| WAV files never treated as candidate dirs | `present = {p.name: p for p in songs.glob("wsb_*") if p.is_dir()}` — directory filter; the live run keeps 37 `wsb_*.wav` files next to the bundles and they are ignored | YES |
| Protocol checks seed/cot/cfg/style/lyrics | seed vs formula, `cot == "full"`, `cfg_scale == 1.0`, style+lyrics byte-equal to the frozen manifest row | YES |
| Recomputed identity vs result.json | `canonical_identity(request, config, weights)` (sha256 of canonical JSON) compared to `result.identity` | YES |
| Official `verify_result` per candidate | `from artifact_storage import verify_result` — `artifact_storage.py` hash is UNCHANGED vs pristine (a5bcc181… in both release.json versions), so the integrity checker itself is unmodified | YES |
| Driver failures reported unless bundle now verifies (recovered) | non-`complete*` manifest records: if dir + result.json + `verify_result` pass → classified `driver:<status> (recovered)`, no problem; else problem | YES |

Gate strength: exit 0 only for `verdict FULL` = zero problems AND
`verified == len(expected)`. Classification is emitted separately and cannot
weaken the gate.

### Test run (re-executed)

```
cd /home/amd/Desktop/YuE2 && source environments/yue2/bin/activate && \
  python -m pytest tests/test_verify_wsb_artifacts.py -v
→ 12 passed in 1.70s
```

### Regression proofs in `tests/test_verify_wsb_artifacts.py` — VERIFIED

- `test_subset_cannot_pass_full_mode`: runs the verifier in **default full mode**
  on a 10-candidate synthetic run; asserts `verdict == PARTIAL`,
  `expected_candidates == 384`, `verified_complete == 10`, and **exactly 374**
  `"missing (no candidate directory)"` problems. The synthetic bundles are real
  (FLAC + npy artifacts with valid hashes written via `_write_bundle`), so this
  is a genuine end-to-end proof, not a mock. A 10-candidate subset CANNOT pass
  full mode. CONFIRMED.
- `test_forged_bundle_caught_by_identity_recheck`: forges a *self-consistent*
  bundle (request seed rewritten AND result.json artifact hash + identity
  rewritten); asserts BOTH the protocol seed problem
  (`seed 831999 != official 831019`) and an identity problem fire. The identity
  re-check is genuinely exercised. CONFIRMED.
- Also verified: `--expect` mismatch rejection (never adjusted), `--expect`
  rejected in full mode, duplicate-directory, unexpected-directory, tampered
  artifact (official hash check), driver-failure open defect, and
  recovered-driver-failure → verdict FULL with
  `driver:finalize_failed (recovered) == 1`.

## 2. Script restoration + reproducibility — VERIFIED (2 P3 nits)

### 2a. Every `scripts/` reference resolves

All `scripts/<name>` references in README.md, reports/*.md and patches/*.md
(7 unique names; 14 reference sites):

| Reference | Sites | Status |
|---|---|---|
| scripts/collect_system_info.sh | 1 | OK |
| scripts/finalize_candidate.py | 1 | OK |
| scripts/phase0_gpu_smoke.py | 2 | OK |
| scripts/run_wsb.py | 2 | OK |
| scripts/serve_yue2_rocm.sh | 3 | OK |
| scripts/setup_gfx1151.sh | 2 | OK |
| scripts/verify_wsb_artifacts.py | 3 | OK |

**Missing: none.** Evidence-repo scripts/ carries the full referenced set
(14 files incl. checkpoint_wsb.py, resume_wsb.py, run_wsb_full.py,
run_wsb_pilot.py, run_smoke_test.sh, run_official_eval.sh, milestone_watcher.sh).

### 2b. Configurability (`grep -rn '/home/amd' scripts/`)

Every path is an env-overridable default — `WS="${WS:-/home/amd/Desktop/YuE2}"`
(shell) or `os.environ.get("WS", "/home/amd/Desktop/YuE2")` (Python) — in
collect_system_info.sh, setup_gfx1151.sh (also `VENV="${VENV:-…}"`),
serve_yue2_rocm.sh, run_official_eval.sh, run_smoke_test.sh, phase0_gpu_smoke.py,
run_wsb.py, finalize_candidate.py, verify_wsb_artifacts.py.
**Single exception:** `milestone_watcher.sh:7` hard-assigns
`WS=/home/amd/Desktop/YuE2`, silently discarding an inherited `WS` (P3-1).
`run_official_eval.sh` additionally re-runs the strict full-mode auditor as a
gate before any scoring — consistent with the batch's claims.

### 2c. Clean-room reproduction evidence (logs/phase1.log tail) — VERIFIED with caveat

The log contains a second `=== setup_gfx1151.sh started: 2026-10-12T05:51:50 ===`
run that bootstrapped a **fresh venv at environments/repro_check**
(`Using Python 3.12.3 environment at: environments/repro_check`, then 23
packages newly installed: torch 2.12.0+rocm7.14.1, triton, torchvision,
torchaudio, rocm-sdk-device-gfx1151, …), then SGLang editable reinstall, then
the verification block with **all checks OK**:

```
torch: 2.12.0+rocm7.14.1 | hip: 7.14.60850
bf16 GPU matmul OK, checksum: -4143.3916015625
sglang import OK; yue2 modules import OK
=== setup_gfx1151.sh finished: 2026-10-12T05:52:49+08:00 ===
```

(`pip check` conflicts are the pre-documented sglang CUDA metadata pins —
consistent with dependency_matrix.json.) With `set -euo pipefail`, reaching the
`finished` line implies RC=0. The live `environments/yue2` env was untouched by
this run (its own install log block at 05:51:31 precedes it).

Caveats: (1) the literal banner `--- creating fresh venv at environments/repro_check ---`
never appears in phase1.log — in setup_gfx1151.sh the `echo` (line 23) executes
**before** `exec >>"$LOG" 2>&1` (line 28), so the banner goes to the caller's
terminal, not the log (P3-2). The fresh-venv substance is nonetheless provable
from the uv install lines. (2) `environments/repro_check` has since been deleted
(the log is the surviving evidence) — acceptable for a throwaway check, but the
reviewer could not re-inspect the venv itself.

## 3. Evaluator patch audit — VERIFIED

### 3a. Independent 3-file diff (re-executed)

```
tar xzf benchmark/WildSongBench/evaluation/wsb_metrics.tar.gz -C /tmp/audit_orig_wsb
diff -rq /tmp/audit_orig_wsb/wsb_metrics benchmark/WildSongBench/wsb_metrics | grep '^Files'
→ exactly:
  release.json differ
  src/mot_infer/eval_worker.py differ
  wsb_eval.py differ
```

All remaining lines are `Only in` model downloads (`evaluation_models/hub/…`,
`models/muq`), `.venvs`, `.cache`, `.runtime`, `validation`, `__pycache__` —
runtime state, not pristine-tree code. **Exactly 3 code/data files differ, as
claimed.**

### 3b. Unchanged-function claim (hunk-level verification)

- `wsb_eval.py`: single diff hunk at @@ -92,11 +92,23 — entirely inside
  `def verify_environment` (function boundaries confirmed in pristine source;
  `environment()`, `prepare_inputs`, `summarize`, metric dispatch untouched —
  everything outside the hunk is byte-identical). The change adds the
  `WSB_ROCM_TORCH_OVERRIDE=1`-gated exemption for {torch, torchaudio, triton,
  torchvision} version mismatches only; Python 3.12.11 check and all other
  packages still enforced; receipt records the override.
- `src/mot_infer/eval_worker.py`: single diff hunk at @@ -143,19 +143,50 —
  entirely inside `PERScorer.__init__` (pristine: class `PERScorer` at line 134,
  `__init__` 135–159, `score` 160). The original vLLM construction is preserved
  **verbatim** in the `else` branch; the ROCm branch constructs the same
  Qwen3-ASR checkpoint via the transformers backend under the same env gate.
  `phoneme_result` (line 118), `score`, `score_batch`, and every other worker
  class (MuLanScorer, AllMusicCapsScorer, Q3OScorer) are outside the hunk →
  byte-identical. CONFIRMED: no metric worker other than `PERScorer.__init__`
  is touched.
- `release.json`: byte-wise the whole file differs (re-serialized with 1-space
  indent), but a semantic JSON diff yields **exactly 3 changes**: the
  `eval_worker.py` and `wsb_eval.py` sha256 entries updated + one added
  `rocm_override_note` key. Matches "2 hash entries + 1 disclosure note"
  (see P3-3 for the reformat note).

### 3c. Determinism evidence (recomputed from the JSONLs)

`per` = `metrics.per.{per, edits, first_pass_per, first_pass_edits}` per id:

- **runB (10 candidates) vs runC (repeat, ~1 h later): 10/10 identical.**
  Same id sets. CONFIRMED — within-set, fixed-order scoring is exactly
  reproducible on this host.
- **runA (2 candidates alone) vs runB (same 2 inside the 10-set): 1 of 2
  identical.**
  - `wsb_000_r1_s831019`: IDENTICAL (0.21608832807570977 / 137 edits).
  - `wsb_000_r0_s831001`: DIFFERENT — A `0.17350157728706625 / 110 edits` →
    B `0.167192429022082 / 106 edits`. Matches the audit doc's
    "0.17350/110 → 0.16719/106" exactly. CONFIRMED batch-composition
    sensitivity; the doc correctly does NOT claim cross-set or cross-backend
    equivalence.
- **Empty-transcript case:** `wsb_076_r1_s831095` present in BOTH runB and
  runC with `per 1.0`, `edits 505`, `reference_phonemes 505`,
  `asr_all_terminated true`, 4/4 empty ASR repeats (`text=''`), `lang en`.
  CONFIRMED, matching evaluator_patch_audit.json.

## 4. INCIDENT-1 disclosure (PHASE6_GENERATION.md §3) — VERIFIED

Report section read: self-inflicted missing-`import os` in finalize_candidate.py
during the hardening edit, 3 candidates finalize_failed ~05:47–06:30, recovered
from intact bundles, manifest history preserved, generation never stopped.

On-disk verification:

- `runs/wsb_full/songs/wsb_{016_r1_s831035, 017_r0_s831018, 017_r1_s831036}/result.json`
  all exist with `status == "complete"`.
- `runs/wsb_full/generation_manifest.jsonl` lines 34–39: for each of the three
  ids BOTH records are present, in order — the original `finalize_failed`
  record (with the NameError traceback) followed by the appended
  `complete(recovered-finalize)` record carrying `recovery` note, `recovered_at`
  timestamps (06:55:24 etc.) and the preserved original error. History was
  appended, not overwritten. CONFIRMED.
- `scripts/finalize_candidate.py` now has `import os` (line 35) and
  `python -m py_compile` → OK (re-executed).
- The recovery path is exactly what the hardened auditor classifies as
  `driver:finalize_failed (recovered)` — demonstrated by
  `test_recovered_driver_failure_is_not_an_open_defect`.

## 5. Live-run non-interference — VERIFIED

- `pgrep -f "run_wsb.py --runs runs/wsb_full"` → PID **24308**, started
  **2026-10-11 23:03:48**, elapsed >8 h at audit time — a single continuous
  process spanning the entire hardening batch window. Never killed, never
  restarted.
- `logs/wsb_full.log` shows the three `[FAIL-finalize]` NameError blocks
  (incident) and then continued completions; artifacts finalized **after
  06:30**: recoveries at 06:54:30 / 06:54:55 / 06:55:21 and the next regular
  candidate `wsb_018_r0_s831019` at 07:06:39 (`[34/384] … ok`, 1455.54 s wall).
  37 result.json files on disk at 07:10. CONFIRMED.

---

## Issues

### P0 — none.

### P1 — none.

### P2 — none.

### P3 (all; none affect the verdict or any published claim)

- **P3-1 — milestone_watcher.sh discards `WS` env override.**
  `scripts/milestone_watcher.sh:7` uses `WS=/home/amd/Desktop/YuE2` (hard
  assignment) while every other script uses `WS="${WS:-…}"`.
  *Fix:* change line 7 to `WS="${WS:-/home/amd/Desktop/YuE2}"`.

- **P3-2 — clean-room banner not captured in phase1.log.**
  In `scripts/setup_gfx1151.sh` the `echo "--- creating fresh venv at $VENV ---"`
  (line 23) runs before `exec >>"$LOG" 2>&1` (line 28), so the section header
  the evidence points to never lands in the log; the log only implies the fresh
  venv via the uv install lines. *Fix:* move the `exec >>"$LOG" 2>&1` redirect
  above the venv-bootstrap block (or append the banner with
  `echo … >>"$LOG"`), so future clean-room runs are self-documenting.

- **P3-3 — EVALUATOR_PATCH_AUDIT.md diffstat wording and release.json reformat.**
  The doc states `wsb_eval.py (… +12 lines, −0)` and `PerScorer.__init__
  (+31/−0, …)`; the actual unified diffstats are +16/−4 and +44/−13 (the
  removed lines are the original block moved verbatim into the preserved
  `else` branch — net +12 and +31, which is what the numbers actually are).
  "−0" is therefore misleading, and the class is named `PERScorer`, not
  `PerScorer`. Separately, release.json was re-serialized (2-space → 1-space
  indent) so its byte diff spans the whole file even though the semantic diff
  is exactly the claimed 3 changes. *Fix:* in patches/EVALUATOR_PATCH_AUDIT.md
  replace "(+12 lines, −0)" with "(net +12; receipt lines rewritten)" and
  "(+31/−0, original branch preserved)" with "(net +31; 13 original lines
  moved verbatim into the preserved vLLM else-branch)"; rename to
  `PERScorer.__init__`; add one sentence noting release.json was re-serialized
  (indent) with semantic diff = 2 hashes + 1 note.

- **P3-4 — future-dated checkpoint row in PHASE6_GENERATION.md.**
  §2's second row is stamped `2026-10-12 07:15` but the file was written/committed
  at 07:07 (commit 3c97abb) — a timestamp ~8 min ahead of the evidence it
  describes. *Fix:* correct the stamp to the actual audit time (~07:05–07:07)
  when the table is next updated.

- **P3-5 — subset mode permits omitting `--expect` entirely.**
  `verify_wsb_artifacts.py` only enforces `--expect == len(selected)` when
  `--expect` is provided; in subset mode without it, the expectation silently
  defaults to the selection size. Full mode is unaffected (384 is frozen).
  *Fix:* in `main()`, subset branch, require
  `if args.expect is None: raise SystemExit("subset mode requires --expect")`
  (and add a 13th regression test).

- **P3-6 — duplicate selection rows collapse silently in subset mode.**
  `expected_from_selection()` keys by `(prompt_index, candidate_index)`; a
  selection file with a duplicated row would collapse, and since `--expect`
  compares against the raw row count (`len(selected)`), `--expect 10` could
  pass while only 9 distinct candidates are gated. The report would show
  `expected_candidates: 9`, so it is detectable, but it contradicts "exactly".
  *Fix:* reject duplicates in `expected_from_selection()`, e.g.
  `if (i, j) in out: raise SystemExit(f"subset selection duplicates prompt {i} candidate {j}")`.

## Evidence commands (reproducible)

```
# 1. tests
cd /home/amd/Desktop/YuE2 && source environments/yue2/bin/activate && \
  python -m pytest tests/test_verify_wsb_artifacts.py -v          # 12 passed
# 2. three-file diff
tar xzf benchmark/WildSongBench/evaluation/wsb_metrics.tar.gz -C /tmp/audit_orig_wsb && \
  diff -rq /tmp/audit_orig_wsb/wsb_metrics benchmark/WildSongBench/wsb_metrics | grep '^Files'
# 3. determinism: compare metrics.per (per, edits, first_pass_*) per id across
#    evidence/evaluator_audit/per_run{A,B,C}*.jsonl (script in review transcript)
# 4. incident: grep the three ids in runs/wsb_full/generation_manifest.jsonl
# 5. liveness: pgrep -af run_wsb.py; stat newest runs/wsb_full/songs/*/result.json
# 6. clean-room: tail -75 logs/phase1.log (repro_check block, checks OK, finished 05:52:49)
```
