# RC2_00 — Live State & Source-Lineage Reconciliation (R0)

**Snapshot:** 2026-11-19T02:55Z (UTC) · **Execution:** read-only; no GPU
workload, no campaign file, no live checkout modified.
**Reviewer worktree:** `/tmp/opencode/rc2` @ `66b5a13` (= PR #15 head) —
separate from the live campaign checkout, which was not touched.

---

## 1. Host & GPU (verified live)

| Item | Value |
|---|---|
| Host | `j-7uqnwhrwmv2s44k6zdqzoq5id` |
| ROCk driver | 6.16.13 loaded; HSA runtime 1.18 |
| GPU | device `0x744b` (gfx1100), W7900D-class, 48 GiB VRAM (`51522830336` B) |
| Live GPU state | 98 % GPU util, 34 % VRAM (17.6 GiB) — campaign workload |
| Disk | 966 GiB free on `/` (overlay; `/data` on same FS) |
| Stale processes | numerous `pytest` stubs + zombies under `/tmp/pytest-of-root/*` and `/tmp/opencode/rcvenv` from earlier CPU test sessions — CPU-only, no GPU KFD use (verified `rocm-smi --showpids`: the only VRAM-bearing KFD pid is the campaign server); harmless but should be reaped at next maintenance window |

## 2. Arm B campaign status: **RUNNING, HEALTHY**

Cross-checked from four independent sources (never from process names alone):

1. **Processes:** launcher `run_armB_campaign.sh` PID 635532 (01:57Z) →
   gateway `gpu_lock.py wait` PID 635539 → `sglang serve` PID 635542
   (port 31000, model `/data/yue2/models/YuE2-3B`) → driver `run_wsb.py`
   PID 636313. Supervisor `mission_chain.py` PID 3363794 alive (since Nov 18).
2. **GPU lock:** `/data/yue2/gpu.lock` →
   `who=armB-campaign:armB_full_20261119T015756Z`, pid 635539,
   acquired 2026-11-19T01:57:56Z, host matches.
3. **Journal:** `mission_chain.log` cadence 10 min: `complete=1/3/5/7/9`
   @ 02:07–02:47Z, `driver_alive=True pids=[636313]` every probe.
   Generation manifest: 10 rows, all `status=complete`, `retries=0`.
4. **Artifacts:** freshest WAV 02:47Z (2 min before probe); per-song
   directories (plan/manifest/result/tensors/audio) present for 10 ids.

Progress & ETA: 10/384 @ 02:49Z; wall-clock per candidate 241–426 s
(mean ≈ 4.7 min) → **ETA ≈ 2026-11-20T23:00Z (±3 h)** for generation,
then chain-run audit + four-metric scoring (serialized, same supervisor).

Campaign identity (from `run_config.json` + first receipts):
run `armB_full_20261119T015756Z` · SGLang commit `ced0ef7d` · patchset
sha256 `c1e04454…` · model `m-a-p/YuE2-3B@1a96eca6` · VAE
`m-a-p/YuE2-Vae-legacy@b54118f0` · dataset `m-a-p/WildSongBench@e361b85a` ·
config (cot=full, ode_steps=32, 9000/4096 max tokens, VAE 1024+16) —
matches the frozen protocol lock and the official seed schedule
(831001+i / 831019+i observed in manifest seeds).

**Action taken per mission §1.1: none beyond read-only inspection.**
No other GPU workload started; live checkout untouched.

## 3. Git / GitHub live status (recomputed 2026-11-19T02:5xZ)

| Ref / PR | HEAD | State | Notes |
|---|---|---|---|
| `main` | `ba99c4d` | — | = merge of PR #7 (security redaction) + 3 prep commits |
| PR #8 | `9a230d5` | OPEN draft, MERGEABLE | base `feat/yue2-rocm-publication-readiness`; superseded semantically by integrated lineage (see RC2_01 disposition) |
| PR #9 | `cdff9312` | OPEN draft, MERGEABLE | fresh-image final closure |
| PR #10 | `87561253` | OPEN draft, MERGEABLE | stacked on #9 |
| PR #11 | `4d9f4a2d` | OPEN draft, MERGEABLE | stacked on #10 |
| PR #12 | `aa3f34f5` | OPEN draft, MERGEABLE | C2/C2.1 provenance stack, merged *content-wise* into #15 |
| PR #13 | `f7fda39` | OPEN draft, MERGEABLE | image-swap resume hardening |
| PR #14 | `fee027d` | OPEN draft, MERGEABLE | = **live campaign checkout**; CI run 44433225686 PASS |
| PR #15 | `66b5a13` | OPEN draft, MERGEABLE | CI run 44442680950 **PASS** (327 passed / 28 skipped) |

- `origin/main...origin/integration/joint-blog-rc` = **119 ahead / 4 behind**
  (merge-base `4612c20`) — recomputed, matches prior review.
- The 4 behind-commits are exactly the PR #7 security merge set
  (`5f1e892`, `cc54a92`, `29252e1`, `ba99c4d`). **Content reconciliation
  verified by blob-identity:** `scripts/public_evidence_guard.py`,
  `docs/PUBLIC_EVIDENCE_REDACTION.md`, `tests/test_public_evidence.py` are
  **byte-identical** between `main` and `66b5a13`. The behind-count is a
  topology artifact (PR #15 bases on `fix/w7900-fresh-image-resume-hardening`),
  **not** an unreconciled semantic divergence. No merge performed (mission rule).
- No PR was closed, merged, or force-pushed in this session.

## 4. Source-lineage compatibility matrix (R0 deliverable)

Method: content hashes, not commit-identity assumptions.
Arm A driver hash `d2b983c8…` (= `sha256(run_wsb_torch.py)`) was searched
against **every** commit that ever touched the file across all refs → unique
match `0dedd415` (2026-11-15 00:05Z, "hardening(P3): RCA F1–F6"), which is an
ancestor of the entire RC stack. Arm B driver `sha256(run_wsb.py)` is
**byte-identical** (`3d168c47…`) at `f7fda39`, `fee027d` (live) and `66b5a13`
(PR #15).

| Evidence | Exact source SHA | Frozen protocol | Relevant code changes vs evidence source | Valid for RC? |
|---|---|---|---|---|
| Arm A generation (384/384, `armA_full_20261115f`) | `0dedd415` (driver content-hash verified; run_config pins model/VAE/manifest/evaluator SHA256) | YES — lock frozen 2026-11-11; seeds/contract asserted per candidate | `run_wsb_torch.py` diff → journal fsync, resume-verify, symlink refusal, worker-sha recording only; **zero sampling/model/param changes** (audited line-by-line, grep for temperature/top_p/top_k/seed/cfg/ode/tokens = none) | **PASS** |
| Arm A scoring (SB/PER + MuLan/AMC, 2026-11-18) | live tree `f7fda39` + frozen evaluator bundle `bd550b36…` at `/data` | YES — same lock; solo serialized | scoring scripts unchanged `f7fda39`→`66b5a13` | **PASS** |
| Arm B generation (running, `armB_full_20261119T015756Z`) | live tree `fee027d`; driver `run_wsb.py` identical at `66b5a13`; `serve_yue2_gfx1100.sh`, `configs/*.lock.yaml`, `patches/*` unchanged `fee027d`→`66b5a13` | YES — same lock, same seeds observed | supervision-only deltas (gpu_lock call-time resolution, mission_chain gate hardening, lifecycle fixes) — no generation-path change | **PASS (prospective)** — final journal/audit hash check at completion (RC2_02) |
| Arm B scoring (future) | will run under the chain on the live tree; evaluator bundle pinned at `/data` (same `bd550b36`-class identity, re-verify at execution) | YES | none expected; record exact tree SHA in the score receipt | **PENDING** |
| PR #15 integrated RC | `66b5a13`, CI 327/0/28 PASS; local manifest-host suite 355/0/0 (M1 freeze) | YES | — | **PASS (engineering)**; independent review = RC2_01 |

**Decision rule applied:** no 384-candidate rerun is demanded because the
deltas between evidence sources and the integrated RC are confined to
(a) journal/provenance robustness, (b) supervision/lifecycle, (c) tests/docs —
verified by file-level diff of `scripts/`, `patches/`, `configs/`,
`supervisor/`. Any future commit touching generation, evaluator, model
loading, sampling, seeds, protocol locks or the server launch path
**invalidates this matrix** and requires recomputation.

## 5. Deltas of the live fast-forward (for the record)

`f7fda39` → `fee027d` (owner-authorized, 2026-11-19T01:25Z, during supervisor
retry-sleep; no process restarted — confirmed by continuous PID set):
`gpu_lock.py` (call-time lock resolution), `mission_chain.py` (injected lock
path; lock-timeout → gate FAIL), Arm B launcher/acceptance lifecycle,
`extract_archive_safe.py` (enforced SHA pin, staged atomic extraction),
plus tests/docs. None touch generation/scoring semantics (§4).

## 6. R0 verdict

- Live state: **reconciled**; Arm B RUNNING under valid single-tenant GPU
  ownership; supervisor healthy.
- GitHub state: **reconciled**; PR #15 remains the RC candidate
  (119/4 explained and content-reconciled, not merged per rules).
- Lineage: **all completed evidence generations PASS compatibility** with the
  PR #15 tree at file-content level; Arm B validity is prospective until the
  completion audit.
- Open items carried forward: Arm B completion (RC2_02), PR #8/#10/#11/#12
  disposition (RC2_01), 4-behind merge cleanup (owner decision at release
  time — recommend retargeting PR #15 base or a final rebase review, not an
  automatic merge).
