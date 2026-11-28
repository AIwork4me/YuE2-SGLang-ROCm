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

def resolve_physical_gpu() -> dict | None:
    """RC6.1 M3.5: the PHYSICAL lock-domain identity of the exposed GPU.

    The domain is keyed by PCI BDF (never by the logical HIP ordinal, which
    can differ per process/container): exactly one amdgpu render node must be
    visible; ambiguity returns None (the caller then falls back to the
    legacy workspace lock and the receipt discloses the unshared domain).
    """
    import re
    dri = Path("/dev/dri")
    sysfs = Path("/sys/class/drm")
    if not (dri.is_dir() and sysfs.is_dir()):
        return None
    render_nodes = sorted(p.name for p in dri.glob("renderD*"))
    if len(render_nodes) != 1:
        return None
    visible = {}
    for node in sorted(sysfs.iterdir(), key=lambda q: q.name):
        if not node.name.startswith("card") or node.name.startswith("card-"):
            continue
        idx = node.name[4:]
        if idx.isdigit() and (dri / node.name).exists():
            ue = (node / "device" / "uevent").read_text() \
                if (node / "device" / "uevent").is_file() else ""
            m = re.search(r"PCI_SLOT_NAME=(\S+)", ue)
            drv = (node / "device" / "driver").resolve().name \
                if (node / "device" / "driver").is_symlink() else ""
            if m and drv == "amdgpu":
                uid = (node / "device" / "unique_id").read_text().strip() \
                    if (node / "device" / "unique_id").is_file() else None
                visible[m.group(1)] = uid
    if len(visible) != 1:
        return None
    bdf, uuid = next(iter(visible.items()))
    return {"bdf": bdf, "uuid": uuid, "render_node": render_nodes[0],
            "host": os.uname().nodename}


DEFAULT_SHARED_LOCK_ROOT = "/var/lock/yue2-gpu"


def _shared_root() -> Path:
    return Path(os.environ.get("YUE2_GPU_LOCK_ROOT", DEFAULT_SHARED_LOCK_ROOT))


def lock_domain_name(gpu: dict | None) -> str:
    """Stable lock-domain name for a physical GPU (BDF-keyed; uuid when the
    kernel does not expose a BDF)."""
    if not gpu:
        return "domain-unresolved"
    return f"gpu-{gpu.get('bdf') or gpu.get('uuid') or 'unknown'}"


def _shared_root_usable(root: Path) -> bool:
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".probe.{os.getpid()}"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_default_lock() -> Path:
    """Resolve the default lock path at CALL time — never import time.

    RC6.1 M3.5: the default is the SHARED PHYSICAL lock domain
    (``<YUE2_GPU_LOCK_ROOT or /var/lock/yue2-gpu>/gpu-<BDF>.lock``) so that
    different workspaces on the same host cannot each claim the same physical
    GPU through separate workspace-local lock files.

    Resolution order (first wins):
      1. ``YUE2_GPU_LOCK``            — explicit file override (unchanged)
      2. ``YUE2_GPU_LOCK_ROOT``       — explicit shared root + physical domain
      3. default shared root          — when writable and the GPU is resolvable
      4. ``<YUE2_WORKSPACE>/gpu.lock``— legacy fallback (disclosed as an
                                        UNSHARED domain; GPU-less CI, read-only
                                        hosts). Containers/users that do not
                                        share this directory are NOT protected
                                        by the cross-workspace protocol.

    An import-time frozen default broke isolation twice in practice:
      * CI runners (non-root, no /data): gpu_ownership() did
        ``path.parent.mkdir(parents=True)`` on the frozen /data/yue2/gpu.lock
        default -> PermissionError: [Errno 13] '/data' (PR #13 run 44421080608,
        5 failures in TestScoreGate).
      * any caller that exports YUE2_WORKSPACE/YUE2_GPU_LOCK after importing
        this module silently locked the wrong file.
    All internal code paths resolve lazily via this function.
    """
    explicit = os.environ.get("YUE2_GPU_LOCK")
    if explicit:
        return Path(explicit)
    gpu = resolve_physical_gpu()
    if gpu is not None:
        root = _shared_root()
        if _shared_root_usable(root):
            return root / f"{lock_domain_name(gpu)}.lock"
    return Path(os.environ.get("YUE2_WORKSPACE", "/data/yue2")) / "gpu.lock"


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


