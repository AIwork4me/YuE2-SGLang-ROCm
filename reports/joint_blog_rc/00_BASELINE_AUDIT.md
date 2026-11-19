# P0 Baseline Audit — Joint Blog RC Mission (YUE2-AMD-JOINT-BLOG-RC)

Captured: **2026-11-19T00:0xZ** (all observations live, read-only; classifications per
mission rules PASS / FAIL / BLOCKED / NOT_TESTED / NOT_APPLICABLE).

Auditor session on host `j-7uqnwhrwmv2s44k6zdqzoq5idj` (fresh image after the
2026-11-16 image swap). Working from isolated worktree
`/data/yue2/worktrees/joint-blog-rc` @ `mission/joint-blog-rc-m1` (base `f7fda39`
= PR #13 HEAD). The live campaign checkout `/workspace/YuE2-SGLang-ROCm`
(branch `fix/w7900-fresh-image-resume-hardening` @ `f7fda39`) was **not
modified** during this audit.

---

## 1. Physical host & GPU

| Item | Observed value | Source |
|---|---|---|
| Hostname | `j-7uqnwhrwmv2s44k6zdqzoq5idj` | `hostname` |
| Kernel | `6.8.0-79-generic` x86_64 | `uname -a` |
| CPU | 2× AMD EPYC 9334 (64C/128T visible) | `rocminfo`/`nproc` |
| RAM | 503 GiB (365 GiB available) | `free -h` |
| GPU PCI | `0000:03:00.0`, device `0x744b`, subsystem `0x0e0c`, SKU `D7070910` | `lspci`, `rocm-smi --showproductname` |
| GPU identity | **AMD Radeon Pro W7900D** (W7900-class 48 GB variant; NOT silently renamed) — marketing string from env-B torch probe; `rocm-smi` itself reports only "AMD Radeon Graphics" | `reports/publication/fresh_image/00_ENVIRONMENT.json` + live `serve_yue2_gfx1100.sh` boot log 2026-11-18T23:55Z |
| Architecture | `gfx1100`, 96 CUs, wave32 | `rocminfo` |
| VRAM | 51,522,830,336 B = 47.98 GiB | `00_ENVIRONMENT.json` |
| Kernel driver | amdgpu 6.16.13 | `00_ENVIRONMENT.json` |
| Host ROCm userspace | 7.2.1 (`/opt/rocm-7.2.1`), HIP 1.18 — preserved unmodified | `00_ENVIRONMENT.json` |
| Container GPU visibility | 1 of 8 host GPUs (host PCI shows 8× `0x744b`; only one render node exposed) | `lspci`, `/dev/dri` |
| GPU state at audit | idle (0% util, 7 W, VRAM 0%) — no generation/scoring running | `rocm-smi` |

Note: the host is a multi-GPU lab machine; **this container sees exactly one
gfx1100 device**. All single-GPU serialization policy refers to that device.

## 2. Storage

| Mount | Size | Free | Role |
|---|---|---|---|
| `/` (overlay) | 3.5 T | 849 G | `/data/yue2`, `/data/yue2-runs` live here |
| `/workspace` (NFS) | 25 G | 18 G | live repo checkout + Arm A archive (7.2 GiB) |
| `/dev/shm` | 32 G | — | unused by policy |
| `/tmp` | 4 G tmpfs | — | **too small for benchmark data** (known constraint) |

## 3. Arm A archive provenance — PASS

- Pinned SHA256 in `reports/publication/fresh_image/IMAGE_SWAP_HANDOFF.md`:
  `45e7c0f9a443cdbd4e822536214155c9c3905da611e55a04c15cf98fe4c32da7`
- Sidecar `/workspace/armA_state_20261116T1145Z.tar.gz.sha256`: same value.
- **Recomputed from the artifact (2026-11-19T00:0xZ): identical.** VERIFIED.
- Prior safe-extraction receipt `/data/yue2-runs.extract_receipt.json`
  (2026-11-16T15:30:26Z, 2134 members, path-safety + no-clobber policy).

## 4. Fresh-image campaign state (supersedes the 177/384 handoff snapshot)

Mission-chain supervisor: PID 3363794 (sleeping; holds
`/data/yue2/mission_chain.lock`; started 2026-11-18; runs from the live
checkout at `f7fda39`). State `/data/yue2/mission_state.json`:

| Stage | Status | Evidence |
|---|---|---|
| armA_campaign | **DONE — 384/384 complete** (recomputed from `generation_manifest.jsonl`: 384 complete entries) | journal + `restoration_audit.json` |
| armA_audit | **PASS (verdict FULL)** | `audit.json`, chain log 11:14:49 |
| armA_score_per_sb | **PASS** (rc=0, summary complete; 2026-11-18T19:29Z) | `scores/summary.json` |
| armA_score_mulan_amc | **PASS** (rc=0, summary complete; 19:55Z) | `additional/summary.json` |
| armB_acceptance | **FAILING IN RETRY LOOP** (attempts 22:25 rc=2, 22:55, 23:25 rc=1, 23:55 in flight) | `mission_chain_console2.log` |

### Fresh Arm A official results (native PyTorch `torch-eager`, full 384)

| Metric (selected-192 unless noted) | Value | Official ref | Δ |
|---|---:|---:|---:|
| SongBench GA | **6.7044** | 6.7316 | −0.0272 |
| PER micro | **16.83 %** | 8.44 % | **+8.39 pp** |
| MuLan | 0.4970 | 0.5068 | −0.0098 |
| AllMusicCaps | 0.4010 | 0.4054 | −0.0044 |
| PER micro (unselected-384) | 24.39 % | — | — |
| ASR-capped candidates (of 384) | 72 | — | — |

Run identity: `armA_full_20261115f`, model rev `1a96eca6…`, VAE rev
`b54118f0…`, protocol lock `configs/benchmark.lock.yaml`
(profile `benchmark-reproduction`, frozen 2026-11-11), seeds
`831001+i`/`831019+i`, full provenance in `run_config.json`.

**Scientific significance (feeds M3):** the *official implementation* on ROCm
(Arm A) shows essentially the same PER gap as the SGLang arm (Arm B fresh
17.77 %). The gap is therefore **not SGLang-specific**; hypothesis space now
concentrates on (a) the ROCm ASR evaluator backend and/or (b) generation-side
numeric behavior common to both backends, and/or (c) evaluator
protocol/config divergence from the authors' run. Same-audio cross-evaluator
matrix (M3.2) is designed to separate these.

### Live defect blocking armB_acceptance (found during audit, not yet fixed)

`armB_acceptance.sh` exports `LOG="$WS/logs"` (a **directory**) into the
environment of `serve_yue2_gfx1100.sh`, which interprets `LOG` as a **file**
(`LOG="${LOG:-$WS/logs/server_yue2_gfx1100.log}"`) and executes
`} >> "$LOG"` → `line 45: /data/yue2/logs: Is a directory` → server dies
instantly → acceptance health-poll times out after 1800 s → retry every 1800 s.
Observed live in the 23:55:31Z attempt boot log. Environment-variable
namespace collision between two repo scripts. Related P0 lifecycle defects
(`trap`/`exec`, no music-generation request in acceptance) are catalogued in
M1.2 of the execution plan. The live tree is **not modified** without owner
authorization (mission §15); fixes are prepared and validated in this
worktree first.

## 5. Repository & CI state

- `main` @ `ba99c4d` (per briefing; not re-based during audit).
- Live checkout: `fix/w7900-fresh-image-resume-hardening` @ `f7fda39` = PR #13 HEAD (verified `git log -1`).
- PR topology (live `gh pr list` 2026-11-19): #7 MERGED (security redaction);
  OPEN drafts: #8 (armA journal quarantine → base feat/yue2-rocm-publication-readiness),
  #9 (fresh-image closure → same base), #10 (CPU risk closure → base #9 branch),
  #11 (C2 provenance → base #10 branch), #12 (C2.1 fail-closed → base #11 branch),
  #13 (image-swap resume hardening → base #9 branch).
- PR #13 CI run 44421080608 (2026-11-18T23:28Z): **135 passed, 5 failed,
  26 skipped** — reproduced failure signature:
  `tests/test_mission_chain_gates.py::TestScoreGate` ×5 with
  `PermissionError: [Errno 13] Permission denied: '/data'`.
- Root cause (code-verified): `scripts/gpu_lock.py:43` freezes
  `DEFAULT_LOCK` at import time from `YUE2_WORKSPACE` (default `/data/yue2`);
  `gpu_ownership()` then does `path.parent.mkdir(parents=True, exist_ok=True)`
  (gpu_lock.py:116). Tests monkeypatch `mission_chain.WS` but `score()`
  calls `gpu_ownership(...)` without `lock_path`, so the frozen `/data/...`
  default is used → mkdir `/data` on a non-root CI runner → PermissionError.
  Exactly the "module-level path constant + late env var + fixture patches
  only mission_chain.WS" defect class anticipated by M1.1.

## 6. Process & lock census (2026-11-19T00:00Z)

| Process / lock | Owner | State | Protected? |
|---|---|---|---|
| PID 3363794 `mission_chain.py` | campaign | sleeping (PPID 1) | yes — untouched |
| PID 433588 `gpu_lock.py wait --who armB-acceptance` (child of 3363794) | campaign | running (23:55:31Z attempt) | yes — untouched |
| `/data/yue2/gpu.lock` | armB-acceptance | held (flock) | yes |
| `/data/yue2/mission_chain.lock` | chain | held (flock) | yes |
| `/data/yue2/locks/armA_launcher.lock` | — | idle file | preserved |
| SGLang server | — | **not running** (died at boot, defect §4) | n/a |
| Numerous `[sshd]/[bash]` zombies | init | defunct | no GPU, ignored |

No YuE2 generation, scoring, or evaluator processes were running at audit
time. GPU physically idle.

## 7. Classification of briefing claims vs. observed

| Briefing claim | Observed | Verdict |
|---|---|---|
| Arm A fresh 177/384 at image swap | archive verified; **campaign since completed 384/384 + audit FULL + both scorings PASS** | superseded (good direction) |
| Arm B SGLang full campaign 384/384 (historical) | per docs/RESULTS.md + evidence index (HISTORICAL generation, fresh solo scoring 2026-11-14) | distinct generation — not conflated |
| Fresh Arm B SongBench 6.7376 / PER 17.77 % / MuLan 0.5093 / AMC 0.4056 | docs/RESULTS.md receipts | consistent |
| PR #13 CI 135/5/26 with /data PermissionError | reproduced signature from run 44421080608 | confirmed, root cause identified |
| "W7900" hardware | device receipts say **W7900D** (0x744b, SKU D7070910) | naming preserved; publication must state W7900D (W7900-class, gfx1100, 48 GB) |

## 8. P0 gate verdict

- Evidence assets (archive, journals, scores, audio, logs): **protected — no
  writes, no deletion, no process disturbance.** PASS
- Active campaign detected & mapped; all CPU work moved to isolated worktree. PASS
- Release blockers enumerated (see `00_EXECUTION_PLAN.md` §blockers). Current
  blog verdict inputs: R2 evidence COMPLETE on host (packaging pending);
  R1 FAIL (CI red); R3/R4/R5 NOT_TESTED-to-BLOCKED; see plan.

**Gate P0: GO** (for CPU-only engineering + evidence-preserving analysis;
GPU windows only between mission-chain GPU stages or after owner decision on
the live-tree fix).
