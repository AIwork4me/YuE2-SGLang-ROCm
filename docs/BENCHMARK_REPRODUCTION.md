# WildSongBench Reproduction on AMD ROCm (gfx1100)

Step-by-step, matching the frozen official protocol
(`evidence/protocol_lock.json`). Every step below was executed on the W7900
rig; logs and machine-readable evidence live under `evidence/gfx1100/`.

## Protocol summary (frozen by the dataset authors)

- 192 prompts × 2 candidates = **384** generations, original style/lyrics/seeds
  (`candidate 0 = 831001+i`, `candidate 1 = 831019+i`)
- Official generation config: `cot=full`, effective cfg 1.0 (single-branch;
  cfg_scale key is NOT sent), `ode_steps=32`, `semantic_max_tokens=9000`,
  `abc_max_tokens=4096`, `vae_core_frames=1024`, `vae_halo_frames=16`
- No filtering: truncated/high-PER/long candidates are kept
- Scoring: PER (Qwen3-ASR-1.7B, 4 repeats) → best-of-2 selection
  (min PER → min edits → min |phoneme-count diff| → min candidate_index);
  SongBench / MuLan / AllMusicCaps on the same selection
- Evaluator: frozen `wsb_metrics` bundle (SHA-verified tarball) + ROCm
  portability patches 0006/0007 (disclosed torch-family substitution, ASR
  backend change; math untouched)

## Steps

1. **Data**: `python3 scripts/download_pins.py` (all pins SHA256-verified;
   mirrors allowed only under hash verification).
2. **Server**: `bash scripts/serve_yue2_gfx1100.sh`.
3. **Pilot** (recommended before the ~24 h full run):
   ```bash
   python scripts/run_wsb.py --runs $WS/runs/gfx1100/pilot1x2 --indices 1 --run-id pilot1x2
   python scripts/run_wsb.py --runs $WS/runs/gfx1100/pilot5x2 --indices 0 1 2 79 81 --run-id pilot5x2
   python scripts/verify_wsb_artifacts.py --runs $WS/runs/gfx1100/pilot5x2 --mode pilot
   ```
4. **Full run**:
   ```bash
   python scripts/run_wsb.py --runs $WS/runs/gfx1100/<run_id>/wsb_full \
       --run-id <run_id> --wav-archive /big/storage/wavs     # ~24 h on W7900
   bash scripts/watch_milestones.sh $WS/runs/gfx1100/<run_id>/wsb_full full   # auto-checkpoints
   ```
   The driver is resumable (verified candidates are skipped; partial artifacts
   quarantined, never deleted), signal-safe, disk-safe (20 GiB floor), and
   writes an immutable `run_config.json` identity.
5. **Strict audit** (the only acceptable completion proof):
   ```bash
   python scripts/verify_wsb_artifacts.py --runs $WS/runs/gfx1100/<run_id>/wsb_full
   # verdict must be FULL: 384 verified, 192 prompts, 2 candidates each,
   # official verify_result green on every candidate
   ```
6. **Scoring** (evaluator prepared with
   `python3 benchmark/wsb_metrics/wsb_eval.py prepare --metrics
   per,songbench,mulan,allmusiccaps --download hf-mirror --install`, then the
   torch-family swapped to the mission wheels inside its venvs — receipts
   record the substitution):
   ```bash
   cd benchmark/wsb_metrics
   WSB_ROCM_TORCH_OVERRIDE=1 python wsb_eval.py score \
     --input $WS/runs/gfx1100/<run_id>/wsb_full/evaluation_inputs.jsonl \
     --output $WS/runs/gfx1100/<run_id>/scores --mode standard --metrics per,songbench
   WSB_ROCM_TORCH_OVERRIDE=1 python wsb_eval.py score \
     --input $WS/runs/gfx1100/<run_id>/wsb_full/evaluation_inputs.jsonl \
     --per-results $WS/runs/gfx1100/<run_id>/scores/per_song.jsonl \
     --output $WS/runs/gfx1100/<run_id>/additional --metrics mulan,allmusiccaps
   ```

## Honest-reporting rules used throughout

