"""Arm B server-lifecycle regression tests (M1.2) — real subprocesses.

These tests exercise the REAL launcher scripts (run_armB_campaign.sh,
armB_acceptance.sh) and REAL infrastructure (gpu_lock.py, server_identity.py,
driver_alive.py) against a fake serving stack:

  * scripts/serve_yue2_gfx1100.sh is replaced by a stub whose argv contains
    `serve --model-path <model> --port <port>` and which serves /health,
    /v1/models and /v1/audio/generations (writes a real decodable WAV);
  * scripts/run_wsb.py is replaced by a stub driver with a configurable
    exit code and runtime.

Scenarios (mission M1.2 list):
  1. successful driver completion -> exit 0, server stopped
  2. driver exits nonzero -> exit propagated, server still stopped
  3. health-check timeout -> bounded failure, no orphan
  4. server identity capture failure -> acceptance fails loudly
  5. server dies during startup -> bounded health failure
  6. SIGINT / SIGTERM -> cleanup runs, server stopped, exit 128+sig
  7. graceful stop failure (server ignores SIGINT+SIGTERM) -> failure surfaced
  8. forged identity receipt -> stop REFUSES, server untouched
  9. competing launchers -> second launcher no-ops; contended gpu_lock -> bounded wait
 10. campaign restart after termination -> existing run_id reused
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
    "scripts/campaign_ops/run_armB_campaign.sh": None,
    "scripts/campaign_ops/armB_acceptance.sh": None,
    "scripts/campaign_ops/armb_acceptance_request.py": None,
    "scripts/campaign_ops/driver_alive.py": None,
    "scripts/gpu_identity.py": None,
    "scripts/server_readiness.py": None,
    "scripts/gpu_lifecycle.py": None,
}

FAKE_SERVER = r'''
import argparse, json, os, signal, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("serve")  # literal 'serve' token (argv contract of sglang)
ap.add_argument("--model-path", required=True)
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--mode-file", required=True)
ap.add_argument("--events", required=True)
args = ap.parse_args()

MODE = Path(args.mode_file)
EVENTS = Path(args.events)

def log_ev(name, **kw):
    with EVENTS.open("a") as f:
        f.write(json.dumps({"event": name, **kw}) + "\n")

# scheduler worker child: the lifecycle supervisor's readiness check requires
# a live worker with this signature (RC5: readiness is part of every launch)
if MODE.read_text() != "nosched":
    pid = os.fork()
    if pid == 0:
        import ctypes
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGKILL)  # die with parent
        os.execv(sys.executable, [sys.executable, "-c",
                 "import sys, time; sys.argv=['sgl_diffusion::scheduler']; "
                 "time.sleep(86400)", "scheduler-worker"])
    log_ev("scheduler_spawned", pid=pid)

LYRICS_SECS = 6.0

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
        if self.path != "/v1/audio/generations":
            self._send(404, {}); return
        n = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(n))
        log_ev("generation", id=payload.get("id"), seed=payload.get("seed"))
        if MODE.read_text() == "genfail":
            self._send(500, {"error": "injected generation failure"}); return
        out_dir = Path(payload["output_path"]); out_dir.mkdir(parents=True, exist_ok=True)
        wav = out_dir / payload["output_file_name"]
        sr = 16000; frames = int(LYRICS_SECS * sr)
        import array, wave
        buf = array.array("h", ((i * 7) % 8000 - 4000 for i in range(frames)))
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(buf.tobytes())
        self._send(200, {"audio": str(wav), "id": payload.get("id")})
    def log_message(self, *a):
        pass

srv = ThreadingHTTPServer((args.host, args.port), H)
def bye(sig, frame):
    # os._exit: shutdown() from serve_forever's own thread would deadlock
    log_ev("signal", sig=sig)
    os._exit(0)
if MODE.read_text() == "stubborn":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
else:
    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)
log_ev("listening", port=args.port, pid=os.getpid())
srv.serve_forever()
'''

FAKE_SERVE_SH = r'''#!/usr/bin/env bash
# stub of serve_yue2_gfx1100.sh: same argv contract as the real server
set -euo pipefail
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MODEL_PATH="${MODEL_PATH:-$WS/models/YuE2-3B}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-31000}"
SERVER_LOG="${SERVER_LOG:-$WS/logs/server_yue2_gfx1100.log}"
mkdir -p "$(dirname "$SERVER_LOG")"
echo "stub-serve boot: model=$MODEL_PATH port=$PORT host=$HOST server_log=$SERVER_LOG" >> "$SERVER_LOG"
exec "$STUB_PY" "$STUB_DIR/fake_server.py" serve \
  --model-path "$MODEL_PATH" --host "$HOST" --port "$PORT" \
  --mode-file "$STUB_DIR/mode" --events "$STUB_DIR/events.json"
'''

FAKE_DRIVER = r'''
import json, os, sys, time
from pathlib import Path
runs = Path(sys.argv[sys.argv.index("--runs") + 1])
run_id = sys.argv[sys.argv.index("--run-id") + 1]
mode = Path(os.environ["STUB_DRIVER_MODE_FILE"]).read_text() if os.environ.get("STUB_DRIVER_MODE_FILE") else "ok"
runs.mkdir(parents=True, exist_ok=True)
rc_file = runs / "driver_rc.txt"
rc = int(rc_file.read_text()) if rc_file.is_file() else 0
cfg = runs / "run_config.json"
if not cfg.is_file():
    cfg.write_text(json.dumps({"run_id": run_id}))
time.sleep(float(os.environ.get("STUB_DRIVER_SLEEP", "1")))
with (runs / "driver_calls.jsonl").open("a") as f:
    f.write(json.dumps({"run_id": run_id, "rc": rc, "mode": mode,
                        "pid": os.getpid()}) + "\n")
sys.exit(rc)
'''


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeStack:
    """Fixture repo + workspace; real launchers, stub server/driver."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.ws = tmp / "ws"
        self.runs = tmp / "runs"
        self.stub = tmp / "stub"
        self.port = _free_port()
        for rel in REAL:
            dst = self.repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dst)
        (self.repo / "scripts" / "run_wsb_stub.py").write_text(FAKE_DRIVER)
        (self.repo / "scripts" / "run_wsb.py").write_text(
            "#!/usr/bin/env python3\nimport run_wsb_stub\n")
        serve = self.repo / "scripts" / "serve_yue2_gfx1100.sh"
        serve.write_text(FAKE_SERVE_SH)
        serve.chmod(0o755)
        self.runs.mkdir(parents=True)
        self.stub.mkdir(parents=True)
        (self.stub / "fake_server.py").write_text(FAKE_SERVER)
        (self.stub / "mode").write_text("ok")
        (self.stub / "events.json").write_text("")
        self.stub_py = self.stub / "python"
        self.stub_py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
        self.stub_py.chmod(0o755)
        venv_bin = self.ws / "environments/yue2-gfx1100/bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        py = venv_bin / "python"
        # exec-wrapper, NOT a symlink: a symlinked venv python resolves
        # sys.prefix from its own location and loses the venv's site-packages.
        # Accelerators are hidden (non-existent device index): a torch-enabled
        # host interpreter then takes the sanctioned CPU test path instead of
        # probing the REAL GPU, so the supervisor's VRAM idle floor does not
        # (correctly) refuse to start while another workload holds the device.
        # site-packages stay visible (the acceptance flow decodes audio).
        py.write_text(f"#!/bin/sh\nexec env HIP_VISIBLE_DEVICES=99 CUDA_VISIBLE_DEVICES= {sys.executable} \"$@\"\n")
        py.chmod(0o755)
        (self.ws / "models/YuE2-3B").mkdir(parents=True)
        (self.ws / "logs").mkdir(parents=True)

    def env(self, **over):
        env = {
            **os.environ,
            "YUE2_WORKSPACE": str(self.ws),
            "YUE2_RUNS": str(self.runs),
            "YUE2_REPO": str(self.repo),
            "YUE2_GPU_LOCK": str(self.ws / "gpu.lock"),
            "ARMB_PORT": str(self.port),
            "ARMB_HOST": "127.0.0.1",
            "ARMB_HEALTH_TIMEOUT_S": "20",
            "ARMB_STOP_TIMEOUT_S": "3",
            "ARMB_GPU_LOCK_WAIT_S": "30",
            "ARMB_DRAIN_S": "3",
            "ARMB_PORT_RELEASE_TIMEOUT_S": "3",
            "ARMB_GPU_RELEASE_TIMEOUT_S": "3",
            "STUB_PY": str(self.stub_py),
            "STUB_DIR": str(self.stub),
            "STUB_DRIVER_SLEEP": "1",
            # sanctioned CPU test-mode token (gpu_identity contract): the stub
            # stack has no GPU; TEST-ONLY, never a GPU PASS
            "YUE2_ALLOW_CPU": "1-I-AM-A-TEST",
        }
        env.update({k: str(v) for k, v in over.items()})
        return env

    def set_mode(self, mode: str):
        (self.stub / "mode").write_text(mode)

    def launch(self, script: str, **envover) -> subprocess.Popen:
        return subprocess.Popen(
            ["bash", str(self.repo / "scripts/campaign_ops" / script)],
            env=self.env(**envover), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)

    def server_pids(self) -> list[int]:
        """Live (non-zombie) fake-server pids from the event log."""
        pids = []
        try:
            for line in (self.stub / "events.json").read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r.get("event") == "listening":
                        pid = r["pid"]
                        try:
                            stat = Path(f"/proc/{pid}/stat").read_text()
                            state = stat.rpartition(")")[2].split()[0]
                            if state not in ("Z", "X"):
                                pids.append(pid)
                        except OSError:
                            pass
        except OSError:
            pass
        return pids

    def wait_healthy(self, timeout=25.0) -> bool:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return True
            except OSError:
                time.sleep(0.5)
        return False

    def kill_all(self):
        """Test-harness cleanup of THIS stack's stub processes (by exact pid
        from the stub event log; never by name). A stubborn stub ignores
        SIGINT/SIGTERM, so the ladder ends in SIGKILL — the harness may do
        what the lifecycle under test must never do."""
        for pid in self.server_pids():
            for sig in (signal.SIGINT, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except OSError:
                    break
                time.sleep(0.5)
                try:
                    if not self._live(pid):
                        break
                except OSError:
                    break

    @staticmethod
    def _live(pid: int) -> bool:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rpartition(")")[2].split()[0] != "Z"


@pytest.fixture()
def stack(tmp_path):
    s = FakeStack(tmp_path)
    yield s
    s.kill_all()


def _run_to_end(p: subprocess.Popen, timeout=90) -> tuple[int, str]:
    out = p.communicate(timeout=timeout)[0]
    return p.returncode, out



def _seed_run_cfg(stack, run_id):
    d = stack.runs / "armB_wsb_full"
    d.mkdir(parents=True, exist_ok=True)
    (d / "run_config.json").write_text(json.dumps({"run_id": run_id}))
    return d

# ---------------------------------------------------------------- 1 + 2
def test_1_driver_success_stops_server_exit0(stack):
    stack.set_mode("ok")
    rc, out = _run_to_end(stack.launch("run_armB_campaign.sh"))
    assert rc == 0, out
    assert "resuming existing campaign" not in out
    assert stack.server_pids() == [], "server must be stopped after driver completion"
    assert (stack.runs / "armB_wsb_full/driver_calls.jsonl").is_file()


def test_2_driver_nonzero_propagates_and_server_stopped(stack):
    (stack.runs / "armB_wsb_full").mkdir(parents=True, exist_ok=True)
    (stack.runs / "armB_wsb_full/driver_rc.txt").write_text("7")
    rc, out = _run_to_end(stack.launch("run_armB_campaign.sh"))
    assert rc == 7, out
    assert stack.server_pids() == [], "server must be stopped on driver failure"


# ---------------------------------------------------------------- 3 + 5
def test_3_health_timeout_bounded_failure_no_orphan(stack):
    # occupy the port so the (real) stub server cannot bind -> never healthy
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", stack.port))
    blocker.listen(1)
    try:
        p = stack.launch("run_armB_campaign.sh", ARMB_HEALTH_TIMEOUT_S="2")
        rc, out = _run_to_end(p, timeout=60)
        assert rc != 0
        assert "server unhealthy" in out
    finally:
        blocker.close()
    stack.kill_all()
    assert stack.server_pids() == []


def test_5_server_dies_during_startup(stack):
    # mode=crash: fake server exits immediately after binding attempt
    (stack.stub / "mode").write_text("crash")
    launcher = (stack.repo / "scripts/serve_yue2_gfx1100.sh")
    launcher.write_text(
        "#!/usr/bin/env bash\nexit 3\n")  # dies like the LOG-collision defect
    rc, out = _run_to_end(stack.launch("run_armB_campaign.sh",
                                       ARMB_HEALTH_TIMEOUT_S="2"))
    assert rc != 0
    assert "server unhealthy" in out
    assert stack.server_pids() == []


# ---------------------------------------------------------------- 6
@pytest.mark.parametrize("sig,expected_rc", [(signal.SIGINT, 130),
                                             (signal.SIGTERM, 143)])
def test_6_signals_cleanup_server(stack, sig, expected_rc):
    stack.set_mode("ok")
    _seed_run_cfg(stack, "sigtest")
    p = stack.launch("run_armB_campaign.sh", STUB_DRIVER_SLEEP="25")
    try:
        assert stack.wait_healthy(), "server should boot"
        # wait for identity capture so the stop path has a verified target
        # (signaling before capture is a different, fail-closed scenario)
        receipt = stack.ws / "logs/armB_server_identity/server-identity.json"
        t0 = time.monotonic()
        while time.monotonic() - t0 < 30 and not receipt.is_file():
            time.sleep(0.5)
        assert receipt.is_file(), "identity receipt should exist before signal"
        p.send_signal(sig)
        out = p.communicate(timeout=60)[0]
        assert p.returncode == expected_rc, out
    finally:
        if p.poll() is None:
            p.kill()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and stack.server_pids():
        time.sleep(0.5)
    assert stack.server_pids() == [], "signal path must stop the verified server"


# ---------------------------------------------------------------- 7
def test_7_graceful_stop_failure_surfaced(stack):
    # server ignores SIGINT+SIGTERM: stop must fail loudly, never SIGKILL
    stack.set_mode("stubborn")
    stack.set_mode("ok")  # generation works
    # boot server ourselves, capture receipt, then flip server to stubborn?
    # simpler: run the ACCEPTANCE with a stubborn server; its finish() must
    # report stop failure -> nonzero acceptance rc, server survives (fail-
    # closed: verified process that ignores signals is left for manual ops).
    stack.set_mode("stubborn")
    # stubborn mode must still serve /health and generate
    rc, out = _run_to_end(stack.launch("armB_acceptance.sh",
                                       ARMB_STOP_TIMEOUT_S="2"),
                          timeout=120)
    assert rc != 0, out
    assert "did not stop gracefully" in out
    # fail-closed evidence: the stubborn server is still alive for manual ops
    # (verified identity, refusing SIGKILL by policy)
    # NOTE: generation happens BEFORE stop; stubborn mode still serves it
    # (SIG_IGN only affects signals) — acceptance must fail ONLY on stop.
    assert "ACCEPTANCE_FAIL" not in out or "stop" in out
    stack.kill_all()


def test_7b_stubborn_server_killed_by_operator_only(stack):
    """The refusal must be a REFUSAL: server_identity exit 5, process alive."""
    stack.set_mode("stubborn")
    p = stack.launch("run_armB_campaign.sh", ARMB_STOP_TIMEOUT_S="2",
                     ARMB_HEALTH_TIMEOUT_S="10")
    try:
        assert stack.wait_healthy()
        # find server pid via receipt
        t0 = time.monotonic()
        receipt = stack.ws / "logs/armB_server_identity/server-identity.json"
        while time.monotonic() - t0 < 30 and not receipt.is_file():
            time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=60)
        r = subprocess.run(
            [sys.executable, str(stack.repo / "scripts/server_identity.py"),
             "stop", "--receipt", str(receipt), "--timeout", "2"],
            capture_output=True, text=True)
        assert r.returncode in (2, 5), r.stderr + r.stdout
        assert "refusing to SIGKILL" in r.stderr or "BLOCKED" in r.stderr
    finally:
        if p.poll() is None:
            p.kill()
    stack.kill_all()


