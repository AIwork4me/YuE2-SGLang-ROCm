# PHASE 0 Independent Verification Review

**Verdict: PASS**

- Reviewer: Independent verification subagent (adversarial audit, no trust in prior claims)
- Date: 2026-10-11 (~18:00 +08:00)
- Scope: PHASE 0 workspace + environment capture for YuE2 x SGLang x ROCm on gfx1151
- Method: every artifact inspected on disk; key claims independently re-executed on the live host

## 1. Verdict rationale

The Phase 0 gate evidence is genuine, internally consistent, and reproducible. The
GPU smoke test was independently re-run in the mission venv and passed again with
statistically identical numerics. All mission-critical environment values (gfx1151,
32 GiB dedicated VRAM, kernel, ROCm 7.2.1 host / 7.14.1 torch-bundled, torch
2.12.0+rocm7.14.1, HIP 7.14.60850) match both the raw captures and live system
state. No secrets are leaked. Two minor data errors were found in
`environment.json` (P2, corrected values listed below); neither affects the gate.

## 2. What was independently re-executed (live) vs statically checked

### Re-executed on the live host

| # | Check | Command | Result | Evidence |
|---|---|---|---|---|
| R1 | GPU arch | `rocminfo \| grep -m1 gfx` | `gfx1151` — CONFIRMED | matches `logs/phase0_raw/rocminfo.txt` (Agent 2, ISA `amdgcn-amd-amdhsa--gfx1151`, Chip ID 0x1586, 40 CUs, APU) |
| R2 | GPU smoke re-run | `source environments/yue2/bin/activate && python scripts/phase0_gpu_smoke.py` | `SMOKE_RESULT: PASS`, RC=0; torch 2.12.0+rocm7.14.1, HIP 7.14.60850, `cuda_available=True`, device `AMD Radeon 8060S Graphics`, cap (11,5), total 100.00 GiB, fp32 diff 0.000e+00, **fp16 4.904e-04**, **bf16 3.907e-03**, peak 104.0 MiB | `reviews/phase0_smoke_rerun_2026-10-11.log` (copy of live stdout). Originals backed up to /tmp, restored after re-run, md5-verified identical (`ada320d9...` json, `d10c720f...` log) — evidence artifacts untouched by this review |
| R3 | Network: huggingface.co | `curl --max-time 10 https://huggingface.co` | timeout, `000` — CONFIRMS "UNREACHABLE (connection timeout)" | `logs/phase0_raw/net_hf.txt` (000, exit 28 at capture) |
| R4 | Network: hf-mirror.com | `curl --max-time 10 https://hf-mirror.com` | `200` — CONFIRMS "REACHABLE" | `logs/phase0_raw/net_hfmirror.txt` (200 at capture) |
| R5 | Network: github.com | `curl --max-time 10 https://github.com` | **timeout now vs 200 at capture** — CONFIRMS "INTERMITTENT" is a fair characterization | `logs/phase0_raw/net_github.txt` (200 at 17:32); live re-test at ~18:00 timed out |
| R6 | Network: github large transfer | `curl --max-time 10 https://codeload.github.com/sgl-project/sglang/tar.gz/refs/heads/main` | stalls mid-transfer (4.5 MB in 10 s then timeout) — corroborates "large transfers fail/slow" | live re-test |
| R7 | rocm-core package version | `dpkg -l rocm-core` | `7.2.1.70201-81~24.04` — value in environment.json is TRUE | (not present in raw captures; see P3-1) |
| R8 | Secrets scan | grep for `gho_`, `ghp_`, `github_pat_`, `hf_`, `api_key`, `secret`, `password`, `Bearer`, `AKIA`, `BEGIN` across logs/, evidence/, scripts/ | **no credential strings found**; `gh auth status` token is `<redacted>` in `gh_auth.txt` (sed in `collect_system_info.sh:36`); `env_proxy` capture has a redaction sed and captured nothing; only match for "token" is the false positive "9000-token generations" in the report | `logs/phase0_raw/gh_auth.txt`, `logs/phase0_raw/env_proxy.txt`, `scripts/collect_system_info.sh` |
| R9 | CPU threads | `nproc` | 32 — matches `cpuinfo_full.txt` (`CPU(s): 32`) and report | `logs/phase0_raw/cpuinfo_full.txt` |

