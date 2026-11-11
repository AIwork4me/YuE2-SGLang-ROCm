# 01 — Upstream Gap Analysis (Phase 1)

**Audit date:** 2026-11-11 (token-verified against live GitHub/HF APIs) · **Branch:** `feat/yue2-rocm-publication-readiness`

## 1. Current upstream state vs the frozen campaign

| Source | Frozen pin | Current state (2026-11-11) | Delta | Action |
|---|---|---|---|---|
| sgl-project/sglang#42106 | head `ced0ef7d` | **OPEN**, head `ced0ef7d` (updated 2026-11-02, no new commits) | none | Arm B stack remains exactly the frozen one |
| sgl-project/sglang-omni#2540 | `85ae4b73` (historical campaign used fork PR) | **OPEN**, head `85ae4b73` (updated 2026-11-06) | none | secondary path; regression-test if promoted |
| yiakwy fork PRs (#1 omni, #1 benchmark-fork) | `eca7770f`, `def437fb` | both **OPEN** (untouched since Oct) | none | our own contributions; still pending upstream |
| m-a-p/YuE main | — (campaign used wheel) | `1116bea7` (2026-11-01): XPU graph-capture work merged | ROCm path still "Eager AR + public SDPA" (no gfx1100-specific changes) | Profile A uses main-or-release; no conflict with Profile B |
| YuE releases | v0.1.6 (mission planning) | + `yue2-music-v1.2.0` (2026-09-25): instrumental generation & covers (agent skill; "Inference requires a compatible NVIDIA GPU") | new capability, NVIDIA-framed | document as upstream feature; AMD verification out of scope unless requested |
| m-a-p/YuE2-3B | rev `1a96eca6` | head `8f24312f` (2026-10-06): README-only diff (19,050→21,898 B); `model.safetensors` byte-identical size; **our sha256 re-verification: `1d55c42c…` MATCH** | docs only | benchmark lock unaffected; developer profile may track head |
| m-a-p/YuE2-Vae / -legacy | legacy `b54118f0` | heads `152733a1` / `d0585a9c` (2026-09-29 metadata) | no weight changes detected (sizes equal); pinned revisions immutable | benchmark lock unaffected |
| m-a-p/WildSongBench | `e361b85a` | **unchanged** (still head) | none | frozen manifest remains the current official release |

**Conclusion:** no upstream movement invalidates the frozen campaign stack. Nothing YuE2-related has merged into any upstream main branch; all five PRs remain open. No historical compatibility patch duplicates new upstream work.

## 2. Implementation differences A/B/C (per mission §1.2)

| Capability | A: official native PyTorch (yue2-infer 0.1.3) | B: original SGLang (#42106 @ ced0ef7d + patches) | C: SGLang-Omni (#2540 + fork PR #1) |
|---|---|---|---|
| AR decode | HF generate; GraphAR (CUDA) or eager (ROCm required) | session GraphAR w/ HIP graphs + ATen flash (validated) | same family as B |
| NAR / VAE | torch eager, fp32 VAE | torch ops in server process | same |
| Fast kernels | none (public SDPA) | DeepSelect/step-graph/batched-AR DISABLED on ROCm (0004 guards) | same guards via fork PR |
| API | Python `YuE2Pipeline`; CLI `yue2 generate` | HTTP `/v1/audio/generations` (PR route) | HTTP `/v1/audio/speech` (Omni route) |
| Upstream status | released (wheel in model repo; WSB reproduce recipe) | **unmerged PR** | **unmerged PR** |
| Verified on gfx1100 | pilot PASS (this mission) | historical 384/384 + today's smoke PASS | historical 384/384 (validation branch) |

**Primary public-facing SGLang entry point decision:** keep **original SGLang (#42106)** as Arm B primary — it is the branch the YuE2 authors submitted, it carries both historical 384/384 W7900-class campaigns' patches, and Omni remains a port pending its own upstream merge. Omni is regression-tested as the secondary path.

## 3. Gaps found and disposition

1. **Official `--backend torch` (graph capture) is broken on ROCm** — new finding this mission: GraphAR's capability probe checks only the aten schema (`seqused_k` present) and picks varlen FlashAttention; the ROCm kernel rejects `seqused_k` (`RuntimeError: [ROCm] mha_varlen_fwd: seqused_k must be nullopt`). Workaround-free official alternative: `--backend torch-eager` (public-SDPA path hardware.md documents for AMD). Recorded as DEV-1; candidate minimal upstream patch (capability probe via 4-element probe call, NVIDIA-neutral) prepared for owner-approved upstream submission.
2. **Evaluator asset download via urllib is proxy-fragile** — the evaluator's own downloader cannot traverse this host's egress proxy (503 on large files). We added `scripts/fetch_eval_assets_hub.py` (huggingface_hub-based, same pins, same sha256 verification) without touching evaluator code.
3. **pip build isolation pulls CUDA torch for `pip install -e sglang`** — must use `--no-build-isolation` (documented in setup_sglang_gfx1100.sh; caught live this mission before any pollution).
4. **Stale test/script API drift** (committed tests targeted an older auditor API) — fixed in Phase 2 (auditor v3 restores the campaign schema).

## 4. Recheck cadence

Re-verify PR states before each campaign start and before final publication (§ Phase 7 discipline); record in run receipts.
