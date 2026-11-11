# 00 — Risk Register (living document)

Legend: S=severity (H/M/L), L=likelihood. Owner: mission executor unless noted. Each risk links to a mitigation and, where applicable, a gate.

| # | Risk | S | L | Mitigation / containment | Gate |
|---|---|---|---|---|---|
| R1 | PER parity gap (ROCm 17.0–17.6% vs official 8.44%) is not causally explained; publication of numerical equivalence would be indefensible | H | M(likely persists) | Phase 5 controlled experiments (evaluator-vs-audio-vs-preprocessing-vs-ASR-config-vs-aggregation); declare NOT COMPARABLE if unresolved | G6/G9 |
| R2 | Official evaluator stack is CUDA/vLLM-pinned; exact-parity evaluation on ROCm may be impossible without substitution disclosures | H | H(already true) | Keep 0006/0007/0009 patches audited + env-gated; document transformers-vs-vLLM semantics delta with evidence; never present substituted-evaluator numbers as official-backend numbers | G6/G9 |
| R3 | Q3O needs 80 GB GPU → cannot run on W7900 | M | Certain | Report NOT TESTED with hardware receipt; never claim "all metrics reproduced" | G9 |
| R4 | Fresh full campaigns (2×384 candidates) exceed wall-clock/disk budget | M | M | Durable supervisor + resume + /data 1.8 T volume + low-space thresholds; pilot first | G7/G8 |
| R5 | Native PyTorch Arm A has never been run in prior campaigns (only SGLang/Omni did); unknown ROCm defects in official `yue2`/`yue2_infer 0.1.3` torch path on gfx1100 | M | M | Phase 3 functional acceptance on 16 items before any campaign; isolate failures per layer; prefer upstream-compatible fixes | G3 |
| R6 | Upstream PRs (sglang#42106 etc.) may merge/rebase mid-mission, invalidating frozen stack | L | L(verified open, head unchanged 2026-11-11) | Re-verify PR state before each campaign; freeze Profile B to ced0ef7d | G1 |
| R7 | Model repo revision drift (1a96eca6→8f24312f) could hide weight changes | M | L(file sizes identical; docs-only diff expected) | SHA256-verify model.safetensors against frozen `1d55c42c…` at download; pin revisions per profile | G1 |
| R8 | Egress proxy blocks PyPI JSON/raw.githubusercontent → tooling assumptions break | M | Confirmed | Use git clone + GitHub contents API + pip indexes; record endpoint matrix in evidence | G0 |
| R9 | HF mirror usage could be construed as unofficial distribution channel | L | L | Downloads SHA256-verified against pinned hashes; endpoint recorded in receipts; official endpoint preferred when reachable (it is, on this host) | G13 |
| R10 | CC BY-NC 4.0 model license limits commercial use; blog must not imply permission | H | Certain(license fact) | Licensing report + README/license sections; no weight redistribution; demo audio from original/user-created lyrics | G13 |
| R11 | WildSongBench lyrics are copyrighted dataset content — cannot be embedded in blog/repo | H | Certain | Keep lyrics only in gitignored benchmark tree; publish hashes/IDs only; user-created demo lyrics for examples | G13 |
| R12 | Two SGLang lineages (sglang vs sglang-omni) confuse users; unmerged work could be advertised as official | M | M | docs/COMPATIBILITY_MATRIX.md + explicit "unmerged PR" status everywhere; primary path decision recorded with rationale | G4/G15 |
| R13 | Fresh-clone developer path breaks due to machine-path defaults (`/home/amd/Desktop/YuE2`) | M | Confirmed present | Phase 2 fixes + fresh-clone CI contract tests | G2/G11 |
| R14 | Long benchmark runs interrupted by shell disconnect | M | M | setsid supervisor + checkpoint/resume (already engineered); verify on this host | G7/G8 |
| R15 | Token/secret leakage into evidence | H | L | Token lives outside repo; secret scan before every push (api_git.py already enforces); never echo tokens in logs | G13 |
| R16 | 48 GiB VRAM insufficient for full-song PyTorch backend + evaluation concurrency | M | M | Budget checks, low_vram mode if supported by official path, one-request-at-a-time (official supported mode) | G3/G7 |
| R17 | Historical evidence accidentally rewritten | H | L | Never touch evidence/ (top level) or validation branch; all new evidence under evidence/publication/ | G15 |
| R18 | Statistical overclaim: single-run deltas without CIs | H | M | Freeze acceptance methodology before unblinding full-run aggregates; paired/unpaired analysis as appropriate; publish CIs | G9 |

Change log:
- 2026-11-11 initial register (mission executor, Phase 0).