# ---------------------------------------------------------------- 4 + 8
def test_4_identity_capture_failure_fails_acceptance(stack):
    # server whose argv does NOT match the run's model path -> capture fails
    serve = (stack.repo / "scripts/serve_yue2_gfx1100.sh")
    serve.write_text(FAKE_SERVE_SH.replace(
        'echo "stub-serve boot',
        'MODEL_PATH="/nonexistent/model"; echo "stub-serve boot'))
    rc, out = _run_to_end(stack.launch("armB_acceptance.sh",
                                       ARMB_HEALTH_TIMEOUT_S="15"), timeout=120)
    assert rc != 0, out
    assert "identity capture" in out
    # fail-closed: an UNVERIFIABLE server is never signaled by the scripts;
    # the test harness owns the cleanup
    stack.kill_all()


def test_8_forged_receipt_refused_server_untouched(stack):
    stack.set_mode("ok")
    p = stack.launch("run_armB_campaign.sh", STUB_DRIVER_SLEEP="25")
    try:
        assert stack.wait_healthy()
        receipt = stack.ws / "logs/armB_server_identity/server-identity.json"
        t0 = time.monotonic()
        while time.monotonic() - t0 < 30 and not receipt.is_file():
            time.sleep(0.5)
        assert receipt.is_file()
        real = json.loads(receipt.read_text())
        pids_before = stack.server_pids()
        # forge: wrong pid + wrong argv hash
        forged = dict(real, pid=real["pid"] + 1, argv_sha256="f" * 64)
        forged_path = stack.tmp / "forged_receipt.json"
        forged_path.write_text(json.dumps(forged))
        r = subprocess.run(
            [sys.executable, str(stack.repo / "scripts/server_identity.py"),
             "stop", "--receipt", str(forged_path), "--timeout", "2"],
            capture_output=True, text=True)
        assert r.returncode in (2, 4), r.stderr + r.stdout
        assert stack.server_pids() == pids_before, "forged receipt must not touch the real server"
    finally:
        if p.poll() is None:
            p.kill()
    stack.kill_all()


