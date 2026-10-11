# PHASE 2 Independent Review — Source + Benchmark Integrity

**Reviewer:** independent verification subagent (fresh shell, recomputed everything from artifacts)
**Date:** 2026-10-11
**Scope:** PHASE2_PROTOCOL.md claims, protocol_lock.json, dataset/model integrity, upstream checkout state
**Method:** all hashes recomputed locally with `sha256sum`; structure checks re-implemented independently in Python; source files read directly. Nothing except this review file was modified.

## Verdict

**PASS**

All 8 assigned verifications reproduce exactly. No protocol-affecting discrepancy found. Three P3 documentation/bookkeeping nits and one disclosed open item (see Issues).

## Verification evidence

### V1. Dataset SHA256SUMS — PASS

`sha256sum -c SHA256SUMS` in `benchmark/WildSongBench` (run 2026-10-11):

- **13 files OK**: benchmark-results.csv/.json, comparison_summary.csv, frontier-composites.json, frontier-teaser.pdf/.png/.svg, **reproduction_manifest.jsonl**, results.md, **code/generate.py**, **code/install_inference.py**, **evaluation/wsb_metrics.tar.gz**, **prompts.jsonl** — exit reports `WARNING: 1 computed checksum did NOT match` (exit 1) solely due to:
- **README.md: FAILED** — SHA256SUMS expects `2fb2a42c…`; recomputed local README.md sha256 = `f9595f297c88f5c5423d5b76748aa46c96db4a5dd3d0093f510f78f6e38f2fe4` → **matches the expected value exactly**. The file is self-consistent; the SHA256SUMS entry is stale upstream. README is dataset-card prose only (verified by inspection: badges, model links, language counts); zero protocol content. Classification "upstream dataset-card discrepancy" is accurate.

### V2. reproduction_manifest.jsonl — PASS

- Recomputed sha256 = `859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0` — **matches expected** (and the SHA256SUMS entry, and protocol_lock.json).
- Independent Python check: **192 rows**; `prompt_index` = exactly 0..191, unique, contiguous.
- `candidate_ar_seeds[:2] == [831001+i, 831019+i]` — **True for all 192 rows**.
- Stronger than required: all **8** seeds per row equal `base+i` for all 8 bases `{831001, 831019, 831037, 831061, 831083, 831109, 831127, 831149}` across **all 192 rows** (0 failures). Bonus: `candidate_ar_seeds == candidate_nar_seeds` on all rows; `prompts.jsonl` has 192 rows.

### V3. Model weights — PASS

Recomputed (background job, full read of both files):

- `models/YuE2-3B/model.safetensors` (7,261,441,640 bytes) = `1d55c42c1a9875c34f5d736e15078449992b044e807ce2a138e6cf289a1e59e9` — matches.
- `models/YuE2-Vae-legacy/model.safetensors` (530,512,720 bytes) = `b6d283628913bb41145ba99e2314eef613905ee95f690eb70e8212d5f4965044` — matches.

Also cross-checked `evidence/dataset_manifest.sha256`: all 7 entries (prompts.jsonl, generate.py, install_inference.py, wsb_metrics.tar.gz, qwen.tiktoken, both config.json) verify OK.

### V4. generate.py pins vs protocol_lock.json — PASS

`benchmark/WildSongBench/code/generate.py` lines 11-15 vs `protocol_lock.json` `models` section:

| Pin | generate.py | protocol_lock.json | Match |
|---|---|---|---|
| MODEL_REVISION | `1a96eca688d6ae5d7f0feb88573fec89920fcd19` | ar_model.revision `1a96eca6…` | ✓ |
| VAE_REVISION | `b54118f0fc462f08999d1ec07e88817f4ee3f770` | vae_decoder.revision `b54118f0…` | ✓ |
| MODEL_SHA | `1d55c42c…89a1e59e9` | ar_model.model.safetensors.sha256 | ✓ |
| VAE_SHA | `b6d28362…f4965044` | vae_decoder.model.safetensors.sha256 | ✓ |

