# RC5.1 P1.1 — PER Same-Audio Causal Root-Cause: Source-Level RCA

## Executive summary

The W7900 selected-192 micro PER of **17.77%** (reproducing the historical Arm B
17.76% almost exactly, +0.007 pp) versus the official reference **8.44%** is
**predominantly an ASR engine-path effect**, demonstrated on identical audio
bytes and identical model weights:

> On the pre-registered 16-candidate diagnostic subset, the frozen official
> ROCm path (transformers backend, the disclosed substitution) scores micro PER
> **0.5796** with 5 confirmed-empty candidates; **vLLM on the same GPU with the
> same Qwen3-ASR-1.7B weights scores 0.2304** and transcribes 3 of the 4
> historically-deterministic empty candidates at PER 0.03–0.13.

The remaining gap on normal candidates is small (normal songs score
0.016–0.05 under vLLM, in line with the official reference).

## The causal chain, stage by stage (all on identical audio bytes)

1. **Audio bytes**: identical (SHA256-verified per receipt; the same MP3s the
   official evaluator produced via `prepare_inputs`).
2. **Feature extraction**: BIT-IDENTICAL across every precision/device/attention
   config (probe `07_ASR_FIRST_DIVERGENCE.json`: `features` equal everywhere) —
   audio decoding, resampling and the mel feature extractor are NOT involved.
3. **Decode steps 1–3**: the language header tokens (11528, 2240, 151704 …) are
   chosen identically by every transformers-path config.
4. **The knife-edge**: right after the header, logits sit in near-ties —
   probe step 8 shows the SAME top-5 set with EOS probability ~2×10⁻⁵; bf16
   picks token 487 while fp32/CPU pick 151645 (EOS). Both branches are bad:
   the transformers path either **enters a whitespace/template-echo
   repetition loop** or **stops immediately** — either way the transcript
   decodes to the literal degenerate string below.
5. **The degenerate output** (all 10 empty candidates of the full 384 share
   this exact shape):
   `text = 'language None<asr_text>'`, `generated_tokens = 318–528`,
   `finish_reason = stop` (or 4096/`length` for the two capped-loop
   candidates): hundreds of tokens that `batch_decode(skip_special_tokens=True)`
   collapses to nothing. **"Empty transcript" ≠ "early stop"** — it is a
   repetition-loop failure mode.
6. **Engine dependence (the decisive cell)**: vLLM 0.19.1 (native
   `Qwen3ASRForConditionalGeneration`, greedy, same weights, same audio, same
   GPU) does **not** enter the loop for wsb_086_r0/086_r1/164_r1 — full
   transcripts, no cap. Two candidates (wsb_120_r1, wsb_085_r1) loop under
   BOTH engines → genuine model-behavior-on-audio.

## Hypotheses ledger

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | Audio not intelligible | **EXCLUDED_WITHIN_SCOPE** | Whisper (unrelated family) hears the lyrics at 0.09–0.33 reference PER (RC5 pilot); vLLM transcribes the same bytes |
| H2 | bf16 rounding triggers the failure | **EXCLUDED_WITHIN_SCOPE** | fp32 and fp16 arms reproduce the same 5 empties (E5 0.5336 / E7 0.5299) |
| H3 | SDPA attention kernels | **EXCLUDED_WITHIN_SCOPE** | eager arm is BIT-IDENTICAL to baseline (0.579557 = 0.579557) |
| H4 | batch padding/composition | **EXCLUDED_WITHIN_SCOPE** (for empties) | batch1 arm reproduces all 5 empties; note: batch size does change cap counts (32→8 truncated repeats) |
| H5 | GPU vs CPU device numerics | **EXCLUDED_WITHIN_SCOPE** | CPU-fp32 arm reproduces the same 4/4 empties on its subset |
| H6 | ASR engine implementation (transformers path vs vLLM) | **CONFIRMED** | E2: same weights+audio+GPU, 3/4 historical empties transcribe; subset PER 0.5796→0.2304; caps vanish |
| H7 | Model weights/version | **EXCLUDED_WITHIN_SCOPE** | identical checkpoint (content-hashed) in both engines; only 2/10 empties persist under vLLM |
| H8 | Scorer/phonemization | **EXCLUDED_WITHIN_SCOPE** | official `phoneme_result` used in every cell; S/D/I decomposition verified equal to official edits 192/192 |
| H9 | Generation-side audio corruption | **EXCLUDED_WITHIN_SCOPE** | 380/384 candidates byte-identical to historical Arm B; the 4 diffs are FLAC-container-only |
| H10 | Exact kernel/op whose numerics flip the loop entry | **OPEN** (bounded) | would require per-layer logit tracing inside two engine implementations; the knife-edge (step-8 near-ties, same top-5) is characterised, the triggering arithmetic is not |
| H11 | Official CUDA vLLM equivalence | **BLOCKED_EXTERNAL** | no CUDA host; E3 handoff package prepared |

## Root-cause verdict

`PER_ROOT_CAUSE_COMPOSITE`:

1. **Dominant, confirmed**: the ROCm transformers ASR substitution falls into
   a degenerate loop-or-stop attractor on ~10/384 hard candidates (and
   contributes to the 112 capped candidates), which the vLLM decode path —
   the family the OFFICIAL evaluator uses — escapes. This is a
   substitution-engine property, not a defect in this repository's code and
   not a property of the audio or weights.
2. **Minor, confirmed**: 2/384 candidates (wsb_085_r1, wsb_120_r1) loop under
   both engines — genuine model behaviour on that audio.
3. **OPEN**: the precise kernel-arithmetic difference that flips the
   knife-edge logits (H10).

## Corrected evaluator arm (P1.1.6 protocol)

The vLLM-native path (vLLM 0.19.1 ROCm, in-process, greedy, same official
prompt/chunking/scoring) is run as the corrected evaluator over the fixed 384
audios (`rc5_1_e2_full`), reported as a SEPARATE arm next to the frozen
original PER; if the best-of-2 selection changes, a corrected-selection arm
is opened (no metric mixing). Note: vLLM 0.19.1 ≠ official 0.14.0 — this arm
is closer to the official engine family, not equivalent to it.

## Reproduction commands

```
# E1–E8 matrix (frozen diagnostic subset):
python scripts/rc5_per_lab.py --evaluator-root <ws>/benchmark/wsb_metrics \
  --manifest rc5_1_matrix_manifest.jsonl --out rc5_1_matrix \
  --arm baseline --arm fp32:dtype=float32 --arm eager:attn=eager \
  --arm batch1:batch_size=1 --arm fp16:dtype=float16 \
  --arm cpu32:dtype=float32,device=cpu,repeats=1
# E2 (vLLM):
python scripts/rc5_asr_vllm_native.py --asr-root <Qwen3-ASR snapshot> \
  --manifest <audio_manifest> --out transcripts.jsonl --repeats 4
# first-divergence probe:
python scripts/rc5_asr_first_divergence.py --evaluator-root <ws>/benchmark/wsb_metrics \
  --manifest rc5_1_matrix_manifest.jsonl --out rc5_1_first_div --ids <empty ids> --steps 12
```
