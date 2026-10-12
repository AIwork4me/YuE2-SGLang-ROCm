# Independent Verification Review — Phases 5 & 6 (gfx1100 / W7900)

**Reviewer:** independent verification subagent (did not author the work)
**Date:** 2026-10-12 · **Method:** execution-based audit on the target machine
(AMD gfx1100, rocm-smi card0 `0x744b` gfx1100, torch `2.12.0+rocm7.14.1` in
`environments/yue2-gfx1100`). Every check below was performed by running real
commands against the artifacts; no claim was accepted from the reports alone.

## VERDICT

| Gate | Definition | Verdict |
|---|---|---|
| **GATE 5** | Real end-to-end output passing all checks, on both HTTP routes, official parameters | **PASS** |
| **GATE 6** | Strict validator + negative test suite + hardened driver | **PASS** (working tree; see P1-1/P1-2 — committed snapshot lags and must be fixed before the full 384 run) |

No P0 findings. Two P1 evidence-hygiene findings, three P2, several NOTEs.

---

## 1. Verified by execution

### 1.1 Audio validity (Phase 5 bundles) — PASS

`soundfile` decode of both official WAVs:

| File | sr | ch | duration | finite | RMS | peak | clipping |
|---|---|---|---|---|---|---|---|
| `wsb_000_r0_s831001.wav` | 48000 | 2 | **185.88 s** | yes | **0.1666** | 0.99997 (1 sample ≥ 0.999, 0 ≥ 1.0) | none |
| `wsb_000_r1_s831019.wav` | 48000 | 2 | **146.00 s** | yes | **0.1647** | 1.0 (3 samples at ±1.0, PCM_16) | negligible |

Both > 100 s, RMS > 0, finite, 48 kHz stereo, PCM_16 WAV — matches the report
(r0 "185.88 s, rms .1666, peak 1.0 (1 sample)"; r1 "146.00 s, rms .1647").
Smoke file also verified: 24.0 s, rms 0.0781 (report: 24.0 s / .078).
WAV sha256 recomputed: r0 `fbe5a7b735dcfef5…e8124824`, r1
`89c5756621f10f14…8e30b78` — both match the report's hashes.

### 1.2 Official frozen verification — PASS

`benchmark/wsb_metrics/artifact_storage.verify_result` (module path confirmed
inside the frozen tree) executed against both bundle directories:

| Dir | status | truncated | identity | semantic content tokens | audio s |
|---|---|---|---|---|---|
| `wsb_000_r0_s831001` | **complete** | **False** | `570c5ce90435fd1b2552c284d502d4eb3ea608dd3d65f24a8c00ea88076a9dc0` | **4647** | 185.879 |
| `wsb_000_r0_s831019_alias` | **complete** | **False** | `cc34b973ec2fcad96a9fb767d8568e2f6a31deb6f4f353d65ce22d24440a135e` | **3650** | 145.999 |

Weight manifests (mot + vae sha256s) verified inside `result.json`; report's
"4647 / 3650 codec frames" confirmed. The alias dir's `request.json` carries
seed 831019 / cot full (it is candidate r1 despite the `r0` in its name — see
NOTE-6).

### 1.3 Cross-machine identity — MATCH (exact)

`evidence/pilot_manifest.jsonl` (gfx1151 pilot) r0 identity
`570c5ce90435fd1b…a9dc0` and r1 identity `cc34b973ec2fcad9…135e` are
**byte-identical** to the gfx1100 official-run identities above. Bonus check:
pilot1x2 prompt-1 identities (`ca184205…`, `4e394be3…`) also byte-match the
gfx1151 pilot. The manifest rows carry
`identity_note: "re-synced after contract-upgraded re-finalization (phase 5
review P2)"` — i.e. both sides were recomputed under the same identity
contract ({request, effective config, weights}), so the equality is
meaningful (see NOTE-5 for the single-machine provenance caveat). Audio
differs across GPUs at equal seeds (185.88 s vs 162.32 s for r0) exactly as
the report discloses.

### 1.4 Negative test suite — 16/16 PASS

```
YUE2_WORKSPACE=/workspace/yue2-sglang-rocm-w7900 \
  python -m pytest tests/test_wsb_full_mode.py tests/test_wsb_resume.py -q
→ 16 passed in 22.63 s   (10 full-mode + 6 resume)
```
Individual test names confirmed (incl. `test_pilot_10_of_10_cannot_pass_full_mode`,
`test_full_383_of_384_rejected`, `test_wrong_seed_rejected_and_error_preserved`,
`test_dataset_hash_mismatch_is_fatal`, `test_driver_quarantines_partial_and_journals_failure`,
`test_resume_skips_complete`). Report's "10/10 + 6/6" is accurate.

