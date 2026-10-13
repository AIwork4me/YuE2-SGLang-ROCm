# Phase 3 Patch Review — 50c91c08 "fix(yue2): enable ROCm reference path without regressing CUDA fast paths"

- Repo: /workspace/yue2-omni-pr/repo, HEAD == 50c91c0888312ae784d3c42d9536665aa517dd9d, parent 85ae4b733144fdc8746c5cbc131bdd1a92a8d5a9
- `git status --porcelain`: clean — existing receipts apply.
- Scope: sglang_omni/models/yue2/{stages.py,song.py,fastpath.py,fa3.py}, tests/unit_test/models/test_yue2_platform_gates.py (+237/−6).

## Gate criteria

### 1. CUDA optimized execution unchanged — PASS
- stages.py:46-47 — `if not (current_platform.is_cuda() or current_platform.is_rocm())`: on CUDA, `is_cuda()` is True, `or` short-circuits, no raise — truth-equivalent to parent's `if not current_platform.is_cuda(): raise`.
- stages.py:59 — `default_max_batch_size = "1" if current_platform.is_rocm() else "4"`: "4" on NVIDIA; env precedence unchanged (`os.environ.get(key, default)`).
- song.py:42-45 — gate only appends `and not current_platform.is_rocm()`; on CUDA `not False == True`, reducing to the original 3-term conjunction. Falls into the same `try/except _StepGraphUnavailable` structure.
- fastpath.py:75-81 — new ROCm early-return block sits between the env check (line 71) and backend load (line 82); on non-ROCm it takes `else: pass` and the original control flow (env → `_load_topk_backend` → `torch.cuda.is_available()`) is byte-identical.
- fa3.py:32-33 — `env == "1" and not current_platform.is_rocm()`; on CUDA reduces to `env == "1"`. Full-file diff vs parent confirms only docstring, module-scope platform import, and this gate conjunct changed; `varlen_attention` and the ATen fallback are untouched.

### 2. ROCm uses safe reference execution — PASS
- song.py:42-45 gate is False on ROCm → `_generate_song_tokens_looped` (song.py:56-60).
- song.py:244 — `fast = fast_sampler_available()` → False on ROCm (fastpath.py:75-79) → `sampler = None` (song.py:245) → reference `sampling._decode_loop` distribution.
- synth.py:160-162 — `synthesize_batch` with `len(states) <= 1` routes to per-request `synthesize` → gated `generate_song_tokens`; ROCm default batch 1 (stages.py:59) means the scheduler delivers single payloads → reference path is the default ROCm execution. DeepSelect batched path requires ≥2 states.
- Caveat: batched path has no ROCm gate of its own — see finding P2-1 (config-gated, self-healing via synth.py:179-181 except-fallback).

### 3. Sampling math unchanged — PASS
`git show 50c91c08 --stat`: exactly 5 files; sampling.py not touched. fastpath.py math (FastSampler.sample_token:144-194, GraphSampler.sample_in_graph:311-344, BatchedGraphSampler.sample_in_graph:479-505) untouched — diff adds only the platform import and the early-return block (fastpath.py:75-81).

### 4. Model weights unchanged — PASS
No changes to synth.py, runtime.py, nar*.py, or any checkpoint/state-dict loading. Diff is dispatch-only.

### 5. Seed semantics unchanged — PASS
song.py still seeds identically in both paths: `manual_seed(request.seed)` at song.py:100 (step graph), song.py:108 (reuse), song.py:285/306 (looped). Diff touches only import + gate + comment in this file.

### 6. NVIDIA batch default remains 4 — PASS
stages.py:59-61 (`"4"` when not ROCm). `SimpleScheduler.__init__` stores `max_batch_size` verbatim (simple_scheduler.py:80), so `executor.max_batch_size == 4` in test_cuda_platform_accepted is a valid assertion.

### 7. ROCm batch default 1; env override honored on both — PASS
stages.py:59-61: `os.environ.get("SGLANG_YUE2_BATCH_MAX_SIZE", default_max_batch_size)` — env var wins on both platforms; only the *default* differs. Tests: test_rocm_platform_accepted (==1), test_rocm_batch_size_env_override_still_honored (==3). Minor gap: no CUDA-side env-override test (P3-1).

### 8. Original Step Graph still works on NVIDIA — PASS
song.py:42-45: gate condition only gained `and not current_platform.is_rocm()`; `SGLANG_YUE2_STEP_GRAPH` semantics unchanged (default "1" enables; "0" disables → looped; try/except `_StepGraphUnavailable` fallback preserved). Tests: test_cuda_step_graph_selected, test_step_graph_env_flag_still_forces_looped_on_cuda, test_rocm_step_graph_bypassed.

### 9. DeepSelect CUDA kernels not selected on ROCm — PASS
- fastpath.py:75-79 — `fast_sampler_available()` returns False on ROCm before any backend load.
- song.py:244-245 — on ROCm `sampler = None`; `GraphSampler`/`FastSampler`/`BatchedGraphSampler` are never constructed; step-graph path (song.py:47) is unreachable on ROCm.
- Note: sampling.py:182 honors `use_fast_sampler` override, and batched.py:313 (`_abc_per_request`) passes `use_fast_sampler=True`, bypassing the platform gate — see finding P2-1 (reachable on ROCm only via env override of batch size; synth.py:179-181 ultimately falls back to per-request reference).