def _pid_starttime(pid: int) -> str | None:
    """starttime (clock ticks since boot) of a pid — the PID-reuse guard."""
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return data[data.rindex(")") + 1:].split()[19]
    except (OSError, ValueError, IndexError):
        return None


class GpuBlockedError(RuntimeError):
    """A previous GPU lifecycle ended BLOCKED and the operator has not cleared
    it. Every acquisition is refused until ``gpu_lock.py unblock --yes``
    verifies the recorded processes are gone (RC5 M1.1: a cleanup failure must
    block the next unsafe start, never hide behind a released flock)."""


BLOCKED_SUFFIX = ".BLOCKED"


def blocked_marker_path(lock_path: Path | None = None) -> Path:
    p = Path(lock_path) if lock_path else resolve_default_lock()
    return Path(str(p) + BLOCKED_SUFFIX)


def read_blocked(lock_path: Path | None = None) -> dict | None:
    try:
        return json.loads(blocked_marker_path(lock_path).read_text())
    except (OSError, ValueError):
        return None


def blocked_live_processes(marker: dict | None) -> list[int]:
    """Recorded pids that are STILL the same live process (pid+starttime)."""
    out = []
    for e in (marker or {}).get("processes", []):
        pid = e.get("pid")
        if not isinstance(pid, int) or not _pid_alive(pid):
            continue
        st = e.get("starttime")
        if st is None or _pid_starttime(pid) == str(st):
            out.append(pid)
    return sorted(out)