### 1.5 Validator code audit (`verify_wsb_artifacts.py`, working tree) — all four confirmed

- **(a) No silent expect-reduction:** full mode demands `--expect == 384`
  (else a problem), `len(expected) == 384` ("REFUSING to lower the bar"),
  192-prompt coverage, candidates {0,1} per prompt; verdict FULL only when
  `complete == 384 and not problems and len(expected) == 384`; the report's
  `expected_candidates` is pinned to 384 in full mode. Verified by code
  (lines 116–132, 174–176, 184) and by the passing negative tests.
- **(b) problems never reset:** initialized once (line 62); the only
  operations after init are `.append` (grep-verified; no reassignment
  anywhere). The v1 reset bug (`results, problems = {}, []`) was confirmed in
  git history at commit `505600f`, along with the v1 expect-reduction
  (`args.expect = len(selected)`) — both exactly as the report describes
  ("v1 line ~50/~51").
- **(c) unexpected-dir detection only flags directories:**
  `if not p.is_dir(): continue` before flagging (lines 165–170). **But this
  fix is uncommitted** — see P1-2: the committed version (e640840) flags the
  per-candidate `.wav` byproducts as "unexpected candidate dir"; demonstrated
  by execution (committed → 2 false problems, verdict PILOT-INCOMPLETE, exit
  1 on a copy of pilot1x2; working tree → PILOT, 0 problems, exit 0).
- **(d) dataset revision hash on by default:** sha256 of
  `reproduction_manifest.jsonl` vs frozen pin `859e5225…cff2edc0`; mismatch
  is FATAL (exit 2) unless `--allow-missing-dataset-hash`, which *records* a
  `WARNING-RECORDED` problem (still a non-passing verdict + exit 1 — it
  cannot hide). Pin re-verified on this machine: manifest sha256 matches.
  Shape check (192 rows, contiguous 0..191) also present.

### 1.6 Driver code audit (`run_wsb.py`, working tree) — all seven confirmed

