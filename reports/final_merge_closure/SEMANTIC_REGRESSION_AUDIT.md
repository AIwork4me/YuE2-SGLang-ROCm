# Semantic regression audit — identifier-only closure (Phase 7)

Base: `ae11c6ad` → working tree `fix/yue2-omni-leading-underscore-closure`.

## Method

1. AST equality proof: for each of the 12 touched yue2 sources, the base
   source at `ae11c6ad` was transformed by exactly the audited identifier map
   (word-boundary regex, the same map applied to the working tree), both
   versions parsed, and `ast.dump(...)` compared. `ast.dump` includes every
   operator, constant, string literal, keyword argument, default value,
   decorator, and base class, so equality proves the computation graph is
   unchanged.
2. Line-level diff audit: every non-rename changed line was inspected
   (8 residual lines, all the rename itself or noqa predecessors).
3. Repo-wide straggler sweep: every old symbol grepped across sglang_omni/,
   tests/, examples/ — zero remaining references (all apparent hits are
   substring collisions with unrelated pre-existing identifiers such as
   `_sample_next_token_ids` in model_runner/base.py, or new-name substrings).
4. Import-graph execution: all 22 yue2 submodules imported in the ROCm env
   against the PYTHONPATH-shadowed worktree; `examples/run_yue2_generate.py`
   compiles.

## Results

| File | AST verdict |
|---|---|
| batched.py, cuda_graph.py, fa3.py, fastpath.py, modeling_vae.py, modeling_yue2.py, nar.py, nar_fast.py, sampling.py, streaming.py, tokenization_yue2.py | EQUAL (modulo identifier map) |
| song.py | EQUAL except one from-import member reorder (`load_topk_backend` sorted after `fast_sampler_available` per isort) — same symbol set, no runtime effect |
| tests/.../test_yue2_platform_gates.py | exactly 2 changed lines: the monkeypatch.setattr strings for the two renamed song generators |
| MIGRATION.md | 1 doc line (`_TorchTopKBackend` → `TorchTopKBackend`) |
| tests/.../test_yue2_rename_regression.py | NEW file (14 tests) |

Auto-format residue: the first pre-commit run re-wrapped 13 lines (black) —
3 long noqa lines were split across lines; the checker's
`statement_has_noqa` still covers them (leading-underscore hook Passed on the
clean re-run); the rest are rewraps of renamed-identifier lines.

## Explicit no-change confirmations

- Attention equations: every `sdpa`, `F.scaled_dot_product_attention`,
  `varlen_attention`, and ATen `_flash_attention_forward` call is inside an
  EQUAL file (AST-identical modulo identifiers).
- Tensor shape transforms: unchanged (AST equality).
- Sampling: `window_penalty`, `distribution`, softmax/topk/multinomial order,
  generator seeding (`manual_seed`) — unchanged; sampler buffers renamed only
  as instance attributes, no math touched.
- TopK/TopP behavior: fastpath graphs/samplers — AST-equal modulo attr names.
- Random seed handling: unchanged.
- AR cache update: StaticKVCache.update/get_seq_length logic unchanged
  (`_seen_tokens` → `seen_tokens` is a plain attribute).
- NAR computations: nar.py/nar_fast.py AST-equal; `model.shift_t_value`
  rename applied at all 4 call sites (modeling_yue2 def + nar + nar_fast×3).
- VAE decode equations: modeling_vae.py AST-equal.
- CUDA Graph capture/replay conditions: `GraphAR.capture_graph` (was
  `_capture`), warmup/capture/replay flow AST-equal; the `self.capture` bool
  semantics untouched (name kept, method renamed to avoid shadowing).
- ROCm fallback gates: `is_rocm()` conjuncts and stage gates AST-equal;
  12 platform-gate tests pass unchanged (they execute both platform
  branches of fa3/fastpath/song/stages dispatch).
- state_dict: no renamed attribute is a parameter/buffer/submodule (verified:
  single `register_buffer("pe", ...)` in the package is untouched;
  `RotaryEmbedding().state_dict() == {}` regression test).
- Config serialization: `YuE2Config`/`YuE2VAEConfig` `to_dict()` regression
  tests pass; renamed `hf_fields`/`inference_fields` are class frozensets and
  never appear in serialized output (old or new names).
- External contracts: `_yue2_fp8_originals` probes byte-identical (noqa'd);
  `torch.ops.aten._flash_attention_forward` / `._schema` untouched;
  transformers `_init_weights` hook untouched.
- API request/response contracts: no request key, JSON field, timing-dict
  string, env var, or registered model name changed (AST equality + string
  sweep).

## Identifier changes vs semantic changes

SEPARATION COMPLETE: 100% of the source delta is identifier renames (165
violations), 6 noqa comment additions (7 violations), 1 import-member
reorder, 2 test setattr strings, 1 doc line. SEMANTIC CHANGES: NONE.
