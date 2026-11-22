# RC2 CUDA reference-evaluator handoff kit — CORRECTED & VALIDATED (supersedes 03_CUDA_REFERENCE_HANDOFF.md §1–2)

**Status:** procedure VALIDATED end-to-end on this host (CPU side) against
the real Arm A bundle: the official frozen `wsb_eval.prepare_inputs()`
accepted **384/384** candidates (request/config/weights/FLAC verification +
mp3 identity receipts) in a clean report directory, 2026-11-19
(validation log: `/data/yue2/tmp/rc2_kit_validation/`, reproduced by
`validate_prepare.py` there).

## Why the previous kit was wrong (defects found by RC2 audit)

| # | Defect in the old handoff | Consequence | Correction |
|---|---|---|---|
| 1 | `python -m wsb_metrics.wsb_eval score …` | `ModuleNotFoundError` — `wsb_metrics` is not a package (no `__init__.py`) | `python wsb_metrics/wsb_eval.py score …` from the WildSongBench root (exactly how the frozen chain invokes it) |
| 2 | Transfers **mp3-only** (`scores/audio/`, ~2 GiB) | The official scorer in `standard` mode REQUIRES each candidate's full verified bundle (`result.json` + `request.json` + `config.json` + `audio.flac` + the npy artifacts — `verify_result` re-hashes everything and validates request text against the frozen WSB targets). Bare mp3s only work in `historical` mode, which is restricted to the frozen fixtures | Transfer the complete `songs/<id>/` directories (**16.3 GiB per arm** per the generated Arm A manifest: 384 candidates, 4224 files, all SHA256-verified) |
| 3 | Layout `runs/armA_cross/audio/<id>/audio.mp3` per `audio_rel` | `prepare_inputs` resolves each row's `path` RELATIVE TO the input file's parent — must be `songs/<id>` exactly as written in `evaluation_inputs.jsonl` | Transfer `evaluation_inputs.jsonl` + `songs/` tree verbatim; `--input <bundle>/evaluation_inputs.jsonl` |
| 4 | Missing environment preparation step | score would fail on a bare clone | run `python wsb_metrics/wsb_eval.py prepare --metrics per,songbench --install` first (uv-managed venvs, frozen) |

## Exact receiving-side procedure (validated)

```bash
# 0. official pinned evaluator — plain CUDA torch machine (H100/A100/RTX…)
git clone https://github.com/m-a-p/WildSongBench && cd WildSongBench
sha256sum -c SHA256SUMS                       # must pass (frozen pins)

# 1. receive the private bundle (HF private dataset or authors' secure upload)
#    armA_transfer/evaluation_inputs.jsonl
#    armA_transfer/songs/wsb_<id>/{result.json,request.json,config.json,
#                                 audio.flac,prefix.npy,semantic.npy,latent.npy,…}
#    armA_transfer/armA_bundle_manifest.json   (RC2 full manifest, see below)

# 2. verify the transfer BEFORE scoring (fail-closed, no GPU needed):
python verify_transfer_bundle.py --bundle armA_transfer \
       --manifest armA_transfer/armA_bundle_manifest.json
#    -> "bundle OK: 384 candidates, N files" or a precise first mismatch

# 3. prepare frozen metric environments (uv; per-metric venvs):
python wsb_metrics/wsb_eval.py prepare --metrics per,songbench --install

# 4. official scoring — NO code changes, identical flags to our runs:
python wsb_metrics/wsb_eval.py score \
    --input armA_transfer/evaluation_inputs.jsonl \
    --output runs/armA_cross_scores_cuda \
    --mode standard --metrics per,songbench
#    selected-192 PER = runs/armA_cross_scores_cuda/summary.json
#                       .standard_selected.groups.all.per.per_micro
```

Notes (verified from the pinned scorer source):
- seeds/requests are validated against the frozen WSB targets
  (`[831001, 831019][j] + i`) — our bundle passes (step 2 of the validation).
- the scorer re-encodes mp3 itself via its bundled ffmpeg with identity
  receipts — do NOT pre-convert audio.
- `--per-results` reuse is available for the mulan/amc stages only after a
  complete per_song.jsonl exists on the same side.

## Return artifacts (what closes cell A2)

1. `runs/armA_cross_scores_cuda/summary.json` (full) + `per_song.jsonl`
   (contains licensed lyrics/transcripts — keep private; aggregates suffice
   for publication).
2. Environment record: `pip freeze` of the metrics venv, GPU model, torch +
   CUDA versions, `git rev-parse HEAD` of WildSongBench, and whether ANY
   modification was needed (expected: none).
3. If possible, per-prompt PER for pairing (we provide
   `03_PER_CROSS_ARM_INTERNAL.json` for prompt-level pairing on our side).

## Pre-registered interpretation (unchanged from 03 report)

| `X_cuda` (selected-192 PER of OUR audio on THEIR evaluator) | Conclusion |
|---|---|
| ≈ 8–11 % (≤ 2 pp above 8.44 %) | H1: evaluator-backend (ROCm ASR) discrepancy |
| ≈ 16–18 % | H2: generation-side (ROCm numerics) discrepancy |
| intermediate | co-factor split; quantify via per-prompt pairing |

## Files in this kit

| File | Purpose |
|---|---|
| `README_CUDA_RUNBOOK.md` | this runbook |
| `verify_transfer_bundle.py` | receiving-side fail-closed bundle verification (RC3-hardened: symlink escape, path traversal via manifest ids, non-`songs/<id>` input paths, duplicate ids and index disagreements all rejected; pinned by `tests/test_transfer_bundle_verifier.py`) |
| `armA_bundle_manifest.json` | Arm A full-bundle manifest: 384 candidates / 4224 files, per-file SHA256 + bytes (16.26 GiB payload; end-to-end verified against the real bundle: `bundle OK: 384 candidates, 4224 files verified`) |
| `armB_bundle_manifest.json` | Arm B full-bundle manifest (RC3): 384 candidates / 4224 files / 8.62 GiB, end-to-end verified; official frozen `prepare_inputs()` additionally accepted the real Arm B bundle **384/384** in a clean report dir (1017 s) |

Privacy: bundles contain performances of licensed WildSongBench lyrics and
model outputs — **private channel only, never the public repository** (same
policy as the previous kit; unchanged).
