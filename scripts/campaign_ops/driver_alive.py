#!/usr/bin/env python3
"""driver_alive.py — reliable campaign-driver liveness probe (no pgrep).

Why not `pgrep -f`:
  * it self-matches the querying shell (handoff gotcha 15);
  * zombie PIDs answer signals but are dead for scheduling (gotcha 20);
  * any transient command line that merely CONTAINS the pattern (grep, tail,
    an editor) false-positives as "driver alive", which makes a supervisor
    stall forever or, worse, double-launch.

Contract: a driver is alive iff some REAL process (scanned from /proc, not
from a shell helper) has ALL of the following:
  * cmdline contains the driver script token (e.g. "run_wsb_torch.py");
  * cmdline contains the campaign --runs directory;
  * /proc/<pid>/stat state is not Z (zombie) and not X (dead).

Library use:
    from driver_alive import driver_alive
    alive, pids = driver_alive(runs_dir=Path("/data/yue2-runs/armA_wsb_full"))

CLI use:
    python driver_alive.py --script run_wsb_torch.py \
        --runs /data/yue2-runs/armA_wsb_full [--proc-root /proc]
    exit 0 = alive (pids printed), exit 1 = not alive, exit 2 = usage error
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read_cmdline(proc_root: Path, pid: str) -> str:
    try:
        return (proc_root / pid / "cmdline").read_bytes().replace(
            b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return ""


def _read_state(proc_root: Path, pid: str) -> str:
    try:
        stat = (proc_root / pid / "stat").read_text()
        # comm may contain spaces/parens; state is the first field after ')'
        return stat.rpartition(")")[2].split()[0]
    except (OSError, IndexError):
        return "?"


def driver_alive(script: str = "run_wsb_torch.py",
                 runs_dir: Path | str | None = None,
                 proc_root: Path | str = "/proc",
                 exclude_pids: set[int] | None = None) -> tuple[bool, list[int]]:
    """Scan <proc_root> for a live process of the campaign driver.

    exclude_pids lets a caller (e.g. the launcher itself) ignore its own tree.
    Returns (alive, pids). Unreadable entries are treated as not-a-match (a
    process we cannot inspect must not be counted as our driver).
    """
    root = Path(proc_root)
    exclude = exclude_pids or set()
    needle_runs = str(runs_dir) if runs_dir is not None else None
    pids: list[int] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return False, []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in exclude:
            continue
        cmd = _read_cmdline(root, entry.name)
        if not cmd or script not in cmd:
            continue
        if needle_runs is not None and needle_runs not in cmd:
            continue
        state = _read_state(root, entry.name)
        if state in ("Z", "X"):
            continue  # zombie/dead — not alive for scheduling purposes
        pids.append(pid)
    return bool(pids), pids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="run_wsb_torch.py",
                    help="driver script token to match in cmdline")
    ap.add_argument("--runs", default=None,
                    help="campaign --runs directory that must appear in cmdline")
    ap.add_argument("--proc-root", default="/proc")
    args = ap.parse_args()
    alive, pids = driver_alive(script=args.script,
                               runs_dir=args.runs, proc_root=args.proc_root)
    print(f"alive={alive} pids={pids}")
    return 0 if alive else 1


if __name__ == "__main__":
    sys.exit(main())
