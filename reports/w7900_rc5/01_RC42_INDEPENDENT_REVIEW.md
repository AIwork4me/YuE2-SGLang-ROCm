# RC5 M1 — RC4.2 Independent Review: Fail-Closed Closure of the RC4.1 Static Findings

Reviewed head: `6f1b7f7631a9b1d3775d35ed5780ba6fb6c942fe` (PR #18 head).
Order of work for every item: REPRODUCE → ROOT CAUSE → MINIMAL FIX → POSITIVE
CONTROL → NEGATIVE CONTROL → REGRESSION → REAL GPU VALIDATION.

| finding | severity | still present at 6f1b7f7? | disposition |
|---|---|---|---|
| GPU lock lifecycle atomicity | **P0** | yes — reproduced deterministically | **CLOSED** |
| GPU probe hard timeout | P1 | yes — `budget_s` was never enforced | **CLOSED** |
| Readiness semantics | P1 | yes — four gaps | **CLOSED** |
| Physical GPU identity binding | P1 | yes — "first AMD GPU" fallback | **CLOSED** (single GPU on hardware) |
| Upstream scheduler RCA | — | unchanged upstream | **OPEN_UPSTREAM** (mitigated) |

Machine-readable closure: `01_P0_P1_CLOSURE.json`. Controls:
`01_NEGATIVE_CONTROL_MATRIX.csv`. Mutations: `01_MUTATION_RESULTS.json`.

## 1. P0 — GPU lock lifecycle atomicity

**Reproduction (before any fix).** `scripts/campaign_ops/rc5_repro_lock_race.py`
runs the real launcher of a given checkout against a stub server that needs
6 s to exit after SIGINT and samples (lock held?, server alive?) every 100 ms
after the wrapped command returns.

| launcher | samples with lock free **and** server alive | window |
|---|---|---|
| RC4.1 `6f1b7f7` | 47 | 5.96 s (first at +0.03 s) |
| RC5 working tree | 0 | — |

**Root cause.** The flock lived in a background gateway (`gpu_lock.py wait`);
the server stop lived in the outer shell's `EXIT` trap. The gateway released
the lock as soon as the inner flow returned — the trap ran afterwards. Three
further defects shared the same root: (a) a server that never became healthy
had no identity receipt, so `stop_server` returned success and the process
survived — the RC4.1 test masked this with its own `kill_all()`; (b) no
verification of process-tree termination, port release or GPU release;
(c) the gateway died on SIGINT/SIGTERM and took the lock with it while its
child was still draining.

**Fix (minimal, one owner).** `scripts/gpu_lifecycle.py` — one process holds
the flock fd for its whole life and performs, in order: identity → idle →
launch (spawn receipt: pid + starttime + session) → health → identity (capture
pinned with `--pid`) → readiness → command → drain → verified stop → tree
termination → port release → GPU release; only then is the lock released.
`run_with_server.sh` and `run_armB_campaign.sh` `exec` into it. In
`gpu_lock.py`: a `<lock>.BLOCKED` marker (later acquisitions refuse until
`unblock --yes` finds the recorded processes dead) and a signal-safe `wait`
gateway (forward, keep the flock while the child drains).

**Ownership rule.** A signal is only ever sent to (a) the verified server pid
(identity receipt whose pid/starttime equal the spawn receipt), (b) the
verified spawned leader, (c) processes proven to be in the session we created,
(d) our own driver's process group. Never by name or port, never SIGKILL for
a server (BLOCKED instead).

**Found by the new tests while fixing (not in the RC4.1 list).**
* Identity discovery by argv + port could bind the receipt to a foreign
  process that legitimately owned the port; cleanup then signalled it. Fixed by
  pinning the capture to the spawned pid **and** a receipt-ownership check
  before any stop (two layers; each has its own test after mutation L2/L3
  survived the first round).
* A receipt left by an earlier session is now moved aside, never used.
* A SIGSTOPped scheduler (state `T`) counted as a live worker → now `WORKER_DEAD`.

**Controls.** 20 real-process tests (`tests/test_gpu_lifecycle_atomicity.py`):
deterministic barrier inside the cleanup phase (a second job is refused while
the first server is still alive), SIGINT/SIGTERM/repeated signal, boot failure
without receipt, look-alike server on the port, replaced and stale receipts,
stubborn server and stubborn scheduler member (BLOCKED, next job refused,
`unblock` refused while alive), foreign decoy untouched in every scenario.

**Residual.** SIGKILL to the supervisor releases the flock early by kernel
design; the next session is still refused by the VRAM idle floor while an
orphan holds memory, and the receipts on disk allow a verified manual stop.

## 2. P1 — GPU probe hard timeout

**Reproduction.** `probe_device(torch_ns, budget_s)` never used `budget_s`;
nothing raised `TimeoutError`, so `GPU_PROGRESS_TIMEOUT` could not occur.
**Fix.** The probe (fp32 256² matmul checked against a CPU recompute, bf16
1024² matmul, SDPA FLASH / EFFICIENT against the MATH reference) runs in a
separate child under a wall-clock deadline. On expiry the child is SIGTERMed,
then SIGKILLed; the receipt carries the evidence and `device_state=BLOCKED`
when the child is uninterruptible or VRAM did not return. A real (non-injected)
runtime cannot take the in-process path any more. Controls: a real hung child
is stopped at the deadline (mutation P1 "unbounded again" is killed), a failing
child is `GPU_EXECUTION_FAILED`, an unrecovered device is BLOCKED.
`CPU_TEST_MODE_AUTHORIZED` requires the explicit token, is labelled "never a
GPU PASS", and makes the lifecycle record GPU checks as `NOT_APPLICABLE`.

## 3. P1 — Readiness semantics

| gap at 6f1b7f7 | fix | control |
|---|---|---|
| `models_advertised_ok` recorded, unused | gates the verdict → `UNKNOWN` rc 4 | HTTP 200 + other model |
| identity verified with `require_port=None` | URL port = receipt port; LISTEN socket owned by the verified pid | foreign listener, URL port mismatch, no listener |
| missing progress file ignored | `UNKNOWN` rc 4 | missing file; stale → BUSY rc 6 |
| canary: any file > 1024 bytes | decodes: 48 kHz, stereo, finite, ≥ 1 s, not silence, fresh | 4 KB zeros, silence, 16 kHz mono, leftover file |
| (new) SIGSTOPped worker | `WORKER_DEAD` | state T with /health 200 |

The eight required cases: HTTP 200 + worker dead, + wrong model, + wrong
process/port, zombie worker, alive-but-no-progress, progress file missing,
canary failure, healthy idle server — all covered.

## 4. P1 — Physical GPU identity binding

The fallback returned the PCI slot of the first amdgpu card in sysfs. This
host exposes eight identical cards in `/sys/class/drm` and one render node to
the container — exactly the case where the guess is wrong. `bind_pci_identity()`
builds a closed chain and fails closed on any ambiguity; unit tests simulate
multi-GPU and same-arch hosts and a container given GPU #5 of 8. On the real
W7900D the chain closes end to end. Two facts were learned only on hardware:
the GPU occupies two PCI functions (a strict "exactly one function" rule
rejected the real card → class-0x03 filter), and KFD nodes of other tenants'
GPUs are unreadable (skipped, disclosed). **Physical multi-GPU validation:
NOT_RUN** (one GPU is exposed to this container).

## 5. Upstream scheduler recheck (M1.5)

| item | status at the latest upstream head | handling |
|---|---|---|
| idle busy-loop | still in the multimodal scheduler loop (code review) | session-scoped server: the supervisor stops it after every session |
| worker death without respawn | unchanged | readiness → `WORKER_DEAD`; supervised relaunch |
| HTTP false health | unchanged | detected (`/health`=200 with a dead or stopped worker) |
| historical AR hang, HIP illegal memory access | not reproduced in RC5 (12/12 pilot candidates, 0 retries) | single-GPU serialization kept |

## 6. Regression and mutation evidence

* Existing lifecycle suites pass against the new supervisor:
  `tests/test_run_with_server.py` (5), `tests/test_armB_lifecycle.py` (16).
* New: atomicity 20, spawn-ownership 11, gpu_identity 35, readiness 28,
  driver integration 5.
* Mutation controls (`scripts/mutation_controls_rc5.py`, isolated copy,
  byte-exact restore): **37 mutations, 37 KILLED** after three real test gaps
  were found and closed (L2/L3: redundant guards each needed their own oracle;
  D6: the driver test did not check the seed actually sent).
