# Independent reviews — verbatim (this mission)

Executed 2026-10-16 by separate read-only subagents (not the implementer).
Light formatting only; verdicts and findings unedited.

---

## Plan audit (pre-implementation)

VERDICT: **APPROVED-WITH-CONDITIONS** — validated adversarially and
empirically: the auditor applied the full plan to a copy of the tree
(216 substitutions) and obtained checker exit 0, compileall OK, 25/25
focused tests passing, imports OK, diff identifier-only.

Findings: P1 — `_hf_fields`/`_inference_fields` renames must include the 4
UNFLAGGED class-body assignment sites (modeling_yue2.py:95,127;
modeling_vae.py:297,329), else AttributeError on config construction
(applied). P2 — header arithmetic is 6 noqa lines / 7 violations; closure
must reconcile 165 renamed + 7 noqa = 172 (applied). P2 — noqa placement on
cuda_graph.py:196 and fa3.py:81 must be line-exact (applied; final line
numbers shifted to 200 after black rewrap — still within statement span,
checker green). P3 — MIGRATION.md:29 `_TorchTopKBackend` stale (applied);
"62-test suite" wording (62 = 12+13+37 across three files — correct);
upstream quantization.py claim unverifiable from the sandbox (we verified it
directly via the GitHub code-search API: multimodal-art-projection/YuE
src/yue2/quantization.py:83 sets the attribute); deviation taxonomy
(cosmetic).

Collision audit: all three claimed collisions REAL (self.capture bool;
local causal_mask; offload_ar param); no missed collisions (full scope
analysis of every rename + passing simulation). Completeness: zero missed
references (test setattr strings included). External contracts: `_init_weights`
called by installed transformers modeling_utils.py:2514 (+2951/3093) —
noqa justified, ALLOWED_DEFS precedent confirmed. State_dict: single
register_buffer("pe") untouched; to_dict() instance-dict-only confirmed
against installed transformers; simulation shows no old/new names in output.

---

## Reviewer A — Python architecture and rename correctness

**Overall: PASS.** Scope items 1–7 all PASS (mapping completeness verified
by word-boundary sweep; no collisions; 76 tests + 22 imports pass on the
ROCm env; checkpoint compatibility verified — one register_buffer("pe"),
no renamed registered names; diff = renames + 6 noqa + 1 import reorder +
2 setattr strings + 1 doc line + new test file; noqa exceptions justified
and minimal; independent AST check: ast.dump EQUAL for all 12 files).

Findings (no P0/P1/P2):
- P3: noqa reason wording "set by upstream YuE quantization.py" vs the
  coding style's provenance rule — "arguably covered by the one-line
  constraint-comment allowance"; optional reword. [Accepted as-is; upstream
  attribution is explicitly preserved by the style guide; tree kept
  byte-identical to the GPU-tested artifact.]
- P3: black re-wraps are an extra disclosed diff category, AST-neutral.
- P3: RENAME_MAP cites pre-rewrap line 196; final 200 (doc nit).

---

## Reviewer B — CUDA + ROCm runtime preservation

**VERDICT: PASS** (static equivalence proven; ROCm reference path
GPU-proven via completed smoke; CUDA fast path NOT GPU-executed).

Method: token-stream equivalence on all 12 sources — "the only changed
tokens are NAME→NAME under one globally consistent 58-symbol map — zero
NUMBER, OP, keyword, or logic-bearing STRING edits"; repo-wide straggler
sweep zero. Findings: P3 ×3 (paired getattr cache-key strings — required,
pinned by regression test; import member reorder — runtime-inert; noqa/black
formatting only).

Scope confirmations: CUDA fast path (sampler chain mask→penalty→div→topk→
topp→multinomial token-identical; fused decode sgl_kernel sequence;
seqused_k schema probe; capture warmup range(3) + stream sync order +
register_generator_state; VelocityGraph warmup range(2)); ROCm gates
byte-identical (fast_sampler_available is_rocm→False; song gate `and not
current_platform.is_rocm()`; stages.py and synth.py md5-IDENTICAL parent vs
new, batch default "1" if is_rocm() else "4" intact); orchestration
(shift_t_value 1 def + 4 call sites consistent; decode_loop signature
unchanged; self.backend = attention no shadowing); numerics (manual_seed
sites, temperature/top_p/top_k/penalty flows, ODE 32-step midpoint, VAE
halo math) — identifier-only per token proof. Tests: 26 passed (12 gates +
14 rename-regression), CPU mocked — not GPU proof.

NOT TESTED: physical H800 / CUDA fast-path execution (token equivalence
only). ROCm: smoke completed — "b91b95440 clean tree, PYTHONPATH shadow
verified, W7900D, torch 2.12.0+rocm7.14.1, HTTP 200, valid 48kHz stereo
12.0s WAV (rms 0.096, peak 0.795), zero renamed-symbol errors". Caveats:
looped-path selection implied by the is_rocm gate; batched/streaming/fp8
and 32-step default not exercised.

---

## Reviewer C — Upstream CI and merge engineering

**VERDICT overall: PASS** (locally testable scope); upstream CI claim:
NOT TESTED (0 check-runs by design).

1. Lint PASS (checker exit 0; pre-commit all Passed/Skipped; no policy file
   touched). 2. Minimal diff PASS (exactly 15 expected files). 3. Ancestry
   PASS (b91b95440^ = ae11c6ad; full graph verified; branch local-only at
   review time). 4. Author-branch immutability PASS (add_yue2 = 85ae4b733
   unchanged; PRs #1/#2 OPEN; PR#2540 head unchanged, BLOCKED; no new PRs
   by us; 2 pre-existing AIwork4me comments on author PR#1 from the earlier
   evidence phase — no git impact). 5. Maintainer-acceptance risk LOW
   (noqa narrow + reasoned; renames consistent; F401 noqa pre-exists).
   6. Author procedure tree-proven via merge-tree: merge(85ae4b73, eca7770f)
   tree 0002fb3c == tree(075f1c62); +4c089d19 → 7fdead12 == tree(19efab35)
   → cherry-picks apply cleanly by construction. 7. CI reality: 0
   check-runs at head; "Lint will pass" rests on local runs; upstream CI
   execution remains required.

Findings: P2 (handoff docs must wire b91b95440 + run the Phase-12 rehearsal
— resolved by this package: reports 06 + rehearsal, executed clean);
P2 (0 upstream check-runs — stated in 01/04/06/08); P3 ×3 (RENAME_MAP line
drift; PR#1 comments provenance; system pytest needs env-omni-rocm +
PYTHONPATH — documented).

---

## Aggregate

Zero unresolved P0/P1 across all four reviews. Gate
`THREE_INDEPENDENT_REVIEWS_PASS` met.
