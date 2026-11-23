# RC4.1 M1 — GPU Fail-Loud RCA & Execution Identity (W7900D, gfx1100)

Date: 2026-11-22/23 UTC. Host: j-7uqnwhrwmv2s44k6zdqzoq5idj
(ROCm 7.2.1 host / 7.14.1 userspace wheels, torch 2.12.0+rocm7.14.1,
HIP 7.14.60850, AMD Radeon PRO W7900D 48 GB gfx1100, PCI 0000:03:00.0,
51522830336 bytes VRAM = 47.98 GiB = 51.5 decimal GB).

## 1. The RC4 suspected "silent CPU fallback" — re-analysis

Original evidence (`/data/yue2-runs/rc4_evidence/cpu_fallback_suspect_wsb_001_r1.txt`,
re-read this mission, byte-identical, SHA256 in the frozen manifest):

- native-path worker PID 1187388: ELAPSED 47:10, %CPU 192, state R, 129 threads
- voluntary/nonvoluntary ctx switches 5739/11479
- KFD process table at the same instant lists OTHER pids; 1187388 absent
- total VRAM in use 2.73 GB (external tenant active)

Facts that CONSTRAIN the diagnosis:

1. `run_wsb_torch.py` pins the pipeline to `device="cuda:0"` (scripts/
   run_wsb_torch.py:400). There is NO device-selection branch anywhere in
   the native path that could "fall back" to CPU — a classic silent-fallback
   code path does not exist here.
2. The native path runs the official yue2-infer torch-eager backend with a
   24 GiB memory budget under which weights are largely host-resident and
   streamed (`03_RESOURCE_ENVELOPE.md`): host->device transfer is part of
   normal operation.
3. "No KFD context" proves the process executed no GPU work IN THAT WINDOW,
   but does NOT distinguish between (a) CPU-only execution, (b) a process
   stalled BEFORE its first GPU op (model load / H2D under VRAM pressure
   from the external tenant), (c) allocator retry loops.
4. 129 threads + ~191% CPU + state R is consistent with a loader/transfer
   spin, not with single-threaded eager CPU inference of a 3B model (which
   would be expected to show higher sustained CPU and steady progress).

Verdict: **SUSPECT_UNCONFIRMED (mechanism)** — the incident is NOT proven to
be CPU fallback; the most plausible mechanism is a host-side load/transfer
stall under external VRAM pressure, but no stack was captured (yama=1,
no CAP_SYS_PTRACE in RC4) so this remains a hypothesis. What is CONFIRMED:

- the observation was invisible to existing tooling (no device-identity
  receipt, no execution receipt, no progress receipt) — the actual blind
  spot, and it is now closed (below).

## 2. Device identity chain — implementation

`scripts/gpu_identity.py` (new): single tool + library API recording
expected-vs-actual GPU identity, framework facts (torch.version.hip —
the `torch.cuda` API namespace is normal on ROCm and is NOT an NVIDIA
indicator; only `torch.version.cuda` being set would be), device props
(name, gcnArchName, PCI BDF via props/sysfs, total memory in bytes AND
GiB), KFD visibility (/dev/kfd + render nodes), worker identity
(pid/starttime/cmdline), and an ACTIVE EXECUTION probe (256×256 fp32 matmul
on device, CPU-recomputed entry cross-check) with placement receipt
(`probe_device`).

Statuses: GPU_IDENTITY_VERIFIED · GPU_EXECUTION_VERIFIED ·
GPU_EXECUTION_UNVERIFIED · GPU_DEVICE_MISMATCH · GPU_UNAVAILABLE ·
GPU_PROGRESS_TIMEOUT · GPU_EXECUTION_FAILED · CPU_TEST_MODE_AUTHORIZED.
Contract: **GPU_REQUIRED by default**; CPU only with explicit
`--allow-cpu` / `YUE2_ALLOW_CPU=1-I-AM-A-TEST` and is then labeled
CPU_TEST_MODE_AUTHORIZED — never a GPU PASS. Failed candidates never
report `ok`; receipts are machine-readable JSON with verdict PASS/FAIL.

Integration: `run_with_server.sh` refuses to boot the server unless
gpu_identity verify passes first (step 1/7).

## 3. Verification matrix

CPU/mock (CI, `tests/test_gpu_identity.py`, 15 tests): GPU not available →
GPU_UNAVAILABLE fail; CUDA-only build → GPU_DEVICE_MISMATCH; wrong arch →
mismatch; wrong PCI BDF → mismatch; props failure → unavailable; probe
error → GPU_EXECUTION_FAILED; probe wrong result → GPU_EXECUTION_FAILED;
no CPU authorization → unavailable; explicit authorization →
CPU_TEST_MODE_AUTHORIZED; normal CPU pre/post-processing unaffected
(probe placement distinguishes device strings); import failure →
GPU_UNAVAILABLE.

Real W7900 (`/data/yue2-runs/rc4_1_evidence/20261122T2300Z/phase_a/`):

| Case | Interpreter | Result | rc |
|---|---|---|---|
| Env B (sglang stack) verify+probe | yue2-gfx1100 | GPU_EXECUTION_VERIFIED (gfx1100, 0000:03:00.0, 47.98 GiB) | 0 |
| Env A (native torch stack) verify+probe | yue2-torch | GPU_EXECUTION_VERIFIED | 0 |
| NC wrong expected arch (gfx1200) | yue2-gfx1100 | GPU_DEVICE_MISMATCH | 3 |
| NC wrong expected BDF (0000:ff:00.0) | yue2-gfx1100 | GPU_DEVICE_MISMATCH | 3 |

(The "GPU absent without CPU authorization" branch cannot be produced on a
GPU-present host without unsafe driver manipulation — covered by mocked
tests; hardware gate intentionally not faked.)

## 4. What this changes for the original suspect

If the RC4 incident recurs under the new contract, the worker's identity
receipt will show either GPU_UNAVAILABLE/GPU_DEVICE_MISMATCH at startup
(fail-loud before any work) or GPU_EXECUTION_VERIFIED + a generation-time
progress record; a silent third state no longer exists in project-run
workloads. The incident itself is not reproducible on demand (it required
an external GPU tenant pressure window) and is closed as
SUSPECT_UNCONFIRMED with the blind spot removed.

## 5. Output artifacts

- `01_GPU_IDENTITY_MATRIX.csv` — full matrix rows
- `01_FAIL_LOUD_TESTS.md` — test inventory and results
- `01_GPU_VERDICT.json` — machine verdict
- receipts: `phase_a/gpu_identity_env{A,B}.json`, NC outputs
