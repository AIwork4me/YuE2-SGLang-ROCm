# 03 — CUDA reference-evaluator handoff kit (A2/B2 cells of the M3.2 matrix)

> **RC2 CORRECTION (2026-11-19):** an exact-HEAD audit + live validation
> found this kit's §1–2 procedure NON-EXECUTABLE as written: (1) the
> `python -m wsb_metrics.wsb_eval` invocation fails (not a package);
> (2) mp3-only transfer is insufficient — the official scorer's `standard`
> mode requires each candidate's FULL verified bundle (~15 GiB/arm);
> (3) the documented layout does not match the scorer's input-path
> resolution; (4) the `prepare --install` step was missing.
> The corrected, **validated** kit (official `prepare_inputs` accepted
> 384/384 real Arm A bundles on this host) lives in
> `rc2/RC2_03_AUTHOR_CUDA_HANDOFF/README_CUDA_RUNBOOK.md` + full-bundle
> manifest + receiving-side verifier. The interpretation table (§4 below)
> and privacy policy are UNCHANGED.

**Purpose:** score OUR audio with the AUTHORS' official CUDA evaluator to
separate evaluator-backend effects (H1) from generation effects (H2) in the
PER gap. This host has no CUDA GPU; cells A2/B2 are `BLOCKED_EXTERNAL` until
this kit executes on a CUDA machine (authors' or any volunteered H100/A100/
RTX host) or the authors provide C1/C2 reference data.

## 1. Package contents (private transfer — licensed WSB lyrics in audio)

| Item | Location (this host) | Size | Verification |
|---|---|---|---|
| Arm A fresh audio (384 × mp3, 24 kHz mono) | `/data/yue2-runs/armA_wsb_full/scores/audio/` | 2.0 GiB | per-file SHA256 in `03_AUDIO_TRANSFER_MANIFEST.json` |
| Transfer manifest (ids, seeds, sha256) | `reports/joint_blog_rc/03_AUDIO_TRANSFER_MANIFEST.json` | — | count must equal 384 |
| evaluation_inputs.jsonl (selection order) | `/data/yue2-runs/armA_wsb_full/evaluation_inputs.jsonl` | — | 384 rows |
| Arm B fresh audio (this image) | `/data/yue2-runs/armB_wsb_full/` (when campaign completes) | — | regenerate manifest with the same script pattern |

Transfer channel: private only (HF private dataset repo, private object
storage, or authors' secure upload) — NEVER the public GitHub repository.

## 2. Exact CUDA-side procedure (unmodified official evaluator)

```bash
# (1) official pinned evaluator, no ROCm patches — plain CUDA torch
git clone https://github.com/m-a-p/WildSongBench && cd WildSongBench
sha256sum -c SHA256SUMS          # must pass (pins incl. manifest 859e5225…)

# (2) place the transferred audio preserving relative paths:
#     runs/armA_cross/audio/<id>/audio.mp3          (per manifest audio_rel)
# (3) verify every file against the manifest before scoring:
python - <<'PY'
import hashlib, json
m = json.load(open("03_AUDIO_TRANSFER_MANIFEST.json"))
bad = [f["id"] for f in m["files"]
       if hashlib.sha256(open("runs/armA_cross/audio/" + f["audio_rel"], "rb").read()).hexdigest() != f["audio_sha256"]]
assert not bad, f"transfer corrupted: {bad[:5]}"
print("transfer OK:", m["count"], "files")
PY

# (4) official scoring — identical to the authors' protocol invocation
#     (adapt only --input paths to the package layout; no code changes):
python -m wsb_metrics.wsb_eval score \
    --input runs/armA_cross/evaluation_inputs.jsonl \
    --output runs/armA_cross/scores_cuda \
    --mode standard --metrics per,songbench
# selected-192 summary lands in runs/armA_cross/scores_cuda/summary.json
# under standard_selected.groups.all.per.per_micro
```

## 3. Return artifacts (what closes the analysis)

1. `scores_cuda/summary.json` (full file) + `per_song.jsonl`.
2. The evaluator environment record: `pip freeze`, GPU model, torch/CUDA
   versions, the exact WSB commit (`git rev-parse HEAD`).
3. Confirmation whether ANY modifications were needed to run (expected: none).

## 4. Validation & interpretation (pre-registered)

Let `X_cuda` = selected-192 PER of our audio on the CUDA evaluator.

| Outcome | Interpretation |
|---|---|
| `X_cuda ≈ 8–11 %` (≤ 2 pp above official 8.44 %) | **H1 confirmed**: the gap is the ROCm ASR backend; ROCm-side fix or disclosed adjustment path follows |
| `X_cuda ≈ 16–18 %` | **H2 confirmed**: generation-side on ROCm; RCA moves to model numerics (bf16 kernels), independent of serving stack |
| intermediate | co-factor split; quantify with the per-prompt paired set provided below |

Power analysis: with 192 prompts, the prompt-level bootstrap CI half-width on
this measurement is ≈ ±2 pp — sufficient to separate the two hypotheses
(8–11 vs 16–18) decisively.

## 5. Per-prompt pairing support

`reports/joint_blog_rc/03_PER_CROSS_ARM_INTERNAL.json` (this repo) contains
per-prompt micro PER for Arm A and gfx1151 enabling the CUDA-side result to
be paired against ours prompt-by-prompt (Spearman ρ between evaluators is
itself diagnostic of transcript-level disagreement localization).

## 6. Status ledger

| Cell | Status | Blocked-on |
|---|---|---|
| A2 | BLOCKED_EXTERNAL | CUDA host + private audio transfer approval (owner decision) |
| B2 | BLOCKED_EXTERNAL | Arm B campaign completion (running) + same |
| C1 | BLOCKED_EXTERNAL | author reference audio (not distributed) |
| C2 | BLOCKED_EXTERNAL | author per-song receipts (not published) |
