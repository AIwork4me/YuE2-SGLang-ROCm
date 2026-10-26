# 03 — SGLang-Omni #2540 Integration Closure (2026-10-26)

## Summary

Two integration artifacts, both validated on gfx1151 today:

1. **Pinned-base rehearsal reproduced bit-exact** — the documented four-step
   sequence on the author's unchanged `add_yue2` (`85ae4b73`) yields exactly
   the recorded tree `363073e688fa9761c72f029a1022a87405b1aead`
   (zero conflicts at every step).
2. **Fresh integration preview vs latest main** —
   `AIwork4me/sglang-omni @ integration/yue2-omni-merge-ready`
   (head `3063cdf5`, pushed): rehearsal tree + upstream main `b6299238`
   (381 commits past the merge base `39288997`), **merged with zero
   conflicts** — the single both-sides file auto-merged correctly.

## Step 1 — Rehearsal + latest-main resolution

Sequence (per `docs/YUE2_UPSTREAM_AUTHOR_HANDOFF.md`), on worktree
`upstream/sglang-omni-rehearsal`:

| Step | Operation | Result |
|---|---|---|
| 1 | `merge --no-ff eca7770f` (Omni ROCm PR #1) | clean |
| 2 | `merge --no-ff 4c089d19` (Long-Lyrics PR #2) | clean |
| 3 | `cherry-pick ae11c6ad` (mechanical style) | clean |
| 4 | `cherry-pick b91b9544` (naming policy) | clean |
| — | tree SHA | **`363073e6…` = recorded historical tree (bit-exact)** |
| 5 | `merge origin/main b6299238` | **clean**; tree `69dc29fa` |

Conflict surface analysis (plumbing diff, no-renames): main changed 2 837
files since the merge base; our delta touches 31 files; **overlap = exactly
one file**, `tests/unit_test/models/test_model_capabilities.py`, whose
changes are in distinct hunks (main reorganized unrelated entries; ours adds
`YuE2ForCausalLM` capabilities). The auto-merge was verified by inspection
(yue2 entry intact on top of main's content) and by the file's tests.

No previously-applied fixes were duplicated: the rehearsal consumes the PRs
and commits as-is; the main-merge adds only upstream content.

## Step 2 — Unit tests and lint

Env: `environments/yue2` venv + `PYTHONPATH=<tree>`; missing pure-python
test deps installed explicitly (msgpack, silero-vad, onnxruntime,
websockets, av) — the torch/HIP stack untouched.

| Suite | Rehearsal tree (`363073e6`) | Merged tree (`3063cdf5`) |
|---|---|---|
| `test_yue2_platform_gates.py` | PASS | PASS |
| `test_yue2_rename_regression.py` | PASS | PASS |
| `test_yue2_speech_input_cap.py` (incl. prompt-164) | PASS | PASS |
| `test_model_capabilities.py` (incl. YuE2 entry) | n/a* | PASS |
| **Total** | **39/39** | **60/60** |

\* not part of the rehearsal delta; on the merged tree it passes with our
entry and main's cases together.

Lint (omni's own pins: ruff 0.11.10 with its hook args, black 24.10.0,
isort 5.13.2 — installed in a dedicated tools venv): all 28 changed `.py`
files clean on both trees. Omni's pre-commit has **no codespell hook**; two
codespell-visible typos exist in the author's original comments
(`modeling_yue2.py:957` "MoT", `sampling.py:14` "suport") — outside omni's
lint surface, left untouched (minimal-change policy).

## Step 3 — Long-lyrics regression

Mission reference: WildSongBench prompt 164 (~4 114 serialized characters)
rejected by the generic 4 096-char speech limit.

- Regression tests present and passing on both trees:
  `test_speech_endpoint_serves_prompt164_under_yue2_limit` (YuE2 accepts
  the valid full-song request) and
  `test_speech_endpoint_rejects_prompt164_under_generic_limit` (other TTS
  models keep the generic limit) — mocked HTTP-contract tests per the
  mission's "no expensive audio generation for acceptance" instruction.
- The synthetic-input case (`4c089d19`) and cap-override neutralization are
  part of the rehearsal content; other-input rejection and the
  resource-consumption bound (model-specific, still-bounded cap) are
  covered by the suite.
- Original behavior reproducibility on the pre-patch baseline was
  demonstrated in the prior mission (documented then); the base is
  unchanged since (`85ae4b73` re-verified 2026-10-26).

## Step 4 — Real ROCm Omni smoke (gfx1151)

```
sgl-omni serve (python -m sglang_omni.cli app) --model-path models/YuE2-3B --port 30075
  PYTHONPATH = <omni integration tree> : <sglang integration tree>/python
  SGLANG_YUE2_VAE_DIR = models/YuE2-Vae-legacy
  no SGLANG_YUE2_* disable vars; engine = sglang integration branch
  (44c8fa51f + host-boot overlay), matching omni main's sglang==0.5.22 pin
```

- `POST /v1/audio/speech` (documented schema: model/voice/input JSON with
  style/lyrics/cot=full/seed 831001) → **HTTP 200 in 158.9 s**
- Output WAV: 2 ch, 48 000 Hz, **79.96 s**, finite, peak 29 275,
  RMS 4 535, 95.5 % non-silent
- Server log: `YuE2 synth done request=speech-75c3e684… samples=3838016
  duration=79.96s elapsed=158.83s batch=1` — **BS=1** as required
- GPU identified: AMD Radeon 8060S (gfx1151); placement/topology plan
  resolved for Yue2PipelineConfig

Artifacts: `runs/merge_readiness/phase3_omni_smoke/` (WAV), log
`logs/server_omni_integration.log`.

## Acceptance criteria status

- Integration preview vs latest main reviewable — **PASS**
  (`integration/yue2-omni-merge-ready`, zero conflicts, 31-file delta)
- No unresolved YuE2-specific lint failures — **PASS**
- Unit tests pass — **PASS** (39/39 rehearsal, 60/60 merged)
- Long-lyrics regression closed — **PASS**
- Real gfx1151 HTTP music generation — **PASS** (sgl-omni serve, /v1/audio/speech)
- NVIDIA CUDA fast paths preserved — **PASS** by construction + simulated
  dispatch tests (unchanged validated content; Review B of the SGLang side
  applies to the shared guard design; physical H800 remains author-owned)
- H800 validation — **PENDING (author)**, unchanged

## Note on merge-methodology honesty

The merged tree's both-sides file count is one; every other path took
exactly one side's content (mechanically safe). The merge commit exists on
a partial clone; the final tree was materialized with a sparse worktree
excluding only `Voxt/` (an unpackaged macOS Swift client app unrelated to
sglang_omni) — no content differences result, and the pushed branch
carries the full tree regardless.
