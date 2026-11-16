# 02 INSTALLATION — Fresh Image (Phase P2)

Written: 2026-11-15T00:30Z (live document; evaluator venv step marked in-progress
until confirmed) · Machine: fresh W7900D image (see 00_ENVIRONMENT).

## Frozen contract

Source of truth: `configs/benchmark.lock.yaml` (frozen 2026-11-11). No version
substitutions beyond the disclosed DEV-1..DEV-4.

## Pinned assets (downloaded + SHA256-verified on THIS image)

`download_pins.py` receipt: `/data/yue2/logs/phase3_download_manifest.json` → **ALL PINS VERIFIED**

| Asset | Pin | Verified |
|---|---|---|
| WildSongBench dataset @ e361b85a (manifest, prompts, evaluator bundle, official code) | sha256 exact | ✅ |
| YuE2-3B @ 1a96eca (model.safetensors 1d55c42c…) | sha256 exact | ✅ |
| YuE2-Vae-legacy @ b54118f0 (b6d28362…) | sha256 exact | ✅ |
| SGLang PR #42106 tarball @ ced0ef7d (bfc912d2…) | sha256 exact | ✅ |

Evaluator assets (SongBench/MuLan/AMC/Qwen3-ASR models): fetched via
`fetch_eval_assets_hub.py` → **verify_assets OK (pinned hashes)** — receipt in
`/data/yue2/logs/fetch_eval_assets.log`.

## Environment A — official native PyTorch arm

```
/usr/bin/python3.12 -m venv /data/yue2/environments/yue2-torch
pip install --index-url https://download.pytorch.org/whl/rocm7.1 \
  torch==2.10.0+rocm7.1 torchaudio==2.10.0+rocm7.1
pip install transformers==4.57.6 safetensors==0.7.0 tiktoken==0.12.0 \
  numpy==2.2.6 soundfile==0.13.1 accelerate==1.13.0 huggingface-hub==0.36.2
pip install --no-deps models/YuE2-3B/yue2_infer-0.1.3-py3-none-any.whl
```

**Result: PASS** — `torch.cuda.is_available()`=True, torch 2.10.0+rocm7.1,
HIP 7.1.25424, transformers 4.57.6, yue2-infer 0.1.3 (wheel from pinned model
repo). Model load + weight-SHA live verification passed in API acceptance
(1d55c42c…/b6d28362… = frozen pins). HF cache warmed at pinned revisions for
offline runs. Installer: `/data/yue2/build_envA.sh` (retry-wrapped).

## Environment B — SGLang ROCm serving arm

```
scripts/setup_gfx1100_rocm7141.sh   # torch[device-gfx1100]==2.12.0+rocm7.14.1 etc.
# sglang tree: tarball @ ced0ef7d → git pristine → patches 0001-0005 + 0008
scripts/setup_sglang_gfx1100.sh     # deps + editable --no-deps --no-build-isolation
```

**Result: PASS** — GPU compute validation inside the setup script
(`SETUP OK: AMD Radeon Pro W7900D 2.12.0+rocm7.14.1`, fp32/fp16/bf16 matmuls
finite); patches applied against verified pristine tarball (git-applied clean);
`sglang import OK | torch 2.12.0+rocm7.14.1 | transformers 5.17.0` (matches
lock arm_b_stack). Torch wheel provenance: repo.amd.com whl-multi-arch with
`[device-gfx1100]` extra (plain wheels → hipErrorInvalidImage; handoff gotcha 3).

## Environment C — frozen WildSongBench evaluator

1. Tarball extracted (pristine sha 29310259… ✅) → git-committed pristine.
2. Patches applied **in the frozen order**, hash-verified at every stage
   (chain test `tests/test_evaluator_patches.py` reproduces this bit-exactly):
   - 0006+0007 (validation-branch patch, relative headers): wsb_eval → **6a4a53ed…** ✅,
     eval_worker → **569404c7…** ✅ (both = lock pins)
   - 0009 (cumulative @@-381 hunk): wsb_eval → **729fd597…** ✅ (= `patched_wsb_eval_sha256`)
   - **0010 formalized** (new in this mission): versioned patch
     `patches/0010-wsb-torch-eager-backend-allowlist.patch` + RCA README; applies
     clean on 0006+0009 → efb89042… recorded in evaluator `release.json` receipts
     (with per-stage sha table + per-patch disclosure).
3. Assets: fetched + verified (above).
4. venvs: `prepare --install` (uv-managed 3.12.11, eval + metrics roles from
   frozen locks) → **in progress at time of writing**; torch-family substitution
   under `WSB_ROCM_TORCH_OVERRIDE=1` follows per DEV-3.
5. Offline check: pending venv completion.

## Deviations on this image (all inherited, disclosed)

- DEV-1 torch-eager backend (Arm A) — unchanged.
- DEV-2 qwen_asr transformers ASR backend for PER — unchanged.
- DEV-3 torch-family substitution in evaluator venvs — unchanged.
- DEV-4 Q3O NOT TESTED (48 GB < 80 GB) — unchanged.
- NEW (disclosed): preinstalled host ROCm userspace 7.2.1 preserved (P0 rule);
  each env ships its own ROCm subset via wheels; driver 6.16.13 newer than all
  pins (supported direction); GPU marketing identity is W7900D (W7900-class).

## Inventory receipts

`evidence/publication/fresh_image/dependency_inventory/` (populated at env
finalization): pip freeze per environment + evaluator venv lock check output.