generate.py also *asserts* these shas at runtime (lines 79-80), i.e. the pins are enforced, not decorative. protocol_lock.json's `verified_local: true` claims are backed by V3 above.

### V5. Seed bases list — PASS

`generate.py:46` `bases = [831001, 831019, 831037, 831061, 831083, 831109, 831127, 831149]` — exactly the 8 bases in WSB `generation_protocol.json` `base_seeds`. Verified `base+i` against the manifest on 5 sampled rows (0, 37, 96, 150, 191) — all correct (e.g. row 191 → `[831192, 831210, 831228, 831252, 831274, 831300, 831318, 831340]`) — and then on all 192 rows (V2). generate.py's own line-48 assert is consistent.

### V6. upstream/sglang checkout — PASS

- `git rev-parse HEAD` = `ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f` ("add concurrency test (5x req/sec)", detached HEAD) — **matches the pinned head** and `logs/pr42106_meta.json` (`head`, `head_ref: add_yue2`, base `ba683062…`, 3 commits, state open).
- `git status --porcelain` shows **exactly 3 modified files, nothing untracked/staged**:
  - `python/sglang/srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4.py`
  - `python/sglang/srt/layers/quantization/quark/schemes/quark_w4a4_mxfp4_moe.py`
  - `python/sglang/srt/layers/quantization/quark_int4fp8_moe.py`
- Read the full diff: all three changes are **aiter import guards** (wrap `aiter.ops…` imports in `try/except ImportError → None`, matching the non-HIP branch), commented as ROCm portability for gfx1151 where aiter (Instinct-CDNA-only) is absent. Registered ops raise at call time only if W4A4/quark schemes are requested — YuE2 is bf16 and never touches them. No behavioral change to the YuE2 path.
- Live `git diff` == `logs/working_tree.diff` == body of `patches/0001-0003-aiter-import-guards.patch` (byte-identical apart from patch header lines).

### V7. SGLang protocol.py defaults vs WSB generation_protocol.json — PASS

Read both files in full. `upstream/sglang/python/sglang/srt/models/yue2/protocol.py`:

| Parameter | protocol.py | generation_protocol.json | Match |
|---|---|---|---|
| abc | `Sampling(.7, .9, 30, 1.005, 100, 32, 4096)` (positional → T/top_p/top_k/rep/window/min/max) | historical_ar.abc: 0.7 / 0.9 / 30 / 1.005 / 100 / 32 / 4096 | ✓ |
| semantic | `Sampling()` defaults = 1.0 / 0.95 / 100 / 1.2 / 50 / 200 / 9000 | historical_ar.semantic: 1.0 / 0.95 / 100 / 1.2 / 50 / 200 / 9000 | ✓ |
| ODE | `ode_steps=32`, `ode_method="midpoint"` | nar.ode_method "midpoint", ode_steps 32 | ✓ |
| context | `CONTEXT = 24576` (line 13; enforced by `__post_init__`) | historical_ar.context_length 24576 | ✓ |

Bonus consistency: `chunk_ranges` implements `min((context - prefix_tokens - 3)//2, CONTEXT)` — identical to the protocol file's `nar.chunk_frames` formula; `generation.py:38` constructs `GenerationConfig()` with defaults (no override) and applies `config.abc` with `abc_max_tokens=4096`. The report's "match exactly (verified value-by-value)" claim is confirmed.

### V8. The four documented disagreements — PASS (all accurate)

