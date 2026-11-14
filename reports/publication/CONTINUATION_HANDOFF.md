# CONTINUATION HANDOFF — YuE2-ROCm publication-readiness mission

**Written:** 2026-11-14T02:10Z · **Author:** mission executor session 1
**For:** the continuation session on the reopened mirror image.
**Repo state:** branch `feat/yue2-rocm-publication-readiness` (all work pushed;
this file is part of the final push of session 1).

---

## 1. MISSION STATE AT HANDOFF (2026-11-14 ~02:00Z)

| Item | State | Where |
|---|---|---|
| Phases 0–2 (preflight, upstream intel, hardening) | ✅ COMPLETE | reports/publication/00_*, 01_*, 02_* |
| Arm B (SGLang) 384-candidate campaign | ✅ COMPLETE — strict audit **FULL** (384/384 verified, identity 384/384, 5 truncated-but-valid, 0 problems) | evidence/publication/armB_campaign/ + /data/yue2-runs/armB_wsb_full |
| Arm B PER+SongBench scoring (solo, official) | 🔄 RUNNING (started 01:56Z Nov 14; first attempt had a concurrent-mode HIP illegal-memory-access crash at prompts 164+, partial 328-receipt run preserved at scores_concurrent_partial/ for determinism comparison) | /data/yue2-runs/armB_wsb_full/scores/ + /data/yue2/logs/armB_solo2.log |
| Arm B mulan+amc | ⏸ QUEUED (run AFTER per,songbench finishes; command in §4.3) | — |
| Arm A (official PyTorch torch-eager) campaign | ⏸ PAUSED at **66/384** (resume-safe; signal-stopped to give Arm B scoring the GPU solo) | /data/yue2-runs/armA_wsb_full + /data/yue2/logs/armA_campaign3.log |
| Arm A scoring | ⏸ queued after Arm A completes | — |
| Phase 5 PER RCA | Pilot evidence strong (official-range PER on good audio; historical gap is tail-driven); full fresh-campaign tail analysis pending Arm B per_song.jsonl | evidence/publication/per_rca/armA_pilot_per.json |
| Phase 9 audits | ✅ done; **LQ-1** (historical per_song.jsonl contains reference_lyrics → publication decision needed from owner) | reports/publication/09_* |
| CI on GitHub | ✅ green (commit 89875d8b+) | actions |
| Q3O | NOT TESTED (48GB < 80GB requirement) — never claim it | docs/KNOWN_LIMITATIONS.md |

## 2. FIRST: figure out what the mirror kept

```bash
ls /data/yue2 /data/yue2-runs /workspace/YuE2-SGLang-ROCm 2>/dev/null
```
- If `/data/yue2` **exists** (image snapshot): jump to §3.
- If `/data` is **gone** (fresh container): reconstruct the workspace with §5
  (≈1–2 h, all automated), then `git clone` the repo and continue. All
  evidence that matters for publication is in the GIT REPO (pushed), not in
  /data. Audio artifacts in /data/yue2-runs are regenerable (seeds/protocol
  pinned) but NOT re-pushed (too large for git).

## 3. LIVE PROCESSES (if the mirror kept the machine state)

Check what survived:
```bash
ps aux | grep -E "wsb_eval|run_wsb_torch|sglang serve" | grep -v grep
tail -5 /data/yue2/logs/armB_solo2.log
tail -2 /data/yue2-runs/armB_wsb_full/scores/per.log 2>/dev/null
```
- The solo scoring (pid family of `/data/yue2/benchmark/WildSongBench/wsb_metrics/.venvs/*/bin/python ... wsb_eval.py score`) is the ONLY GPU job that should run. **Do NOT run anything else on the GPU concurrently** (see §6 G-7: the ASR crashes with HIP illegal-memory-access when the GPU is shared during long 4096-token decodes).
- Scoring progress: `grep -c ": complete" /data/yue2-runs/armB_wsb_full/scores/per.log`
- Expected solo duration: per ≈ 8–12 h (long-song tail is slowest), songbench ≈ 4 h after that.

