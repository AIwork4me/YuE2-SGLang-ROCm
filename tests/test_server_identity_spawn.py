"""server_identity.py spawn-receipt ownership tests (RC5 M1.1).

The spawn receipt is the ONLY basis for stopping a server that never produced
an identity receipt (boot failure). These tests pin down what it may do:
verify pid + starttime + uid + session, signal only the verified leader and
processes PROVEN to be in its session, refuse PID reuse, never SIGKILL.
Mocked /proc trees; signals go through the SI_SIGNAL_CMD test hook.
"""
from __future__ import annotations

import importlib.util
import json
import os
import signal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "server_identity_spawn_mod", REPO / "scripts" / "server_identity.py")
si = importlib.util.module_from_spec(spec)
spec.loader.exec_module(si)


def write_proc(root: Path, pid: int, ppid: int, comm: str, state="S",
                starttime="1000", pgrp=None, session=None, uid=0):
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    pgrp = pgrp if pgrp is not None else ppid
    session = session if session is not None else ppid
    (d / "cmdline").write_bytes(f"prog {pid}".encode() + b"\0")
    (d / "comm").write_text(comm + "\n")
    # rest = state ppid pgrp session <15 fields> starttime ...  (starttime = rest[19])
    (d / "stat").write_text(
        f"{pid} ({comm}) {state} {ppid} {pgrp} {session} " + "0 " * 15
        + f"{starttime} 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n")
    (d / "status").write_text(f"Name:\t{comm[:15]}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    root = tmp_path / "proc"
    root.mkdir()
    # our spawned server: pid 500, session leader of 500
    write_proc(root, 500, 1, "sglang", starttime="5000", pgrp=500, session=500)
    # its scheduler worker and a reparented grandchild share the session
    write_proc(root, 501, 500, "sgl_diffusion::s", starttime="5001", pgrp=500, session=500)
    write_proc(root, 502, 1, "orphan-worker", starttime="5002", pgrp=500, session=500)
    # a foreign process that merely LOOKS like the server (own session)
    write_proc(root, 900, 1, "sglang", starttime="9000", pgrp=900, session=900)
    # a PID-reuse lookalike: same pid, different starttime, is detected below
    signals = tmp_path / "signals.log"

    def hook():
        si.TEST_HOOKS_PROC_ROOTS.add(str(root))
        monkeypatch.setenv("SI_ALLOW_REAL_PROC_HOOKS", "1-I-AM-A-TEST")
        monkeypatch.setenv("SI_SIGNAL_CMD", f"echo {signal.__name__} >> {signals}")
    hook()
    # record (pid, signum) pairs without touching any real process
    monkeypatch.setattr(si, "send_signal",
                        lambda pid, sig: signals.open("a").write(f"{pid}:{int(sig)}\n"))
    monkeypatch.setattr(si, "wait_gone", lambda *a, **k: "alive")
    monkeypatch.setattr(si.time, "sleep", lambda s: None)
    spawn = {"pid": 500, "uid": 0, "starttime": "5000", "session": 500}
    return root, spawn, signals


def _signalled(log: Path) -> list[str]:
    return log.read_text().split() if log.is_file() else []


def test_verify_spawned_ok(tree):
    root, spawn, _ = tree
    f = si.verify_spawned(str(root), spawn)
    assert f["pid"] == 500 and f["session"] == 500 and f["starttime"] == "5000"


def test_verify_spawned_refuses_pid_reuse(tree):
    root, spawn, _ = tree
    with pytest.raises(si.IdentError) as ei:
        si.verify_spawned(str(root), {**spawn, "starttime": "4242"})
    assert ei.value.code == 2 and "PID reused" in ei.value.reason


def test_verify_spawned_refuses_other_session(tree):
    """A healthy process with the same pid but another session is not ours."""
    root, spawn, _ = tree
    with pytest.raises(si.IdentError) as ei:
        si.verify_spawned(str(root), {**spawn, "pid": 900, "starttime": "9000",
                                      "session": 500})
    assert ei.value.code == 3 and "not our process" in ei.value.reason


def test_verify_spawned_refuses_uid_change_and_zombie(tree):
    root, spawn, _ = tree
    write_proc(root, 500, 1, "sglang", starttime="5000", pgrp=500, session=500, uid=1000)
    with pytest.raises(si.IdentError) as ei:
        si.verify_spawned(str(root), spawn)
    assert ei.value.code == 2 and "uid" in ei.value.reason
    write_proc(root, 500, 1, "sglang", state="Z", starttime="5000", pgrp=500,
               session=500, uid=0)
    with pytest.raises(si.IdentError) as ei:
        si.verify_spawned(str(root), spawn)
    assert ei.value.code == 2 and "zombie" in ei.value.reason


def test_session_processes_only_members(tree):
    root, _, _ = tree
    me = {p["pid"] for p in si.session_processes(str(root), 500)}
    assert me == {500, 501, 502}          # 900 (foreign session) excluded
    late = si.session_processes(str(root), 500, min_starttime=5002)
    assert {p["pid"] for p in late} == {502}  # starttime floor excludes reuse


def test_stop_spawned_signals_only_owned_session(tree):
    root, spawn, log = tree
    res = si.stop_spawned(str(root), spawn, timeout=1)
    sig = _signalled(log)
    assert res["status"] == "blocked"      # nothing dies in this mock
    pids = {s.split(":")[0] for s in sig}
    assert pids == {"500", "501", "502"}, sig   # ours only
    assert "900" not in pids                # the look-alike is never signalled
    assert all(s.split(":")[1] in (str(int(signal.SIGINT)), str(int(signal.SIGTERM)))
               for s in sig)                 # never SIGKILL
    assert any(s == "500:2" for s in sig) and any(s == "500:15" for s in sig)


def test_stop_spawned_dry_run_sends_nothing(tree):
    root, spawn, log = tree
    res = si.stop_spawned(str(root), spawn, timeout=1, dry_run=True)
    assert res["status"] == "dry-run" and _signalled(log) == []


def test_stop_spawned_already_gone_is_not_an_error(tree):
    root, spawn, log = tree
    import shutil
    shutil.rmtree(root / "500")
    with pytest.raises(si.IdentError) as ei:
        si.stop_spawned(str(root), spawn, timeout=1)
    assert ei.value.code == 2
    assert _signalled(log) == []


def test_live_owned_requires_same_pid_and_starttime(tree):
    root, _, _ = tree
    snap = si.session_processes(str(root), 500)
    assert {m["pid"] for m in si.live_owned(snap, str(root))} == {500, 501, 502}
    write_proc(root, 501, 1, "recycled", starttime="77777", pgrp=501, session=501)
    assert {m["pid"] for m in si.live_owned(snap, str(root))} == {500, 502}


def test_cli_stop_spawned_exit_codes(tree, tmp_path):
    """Through the real CLI in a child process: the SI_* hooks are honoured
    only for the mocked --proc-root, so nothing real is signalled."""
    import subprocess
    import sys
    root, spawn, _ = tree
    siglog = tmp_path / "cli-signals.log"
    env = {**os.environ, "SI_SIGNAL_CMD": f"echo {{pid}}:{{signum}} >> {siglog}",
           "SI_WAIT_TIMEOUT": "0.2", "SI_WAIT_POLL": "0.05"}
    tool = [sys.executable, str(REPO / "scripts/server_identity.py"), "stop-spawned",
            "--proc-root", str(root), "--timeout", "1"]
    rp = tmp_path / "spawn.json"
    rp.write_text(json.dumps(spawn))
    r = subprocess.run(tool + ["--spawn-receipt", str(rp), "--dry-run"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "dry-run"
    assert not siglog.exists()                       # dry run signals nothing
    r = subprocess.run(tool + ["--spawn-receipt", str(rp)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 5 and "BLOCKED" in r.stderr   # survivor, never SIGKILL
    got = {x.split(":")[0] for x in siglog.read_text().split()}
    assert got == {"500", "501", "502"} and "900" not in got
    assert ":9" not in siglog.read_text()
    rp.write_text(json.dumps({**spawn, "starttime": "1"}))
    r = subprocess.run(tool + ["--spawn-receipt", str(rp)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2                          # PID reuse refused
    rp.write_text(json.dumps({"pid": 500}))
    r = subprocess.run(tool + ["--spawn-receipt", str(rp)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 4                          # malformed: clean refusal


def test_hooks_never_apply_to_the_real_proc(monkeypatch):
    monkeypatch.delenv("SI_ALLOW_REAL_PROC_HOOKS", raising=False)
    si.TEST_HOOKS_PROC_ROOTS.clear()
    si.TEST_HOOKS_PROC_ROOTS.add("/proc")
    monkeypatch.setenv("SI_SIGNAL_CMD", "echo should-not-run")
    monkeypatch.setattr(si, "wait_gone", lambda *a, **k: pytest.fail("hook honoured"))
    called = []
    monkeypatch.setattr(si.os, "kill", lambda pid, sig: called.append((pid, sig)))
    si.send_signal(999999, signal.SIGINT)
    assert called == [(999999, signal.SIGINT)]
    assert si.hooks_allowed() is False
