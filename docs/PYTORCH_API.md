# PyTorch API (YuE2 on AMD ROCm)

The official `yue2-infer` package runs on gfx1100 with two verified entry
points. Status markers: ✅ executed on W7900 this mission; 🔬 documented,
verification scheduled.

## Backend selection (READ FIRST)

On ROCm, use `backend="torch-eager"` (or `--backend torch-eager` on the
official CLI). The graph-capture backend's varlen FlashAttention probe is
schema-only in the 0.1.3 wheel and the HIP kernel rejects `seqused_k`
(`docs/TROUBLESHOOTING.md`). YuE main already guards this upstream; the
pinned benchmark wheel needs the eager backend.

## Entry point 1 — official benchmark generator ✅

```bash
cd $YUE2_WORKSPACE/benchmark/WildSongBench
python code/generate.py --backend torch-eager --candidates 2 \
    --prompt-index 0 --output <fresh-dir> --cache-dir $YUE2_WORKSPACE/hf-cache
```

- Official seeds (`831001+i`, `831019+i`), request contract asserted against
  the frozen manifest (`SongRequest.text() == row["generation_prompt"]`),
  artifacts via `save_artifacts()` + official `verify_result`, model/VAE
  sha256 asserted at load.
- Resumable campaign wrapper with the same semantics:
  `scripts/run_wsb_torch.py` (write-once identity, verified resume-skip,
  quarantine-not-delete, disk thresholds).

## Entry point 2 — Python pipeline 🔬 (mirrors official docs/generation.md)

```python
from yue2 import YuE2Pipeline, SymbolicPlan

with YuE2Pipeline.from_pretrained(
        "m-a-p/YuE2-3B", revision="1a96eca6...", vae="m-a-p/YuE2-Vae-legacy",
        vae_revision="b54118f0...", backend="torch-eager",
        device="cuda:0", memory_budget_gib=24) as pipe:
    plan = pipe.plan(**request)          # symbolic planning (ABC)
    semantic = pipe.generate_semantic(plan)
    latents = pipe.synthesize(semantic)  # NAR (ODE, 32 steps, midpoint)
    audio = pipe.decode(latents)         # VAE (fp32, 48 kHz stereo)
```

- Staged API, artifact inspection, `cot` modes (`full`/`melody`/`off`),
  external ABC input, determinism: exercised in the Phase 3 acceptance
  window; wrappers: `examples/pytorch_generate.py`.
- Output contract: 48 kHz stereo FLAC (PCM_24), `result.json` integrity
  records, `truncated` flags.

## Verification envelopes (what we claim)

| Claim | Status |
|---|---|
| torch 2.10.0+rocm7.1 (official pin) works on gfx1100 | ✅ |
| torch-eager full song, official seeds, official artifacts | ✅ (pilot 2/2) |
| Developer-path staged API + examples | 🔬 scheduled |
| Numerical equivalence with CUDA graph backend | NOT CLAIMED (kernel-selection differences; disclosed DEV-1) |
