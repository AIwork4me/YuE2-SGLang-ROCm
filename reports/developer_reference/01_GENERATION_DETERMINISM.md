# 01_GENERATION_DETERMINISM.md — RC6 A1: historical generation determinism closure

Generated: 2026-11-27 · Tool: `scripts/rc6_determinism_closure.py` (re-derives
everything live; nothing is copied forward from RC5.1 reports without
recomputation).

## A1.1 — Comparison reproduced

| Check (journal × frozen historical Arm B manifest) | Result |
|---|---|
| Candidates compared | 384/384 |
| FLAC **file** byte-identical (SHA256) | **380/384** (98.96%) |
| Non-identical | `wsb_077_r0_s831078`, `wsb_077_r1_s831096`, `wsb_166_r1_s831185`, `wsb_171_r1_s831190` |
| Duration (1e-6 s), truncation flag, official seed, style/lyrics input hashes | identical on **all 384** |
| Codec frame count (audio token count) | identical on all 4 non-identical |
| FLAC byte deltas | −2 / +2 / +15 / **0** bytes (in 17–26 MB files) |

## A1.2 — Decoded PCM identity

For the 4 non-identical candidates + 8 byte-identical controls:

- Decoded via soundfile/libsndfile 1.2.2; **no resampling, no precision loss**
  (24-bit values are exact in float64).
- PCM identity recorded two ways: the FLAC STREAMINFO MD5 recomputation
  (24-bit LE interleaved) and a float64-interleaved SHA256
  (decoder-independent). Both agree with the container's own MD5 on every
  file: **lossless self-consistency 12/12**.
- The campaign copies are byte-identical to the restore-drill copies (backup
  integrity) for all tested candidates.

**Historical FLAC artifacts do not exist on this host** (verified by a
full-filesystem search; they were deleted with the historical image). Only
the frozen manifest rows survive. Therefore:

> `PCM_IDENTITY_UNVERIFIABLE_HISTORICAL_ARTIFACT_ABSENT` for each of the 4
> candidates; their **content identity remains `CONTENT_IDENTITY_NOT_ESTABLISHED`**.
> 380/384 remain `FILE_BYTE_IDENTICAL`.

We did **not** regenerate historical audio and did not substitute new audio
for old files.

## A1.3 — Token / codec identity

Current-run intermediates (`semantic.npy`, `abc_tokens.npy`, `latent.npy`,
`prefix.npy`, `config.json`) are hashed and match the restore-drill copies.
Historical intermediates are absent → cross-run **token-sequence** identity
cannot be computed. Note precisely: identical `codec_frames` is token-**count**
evidence, never token-sequence identity (the 380 byte-identical files *do*
prove full-chain identity including tokens; the 4 do not).

## A1.4 — FLAC encoder RCA (controlled experiment)

| Experiment | Result |
|---|---|
| Same-build re-encode (soundfile PCM_24, current libsndfile 1.2.2) of the 4 + 2 controls | **byte-identical 6/6** to the campaign files — the current toolchain is deterministic and the campaign files are its exact product |
| Different-encoder control (ffmpeg native FLAC) on the same PCM | **bytes differ 6/6, decoded PCM identical 6/6** — direct, reproducible proof that identical PCM yields non-identical FLAC bytes across encoder implementations |

This converts the RC5.1 libFLAC-build-drift root cause from a plausible
narrative into a *demonstrated mechanism class* (encoder-build sensitivity),
while honestly leaving the historical file comparison itself unverifiable.
The RC5.1 claim "root cause = libFLAC build drift" is *consistent* with all
live evidence (identical duration/frames/seed; ±15-byte container deltas;
encoder-build sensitivity demonstrated) but remains **NOT_PROVEN_PER_SAMPLE**
because the historical bytes are gone.

## Verdict

- `380/384 FILE_BYTE_IDENTICAL` — live-rederived.
- 4 candidates: duration/frames/seed/inputs identical; PCM identity
  UNVERIFIABLE (historical artifact absent); content identity NOT_ESTABLISHED.
- Generation determinism was never an acceptance gate and is not converted
  into one now.

Machine-readable: `01_PCM_HASH_COMPARISON.json`,
`01_TOKEN_IDENTITY_COMPARISON.json`, `01_DETERMINISM_VERDICT.json`.
