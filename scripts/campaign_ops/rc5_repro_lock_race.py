#!/usr/bin/env python3
"""rc5_repro_lock_race.py — deterministic reproduction of the RC4.1 GPU-lock
lifecycle race (RC5 M1.1, "REPRODUCE before FIX").

RC4.1 launcher layout (PR #18 head 6f1b7f7):

    outer bash (EXIT trap -> stop_server)
      └─ gpu_lock.py wait -- bash -c lifecycle_flow      (holds the flock)
           └─ setsid server ... ; <command> ; return

When the command returns, the gateway releases the flock and THEN the outer
trap stops the server. While the server is still shutting down the lock is
free: a second job can start on a GPU that still holds the first server.

This harness runs a real launcher (old or new) with a stub server that needs
several seconds to exit after SIGINT, and samples (lock held?, server alive?)
every 100 ms. The defect signature is any sample with
``lock_held == False and server_alive == True``.

Usage:
  python scripts/campaign_ops/rc5_repro_lock_race.py --label RC4.1 --repo <checkout of 6f1b7f7> \
      --label RC5 --repo <this repo> --out reports/w7900_rc5/01_LOCK_RACE_REPRO.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

FAKE_SERVER = r'''
import argparse, json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("serve"); ap.add_argument("--model-path", required=True)
ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, required=True)
ap.add_argument("--events", required=True); ap.add_argument("--stop-delay", type=float, default=6.0)
a = ap.parse_args()
EV = Path(a.events)
def log_ev(n, **kw):
    with EV.open("a") as f: f.write(json.dumps({"event": n, **kw}) + "\n")
pid = os.fork()
if pid == 0:
    import ctypes; ctypes.CDLL("libc.so.6").prctl(1, signal.SIGKILL)
    os.execv(sys.executable, [sys.executable, "-c",
             "import sys,time; sys.argv=['sgl_diffusion::scheduler']; time.sleep(86400)", "w"])
def bye(sig, frame):
    log_ev("signal", sig=sig); time.sleep(a.stop_delay); log_ev("exiting"); os._exit(0)
signal.signal(signal.SIGINT, bye); signal.signal(signal.SIGTERM, bye)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({"status": "ok"} if self.path == "/health"
                       else {"data": [{"id": a.model_path}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *x): pass
log_ev("listening", pid=os.getpid())
ThreadingHTTPServer((a.host, a.port), H).serve_forever()
'''

SERVE_SH = r'''#!/usr/bin/env bash
set -euo pipefail
# the RC4.1 launcher exports PORT/HOST/SERVER_LOG only; MODEL_PATH has a default
MODEL_PATH="${MODEL_PATH:-$YUE2_WORKSPACE/models/YuE2-3B}"
exec "$STUB_PY" "$STUB_DIR/fake_server.py" serve --model-path "$MODEL_PATH" \
  --host "$HOST" --port "$PORT" --events "$STUB_DIR/events.json" --stop-delay "$STOP_DELAY"
'''


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def alive(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return False


def run_case(label: str, repo: Path, tmp: Path, stop_delay: float) -> dict:
    work = tmp / label
    r = work / "repo"
    shutil.copytree(repo / "scripts", r / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    (r / "scripts/serve_yue2_gfx1100.sh").write_text(SERVE_SH)
    stub = work / "stub"
    stub.mkdir(parents=True)
    (stub / "fake_server.py").write_text(FAKE_SERVER)
    (stub / "events.json").write_text("")
    py = work / "py"
    py.write_text(f'#!/bin/sh\nexec {sys.executable} -S "$@"\n')
    py.chmod(0o755)
    venv = work / "ws/environments/yue2-gfx1100/bin"
    venv.mkdir(parents=True)
    shutil.copyfile(py, venv / "python")
    (venv / "python").chmod(0o755)
    (work / "ws/models").mkdir(parents=True)
    port = free_port()
    lock = work / "gpu.lock"
    marker = work / "cmd-done"
    cmd = [sys.executable, "-c",
           f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).write_text('1')"]
    env = {**os.environ, "YUE2_WORKSPACE": str(work / "ws"), "YUE2_REPO": str(r),
           "YUE2_GPU_LOCK": str(lock), "RWS_PORT": str(port), "RWS_LOG_DIR": str(work / "logs"),
           "RWS_HEALTH_TIMEOUT_S": "60", "RWS_HEALTH_POLL_S": "1", "RWS_STOP_TIMEOUT_S": "30",
           "RWS_DRAIN_S": "1", "RWS_PORT_RELEASE_TIMEOUT_S": "5", "RWS_GPU_RELEASE_TIMEOUT_S": "2",
           "STUB_PY": str(py), "STUB_DIR": str(stub), "STOP_DELAY": str(stop_delay),
           "YUE2_ALLOW_CPU": "1-I-AM-A-TEST"}
    for k in ("YUE2_EXPECT_GPU_BDF", "YUE2_SERVE_SCRIPT", "YUE2_LIFECYCLE_TEST_BARRIER"):
        env.pop(k, None)
    p = subprocess.Popen(["bash", str(r / "scripts/campaign_ops/run_with_server.sh"),
                          "--log-dir", str(work / "logs"), "--port", str(port), "--", *cmd],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    ev = stub / "events.json"
    server_pid = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 120 and server_pid is None:
        if ev.is_file():
            for line in ev.read_text().splitlines():
                if line.strip() and json.loads(line).get("event") == "listening":
                    server_pid = json.loads(line)["pid"]
        time.sleep(0.05)
    if server_pid is None:
        return {"label": label, "error": "server never started", "output": p.communicate(timeout=60)[0][-800:]}
    while not marker.is_file() and time.monotonic() - t0 < 120:
        time.sleep(0.02)
    samples = []
    t_cmd_end = time.monotonic()
    while time.monotonic() - t_cmd_end < stop_delay + 20:
        st = subprocess.run([sys.executable, "-S", str(r / "scripts/gpu_lock.py"), "--lock",
                             str(lock), "status"], capture_output=True, text=True)
        try:
            held = json.loads(st.stdout)["held"]
        except ValueError:
            held = None
        s_alive = alive(server_pid)
        samples.append({"t": round(time.monotonic() - t_cmd_end, 2), "lock_held": held,
                        "server_alive": s_alive})
        if p.poll() is not None and not s_alive:
            break
        time.sleep(0.1)
    try:
        out = p.communicate(timeout=60)[0]
    except subprocess.TimeoutExpired:
        p.kill()
        out = "LAUNCHER TIMEOUT"
    race = [s for s in samples if s["lock_held"] is False and s["server_alive"] is True]
    if alive(server_pid):
        try:
            os.kill(server_pid, signal.SIGKILL)
        except OSError:
            pass
    return {
        "label": label, "repo": str(repo), "launcher_rc": p.returncode,
        "stop_delay_s": stop_delay, "samples": len(samples),
        "samples_with_lock_free_and_server_alive": len(race),
        "first_race_sample": race[0] if race else None,
        "last_race_sample": race[-1] if race else None,
        "race_window_s": round(race[-1]["t"] - race[0]["t"], 2) if race else 0.0,
        "defect_reproduced": bool(race),
        "launcher_output_tail": out[-600:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", action="append", required=True)
    ap.add_argument("--repo", action="append", required=True)
    ap.add_argument("--stop-delay", type=float, default=6.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tmp", type=Path, default=Path("/data/yue2/tmp/rc5_lock_race_repro"))
    a = ap.parse_args()
    if a.tmp.exists():
        shutil.rmtree(a.tmp)
    a.tmp.mkdir(parents=True)
    results = [run_case(label, Path(repo), a.tmp, a.stop_delay)
               for label, repo in zip(a.label, a.repo)]
    out = {"receipt_type": "rc5_lock_race_reproduction",
           "executed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "method": "real launcher + stub server that needs stop_delay seconds to exit; "
                     "(lock held, server alive) sampled every 100 ms after the wrapped "
                     "command returned; defect = any sample with lock free AND server alive",
           "results": results}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    for r in results:
        print(f"{r.get('label')}: defect_reproduced={r.get('defect_reproduced')} "
              f"race_samples={r.get('samples_with_lock_free_and_server_alive')} "
              f"window={r.get('race_window_s')}s rc={r.get('launcher_rc')} {r.get('error', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
