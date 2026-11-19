# 08 — Developer reproduction guide (DRAFT — validation pending, M8.1)

**Status: DRAFT.** Commands are the ones actually used on the fresh image
(2026-11-14 → 2026-11-19 sessions, receipts in-repo). Fresh-clone
verification from a clean workspace has NOT yet been executed (M8.1 runs
after M2 completes); any divergence found will be corrected here, not papered
over.

## What you get (verified on W7900D / gfx1100, 48 GB, ROCm)

- Native PyTorch YuE2 inference (official implementation, `torch-eager`)
- SGLang serving of YuE2 with full-song generation via OpenAI-style API
- Official WildSongBench benchmark reproduction (SongBench/PER/MuLan/AMC)
- Single-GPU safety tooling (ownership lock, identity-verified server stop)

## 0. Hardware/software matrix (verified)

| Component | Verified value |
|---|---|
| GPU | AMD Radeon Pro W7900D (gfx1100, 48 GB — W7900-class; keep the exact variant name in publications) |
| Kernel driver | amdgpu 6.16.13 |
| Host ROCm userspace | 7.2.1 (preserved unmodified) |
| Env A (native torch) | torch 2.12.0+rocm7.14.1 wheels, transformers 5.17.0, numpy 2.3.5 |
| Env B (SGLang) | same torch + pinned SGLang source + triton 3.8.0 rocm build |
| Evaluator venv | frozen WildSongBench tree (manifest sha256 859e5225…) |
| RAM/disk | ≥64 GB RAM advised; ≥200 GB free on /data-class storage; /tmp must NOT hold benchmark data (small tmpfs) |

## 1. Environment build (fresh image, ~1–2 h unattended)

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git
cd YuE2-SGLang-ROCm && git checkout <pinned-release-branch>   # exact RC tag after merge
python3 scripts/check_environment.py
export YUE2_WORKSPACE=/data/yue2 && mkdir -p $YUE2_WORKSPACE/{logs,tmp,hf-cache} /data/yue2-runs
python3 scripts/download_pins.py --workspace $YUE2_WORKSPACE          # full pin-hash verification
bash scripts/campaign_ops/build_envA.sh                              # Env A
bash scripts/campaign_ops/evaluator_install.sh                       # Env C (metrics venv)
bash scripts/campaign_ops/build_envB.sh                              # Env B (before Arm B)
```

## 2. First complete song (native PyTorch, minutes)

```bash
source $YUE2_WORKSPACE/environments/yue2-torch/bin/activate
# minimal full-pipeline generation (official implementation, torch-eager):
python scripts/run_smoke_test.py --workspace $YUE2_WORKSPACE    # short smoke
# full-song example: see docs/QUICKSTART_W7900.md (exact, tested commands)
```

## 3. First complete song (SGLang serving)

```bash
bash scripts/serve_yue2_gfx1100.sh            # logs to $WS/logs/server_yue2_gfx1100.log
curl -s localhost:31000/health
# real music-generation acceptance (bounded, validates audio):
$YUE2_WORKSPACE/environments/yue2-gfx1100/bin/python \
  scripts/campaign_ops/armb_acceptance_request.py --server http://127.0.0.1:31000 \
  --out-dir /data/yue2/logs/armB_acceptance
# stop ONLY via verified identity (never pkill):
$YUE2_WORKSPACE/environments/yue2-gfx1100/bin/python scripts/server_identity.py \
  stop --receipt $YUE2_WORKSPACE/logs/armB_server_identity/server-identity.json --yes-path: see script help
```

## 4. Official WildSongBench reproduction (the real protocol)

```bash
# Arm A (native PyTorch, official torch-eager):
bash scripts/campaign_ops/run_armA_campaign.sh        # resume-safe; 384 candidates ≈ 2–3 days on W7900D
# Arm B (SGLang):
bash scripts/campaign_ops/run_armB_campaign.sh
# Serialized supervision of the whole chain (audit → four-metric scoring):
setsid nohup python3 scripts/campaign_ops/mission_chain.py \
  > $YUE2_WORKSPACE/logs/mission_chain_console2.log 2>&1 &
```

GPU discipline: exactly ONE heavy workload at a time (gpu_lock enforces
generation+scoring serialization; the known HIP illegal-memory-access
historical failure under sharing is avoided by policy, not claimed fixed).

## 5. Verify your results

```bash
$WS/environments/yue2-torch/bin/python scripts/verify_wsb_artifacts.py \
  --runs /data/yue2-runs/armA_wsb_full            # strict FULL/PARTIAL audit
$WS/environments/yue2-torch/bin/python scripts/verify_provenance.py \
  --runs /data/yue2-runs/armA_wsb_full            # per-candidate identity chain
```

## 6. Known limitations (honest list)

- PER on the ROCm evaluator sits ≈ +8 pp above the official reference across
  ALL stacks; root-cause investigation is open (see 03_PER_CAUSAL_ANALYSIS).
- Q3O NOT_TESTED on 48 GB (official judge memory) — no substitute attempted.
- AR-stage hang (~1/300 historical) mitigated by watchdog, NOT root-caused.
- Do not run evaluator and generator concurrently on the same GPU.
- Native `close()` releases little device memory in-process; one
  process per song is the supported pattern.

## 7. Fresh-clone verification checklist (M8.1 — TO RUN)

- [ ] clean workspace + pinned branch, all commands above re-executed
- [ ] model/dataset downloads hash-verified
- [ ] smoke + full-song generation
- [ ] audit FULL on a small pilot
- [ ] reproducible metric subset
- [ ] error handling: server killed mid-generation → journal resume-safe
- [ ] independent engineer (not the author of these scripts) executes
