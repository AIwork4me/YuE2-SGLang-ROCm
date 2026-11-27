# AMD_ACCEPTANCE_PACKAGE_EN.md — RC6 D4: AMD engineering acceptance package

**Status: PACKAGE READY — not submitted.** AMD engineering acceptance is an
external process; this repository never claims AMD approval (AMD01–AMD10
below track real reviewer records when they exist; they are all
READY_FOR_REVIEW / NOT_SUBMITTED today).

## 1. Hardware & stack (verified, receipted)

| Item | Value |
|---|---|
| GPU | AMD Radeon PRO W7900D 48 GiB, gfx1100, BDF 0000:03:00.0, uuid e9d0e20b-… |
| ROCm userspace | 7.14.1 (venv-local; host kernel amdgpu, ROCk 6.16.13) |
| torch | 2.12.0+rocm7.14.1 (AMD multi-arch index, device-gfx1100 extra) |
| GPU identity chain | framework device → HIP props → PCI BDF → render node → KFD topology → uuid → arch → isolated compute probe (fail-closed, no "first AMD GPU" guess) |
| Execution evidence | GPU_EXECUTION_VERIFIED receipts in every session; gpu busy 93.41% mean (campaign) |

## 2. Official model provenance

YuE2-3B @1a96eca6 (sha 1d55c42c…), YuE2-Vae-legacy @b54118f (sha b6d28362…),
WildSongBench @e361b85a — SHA256-pinned downloads; every candidate bundle
binds the weight hashes; the frozen evaluator verifies the scoring VAE
identity per candidate.

## 3. Full generation evidence

384/384 candidates (192 prompts × 2), 0 failures, 0 retries, 5
truncated-but-valid (official protocol); single resumed session rc=0; P50
wall 275.27 s; 380/384 byte-identical to the prior-stack run (4 diffs =
FLAC encoder build, PCM-level parity unprovable — historical artifacts
absent, honestly recorded).

## 4. Quality scoreboard (per arm, never mixed)

| Arm | SongBench | PER | MuLan | AMC | Q3O |
|---|---|---|---|---|---|
| Frozen (transformers ASR) | 6.736891 | 17.7699% | 0.509395 | 0.405181 | 4.393986 (ROCm-adapted) |
| Corrected (vLLM 0.19.1 ASR) | Scoreboard B (RC6, separate) | 8.4488% | Scoreboard B | Scoreboard B | — |
| Official CUDA reference | not run (no CUDA host) | 8.44% (paper) | 0.5068 | 0.4054 | 4.68 |

RC6 adds the 2×2 PER attribution (T/V × S_T/S_V) with bootstrap CIs and the
corrected-selection scoreboard B — each arm separately disclosed.

## 5. Performance envelope

Cold start ≈ 46 s (lock→ready); P50 275.27 s / mean 284.78 s / P95 434.33 s
/ P99 496.62 s; AR 164.2 / NAR 42.2 / VAE 78.4 s (means); RTF mean 1.2866;
realtime multiplier 0.7894; 12.64 candidates/h sequential; peak VRAM 29.7
GiB (generation), 42.41 GiB (Q3O judge); Q3O host VmHWM 49.83 GiB under 55
GiB cgroup. Units: GiB = 2³⁰. Full reference:
`reports/developer_reference/06_PERFORMANCE_REFERENCE.md`.

## 6. Resource requirements

Install ~25 GB (env+models); full benchmark ~50 GB + 18 GB backup volume;
Q3O needs ≥ 42.4 GiB free VRAM + ~50 GiB host memory headroom.

## 7. Known limitations & scientific caveats

`docs/KNOWN_LIMITATIONS.md` + the RC6 scientific reports: PER engine
substitution (root-caused, corrected arm separate), Q3O official
equivalence NOT_ESTABLISHED (~20% tied routing, unpublished official tie
rule; same-audio CUDA runbook + comparator ready), SGLang PR unmerged
(pinned snapshot), R1 scheduler busy-spin open upstream, telemetry gaps
(peak_memory_mb 0.0 on ROCm).

## 8. Developer reproduction

Reference CLI + canonical quickstart + verification tool with verdict
vocabulary; fresh-clone same-host reproduction report (Mode 2) +
independent-runner task package; tiered benchmark definition with receipts.

## 9. Security & licensing

- No weights, dataset lyrics, audio, or ASR text redistributed; public
  evidence = hashes/numbers/commands/public-safe fixtures; guards
  (evidence guard, lyrics detector, secret scan) run in CI.
- YuE2 weights CC BY-NC 4.0; WSB dataset terms; evaluator bundle terms
  respected (in-repo patches are env-gated and disclosed, math untouched).
- Historical Git objects: not covered by the working-tree guard — disclosed;
  history rewriting requires explicit owner authorization (not done, not
  planned in RC6; see PR_DEPENDENCY_GRAPH.md §3 for the #7 coexistence
  note and the merge-time guard rule).

## 10. Upstream maintenance plan

`UPSTREAM_PATCH_OWNERSHIP.md`: 6 SGLang-side items (3 absorbed, 2
ready-to-file import guards, 1 open scheduler issue), 6 YuE2-side items
(disclosed substitutions + 2 ready-to-file evaluator items + the Q3O
tie-rule question), repo-local tooling. Version policy + update procedure:
`docs/VERSION_MATRIX.md` + the D7 maintenance schema.

## AMD Acceptance Matrix (AMD01–AMD10)

| ID | Item | Status | Evidence |
|---|---|---|---|
| AMD01 | Hardware validation (gfx1100 W7900D physical) | READY_FOR_REVIEW | identity chain receipts, all sessions |
| AMD02 | ROCm compatibility (7.14.1 userspace pinned) | READY_FOR_REVIEW | install receipts, runtime manifest |
| AMD03 | Runtime reliability (lifecycle, lock, resume) | READY_FOR_REVIEW | lifecycle receipts, restore drill 384/384 |
| AMD04 | Benchmark integrity (official protocol, frozen evaluator) | READY_FOR_REVIEW | protocol.json chains, RC6 provenance audit |
| AMD05 | Performance reporting (units, scope, methodology) | READY_FOR_REVIEW | 06_PERFORMANCE_REFERENCE.md |
| AMD06 | Developer reproducibility (golden path, fresh clone) | READY_FOR_REVIEW | RC6 C-phase reports |
| AMD07 | Security / license compliance | READY_FOR_REVIEW | guard suite, licensing section above |
| AMD08 | Upstream maintainability (patch ownership plan) | READY_FOR_REVIEW | UPSTREAM_PATCH_OWNERSHIP.md |
| AMD09 | Public communication accuracy | READY_FOR_REVIEW | PUBLIC_CLAIMS_MATRIX.md |
| AMD10 | Publication approval | NOT_SUBMITTED | external process |

Machine-readable: `AMD_ACCEPTANCE_MATRIX.json`. No AMD personnel have
reviewed or approved anything in this repository as of this document's
date; RC6 does not and cannot self-grant AMD acceptance.
