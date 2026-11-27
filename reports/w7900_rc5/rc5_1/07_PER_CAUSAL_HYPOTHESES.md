# RC5.1 P1.1 — PER Causal Hypotheses (pre-registered subset, frozen before controls)

Frozen diagnostic subset: `07_DIAGNOSTIC_SUBSET.json` — 16 candidates from the
NEW 384: 4 historically-deterministic empty-transcript, 3 token-cap, 4 normal
en, 4 normal zh, 1 additional high-PER empty (all selections made BEFORE any
control cell ran; audio bytes SHA256-bound per receipt).

## What each hypothesis predicted vs what happened

| Hypothesis | Prediction if true | Observed | Verdict |
|---|---|---|---|
| H1 audio unintelligible | Whisper + vLLM also fail | Whisper hears lyrics (RC5 pilot, 0.09–0.33 ref PER); vLLM transcribes | EXCLUDED_WITHIN_SCOPE |
| H2 bf16 rounding | fp32/fp16 fix the empties | same 5 empties in fp32 (0.5336), fp16 (0.5299) | EXCLUDED_WITHIN_SCOPE |
| H3 SDPA kernel bug | eager differs | eager BIT-IDENTICAL to baseline | EXCLUDED_WITHIN_SCOPE |
| H4 batch padding | batch1 fixes empties | batch1 keeps all 5 empties | EXCLUDED_WITHIN_SCOPE |
| H5 device numerics | CPU fp32 fixes | CPU fp32 keeps 4/4 | EXCLUDED_WITHIN_SCOPE |
| H6 engine path | vLLM differs on same audio/GPU/weights | CONFIRMED: 0.5796 → 0.2304, 3/4 historical empties transcribe | CONFIRMED |
| H7 weights | any engine fails | only 2/384 persist under vLLM | EXCLUDED_WITHIN_SCOPE |
| H8 scorer | PER arithmetic differs | official scorer everywhere; S/D/I verified | EXCLUDED_WITHIN_SCOPE |
| H9 audio corruption vs history | new audio differs | 380/384 byte-identical | EXCLUDED_WITHIN_SCOPE |
| H10 exact kernel arithmetic | (mechanistic detail) | knife-edge characterised (step-8 near-ties), trigger not traced | OPEN |
| H11 CUDA official parity | needs CUDA | no host | BLOCKED_EXTERNAL |

## Key numeric evidence

- Empty-transcript anatomy (all 10 in the full 384): `text='language
  None<asr_text>'`, 318–528 generated tokens, finish=stop (2 candidates hit
  the 4096 cap) — a **repetition-loop degenerate output**, not an early stop.
- First-divergence probe: features bit-identical across all configs; decode
  tokens identical for 12 steps except step-8 near-tie flips (same top-5,
  EOS prob ~2e-5) — the model sits on a knife-edge after the language header.
- E2 vLLM on the 16-id subset: micro 0.2304 vs E1 0.5796; normal songs
  0.016–0.05 (official-reference territory).
