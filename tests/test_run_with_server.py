"""run_with_server.sh lifecycle tests (RC4.1 M3.1) — real wrapper + real
gpu_lock/server_identity/server_readiness infrastructure, stub server.

Closes RC4 follow-up R1-L1: a pilot-style command must never leave an
orphaned server, and the GPU lock must be held for the WHOLE session.
"""
from __future__ import annotations

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
import argparse, json, os, signal, sys, time
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

def log_ev(name, **kw):
    with EVENTS.open("a") as f:
        f.write(json.dumps({"event": name, **kw}) + "\n")

# scheduler worker child: argv carries the signature server_readiness scans
if MODE.read_text() != "nosched":
    pid = os.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c",
                 "import sys, time; sys.argv=['sgl_diffusion::scheduler']; "
                 "time.sleep(86400)",
                 "scheduler-worker"])
    log_ev("scheduler_spawned", pid=pid)

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
            self._send(200, {"data": [{"id": "YuE2-3B"}]})
        else:
            self._send(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); self.rfile.read(n)
        self._send(200, {"audio": "/dev/null", "id": "stub"})
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer((args.host, args.port), H)
def bye(sig, frame):
    log_ev("signal", sig=sig)
    os._exit(0)
signal.signal(signal.SIGINT, bye)
signal.signal(signal.SIGTERM, bye)
log_ev("listening", port=args.port, pid=os.getpid())
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


class FakeStack:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.ws = tmp / "ws"
        self.stub = tmp / "stub"
        self.port = _free_port()
        for rel in REAL:
            dst = self.repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dst)
        serve = self.repo / "scripts" / "serve_yue2_gfx1100.sh"
        serve.write_text(FAKE_SERVE_SH)
        serve.chmod(0o755)
        self.stub.mkdir(parents=True)
        (self.stub / "fake_server.py").write_text(FAKE_SERVER)
        (self.stub / "mode").write_text("ok")
        (self.stub / "events.json").write_text("")
        stub_py = self.stub / "python"
        stub_py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
        stub_py.chmod(0o755)
        venv_bin = self.ws / "environments/yue2-gfx1100/bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        py = venv_bin / "python"
        # Accelerators are hidden (non-existent device index): a torch-enabled
        # host interpreter then takes the sanctioned CPU test path instead of
        # probing the REAL GPU, so the supervisor's VRAM idle floor does not
        # (correctly) refuse to start while another workload holds the device.
        py.write_text(f"#!/bin/sh\nexec env HIP_VISIBLE_DEVICES=99 CUDA_VISIBLE_DEVICES= {sys.executable} \"$@\"\n")
        py.chmod(0o755)
        (self.ws / "models").mkdir(parents=True, exist_ok=True)

    def env(self) -> dict:
        e = dict(os.environ)
        e.update({
            "YUE2_WORKSPACE": str(self.ws),
            "YUE2_REPO": str(self.repo),
            "YUE2_GPU_LOCK": str(self.tmp / "gpu.lock"),
            "RWS_PORT": str(self.port),
            "RWS_LOG_DIR": str(self.tmp / "logs"),
            "RWS_HEALTH_TIMEOUT_S": "60",
            "RWS_HEALTH_POLL_S": "1",
            "RWS_STOP_TIMEOUT_S": "30",
            "RWS_DRAIN_S": "3",
            "RWS_PORT_RELEASE_TIMEOUT_S": "3",
            "RWS_GPU_RELEASE_TIMEOUT_S": "3",
            "STUB_PY": str(self.stub / "python"),
            "STUB_DIR": str(self.stub),
            # sanctioned CPU test-mode token (gpu_identity contract): the
            # stub stack has no GPU; this is a TEST-ONLY authorization
            "YUE2_ALLOW_CPU": "1-I-AM-A-TEST",
        })
        return e

    def run(self, cmd: list[str], timeout=120):
        return subprocess.run(
            ["bash", str(self.repo / "scripts/campaign_ops/run_with_server.sh"),
             "--log-dir", str(self.tmp / "logs"), "--port", str(self.port),
             "--"] + cmd,
            capture_output=True, text=True, env=self.env(), timeout=timeout)

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


