# Execution Plan — YUE2-AMD-JOINT-BLOG-RC

## Current campaign state (see 00_BASELINE_AUDIT.md)

- Fresh Arm A: **complete & scored** (384/384, audit FULL, 4 metrics). 
- Chain stuck at `armB_acceptance` in a 30-min retry loop: server dies at boot
  (`LOG` env collision). In-flight attempt started 23:55:31Z will fail
  ~00:25:31Z; retries continue until code is fixed.
- GPU otherwise idle; no other GPU consumer.

## Sequencing rules (mission §1.2, §12)

1. All M1 engineering in this isolated worktree; live checkout untouched.
2. GPU work only in windows where the mission chain does not hold
   `gpu.lock` AND with owner-authorized live-tree fix applied — the chain
   itself will run Arm B campaign next, which takes GPU-days.
3. No concurrent heavy GPU jobs. No cleanup of campaign artifacts.

## Work order

| # | Task | Type | Blocking relationship |
|---|---|---|---|
| 1 | M1.1 fix `gpu_lock.DEFAULT_LOCK` import-time freeze + test isolation (CI red→green) | CPU | gates R1 |
| 2 | M1.2 fix Arm B lifecycle: LOG env collision; trap/exec loss; acceptance must generate real music; bounded cleanup owned by server lifecycle owner | CPU (+GPU validation window) | gates armB_acceptance → armB_campaign |
| 3 | M1.3 review/harden extract_archive_safe / restoration_audit / mission_chain gates (verify existing PR #13/#12 coverage; add missing tests) | CPU | gates R1 |
| 4 | M1.4 integration branch from #13 + merge #12 stack + reconcile #8; Draft PR; full CPU CI | CPU | gates R1 |
| 5 | Owner decision point: apply validated fix to live checkout (fast-forward `fix/w7900-fresh-image-resume-hardening`) so the chain's next retry passes | requires authorization | gates M2 Arm B |
| 6 | M2.3/M2.4 Arm B fresh campaign (driven by mission_chain once acceptance passes) + audits + scoring | GPU (days) | gates R3 |
| 7 | M3 PER causal work: same-audio matrix A1/B1 (+A2/B2/C1/C2 handoff kits), per-candidate decomposition using fresh receipts (both arms show gap ⇒ evaluator-backend hypothesis first) | CPU + GPU windows | gates R4 |
| 8 | M4 reliability RCAs (AR hang watchdog evidence, HIP IMA serialized-envelope proof, close() memory) | GPU windows | gates R5 |
| 9 | M5 metric matrix + perf characterization | GPU windows | gates R6 |
| 10 | M6 security/licensing scan of integration tree + historical Git objects | CPU | gates R7 |
| 11 | M7 upstream/author packages (no submission) | CPU | gates R9 inputs |
| 12 | M8 fresh-clone reproduction + blog package | CPU + GPU smoke | gates R8 |

## Exact release blockers (at P0)

- R1 FAIL: PR #13 CI red (M1.1) + integration not built (M1.4).
- R2 evidence complete on host; needs packaging into repo evidence chain.
- R3 BLOCKED: armB_acceptance retry loop (live defect) — then ~days of GPU.
- R4 BLOCKED: PER gap +8.4pp (Arm A) / +9.3pp (Arm B) vs 8.44% official;
  cross-evaluator kits + author collaboration required.
- R5 PARTIAL: historical RCA evidence; fresh-image revalidation NOT_TESTED.
- R6/R7/R8 NOT_TESTED. R9/R10 absent (no author/AMD contact yet).

## External dependencies

- YuE2 authors: reference audio or CUDA-side scoring (M3.2 C2/A2/B2),
  protocol clarifications, Q3O feasibility, publication claims review.
- AMD reviewers: blog acceptance.
- CUDA hardware (A2/B2/C2 columns): unavailable on this host → prepare
  `BLOCKED_EXTERNAL` handoff kits, never fabricate.