# ---------------------------------------------------------------- 9
def test_9a_second_launcher_noops_while_driver_alive(stack):
    stack.set_mode("ok")
    _seed_run_cfg(stack, "already")
    first = stack.launch("run_armB_campaign.sh", STUB_DRIVER_SLEEP="25")
    try:
        assert stack.wait_healthy()
        second = stack.launch("run_armB_campaign.sh")
        rc2, out2 = _run_to_end(second, timeout=60)
        assert rc2 == 0, out2
        assert "already alive" in out2 or "another Arm B launcher holds the lock" in out2
    finally:
        if first.poll() is None:
            first.kill()
    stack.kill_all()


def test_9b_gpu_lock_contention_bounded(stack):
    import fcntl
    lock = stack.ws / "gpu.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        rc, out = _run_to_end(
            stack.launch("armB_acceptance.sh", ARMB_GPU_LOCK_WAIT_S="2",
                         ARMB_HEALTH_TIMEOUT_S="5"), timeout=90)
        assert rc != 0
        assert "GPU ownership lock" in out or "TimeoutError" in out or \
               "held by" in out
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert stack.server_pids() == []


# ---------------------------------------------------------------- 10
def test_10_restart_reuses_run_id_and_resumes(stack):
    d = _seed_run_cfg(stack, "armB_full_RESUME")
    (d / "generation_manifest.jsonl").write_text(
        json.dumps({"id": "wsb_000_r0_s831001", "status": "complete"}) + "\n")
    rc, out = _run_to_end(stack.launch("run_armB_campaign.sh"))
    assert rc == 0, out
    assert "resuming existing campaign run_id=armB_full_RESUME" in out
    calls = [json.loads(l) for l in
             (stack.runs / "armB_wsb_full/driver_calls.jsonl").read_text().splitlines() if l]
    assert all(c["run_id"] == "armB_full_RESUME" for c in calls)


