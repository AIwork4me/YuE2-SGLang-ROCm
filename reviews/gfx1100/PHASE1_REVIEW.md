# PHASE 1 Independent Verification Review — gfx1100 / W7900

**Reviewer role:** independent (did not author Phase 0/1 work; every claim below re-executed on-host 2026-10-11 ~22:3x UTC)
**Artifacts under review:** `reports/gfx1100/PHASE1_INSTALL.md`, `evidence/gfx1100/phase1_validation.log`, `evidence/gfx1100/phase1_torch_environment.json`, `scripts/setup_gfx1100_rocm7141.sh`, `scripts/validate_torch_gfx1100.sh`, plus Phase 0 fix-back (`PHASE0_PREFLIGHT.md`, `environment.json`, `check_environment.py`)

## VERDICT — GATE 1: **PASS**

| Gate criterion | Independent result |
|---|---|
| Exact versions installed | `torch 2.12.0+rocm7.14.1` / `torchvision 0.27.0+rocm7.14.1` / `torchaudio 2.11.0+rocm7.14.1`, `hip=7.14.60850`, `cuda=None` — re-executed in the venv, exact match |
| GPU compute succeeds | bf16+fp32+fp16 GEMM 1024² executed by reviewer on `cuda`; all finite; additionally checked against float64 CPU reference (max err 2.8e-4 fp32, ~3–4e-1 bf16/fp16 at scale ~155 — expected rounding). Device `AMD Radeon Pro W7900D`, `gcnArchName='gfx1100'`, 49136 MB |
| No CUDA substitutions | `pip freeze` has **zero** nvidia-*/cuda*/cublas/cudnn/nccl/flashinfer entries; no such dirs in site-packages; `importlib.find_spec('flashinfer')` → None |

PASS is qualified by findings F1/F2 below (reproducibility + evidence durability), neither of which invalidates the gate criteria themselves.

## Findings table

