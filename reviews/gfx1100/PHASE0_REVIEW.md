# PHASE 0 Independent Verification Review — gfx1100 / W7900

**Reviewer role:** independent (did not author the Phase 0 work; all measurements below re-executed on-host 2026-10-11 ~22:2x UTC)
**Artifact under review:** `reports/gfx1100/PHASE0_PREFLIGHT.md`

## VERDICT: **PARTIAL**

Gate criteria (GPU+OS validated / no destructive changes / no unresolved device-access blocker)
are **substantively met** — every hardware/OS/ROCm/device-access claim I re-executed checked out.
However, the report's **evidence chain is broken**: both artifacts it cites as proof
(`evidence/gfx1100/environment.json` and `scripts/check_environment.py`) **do not exist**, and
several specific claims are contradicted by on-host measurement or by the mission's own logs.
Phase 0 may proceed to Phase 1 only after the P1 items are fixed (regenerate + commit the
machine-scoped evidence and the checker script).

## Findings table

| # | Severity | Finding | Claimed | Measured (independent) |
|---|---|---|---|---|
| 1 | **P1** | Cited evidence JSON missing | `evidence/gfx1100/environment.json` exists (report header) | File does not exist; no `evidence/gfx1100/` dir at all. Only `evidence/environment.json` exists and is the **gfx1151 clone's** data (hostname `amd-HP-ZBook-Ultra`, gfx1151, kernel 6.17.0-1033-oem; tracked in git, commit `6df6016` "phase 0 gfx1151") — i.e., data from the *other* machine |
| 2 | **P1** | Cited generator script missing | `scripts/check_environment.py` generated the evidence | Absent from `evidence-repo/scripts/`, workspace `scripts/`, and anywhere under `/workspace` (glob). Its collection logic, exception paths, and exit-code soundness: **NOT VERIFIED — nothing to audit** |
| 3 | P2 | `https://github.com` "blocked" claim not reproduced | "https://github.com CONNECT tunnels time out" | **200 in ~0.53 s, 4/4 tries** via egress proxy (`HTTPS_PROXY=…notebook-egress-proxy…:3128`). Possibly stale/intermittent, but not true at review time |
| 4 | P2 | `objects.githubusercontent.com` "blocked" | listed as blocked | **HTTP 404** = host reachable and answering (404 is just the bare path). Sub-claim wrong |
| 5 | P2 | ffmpeg version wrong | "ffmpeg 7.1.1" | `ffmpeg version 6.1.1-3ubuntu5` — apt epoch `7:6.1.1` was misread as 7.1.1 |
| 6 | P2 | git `insteadOf` hardening misdocumented | `git config --global url."http://github.com/".insteadOf "https://github.com/"` | Global config rewrites **only `git@github.com:` → `http://github.com/`**; no https→http rewrite in global *or* local config. Remote URL is hardcoded `http://github.com/AIwork4me/…` so the functional outcome (plain-HTTP transport) holds |
| 7 | P2 | HF endpoint claim contradicted by own evidence | "we use the official endpoint" (huggingface.co) | `logs/phase3_download_manifest.json` (started 22:18:40Z, before report mtime 22:19) records `"endpoint": "https://hf-mirror.com"` |
| 8 | P2 | `scripts/api_git.py` "mirror" claim false | tools/api_git.py "mirrored at scripts/api_git.py" | `tools/api_git.py` exists; **no** `api_git.py` in either `evidence-repo/scripts/` or workspace `scripts/` |
| 9 | P2 | gfx1100 deliverables not committed | report describes completed Phase 0 | `git status`: `reports/gfx1100/` **untracked**, `.gitignore` modification **unstaged** — nothing pushed to `validation/gfx1100-rocm7141`; evidence not yet durable on remote |
| 10 | P2/NOTE | Multi-GPU hardware context omitted | "GPU (PCI): 03:00.0 …; visible agent at 0000:c3:00.0" | lspci shows **8×** `1002:744b` devices (03/23/43/63/83/a3/c3/e3:00.0); exactly one (`c3:00.0`) is bound (amd-smi single row; `/dev/dri` has only `card7`+`renderD134`). Report should disclose the 8-device chassis and single-GPU exposure explicitly |
| 11 | NOTE | apt-repo status code differs | "AMD ROCm apt repository … unreachable (503)" | `https://repo.amd.com/amdgpu-install/` → **403** (not 503); `…/rocm/whl-multi-arch/` → **200** (Phase 1 wheel path reachable — the part that matters). Substance roughly holds, exact code wrong |
| 12 | NOTE | `setsid` narrative (§3.4) unverifiable | nohup killed by shell cleanup; setsid fixes it | **NOT VERIFIED** — narrative claim, no artifact to check |
| 13 | NOTE | L2/L3 cache figures not directly confirmed | "L2 6 MiB, L3 96 MiB" | This rocminfo build exposes only cacheline size; figures match Navi31 public specs but were **not** machine-verified |

