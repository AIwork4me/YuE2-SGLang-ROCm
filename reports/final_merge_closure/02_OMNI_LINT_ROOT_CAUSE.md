# 02 — Omni leading-underscore lint root cause

Authoritative reproduction at base `ae11c6ad`:
`python scripts/check_leading_underscore.py` → exit 1,
**172 violations / 62 unique symbols / 12 files**, all in
`sglang_omni/models/yue2/` (fastpath 60, cuda_graph 35, nar_fast 19,
modeling_yue2 18, batched 10, nar 8, modeling_vae 8, tokenization 4,
sampling 4, song 3, fa3 2, streaming 1). 34 definitions + 138
attribute/getattr-string accesses.

Root cause: the author's YuE2 package was ported with PEP-8 private-name
style; the omni no-leading-underscore policy (#2267/#2338/#2365) predates
PR #2540, so every module-scope def and attribute access violates it.

Why the checker's `--fix` was NOT used (verified traps):
1. `GraphAR._capture` → `self.capture` bool attribute would shadow a
   `capture` method (`TypeError: 'bool' object is not called`).
2. `_causal_mask` → local variable `causal_mask` in `forward` creates
   `UnboundLocalError`.
3. `_offload_ar` → bool parameter `offload_ar` shadows the module function.
4. Cross-module edges (`_load_topk_backend`, `_decode_loop`, `_apply_rotary`,
   `_shift_t_value`, `sampler._k`) are renamed per-file by `--fix`, leaving
   importers broken at request time.
5. `monkeypatch.setattr(song, "_generate_song_tokens_*", ...)` string
   references in the platform-gate tests.
6. `getattr(model, "_yue2_fp8_originals", ...)` is an external contract:
   upstream YuE `src/yue2/quantization.py:83` sets that exact attribute via
   `object.__setattr__`; renaming the probe silently disables FP8 detection.

Closure arithmetic: 165 violations resolved by rename + 7 by 6 narrowly
scoped `# noqa: leading-underscore` lines (transformers `_init_weights` hook
— repo precedent in the checker's ALLOWED_DEFS for two other models;
`torch.ops.aten._flash_attention_forward`/`._schema` ATen op names;
`_yue2_fp8_originals` ×3 external marker) = 172.

Machine-readable inventory with every definition owner, reference context,
and cross-file edge: `LEADING_UNDERSCORE_INVENTORY.json`.