1. **hf_models repos**: `generation_protocol.json` cites `a43992899/YuE2-3B @ 321eed2a686a01856150b9905cdcb1a90cbdadb5` and `a43992899/YuE2-Vae-legacy @ f1c0dad4e7dcef829bdfd5de78b56350e6385aff`, while `generate.py` pins `m-a-p/* @ 1a96eca6 / b54118f` — confirmed by direct read of both files. The protocol file's `sha256` fields (`1d55c42c…`, `b6d28362…`) are byte-identical to the m-a-p pins and to the locally verified weights (V3) → "mirrored repos, same weights" is correct.
2. **Wheel sha**: protocol `generation_wheel.sha256 = 15e0f6cb414484e205edb9da300aba9ce55ccb30fce6c0b093a5bd3ff9d50e3d` ≠ `install_inference.py:17` assertion `156d6b8b7e46c3bd23cf22a50d3c20c403e5dc7f4a315582a224a840b01f4f07`. Recomputed the local `models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl` = **`156d6b8b…`** → matches install_inference.py, as documented.
3. **Languages**: README/protocol say 94 zh / 98 en; my independent naive Han-character scan over manifest lyrics counts **95** Han-containing rows (reproduced). Lowest-fraction row idx=2 (96 Han vs 1,029 ASCII letters) is a plausible mixed-language row counted `en` by the evaluator. "One row classifies differently under naive CJK detection" is accurate.
4. **Kernel version**: `logs/pr42106_body.md:25` references "sgl kernels (0.4.7 …)"; `upstream/sglang/python/pyproject.toml:81` pins `sglang-kernel==0.4.9`. Confirmed. (The "neither installs on ROCm" half is an environment claim carried from Phase 0/1; not re-tested here, and it has no protocol impact.)

## Issues

- **P0:** none.
- **P1:** none.
- **P2:** none.
- **P3-1 — wrong byte count in model_manifest.json:** `models[0].files["model.safetensors"].bytes` records `7261388800`; the actual file is `7261441640` bytes (stat; Δ 52,840). The sha256 recorded there is correct and authoritative (reverified in V3), so identity is unaffected, but the bytes field is wrong bookkeeping and should be corrected or dropped.
- **P3-2 — ambiguous commit list in model_manifest.json:** `checkout_mode: "shallow fetch …; commits: 6bd2ad33, 8367a579, ced0ef7d"` reads as if all three commit objects are local. In fact the checkout is depth-1: `git rev-list --count HEAD` = 1 and `6bd2ad33` / `8367a579` / base `ba683062` are not present locally. The PHASE2 report §1 states this honestly ("Shallow single-commit fetch"); suggest rewording the manifest to "PR commit list (from metadata); only HEAD fetched".
- **P3-3 — disclosed open item, authors' validated commit:** `e0683229e755d60af70ad52af036e6386a8d60d1` is not in the PR's 3-commit list and remains unidentified (report §1; fetch of `multimodal-art-projection/YuE` pending). Transparently disclosed and deferred; does not affect Phase 2 integrity (the mission pins PR head `ced0ef7d`, which is what is checked out), but it should be resolved before any "author-validated configuration" provenance claim is made in later phases.

## Notes (non-issues)

- README.md SHA256SUMS mismatch is upstream staleness, correctly triaged; all 13 protocol-bearing files verify.
- `prompts.jsonl` rows carry only a `prompt` field; lyrics/style live in the manifest — both hash-verified.
- Selection/ASR/decode parameters in protocol_lock.json (Qwen3-ASR @ `7278e1e7…` 4 repeats, FLAC PCM_24 → MP3 192k, selection key order) match `generation_protocol.json` verbatim on read-through.

## Bottom line

**PASS.** Every claim in PHASE2_PROTOCOL.md that falls in this phase's scope reproduces from the artifacts: dataset 13/14 exact with the one mismatch being upstream README staleness (local file matches the official raw hash), manifest structure and seed algebra exact on all 192 rows, model weights bit-identical to the official pins, SGLang checkout at the pinned head with only the three declared aiter guards, and the SGLang/WSB sampling-parameter equivalence confirmed value-by-value from source. The three P3s are documentation/metadata polish, none affecting the frozen protocol.