- **(a)** `args.runs = args.runs.resolve()` (line 229, "payloads embed
  absolute paths (server cwd differs)"). The committed version lacks this and
  **demonstrably failed**: `logs/phase7_pilot1.log` shows 2/2 FAIL with the
  server returning a *relative* audio path (`../runs/gfx1100/pilot1x2/...`).
- **(b)** `check_or_write_run_config`: existing `run_config.json` differing
  from the current identity → FATAL exit 3 ("refusing to mix runs"); identity
  includes platform/gpu/torch/sglang commit/dataset+model+VAE revisions/
  patchset sha256/official config/run_id (unit-tested).
- **(c)** Quarantine, never delete: stale/partial candidate →
  `shutil.move` into `quarantine/<timestamp>/`, journaled
  `quarantined(partial)`. No `rmtree`/`unlink`/`os.remove` anywhere in the
  file (grep-verified). Unit-tested end-to-end against a dead server.
- **(d)** Disk safety: `shutil.disk_usage(args.runs).free < MIN_FREE_GB`
  (default 20 GiB, `YUE2_MIN_FREE_GB` override) → `skipped(disk)` + stop.
- **(e)** SIGINT/SIGTERM handlers → `STOP` event; in-flight candidate
  finishes; `interrupted` status; summary always written (finally-block
  poller stop). **Live evidence exists:** `logs/phase7_pilot1b.log` shows
  `[signal 15] graceful stop requested; finishing in-flight candidate, then
  exiting`, then 1 complete / 1 pending, `stopped_by_signal: true`, valid
  summary.
- **(f)** wav-archive: `shutil.move(wav → archive/run_id/)` after verified
  finalize — moves, never deletes (code-verified). Uncommitted and never
  exercised (see P2-2).
- **(g)** No `/home/amd` in `run_wsb.py`, `verify_wsb_artifacts.py`,
  `finalize_candidate.py`, or `serve_yue2_gfx1100.sh` (grep-verified).
  Exceptions: legacy `serve_yue2_rocm.sh` (disclosed in the report as
  historical) and `tests/test_first_audio.py:23` (undisclosed — P2-3).
  `serve_yue2_gfx1100.sh` is fully env-driven and asserts the exact torch
  stack + `gfx1100` before launch.

### 1.7 Pilot evidence (`runs/gfx1100/pilot1x2`) — consistent

- `generation_summary.json`: run_id `pilot1x2c`, expected 2 / complete 2 /
  failed 0 / pending 0, wall 465.3 s, **peak_vram_bytes 40754262016
  (37.95 GiB)**, peak_gtt 35033088 (33.4 MiB), stopped_by_signal false.
- `run_config.json`: **official config recorded exactly** (cot=full,
  ode_steps=32, semantic_max_tokens=9000, abc_max_tokens=4096,
  vae_core_frames=1024, vae_halo_frames=16), platform gfx1100, torch
  2.12.0+rocm7.14.1, sglang `ced0ef7d…`, dataset `e361b85a…`, model/vae
  revisions, patchset sha256.
- Manifest records: both `complete` with wall_s, audio_seconds, truncated,
  codec_frames, identity — identities byte-match the gfx1151 pilot rows for
  prompt 1.
- `audit.json` (verdict PILOT, 2/2 verified, 0 problems) **independently
  reproduced** by re-running the current validator on a copy.

### 1.8 Server log stage timings (official r0) — CONFIRMED EXACTLY

`grep "Stage] finished" logs/server_yue2_gfx1100.log`, r0 request window
23:20:49 → 23:27:48 UTC:

| Stage | Log value | Report claim |
|---|---|---|
| Yue2ARStage | **146.9705 s** | 147.0 ✓ |
| Yue2NARStage | **30.6153 s** | 30.6 ✓ |
| Yue2VAEDecodeStage | **241.5006 s** | 241.5 ✓ |

Stage sum + overhead = 419.1 s wall (`logs/phase5_official.log`: HTTP=200,
419.110 s ✓). r1 alias window 23:27:48 → 23:30:58: AR 97.98 / NAR 20.99 /
VAE 71.49 → 190.5 s ✓ (log: 190.475 s). Smoke: AR 19.43 / NAR 0.50 /
VAE 48.54 ≈ 68.5 s ✓. Access log confirms **both routes**: r0
`POST /v1/audio/generations` 200 (23:27:48), r1
`POST /v1/audio/music/generations` 200 (23:30:58). Startup header confirms
the exact flag matrix (FAST_SAMPLER/STEP_GRAPH/FUSED_DECODE/FAST_NAR/FA3/
BATCHED_AR=0, SESSION=1, GRAPH_POOL=1) and `/health` 200 at 23:18:18.
Upstream verified: `upstream/sglang` git shows pristine `ced0ef7d` (PR
#42106 head) + patches 0001-0005 + 0008.

### 1.9 Report-claim spot checks (all supported)

- `peak_memory_mb: 0.0`, null `yue2_stage_seconds` on this stack — confirmed
  in both `phase5_official.log` and `phase7_pilot1.log` responses (honest
  telemetry-gap disclosure).
- "cfg_scale not sent / effective cfg 1.0": driver payload omits cfg_scale;
  `finalize_candidate.py` documents that the PR head does not accept the key
  and materializes effective `cfg_scale: 1.0` into `request.json` —
  consistent with the bundles.
- Effective config (`config.json`) is byte-identical between the phase5
  official r0 bundle and a pilot1x2 candidate (deterministic effective
  config, ode_steps 32, semantic max 9000, abc max 4096, vae 1024/16).
- gfx1151 pilot r0 audio 162.32 s vs gfx1100 185.88 s — the report's
  cross-GPU audio-difference claim is accurate.

---

## 2. Findings

### P0 — none

### P1-1 · Dead evidence pointer in PHASE5 report
`reports/gfx1100/PHASE5_FIRST_AUDIO.md` header cites
`evidence/gfx1100/phase5_official.json` as the evidence artifact. **That file
does not exist** anywhere in the workspace and was never committed
(`git log --all --diff-filter=A` finds nothing). The underlying evidence
(runs/, logs/, hashes, this review's independent re-verification) fully
supports the report's substance, but in a "every claim must have evidence"
repo the primary evidence pointer must not be dead. Fix: create the JSON
evidence file (WAV hashes, identities, stage timings, verify_result outputs)
or correct the pointer.

### P1-2 · Working tree ≠ committed state; committed validator false-positives on real runs
`git status`: `scripts/run_wsb.py` and `scripts/verify_wsb_artifacts.py` are
modified-uncommitted relative to the phase 5-6 commit `e640840` (23:32). The
uncommitted deltas are: (i) `args.runs.resolve()` absolutize, (ii)
`--wav-archive`, (iii) the validator's `is_dir()` skip. Consequences,
demonstrated by execution:
- The **committed** validator run against pilot1x2 produces 2 false
  "unexpected candidate dir" problems (the `.wav` byproducts) → verdict
  PILOT-INCOMPLETE, exit 1; the **working tree** version correctly returns
  PILOT / 0 problems. Hence the stored `pilot1x2/audit.json` (23:58) was
  necessarily produced by the uncommitted fix.
- The **committed** driver's relative-path bug is demonstrated live by
  `phase7_pilot1.log` (2/2 FAIL, server returned `../runs/...`).
All Phase 6 gate claims are true of the current working tree (verified), but
the committed snapshot does not match the described/verified behavior. Fix:
commit the fixes before any future checkout/verification or the full run.

### P2-1 · pilot1x2 run history shows a manual reset between attempts
Timeline from logs: pilot1 (23:39–23:42, relative-path bug) 2/2 FAIL →
pilot1x2b (23:44–23:45:59, SIGTERM-graceful, 1 complete) → pilot1x2c
(23:46:21–23:54, 2/2 complete, `resumed: 0`, r0 regenerated). The final
`generation_manifest.jsonl` contains **no** pilot1x2b records, and
`run_config.json`/`evaluation_inputs.jsonl` carry pilot1x2c's identity —
i.e. the run directory was manually cleaned between b and c (otherwise the
run-config immutability check would have aborted c, and c would have skipped
the already-complete r0). The final state is internally consistent and fully
verifies, and the invariants are unit-tested — but the recorded end-to-end
evidence does not exercise write-once/immutability across a real resume.

### P2-2 · wav-archive feature unexercised
`--wav-archive` (added 00:13, after all recorded runs) moves rather than
deletes WAVs (code-verified) but appears in **no** recorded run (zero
`wav_archived` fields in any manifest; pilot WAVs still in `songs/`) and has
no unit test. Verify it during the full run or add a test.

### P2-3 · Undisclosed hard-coded machine path in tests
`tests/test_first_audio.py:23` — `RUNS =
Path("/home/amd/Desktop/YuE2/runs/phase4")` (Phase-4-era gfx1151 file, not
part of the Phase 6 suites, but the repo claim "no machine paths" should
account for it; the report only discloses the legacy launcher).

### NOTEs
1. "rocm-smi 100% utilization during stages, VRAM ≈ 11/48 GB during VAE" is
   an operator observation with no retained telemetry. Real GPU execution is
   independently supported (stage timings, launcher stack assertions incl.
   `gcnArchName == gfx1100`, poller peak VRAM 40.75 GB on pilot1x2,
   rocm-smi card0 gfx1100/0x744b on this 8×W7900 machine).
2. "Atomic writes (fsync + rename) for manifests/config": config, inputs and
   summary are rename-atomic; `generation_manifest.jsonl` is an
   append+fsync-per-record journal (correct design, but not rename-atomic —
   wording slightly overstates). Likewise the docstring's status list
   ("verified"/"retried") does not match emitted statuses
   (`retries` is a counter; no "verified" status is journaled).
3. `finalize_candidate.py` ported off `/home/amd/Desktop` — verified
   (YUE2_WORKSPACE only).
4. r1 WAV has 3 samples at full scale (±1.0 PCM_16) — negligible, consistent
   with "no serious clipping".
5. `pilot_manifest.jsonl` is the gfx1151 copy (with "re-synced" identity
   notes); a single-machine audit can verify the copy matches but cannot
   independently attest the gfx1151 originals.
6. The r1 bundle directory is named `wsb_000_r0_s831019_alias` ("r0" in the
   name, but it is candidate r1, seed 831019) — cosmetic; request.json seed
   and identity confirm r1.
7. The phase5 manual driver (std-route/alias-route script) is not preserved
   (log + bundles are); `run_wsb.py`-based runs are reproducible.
8. README phase table reflects the gfx1151 mission numbering; gfx1100
   reports use re-mapped phase semantics (Phase 5 = official e2e) — potential
   confusion for readers.
9. "W7900D" variant not distinguishable from rocm-smi/lspci output
   (`0x744b`, gfx1100 — W7900 family); no impact on any claim.

---

## 3. Conclusion

**GATE 5: PASS.** Real end-to-end generation on gfx1100 via both HTTP routes
with the official parameter set; audio is valid 48 kHz stereo, finite,
RMS-positive, > 100 s; both bundles pass the frozen official
`verify_result` (complete, not truncated, correct weights); identities
byte-match the gfx1151 pilot; all reported timings (AR 147.0 / NAR 30.6 /
VAE 241.5; walls 419.1/190.5/68.5 s) reproduce exactly from the server log.

**GATE 6: PASS** (of the current working tree, verified by execution):
the validator is strict in all four audited dimensions, 16/16 negative/resume
tests pass, and the driver hardening (absolutize, immutable identity,
write-once inputs, quarantine-not-delete, disk floor, graceful signals —
with live SIGTERM evidence — atomic writes, dynamic GPU discovery) is
present and correct. The P1s are evidence-hygiene, not capability, gaps:
commit the working-tree fixes and repair the dead Phase-5 evidence pointer
before the full 384-candidate run relies on this harness.