### 3.1 If the scoring process died mid-run
The evaluator has NO resume for a partially scored output dir. If per_song.jsonl
has <384 metric rows and no process is running:
```bash
mv /data/yue2-runs/armB_wsb_full/scores /data/yue2-runs/armB_wsb_full/scores_partial_<ts>
setsid nohup /data/yue2/run_armB_solo_scoring.sh > /data/yue2/logs/armB_solo_<ts>.log 2>&1 < /dev/null &
```
(The .lock is flock-based and releases automatically when the process dies.)

## 4. COMMAND SEQUENCE FOR THE REMAINING MISSION (in order)

### 4.1 Wait for Arm B per,songbench to finish (exit 0 expected)
```bash
grep -E "Finished per|Finished songbench" /data/yue2/logs/armB_solo2.log
# then summarize:
python3 scripts/summarize_campaign.py --run /data/yue2-runs/armB_wsb_full \
  --label "Arm B (SGLang, W7900, fresh 2026-11)" \
  --evidence-out evidence/publication/armB_campaign/
```

### 4.2 Then mulan + allmusiccaps (reuses PER selection)
```bash
cat > /data/yue2/run_armB_mulan_amc.sh <<'EOF'
#!/usr/bin/env bash
cd /data/yue2/benchmark/WildSongBench
export WSB_ROCM_TORCH_OVERRIDE=1 HF_HOME=/data/yue2/hf-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/data/tmp
exec /data/yue2/benchmark/WildSongBench/wsb_metrics/.venvs/metrics/bin/python wsb_metrics/wsb_eval.py score \
  --input /data/yue2-runs/armB_wsb_full/evaluation_inputs.jsonl \
  --per-results /data/yue2-runs/armB_wsb_full/scores/per_song.jsonl \
  --output /data/yue2-runs/armB_wsb_full/additional \
  --mode standard --metrics mulan,allmusiccaps
EOF
chmod +x /data/yue2/run_armB_mulan_amc.sh
setsid nohup /data/yue2/run_armB_mulan_amc.sh > /data/yue2/logs/armB_mulan_amc.log 2>&1 < /dev/null &
```

### 4.3 Resume Arm A campaign (SOLO — after 4.2 finishes)
```bash
cd /workspace/YuE2-SGLang-ROCm
YUE2_WORKSPACE=/data/yue2 HF_HOME=/data/yue2/hf-cache HF_HUB_CACHE=/data/yue2/hf-cache/hub \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/data/tmp \
setsid nohup /data/yue2/environments/yue2-torch/bin/python scripts/run_wsb_torch.py \
  --runs /data/yue2-runs/armA_wsb_full --run-id armA_full_20261113 \
  --cache-dir /data/yue2/hf-cache > /data/yue2/logs/armA_campaign4.log 2>&1 < /dev/null &
```
- Resume verifies each completed bundle and skips it (66 already done, ~7–11 min
  per new candidate solo → ~40–50 h for the remaining 318).
- Stall guard (optional but recommended): the old chain script
  /data/yue2/campaign_chain.sh has a 45-min stall-restart pattern for the SGLANG
  arm only; for Arm A, torch-eager was hang-free so far — a simple liveness
  cron is enough.

### 4.4 Arm A audit + scoring (after 4.3 completes)
```bash
# strict audit (must be FULL):
YUE2_WORKSPACE=/data/yue2 /data/yue2/environments/yue2-torch/bin/python \
  scripts/verify_wsb_artifacts.py --runs /data/yue2-runs/armA_wsb_full --mode full
# scoring: same two commands as Arm B but --input armA evaluation_inputs and
# output dirs under /data/yue2-runs/armA_wsb_full/scores|additional
# (mirror §4.1/4.2 exactly; evaluator env vars identical)
```

