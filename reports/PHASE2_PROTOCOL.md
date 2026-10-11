# PHASE 2 — Source and Benchmark Integrity

**Status: PASS (with documented upstream discrepancies, none protocol-affecting)**
**Date: 2026-10-11**

## 1. Source control

- SGLang PR #42106 (`add_yue2`) checked out at head
  **`ced0ef7d1bbbe703607b302ec86bb20a5c06bc8f`** — exactly the mission's pinned
  initial head. Shallow single-commit fetch (GitHub throttling from this
  network makes full clones fail; documented in Phase 0). PR commits:
  `6bd2ad33` (add YuE 2 support) → `8367a579` (e2e test) → `ced0ef7d`
  (concurrency test). Base `ba683062…` fetched for diffing when the network
  permits (background retry; the PR file list is already known from the tree).
- PR body + all 3 comments archived (`logs/pr42106_body.md`,
  `logs/pr42106_comments.md`). The YuE2 author (a43992899, Oct 4) validated
  the AR→NAR→VAE path with DeepSelect+fused-NAR active; reference numbers in
  PHASE8 table.
- **The authors' validated commit `e0683229…` is NOT among the PR's 3 commits.**
  It is either a force-pushed-away former head or a YuE-repo commit; the
  `multimodal-art-projection/YuE` fetch at that revision is in progress and
  the resolution will be recorded in this report when it lands.
- Official YuE repo reference (for examples/ABC + native comparison):
  shallow fetch at `e0683229…` (in progress; network-limited).

## 2. WildSongBench dataset integrity

Downloaded the full dataset repository (485 MB) at pinned revision
**`e361b85a8d7365d3079fa9647641a87ce3c8c5b5`** via hf-mirror.com
(huggingface.co unreachable — Phase 0). Verified against the dataset's own
`SHA256SUMS`:

- **13/14 files verify exactly**, including every protocol-bearing file:
  `prompts.jsonl`, `benchmark/reproduction_manifest.jsonl`, `code/generate.py`,
  `code/install_inference.py`, `evaluation/wsb_metrics.tar.gz`, and all
  benchmark result records.
- **README.md mismatch**: SHA256SUMS expects `2fb2a42c…`, the file served at
  the pinned revision (and matching our local copy byte-for-byte) hashes
  `f9595f29…`. This is an upstream dataset-card bookkeeping discrepancy;
  documentation only, zero protocol impact.

Manifest structure verified programmatically:

| Check | Result |
|---|---|
| manifest rows | 192 |
| prompt_index | 0–191, unique, contiguous |
| `candidate_ar_seeds[:2] == [831001+i, 831019+i]` | ✓ all 192 rows (8 seeds/row present for optional best-of-8; first two are the benchmark candidates) |
| candidate_nar_seeds | identical values to ar seeds ✓ |
| candidates | 2 → expected total **384** |
| languages | README: 94 zh / 98 en (our naive CJK-lyrics scan counts 95; classification nuance, no protocol impact) |

`benchmark/reproduction_manifest.jsonl` sha256:
`859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0`.
Additional file hashes: `evidence/dataset_manifest.sha256`.

## 3. Frozen official protocol (from README + code/generate.py + wsb_metrics/data/generation_protocol.json)

- Model: **m-a-p/YuE2-3B @ `1a96eca6`** (weights sha `1d55c42c…`,
  verified locally, byte-identical)
- Decoder: **m-a-p/YuE2-Vae-legacy @ `b54118f`** (sha `b6d28362…`, verified) —
  the benchmark-compatible legacy decoder, *not* substituted.
- Generation: `cot=full`, `cfg_scale=1.0`, `ode_steps=32` (midpoint),
  `semantic_max_tokens=9000`, `abc_max_tokens=4096`, `vae_core_frames=1024`,
  `vae_halo_frames=16`, context 24576.
- AR sampling (abc): T=0.7, top_p=0.9, top_k=30, rep=1.005/100w, min 32.
- AR sampling (semantic): T=1.0, top_p=0.95, top_k=100, rep=1.2/50w, min 200.
- NAR: bf16 solver, fp32 CPU noise `[frames,64]` from
  `Generator(cpu).manual_seed(actual_seed)`, full-song draw then slice.
- Decode: fp32, 48 kHz stereo, clamp [-1,1], FLAC PCM_24; evaluator scores
  MP3 192k (libmp3lame) derived from the FLAC.
- Selection: PER (Qwen3-ASR-1.7B @ `7278e1e7…`, 4 repeats) → min PER, then
  min edits, then min |phoneme-count diff|, then min candidate_index. Same
  selection reused for every metric. No filtering of truncated/high-PER rows.
- Candidate artifact bundle (evaluator input schema, from
  `wsb_metrics/artifact_storage.py` + official `yue2-infer 0.1.3` wheel):
  `result.json` + `audio.flac`, `prefix.npy`, `semantic.npy`, `latent.npy`,
  `request.json`, `config.json`, with `request_identity =
  sha256({request, effective_config, weights})`.

All of the above is machine-locked in `evidence/protocol_lock.json`.

## 4. Source-of-truth disagreements (documented, per mission §2)

1. `generation_protocol.json` cites `a43992899/YuE2-3B @ 321eed2a` /
   `a43992899/YuE2-Vae-legacy @ f1c0dad4`; `code/generate.py` pins
   `m-a-p/* @ 1a96eca6 / b54118f`. Weight sha256 identical → mirrored repos;
   we pin the `m-a-p` revisions (the ones `code/generate.py` asserts).
2. Wheel sha in `generation_protocol.json` (`15e0f6cb…`) ≠
   `install_inference.py` assertion (`156d6b8b…`). Our wheel matches the
   latter; recorded.
3. PR prose (sgl-kernel 0.4.7) vs pyproject at head (sglang-kernel 0.4.9) —
   neither installs on ROCm.
4. README README-sha stale (above).

## 5. Machine-specific paths in the PR recipe (removed for our reproduction)

`/raid/yiakwy` (model), `/home/yiakwy` (examples), `/tmp/opencode`
(scratch + wsb_runtime.json), `CUDA_VISIBLE_DEVICES=5` (fixed device index) —
all replaced with configurable paths and runtime device discovery; see
`scripts/` (Phase 5/6 drivers).

## 6. SGLang YuE2 implementation audit (feeding Phase 3)

Read in full: `modeling_yue2.py` structure, `song.py`, `sampling.py`,
`fastpath.py`, `cuda_graph.py`, `fa3.py`, `nar.py`, `nar_fast.py` (lazy
sgl_kernel), `streaming.py`, `storage.py`, `protocol.py`, pipeline stages
(`ar.py`, `nar.py`, `artifacts.py`, `vae.py`, `request.py`),
`yue2_loader.py`, `yue2_pipeline.py`, HTTP entrypoints, and the PR's own
opt-in E2E test (`test_server_yue2.py`). Sampling parameters and seed
semantics in SGLang's `protocol.py`/stages match the frozen WSB protocol
exactly (verified value-by-value). ROCm-relevant conclusions recorded in
PHASE3 (next).

## 7. Deliverables

- `evidence/protocol_lock.json` — frozen protocol + integrity results
- `evidence/model_manifest.json` — pinned model/source identities
- `evidence/dataset_manifest.sha256` — auxiliary file hashes
- `reviews/PHASE2_REVIEW.md` (independent subagent)

## 8. Gate

**PASS** — dataset integrity verified (13/14 exact, 1 documented
dataset-card discrepancy), 192×2 seed formula confirmed on all rows, models
hash-verified against official pins, protocol frozen.