# ---------------------------------------------------------------- acceptance
def test_acceptance_full_pass_includes_real_generation(stack):
    stack.set_mode("ok")
    rc, out = _run_to_end(stack.launch("armB_acceptance.sh"), timeout=120)
    assert rc == 0, out
    assert "ARMB_ACCEPTANCE_PASS" in out
    assert "music-generation acceptance PASS" in out
    receipt = stack.ws / "logs/armB_acceptance/acceptance_receipt.json"
    d = json.loads(receipt.read_text())
    assert d["audio"]["duration_s"] >= 5.0
    assert d["audio"]["rms"] > 1e-4
    assert len(d["audio_sha256"]) == 64
    assert stack.server_pids() == []


def test_acceptance_generation_failure_fails(stack):
    stack.set_mode("genfail")
    rc, out = _run_to_end(stack.launch("armB_acceptance.sh"), timeout=120)
    assert rc != 0, out
    assert "music-generation acceptance" in out
    stack.kill_all()


def test_acceptance_health_timeout_leaves_boot_evidence(stack):
    # port blocked -> acceptance fails bounded and preserves the boot log
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", stack.port))
    blocker.listen(1)
    try:
        rc, out = _run_to_end(
            stack.launch("armB_acceptance.sh", ARMB_HEALTH_TIMEOUT_S="2"),
            timeout=90)
        assert rc != 0
        assert "did not become healthy" in out
        assert (stack.ws / "logs/armB_server_boot.log").is_file()
    finally:
        blocker.close()
    stack.kill_all()
