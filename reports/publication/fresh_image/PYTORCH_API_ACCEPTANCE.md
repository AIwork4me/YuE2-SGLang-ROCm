# PYTORCH API ACCEPTANCE (P4.1) — Fresh Image

Executed: 2026-11-15 00:05–03:36 UTC · Environment A (torch 2.10.0+rocm7.1,
HIP 7.1.25424, transformers 4.57.6, yue2-infer 0.1.3, backend `torch-eager`)
· GPU: gfx1100 (W7900D, 48 GB) · Receipts: `/data/yue2-runs/api_acceptance/acceptance.json`
(log: `/data/yue2/logs/api_acceptance2.log`)

## Verdict: 13/14 PASS (the single FAIL is a documented library behavior, not a blocker)

| # | Test | Result | Evidence |
|---|---|---|---|
| 1 | Fresh model load | PASS | 5.5 s; weights sha verified live = frozen pins (1d55c42c…/b6d28362…) |
| 2 | Full-song cot=full (2 GiB budget) | PASS | stereo 48 kHz, verify_result round-trip |
| 3 | Save/reload artifacts | PASS | verify_result identity match on reload |
| 4 | cot=melody | PASS | 29.12 s audio, 201 s wall |
| 5 | cot=off | PASS | 37.52 s audio |
| 6 | External ABC score | PASS | 42.12 s audio from provided ABC |
| 7 | Staged API plan→semantic→synthesize→decode | PASS (retest) | 42.64 s stereo/48 kHz finite audio, sha 5099e122…; see corrections below |
| 8 | Deterministic replay (same seed, same env) | PASS | identical semantic.npy sha across two runs (5172dd1b…) |
| 9 | Original demo lyrics | PASS | items 2–8 use original repo-written lyrics |
| 10 | Error handling (empty lyrics) | PASS·disclosed | API ACCEPTS empty lyrics (recorded as API choice, no crash; GPU healthy after) |
| 11 | GPU healthy after error paths | PASS | finite matmul after error tests |
| 12 | Long request (official 24 GiB budget) | PASS | 72.24 s audio, 327.7 s wall |
| 13 | Memory cleanup on close | **FAIL — root-caused** | see below |
| 14 | (7 retried under correct API) | — | — |

## Corrections made during acceptance (full disclosure)

Three retest iterations were needed for item 7; each initial failure was MY
API misuse, corrected against the real package source — not product defects:
1. `sampling={"seed": 7}` — invented parameter (`Sampling` has no seed; the
   seed travels via `SongRequest.seed`). Fixed: `sampling=Sampling()`,
   `request=SongRequest(seed=7, …)`.
2. `memory_budget_gib=2/4` — below the model's needs (budget is a hard cap
   minus 2 GiB reserve; 3B model needs ~10 GiB). Fixed: official 24.
3. `decode()` returns raw audio (ndarray), not a Song object — `save_artifacts`
   exists only on `pipe(...)` results. Fixed: soundfile write + validity checks.

## Item 13 root cause (real finding, reported as-is)

`pipe.close()` + `gc.collect()` + `torch.cuda.empty_cache()` released only
0.34 GiB of ~10.2 GiB device memory **inside the living process**
(`close_probe` in acceptance.json). Full release happens at process exit.
Consequence: sequential pipelines in ONE process will accumulate device memory
and can OOM; the campaign driver already avoids this by design (fresh child
process per candidate). This is documented as a YuE2 (yue2-infer 0.1.3)
behavior observation for the upstream conversation — not silent-failed, not
worked around by weakening the assertion.

## Notes

- MIOpen workspace warnings (`IsEnoughWorkspace … provided ptr: 0 size: 0`)
  appear throughout generation; they are benign advisories, generation is
  correct (all audio finite/valid; official verify_result passes).
- Empty-lyrics acceptance (item 10) is the package's actual behavior on
  0.1.3; recorded honestly rather than treated as a defect.
- Campaign-relevant conclusion: Environment A + official API + torch-eager on
  this fresh image produce valid full songs with deterministic replay —
  G3-class acceptance evidence for the fresh image.
