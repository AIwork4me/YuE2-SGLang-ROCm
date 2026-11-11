# 00 — Baseline Audit (Phase 0)

**Date:** 2026-11-11 · **Operator:** publication-readiness mission (fresh machine) · **Branch:** `feat/yue2-rocm-publication-readiness` (from `main` @ `4612c200`)

## 1. Baseline state

- `main` HEAD: `4612c200b2e09f1513a03ad479d601f373f8fb56` — matches the previously observed HEAD (2026-10-17 documentation commit).
- Working tree clean; single remote `origin = AIwork4me/YuE2-SGLang-ROCm`; push permission confirmed with `AIwork4me` token.
- Remote branches present: `main`, `docs/*` (2), `evidence/omni-http-gfx1100`, `fix/omni-evidence-acceptance-closure`, `handoff/*` (5), `validation/gfx1100-rocm7141`.
- No releases, no open PRs against `main` at audit time (last merged PR: #5).

## 2. Inherited historical evidence (preserved, not to be modified)

| Campaign | Hardware / stack | Location | Headline (selected-192) | ASR-capped samples (of 384) |
|---|---|---|---|---|
| H1 gfx1151 | Radeon 8060S 32G, SGLang @ ced0ef7d + patches | `evidence/` (top level) | PER 17.22%, SongBench GA 6.683 | 88 |
| H2 gfx1100 SGLang | W7900 48G, SGLang @ ced0ef7d + patches | `evidence/gfx1100/` | PER 17.01%, SongBench GA 6.736 | 120 |
| H3 gfx1100 Omni | W7900 48G, SGLang-Omni | branch `validation/gfx1100-rocm7141` @ `137ce40d` | PER 17.61%, SongBench GA 6.732 | 128 |

Official reference (WildSongBench README/results.md, YuE2 standard): SongBench 6.7316, MuLan 0.5068, AllMusicCaps 0.4054, Q3O 4.6819, PER 8.44%.

Historical evidence is distinguishable by path/branch and must remain byte-identical; new mission evidence is written under `evidence/publication/` and `reports/publication/` only.

## 3. Inherited engineering assets

- 31 scripts incl. hardened campaign driver (`run_wsb.py` v2), strict auditor (`verify_wsb_artifacts.py`), supervisor (`supervisor/complete_benchmark.py`), safe-stop tooling (`server_identity.py`), scoring scheduler v2.
- Patch series: SGLang ROCm guards 0001–0005, 0008; WSB evaluator ROCm substitutions 0006/0007/0009 (env-gated by `WSB_ROCM_TORCH_OVERRIDE=1`).
- 8 test files; CI runs only 2 of them plus syntax checks.
- Full protocol lock (`evidence/protocol_lock.json`): WSB @ e361b85a, model @ 1a96eca6, Vae-legacy @ b54118f0, SGLang PR #42106 head ced0ef7d, seeds `831001+i` / `831019+i`.

## 4. Known inherited defects (mission Issues A–F verified present)

- **A** `parents[2]` workspace resolution in `run_wsb.py`, `finalize_candidate.py`, `per_parity_study.py`, `verify_wsb_artifacts.py`, `tests/test_yue2_rocm_fallbacks.py`.
- **B** `run_official_eval.sh` default `WS=/home/amd/Desktop/YuE2`; venv-name coupling.
- **C** No lockfile at repo root; CUDA-vs-ROCm torch swap risk documented but not machine-checked.
- **D** CI covers 2/8 test files; `test_wsb_full_mode.py` skips without gitignored pinned manifest.
- **E** `download_pins.py` `tarfile.extractall()` without `filter="data"`; machine paths inside `0009` patch headers.
- **F** Historical evidence retention — currently satisfied; must stay so.

## 5. Fresh-machine environment verdict

Physical W7900 verified (gfx1100, 48 GiB, ROCk 6.16.13 driver, ROCm 7.2.1 userspace in `/opt/rocm`, one GPU granted to this container). PyTorch ROCm compute, bf16 matmul and SDPA functional in the pre-provisioned lab venv (torch 2.9.1+hip7.2). Network: GitHub (git + API), huggingface.co, hf-mirror.com, repo.amd.com, download.pytorch.org reachable via egress proxy; `raw.githubusercontent.com` and PyPI JSON API blocked — workflows must use `git clone`/GitHub contents API and pip indexes.

Storage: `/workspace` 93 G free (repo, tools); `/data/yue2` created on the 1.8 T overlay for models/environments/runs (write-tested).

## 6. Upstream state snapshot (2026-11-11, token-verified)

- sgl-project/sglang#42106 "Add yue2": **OPEN**, head `ced0ef7d` (unchanged since the frozen campaign; updated 2026-11-02).
- sgl-project/sglang-omni#2540 "Add yue2 [Port from SGLang]": **OPEN**, head `85ae4b73`.
- yiakwy fork PRs #1 (omni ROCm) and #1 (benchmark-fork ROCm): **OPEN**.
- multimodal-art-projection/YuE main @ `1116bea7` (2026-11-01); releases: `yue2-music-v1.2.0` (2026-09-25, agent skill) and `yue2-v0.1.6` (2026-09-09). Official hardware.md documents experimental AMD ROCm path: "Eager AR with public SDPA; no NVIDIA private attention operators", torch pin 2.10.0 (non-macOS), ROCm wheel index rocm7.1.
- m-a-p/YuE2-3B repo moved 1a96eca6 → 8f24312f (2026-10-06): file listing identical for `model.safetensors` (7,261,441,640 B), `modeling_yue2.py`, `config.json`, wheels; README grew 19,050 → 21,898 B. **Weights appear unchanged; SHA256 to be re-verified at download.**
- m-a-p/YuE2-Vae @ 152733a1, YuE2-Vae-legacy @ d0585a9c (current heads; frozen revisions remain fetchable).
- m-a-p/WildSongBench @ e361b85a: **unchanged** — frozen manifest remains the current release.

## 7. Official benchmark semantics (from WSB README + results.md, verified 2026-11-11)

- Generation: `code/generate.py --candidates 2 --backend torch` (native PyTorch is the official generation path), inference version **0.1.3** retained ("model weights and numerical inference code are unchanged"), scoring VAE = **YuE2-Vae-legacy**.
- Seeds `831001+i`, `831019+i` applied to planning, semantic and acoustic stages.
- PER: 4 ASR passes per candidate, **candidate PER = lowest of the 4 passes**; per prompt the **lower-PER candidate** is selected and used for **every** metric; capped ASR outputs **retained**.
- Official fresh-runs: SongBench 6.73 (H800) / 6.74 (RTX 4090) vs 6.7316 paper; MuLan/AMC match within 1e-6 on original audio; Q3O 4.69–4.71 vs 4.68 "equality to two decimals remains unresolved" — even the authors treat Q3O as not exactly settled.
- Evaluator weights ~83 GB for all metrics; **Q3O requires an 80 GB GPU** → W7900 (48 GB) is expected NOT TESTED for Q3O, consistent with prior campaigns.

## 8. Initial GO/NO-GO

**GO** for environment, hardening, developer-path, serving and documentation phases. The Phase 5/7 quality-parity publication gate starts **BLOCKED**: historical ROCm PER (17.0–17.6% selected) vs official 8.44% lacks a proven root cause; the leading hypothesis (evaluator ASR backend substitution / output capping, evidenced by 88/120/128 capped samples) must be tested against the official evaluator semantics before any parity claim.