## Claims VERIFIED by independent re-execution

| Claim | Measured | Match |
|---|---|---|
| rocminfo Agent 3 = gfx1100 | `Agent 3 … Name: gfx1100`; `amdgcn-amd-amdhsa--gfx1100` | ✓ |
| 96 CUs / 6 SEs / 1760 MHz | `Compute Unit: 96`, `Shader Engines: 6`, `Max Clock 1760` | ✓ |
| VRAM pool 50,315,264 KiB ≈ 48 GiB | Agent 3 GLOBAL pool `Size: 50315264 KB` (= 49136 MiB); amd-smi `26/49136 MB` | ✓ |
| PCI device 1002:744b @ c3:00.0 | lspci 8× `[1002:744b]`; amd-smi row `0000:c3:00.0` | ✓ (see F10) |
| Ubuntu 24.04.4 LTS, kernel 6.8.0-79-generic | identical | ✓ |
| ROCm userspace 7.2.1 | `/opt/rocm/.info/version` = `7.2.1`; `rocm-core 7.2.1.70201-81~24.04` | ✓ |
| 7.2.1-vs-7.14.1 wheel discrepancy documented honestly | §2 states it explicitly, defers resolution to Phase 1 `ldd` check | ✓ |
| amdgpu driver 6.16.13, unmodified | `/sys/module/amdgpu/version` = `6.16.13`; amd-smi header agrees; **0** dkms/driver packages; apt history on 2026-10-11 shows only openssh-server (platform) + prereqs | ✓ |
| `/dev/kfd` root:993 660, `/dev/dri/renderD134` accessible | `crw-rw---- root 993 226,134` / `crw-rw---- root 993 234,0`; uid=0 | ✓ |
| 2× EPYC 9334, 64C/128T, NUMA×2 | lscpu: EPYC 9334, Socket(s):2, CPU(s):128, NUMA 2 | ✓ |
| RAM 503 GiB | `free -g`: 503 | ✓ |
| Disk `/` 1.8 T, `/workspace` 93 G | 1.8 T / 80 G now (drift, fine) | ✓ |
| api.github.com / huggingface.co / repo.amd.com / codeload / pypi / hf-mirror reachable | 200 / 200 / 200 / 301 / 200 / 200 | ✓ |
| ssh.github.com:443 blocked | `000`, curl rc=35 (SSL error) | ✓ |
| Remote branch SHA `2b4cacd6…` = main at creation | `gh api …/git/ref/heads/validation%2Fgfx1100-rocm7141` → `2b4cacd6efd0f15959a1142d81907e6fb11a85dc`; main → same SHA; local clone at same commit, subject matches report | ✓ |
| Prereqs installed (no upgrade) | apt history 22:11:50: `git-lfs ffmpeg jq build-essential pkg-config`; git-lfs 3.4.1 ✓, jq 1.7 ✓ | ✓ (ffmpeg version wrong, F5) |
| gh 2.x as AIwork4me w/ repo scope | gh 2.101.0; active account AIwork4me; scopes incl. `repo` | ✓ |
| `/usr/local/bin/git` wrapper with plain-HTTP fallback | exists (May 28), rewrites to gh-proxy then `http://github.com` | ✓ |
| `YUE2_WORKSPACE` override | `scripts/download_pins.py:72` reads env `YUE2_WORKSPACE` | ✓ |
| .gitignore excludes weights/audio/env trees | `*.safetensors *.wav *.flac *.pt *.npy models/ runs/ environments/ upstream/ benchmark/ scratch/` all present | ✓ (but uncommitted, F9) |

