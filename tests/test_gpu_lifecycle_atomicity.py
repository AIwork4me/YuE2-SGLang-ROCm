"""gpu_lifecycle.py atomicity + fault-injection tests (RC5 M1.1, P0).

RC4.1 static review finding: the GPU lock was released by a background gateway
BEFORE the outer launcher's EXIT trap stopped the server. These tests use REAL
processes, REAL signals and REAL flocks (no mocks on the lock path) to prove
the RC5 contract of scripts/gpu_lifecycle.py:

  1. a second job CANNOT acquire the GPU lock while the first one is cleaning
     up (deterministic barrier parked inside the cleanup phase);
  2. normal exit, driver failure, SIGINT and SIGTERM all stop the server,
     verify tree/port/GPU release, and only then release the lock;
  3. a server that never becomes healthy (no identity receipt yet) is stopped
     through its SPAWN receipt — nothing is orphaned;
  4. a server that survives SIGINT+SIGTERM is never SIGKILLed: the lifecycle
     ends BLOCKED, later GPU work is refused until an operator clears it;
  5. a foreign process that merely LOOKS like the server is never signalled;
  6. the gpu_lock.py gateway keeps the flock while its child drains.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REAL = {
    "scripts/gpu_lock.py": None,
    "scripts/server_identity.py": None,
    "scripts/server_readiness.py": None,
    "scripts/gpu_identity.py": None,
    "scripts/gpu_lifecycle.py": None,
    "scripts/campaign_ops/run_with_server.sh": None,
}

FAKE_SERVER = r'''
import argparse, ctypes, json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("serve")
ap.add_argument("--model-path", required=True)
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--mode-file", required=True)
ap.add_argument("--events", required=True)
args = ap.parse_args()
MODE = Path(args.mode_file); EVENTS = Path(args.events)
mode = MODE.read_text().strip()

def log_ev(name, **kw):
    with EVENTS.open("a") as f:
        f.write(json.dumps({"event": name, **kw}) + "\n")

# scheduler worker: argv carries the signature server_readiness scans for
if "nosched" not in mode:
    pid = os.fork()
    if pid == 0:
        if "treestubborn" in mode:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        else:
            ctypes.CDLL("libc.so.6").prctl(1, signal.SIGKILL)  # die with parent
        os.execv(sys.executable, [sys.executable, "-c",
                 "import sys, time; sys.argv=['sgl_diffusion::scheduler']; "
                 "time.sleep(86400)", "scheduler-worker"])
    log_ev("scheduler_spawned", pid=pid)

def bye(sig, frame):
    log_ev("signal", sig=sig)
    if "slowstop" in mode:
        time.sleep(6)
    log_ev("exiting")
    os._exit(0)

if mode == "stubborn":      # leader ignores every stop request
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
else:
    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)
log_ev("listening", port=args.port, pid=os.getpid(), mode=mode)

if "nohealth" in mode:   # stuck before the HTTP server exists (model loading)
    while True:
        time.sleep(60)

if "nobind" in mode:     # alive but the port is taken: never listens, never exits
    log_ev("bind_failed")
    while True:
        time.sleep(60)

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._send(200, {"data": [{"id": args.model_path}]})
        else:
            self._send(404, {})
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer((args.host, args.port), H)
srv.serve_forever()
'''

FAKE_SERVE_SH = r'''#!/usr/bin/env bash
set -euo pipefail
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MODEL_PATH="${MODEL_PATH:-$WS/models/YuE2-3B}"
HOST="${HOST:-127.0.0.1}"; PORT="${PORT:-31000}"
SERVER_LOG="${SERVER_LOG:-$WS/logs/server.log}"
mkdir -p "$(dirname "$SERVER_LOG")"
echo "stub-serve boot port=$PORT" >> "$SERVER_LOG"
exec "$STUB_PY" "$STUB_DIR/fake_server.py" serve \
  --model-path "$MODEL_PATH" --host "$HOST" --port "$PORT" \
  --mode-file "$STUB_DIR/mode" --events "$STUB_DIR/events.json"
'''


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _alive(pid: int) -> bool:
    try:
        st = Path(f"/proc/{pid}/stat").read_text()
        return st.rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return False


def _wait_for(pred, timeout: float, what: str):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(0.1)
    pytest.fail(f"timeout waiting for {what}")


class Stack:
    """Real launcher + real lock/identity/lifecycle code, stub server."""

    def __init__(self, tmp: Path, mode: str = "ok"):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.ws = tmp / "ws"
        self.stub = tmp / "stub"
        self.port = _free_port()
        self.lock = tmp / "gpu.lock"
        for rel in REAL:
            dst = self.repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dst)
        serve = self.repo / "scripts" / "serve_yue2_gfx1100.sh"
        serve.write_text(FAKE_SERVE_SH)
        serve.chmod(0o755)
        self.stub.mkdir(parents=True)
        (self.stub / "fake_server.py").write_text(FAKE_SERVER)
        (self.stub / "mode").write_text(mode)
        (self.stub / "events.json").write_text("")
        stub_py = self.stub / "python"
        stub_py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
        stub_py.chmod(0o755)
        venv_bin = self.ws / "environments/yue2-gfx1100/bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        py = venv_bin / "python"
        # -S (no site-packages): the lifecycle tools are stdlib-only and the
        # stub stack must NOT see a host torch/GPU, so gpu_identity takes the
        # sanctioned CPU-test branch deterministically (also on GPU hosts)
        py.write_text(f"#!/bin/sh\nexec {sys.executable} -S \"$@\"\n")
        py.chmod(0o755)
        (self.ws / "models").mkdir(parents=True, exist_ok=True)

    def set_mode(self, mode: str):
        (self.stub / "mode").write_text(mode)

    def env(self, log_dir: Path, **over) -> dict:
        e = {
            **os.environ,
            "YUE2_WORKSPACE": str(self.ws),
            "YUE2_REPO": str(self.repo),
            "YUE2_GPU_LOCK": str(self.lock),
            "RWS_PORT": str(self.port),
            "RWS_LOG_DIR": str(log_dir),
            "RWS_HEALTH_TIMEOUT_S": "60",
            "RWS_HEALTH_POLL_S": "1",
            "RWS_STOP_TIMEOUT_S": "10",
            "RWS_DRAIN_S": "2",
            "RWS_PORT_RELEASE_TIMEOUT_S": "5",
            "RWS_GPU_RELEASE_TIMEOUT_S": "3",
            "STUB_PY": str(self.stub / "python"),
            "STUB_DIR": str(self.stub),
            # sanctioned CPU test-mode token (gpu_identity contract): the stub
            # stack has no GPU; TEST-ONLY, never a GPU PASS
            "YUE2_ALLOW_CPU": "1-I-AM-A-TEST",
        }
        e.update({k: str(v) for k, v in over.items()})
        return e

    def launch(self, cmd: list[str], log_dir: Path, name: str = "a", **over):
        return subprocess.Popen(
            ["bash", str(self.repo / "scripts/campaign_ops/run_with_server.sh"),
             "--log-dir", str(log_dir), "--port", str(self.port), "--"] + cmd,
            env=self.env(log_dir, RWS_LOCK_WHO=f"atomic-test-{name}", **over),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)

    def decoy(self) -> subprocess.Popen:
        """A FOREIGN process whose argv mimics the server (same model path,
        same port). It must survive every scenario untouched."""
        model = self.ws / "models/YuE2-3B"
        return subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)", "sglang",
             "serve", "--model-path", str(model), "--host", "127.0.0.1",
             "--port", str(self.port)],
            start_new_session=True)

    def server_pids(self) -> list[int]:
        out = []
        for line in (self.stub / "events.json").read_text().splitlines():
            if line.strip() and json.loads(line).get("event") == "listening":
                pid = json.loads(line)["pid"]
                if _alive(pid):
                    out.append(pid)
        return out

    def scheduler_pids(self) -> list[int]:
        out = []
        for line in (self.stub / "events.json").read_text().splitlines():
            if line.strip() and json.loads(line).get("event") == "scheduler_spawned":
                pid = json.loads(line)["pid"]
                if _alive(pid):
                    out.append(pid)
        return out

    def port_open(self) -> bool:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", self.port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def lock_status(self) -> dict:
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts/gpu_lock.py"),
             "--lock", str(self.lock), "status"],
            capture_output=True, text=True, check=True)
        return json.loads(r.stdout)

    def receipt(self, log_dir: Path) -> dict:
        return json.loads((log_dir / "lifecycle-receipt.json").read_text())

    def kill_all(self):
        for pid in self.server_pids() + self.scheduler_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


@pytest.fixture()
def stack(tmp_path):
    s = Stack(tmp_path)
    yield s
    s.kill_all()


def _sleep_cmd(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def _finish(p: subprocess.Popen, timeout: float = 120) -> tuple[int, str]:
    try:
        out = p.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        p.kill()
        pytest.fail("launcher did not exit in time")
    return p.returncode, out


def _assert_clean(stack: Stack, log_dir: Path, out: str):
    rec = stack.receipt(log_dir)
    assert rec["cleanup_state"] == "CLEAN", (rec["cleanup_state"], out)
    by = {s["step"]: s["status"] for s in rec["steps"]}
    assert by["stop_server"] == "STOPPED", by
    assert by["tree_termination"] == "TERMINATED", by
    assert by["port_release"] == "RELEASED", by
    # CPU test mode is disclosed, never presented as a GPU release
    assert by["gpu_release"] == "NOT_APPLICABLE_CPU_TEST_MODE", by
    assert stack.server_pids() == [] and stack.scheduler_pids() == []
    assert not stack.port_open()
    st = stack.lock_status()
    assert st["held"] is False and st["blocked"] is False


# --------------------------------------------------------------- 1. the race
def test_second_job_cannot_take_the_lock_during_cleanup(stack, tmp_path):
    """THE P0 interleaving, reproduced deterministically. Job A parks inside
    its cleanup phase (lock held, server still alive). Job B tries to start
    at exactly that moment and must be refused."""
    barrier = tmp_path / "barrier"
    log_a, log_b, log_c = (tmp_path / d for d in ("a", "b", "c"))
    decoy = stack.decoy()
    a = stack.launch(_sleep_cmd(3), log_a, name="a",
                      YUE2_LIFECYCLE_TEST_BARRIER=str(barrier))
    try:
        _wait_for(lambda: Path(str(barrier) + ".entered").is_file(), 90,
                  "job A reaching its cleanup phase")
        # A is cleaning up: the server is STILL alive and A STILL holds the lock
        assert stack.server_pids(), "server already gone: not in the cleanup window"
        st = stack.lock_status()
        assert st["held"] is True
        assert st["holder"]["who"] == "atomic-test-a"
        # B is refused while A cleans up
        b = stack.launch(_sleep_cmd(1), log_b, name="b", RWS_GPU_LOCK_WAIT_S="3")
        rc_b, out_b = _finish(b, 60)
        assert rc_b != 0
        assert "GPU ownership lock unavailable" in out_b, out_b
        assert "GPU ownership lock held by" in out_b
        assert not (log_b / "lifecycle-launched.json").exists(), "B ran under A"
        assert not (log_b / "rws_server_identity/server-spawn.json").exists()
        # A is still parked and still holds the lock after B gave up
        assert a.poll() is None and stack.lock_status()["held"] is True
        barrier.write_text("release")
        rc_a, out_a = _finish(a)
        assert rc_a == 0, out_a
        _assert_clean(stack, log_a, out_a)
        # only now can the next job run
        c = stack.launch(_sleep_cmd(1), log_c, name="c", RWS_GPU_LOCK_WAIT_S="3")
        rc_c, out_c = _finish(c)
        assert rc_c == 0, out_c
        _assert_clean(stack, log_c, out_c)
        assert decoy.poll() is None, "foreign process was signalled"
    finally:
        if a.poll() is None:
            a.kill()
        decoy.kill()


def test_lock_holder_is_the_process_that_cleans_up(stack, tmp_path):
    """The flock holder pid equals the supervisor pid in the lifecycle
    receipt (one process owns lock + cleanup)."""
    log = tmp_path / "a"
    inside = tmp_path / "inside.json"
    cmd = [sys.executable, "-c",
           f"import json,subprocess,sys; from pathlib import Path; "
           f"Path({str(inside)!r}).write_text(subprocess.run([sys.executable, "
           f"{str(REPO / 'scripts/gpu_lock.py')!r}, '--lock', "
           f"{str(stack.lock)!r}, 'status'], capture_output=True, "
           f"text=True).stdout)"]
    p = stack.launch(cmd, log)
    rc, out = _finish(p)
    assert rc == 0, out
    st = json.loads(inside.read_text())
    rec = stack.receipt(log)
    assert st["held"] is True
    assert st["holder"]["pid"] == rec["supervisor_pid"]
    assert st["holder"]["cmdline"].startswith(sys.executable)
    assert "gpu_lifecycle.py" in st["holder"]["cmdline"]


# ------------------------------------------------- 2. every exit is a cleanup
@pytest.mark.parametrize("driver_rc", [0, 7])
def test_driver_exit_cleans_everything_then_unlocks(stack, tmp_path, driver_rc):
    decoy = stack.decoy()
    log = tmp_path / "a"
    p = stack.launch([sys.executable, "-c", f"import sys; sys.exit({driver_rc})"],
                     log)
    rc, out = _finish(p)
    assert rc == driver_rc, out
    _assert_clean(stack, log, out)
    assert decoy.poll() is None
    decoy.kill()


@pytest.mark.parametrize("sig,expected_rc", [(signal.SIGINT, 130),
                                              (signal.SIGTERM, 143)])
def test_signals_clean_before_unlock(stack, tmp_path, sig, expected_rc):
    decoy = stack.decoy()
    log = tmp_path / "a"
    started = tmp_path / "started"
    cmd = [sys.executable, "-c",
           f"from pathlib import Path; Path({str(started)!r}).write_text('1')\n"
           "import time; time.sleep(300)"]
    p = stack.launch(cmd, log)
    try:
        _wait_for(started.is_file, 90, "driver start")
        assert stack.lock_status()["held"] is True
        p.send_signal(sig)
        rc, out = _finish(p, 90)
        assert rc == expected_rc, (rc, out)
        _assert_clean(stack, log, out)
        rec = stack.receipt(log)
        assert rec["signal"] == int(sig)
        assert rec["cmd_rc"] not in (None, 0)  # the driver was stopped too
        assert decoy.poll() is None, "foreign process was signalled"
    finally:
        if p.poll() is None:
            p.kill()
        decoy.kill()


def test_second_signal_during_cleanup_does_not_break_it(stack, tmp_path):
    log = tmp_path / "a"
    started = tmp_path / "started"
    cmd = [sys.executable, "-c",
           f"from pathlib import Path; Path({str(started)!r}).write_text('1')\n"
           "import time; time.sleep(300)"]
    p = stack.launch(cmd, log)
    try:
        _wait_for(started.is_file, 90, "driver start")
        p.send_signal(signal.SIGTERM)
        time.sleep(0.5)
        p.send_signal(signal.SIGINT)   # repeated Ctrl-C style
        rc, out = _finish(p, 90)
        assert rc == 143, (rc, out)
        _assert_clean(stack, log, out)
    finally:
        if p.poll() is None:
            p.kill()


# ----------------------------- 3. boot failure before the identity receipt
def test_boot_failure_without_receipt_stops_the_owned_process(stack, tmp_path):
    """The server never becomes healthy (stuck loading, nothing listening):
    there is no identity receipt. The process WE spawned is stopped via the
    spawn receipt; nothing is left behind — without any test-side kill."""
    stack.set_mode("nohealth")
    decoy = stack.decoy()
    log = tmp_path / "a"
    p = stack.launch(_sleep_cmd(1), log, RWS_HEALTH_TIMEOUT_S="5")
    rc, out = _finish(p)
    assert rc == 1, out
    assert "server unhealthy" in out
    assert "spawn receipt" in out
    spawn = json.loads((log / "rws_server_identity/server-spawn.json").read_text())
    assert not _alive(spawn["pid"]), "spawned server survived the launcher"
    assert stack.server_pids() == [] and stack.scheduler_pids() == []
    rec = stack.receipt(log)
    assert rec["flow_error"] == "health"
    assert rec["cleanup_state"] == "CLEAN"
    by = {s["step"]: s for s in rec["steps"]}
    assert by["stop_server"]["basis"] == "spawn_receipt"
    assert not (log / "rws_server_identity/server-identity.json").exists()
    assert stack.lock_status()["held"] is False
    assert decoy.poll() is None, "foreign process was signalled"
    decoy.kill()


def test_identity_mismatch_never_signals(stack, tmp_path):
    """A healthy server that is NOT the one we spawned (spawn chain broken)
    is refused before the driver runs; the foreign process stays alive."""
    log = tmp_path / "a"
    # boot a look-alike ourselves on the service port: the launcher's own
    # server cannot bind, so capture can only ever see OUR decoy
    decoy = subprocess.Popen(
        [sys.executable, str(stack.stub / "fake_server.py"), "serve",
         "--model-path", str(stack.ws / "models/YuE2-3B"), "--host", "127.0.0.1",
         "--port", str(stack.port), "--mode-file", str(stack.stub / "mode"),
         "--events", str(stack.stub / "events.json")],
        start_new_session=True)
    try:
        _wait_for(stack.port_open, 30, "look-alike server")
        p = stack.launch(_sleep_cmd(1), log, RWS_HEALTH_TIMEOUT_S="8")
        rc, out = _finish(p)
        assert rc == 1, out
        assert "identity" in out
        assert decoy.poll() is None, "a process we did not spawn was signalled"
    finally:
        decoy.kill()


def _look_alike(stack: Stack):
    """A FOREIGN healthy server on the stack's port. It uses its own mode
    file ("ok") and its own event log: it is not part of the stack."""
    (stack.stub / "foreign-mode").write_text("ok")
    (stack.stub / "foreign-events.json").write_text("")
    return subprocess.Popen(
        [sys.executable, str(stack.stub / "fake_server.py"), "serve",
         "--model-path", str(stack.ws / "models/YuE2-3B"), "--host", "127.0.0.1",
         "--port", str(stack.port), "--mode-file", str(stack.stub / "foreign-mode"),
         "--events", str(stack.stub / "foreign-events.json")],
        start_new_session=True)


def test_identity_receipt_never_names_a_foreign_process(stack, tmp_path):
    """Our server is alive but a FOREIGN process owns the port and answers
    /health. The identity capture is pinned to the spawned pid: it must fail
    and must leave NO receipt naming the foreign process (a later
    `server_identity.py stop --receipt` would otherwise signal it)."""
    stack.set_mode("nobind")
    log = tmp_path / "a"
    foreign = _look_alike(stack)
    try:
        _wait_for(stack.port_open, 30, "foreign listener")
        p = stack.launch(_sleep_cmd(1), log, RWS_HEALTH_TIMEOUT_S="15")
        rc, out = _finish(p)
        assert rc == 1 and "identity" in out, out
        receipt = log / "rws_server_identity/server-identity.json"
        if receipt.is_file():
            spawn = json.loads((log / "rws_server_identity/server-spawn.json").read_text())
            named = json.loads(receipt.read_text())["pid"]
            assert named == spawn["pid"], (
                f"identity receipt names pid {named}, we spawned {spawn['pid']}")
        assert foreign.poll() is None, "a process we did not spawn was signalled"
    finally:
        foreign.kill()


def test_stale_receipt_of_an_earlier_session_is_never_used(stack, tmp_path):
    """The receipt directory already holds a VALID receipt of a foreign,
    healthy server (an earlier session). It must be moved aside, never used
    to signal anything, and our own spawned process is still cleaned up."""
    stack.set_mode("nobind")
    log = tmp_path / "a"
    foreign = _look_alike(stack)
    try:
        _wait_for(stack.port_open, 30, "foreign listener")
        rdir = log / "rws_server_identity"
        rdir.mkdir(parents=True)
        stale = subprocess.run(
            [sys.executable, str(REPO / "scripts/server_identity.py"), "capture",
             "--run-state", str(rdir), "--model", str(stack.ws / "models/YuE2-3B"),
             "--host", "127.0.0.1", "--port", str(stack.port)],
            capture_output=True, text=True)
        assert stale.returncode == 0 and (rdir / "server-identity.json").is_file()
        stale_pid = json.loads((rdir / "server-identity.json").read_text())["pid"]
        assert stale_pid == foreign.pid
        p = stack.launch(_sleep_cmd(1), log, RWS_HEALTH_TIMEOUT_S="15")
        rc, out = _finish(p)
        assert rc == 1, out
        assert foreign.poll() is None, "a stale receipt was used to signal a process"
        spawn = json.loads((rdir / "server-spawn.json").read_text())
        assert not _alive(spawn["pid"]), "our own spawned server survived"
        moved = list(rdir.glob("server-identity.stale-*.json"))
        assert moved, "stale receipt was not moved aside"
        rec = stack.receipt(log)
        assert rec["cleanup_state"] in ("FAILED", "CLEAN")   # port held by a foreign listener
    finally:
        foreign.kill()


def test_replaced_receipt_mid_session_is_refused(stack, tmp_path):
    """Threat model: the identity receipt in OUR receipt directory is replaced
    during the session by a VALID receipt of a different, healthy process (a
    stale file restored from a backup, another operator tool, ...). The
    lifecycle must not signal that process and must still stop the server it
    spawned (through the spawn receipt)."""
    barrier = tmp_path / "barrier"
    log = tmp_path / "a"
    foreign = subprocess.Popen(
        [sys.executable, str(stack.stub / "fake_server.py"), "serve",
         "--model-path", str(stack.ws / "models/YuE2-3B"), "--host", "127.0.0.1",
         "--port", str(_free_port()), "--mode-file", str(stack.stub / "mode"),
         "--events", str(tmp_path / "foreign-events.json")],
        start_new_session=True)
    (tmp_path / "foreign-events.json").write_text("")
    foreign_port = None
    try:
        # recover the foreign port from its argv
        foreign_port = int(foreign.args[foreign.args.index("--port") + 1])
        for _ in range(100):
            s = socket.socket()
            s.settimeout(0.2)
            try:
                s.connect(("127.0.0.1", foreign_port))
                break
            except OSError:
                time.sleep(0.1)
            finally:
                s.close()
        a = stack.launch(_sleep_cmd(3), log, name="a",
                          YUE2_LIFECYCLE_TEST_BARRIER=str(barrier))
        _wait_for(lambda: Path(str(barrier) + ".entered").is_file(), 90,
                  "job A parked in cleanup")
        # A's own receipt exists; now it is replaced by the foreign one
        mine = json.loads((log / "rws_server_identity/server-identity.json").read_text())
        assert mine["pid"] in stack.server_pids()
        side = tmp_path / "foreign-receipt"
        subprocess.run(
            [sys.executable, str(REPO / "scripts/server_identity.py"), "capture",
             "--run-state", str(side), "--model", str(stack.ws / "models/YuE2-3B"),
             "--host", "127.0.0.1", "--port", str(foreign_port)],
            capture_output=True, text=True, check=True)
        shutil.copyfile(side / "server-identity.json",
                        log / "rws_server_identity/server-identity.json")
        barrier.write_text("release")
        rc, out = _finish(a)
        assert rc == 0, out
        assert foreign.poll() is None, "a replaced receipt was used to signal a process"
        assert stack.server_pids() == [], "our own server was not stopped"
        rec = stack.receipt(log)
        by = {x["step"]: x for x in rec["steps"]}
        assert by.get("stop_server_refusal", {}).get("status") == "RECEIPT_NOT_OURS"
        assert by["stop_server"]["basis"] == "spawn_receipt"
    finally:
        if foreign.poll() is None:
            foreign.kill()


def test_receipt_is_ours_unit(tmp_path):
    """The receipt-ownership predicate on its own (defense-in-depth layer 2)."""
    mod = _lifecycle_module()
    s = _sup(mod)
    s.spawn = {"pid": 500, "starttime": "4242"}
    rdir = tmp_path / "r"
    rdir.mkdir()
    s.a.receipt_dir = str(rdir)

    def write(pid, starttime, **extra):
        (rdir / "server-identity.json").write_text(json.dumps({
            "pid": pid, "uid": 0, "starttime": starttime, "argv_sha256": "f" * 64,
            "port": 31000, **extra}))
    write(500, "4242")
    assert s._receipt_is_ours() is True
    write(501, "4242")
    assert s._receipt_is_ours() is False       # another pid
    write(500, "4243")
    assert s._receipt_is_ours() is False       # PID reuse: same pid, new process
    (rdir / "server-identity.json").write_text("{not json")
    assert s._receipt_is_ours() is False       # malformed: refuse
    (rdir / "server-identity.json").unlink()
    assert s._receipt_is_ours() is False
    s.spawn = None
    write(500, "4242")
    assert s._receipt_is_ours() is False       # nothing spawned by us


# ------------------------------------------------------- 4. BLOCKED fail-closed
def test_stubborn_server_is_blocked_and_blocks_the_next_job(stack, tmp_path):
    stack.set_mode("stubborn")
    decoy = stack.decoy()
    log_a, log_b = tmp_path / "a", tmp_path / "b"
    marker = Path(str(stack.lock) + ".BLOCKED")
    p = stack.launch(_sleep_cmd(1), log_a, RWS_STOP_TIMEOUT_S="3")
    rc, out = _finish(p)
    assert rc != 0, out
    assert "BLOCKED" in out
    assert stack.server_pids(), "a stubborn server is left for the operator"
    assert marker.is_file()
    rec = stack.receipt(log_a)
    assert rec["cleanup_state"] == "BLOCKED"
    assert rec["blocked_processes"]
    st = stack.lock_status()
    assert st["blocked"] is True and st["blocked_live_pids"]

    # the next job is refused and starts nothing
    b = stack.launch(_sleep_cmd(1), log_b, name="b", RWS_GPU_LOCK_WAIT_S="2")
    rc_b, out_b = _finish(b, 60)
    assert rc_b != 0
    assert "BLOCKED" in out_b
    assert not (log_b / "lifecycle-launched.json").exists()

    gl = [sys.executable, str(REPO / "scripts/gpu_lock.py"), "--lock",
          str(stack.lock)]
    # refused while the recorded processes are still alive, even with --yes
    for extra in ([], ["--yes"]):
        r = subprocess.run(gl + ["unblock"] + extra, capture_output=True,
                           text=True)
        assert r.returncode == 3, (extra, r.stdout)
        assert json.loads(r.stdout)["cleared"] is False
        assert json.loads(r.stdout)["live_pids"]
    assert marker.is_file()

    # operator resolves the device manually; only then can it be cleared
    stack.kill_all()
    _wait_for(lambda: not stack.server_pids() and not stack.scheduler_pids(),
              30, "stubborn processes gone")
    # ...and still requires the explicit confirmation
    r = subprocess.run(gl + ["unblock"], capture_output=True, text=True)
    assert r.returncode == 2 and json.loads(r.stdout)["cleared"] is False
    r = subprocess.run(gl + ["unblock", "--yes"], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["cleared"] is True
    assert not marker.exists()
    assert list(stack.tmp.glob("gpu.lock.BLOCKED.cleared-*")), "evidence kept"
    assert decoy.poll() is None, "foreign process was signalled"
    decoy.kill()
    # the GPU is usable again
    stack.set_mode("ok")
    (stack.stub / "events.json").write_text("")
    log_c = tmp_path / "c"
    c = stack.launch(_sleep_cmd(1), log_c, name="c", RWS_GPU_LOCK_WAIT_S="5")
    rc_c, out_c = _finish(c)
    assert rc_c == 0, out_c
    _assert_clean(stack, log_c, out_c)


def test_stubborn_scheduler_member_blocks(stack, tmp_path):
    """Leader stops, a session member ignores SIGTERM: BLOCKED with that pid,
    never SIGKILL, and the refusal names it."""
    stack.set_mode("treestubborn")
    decoy = stack.decoy()
    log = tmp_path / "a"
    p = stack.launch(_sleep_cmd(1), log, RWS_STOP_TIMEOUT_S="3")
    rc, out = _finish(p)
    assert rc != 0 and "BLOCKED" in out
    assert stack.server_pids() == []          # the leader did stop
    leftovers = stack.scheduler_pids()
    assert len(leftovers) == 1                # the member survived
    rec = stack.receipt(log)
    assert [b["pid"] for b in rec["blocked_processes"]] == leftovers
    assert rec["blocked_processes"][0]["role"] == "server-session-member"
    assert decoy.poll() is None
    decoy.kill()


# ------------------------------------------------- 6. gateway keeps the lock
def test_gateway_holds_flock_while_child_drains(tmp_path):
    lock = tmp_path / "gpu.lock"
    child = tmp_path / "child.sh"
    child.write_text("#!/usr/bin/env bash\n"
                     "trap 'sleep 4; exit 0' TERM INT\n"
                     "sleep 60 &\nwait\n")
    gw = subprocess.Popen(
        [sys.executable, str(REPO / "scripts/gpu_lock.py"), "--lock", str(lock),
         "wait", "--who", "gw-test", "--", "bash", str(child)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)

    def held() -> bool:
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts/gpu_lock.py"), "--lock",
             str(lock), "status"], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)["held"]

    try:
        _wait_for(held, 20, "gateway lock")
        gw.send_signal(signal.SIGTERM)
        t0 = time.monotonic()
        time.sleep(1.0)
        # RC4.1 behaviour: the gateway died on SIGTERM and the lock was free
        # while the child was still running. Now: lock held, both alive.
        assert gw.poll() is None, "gateway died before its child drained"
        assert held() is True, "flock released while the child was draining"
        out = gw.communicate(timeout=60)[0]
        assert time.monotonic() - t0 >= 3.5, "gateway did not wait for the drain"
        # the child handled the signal itself: ITS exit status is the answer
        assert gw.returncode == 0, (gw.returncode, out)
        assert held() is False, "lock not released after the child exited"
    finally:
        if gw.poll() is None:
            gw.kill()


def test_gateway_reports_a_signal_killed_child(tmp_path):
    lock = tmp_path / "gpu.lock"
    gw = subprocess.Popen(
        [sys.executable, str(REPO / "scripts/gpu_lock.py"), "--lock", str(lock),
         "wait", "--who", "gw-test", "--", "sleep", "60"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)

    def held() -> bool:
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts/gpu_lock.py"), "--lock",
             str(lock), "status"], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)["held"]
    try:
        _wait_for(held, 20, "gateway lock")
        gw.send_signal(signal.SIGTERM)
        out = gw.communicate(timeout=60)[0]
        assert gw.returncode == 143, (gw.returncode, out)
        assert held() is False
    finally:
        if gw.poll() is None:
            gw.kill()


# ---------------------------------------------------- GPU release (unit)
def _lifecycle_module():
    spec = importlib.util.spec_from_file_location(
        "gpu_lifecycle_mod", REPO / "scripts" / "gpu_lifecycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sup(mod, **over):
    import argparse
    a = mod.build_parser().parse_args(
        ["--who", "unit", "--log-dir", "/tmp/x", "--serve-script", "x",
         "--model", "m", "--", "true"])
    for k, v in over.items():
        setattr(a, k, v)
    s = mod.Lifecycle(a)
    return s


def test_gpu_idle_floor_refuses_an_occupied_device(monkeypatch):
    mod = _lifecycle_module()
    monkeypatch.setattr(mod, "read_vram_gtt", lambda card, sys_root="/sys":
                        (10 * 2**30, 0))
    s = _sup(mod)
    s.cpu_test_mode, s.card, s.bdf = False, "card1", "0000:03:00.0"
    assert s.step_gpu_idle() is False          # 10 GiB already in use
    assert s.steps[-1]["status"] == "BUSY"
    monkeypatch.setattr(mod, "read_vram_gtt", lambda card, sys_root="/sys":
                        (28 * 2**20, 0))
    assert s.step_gpu_idle() is True           # idle baseline
    monkeypatch.setattr(mod, "read_vram_gtt", lambda card, sys_root="/sys": None)
    assert s.step_gpu_idle() is False          # unreadable -> fail closed
    assert s.steps[-1]["status"] == "UNVERIFIABLE"
    s2 = _sup(mod, require_gpu_release=False)
    s2.cpu_test_mode, s2.card = False, "card1"
    assert s2.step_gpu_idle() is True          # only with an explicit opt-out


def test_gpu_release_must_return_to_baseline(monkeypatch):
    mod = _lifecycle_module()
    s = _sup(mod, gpu_release_timeout_s=0.2)
    s.cpu_test_mode, s.card, s.bdf = False, "card1", "0000:03:00.0"
    s.vram_baseline = (28 * 2**20, 0)
    monkeypatch.setattr(mod, "read_vram_gtt", lambda card, sys_root="/sys":
                        (10 * 2**30, 0))
    assert s._verify_gpu_release() is False    # 10 GiB still allocated
    assert s.steps[-1]["status"] == "NOT_RELEASED"
    monkeypatch.setattr(mod, "read_vram_gtt", lambda card, sys_root="/sys":
                        (28 * 2**20 + 100 * 2**20, 0))
    assert s._verify_gpu_release() is True     # back within tolerance


def test_drm_card_for_bdf_never_guesses(tmp_path):
    mod = _lifecycle_module()
    root = tmp_path / "sys"
    for name, slot in (("card0", "0000:65:00.0"), ("card1", "0000:03:00.0"),
                       ("card2", "0000:23:00.0")):
        d = root / "class/drm" / name
        d.mkdir(parents=True)
        os.symlink(f"../../../devices/pci0000:00/0000:00:01.7/{slot}", d / "device")
    assert mod.drm_card_for_bdf("0000:23:00.0", str(root)) == "card2"
    assert mod.drm_card_for_bdf("03:00.0", str(root)) == "card1"
    assert mod.drm_card_for_bdf("0000:ff:00.0", str(root)) is None
