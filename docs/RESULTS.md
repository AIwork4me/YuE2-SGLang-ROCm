# Results

Every number below maps to a machine-readable receipt. Historical campaign
numbers are labeled HISTORICAL; numbers from the 2026-11 mission are labeled
FRESH. Nothing is transcribed by hand where a generator script exists.

## Official reference points (WildSongBench, standard YuE2)

Source: `m-a-p/WildSongBench` README + `benchmark/results.md` (September 12,
2026 comparison), verified 2026-11-11.

| Metric | Official YuE2 (selected-192 protocol) |
|---|---:|
| SongBench Avg | 6.7316 |
| MuLan | 0.5068 |
| AllMusicCaps | 0.4054 |
| Q3O | 4.6819 |
| PER | 8.44% |

Official fresh-run variance (documented by the authors): SongBench 6.73
(H800) / 6.74 (RTX 4090) vs 6.7316 paper.

## HISTORICAL campaigns (inherited evidence — unchanged)

| Metric | gfx1151 SGLang | W7900 SGLang | W7900 Omni |
|---|---:|---:|---:|
| SongBench GA (unselected-384) | 6.718 | 6.731 | 6.730 |
| SongBench GA (selected-192) | 6.683 | 6.736 | 6.732 |
| PER micro (selected-192) | 17.22% | 17.01% | 17.61% |
| MuLan (selected-192) | 0.505 | 0.510 | 0.508 |
| AllMusicCaps (selected-192) | 0.412 | 0.405 | 0.406 |
| ASR-capped samples (of 384) | 88 | 120 | 128 |

Evidence: `evidence/official_scores*.json`, `evidence/gfx1100/scoring_snapshot.json`,
branch `validation/gfx1100-rocm7141`.

## FRESH campaigns (2026-11 mission, this branch)

| Arm | Status | Receipts |
|---|---|---|
| Arm A pilot (official torch-eager, prompt 0) | 2/2 complete; PER 6.47% / 19.40% (4 identical greedy passes, no capping) | `evidence/publication/armA_pilot/` |
| Arm B full (SGLang, 384) | **COMPLETE — audit FULL; solo official scoring done** | `evidence/publication/armB_campaign/` |
| Arm A full (official PyTorch, 384) | QUEUED (chained after Arm B audit) | `evidence/publication/armA_campaign/` (when complete) |

### Arm B fresh official results (2026-11-14, solo, frozen evaluator + disclosed patches)

| Metric | Fresh W7900 SGLang | Official reference | Δ | Verdict |
|---|---:|---:|---:|---|
| SongBench GA (selected-192) | **6.7376** | 6.7316 | +0.0060 | within ±0.05 target |
| SongBench GA (unselected-384) | 6.7311 | — | — | matches historical pattern |
| PER micro (selected-192) | 17.77% [CI 15.20–20.68] | 8.44% | +9.33pp | gap root-caused (reports/publication/05_PER_ROOT_CAUSE.md) |
| MuLan (selected-192) | **0.5093** | 0.5068 | +0.0025 | within ±0.01 target |
| AllMusicCaps (selected-192) | **0.4056** | 0.4054 | +0.0002 | within ±0.01 target |

ASR backend: qwen_asr/transformers on ROCm (patch 0007, disclosed); 112/384
capped-ASR candidates retained per official policy. Empty cells mean "not
measured yet", never "assumed".

**Headline (Arm B, fresh 2026-11-14, solo official scoring): SongBench,
MuLan and AllMusicCaps all reproduce the official YuE2 reference within the
frozen acceptance thresholds (Δ +0.006 / +0.0025 / +0.0002). The PER gap is
separately root-caused and disclosed (05_PER_ROOT_CAUSE.md).**

## Performance (W7900, measured)

| Path | Metric | Value | Receipt |
|---|---|---|---|
| PyTorch torch-eager | full-song generation | ~7 min/song (pilot, 2 songs) | armA pilot log |
| SGLang server | full-song generation (official budget) | 245.8 s median (first 9) | armB progress.jsonl |
| SGLang server | idle VRAM | ~11 GiB | phase-4 observation |
| SGLang server | peak VRAM during generation | ~41 GiB (historical; re-measuring) | historical evidence |

Real-time factor and concurrency sweeps are scheduled with Phase 4
performance measurement on the fresh stack; the historical serving
measurement (BS=1, P50 217.3 s for 223 s audio) remains in the README until
superseded.
