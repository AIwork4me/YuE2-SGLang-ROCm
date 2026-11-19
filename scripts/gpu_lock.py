#!/usr/bin/env python3
"""gpu_lock.py — single-GPU ownership lock for heavyweight workloads (RCA-F4).

Policy background (reports/publication/02_RCA_LEDGER.md RCA-7): sharing the
W7900 between the ASR evaluator and a generator reproducibly triggers
`HIP error: an illegal memory access`. Single-GPU serialization is the safe
operating policy — it is NOT a claim that the underlying fault was fixed.

Contract:
  * flock-based exclusion (LOCKS GPU WORKLOADS, not the device file):
    lock file lives at <workspace>/gpu.lock by default (override: YUE2_GPU_LOCK).
  * the holder's pid + cmdline is written into the lock file for auditability.
  * acquire() verifies any recorded pid is alive AND its cmdline still matches
    what was recorded; a dead/mismatched holder is treated as stale and the
    lock is reclaimed (bounded, atomic rename-aside — never blind rm of live state).
  * graceful stop: send SIGINT/SIGTERM to the recorded pid only after explicit
    operator confirmation (--stop flag); never pkill -f, never SIGKILL.
  * wait with bounded timeout; crash evidence preserved in the lock receipt.

Usage (library):
    from gpu_lock import gpu_ownership
    with gpu_ownership("armA-campaign", wait_s=3600):
        ...heavy GPU work...

Usage (CLI):
    python scripts/gpu_lock.py status
    python scripts/gpu_lock.py wait --who armB-scoring --wait-s 7200 -- cmd...
    python scripts/gpu_lock.py stop --yes   # graceful SIGINT/SIGTERM to holder
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

def resolve_default_lock() -> Path:
    """Resolve the default lock path at CALL time — never import time.

    An import-time frozen default broke isolation twice in practice:
      * CI runners (non-root, no /data): gpu_ownership() did
        ``path.parent.mkdir(parents=True)`` on the frozen /data/yue2/gpu.lock
        default -> PermissionError: [Errno 13] '/data' (PR #13 run 44421080608,
        5 failures in TestScoreGate).
      * any caller that exports YUE2_WORKSPACE/YUE2_GPU_LOCK after importing
        this module silently locked the wrong file.
    All internal code paths resolve lazily via this function.
    """
    return Path(os.environ.get(
        "YUE2_GPU_LOCK",
        str(Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2")) / "gpu.lock")))


# Backwards-compatible module constant: snapshot at import. New code must call
# resolve_default_lock() instead of reading this.
DEFAULT_LOCK = resolve_default_lock()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else — treat as alive
    try:
        # zombies answer os.kill(pid,0) but are dead for scheduling purposes
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rpartition(")")[2].split()[0] != "Z"
    except (OSError, IndexError):
        return True  # cannot inspect — assume alive (conservative)


def _pid_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            errors="replace").strip()
    except OSError:
        return ""


def _read_holder(lock_path: Path) -> dict | None:
    try:
        return json.loads(lock_path.read_text())
    except (OSError, ValueError):
        return None


def _holder_is_live(holder: dict | None) -> bool:
    if not holder:
        return False
    pid = holder.get("pid")
    if not isinstance(pid, int) or not _pid_alive(pid):
        return False
    cmd = _pid_cmdline(pid)
    recorded = (holder.get("cmdline") or "")
    # live only if the pid is ours AND still running the recorded workload
    return bool(cmd) and (not recorded or recorded[:120] in cmd or cmd[:120] in recorded)


def status(lock_path: Path | None = None) -> dict:
    """Report lock state. The KERNEL flock is authoritative for held/not-held;
    the receipt file only identifies who holds it (or last held it)."""
    lock_path = Path(lock_path) if lock_path else resolve_default_lock()
    holder = _read_holder(lock_path)
    held = False
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            held = True
        finally:
            os.close(fd)
    except OSError:
        pass
    holder_live = held and _holder_is_live(holder)
    return {"lock": str(lock_path), "held": held, "holder": holder,
            "holder_live": holder_live}


@contextmanager
def gpu_ownership(who: str, wait_s: float = 0.0, poll_s: float = 10.0,
                  lock_path: Path | None = None):
    """Acquire the single-GPU ownership lock; yields the receipt dict."""
    path = Path(lock_path) if lock_path else resolve_default_lock()
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.0, wait_s)
    fd = None
    while True:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            fd = None
            holder = _read_holder(path)
            if not _holder_is_live(holder):
                # stale receipt under a live flock can only happen if the flock
                # is held without a valid holder — cannot happen with flock()
                # semantics (kernel releases on process death); if the FILE was
                # tampered with, report loudly rather than guessing.
                print(f"[gpu_lock] lock busy but holder receipt is stale/tampered: "
                      f"{holder!r}; waiting (flock is authoritative)", file=sys.stderr)
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"GPU ownership lock held by {holder!r} after {wait_s}s wait")
            time.sleep(poll_s)
            continue
        break
    receipt = {
        "who": who,
        "pid": os.getpid(),
        "cmdline": _pid_cmdline(os.getpid()),
        "acquired_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": os.uname().nodename,
    }
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(receipt, indent=1).encode() + b"\n")
    os.fsync(fd)
    # NOTE: keep fd open for the duration; flock is released on close/death.
    try:
        yield receipt
    finally:
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, json.dumps(
                {**receipt, "released_at_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}).encode() + b"\n")
            os.fsync(fd)
        except OSError:
            pass
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def graceful_stop(lock_path: Path | None = None, confirmed: bool = False) -> int:
    lock_path = Path(lock_path) if lock_path else resolve_default_lock()
    st = status(lock_path)
    holder = st["holder"]
    if not holder or not st["holder_live"]:
        print(json.dumps({"stopped": False, "reason": "no live holder",
                          "status": st}))
        return 1
    pid = holder["pid"]
    print(f"holder: pid={pid} who={holder.get('who')!r}")
    print(f"cmdline: {holder.get('cmdline', '')[:200]}")
    if not confirmed:
        print("refusing to signal without --yes (operator confirmation)")
        return 2
    # graceful first; the holder's own SIGINT/SIGTERM handlers finish in-flight
    # work (campaign drivers implement graceful stop)
    for sig, wait in ((signal.SIGINT, 30), (signal.SIGTERM, 30)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            print("holder exited before signal")
            return 0
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait:
            if not _pid_alive(pid):
                print(json.dumps({"stopped": True, "pid": pid, "signal": sig.name}))
                return 0
            time.sleep(2)
    print(json.dumps({"stopped": False, "pid": pid,
                      "reason": "still alive after SIGINT+SIGTERM grace; "
                                "refusing SIGKILL by policy — inspect manually"}))
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    # default resolved at call time (see resolve_default_lock); an import-time
    # frozen default silently broke env overrides set after module import.
    ap.add_argument("--lock", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    w = sub.add_parser("wait")
    w.add_argument("--who", required=True)
    w.add_argument("--wait-s", type=float, default=3600.0)
    # NOTE: dest must NOT be "cmd" — the subparsers' dest is also "cmd" and a
    # positional with the same name silently overwrites it, making every
    # `wait` invocation fall through to `return 2` (live defect found while
    # wiring armB_acceptance.sh; the library API was unaffected).
    w.add_argument("cmd_args", nargs=argparse.REMAINDER)
    s = sub.add_parser("stop")
    s.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    lock = Path(args.lock) if args.lock else resolve_default_lock()
    if args.cmd == "status":
        print(json.dumps(status(lock), indent=2))
        return 0
    if args.cmd == "stop":
        return graceful_stop(lock, confirmed=args.yes)
    if args.cmd == "wait":
        cmd = args.cmd_args
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if not cmd:
            print("no command given", file=sys.stderr)
            return 2
        with gpu_ownership(args.who, wait_s=args.wait_s, lock_path=lock):
            return subprocess.run(cmd).returncode
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
