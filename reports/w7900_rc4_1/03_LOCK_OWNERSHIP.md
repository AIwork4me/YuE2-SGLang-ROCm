# RC4.1 — GPU lock ownership during RC4.1 sessions

## Contract

Every GPU-touching session in this mission ran inside ONE continuous
`gpu_ownership` hold:

| Session | Lock holder `who` | Scope held | Release evidence |
|---|---|---|---|
| phase A (identity chain + NCs) | `rc41-phase-a-identity` | all probes (Env A + Env B) | gpu_lock status post-run: held=false |
| phase B1 (real server + generations) | `rc41-lifecycle-20261122T234057Z` (run_with_server.sh) | boot → identity → readiness → short gen → repeated-tags (short + default) → idle sample → verified stop | in-session `gpu_lock status` (probe inside the command): held=true, holder who matches; post-run held=false with release receipt |
| phase B2 (scheduler death + recovery) | `rc41-b2-scheduler-death` | boot → kill → ladder → reboot → final stop | release receipt; VRAM 28,028,928 B after |
| phase C (native pilot) | `armA-campaign:rc41_native_pilot` (run_wsb_torch's own gpu_ownership) | whole native run incl. model load + 2 candidates | gpu_lock release receipt |

## Negative controls (from the existing suite, re-run green)

- contention: second holder fails closed with bounded wait (tests/
  test_run_with_server.py + armB lifecycle suite)
- SIGINT/SIGTERM/exit all release the lock (flock released on process
  death by the kernel; receipts written by gpu_lock.py itself)
- the RC4 self-reported `wait -- true` instant-release pattern is not used
  anywhere in RC4.1 sessions

## Live proof snapshot (phase B1)

`gpu_lock.py status` executed from INSIDE the wrapped command showed:

```json
{"lock": "/data/yue2/gpu.lock", "held": true,
 "holder": {"who": "rc41-lifecycle-20261122T234057Z", ...}}
```

and after wrapper exit: `held: false` + `released_at_utc` recorded.
Full output archived in phase_b1.log.
