# 04 — CI and Regression Matrix (merge-readiness mission, 2026-10-26)

Machine-readable summary. Status legend: PASS / FAIL / BLOCKED / NOT RUN.

## A. Upstream CI state (as observed 2026-10-26)

| Check | sglang#42106 | Classification |
|---|---|---|
| `call-gate/pr-gate`, `pr-gate` (many) | FAIL (3–6 s) | label gate "Require run-ci label (optional)" — maintainer-controlled |
| `pr-test-*-finish` | FAIL (3 s) | orchestrators blocked by the gate; GPU tests **NOT RUN** (skipped, not failed) |
| `lint` | FAIL (2 m 47 s) | real lint execution; addressed by `1a9f2d92` (validated in-branch) |
| omni#2540 checks | 0 check-runs | workflows await maintainer approval (unchanged) |

## B. Local validation matrix (this mission)

### SGLang integration branch (`44c8fa51f`)

| Check | Result | Evidence |
|---|---|---|
| Merge conflicts resolved (vs main `5ef99013a`) | PASS | 0 unmerged; 36-file delta |
| Guard preservation vs `def437fb` | PASS | function-level AST identical (7 functions) |
| `test_yue2_platform_gates.py` | PASS 21/21 | venv + PYTHONPATH |
| `test_kernels_namespace.py` (full suite) | PASS 100/100 | post P0-1 fix; total 121/121 with gates |
| ruff (CI args `--select=F401,F821,F823,UP037`, pinned 0.15.1) | PASS | changed files |
| ruff format / isort 7.0.0 / codespell 2.4.1 | PASS | changed files |
| py_compile (34 changed .py) | PASS | — |
| gfx1151 boot (serve, Yue2Pipeline) | PASS | `--model-type diffusion` required |
| Test B short E2E | PASS | HTTP 200; 47.00 s WAV; finite; non-silent |
| Test C full-song | PASS | HTTP 200; 112.12 s WAV; 414 s wall |
| Post-fix re-smoke | PASS | HTTP 200; 5.9 s; 0.8 s WAV blip |
| Env-disable proof | PASS | `/proc/<pid>/environ` — no disable vars |
| Independent reviews A/B/C | PASS/PASS/FAIL→fixed | reviews/; all P0/P1 fixed + revalidated |
| H800 physical | NOT RUN (author) | simulated dispatch only — no claim |

### SGLang-Omni integration (`3063cdf5` + rehearsal `363073e6`)

| Check | Result | Evidence |
|---|---|---|
| Rehearsal tree SHA vs record | PASS bit-exact | `363073e6…` |
| Merge vs main `b6299238` | PASS 0 conflicts | both-sides files = 1 (auto-merged, verified + tested) |
| 3 yue2 suites, rehearsal | PASS 39/39 | incl. prompt-164 pair |
| 3 yue2 suites + capabilities, merged | PASS 60/60 | — |
| Lint (ruff 0.11.10 / black 24.10.0 / isort 5.13.2) | PASS | 28 changed .py |
| Long-lyrics regression | PASS | mocked HTTP-contract tests |
| `sgl-omni serve` + `POST /v1/audio/speech` (BS=1) | PASS | HTTP 200; 79.96 s WAV; 158.9 s |
| H800 physical | NOT RUN (author) | — |

## C. Cross-cutting

| Item | Status |
|---|---|
| Upstream main importability on sgl_kernel-less HIP hosts | FAIL (main itself) → 4-file overlay prepared as independent-main-PR candidate (`patches/sglang_main_rocm_host_boot_overlay.patch`) |
| sglang-kernel 0.4.10 on PyPI for ROCm | NOT AVAILABLE (CUDA-only; verified) |
| Full 384-candidate WildSongBench rerun | NOT RUN (intentionally out of scope) |
| New GPU kernels / performance work | NOT RUN (out of scope by directive) |