### Statically cross-checked (artifact vs artifact)

| # | Claim (environment.json / report) | Raw evidence | Match |
|---|---|---|---|
| S1 | Dedicated VRAM 34359738368 bytes (32 GiB) | `amdgpu_params.txt`: `mem_info_vram_total:34359738368` (card1) | YES |
| S2 | PyTorch-visible 100.0 GiB = GTT pool, not VRAM | `rocminfo.txt` Agent 2 GLOBAL pools `104857600 KB` = 100 GiB; smoke log `reported total GPU memory = 100.00 GiB` | YES — the environment.json explanatory note is accurate |
| S3 | RAM 94 GiB total / 90 GiB available; memtotal 98634036 KiB, memavailable 94507256 KiB | `free.txt`, `meminfo.txt` | YES (exact) |
| S4 | Swap 8.0 GiB unused | `free.txt`, `swapon.txt`, `meminfo.txt` (SwapTotal 8388604 kB, SwapFree equal) | YES |
| S5 | Kernel 6.17.0-1033-oem; Ubuntu 24.04.4 LTS | `uname.txt`, `os_release.txt`, `lsb_release.txt` | YES |
| S6 | Host ROCm userspace 7.2.1, /opt/rocm-7.2.1 | `rocm_ver.txt` (`.info/version` = 7.2.1) | YES |
| S7 | KFD runtime 1.18 | `rocminfo.txt` line 6 `Runtime Version: 1.18` | YES |
| S8 | In-tree amdgpu, no amdgpu-dkms | `dkms.txt` ("no-dkms"), `kernel_mod.txt` (amdgpu loaded), `kfd.txt` (/dev/kfd, renderD128) | YES |
| S9 | torch 2.12.0+rocm7.14.1, HIP 7.14.60850, gfx1151 | smoke log/JSON (and re-run R2); venv install log `phase1_torch_install.log` shows `torch==2.12.0+rocm7.14.1` from AMD index | YES |
| S10 | Report table: fp16 4.9e-4, bf16 3.9e-3, PASS | smoke log `4.907e-04` / `3.907e-03`; smoke JSON `0.0004906654357910156` / `0.003906965255737305` | YES (log, JSON, report mutually consistent) |
| S11 | capture exit codes | `phase0.log` exit tails match every raw file's `[exit N]` line, including honest non-zero exits (amdgpu_params exit 2 — gtt_size/vis_vram_total absent; net_hf/net_pypi exit 28 timeouts) | YES |
| S12 | Script authenticity | `collect_system_info.sh` run() emits `$ <cmd>` + `[exit N]`; flattened command lines match raw files byte-for-byte in structure; gh/env redaction seds present | YES |
| S13 | gh CLI auth, git 2.43.0, uv 0.12.3, python 3.12.3 | `gh_auth.txt`, `git_ver.txt`, `uv_ver.txt`, `python.txt` | YES |
| S14 | Disk 1.9T NVMe, 262G free, 86% used (report §1) | `df.txt`: `/dev/nvme0n1p2 1.9T 1.5T 262G 86%` | YES in report; see P2-1 for the JSON field |

## 3. Issues found

### P2 (major-minor: data errors in environment.json, gate unaffected)

- **P2-1 `environment.json` `disk.total = "262G"` is wrong.** `df.txt` shows
  `/dev/nvme0n1p2` Size **1.9T**, Avail 262G. The JSON's `total` field actually
  holds the *free* value (duplicate of `free_at_capture`). The human-readable
  report states it correctly ("1.9 TB NVMe, 262 GB free"). Fix: `"total": "1.9T"`.
  Evidence: `logs/phase0_raw/df.txt`, `evidence/environment.json` `disk` object.
- **P2-2 `environment.json` `disk.inodes_free = "12327548"` is misattributed.**
  That is the **tmpfs `/run`** IFree (first line of `df -i`), not the stated
  filesystem `/dev/nvme0n1p2`, whose IFree is **116759031**. The collector took
  the first line of `df -i` but the second line of `df -h`. Fix: use
  116759031 for /dev/nvme0n1p2. Evidence: `logs/phase0_raw/df_inode.txt`.

