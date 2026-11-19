# RC2_06c — Upstream contribution matrix (RC2 revision of 07_UPSTREAM_PATCH_MATRIX.md)

Live states re-verified 2026-11-19; RC2 evidence folded in. Nothing was
submitted from this session; every row is owner-gated.

| Target | Item | Contribution-ready? | Proven on W7900D | Untested on CUDA | Local workaround (not general fix) | Action (owner-gated) |
|---|---|---|---|---|---|---|
| sgl-project/sglang | #42106 "Add yue2" | patches 0001–0005, 0008 re-applied + verified on pristine `ced0ef7d` | full 384-candidate campaign in flight; acceptance incl. real generation | ROCm guard deltas untested on CUDA CI | — | post-campaign: attach W7900D validation receipts as PR comments |
| sgl-project/sglang-omni | #2540 (port) | same patch lineage | historical omni campaign 384/384 FULL (PER 17.61 %, own generation) | same | — | same |
| yiakwy …/sglang-omni | #1 ROCm reference path | our 0001–0005 chain overlaps/supersedes | acceptance PASS incl. 33.1 s real generation | — | — | reconciliation comment w/ fresh receipts |
| yiakwy …/sglang-omni | #2 full-song lyrics | exercised by every WSB full-song request (multiple campaigns) | yes | — | — | same |
| m-a-p/WildSongBench | 0010 torch-eager allowlist (1-line; no scoring-math change) | YES — bit-exact chain tests + fresh Arm A campaign ran under it | yes (384/384 + 4 metrics) | n/a (CPU-side guard) | — | open upstream issue + submit after owner approval |
| m-a-p/WildSongBench | 0006/0007/0009 evaluator ROCm backend | DISCLOSED only; needs author conversation (may be accepted as ROCm backend or replaced by their fix) | all fresh scorings used them; disclosed in every report | CUDA-side equivalence UNPROVEN (this is exactly the PER question) | **yes — treat as workaround until A2/B2 resolve** | author request item 1/3; no submission before |
| m-a-p/YuE (upstream impl) | `close()` device-memory behavior (~10.2 GiB before, ~0.34 GiB released) | DOCUMENTED; minimal report draft after M4.3 re-validation | observed on fresh image | — | one-process-per-song is OUR supported pattern | upstream discussion after M4.3 (owner-gated) |
| m-a-p/YuE | staged-API footguns (3) | DOCUMENTED | PYTORCH_API_ACCEPTANCE | — | — | docs PR proposal (owner-gated) |
| sgl-project/sglang | AR-stage hang (~1/300 historical) | NO — root cause open; watchdog = operational mitigation only | historical evidence | — | watchdog | nothing until M4.1 root-causes it |
| ROCm/HIP layer | illegal memory access under GPU sharing | NO — serialized single-tenant is an enforced POLICY, not a fix | two full campaigns solo-clean | — | **yes — gpu_lock policy** | minimal reproducer first (M4.2), then route |

New in RC2 (not upstream items, repo-internal): the five engineering fixes
from PR #16 (resume-status chain stall, opt-in live-server tests, bounded
scoring, mutation-pinned invariants, docs repair) — already landed on the
rc2 branch for owner review; no external visibility required.