### 10. Native ATen varlen path on ROCm — PASS
fa3.py:32-33 gate makes `_load_varlen()` return None on ROCm → `varlen_attention` falls through to fa3.py:68-70:
`torch.ops.aten._flash_attention_forward(q, k, v, cu_seqlens_q, cu_seqlens_k, max_q, max_k, 0.0, False, False, seqused_k=seqused_k)[0]`
Byte-identical to the pre-existing fallback (verified: full-file diff vs parent shows zero changes below line 33). Same `seqused_k` kwarg and GQA (HQ vs HKV heads) semantics. test_rocm_varlen_uses_native_aten asserts the shared FA op must not run, `calls[0][1]["seqused_k"] is seqused_k`, and one call.

### 11. No new AMD-only kernels introduced — PASS
Diff adds conditionals, comments, a docstring paragraph, a module-scope import, and tests. No kernel/Triton/extension code anywhere in the hunks.

### 12. No unrelated refactoring — PASS (hunk-by-hunk audit)
- fa3.py: (a) docstring ROCm sentence, (b) platform import, (c) gate conjunct — all in-scope.
- fastpath.py: (a) platform import, (b) signed comment + ROCm early-return block.
- song.py: (a) platform import, (b) signed comment, (c) gate conjunct.
- stages.py: (a) gate broadened + error message, (b) per-platform default + signed comment.
- tests: new file, every test targets one of these gates.
No drive-by renames/moves/whitespace churn. Pre-existing duplicate import song.py:19/25 untouched (not introduced here).

## Test execution (CPU-only dispatch simulation — verified safe first)
- Venv used: /workspace/yue2-omni-pr/env-omni-rocm/bin/python (exists).
- Safety inspection before running: no conftest.py anywhere under tests/; pyproject pytest config is `pythonpath=["."]` only; import chain (stages → synth → batched → cuda_graph/fastpath/sampling) is pure PyTorch — cuda_graph.py header: "No vLLM, Triton, or custom extension is imported". Test file allocates only CPU tensors, constructs `torch.device("cuda")` without allocation, and monkeypatches `torch.cuda.is_available` and `torch.ops.aten._flash_attention_forward`. No servers, no GPU memory. Safe to run alongside the benchmark.
- Result: **12 passed in 4.47s** (all 12 tests listed, no skips).

## Test quality
- Covers both is_rocm=True/False branches of all four gates: stages (cuda/rocm/cpu + ROCm env override), song (cuda/rocm + env flag), fastpath (cuda/rocm + env disable), fa3 (cuda/rocm).
- Explicit NVIDIA assertions: test_cuda_platform_accepted (batch 4), test_cuda_step_graph_selected, test_cuda_fast_sampler_unchanged, test_cuda_varlen_dispatch_unchanged (asserts shared-op kwargs `{seqused_k, causal: False, ver: 3}`).
- Gaps: no CUDA-side SGLANG_YUE2_BATCH_MAX_SIZE override test (P3-1); test_cuda_fast_sampler_unchanged can pass via the `_TORCH` fallback (fastpath.py:67) rather than DeepSelect presence (P3-2).

## Lint / compile
- `python -m ruff check sglang_omni/models/yue2/ tests/unit_test/models/test_yue2_platform_gates.py` (env-omni-rocm): **All checks passed** (tests/** excluded by pyproject anyway).
- `python -m py_compile` all 5 changed files: OK.

## Licensing / metadata
- LICENSE present at repo root; files carry Apache-2.0 SPDX headers; new test file's SPDX line matches repo convention (not a fabricated copyright header).
- Commit author: `AIwork4me <AIwork4me@users.noreply.github.com>` — as expected.
- No CLA/DCO/CONTRIBUTING files required: `git ls-tree -r HEAD --name-only | grep -iE 'cla|contributing|dco'` matched only unrelated paths (.claude/skills/*, CLAUDE.md, router classification .rs files).
- Style (per .claude/skills/code-review/coding-style.md): `else: pass` chains preserved; comments signed `# note (AIwork4me):`; imports at module scope; no backticks in comments.

## Findings

- **P2-1 (latent, config-gated):** batched.py has no ROCm gate. `run_batched_ar` (batched.py:320) builds `BatchedGraphSampler` (DeepSelect) and replays CUDA graphs; `_abc_per_request` (batched.py:313) passes `use_fast_sampler=True`, bypassing `fast_sampler_available()` at sampling.py:182. On ROCm this is reachable only if an operator overrides `SGLANG_YUE2_BATCH_MAX_SIZE>1` (default 1 keeps `synthesize_batch` on the single-request reference path, synth.py:160-162). If reached, failures propagate to synth.py:179-181 `except Exception` → per-request reference fallback, so outputs remain correct, but with exception storm and log noise. Recommend follow-up: platform-gate `run_batched_ar` (or `_abc_per_request`'s `use_fast_sampler`).
- **P3-1:** No test that `SGLANG_YUE2_BATCH_MAX_SIZE` override is honored on the CUDA/default branch (only the ROCm side is tested).
- **P3-2:** test_cuda_fast_sampler_unchanged asserts `True`, which the `_TORCH` fallback (fastpath.py:67) can satisfy even without DeepSelect; asserting the backend identity would pin the CUDA fast path more strongly.
- **P3-3 (pre-existing, out of scope):** song.py:25 duplicates the protocol import from song.py:19 — untouched by this diff.

No P0 or P1 findings.

## PHASE3_VERDICT: PASS
