"""driver_alive.py regression tests (C3) — zombie-safe /proc scanning.

Synthetic /proc trees only; no GPU, no real processes with those names.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/campaign_ops"))
import driver_alive  # noqa: E402


def make_proc(root: Path, pid: int, cmdline: str, state: str = "S") -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode() + b"\0")
    # stat format: pid (comm) state ...
    (d / "stat").write_text(f"{pid} (fakeproc) {state} 1 1 1\n")


def test_live_driver_detected(tmp_path):
    make_proc(tmp_path, 100, "/py run_wsb_torch.py --runs /data/yue2-runs/armA_wsb_full")
    alive, pids = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path)
    assert alive and pids == [100]


def test_zombie_not_alive(tmp_path):
    make_proc(tmp_path, 101, "/py run_wsb_torch.py --runs /data/yue2-runs/armA_wsb_full",
              state="Z")
    alive, pids = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path)
    assert not alive and pids == []


def test_wrong_runs_dir_ignored(tmp_path):
    make_proc(tmp_path, 102, "/py run_wsb_torch.py --runs /some/other/run")
    alive, _ = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path)
    assert not alive


def test_grep_like_cmdline_not_a_driver_when_runs_filtered(tmp_path):
    # a shell whose cmdline merely CONTAINS the token (the pgrep self-match
    # failure mode) must not count when the runs dir is required
    make_proc(tmp_path, 103, "grep run_wsb_torch.py /var/log/syslog")
    alive, _ = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path)
    assert not alive


def test_excluded_pid_ignored(tmp_path):
    make_proc(tmp_path, 104, "/py run_wsb_torch.py --runs /data/yue2-runs/armA_wsb_full")
    alive, _ = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path, exclude_pids={104})
    assert not alive


def test_probe_invocation_not_counted_as_driver(tmp_path):
    # THE regression that bit the real launcher: this tool's own invocation
    # carries the script token as an ARGUMENT and must never match itself
    make_proc(tmp_path, 105,
              "/py driver_alive.py --script run_wsb_torch.py "
              "--runs /data/yue2-runs/armA_wsb_full")
    alive, _ = driver_alive.driver_alive(
        script="run_wsb_torch.py", runs_dir="/data/yue2-runs/armA_wsb_full",
        proc_root=tmp_path)
    assert not alive


def test_empty_proc_root(tmp_path):
    alive, pids = driver_alive.driver_alive(
        script="run_wsb_torch.py", proc_root=tmp_path)
    assert not alive and pids == []


def test_cli_reports_not_alive(tmp_path):
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts/campaign_ops/driver_alive.py"),
         "--script", "run_wsb_torch.py", "--proc-root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "alive=False" in r.stdout
