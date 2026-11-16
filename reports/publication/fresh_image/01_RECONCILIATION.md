# 01 RECONCILIATION — Fresh Image vs Historical Records

Written: 2026-11-15T00:05Z · Executor: fresh-image session 1
Repo base: `feat/yue2-rocm-publication-readiness` @ `fdfc0ac` (verified identical to
the mission brief's reference SHA; `main` @ `4612c20` also verified).
Continuation branch: `mission/w7900-fresh-image-final-closure`.

## 1. What survived (verified on this image)

| Asset | Where | State |
|---|---|---|
| All reports, evidence receipts, docs, scripts, configs, patches, tests, CI | git repo (pushed) | ✅ intact — cloned and SHA-verified against GitHub |
| Arm B final receipts (384/384 audit FULL; SongBench 6.7376 / MuLan 0.5093 / AMC 0.4056 / PER 17.77%) | `evidence/publication/armB_campaign/` in git | ✅ intact |
| Arm A progress snapshot (108/384 verified) + pilot (2/2) | git receipts + handoff | ✅ receipts intact |
| Frozen pins (dataset rev, model/VAE revisions + SHA256, evaluator bundle SHA, SGLang PR commit + tarball SHA) | `configs/benchmark.lock.yaml`, `scripts/download_pins.py` | ✅ intact — all re-downloadable from upstream at these pins |

## 2. What is missing on this image

| Asset | Consequence |
|---|---|
| `/data/yue2` and `/data/yue2-runs` (all venvs, evaluator tree, HF cache, **all raw campaign audio**, scoring dirs, logs) | Nothing is directly reusable; per handoff §2/§8 this was expected: "audio artifacts in /data are regenerable (seeds/protocol pinned) but NOT re-pushed" |
| Live Arm A campaign process (was at ≥108/384 when the old image was reclaimed) | Fresh campaign required; historical audio cannot be claimed as this image's evidence |

## 3. Reuse policy (strict)

- **Historical Arm B scores (SongBench 6.7376, MuLan 0.5093, AMC 0.4056, PER 17.77%)**
  are retained **only as historical receipts** from a prior execution environment
  (gfx1100, torch 2.12.0+rocm7.14.1, SGLang ced0ef7d). They are NOT reused as
  fresh-image evidence. Fresh-image Arm B requires either verified raw artifacts
  (absent → regenerate) — i.e. a new 384-candidate campaign.
- **Historical Arm A 108/384**: same rule. The new campaign restarts from 0 on
  this image with a new run identity. No JSON summary may be converted into
  "complete" status.
- **Regeneration determinism**: seeds/protocol are pinned per candidate
  (`831001+i`, `831019+i` from the frozen manifest), so regenerated audio is
  protocol-identical, but we do **not** claim byte-identity with lost historical
  audio (no verified comparison exists). Each fresh bundle is hashed at creation.

## 4. Claims status after reconciliation

| Claim | Status on fresh image |
|---|---|
| G0 environment verified | ✅ NEW evidence (this image) |
| G1 reproducible install | ⏳ to rebuild (P2) — reconstruction recipe exists (handoff §5) |
| G2 pins verified | ⏳ downloading now, SHA256-gated |
| Arm B 384/384 + scores | 📁 historical receipts stand; fresh-image re-run REQUIRED for fresh claims |
| Arm A 108/384 | 📁 historical; fresh campaign required (G5) |
| PER gap analysis (pilot) | 📁 historical pilot evidence stands as historical; P6 re-derives on fresh data |
| LQ-1 lyrics-in-evidence security issue | 🔴 still open (Phase P8) |

## 5. What must be regenerated on this image (full list)

1. Environment A (yue2-torch venv: torch 2.10.0+rocm7.1, yue2-infer 0.1.3 wheel).
2. Environment B (sglang venv: torch 2.12.0+rocm7.14.1 device-gfx1100, SGLang
   PR #42106 @ ced0ef7d + patches 0001–0005, 0008).
3. Environment C (evaluator: wsb_metrics tarball + patches 0006/0007/0009 +
   formalized 0010 + metrics/eval venvs + ASR/SongBench/MuLan/AMC weights).
4. Arm A full campaign 384/384 (new run-id).
5. Arm B full campaign 384/384 (new run-id) — fresh-image reproducibility.
6. All scoring runs (PER, SongBench, MuLan, AMC) for both arms.
7. P6 PER RCA experiments (fresh per-song data).

## 6. Deviations & disclosure

None new beyond those already frozen in `configs/benchmark.lock.yaml`
(DEV-1..DEV-4). This image's ROCm userspace is 7.2.1 (preinstalled, preserved);
frozen venvs install their own ROCm torch-wheel subsets — each environment's
GPU smoke validates before any benchmark use. Driver 6.16.13 (newer than all
pins — supported direction).
