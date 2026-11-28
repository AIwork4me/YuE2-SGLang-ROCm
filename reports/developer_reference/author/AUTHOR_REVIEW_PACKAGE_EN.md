# YuE2 on ROCm — Joint Reproduction Review (RC6 author package)

**From:** AIwork4me (repo owner) — engineering executed on a W7900D rig.
**To:** the YuE2 authors / WildSongBench evaluators (and AMD reviewers, via
the AMD package). **Status: READY_FOR_REVIEW — not submitted** (submission
needs owner authorization; no un-authorized external contact has been made).
**Everything below is executable/verifiable from this repository.**

## 1. One-page executive summary

We reproduced the complete WildSongBench protocol with the official YuE2
weights on a single **AMD Radeon PRO W7900D 48 GB (gfx1100, ROCm 7.14.1,
torch 2.12.0+rocm7.14.1)** using your SGLang integration head (`c67d541a`,
PR sgl-project/sglang#42106, unmerged snapshot) with only three import-guard
patches. **384/384 candidates, 0 failures, official protocol untouched;
380/384 byte-identical** to the earlier run of the previous stack (the 4
differences are FLAC-encoder-build-only). The official five-metric evaluation
was executed; four metrics match the paper closely, and the PER gap was
root-caused to our **disclosed ASR engine substitution** (not your model,
audio, scoring or generation): re-scoring the same 384 audios through the
vLLM decode path gives **selected micro PER 8.4488% vs the paper 8.44%**.
Q3O runs on the 48 GB card via a disclosed ROCm-adapted judge (no CUDA host
available for the official-engine comparison). What we need from you is
listed in §8 — mainly confirmations, not engineering.

## 2. Exact identities

| Item | Value |
|---|---|
| Model | `m-a-p/YuE2-3B@1a96eca6` (content-hashed in every bundle) |
| VAE | `m-a-p/YuE2-Vae-legacy@b54118f` |
| Dataset | `m-a-p/WildSongBench@e361b85a` |
| SGLang | PR #42106 head `c67d541a40f8bf851e9fc1e925f5316638838cd6` (frozen PR head, not the merge ref) |
| ROCm stack | userspace 7.14.1 (venv-local), host kernel amdgpu; GPU gfx1100 BDF 0000:03:00.0 uuid e9d0e20b-… |
| Patches | `patches/rc5-0001-0003-0008-rocm-import-guards.patch` ONLY (import guards for aiter/sgl_kernel/kvcacheio; 0004/0005 were absorbed upstream) |
| Effective runtime SHA256 | `342b2f531b14a201b4aae1a6a14424bed7f03cd7f993c3a1c09657a6d6109051` (unchanged across the whole campaign) |

## 3. Results (selected-192, official evaluator)

| Metric | Paper | Author SGLang | This W7900 reproduction |
|---|---|---|---|
| SongBench GA | 6.7316 | 6.14→6.7146 | 6.736891 |
| PER micro (frozen arm, transformers ASR) | 8.44% | 8.1471% | 17.7699% — **engine substitution effect, see §4** |
| PER micro (corrected arm, vLLM 0.19.1 decode) | — | — | **8.4488%** (reported as a SEPARATE arm) |
| MuLan | 0.5068 | 0.49960 | 0.509395 |
| AllMusicCaps | 0.4054 | 0.40825 | 0.405181 |
| Q3O 0–5 | 4.68 | not published | 4.393986 — ROCm-adapted judge, official equivalence NOT_ESTABLISHED |

## 4. Why PER differed (same-audio evidence, no tuning)

Same 384 audio bytes, same Qwen3-ASR-1.7B weights, same official scorer:

- The frozen arm's engine (qwen_asr **transformers** backend — vLLM 0.14.0
  has no ROCm build) enters a degenerate repetition loop on hard candidates
  (10 empty + 112 cap-affected of 384); invariant to precision/attention/
  batch/device; input features bit-identical; first-divergence shows
  knife-edge logits after the language header (identical top-5, EOS ~2e-5).
- The same weights through **vLLM** on the same GPU transcribe normally;
  re-scoring all 384 yields 8.4488% vs 8.44% paper (Δ 0.009 pp, zero tuning).
- RC6 added the full 2×2 attribution on identical audio:
  T(S_T)=17.77% → V(S_T)=9.59% (evaluator-path effect, fixed selection) →
  V(S_V)=8.45% (selection effect −1.14 pp); T(S_V)=20.20%.
- 2/384 candidates loop under BOTH engines (genuine model behaviour).

## 5. What was verified for Q3O

Official prompt/parser/scorer/weights verbatim (sha-bound); Thinker-only
BF16; 34 GPU + 14 CPU MoE layers; deterministic stable top-k tie-break;
5-run/2-process token-identical; 192/192 valid; peak VRAM 42.4 GiB.
**Not claimed:** official-engine equivalence (HF-ROCm vs vLLM-CUDA
attention kernels; ~18–20% of routed slots sit on exact top-k boundary ties
whose official tie rule is unpublished). A same-audio CUDA comparator with
pre-registered criteria is ready (`CUDA_Q3O_RUNBOOK.md`).

## 6. Reproduction commands

Commands executed on our W7900 rig (NOT author-verified commands — this
package is the request for exactly that review):

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git && cd YuE2-SGLang-ROCm
python3 scripts/reference_cli.py doctor
python3 scripts/reference_cli.py install          # pinned stack, hash-gated
python3 scripts/reference_cli.py generate \
  --lyrics examples/first_song/lyrics_en.txt --style examples/first_song/style.txt \
  --seed 831001 --out-dir $WS/runs/my-first-song
python3 scripts/reference_cli.py benchmark --mode pilot   # 5x2, ~1 h
# full: bash scripts/campaign_ops/rc5_supervise.sh <run_dir> <run_id>  (RC5.1 protocol)
```

## 7. Known limitations (full list: docs/KNOWN_LIMITATIONS.md)

- SGLang YuE2 support is unmerged upstream; we pin a PR snapshot.
- PER official engine (vLLM 0.14.0) has no ROCm build → disclosed
  substitutions (frozen transformers arm; corrected vLLM 0.19.1 arm).
- Q3O official equivalence NOT_ESTABLISHED (no CUDA host).
- Single-GPU serial execution; DeepSelect/sgl_kernel fast paths are
  CUDA-only (author's native capability gates fall back to reference paths).

## 8. Requested author decisions (see AUTHOR_ACCEPTANCE_MATRIX.json)

A01–A12 matrix, each with status and the exact evidence to review. The four
decisions that matter most:

1. **A06/A07**: is our PER interpretation (transformers-substitution
   repetition loop; corrected vLLM arm as the fairer engine-family
   comparison) consistent with your understanding of the official evaluator?
2. **A10**: run the prepared same-audio CUDA PER/Q3O comparison (runbooks +
   hash-bound handoff package with all 384 audio hashes ready; 30–60 min of
   H100/A100 time), or confirm the equivalence criteria you want applied.
3. **A09**: confirm or correct the Q3O ROCm-adapted protocol's disclosure
   (tie-break rule, placement, rounding points).
4. **A04/A12**: any correction to our public statements about selection
   semantics and reproduction guidance.

No claims of author approval exist anywhere in this repository; every
author/AMD status field is READY_FOR_REVIEW or NOT_SUBMITTED.