- Verdicts: PASS / FAIL / PARTIAL / BLOCKED / NOT TESTED — never relabeled.
- Truncated-but-valid candidates count as complete (recorded, never filtered).
- Q3O is NOT RUN on 48 GB ROCm hardware (flash-attn 2.8.3 + 30B model
  requirement); it never enters an "all metrics" claim.
- Evaluator backend parity: PER runs the transformers ASR backend on ROCm
  (vLLM has no ROCm build). A parity study vs the reference backend is part of
  the evidence; where parity is not established, results say so explicitly.

## RC5.1 (latest upstream, final results)

Commands as executed on the W7900D (workspace `/data/yue2`):

```bash
# generation (384/384, resumable, crash-durable journal + checkpoints)
RC5_ALLOW_DRIVER_UPDATE=1 RC5_BACKUP_DIR=/workspace/yue2-rc5-backup \
RC5_BACKUP_CLASS=same_host_second_volume \
bash scripts/campaign_ops/rc5_supervise.sh \
  /data/yue2-runs/rc5-latest-upstream-20261124T065451Z/wsb_full \
  rc5_armB_latest_upstream_20261124T065451Z

# PER + SongBench + MuLan/AMC (official evaluator, GPU lock held internally)
bash scripts/campaign_ops/rc5_score.sh <run_dir>/wsb_full per_full standard per
bash scripts/campaign_ops/rc5_score.sh <run_dir>/wsb_full songbench_sel standard songbench <run_dir>/wsb_full/per_full/per_song.jsonl
bash scripts/campaign_ops/rc5_score.sh <run_dir>/wsb_full additional_sel standard mulan,allmusiccaps <run_dir>/wsb_full/per_full/per_song.jsonl

# Q3O (ROCm-adapted judge; official scorer/prompt/weights verbatim)
python scripts/gpu_lock.py wait --who q3o-full --wait-s 3600 -- \
  <vllm-rocm venv>/python scripts/rc5_q3o_judge.py \
  --evaluator-root /data/yue2/benchmark/wsb_metrics \
  --rows <run_dir>/wsb_full/songbench_sel/audio_manifest.jsonl \
  --out /data/yue2-runs/rc5-q3o/rc5_1-full-192

# PER causal matrix (same audio, one factor per arm)
python scripts/rc5_per_lab.py --evaluator-root ... --manifest <16-id manifest> \
  --out <dir> --arm baseline --arm fp32:dtype=float32 --arm eager:attn=eager \
  --arm batch1:batch_size=1 --arm fp16:dtype=float16 --arm cpu32:dtype=float32,device=cpu,repeats=1
python scripts/rc5_asr_vllm_native.py --asr-root <Qwen3-ASR snapshot> --manifest ... --repeats 4
python scripts/rc5_asr_first_divergence.py --evaluator-root ... --ids <empty ids> --steps 12
```

Final scoreboard (selected-192, official protocol):

| Metric | Paper | Author SGLang | Historical W7900 | RC5.1 W7900 |
|---|---|---|---|---|
| SongBench GA | 6.7316 | 6.7146 | 6.738264 | **6.736891** |
| PER micro | 8.44% | 8.1471% | 17.762763% | **17.7699%** (frozen transformers arm) · **8.4488%** (vLLM-corrected arm, separate) |
| MuLan | 0.5068 | 0.49960 | 0.509166 | **0.509395** |
| AllMusicCaps | 0.4054 | 0.40825 | 0.405556 | **0.405181** |
| Q3O (0–5) | 4.68 | — | — | **4.393986** (ROCm-adapted; no equivalence claim) |

The corrected PER arm re-scores the SAME 384 audios through the vLLM decode
path; its selection differs on **60 changed prompts** (= 120 candidate-id
symmetric difference: 60 removed + 60 added — see
`reports/developer_reference/03_SELECTION_RECONCILIATION.json` for the four
explicit fields) and is published as a separate manifest — never mixed into
the frozen scoreboard. The corrected-selection five-metric scoreboard
(Scoreboard B) is published separately in
`reports/developer_reference/03_CORRECTED_SCOREBOARD.csv`.
