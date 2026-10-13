# Final Review A — ROCm/NVIDIA Compatibility (independent audit)

Date: 2026-10-13. Patch under audit: commit `50c91c0888312ae784d3c42d9536665aa517dd9d` in /workspace/yue2-omni-pr/repo (HEAD, worktree clean — verified `git status --porcelain` = 0 lines). All checks performed read-only; source of truth read directly, not via intermediaries.

## Section 1 — Real W7900 evidence — PASS

All five files exist on branch `evidence/omni-http-gfx1100` of the evidence repo (read via `git show`):

- `evidence/omni_http/environment.json` — AMD Radeon Pro W7900D (gfx1100, 47.98 GiB), ROCm 7.14.1 (torch hip 7.14.60850), torch 2.12.0+rocm7.14.1, `cuda_available: true` with `gcn_arch: gfx1100` (HIP-names-CUDA confirmed in situ). Server: `sgl-omni serve --model-path .../YuE2-3B --port 32100` with `SGLANG_YUE2_BATCH_MAX_SIZE=1` — consistent with the patched ROCm default (stages.py:59). Discloses environment-only `python-multipart` install (category G, out of PR scope).
- `source_manifest.json` — head `50c91c08...` matches actual repo HEAD; `worktree_clean: true` re-verified; pristine upstream sglang checkout (`ccae40c`, empty diff); model/vae revisions pinned.
- `smoke_response.json` / `full_response.json` / `audio_validation.json` — cross-consistent: smoke audio sha256/frames(982976)/rms/peak identical in smoke_response and audio_validation; full frames 2267456.

Raw-body SHA256 recomputed independently with `sha256sum`:
- `/workspace/yue2-omni-pr/http-e2e/response.body` → `358ffc66b6d899231dc75fc5c9bcef0b0f1840e2c2532dff4363357d2882feed` ✔ matches expected + smoke_response.json
- `/workspace/yue2-omni-pr/http-e2e/full_response.body` → `218634d46abfe48f1aa27c3dd43d6d84e1776fc6c64e6c0dc772fd52330526bd` ✔ matches expected + full_response.json

Byte math independently recomputed (PCM16 stereo 48 kHz + 44-byte RIFF header): 982976·4+44 = 3,931,948 = content_length ✔; 2267456·4+44 = 9,069,868 = content_length ✔. Durations 20.479 s / 47.239 s ✔. The two waveforms are distinct (different budgets), not a cached replay. `gpu_trace_note` honestly discloses that the smoke-window GPU trace is inferential — good epistemic hygiene.

**Verdict: PASS.**

## Section 2 — Minimality — PASS

`git show --stat 50c91c08`: exactly **5 files changed, 237 insertions(+), 6 deletions(-)**:
- 4 source files, **+30/−6** total: fa3.py (+8/−1), fastpath.py (+9/−0), song.py (+7/−1), stages.py (+6/−4) — all under `sglang_omni/models/yue2/`
- 1 test file: `tests/unit_test/models/test_yue2_platform_gates.py` (+207/−0)

No other files touched; sampling math, weights loading, synth.py/runtime.py untouched (confirmed by full source diff read). Matches spec exactly.

**Verdict: PASS.**

## Section 3 — CUDA fast-path preservation — PASS

Read all four files at HEAD **and** diffed against parent `85ae4b73`. Every gate is the original expression plus a ROCm-only conjunct/branch:

1. **stages.py:46** — `if not (current_platform.is_cuda() or current_platform.is_rocm())`. Parent: `if not current_platform.is_cuda():`. On NVIDIA, `is_rocm()` is False → truth-identical; new error message unreachable on working NVIDIA hosts.
2. **stages.py:59** — `"1" if current_platform.is_rocm() else "4"`; parent had constant `"4"`. NVIDIA default 4 preserved; `os.environ.get` precedence unchanged.
3. **song.py:42-45** — step-graph gate only appends `and session.device.type == "cuda"`→ parent's `and session.device.type == "cuda"` retained, plus `and not current_platform.is_rocm()` (line 45). On NVIDIA: `not False` = no-op; original 3-term conjunction intact; `SGLANG_YUE2_STEP_GRAPH` semantics unchanged.
4. **fastpath.py:75-81** — ROCm early-return inserted between env check (line 71) and backend load (line 82); non-ROCm takes `else: pass` → original chain (env → `_load_topk_backend` → `torch.cuda.is_available()`) byte-identical.
5. **fa3.py:32-33** — `env == "1" and not current_platform.is_rocm()`; parent: `env == "1"`. No-op on NVIDIA; `varlen_attention` and ATen fallback untouched.

