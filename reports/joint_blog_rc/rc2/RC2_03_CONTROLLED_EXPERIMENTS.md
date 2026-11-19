# RC2_03b — Controlled experiments register (PER investigation)

Every experiment pre-registered before execution; results tagged with the
RC2 evidence-class rules (PASS/FAIL/BLOCKED/NOT_TESTED).

| # | Experiment | Method | Denominator | Result | Artifact |
|---|---|---|---|---|---|
| E1 | Selection-rule recomputation | independent min-per selection from per_song.jsonl | 192 prompts / 384 candidates | **reproduces official aggregates exactly** (0.168292) | 03_PER_CAUSAL_ANALYSIS.md §2 |
| E2 | Capping exclusion | drop ASR-capped candidates | Arm A 156, gfx1151 148 uncapped | uncapped PER 16.15 % vs 16.14 % (common-mode) | 03 §3 |
| E3 | Cross-arm pairing | Spearman/Pearson on per-prompt micro PER | 192 prompts | ρ=0.755; paired Δ +1.11 pp [−3.73,+5.59] | 03 §4 |
| E4 | ASR determinism | byte-identical repeats ×4 | 384 × both arms | 384/384 identical | 03 §5 |
| E5 | Non-ASR judge parity | SB/MuLan/AMC vs official | selected-192 | Δ −0.027/−0.010/−0.004 | 02_M2 + 08 claims |
| E6 | Language balance | zh/en split | 94/98 prompts | 16.4/17.2 % (Arm A) | 03 §7 H6 |
| E7 | **Error direction** (RC2) | net transcript length (hyp−ref chars), bootstrap | selected-192 | **−47.7 chars [−70.3,−28.5]; 140/50 negative-dominant** | RC2_03_PER_LENGTH_EFFECTS_ARMA.json |
| E8 | **Length-effect check** (RC2) | Spearman PER vs ref-phonemes/hyp-length/audio-seconds | selected-192 | \|ρ\| ≤ 0.13 → not a length artifact | same |
| E9 | **Official input-preparation validation** (RC2) | frozen `prepare_inputs()` on real Arm A bundle, clean report dir | 384 candidates | **PASS 384/384** (request/config/weights/FLAC + mp3 receipts) | /data/yue2/tmp/rc2_kit_validation/ + runbook |
| E10 | **Bundle verifier fault injection** (RC2) | count/missing-artifact/size/sha corruption modes | synthetic mini-bundle | 4/4 fail-closed with precise diagnosis | verifier unit check (session log) |
| E11 | Cross-evaluator A2 | official CUDA scorer on our audio | selected-192 | **BLOCKED_EXTERNAL** (kit validated; owner transfer approval + CUDA host) | RC2_03_CROSS_EVALUATOR_MATRIX.csv |
| E12 | Author reference C1/C2 | authors' audio/receipts on both evaluators | tbd | **BLOCKED_EXTERNAL** | RC2_06 request |

Positive/negative control status: E1 is the positive control for the
analysis path (exact aggregate reproduction); E5 is the negative control for
"everything is worse" (non-ASR judges at parity on the same audio); E9 is
the positive control for the external procedure. The decisive discriminating
experiment (E11) remains blocked external — no causal claim is upgraded.
