# UPSTREAM_PATCH_OWNERSHIP.md — RC6 D3: per-issue upstream ownership

Every ROCm-facing change in this repository, classified by where it belongs
upstream. Rule: one issue → one destination → one minimal reproducer. We do
NOT plan a single mega-PR.

## A. SGLang (sgl-project/sglang) — import guards & capability gates

| # | Problem | Our patch | Minimal reproducer | Regression test | Hardware validation | Removal condition | Upstream destination |
|---|---|---|---|---|---|---|---|
| A1 | `aiter.*` module-level imports assume HIP ⇒ aiter (Instinct-only; RDNA has no build) → ModuleNotFoundError on any model import | 0001/0002/0003 try/except ImportError → None (exact non-HIP fallback shape) | import sglang model on gfx1100 without aiter | `tests/test_yue2_rocm_fallbacks.py::test_quantization_chain_imports` | W7900D + historical gfx1151 | upstream adopts guarded imports (or ships RDNA aiter) | sgl-project/sglang (small standalone PR; also relevant to amd-miopen/aiter) |
| A2 | `sgl_kernel`/kvcacheio unguarded imports make `sglang serve` fall back to the LLM backend on ROCm (PyPI sgl_kernel = CUDA sm100) | 0008 import guards | `sglang serve` boot on ROCm without sgl_kernel | boot smoke + serve receipt | W7900D | upstream guards or ships ROCm sgl_kernel | sgl-project/sglang (standalone PR) |
| A3 | DeepSelect/sgl_kernel fast paths selected on import-availability, crash at call time on ROCm | 0004/0005 capability gates (**ABSORBED upstream at 2a816358d — NOT reapplied; verified**) | attempt fast path on gfx1100 | upstream's own gates (plan.json execution fields) | W7900D | already absorbed | CLOSED upstream (track #42106 evolution) |
| A4 | Scheduler idle busy-spin after a completed batch (R1: ~99% one core, 0% GPU, hours; HTTP healthy) | in-repo lifecycle: readiness checks + drain/stop per session (docs/KNOWN_LIMITATIONS) | live capture 2026-11-22 04:51–13:36Z (RC4 evidence) | `server_readiness.py` + lifecycle receipts | W7900D | upstream fixes the spin loop | sgl-project/sglang issue (with the capture log); **OPEN, not filed** |
| A5 | vLLM 0.19.1 ROCm platform probe: amdsmi shim raises after a SUCCESSFUL init → plugin swallows its own success → UnspecifiedPlatform → "Device string must not be empty" | in-runner workaround: register RocmPlatform directly (disclosed in engine receipt) | boot vLLM 0.19.1 on this host | `rc5_asr_vllm_native.py` engine receipt (`vllm_platform: RocmPlatform`) | W7900D | amdsmi shim / vLLM probe fixed | vllm-project/vllm issue (+ AMD amdsmi); **draft ready, not filed** |

## B. YuE2 / authors (m-a-p) — evaluator & model behaviour

| # | Problem | Our adaptation | Minimal reproducer | Test | Validation | Removal condition | Destination |
|---|---|---|---|---|---|---|---|
| B1 | qwen_asr **transformers** backend: greedy decode falls into whitespace repetition loop (`language None<asr_text>` + skipped tokens) on knife-edge audio where vLLM transcribes normally | none (we disclosed + root-caused; corrected arm uses vLLM) | SHA-bound audio + both engines' outputs + first-divergence probe (07_ASR_FIRST_DIVERGENCE.json) | E1–E8 same-audio matrix | W7900D | upstream fixes the loop | YuE2/WildSongBench evaluators (public issue carries hashes/numeric receipts only — audio is benchmark-restricted); **draft ready, not filed** |
| B2 | evaluator `--mode standard` rejects `backend: torch-eager` configs (allowlist gap) | 0010 allowlist admission only | config with backend torch-eager | evaluator suite | W7900D | upstream allowlist updated | WildSongBench evaluator (patch prepared for owner-approved submission) |
| B3 | evaluator env admission assumes CUDA torch-family | 0006 env-gated exemption (+ receipts) | evaluator venv with ROCm torch | per.environment.json receipts | W7900D | evaluator ships ROCm env support | WildSongBench evaluator |
| B4 | evaluator PER assumes vLLM 0.14.0 (no ROCm build) | 0007 transformers backend under the same env gate (disclosed substitution; math untouched) | PER run on ROCm | parity study + RC5.1/RC6 arms | W7900D | vLLM 0.14+ ROCm build exists | WildSongBench evaluator |
| B5 | Q3O judge needs 80 GB-class GPU under the official engine | ROCm-adapted judge (34 GPU + 14 CPU MoE, stable tie-break) — NOT claimed equivalent | Q3O run on 48 GB | 5-run/2-process token identity | W7900D | official engine runs on ≤48 GB (or official tie rule published + comparator run) | YuE2 authors (acceptance A09/A10) |
| B6 | official vLLM MoE top-k tie-break rule unpublished (decides ~20% of routed slots) | none (disclosed + quantified) | real-router tie statistics (03_Q3O_REAL_ROUTER_ANALYSIS.json) | mutation R3/R4 | W7900D | rule documented | YuE2/WildSongBench (question, not a PR) |

## C. This repository (AIwork4me) — no upstream destination

Lifecycle supervisor (GPU lock atomicity), fail-closed resume, identity
contracts, verification tooling, docs, RC6 evidence — maintained here;
nothing to send upstream beyond the items above.

## Submission policy

- No external issue/PR/comment is filed without explicit owner
  authorization (B5 package + drafts are READY).
- Each external submission carries: problem, minimal reproducer, patch
  (when applicable), hardware receipt pointers, and NO benchmark-restricted
  content (audio/lyrics/ASR text).
- Upstream PR #42106 monitoring: pinned snapshot `c67d541a`; if the PR head
  moves, re-audit `02_UPSTREAM_DELTA_REVIEW.md`-style diffs and run a
  bounded pilot regression BEFORE extending any claim to the new head
  (never auto-extend the 384-campaign validation).
