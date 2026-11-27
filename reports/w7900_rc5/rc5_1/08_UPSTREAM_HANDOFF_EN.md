# RC5.1 — Upstream / Author Hand-off (English)

## 1. What this repository delivers

A complete, bit-reproducible WildSongBench run of the latest YuE2 SGLang stack
(PR sgl-project/sglang#42106, commit `c67d541a`) on a single **AMD Radeon PRO
W7900D 48 GB (gfx1100)**, ROCm 7.14.1 / torch 2.12, with the official
five-metric evaluation and a closed PER root-cause analysis.

- Generation: **384/384** candidates, 0 failures, official protocol untouched
  (cot=full, ode_steps=32, seed from the official manifest); **380/384 are
  byte-identical** to the previous Arm B run of the older stack (the 4
  differences are FLAC-encoder-build-only: identical codec frames, duration,
  truncation).
- Metrics (selected-192, official evaluator verbatim):

| Metric | Paper | Author SGLang | Historical W7900 | RC5.1 W7900 |
|---|---|---|---|---|
| SongBench GA | 6.7316 | 6.7146 | 6.738264 | **6.736891** |
| PER (micro) | 8.44% | 8.1471% | 17.762763% | **17.7699%** (frozen) / **8.4488%** (corrected arm) |
| MuLan | 0.5068 | 0.49960 | 0.509166 | **0.509395** |
| AllMusicCaps | 0.4054 | 0.40825 | 0.405556 | **0.405181** |
| Q3O (0–5) | 4.68 | — | — | **4.393986** (ROCm-adapted judge, see §3) |

## 2. The PER root cause (verified, same audio bytes, same weights)

The historical ~9.3 pp W7900 PER gap is **not** the audio, the weights, the
scoring or the generation runtime. It is the **ASR engine substitution**: the
qwen_asr *transformers* backend (used because vLLM 0.14.0 has no ROCm build)
falls into a degenerate repetition loop on ~10/384 candidates (literal output
`language None<asr_text>` followed by hundreds of skipped tokens; 2 more hit
the 4096-token cap), invariant to dtype (bf16/fp16/fp32), attention (sdpa/
eager), batch size and device (GPU/CPU; features are bit-identical). The same
checkpoint through **vLLM on the same GPU transcribes those candidates
normally**, and re-scoring all 384 through the vLLM path yields a selected
micro PER of **8.4488% vs the paper's 8.44%** without any tuning (vLLM 0.19.1,
disclosed version difference). Two candidates loop under both engines
(genuine model behaviour on that audio).

Suggested upstream item (single, minimal, with repro): **qwen_asr transformers
backend enters a whitespace repetition loop on greedy decoding where the same
checkpoint under vLLM transcribes normally** — minimal repro: the SHA-bound
audio + both engines' outputs + the first-divergence probe log showing the
post-header knife-edge (identical top-5, EOS probability ~2e-5). We did not
file it yet: the audio is benchmark-restricted, so the public issue would
carry hashes/numeric receipts only unless the maintainers provide a private
channel.

## 3. Q3O on 48 GB (ROCm-adapted, equivalence NOT claimed)

Thinker-only BF16 with 34 GPU / 14 CPU-resident MoE layers (fp32 CPU blocks
with the official bf16 rounding points; **18.4%/20.2% of routed slots sit on
exact top-k boundary ties** — quantified), deterministic stable tie-break,
5-run/2-process token-identical repeatability, 192/192 coverage at 87 s per
candidate, peak VRAM 42.4 GiB, host headroom 4.3–5.2 GiB. The official engine
is vLLM 0.14 + FlashAttention 2.8.3 on CUDA; no equivalence is claimed
(no CUDA host). Score 4.394 vs the paper 4.68 (README-verified reference).

Engineering notes worth upstream attention (all root-caused on hardware):
- the 48 GB card cannot hold the batched-GPU-MoE packing next to the live
  weights (allocator fragmentation grows ~0.19 GiB/layer) — the validated
  path patches the stock HF loop's top-k in place;
- llvmlite's optimizer segfaults (rc=139) when numba compiles after the HIP
  stack is loaded — warm up librosa/madmom torch-free first;
- vLLM 0.19.1's ROCm platform probe swallows its own success when the amdsmi
  shim raises on `amdsmi_shut_down`.

## 4. Reproduction (author-verified commands)

See `docs/QUICKSTART_W7900.md` and `docs/BENCHMARK_REPRODUCTION.md`. All
numeric evidence is under `reports/w7900_rc5/rc5_1/` (hashes and numbers
only; no benchmark text or audio is published).

## 5. What we ask the author / community

1. Confirmation of the PER interpretation (§2) against the official CUDA
   run if feasible — a prepared hand-off package with the 384 audio hashes,
   evaluator runbook and comparison script is ready (local; private transfer
   needs an authorised channel).
2. Whether the Q3O tie-break rule of the official vLLM kernel is documented
   (it decides ~20% of routed slots).
3. Optional: best-of-2 selection changed on 120 candidates between the
   transformers and vLLM arms — the corrected-selection manifest is provided
   if a re-scored scoreboard is desired.
