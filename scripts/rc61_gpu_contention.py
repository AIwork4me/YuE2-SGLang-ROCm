#!/usr/bin/env python3
"""rc61_gpu_contention.py — M3.5/M3.7 physical GPU lock-domain contention test.

Proves, with two DIFFERENT workspaces on the same physical GPU:
  1. A holds the shared lock  ->  B's acquisition returns LOCK_CONTENTION
     (TimeoutError) — B cannot start GPU work;
  2. reference stop --workspace B is REFUSED while A holds the lock
     (cross-workspace stop safety, M3.6);
  3. safe stop of A (graceful signal to the recorded holder only);
  4. B then acquires and runs a REAL GPU workload under the lock
     (--physical: torch compute on gfx1100 via the generation venv);
  5. stale-lock reclaim and BLOCKED-marker scope on the shared domain;
  6. the legacy fallback (unwritable shared root) is disclosed, not silent.

Usage:
  python3 scripts/rc61_gpu_contention.py            # lock-domain semantics
  python3 scripts/rc61_gpu_contention.py --physical # + real GPU compute under B
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import gpu_lock  # noqa: E402

HOLDER_ENV = "RC61_CONTENTION_HOLDER"


def holder_main() -> int:
    """Workspace A's 'GPU workload': holds the lock for N seconds."""
    with gpu_lock.gpu_ownership("wsA-holder", wait_s=0):
        print(json.dumps({"holder": "acquired", "pid": os.getpid()}), flush=True)
        time.sleep(float(os.environ.get("RC61_HOLD_S", "60")))
    return 0


