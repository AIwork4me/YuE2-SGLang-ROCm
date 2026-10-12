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
