# 02 — M2 physical campaign closure (INTERIM — Arm B in progress)

**Snapshot:** 2026-11-19T02:10Z. This file reaches its final state only when
both arms have formally-accepted full-run evidence. Nothing here is upgraded
to PASS before receipts exist.

## Arm A (native PyTorch `torch-eager`, official implementation) — COMPLETE

| Gate item | Status | Evidence |
|---|---|---|
| Archive restoration provenance | **PASS** — pinned SHA256 `45e7c0f9…` recomputed = match; safe-extraction receipt (2134 members, path-safety, no-clobber) | `00_BASELINE_AUDIT.md` §3 |
| Restored subset audit | **PASS** — restoration receipt + journal identity; 177 restored candidates verified against official checker (pre-swap audit log) | `/data/yue2-runs/armA_wsb_full/restoration_audit.json` |
| Full run | **PASS — 384/384 complete** (recomputed from journal, never hard-coded) | `generation_manifest.jsonl` (384 complete) |
| Strict FULL audit | **PASS** verdict=FULL | `audit.json`; chain log 2026-11-18T11:14Z |
| Seeds / protocol / model / source identity | **PASS** — frozen protocol lock; model rev 1a96eca6; VAE rev b54118f0; run_config v2 identity | `run_config.json` |
| Provenance chain | **PASS — 0 violations** (384 legacy records honestly marked) | `verify_provenance.py` (M6 run) |
| Four-metric official scoring (solo, disclosed evaluator) | **PASS** both stages rc=0 + complete summaries | `scores/summary.json`, `additional/summary.json` |
| Results | SB 6.7044 / PER 16.83 % [14.87–18.92] / MuLan 0.4970 / AMC 0.4010 | receipts + `03_*` analysis |

## Arm B (SGLang ROCm serving, this image) — IN PROGRESS

| Gate item | Status | Evidence |
|---|---|---|
| Server acceptance (real music generation) | **PASS 2026-11-19T01:55–01:57Z** — 33.079 s audio @48 kHz, RMS 0.1486, sha256 receipt, graceful verified stop | `/data/yue2/logs/armB_acceptance/` + `armB_acceptance.out` |
| Campaign launch | **RUNNING** `armB_full_20261119T015756Z` since 01:57:56Z; gpu_lock held by launcher gateway (verified single-tenant); driver + server alive | `mission_chain_console2.log`; process census |
| Progress | 1/384 at 02:06Z (≈7 min/candidate ⇒ ETA ≈ 2026-11-20T23:00Z) | journal |
| Full run 384/384 + FULL audit + four metrics | **PENDING** | — |

Historical Arm B evidence (pre-swap image, 2026-11-14): 384/384 FULL,
SB 6.7376 / PER 17.77 % / MuLan 0.5093 / AMC 0.4056 — valid as its own
generation; never conflated with this-image results (mission §2).

## Campaign supervision (durable)

- Supervisor: `mission_chain.py` PID 3363794, chain lock held, state
  `armB_campaign`, retries every 600 s while driver alive (it is).
- Live-tree code: `fee027d` (PR #14 head; owner-authorized fast-forward).
- Next chain transitions after 384/384: `armB_audit` → `armB_score_per_sb`
  → `armB_score_mulan_amc` → `done` — all serialized under gpu_lock by the
  chain itself.

## M2 verdict (current)

**Arm A: PASS (all sub-gates). Arm B: IN PROGRESS (acceptance PASS, campaign
running). M2 overall: PENDING — cannot be PASS while Arm B is incomplete.**