def _stub_driver(tmp: Path, rc: int = 0, sleep_s: float = 1.0) -> list[str]:
    script = tmp / "driver.py"
    script.write_text(
        "import sys, time\n"
        f"time.sleep({sleep_s})\n"
        f"sys.exit({rc})\n")
    return [sys.executable, str(script)]


def test_1_success_stops_server(tmp_path):
    stack = FakeStack(tmp_path)
    marker = tmp_path / "marker.txt"
    cmd = [sys.executable, "-c",
           f"from pathlib import Path; Path(r'{marker}').write_text('ran')"]
    r = stack.run(cmd)
    assert r.returncode == 0, r.stderr
    assert marker.is_file()
    assert not stack.port_open(), "server survived the wrapper"
    ev = [json.loads(l) for l in
          (tmp_path / "stub" / "events.json").read_text().splitlines() if l]
    kinds = [e["event"] for e in ev]
    assert "listening" in kinds and "signal" in kinds  # booted and stopped


def test_2_driver_failure_still_stops_server(tmp_path):
    stack = FakeStack(tmp_path)
    r = stack.run(_stub_driver(tmp_path, rc=2))
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert not stack.port_open()
    assert "FAIL" not in r.stdout or "did not stop" not in r.stdout


def test_3_dead_scheduler_fails_readiness(tmp_path):
    """Mode nosched: no scheduler worker → readiness WORKER_DEAD → wrapper
    fails loudly even though /health would answer 200."""
    stack = FakeStack(tmp_path)
    (tmp_path / "stub" / "mode").write_text("nosched")
    r = stack.run(_stub_driver(tmp_path), timeout=120)
    assert r.returncode != 0
    assert "not GENERATION_READY" in r.stdout + r.stderr
    assert not stack.port_open()


def test_4_sigterm_cleans_up(tmp_path):
    stack = FakeStack(tmp_path)
    marker = tmp_path / "started.txt"
    script = tmp_path / "slow.py"
    script.write_text(
        f"from pathlib import Path; Path(r'{marker}').write_text('1')\n"
        "import time; time.sleep(300)\n")
    proc = subprocess.Popen(
        ["bash", str(stack.repo / "scripts/campaign_ops/run_with_server.sh"),
         "--log-dir", str(tmp_path / "logs"), "--port", str(stack.port), "--",
         sys.executable, str(script)],
        env=stack.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    for _ in range(120):
        if marker.is_file():
            break
        time.sleep(0.5)
    assert marker.is_file(), "command never started"
    proc.send_signal(signal.SIGTERM)
    try:
        out, err = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("wrapper did not exit after SIGTERM")
    assert proc.returncode == 143, proc.returncode
    assert not stack.port_open(), "server survived SIGTERM cleanup"


def test_5_gpu_lock_held_for_whole_session(tmp_path):
    """While the wrapped command runs, a competing gpu_lock holder must be
    refused (lock held for the entire session, not just at boot)."""
    stack = FakeStack(tmp_path)
    inside = tmp_path / "inside.txt"
    lock_status = tmp_path / "lockstatus.json"
    script = tmp_path / "probe.py"
    script.write_text(
        f"from pathlib import Path; Path(r'{inside}').write_text('1')\n"
        "import subprocess, sys, time; time.sleep(1)\n"
        f"subprocess.run([sys.executable, r'{REPO}/scripts/gpu_lock.py', "
        f"'--lock', r'{tmp_path}/gpu.lock', 'status'], "
        f"stdout=open(r'{lock_status}', 'w'))\n")
    r = stack.run([sys.executable, str(script)])
    assert r.returncode == 0, r.stderr
    st = json.loads(lock_status.read_text())
    assert st["held"] is True
    who = st.get("holder") or {}
    assert "rc41-lifecycle" in (who.get("who") or "")
    # after the wrapper exits the lock is released
    st2 = subprocess.run(
        [sys.executable, str(REPO / "scripts/gpu_lock.py"),
         "--lock", str(tmp_path / "gpu.lock"), "status"],
        capture_output=True, text=True).stdout
    assert json.loads(st2)["held"] is False
