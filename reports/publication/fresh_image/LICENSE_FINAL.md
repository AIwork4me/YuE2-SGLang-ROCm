# LICENSE FINAL — Fresh Image (Phase P8)

Written: 2026-11-15 · Supplement to `reports/publication/09_LICENSE_AND_ATTRIBUTION.md`
(all historical analysis remains valid; this file adds the fresh-image state and
the exact licensing posture for the planned blog/publication).

## 1. Component licensing matrix (unchanged by the fresh image)

| Component | License | Key restriction | Our use |
|---|---|---|---|
| YuE2-3B weights (`m-a-p/YuE2-3B`) | **CC BY-NC 4.0** (model card; licenses/ dir in repo) | no commercial use | research reproduction only — disclosed |
| YuE2-Vae-legacy weights | CC BY-NC 4.0 (same family) | no commercial use | research reproduction only — disclosed |
| YuE code / yue2-infer 0.1.3 | Apache-2.0 (repo) | attribution | per LICENSE/THIRD_PARTY_NOTICES |
| WildSongBench dataset (prompts, lyrics, evaluator bundle) | dataset license (HF) — research use | **lyrics/audio are copyrighted third-party content** | generation+scoring only; no redistribution; receipts lyric-redacted |
| Qwen3-ASR-1.7B | Apache-2.0 | — | PER scoring |
| SGLang PR #42106 @ ced0ef7d | Apache-2.0 | — | serving arm; patches 0001–0005/0008 disclosed |
| wsb_metrics evaluator bundle | per dataset release | frozen-pin scoring only, patches disclosed (0006/0007/0009/0010) | no scoring-math changes |

## 2. What we may publish

- ✅ Metric values, hashes, manifests, protocol descriptions, redacted receipts.
- ✅ Original demo audio generated from OUR OWN lyrics (acceptance script
  lyrics are original text written in this repo).
- ❌ WildSongBench lyrics (any form that reproduces them: text, phoneme
  sequences, ASR transcripts of songs that sing them) → `scripts/redact_evidence.py`.
- ❌ Model weights (CC BY-NC; no redistribution).
- ❌ Claims implying commercial use of YuE2 weights.

## 3. Attribution requirements for the blog (with YuE2 authors)

1. YuE2 model + inference code: multimodal-art-projection/YuE (Apache-2.0), cite paper.
2. WildSongBench: m-a-p/WildSongBench, cite paper/dataset card.
3. SGLang: sgl-project/sglang PR #42106 (YuE2 support), patches listed in `patches/README.md`.
4. AMD ROCm stack versions (torch wheels, driver) — reproducibility table.
5. This repo's evidence chain (commit SHAs) for every number quoted.

## 4. Verdict

- **Licensing review: PASS** for research reproduction + redacted publication
  of receipts, contingent on the LQ-1 owner decision (see SECURITY_FINAL.md).
- Blog must carry the CC BY-NC statement for YuE2 weights and must not imply
  commercial-use rights.