**Phase 3 report spot-check** (/tmp/opencode/phase3_patch_review.md): its central claims independently reproduced — the four gate sites match my own HEAD read + parent diff line-for-line, and the test file's NVIDIA-branch assertions exist and are real:
- `test_cuda_platform_accepted` (test:66-69) asserts `max_batch_size == 4`
- `test_cuda_step_graph_selected` (test:116-120) asserts step-graph on CUDA
- `test_cuda_fast_sampler_unchanged` (test:138-143) asserts True on CUDA
- `test_cuda_varlen_dispatch_unchanged` (test:188-207) asserts shared-op dispatch with exact original kwargs (`seqused_k`, `causal=False`, `ver=3`)
- Env-override semantics on CUDA also asserted (test:123-127, 146-151). File contains exactly 12 tests, matching the "12/12" claim.
- ROCm-side assertions verified too (test:72-87, 109-113, 130-135, 161-185), including `torch.cuda.is_available → True` while fast sampler returns False — proving the platform check, not the CUDA check, does the gating.

Not re-executed (read-only mandate; pytest would write `__pycache__`): the 12/12 pass run, 37/37 capability run, and 51-case simulated A/B matrix are consistent with file contents and the Phase 3 report but not re-run here.

**Verdict: PASS (gate preservation independently confirmed; test re-execution NOT TESTED — read-only).**

## Section 4 — Actual ROCm path vs source_manifest — PASS

`execution_paths_on_rocm` checked against code at HEAD:
- `ar`: looped reference generator, "song.py:44-51 gates ... via current_platform.is_rocm()" — gate conjunct is at **song.py:45**; cited range 44-51 covers it (range slightly imprecise, substance correct).
- `attention`: "fa3.py:31-33 skips shared FA3 op" — actual **fa3.py:32-33** ✔.
- `fast_sampler`: "disabled on ROCm (fastpath.py:75)" — line 75 is exactly `if current_platform.is_rocm():` ✔ exact.
- `step_graph`: "bypassed on ROCm (song.py:45)" ✔ exact.
- `deepselect`: disabled — consequence of fastpath.py:75 + song.py:45 ✔.
- `nar` (HIP-graph velocity capture) and `vae_decoder`: runtime observations of untouched code paths — consistent with dispatch-only patch scope; no gate exists or is needed.

Manifest and code agree.

**Verdict: PASS.**

## Section 5 — Unsupported claims in live PR body + comment — PASS

Live PR body (`gh pr view 1`) and posted comment (id 6144689787, fetched via `gh api`; note the alias `issuecomment-6144689787` 404s — numeric id works) audited against the prohibited-claim list:

| Claim type | Found? | Evidence |
|---|---|---|
| Cross-vendor bit-identity | **No — explicitly disclaimed twice** | "Identical audio SHA256 is **not** expected across GPU vendors"; "audio is not expected to be bit-identical across GPU vendors"; comment: "No need to match the audio SHA256" |
| Quality parity | **No** | "**Not claimed:** ... no performance/quality parity claim beyond the author's own evaluation of the base PR" |
| Performance numbers | **No claim; observational evidence only** | Elapsed 15.25 s/38.11 s, GPU util 0→100%, VRAM 21→35% presented as real-execution evidence with the smoke-window gap disclosed; "performance optimization is explicitly out of scope". No speedup/throughput/comparison-to-NVIDIA claims. |
| Production-readiness | **No** | "Known limitations" section; "Verified on W7900 (gfx1100) only"; "not a long-form endurance or stress claim" |
| H800 execution by our team | **No — explicitly denied** | "a real NVIDIA run of this exact commit has not been performed by our team"; comment: "**We have no H800**" — H800 framed as an outstanding request of the maintainer |
| WSB closure | **No** | String "WSB" absent from body and comment |

The PR actively requests H800 confirmation from the maintainer rather than asserting it. All W7900 results quoted in body/comment match the evidence JSONs byte-for-byte (SHAs, durations, RMS, config).

**Verdict: PASS.**

---

## REVIEWER_A_VERDICT:

- Section 1 (Real W7900 evidence): **PASS**
- Section 2 (Minimality, 5 files +237/−6; 4 sources +30/−6): **PASS**
- Section 3 (CUDA fast-path preservation): **PASS** (gate sites + NVIDIA test assertions independently spot-checked; pytest re-execution NOT TESTED — read-only mandate)
- Section 4 (ROCm execution paths vs manifest): **PASS**
- Section 5 (No unsupported claims in PR body/comment): **PASS**
- **Overall: PASS**
