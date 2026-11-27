# M3.5 — Physical GPU Lock Domain

## Contract

- **Domain identity**: the exposed amdgpu PCI BDF (`resolve_physical_gpu()`):
  exactly one visible render node -> BDF + `unique_id`; ambiguity resolves to
  None (legacy fallback, disclosed). The logical HIP ordinal NEVER names a
  domain (it can differ per process/container).
- **Default lock**: `$YUE2_GPU_LOCK` (explicit file) > `$YUE2_GPU_LOCK_ROOT`
  (shared root) > `/var/lock/yue2-gpu/gpu-<BDF>.lock` > legacy
  `<YUE2_WORKSPACE>/gpu.lock` (unshared, disclosed).
- **Scope**: the mutex holds where the shared root is commonly mounted
  (same container/user). Containers or users with distinct roots are OUTSIDE
  the cross-workspace protocol — the receipt discloses `legacy_workspace_fallback`
  rather than assuming protection.
- **Receipt**: every acquisition records `lock_domain` {name, physical,
  shared} and `workspace` (env-level binding used by `reference stop`).
- **Stop**: only the recorded holder pid is signalled (SIGINT/SIGTERM, no
  SIGKILL, no pkill -f); wrong-workspace / wrong-run-id stops are REFUSED.
- **BLOCKED marker**: domain-scoped; acquisition is refused until an operator
  runs `gpu_lock.py unblock --yes` (recorded processes verified gone).

## Live evidence (this rig)

- Domain: `gpu-0000:03:00.0` (uuid `e9d0e20bb686e6c6`, render node
  `renderD128`); lock file `/var/lock/yue2-gpu/gpu-0000:03:00.0.lock`.
- Host has 8 amdgpu functions; THIS container exposes exactly one — the
  domain covers the visible device, sibling GPUs are not addressable.
- Cross-workspace contention + real GPU compute under workspace B's lock:
  see `03_CROSS_WORKSPACE_CONTENTION.json` (9/9 PASS, `--physical` run).
