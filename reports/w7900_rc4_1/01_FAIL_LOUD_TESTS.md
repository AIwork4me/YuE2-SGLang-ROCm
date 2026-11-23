# RC4.1 — Fail-loud test inventory (M1.4)

Unit/mocked battery: `tests/test_gpu_identity.py` (15 tests) — see
`01_GPU_IDENTITY_MATRIX.csv` for the per-case mapping. Real-G7900
hardware results: `phase_a/` receipts (this file's §Hardware).

## States exercised (requirement → where)

- GPU not available → GPU_UNAVAILABLE fail (mock: test_gpu_unavailable_*)
- HIP runtime unavailable (torch import failure) → GPU_UNAVAILABLE
  (test_torch_import_failure_is_unavailable)
- Wrong target device arch → GPU_DEVICE_MISMATCH rc3 (mock + real NC)
- CUDA-only build → GPU_DEVICE_MISMATCH (test_cuda_only_build_rejected)
- Incorrect expected PCI BDF → GPU_DEVICE_MISMATCH rc3 (real NC +
  test_wrong_bdf_mismatch / test_matching_bdf_passes)
- Invalid identity metadata (props read failure) → GPU_UNAVAILABLE
- GPU diagnostic probe error → GPU_EXECUTION_FAILED rc5
  (test_probe_failure_is_execution_failed; wrong result →
  test_probe_wrong_result_fails)
- Missing progress receipt (probe timeout class) → GPU_PROGRESS_TIMEOUT
  state exists; produced only under real hang (NOT_TESTED on hardware —
  no safe way to hang the GPU without driver abuse; mocked coverage of
  the state machine via status table)
- No explicit CPU authorization → GPU_UNAVAILABLE (mock; on-GPU host the
  branch is unreachable without unsafe driver manipulation — honestly
  recorded, not faked)
- Explicitly authorized CPU test mode → CPU_TEST_MODE_AUTHORIZED, never
  GPU PASS (test_cpu_authorized_is_test_mode_not_gpu_pass; token
  YUE2_ALLOW_CPU=1-I-AM-A-TEST also exercised live by the lifecycle test
  suite's stub stack)
- Normal CPU pre/post-processing → allowed by contract; GPU model
  execution distinguished via probe placement receipts (probe_device)

## Hardware results (real W7900D)

| Test | Result |
|---|---|
| Env B verify+probe | GPU_EXECUTION_VERIFIED, rc 0 (gfx1100 @ 0000:03:00.0, 47.98 GiB) |
| Env A verify+probe | GPU_EXECUTION_VERIFIED, rc 0 |
| NC wrong arch (gfx1200) | GPU_DEVICE_MISMATCH, rc 3 |
| NC wrong BDF (0000:ff:00.0) | GPU_DEVICE_MISMATCH, rc 3 |
| run_with_server boot gate | wrapper refuses to start server on identity failure (unit-tested; live path exercised by B1 boot gate step 1/7 GPU_EXECUTION_VERIFIED) |

## Failure-candidate semantics

A failed identity/probe never marks anything complete: gpu_identity
receipts carry verdict FAIL; run_with_server treats rc!=0 as lifecycle
failure before any server boot; evidence receipts are retained (never
deleted on failure paths).
