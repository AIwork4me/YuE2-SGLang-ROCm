# 03 — Omni rename map (33 definitions + 25 attribute names = 58 symbols)

Rule: strip the leading underscore; where the stripped name collides or
misleads, nearest unambiguous public name. Exceptions keep the old name with
`# noqa: leading-underscore` + inline reason (6 lines / 7 findings):
`_init_weights` (transformers PreTrainedModel init hook, called by
transformers `modeling_utils.init_weights`), ATen
`_flash_attention_forward` + `._schema` (cuda_graph, fa3), and
`_yue2_fp8_originals` probes ×3 (set by YuE `quantization.py`).

## Definition renames

| Old → New | Scope | Deviation reason |
|---|---|---|
| fastpath `_TorchTopKBackend` → `TorchTopKBackend` | same file | mechanical |
| fastpath `_load_topk_backend` → `load_topk_backend` | + song.py import/call | mechanical |
| FastSampler `_phase_mask` → `phase_mask` | same file | mechanical |
| BatchedGraphSampler `_fill_scalars` → `fill_scalars` | same file | mechanical |
| fastpath `_window_penalty_` → `window_penalty_inplace` | same file | distinct from sampling.window_penalty |
| cuda_graph `_fused_enabled` → `fused_enabled` | same file | mechanical |
| cuda_graph `_PrefixCache` → `PrefixCache` | same file | mechanical |
| GraphAR `_decode` → `decode` | same file | mechanical |
| GraphAR `_decode_fused` → `decode_fused` | same file | mechanical |
| GraphAR `_step_once` → `step_once` | same file | mechanical |
| GraphAR `_capture` → `capture_graph` | same file | COLLISION: self.capture bool |
| fa3 `_load_varlen` → `load_varlen` | same file | mechanical |
| modeling_yue2 `_causal_mask` → `build_causal_mask` | same file | COLLISION: local causal_mask |
| modeling_yue2 `_apply_rotary` → `apply_rotary` | + cuda_graph import/calls | mechanical |
| YuE2ForCausalLM `_shift_t_value` → `shift_t_value` | + nar, nar_fast ×3 calls | mechanical |
| nar `_integers` → `coerce_integers` | same file | clarity |
| CachedNAR `_attention` → `attention` | same file | mechanical (self-attr vs module fn distinct) |
| CachedNAR `_prefill` → `prefill` | same file | mechanical |
| nar `_offload_ar` → `offload_ar_modules` | same file | COLLISION: bool param offload_ar |
| nar_fast `_sgl_kernel` → `load_sgl_kernel` | same file | consistent lazy-loader naming |
| nar_fast `_flash_varlen` → `flash_varlen` | same file | mechanical |
| nar_fast `_VelocityGraph` → `VelocityGraph` | same file | mechanical |
| _VelocityGraph `_velocity_impl` → `velocity_impl` | same file | mechanical |
| sampling `_sample_next` → `sample_next` | same file | mechanical |
| sampling `_decode_loop` → `decode_loop` | + song.py import/calls | mechanical |
| song `_StepGraphUnavailable` → `StepGraphUnavailable` | same file | mechanical |
| song `_generate_song_tokens_step_graph` → `generate_song_tokens_step_graph` | + test setattr string | mechanical |
| song `_generate_song_tokens_looped` → `generate_song_tokens_looped` | + test setattr string | mechanical |
| batched `_abc_per_request` → `abc_per_request` | same file | mechanical |
| modeling_vae `_dependency_interval` → `dependency_interval` | same file | mechanical |
| modeling_vae `_output_length` → `output_length` | same file | mechanical |
| YuE2VAE `_latent` → `validate_latent` | same file | clarity (self.latent(latent) tautology) |
| streaming `_windows` → `windows` | same file | mechanical |

## Attribute renames

FastSampler `_masks→masks`, `_ends→ends`; GraphSampler and
BatchedGraphSampler `_ages→ages`, `_window_weights→window_weights`,
`_topk_ranks→topk_ranks`, `_freq→freq`, `_k→k` (external read in
batched.py updated), `_ones_w→ones_w`, `_end_only→end_only`, `_mixed→mixed`,
`_rows→rows`; GraphAR `_fused_layer_weights→fused_layer_weights`; model
cache attrs `_yue2_fused_weights→yue2_fused_weights` (cuda_graph set+get),
`_yue2_fused_nar_weights→yue2_fused_nar_weights` (nar_fast set+get);
GraphSessionPool `_idle→idle`, `_live→live`, `_lock→lock`;
VelocityGraphPool `_graphs→graphs`, `_lock→lock`; BatchedSessionLease
`_refs→refs`, `_released→released`, `_lock→lock`; RotaryEmbedding
`_inv_freq→inv_freq` (plain attr — NOT a buffer; state_dict unchanged);
StaticKVCache `_seen_tokens→seen_tokens`; YuE2TextTokenizer `_enc→enc`;
YuE2Config and YuE2VAEConfig `_hf_fields→hf_fields`,
`_inference_fields→inference_fields` (class-level frozensets incl. the 4
unflagged assignment sites; to_dict() output unchanged — tested).

## Not renamed

Module-level variable names (`_IN_TREE`, `_PIP`, `_TORCH`, `_VARLEN`,
`_LOADED`, `_SGL_KERNEL`, `_logger`) — plain bindings, not checked by policy
and not API. torch op names, `_init_weights`, `_yue2_fp8_originals`,
all API/JSON/env/checkpoint/registered-model strings.
