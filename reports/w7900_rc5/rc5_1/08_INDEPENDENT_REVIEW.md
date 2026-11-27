# RC5.1 P1.2 — Independent Review (engineering + scientific integrity)

Reviewer stance: adversarial — every claim is traced to evidence on the host;
developer GO statements are not accepted at face value. All times UTC.

## A. Defects found during RC5.1, their closure verified

| # | Defect (reproduced) | Root cause (source level) | Fix | Regression | Verified on hardware |
|---|---|---|---|---|---|
| 1 | CI collection error `ModuleNotFoundError: torch` | test module exec'd `spec.loader.exec_module` at import time (scripts/rc5_q3o_moe.py imports torch at module scope) | lazy `_module(torch)` + `_skip_without_torch()` | torch-free run = 9 honest skips; CI green | CI runs 46000484093 / 46000493357 |
| 2 | Workflow YAML syntax failure (run 45415198539, 0s) | plain scalar broke on `': '` in the disclosure step | block scalar | yaml.safe_load + green CI | yes |
| 3 | SIGTERM pause left candidates 17–20 unarchived | `rc5_generate.py` guarded the tail checkpoint with `not STOP.is_set()` | tail checkpoint always written; `--checkpoint-only` mode | unit tests + real closure (20/20) | yes |
| 4 | Cross-session resume would hard-fail on repo-head/receipt-path drift | drift check compared every field incl. per-session paths | `resume_decision()` pure function: frozen / per-session / driver-revision classes, `--allow-driver-update` journal-disclosed | `tests/test_rc5_resume_gate.py` (7 controls incl. FATAL paths) | real resume session 2 (2026-11-24T17:27Z) |
| 5 | Restore drill re-archived all 20 candidates (duplicate 421 MB) | `rc5_backup.py restore` did not preserve checkpoint history | archives+manifests copied with hash check | final drill: 0 duplicates, history preserved | 384/384 drill |
| 6 | Q3O receipts reused with zero identity validation | `status in (complete, not_applicable)` only | full run-identity manifest + per-receipt identity/audio reuse rule + supersede-not-overwrite + atomic writes | `tests/test_rc5_q3o_resume.py` (9 negative controls) | real runs reuse 0 / supersede only on mismatch |
| 7 | Q3O full-model load OOM (3 layers of cause) | contiguous transpose copies + list-of-cats transients + accelerate-hook reference cycles never freed (allocator fragmentation +0.19 GiB/layer) | preallocated buffers + per-expert freeing + gc.collect per layer; **final validated path: stock HF GPU experts + in-place stable-tie-break forward patch** (no packing) | MoE unit tests + mutation 15/16 + real model load | W7900D, 34+14 placement |
| 8 | llvmlite rc=139 segfault after torch HIP load | lazy_loader deferred librosa's module-level numba stencil compilation until after the HIP stack was loaded | torch-free warm-up chain before `import torch` | 3/3 standalone + 5 subsequent in-process runs clean | yes |
| 9 | tie-stats accumulator poisoned by inference mode | in-place reset of an inference tensor outside InferenceMode | reset replaces with fresh normal tensors | repeat runs 2..N clean | yes |
| 10 | per-lab CPU arm thread thrash (15 h, 64 R-threads on 16-core quota) | torch default pool sizes to visible CPUs | `torch.set_num_threads(cpu_quota)` for device=cpu arms | fixed arm: same results in 55 min | yes |
| 11 | vLLM 0.19.1 UnspecifiedPlatform on ROCm | amdsmi shim's `amdsmi_shut_down` raises after successful init → plugin swallows its own success | platform registered directly + in-process engine (VLLM_ENABLE_V1_MULTIPROCESSING=0), disclosed | E2 subset + E2 full (384) | yes |

## B. Engineering review of the load-bearing scripts

- `gpu_lifecycle.py` / `gpu_lock.py`: single-owner flock, signal-forwarding
  with drain warning, fail-closed BLOCKED marker — re-reviewed; the RC5.1
  sessions all show `cleanup=CLEAN` exits; no lock race observed across
  ~50 lock acquisitions in RC5.1 (generation, PER, SongBench, AMC, Q3O,
  matrix, probes).
- `rc5_generate.py`: no-clobber publish, quarantine-not-delete, journal
  receipts fsynced before publish, atomic checkpoints; the resume audit
  re-verified all 384 with the official verifier (`--checkpoint-only`).
- `rc5_q3o_judge.py`: identity manifest binds code+model content+prompts+
  decoding+placement+tie-break; audio SHA cross-checked against
  prepare_inputs declarations; supersede-not-overwrite preserved every
  replaced receipt.
- Known residual (accepted, disclosed): `BatchedGpuMoeBlock` retained in
  code but unused at runtime (does not fit 48 GB as implemented); Q3O
  per-candidate latency 87 s (optimisation explicitly out of mission scope).

## C. Scientific integrity review — numbers recomputed independently

| Claim | Recomputation | Result |
|---|---|---|
| 384/384 generation | journal replay + official verify_result | 384 unique ids, 0 missing/duplicate/invalid, 0 unresolved failures, 5 truncated-but-valid |
| Historical hash comparison | independent script over Arm B manifest | 380/384 byte-identical; 4 diffs all container-only (same codec frames/duration/truncation; ±2/+15/0 bytes) |
| Selected-192 identity | full official ordering key re-derived | 192/192 match, 0 tie-break inversions |
| PER micro/macro | re-aggregated from per_song.jsonl | selected micro 0.17769855 (matches evaluator), zh 0.17692975 / en 0.17837569 |
| S/D/I decomposition | Levenshtein backtrace | sums equal official edits for 192/192 selected candidates |
| SongBench/MuLan/AMC | re-read evaluator summaries | 6.736891 / 0.509395 / 0.405181 (192/192 each, 0 failures) |
| Q3O coverage | receipt scan | 192/192 valid, 0 failed, 0 parser failures, 0 unexplained OOM; identity-bound receipts |
| Q3O repeatability | 5 runs / 2 processes | identical token-IDs hash + identical score 4.833333 |
| Corrected PER arm | re-keyed selection on E2-full rows | 8.4488% micro, 120 selection swaps (reported as separate arm) |
| Performance | journal-derived percentiles | P50 275.27 s vs historical 275.3 s; RTF mean 1.2866 |

Pilot/full, selected/unselected, CPU/GPU, official/ROCm-adapted, original/
corrected PER are all reported as SEPARATE, labelled quantities — no mixing
found in any published table (checked `06_FIVE_METRIC_SCOREBOARD.csv`).

## D. Fail-closed honesty checks

- OFF_MACHINE_BACKUP: BLOCKED_EXTERNAL (verified status, never claimed).
- Q3O official equivalence: NOT_ESTABLISHED (no CUDA host) — claimed as
  ROCm-adapted only.
- E3 CUDA PER: NOT_RUN/BLOCKED_EXTERNAL with handoff prepared.
- The corrected PER arm is NOT substituted into the official scoreboard.
- All NOT_RUN / PARTIAL items are listed in the release-gate ledger.