def run_cli(args: list[str], env: dict | None = None) -> tuple[int, str]:
    e = dict(os.environ)
    if env:
        e.update({k: str(v) for k, v in env.items()})
    p = subprocess.run([sys.executable, str(REPO / "scripts/reference_cli.py")]
                       + [str(a) for a in args], capture_output=True, text=True,
                       env=e, timeout=120)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    if os.environ.get(HOLDER_ENV):
        return holder_main()
    ap = argparse.ArgumentParser()
    ap.add_argument("--physical", action="store_true",
                    help="run a real GPU compute workload under workspace B's lock")
    ap.add_argument("--workspace-a", default="/tmp/opencode/rc61_wsA")
    ap.add_argument("--workspace-b", default="/tmp/opencode/rc61_wsB")
    a = ap.parse_args()

    for w in (a.workspace_a, a.workspace_b):
        Path(w).mkdir(parents=True, exist_ok=True)

    steps = []
    lock = gpu_lock.resolve_default_lock()
    domain = gpu_lock.lock_domain_name(gpu_lock.resolve_physical_gpu())

    def step(name, ok, detail=None):
        steps.append({"step": name, "pass": bool(ok), "detail": detail})
        print(f"[contention] {name}: {'PASS' if ok else 'FAIL'}")
        return ok

    # 1) A holds the lock
    env_a = {**os.environ, HOLDER_ENV: "1", "RC61_HOLD_S": "45",
             "YUE2_WORKSPACE": a.workspace_a}
    holder = subprocess.Popen([sys.executable, __file__], env=env_a,
                              stdout=subprocess.PIPE, text=True)
    line = holder.stdout.readline()
    acquired = json.loads(line) if line.startswith("{") else {}
    step("A acquires the shared physical lock", acquired.get("holder") == "acquired",
         {"pid": acquired.get("pid"), "lock": str(lock), "domain": domain})
    time.sleep(1.0)

    # 2) B (different workspace, same GPU) cannot acquire
    env_b = {**os.environ, "YUE2_WORKSPACE": a.workspace_b}
    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r)\n"
         "import gpu_lock\n"
         "try:\n"
         "    with gpu_lock.gpu_ownership('wsB-probe', wait_s=3):\n"
         "        print('ACQUIRED')\n"
         "except TimeoutError as e:\n"
         "    print('LOCK_CONTENTION')" % str(REPO / "scripts")],
        capture_output=True, text=True, env=env_b, timeout=30)
    step("B is refused (LOCK_CONTENTION, no new GPU workload)",
         probe.stdout.strip() == "LOCK_CONTENTION", {"out": probe.stdout.strip()})

    # 3) B cannot stop A's session
    rc, out = run_cli(["stop", "--workspace", a.workspace_b], env=env_b)
    step("reference stop --workspace B is REFUSED while A holds",
         rc == 4 and "REFUSED" in out, {"rc": rc})

    # 4) safe stop of A (targets the recorded holder pid only)
    rc, out = run_cli(["stop", "--workspace", a.workspace_a], env=env_a)
    holder.wait(timeout=60)
    st = gpu_lock.status()
    step("safe stop of A releases the domain",
         rc == 0 and not st["holder_live"], {"rc": rc, "holder_live": st["holder_live"]})

    # 5) B acquires and (optionally) runs real GPU work under the lock
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import gpu_lock\n"
            "with gpu_lock.gpu_ownership('wsB-workload', wait_s=5):\n"
            "    print('B-LOCKED')" % str(REPO / "scripts"))
    if a.physical:
        code = ("import sys; sys.path.insert(0, %r)\n"
                "import gpu_lock\n"
                "with gpu_lock.gpu_ownership('wsB-gpu-compute', wait_s=5):\n"
                "    import torch\n"
                "    x = torch.randn(2048, 2048, device='cuda', dtype=torch.bfloat16)\n"
                "    y = (x @ x).sum().item()\n"
                "    print('B-GPU-COMPUTE-OK', torch.cuda.get_device_name(0), y != 0)\n"
                % str(REPO / "scripts"))
        venv = Path("/data/yue2/environments/generation/bin/python")
        probe = subprocess.run([str(venv), "-c", code], capture_output=True,
                               text=True, env=env_b, timeout=300)
    else:
        probe = subprocess.run([sys.executable, "-c", code], capture_output=True,
                               text=True, env=env_b, timeout=60)
    step("B acquires the domain after release"
         + (" and runs real GPU compute" if a.physical else ""),
         (("B-GPU-COMPUTE-OK" in probe.stdout and "True" in probe.stdout)
          if a.physical else "B-LOCKED" in probe.stdout),
         {"out": probe.stdout.strip()[:200], "rc": probe.returncode})

    # 6) stale receipt reclaim on the shared domain
    lock.write_text(json.dumps({"who": "ghost", "pid": 999999,
                                "cmdline": "dead-process"}))
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import gpu_lock\n"
            "with gpu_lock.gpu_ownership('stale-reclaimer', wait_s=0):\n"
            "    print('STALE-RECLAIMED')" % str(REPO / "scripts"))
    probe = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=60)
    step("stale receipt is reclaimed (flock is authoritative)",
         "STALE-RECLAIMED" in probe.stdout, {"out": probe.stdout.strip()[:120]})

    # 7) BLOCKED marker scope: the domain refuses acquisition until unblock
    gpu_lock.mark_blocked(None, "test-blocked", [{"pid": 999999, "starttime": "1",
                                                  "role": "ghost"}], "contention test")
    refused = subprocess.run([sys.executable, "-c",
                              "import sys; sys.path.insert(0, %r)\n"
                              "import gpu_lock\n"
                              "try:\n"
                              "    with gpu_lock.gpu_ownership('blocked-probe'):\n"
                              "        print('ACQUIRED')\n"
                              "except gpu_lock.GpuBlockedError:\n"
                              "    print('REFUSED-BLOCKED')" % str(REPO / "scripts")],
                             capture_output=True, text=True, timeout=60)
    step("BLOCKED marker refuses acquisition in the domain",
         "REFUSED-BLOCKED" in refused.stdout)
    unblock = subprocess.run([sys.executable, str(REPO / "scripts/gpu_lock.py"),
                              "unblock", "--yes"], capture_output=True, text=True,
                             timeout=60)
    step("operator unblock clears the marker (evidence kept)",
         unblock.returncode == 0, {"out": unblock.stdout.strip()[:120]})

    # 8) legacy fallback disclosure (unwritable shared root)
    env_legacy = {**os.environ, "YUE2_GPU_LOCK_ROOT": "/proc/no-such-lock-root",
                  "YUE2_WORKSPACE": a.workspace_b}
    probe = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, %r)\n"
                            "import gpu_lock\n"
                            "p = gpu_lock.resolve_default_lock()\n"
                            "print('LEGACY' if str(p).endswith('gpu.lock') else 'SHARED')"
                            % str(REPO / "scripts")],
                           capture_output=True, text=True, env=env_legacy, timeout=60)
    step("unwritable shared root falls back to the workspace lock (disclosed)",
         probe.stdout.strip() == "LEGACY", {"out": probe.stdout.strip(),
                                            "note": "cross-workspace protection "
                                                    "does NOT hold in this mode"})

    ok = all(s["pass"] for s in steps)
    report = {
        "schema": "yue2-rc6_1-cross-workspace-contention/1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lock_domain": {"lock": str(lock), "name": domain,
                        "physical": gpu_lock.resolve_physical_gpu()},
        "workspace_a": a.workspace_a, "workspace_b": a.workspace_b,
        "physical_gpu_compute": bool(a.physical),
        "steps": steps, "verdict": "PASS" if ok else "FAIL",
        "scope_note": "cross-workspace mutex holds where the shared lock root is "
                      "commonly mounted; containers/users with distinct roots are "
                      "outside this protocol (disclosed, not assumed)",
    }
    out = REPO / "reports/developer_reference/rc6_1/03_CROSS_WORKSPACE_CONTENTION.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"verdict": report["verdict"], "report": str(out)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