def _write_json_durable(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        f.write(json.dumps(obj, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def mark_blocked(lock_path: Path | None, who: str, processes: list[dict],
                 reason: str, **extra) -> dict:
    """Record a BLOCKED lifecycle next to the lock. ``processes`` carries
    {pid, starttime, role} for every process that could not be reaped."""
    marker = {
        "state": "BLOCKED",
        "who": who,
        "reason": reason,
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": os.uname().nodename,
        "processes": processes,
        **extra,
    }
    path = blocked_marker_path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_durable(path, marker)
    return marker


def clear_blocked(lock_path: Path | None, confirmed: bool) -> int:
    path = blocked_marker_path(lock_path)
    marker = read_blocked(lock_path)
    if marker is None:
        print(json.dumps({"cleared": False, "reason": "no BLOCKED marker",
                          "marker": str(path)}))
        return 0
    live = blocked_live_processes(marker)
    if live:
        print(json.dumps({"cleared": False,
                          "reason": "recorded process(es) still alive; resolve "
                                    "them first (never signalled by this tool)",
                          "live_pids": live, "marker": marker}, indent=1))
        return 3
    if not confirmed:
        print(json.dumps({"cleared": False,
                          "reason": "refusing without --yes (operator "
                                    "confirmation)", "marker": marker}, indent=1))
        return 2
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    kept = path.with_name(path.name + f".cleared-{stamp}")
    os.replace(path, kept)
    print(json.dumps({"cleared": True, "evidence_kept": str(kept)}))
    return 0


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
    blocked = read_blocked(lock_path)
    return {"lock": str(lock_path), "held": held, "holder": holder,
            "holder_live": holder_live,
            "blocked": blocked is not None,
            "blocked_live_pids": blocked_live_processes(blocked),
            "blocked_marker": blocked}


@contextmanager
def gpu_ownership(who: str, wait_s: float = 0.0, poll_s: float = 10.0,
                  lock_path: Path | None = None):
    """Acquire the single-GPU ownership lock; yields the receipt dict.

    Refuses (GpuBlockedError) while a BLOCKED marker exists: the previous
    lifecycle could not clean up, so the device may still be occupied by a
    process nobody owns. Only an operator can clear it (``unblock --yes``)."""
    path = Path(lock_path) if lock_path else resolve_default_lock()
    path.parent.mkdir(parents=True, exist_ok=True)
    blocked = read_blocked(path)
    if blocked is not None:
        raise GpuBlockedError(
            f"GPU lifecycle BLOCKED by a previous run (who={blocked.get('who')!r}, "
            f"recorded {blocked.get('recorded_at_utc')}, live pids "
            f"{blocked_live_processes(blocked)}): {blocked.get('reason')} "
            f"— resolve and run `gpu_lock.py unblock --yes`")
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
    gpu = resolve_physical_gpu()
    receipt = {
        "who": who,
        "pid": os.getpid(),
        "cmdline": _pid_cmdline(os.getpid()),
        "workspace": os.environ.get("YUE2_WORKSPACE"),
        "acquired_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": os.uname().nodename,
        "lock_domain": {
            "name": lock_domain_name(gpu),
            "physical": gpu,          # BDF/uuid-keyed: logical HIP ordinals never name a domain
            "shared": gpu is not None,
            "legacy_workspace_fallback": gpu is None,
            "note": "cross-workspace mutex holds ONLY where this shared root is "
                    "commonly mounted; unshared roots are disclosed, not assumed",
        },
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


def run_child_holding_lock(cmd: list[str], drain_s: float = 0.0) -> int:
    """Run ``cmd`` while THIS process keeps the flock, signal-safe.

    RC5 M1.1: the legacy gateway died on SIGINT/SIGTERM (KeyboardInterrupt /
    default action), releasing the flock while its child was still cleaning
    up. Now the signal is forwarded to the child and the lock is held until
    the child exits (optionally warning after ``drain_s``). Only a SIGKILL to
    this process can release the lock early — the outer lifecycle supervisor
    is the second line of defence for that case."""
    child = subprocess.Popen(cmd)
    state = {"signum": None, "warned": False}

    def forward(signum, _frame):
        state["signum"] = signum
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"[gpu_lock] cannot forward signal {signum} to child "
                  f"{child.pid} (permission denied)", file=sys.stderr)

    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            previous[sig] = signal.signal(sig, forward)
        except (ValueError, OSError):
            pass  # not the main thread / unsupported signal
    t_sig = None
    try:
        while True:
            try:
                rc = child.wait(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                if state["signum"] is not None:
                    t_sig = t_sig or time.monotonic()
                    if (drain_s > 0 and not state["warned"]
                            and time.monotonic() - t_sig > drain_s):
                        state["warned"] = True
                        print(f"[gpu_lock] child {child.pid} still draining "
                              f"{drain_s:.0f}s after signal {state['signum']}; "
                              f"LOCK STAYS HELD (fail-closed)", file=sys.stderr)
    finally:
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
    if rc is not None and rc < 0:
        return 128 - rc  # killed by signal -N -> 128+N (shell convention)
    return rc


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
    w.add_argument("--poll-s", type=float, default=10.0)
    w.add_argument("--drain-s", type=float, default=0.0,
                   help="warn (lock stays held) if the child keeps draining "
                        "this long after a forwarded signal")
    # NOTE: dest must NOT be "cmd" — the subparsers' dest is also "cmd" and a
    # positional with the same name silently overwrites it, making every
    # `wait` invocation fall through to `return 2` (live defect found while
    # wiring armB_acceptance.sh; the library API was unaffected).
    w.add_argument("cmd_args", nargs=argparse.REMAINDER)
    s = sub.add_parser("stop")
    s.add_argument("--yes", action="store_true")
    u = sub.add_parser("unblock")
    u.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    lock = Path(args.lock) if args.lock else resolve_default_lock()
    if args.cmd == "status":
        print(json.dumps(status(lock), indent=2))
        return 0
    if args.cmd == "stop":
        return graceful_stop(lock, confirmed=args.yes)
    if args.cmd == "unblock":
        return clear_blocked(lock, confirmed=args.yes)
    if args.cmd == "wait":
        cmd = args.cmd_args
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if not cmd:
            print("no command given", file=sys.stderr)
            return 2
        with gpu_ownership(args.who, wait_s=args.wait_s, poll_s=args.poll_s,
                           lock_path=lock):
            return run_child_holding_lock(cmd, drain_s=args.drain_s)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