| # | Severity | Finding | Evidence (executed by reviewer) |
|---|---|---|---|
| 1 | **P1** | `setup_gfx1100_rocm7141.sh` **cannot perform a fresh install**: the guard maps `ImportError` (no torch yet) to exit 2 → bash `if` fails → "non-conforming torch" FATAL. The echo text "(or absent)" shows intent, the code contradicts it. The "idempotent installer / reproducer" only re-validates an already-conforming venv | Ran `YUE2_VENV=/tmp/opencode/fresh_venv_test bash setup_gfx1100_rocm7141.sh` → `[2/5] FATAL … refusing to overwrite`, exit 1, before any pip/network action |
| 2 | **P1** | Phase 0 carryover (predecessor required action 2, P1): **nothing committed or pushed**. `git status`: `evidence/gfx1100/`, `reports/gfx1100/`, `reviews/gfx1100/`, `scripts/api_git.py`, `scripts/check_environment.py` all untracked; `.gitignore` modified-unstaged. Remote `validation/gfx1100-rocm7141` SHA = `main` SHA = `2b4cacd6…`. All gfx1100 evidence exists only on this disk | `git status --short`; `gh api …/git/ref/heads/validation%2Fgfx1100-rocm7141` → `2b4cacd6efd0f15959a1142d81907e6fb11a85dc` = `main` |
| 3 | **P2** | §4 "Config A vs B" **mischaracterizes runtime loading**. `torch/__init__.py:157-163` unconditionally calls `_rocm_init.initialize()` → `rocm_sdk.initialize_process(preload_shortnames=[amdhip64, rocblas-math-stack…], check_version='7.14.1')`. Plain `import torch` (verified under `env -i`) already puts `rocm_sdk` in `sys.modules` and maps 53 unique venv `_rocm_sdk_` libs with exactly **1** unique host lib. There is no runtime path where host 7.2.1 math libs serve compute in this venv. The "A: 25 host libs / GEMMs PASS" row is an **ldd static-resolution artifact** (the log's own section header "which ROCm userspace actually loads" is ldd output), not a measured runtime configuration. The truth is *stronger* than claimed (venv-consistency is automatic), but the dichotomy and the A-row's "all GEMMs PASS on 7.2.1 host libs" are unsupported | Read `torch/__init__.py` + `torch/_rocm_init.py`; `env -i … python -c "import torch, sys; …"` → `rocm_sdk in sys.modules: True`, maps: 53 unique `_rocm_sdk_` libs, 1 unique `/opt/rocm` lib; `ldd _C.so` reproduces 9 venv / 25 host exactly |
| 4 | **P2** | §4 Config-B numbers: **"375 venv libs" appears in no evidence file** (grep over `evidence/` and `logs/`) and is not reproducible — I measure 313 maps lines containing `_rocm_sdk_` (373 including `torch/lib` lines). "5 residual host libs" = 5 *maps lines* of **one** library, and the explanation "hsa-amd-aqlprofile extras **not shipped in venv**" is false: `_rocm_sdk_core/lib/libhsa-amd-aqlprofile64.so.1` exists in the venv. The residual host load is real (verified) but the stated cause is wrong — see F5 | `grep -rn 375 evidence/ logs/` → nothing; maps count 313/53; `find _rocm_sdk_*/lib -name '*aqlprofile*'` → 1 hit |
| 5 | **P2** | "No `LD_LIBRARY_PATH` is set at any point" is **overstated**: neither script sets it (verified), but the container login environment presets `LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/lib:` (not from `/etc/profile*`, `.bashrc`, `.profile` — inherited from container invocation), so any non-sanitized process, including presumably the original validation runs, had it. It is the likely reason the aqlprofile soname resolves to host despite the venv copy. Compute still selects the venv stack regardless (all my GEMM/maps tests ran with the ambient var set and venv won) | `echo $LD_LIBRARY_PATH`; grep of profile files → no hits |
| 6 | NOTE | `setup_gfx1100_rocm7141.sh:36` typo `YUE2_VENC` (should be `YUE2_VENV`) — message-only | read |
| 7 | NOTE | `logs/phase1_pip_freeze.txt` contains `pip==26.2.1` but reviewer's `pip freeze` does not: recorded via `pip list --format=freeze` (includes pip) vs `pip freeze` (excludes self). Content otherwise identical; no audit concern | diff of both |
| 8 | NOTE | Network flakiness corroborates the corrected "intermittent github.com" wording: committed `environment.json` (22:29:23Z) recorded github.com → 206; reviewer's recheck (22:33:31Z) got 3× timeout on github.com and codeload while repo.amd.com/pypi/hf-mirror/api stayed 206 | both JSONs compared |

## Claims VERIFIED by independent execution

| Claim (source) | Measured | Match |
|---|---|---|
| versions / hip / cuda (§2) | identical to log/json | ✓ |
| Device W7900D, gfx1100, 49136 MB, L2 6 MB, pci_bus_id 195 (§2) | reproduced via `get_device_properties` | ✓ |
| FP32/FP16/BF16 GEMM finite (§2) | reproduced + fp64-reference correctness check | ✓ (stronger) |
| Extended: 50-launch 39.45 ms, peak 138,023,936 B, cudnn True (§3) | present in log; consistent with my runs (launch path healthy) | ✓ |
| Mission command verbatim in setup script (§1) | lines 42-46 character-identical incl. extras `torch[device-gfx1100]`, `torchvision[device-gfx1100]`, bare `torchaudio`, `--index-url https://repo.amd.com/rocm/whl-multi-arch/` | ✓ |
| No LD_LIBRARY_PATH in scripts (§4) | `grep` both scripts → none | ✓ |
| log "venv-provided ROCm libs: 9, host-provided: 25" | reproduced via `ldd torch/_C…so` → 9/25 exactly | ✓ (but it is ldd, see F3) |
| Config-B mechanism usable & compute-clean (§4) | `import rocm_sdk; rocm_sdk.initialize_process(); import torch` → GEMMs pass; maps: 313 `_rocm_sdk_` lines vs 5 `/opt/rocm` lines, sole host lib `libhsa-amd-aqlprofile64.so.1.0.70201` | ✓ (qualitatively; numbers differ, F4) |
| Freeze clean of nvidia/cuda/flashinfer (§5) | grep freeze / site-packages dirs / find_spec → none | ✓ |
| venv-local ROCm 7.14.1 userspace installed (§4) | `rocm-sdk-core/libraries/device-gfx1100==7.14.1`, `_rocm_sdk_*/lib` trees present | ✓ |
| W7900D = China SKU of same gfx1100 silicon, PCI 1002:744b (§2 note) | lspci shows `[1002:744b]`; honest disclosure | ✓ |

## Executed commands + outputs (condensed)

```
source environments/yue2-gfx1100/bin/activate
python -c versions        → torch 2.12.0+rocm7.14.1 / 0.27.0+rocm7.14.1 / 2.11.0+rocm7.14.1
                             hip 7.14.60850 / cuda None / available True
GEMM bf16/fp32/fp16 1024²  → all finite; max_abs_err 4.98e-1 / 2.80e-4 / 6.19e-2 (fp64 ref scale ~155)
                             device AMD Radeon Pro W7900D, gfx1100, 49136 MB
config B: rocm_sdk.initialize_process(); import torch; GEMM; /proc/self/maps
                          → 1038 lines: _rocm_sdk_ 313, /opt/rocm 5 (all libhsa-amd-aqlprofile64.so.1.0.70201),
                             torch/lib 60; unique libs: 53 venv-sdk / 1 host / 11 torch
config A (env -i, plain import torch) → rocm_sdk in sys.modules True (torch/__init__.py:158-162 auto-preload);
                             same 313/53/1 profile ⇒ no runtime "host-7.2.1" config exists (F3)
pip freeze                → no nvidia/cuda/flashinfer (grep NONE); site-packages dirs NONE; find_spec None
ldd torch/_C…so          → venv 9 / host 25 (matches log line 79 exactly)
grep evidence+logs '375'  → NOT FOUND (F4); initialize_process NOT in evidence (F4)
grep LD_LIBRARY_PATH scripts → none; ambient shell: /opt/rocm/lib:/usr/local/lib: (F5)
YUE2_VENV=/tmp/opencode/fresh_venv_test bash setup_gfx1100_rocm7141.sh
                          → [2/5] FATAL non-conforming (fresh venv!) exit 1 (F1); typo YUE2_VENC (F6)
python3 scripts/check_environment.py --json /tmp/opencode/p0_recheck.json
                          → exit 0, BLOCKERS none, WARNINGS none, JSON written (captured 22:33:31Z)
ffmpeg -version           → 6.1.1-3ubuntu5
git config --global -l    → insteadOf: git@github.com:→http AND https://github.com/→http/ (F6-P0 fixed)
ls evidence-repo/scripts  → api_git.py present (11617 B) + check_environment.py (9093 B)
find _rocm_sdk_*/lib -name '*aqlprofile*' → 1 (venv copy EXISTS; contradicts §4 wording, F4)
git status/ls-files (evidence-repo) → all gfx1100 artifacts untracked; .gitignore unstaged (F2)
gh api refs validation/gfx1100-rocm7141 & main → both 2b4cacd6efd0f15959a1142d81907e6fb11a85dc (F2)
```

## Required actions

1. **(P1)** Fix the guard: `ImportError` must take the *install* path (exit 0 or restructure), keeping exit≠0 only for a present-but-wrong torch; fix `YUE2_VENC` typo; re-test fresh-venv path end-to-end.
2. **(P1)** Commit and push all gfx1100 artifacts (reports/evidence/reviews/scripts, `.gitignore`) to `validation/gfx1100-rocm7141` — same as predecessor action 2, still open.
3. **(P2)** Rewrite §4: replace the A/B dichotomy with the actual mechanism (torch auto-preload via `_rocm_init`; explicit `rocm_sdk.initialize_process()` is harmless and still correct for serving launchers), label the 25/9 numbers as `ldd` static resolution, re-derive or drop "375", correct "5 residual host libs" to "5 maps segments of 1 library", and delete the false "not shipped in venv" aqlprofile explanation.
4. **(P2)** Disclose ambient `LD_LIBRARY_PATH=/opt/rocm/lib` and consider `unset`ing it in serving launchers.

---

# PHASE0 RE-CHECK (fix-back verification)

Predecessor review: `reviews/gfx1100/PHASE0_REVIEW.md` (verdict PARTIAL, 2×P1 + 7×P2).

## Fixed — verified by reviewer execution

| # (orig) | Was | Now | Verification |
|---|---|---|---|
| F1 (P1) | `evidence/gfx1100/environment.json` missing (only gfx1151 clone present) | exists, regenerated | file present, `captured_at 2026-10-11T22:29:23Z`, host `j-4s7l75qngxo2pvww4zkw6ytsnu`, gfx1100, kernel 6.8.0-79-generic, blockers `[]` — live-host fields re-checked (amdgpu 6.16.13, /opt/rocm 7.2.1, kfd root:993 660, renderD134) all consistent |
| F2 (P1) | `scripts/check_environment.py` missing | exists in `evidence-repo/scripts/` | ran `python3 scripts/check_environment.py --json /tmp/opencode/p0_recheck.json` → **exit 0**, BLOCKERS none, WARNINGS none; code audited: failure paths append BLOCKERS → exit 1; network probed 3× with per-attempt recording |
| F3 (P2) | github.com claimed "blocked" | "intermittent (per-connection outcomes vary)" | corroborated: 22:29 capture = 206, my 22:33 recheck = 3× timeout on github.com/codeload while api/pypi/repo.amd.com/hf-mirror stayed 206 |
| F5 (P2) | ffmpeg "7.1.1" | "ffmpeg 6.1.1" | `ffmpeg -version` → 6.1.1-3ubuntu5 ✓ |
| F6 (P2) | insteadOf description didn't match config | config now matches description | global config now has **both** `git@github.com:`→`http://github.com/` **and** `https://github.com/`→`http://github.com/` rewrites (they added the rewrite; remote URL `http://github.com/AIwork4me/…`) |
| F7 (P2) | HF endpoint claim contradicted manifest | §3.3 documents `HF_ENDPOINT=https://hf-mirror.com` + full-SHA256 pinning condition | report wording matches environment.json (`huggingface.co` 3×FAIL, `hf-mirror.com` 206) |
| F8 (P2) | `scripts/api_git.py` "mirror" false | file present | `evidence-repo/scripts/api_git.py` (11617 B) exists |
| F10/F11/P2s | 8-GPU chassis / W7900D / apt-403 / gitignore | all corrected | §1 table discloses 8×1002:744b + single mapped c3:00.0 + W7900D SKU note; §2 says apt 403; `.gitignore` now carries `models/ runs/ environments/ upstream/ benchmark/ scratch/ *.npy …` |

## Still open

| # (orig) | Item | Status |
|---|---|---|
| F9 / required action 2 (P1) | Commit & push gfx1100 deliverables to `validation/gfx1100-rocm7141` | **NOT done** — everything untracked/unstaged; remote branch still equals `main` (`2b4cacd6…`). Local files exist; remote durability absent. (Rolled into F2 above.) |
| — (new) | — | The Phase 1 findings F1 (setup-script fresh-install bug) and F3–F5 (§4 wording) are new issues introduced with Phase 1, listed above. |

**Phase 0 re-check conclusion:** the two P1 *substance* fixes (evidence + checker) are genuinely done and verified by execution; the P1 *durability* fix (commit/push) remains open and now covers the Phase 1 artifacts as well.