### P3 (nits / provenance notes)

- **P3-1 rocm-core version not backed by a raw capture.** environment.json cites
  `rocm-core 7.2.1.70201-81~24.04`; no raw file contains it (grep across logs/ found
  it only in the derived artifacts). Independently verified TRUE via `dpkg -l
  rocm-core`. Recommendation: add a `dpkg -l rocm-core` capture.
- **P3-2 `cpu.max_freq_mhz: null` despite available data.** `cpuinfo_full.txt`
  (lscpu) contains `CPU max MHz: 5187.5000`. The null understates captured data.
- **P3-3 `capture_time` semantics.** environment.json `capture_time` is
  17:58:46 (JSON authoring time); the raw capture actually ran 17:32:18–17:32:53
  (`phase0.log`), and the smoke artifacts are 17:54 (after the 17:37 phase-1 torch
  install). Chronology is honest but the field name invites misreading; smoke ran
  on the venv-installed torch, which is correct for the gate.
- **P3-4 "TLS resets" wording not evidenced in phase0 artifacts.** The report §2
  attributes GitHub failures to "TLS resets"; `net_github.txt` records only a
  plain 200, and no retry/failure log was captured in phase 0. The INTERMITTENT
  characterization itself is independently confirmed (R5/R6), so this is a
  provenance/wording nit, not an overclaim that changes decisions.
- **P3-5 Account username disclosure.** GitHub username "AIwork4me" appears in
  `gh_auth.txt`, environment.json, and the report. The token itself is properly
  redacted; a username is not a credential. Noted as a privacy consideration only.
- **P3-6 Stray JSON key.** `gpu.torchsplash: null` — unknown/misspelled key,
  cosmetic.
- **P3-7 Forward reference for Phase 2.** Report §2 says shallow-fetch strategy is
  "documented in Phase 2"; `upstream/sglang` is currently an empty repo (branch
  `master` unborn, no commits, remote set to github.com/sgl-project/sglang).
  Out of phase 0 scope; flagged so the Phase 2 review verifies it lands.

### No P0 or P1 issues found

- No fabrication indicators: raw captures carry realistic noise (exit 2 on
  missing sysfs nodes, curl exit 28 partial transfers, N/A fields in amd-smi).
- Smoke numbers are physically plausible for 1024x1024 matmuls at ~0.1 scale and
  reproduce on re-run (fp16 4.904e-04 vs 4.907e-04 — expected variation, script
  uses unseeded `randn`; bf16 identical to 4 significant digits).
- The 100 GiB "GPU memory" is honestly explained as GTT (rocminfo pools
  corroborate) rather than passed off as dedicated VRAM; the 32 GiB carveout is
  separately and correctly recorded from sysfs.

## 4. Coverage of requested checks

| Requested | Status | Where |
|---|---|---|
| GPU really gfx1151 | CONFIRMED (live) | R1 |
| Smoke artifacts genuine & internally consistent; report table 4.9e-4 / 3.9e-3 | CONFIRMED | S10, R2 |
| environment.json vs raw: RAM, VRAM 34359738368, kernel, ROCm 7.2.1 host, torch 2.12.0+rocm7.14.1, HIP 7.14.60850 | ALL MATCH (except disk fields, P2-1/P2-2) | S1–S9 |
| No secrets/tokens leaked | CONFIRMED | R8 |
| Network claims (HF unreachable, hf-mirror reachable, GitHub intermittent) | CONFIRMED by live re-test | R3–R6 |
| Independent smoke re-run passes FP32/FP16/BF16 | CONFIRMED | R2 |
| Report overclaims vs evidence | None material; P3-4 wording nit, P2 JSON fields contradict the (correct) report | §3 |

## 5. Required corrections before Phase 1+ relies on environment.json

1. `disk.total` → `"1.9T"` (P2-1)
2. `disk.inodes_free` → `"116759031"` for /dev/nvme0n1p2, or relabel as /run tmpfs (P2-2)

Both are one-line JSON fixes; neither alters the PASS gate.