### 4.5 Analysis + reports (CPU, can overlap with 4.3)
- `scripts/summarize_campaign.py` for both arms; fill docs/RESULTS.md;
  compare vs official (acceptance thresholds frozen in
  configs/benchmark.lock.yaml §deviations/§metrics_run — SongBench Δ≤0.05,
  MuLan Δ≤0.01, AMC Δ≤0.01, PER Δ≤2pp under comparable protocol, CIs via the
  summarizer's bootstrap).
- Determinism comparison (Phase 5 bonus): compare
  scores_concurrent_partial/per_song.jsonl vs solo scores/per_song.jsonl for
  the 328 shared candidates (bit-identical per/edits or not).
- Update reports/publication/05_PER_ROOT_CAUSE.md (skeleton data: pilot json +
  the fresh Arm B tail decomposition from the summarizer).
- Reviews A/B (Phase 10) + gate ledger final statuses + final Chinese report.

## 5. RECONSTRUCTING THE WORKSPACE FROM A FRESH MACHINE (~1–2 h)

```bash
git clone https://github.com/AIwork4me/YuE2-SGLang-ROCm.git /workspace/YuE2-SGLang-ROCm
cd /workspace/YuE2-SGLang-ROCm && git checkout feat/yue2-rocm-publication-readiness
python3 scripts/check_environment.py
export YUE2_WORKSPACE=/data/yue2
python3 scripts/download_pins.py --workspace $YUE2_WORKSPACE     # ~16 GB, SHA256-verified
mkdir -p $YUE2_WORKSPACE/hf-cache /data/tmp /data/yue2-runs

# Arm A venv (official stack):
python3.12 -m venv $YUE2_WORKSPACE/environments/yue2-torch
TMPDIR=/data/tmp $YUE2_WORKSPACE/environments/yue2-torch/bin/pip install \
  --index-url https://download.pytorch.org/whl/rocm7.1 "torch==2.10.0+rocm7.1" "torchaudio==2.10.0+rocm7.1"
TMPDIR=/data/tmp $YUE2_WORKSPACE/environments/yue2-torch/bin/pip install \
  "transformers==4.57.6" "safetensors==0.7.0" "tiktoken==0.12.0" "numpy==2.2.6" \
  "soundfile==0.13.1" "accelerate==1.13.0" "huggingface-hub==0.36.2"
TMPDIR=/data/tmp $YUE2_WORKSPACE/environments/yue2-torch/bin/pip install --no-deps \
  $YUE2_WORKSPACE/models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl
# warm the HF cache (from_pretrained needs it in OFFLINE mode): run the Arm A
# pilot once with --prompt-index 0 WITHOUT offline env first, or
# snapshot_download model+vae at pinned revisions into /data/yue2/hf-cache.

# Arm B venv:
bash scripts/setup_gfx1100_rocm7141.sh          # torch 2.12.0+rocm7.14.1
cd $YUE2_WORKSPACE/upstream && tar xzf sglang-ced0ef7d*.tar.gz && mv sglang-ced0ef7d-* sglang
cd sglang && git init && git add -A && git commit -qm pristine && \
  git apply /workspace/YuE2-SGLang-ROCm/patches/0001-0005-rocm-compat.patch && \
  git apply /workspace/YuE2-SGLang-ROCm/patches/0008-kvcacheio-import-guards.patch
YUE2_WORKSPACE=$YUE2_WORKSPACE bash /workspace/YuE2-SGLang-ROCm/scripts/setup_sglang_gfx1100.sh

# Evaluator (frozen + patches, exact):
cd /data/yue2/benchmark/WildSongBench
tar --no-same-owner -xzf evaluation/wsb_metrics.tar.gz      # -> ./wsb_metrics at WSB ROOT
cd wsb_metrics
#   apply 0006+0007 from branch validation/gfx1100-rocm7141:patches/0006-0007-wsb-evaluator-rocm.patch
#   (headers rewritten to relative; verified to reproduce wsb_eval.py sha 6a4a53ed bit-identically),
#   then the 0009 hunk from patches/0006-0007-0009-wsb-evaluator-rocm.patch (offset ok),
#   then the 0010 backend-allowlist one-liner:
python3 - <<'PY'
from pathlib import Path
p = Path('wsb_eval.py'); t = p.read_text()
old = "    if config.get('backend') not in {'torch', 'vllm'}:"
new = "    if config.get('backend') not in {'torch', 'vllm', 'torch-eager'}:"
assert old in t; p.write_text(t.replace(old, new, 1)); print('0010 applied')
PY
#   update release.json hashes for wsb_eval.py + src/mot_infer/eval_worker.py
#   (see the disclosure dict in the current /data tree's release.json for the exact format)
# venvs + weights:
YUE2_WORKSPACE=/data/yue2 $OLD_VENV_PYTHON wsb_metrics/wsb_eval.py prepare --metrics per,songbench,mulan,allmusiccaps --install
/data/yue2/benchmark/WildSongBench/wsb_metrics/bin/uv pip install --python .venvs/metrics/bin/python \
  --index-url https://repo.amd.com/rocm/whl-multi-arch/ \
  "torch[device-gfx1100]==2.10.0+rocm7.14.1" "torchaudio[device-gfx1100]==2.10.0+rocm7.14.1" "torchvision[device-gfx1100]==0.25.0+rocm7.14.1"
#   (same for .venvs/eval; NOTE the [device-gfx1100] EXTRA — plain wheels give hipErrorInvalidImage)
/data/yue2/environments/yue2-torch/bin/python /workspace/YuE2-SGLang-ROCm/scripts/fetch_eval_assets_hub.py
ln -sfn /data/yue2/benchmark/WildSongBench/wsb_metrics /data/yue2/benchmark/wsb_metrics   # layout compat
```
Layout on this machine (IMPORTANT — scripts probe several, but keep this):
`/data/yue2/{models,environments,upstream,benchmark/WildSongBench/{wsb_metrics(.venvs,evaluation_models)},hf-cache}`
Runs: `/data/yue2-runs/{armA_wsb_full, armB_wsb_full, armA_pilot0}`.

## 6. GOTCHAS LEARNED THE HARD WAY (session 1) — read before acting

1. **GPU is strictly single-tenant for the ASR evaluator.** Long 4096-token
   greedy decodes hit `HIP error: an illegal memory access` when another job
   shares the GPU (Arm A + ASR crashed at prompts 164+). NEVER overlap the
   evaluator with generation. Small-model metrics (probe: mulan-class) seemed
   fine, but after the crash we policy-serialized ALL GPU work.
2. `pip install -e` on sglang WITHOUT `--no-build-isolation` pulls CUDA torch
   into the build env (fails on /tmp space; guard your torch version after).
3. AMD torch wheels need the **device extra** (`torch[device-gfx1100]`) — plain
   wheels → `hipErrorInvalidImage`.
4. `/tmp` is 4 GB tmpfs — always `TMPDIR=/data/tmp`.
5. Egress proxy 503s intermittently (git push, big downloads): retry; use
   `huggingface_hub`-based fetcher for assets; NEVER downgrade to http.
6. `pkill -f` patterns can match your own shell command line — use PIDs.
7. Evaluator `--mode standard` refuses to summarize incomplete runs (by design);
   per crashes leave no resume → restart clean dir (§3.1).
8. Arm A runs need `HF_HUB_OFFLINE=1` + warmed cache
   (/data/yue2/hf-cache) or hub metadata fetches time out through the proxy.
9. SGLang server can hang in AR stage (~1/300 candidates, RCA-10): symptoms
   GPU 0% + VRAM held; the fix is a full server restart + driver resume
   (run_wsb.py resumes verified-complete candidates automatically).
10. `run_wsb.py --resume` requires the SAME `--run-id` (write-once identity).
11. Scoring env vars that must accompany every wsb_eval invocation:
    `WSB_ROCM_TORCH_OVERRIDE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    TMPDIR=/data/tmp HF_HOME=/data/yue2/hf-cache`.
12. The scoring launcher must `setsid nohup ... < /dev/null &` detached from
    the interactive shell (a session kill took one down — §3 covers restart).

## 7. PUBLICATION BLOCKERS UNRELATED TO GPU (for the owner)

- **LQ-1**: historical `evidence/per_song.jsonl` embeds `reference_lyrics`
  (copyrighted). Decision needed: redacted republication vs keep (repo
  currently private-ish). Blocks blog publication, not the campaigns.
- **LQ-2**: demo-audio attribution wording with YuE2 authors.
- Upstream submissions (U-2 evaluator allowlist; optional author note on
  0.1.3-wheel ROCm backend) wait for owner approval. NEVER submit without it.

## 8. ARTIFACT MAP

- Git (durable, pushed): all reports/publication/*, evidence/publication/*
  (receipts, hashes, manifests — no audio/lyrics from NEW runs),
  docs, scripts, configs, patches, tests, CI.
- /data (machine): audio (9 GB armB, growing armA), scores dirs, all logs,
  venvs, evaluator tree with patched files + .venvs + weights, hf-cache.
- If /data is lost: Arm B audio is regenerable only by re-running the campaign
  (protocol-pinned); scoring inputs would need that regeneration. The AUDITED
  evidence + per-candidate sha256 manifest for Arm B are safely in git.
