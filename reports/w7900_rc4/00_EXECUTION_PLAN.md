# W7900 RC4 — Execution Plan (M0)

Mission: W7900-RC4 — developer reproducibility, runtime reliability, performance, release hardening.
Base: `48d1cb6` (verified live PR #16 HEAD). Branch: `mission/w7900-rc4-repro-reliability`.

## Order of work

1. **M0 (this file)** — env/git audit, frozen-evidence SHA256 manifests
   (`/data/yue2-runs/rc4_evidence/frozen_manifests_20261122.txt`,
   `frozen_scores_manifest_20261122.txt`), orphaned-server diagnostics + cleanup
   (done: R1-E1 evidence captured before shutdown).
2. **M1** — fresh clone at `/data/rc4/fresh_clone` (local /data class, not NFS, not old
   checkout), Mode A (verified local asset cache) + Mode B attempted where network allows.
   Run the documented developer journey end-to-end incl. GPU smoke, full song per path,
   WSB pilot + audit + score, negative controls, docs repair.
3. **M2** — reliability matrix (bounded), root-cause work on R1 (already have live
   evidence R1-E1), R3 close()/memory lifecycle cycles, GPU lock contention, orphan scan.
   R2 (HIP IMA concurrency) only inside isolated window; otherwise NOT_TESTED + keep
   serialization boundary.
4. **M3** — performance per frozen methodology: paired Arm A/B full-song runs with new
   run IDs under `/data/yue2-runs/rc4_perf/`; n>=30/path target, staged pilot first;
   honest PARTIAL if budget-bound; concurrency C=1,2,4 only where resource-safe.
5. **M4** — prompt-19 tie review, 5 truncated-but-complete audit, Arm A 384-truncation
   semantics clarification, provenance review, evidence index, README/docs hardening.
6. **M5** — independent review, full test suite, release-gate ledger, atomic commits,
   push, stacked PR to `mission/joint-blog-rc2`, exact-HEAD CI check, handoff.

## GPU safety rules (all GPU work)

- Acquire `/data/yue2/gpu.lock` via `scripts/gpu_lock.py` before any GPU tier.
- Verify no other KFD process holds VRAM; verify disk >50G free on /data.
- Bounded deadlines (timeout wrappers) on every GPU command; failures preserved under
  `/data/yue2-runs/rc4_evidence/`.
- Never touch frozen dirs (`armA_wsb_full`, `armB_wsb_full`); new run IDs only.
- Never run overlapping GPU-intensive workloads.

## Stop-rule status at M0

No hard stop. GPU ownership establishable (lock free + VRAM released after orphan
cleanup). Frozen evidence intact. Disk OK on /data (941G).