**Item 7 (environment.json consistency):** could not be performed as intended — the gfx1100
environment.json does not exist. I instead spot-checked ≥18 report fields directly against
live measurements (table above).

**Item 8 (check_environment.py audit):** **NOT VERIFIED — script absent.** No assessment of
exception-masking or exit-code logic is possible; existence of such a script is itself an
unsupported claim.

## Independently executed command list (key outputs)

```
rocminfo | grep -A2 'Agent 3'                     → Name: gfx1100
rocminfo (Agent 3 block)                          → CU 96, Shader Engines 6, 1760 MHz,
                                                     GLOBAL pool 50315264 KB, amdgcn-…-gfx1100
lspci -nn | grep 744b                             → 8 devices 03/23/43/63/83/a3/c3/e3:00.0
amd-smi                                           → amdgpu 6.16.13, ROCm 7.2.1, 0000:c3:00.0,
                                                     26/49136 MB, 33 °C, 7/241 W
head -2 /etc/os-release ; uname -r                → Ubuntu 24.04.4 LTS / 6.8.0-79-generic
cat /opt/rocm/.info/version                       → 7.2.1
dpkg -l | grep rocm-core                          → 7.2.1.70201-81~24.04
cat /sys/module/amdgpu/version                    → 6.16.13
ls -l /dev/kfd /dev/dri/renderD*                  → root:993 660 / root:993 renderD134
curl (15 s cap): api.github.com 200 · huggingface.co 200 · repo.amd.com 200 ·
   github.com 200 ×4 (~0.5 s) · ssh.github.com:443 000/rc35 ·
   objects.githubusercontent.com 404 · codeload 301 · pypi 200 · hf-mirror 200 ·
   repo.amd.com/amdgpu-install/ 403 · repo.amd.com/rocm/whl-multi-arch/ 200
gh api …/git/ref/heads/validation%2Fgfx1100-rocm7141 → 2b4cacd6efd0f15959a1142d81907e6fb11a85dc
gh api …/git/ref/heads/main                        → 2b4cacd6efd0f15959a1142d81907e6fb11a85dc
lscpu / free -g / df -h / id / hostname           → see table
git-lfs --version → 3.4.1 · ffmpeg → 6.1.1 · gh → 2.101.0 · python3 → 3.12.3
gh auth status                                    → AIwork4me active, repo scope
git config --global -l / --local -l (evidence-repo)→ insteadOf covers SSH only; origin=http://…
tail /var/log/apt/history.log                     → 2026-10-11: openssh-server + prereqs only
dpkg -l | grep -c 'amdgpu-dkms\|rocm-dkms'        → 0
glob **/check_environment.py (whole /workspace)    → no hits
ls evidence/ ; git ls-files evidence/             → no gfx1100/ subtree; environment.json = gfx1151
git status (evidence-repo)                        → .gitignore modified (unstaged); reports/gfx1100/ untracked
head logs/phase3_download_manifest.json           → "endpoint": "https://hf-mirror.com"
```

## Required actions before Phase 1 gate

1. **(P1)** Create `scripts/check_environment.py`, run it on this host, and commit
   `evidence/gfx1100/environment.json` it produces; ensure FAIL paths abort with nonzero exit
   (auditable), then re-cite both in the report.
2. **(P1)** Commit and push `reports/gfx1100/PHASE0_PREFLIGHT.md`, the corrected `.gitignore`,
   and the evidence above to `validation/gfx1100-rocm7141`.
3. **(P2)** Correct: ffmpeg version, insteadOf description, HF-endpoint wording (or switch the
   manifest to the official endpoint), github.com/objects.githubusercontent.com reachability
   statements, `scripts/api_git.py` mirror claim, apt "503"→actual code; disclose the 8-GPU
   chassis with single exposed GPU.
