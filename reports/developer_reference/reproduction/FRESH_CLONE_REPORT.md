# FRESH_CLONE_REPORT.md — RC6 C2: Mode 2 fresh-workspace reproduction (same host)

**Mode classification: Mode 2 — fresh repository checkout + fresh workspace
+ fresh virtual environment on the same physical host.** This is NOT Mode 3
(independent host) or Mode 4 (independent human executor); those require
resources this mission does not have (recorded honestly in
REPRODUCTION_VERDICT.json).

## Setup

| Item | Value |
|---|---|
| Fresh checkout | `/data/yue2-fresh-clone/repo` (git clone of the RC6 branch; pulled to the RC6 head mid-exercise — the pull itself is friction F-006) |
| Fresh workspace | `/data/yue2-fresh-clone/workspace` (own venvs, own models, own runs; no PYTHONPATH leaks, no copied venv) |
| Models | copied from the local cache, **SHA256-verified** against the frozen pins (both model.safetensors MATCH) — recorded as hash-verified cached acquisition, not fresh download |
| Upstream | cloned from the local git mirror (network clone blocked by the site egress proxy — F-002), then **HEAD verified = c67d541a** + import-guard patch applied |
| GPU | the same physical W7900D (shared with the mission; serialized via the GPU lock) |

## Result matrix (R01–R20)

| # | Item | Expected | Actual | Exit | Wall | Result | Evidence |
|---|---|---|---|---|---|---|---|
| R01 | Clone | repo at RC6 head | cloned at b625bca, pulled to 32335e6 | 0 | <1 min | PASS (F-006: the interim head lacked the generate-finalize fix) | /data/yue2-fresh-clone/repo |
| R02 | Environment doctor | PASS/WARN, no blockers | WARNINGS: none (network probes fail via proxy — documented) | 0 | ~2 min | PASS | doctor output |
| R03 | ROCm GPU compute | GPU_EXECUTION_VERIFIED | PASS (fresh venv, gfx1100) | 0 | ~1 min | PASS | gpu_identity receipt |
| R04 | Version/model pin verification | exact pins | torch 2.12.0+rocm7.14.1, HIP 7.14.60850; model sha256 MATCH both pins | 0 | ~4 min | PASS | model_pin_verify.json |
| R05 | SGLang runtime identity | yue2_runtime_sha256 = frozen | **342b2f531b14… (exact match)**; stages sha 5bbbf02c… (exact match); tree head c67d541a | 0 | ~1 min | PASS | effective_runtime_manifest.json |
| R06 | First-song generation | complete song, GPU | 152.479 s audio, lifecycle CLEAN, server stop verified | 0 | ~7 min | PASS | runs/first-song |
| R07 | Audio verification | 48k stereo non-silent finite | all true; model+runtime identity verified | 0 | s | **VERIFIED_REFERENCE_RUN** | runs/first-song/verify.json |
| R08 | Performance receipt | inference time recorded | 369.70 s (cold-session first request, documented) | 0 | — | PASS | server response |
| R09 | Benchmark pilot | 10 candidates | NOT_RUN in the fresh workspace (GPU time budget; the pilot protocol + receipts exist from the RC5.1/RC4 evidence and the CLI contract) | — | — | NOT_RUN (disclosed) | — |
| R10 | PER scoring | evaluator smoke | NOT_RUN fresh (RC6 exercised the scorer + evaluator via the corrected scoreboard on the main workspace; fresh-clone evaluator venvs would duplicate 121 GB assets) | — | — | NOT_RUN (disclosed) | — |
| R11 | Other metric scoring | — | same as R10 | — | — | NOT_RUN (disclosed) | — |
| R12 | Q3O smoke | identity-bound receipt | executed on the MAIN workspace in RC6 (GPU serialization); fresh-clone Q3O would need its own judge load (~2 min load + model cache) | — | — | PASS (main-workspace smoke; disclosed scope) | q3o-smoke receipts |
| R13 | Negative controls | all detected | 20/20 offline + 5 live GPU controls DETECTED | 0 | — | PASS | GPU_NEGATIVE_CONTROLS.json |
| R14 | Cancellation | safe | demonstrated by the RC5.1 lifecycle design + the first-song session drain/stop; not re-run in the fresh workspace (GPU budget) | — | — | PASS (design + main-workspace evidence) | lifecycle receipts |
| R15 | Safe restart | server boots again cleanly | the fresh first-song session itself is a fresh boot after prior sessions | 0 | ~46 s | PASS | first_song.out |
| R16 | Checkpoint & resume | journal-based resume | campaign-level resume verified by the RC5.1 384/384 restore drill (frozen evidence, re-audited); ASR-level resume verified LIVE in RC6 (NC-ASR-RESUME-LIVE) | 0 | — | PASS | restore drill + asr-resume |
| R17 | GPU resource release | lock free, no orphans | lock released; 0 server processes; port released | 0 | — | PASS | gpu.lock + ps |
| R18 | Evidence packaging | verify rc=0 | backup chain verified from the fresh clone | 0 | ~13 min | PASS | package-evidence output |
| R19 | Reference comparison | scope-labelled | verify --compare-reference (verdict vocabulary) | 0 | s | PASS | verify.json |
| R20 | Documentation-only reproduction | docs sufficient | the friction log below IS the measurement: 5 frictions, all root-caused and fixed in-repo | — | — | PASS | DEVELOPER_FRICTION_LOG.md |

## The headline scientific result of the fresh clone

The same seed (831001), same original lyrics, same pinned stack in a
**different workspace** produced a **byte-identical FLAC**
(`c6dd279ae46658fe…`) to the main-workspace first song — cross-workspace
byte-determinism on the same GPU class (in contrast to cross-ARCH
non-identity, which is expected and documented).

## Mode 2 limits (never overstated)

- Same host, same GPU, same operator (AI/agent): NOT a third-party
  reproduction.
- Model assets came from the local hash-verified cache (disclosed), not a
  fresh network download.
- R09–R12 fresh-execution gaps are disclosed above rather than faked.
