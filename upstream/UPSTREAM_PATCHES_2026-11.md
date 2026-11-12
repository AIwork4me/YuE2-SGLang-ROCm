# Upstream patch handoff (2026-11 mission) — PREPARED, NOT SUBMITTED

Owner approval required before any upstream submission
(mission rule: no public upstream PRs/comments without explicit approval).

## Patch U-1 — WITHDRAWN (already fixed upstream)

Originally prepared: runtime probe for varlen FlashAttention capability.
Verification against YuE main @ `1116bea7` shows the dispatch already guards
`torch.version.hip` explicitly (`src/yue2/cuda_graph.py` capability function
returns flash=False on ROCm), matching hardware.md's "Eager AR with public
SDPA" AMD path. The defect exists only in the frozen `yue2-infer 0.1.3`
wheel used by the benchmark reproduction recipe. **No upstream action
needed**; Arm A documents the `torch-eager` backend as the 0.1.3-on-ROCm
path (DEV-1). Candidate note to the authors (approval-gated): consider
allowing `torch-eager` configs in the evaluator (see U-2) and noting the
0.1.3-wheel ROCm backend in the WSB recipe.

## Patch U-2 — WildSongBench evaluator: accept the official torch-eager backend label

- **Target:** `m-a-p/WildSongBench` `evaluation/wsb_metrics/wsb_eval.py`
  (`validate_generation`).
- **Root cause:** `code/generate.py` officially offers `--backend
  torch-eager`, but the evaluator's admission control rejects
  `config.backend == "torch-eager"` ("Unrecognized inference backend"),
  making officially supported eager runs unscorable.
- **Fix:** allowlist `{'torch', 'vllm', 'torch-eager'}`. Admission control
  only; no scoring/selection/aggregation change.
- **Locally applied as:** patch 0010 under the ROCm disclosure chain
  (release.json updated, hashes pinned).
- **Hardware tested:** gfx1100 (Arm A pilot scored end-to-end).

## Patch U-3 (informational) — sglang#42106 ROCm capability guards

Already handed off upstream in October (patches 0001-0005, 0008 on
`ced0ef7d`); no changes this mission. See `upstream/SGLANG_PATCH_HANDOFF.md`.

---

# PR organization plan for THIS repository (drafts for owner review)

| PR | Content | Base | Status |
|---|---|---|---|
| A — Reproducibility & security hardening | workspace contract, auditor v3, safe extraction, CI expansion, docs-contract + lock tests, machine-path removal | main | ready (commits 6f87469, 3bd848c, dd18a61) |
| B — Native PyTorch ROCm developer path | run_wsb_torch.py + tests, PYTORCH_API docs, examples (after GPU-window verification), DEV-1 documentation | A | ready except examples verification |
| C — SGLang/Omni compatibility & serving | setup_sglang_gfx1100.sh, sglang-rocm-deps.txt, SGLANG_API docs, RCA-3 guard, harness fixes (3cd96d5) | A | ready |
| D — WildSongBench reproduction & scientific evidence | campaigns Arm A/B receipts, evaluator 0010 provenance, PER RCA evidence, fetch_eval_assets_hub.py, scoring + stats | A | after campaigns |
| E — Public documentation & blog readiness | README restructure, RESULTS, EVIDENCE_INDEX, QUICKSTART, blog claims matrix, author handoff | A–D | last |

Rules: never merge without owner review; each PR carries its own evidence
links; upstream submissions stay separate and approval-gated.
