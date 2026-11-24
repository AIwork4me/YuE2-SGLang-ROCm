#!/usr/bin/env python3
"""rc5_real_gpu_controls.py — readiness negative controls on a LIVE server.

Invoked by scripts/campaign_ops/rc5_real_gpu_controls.sh inside a lifecycle
session. Every fault is injected into the server this session owns (pids come
from the session's identity receipt and its child table), never into anything
else. The session's own cleanup afterwards has to stop a server whose
scheduler worker is dead.

Controls
  RG-01 healthy server                         -> READY rc 0
  RG-02 real canary                            -> decodable 48 kHz stereo audio
  RG-03 wrong expected model path              -> UNKNOWN rc 4
  RG-04 scheduler SIGSTOP (state T)            -> WORKER_DEAD rc 3, /health 200
  RG-05 scheduler SIGCONT                      -> READY rc 0
  RG-06 scheduler SIGKILL, /health still 200   -> WORKER_DEAD rc 3
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--server-pid", type=int, required=True)
    ap.add_argument("--scheduler-pid", type=int, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    tool = Path(a.repo) / "scripts" / "server_readiness.py"

    def health():
        try:
            with urllib.request.urlopen(a.url + "/health", timeout=5) as r:
                return r.status
        except Exception as e:  # noqa: BLE001
            return getattr(e, "code", None) or 0

    def ready(extra=()):
        r = subprocess.run([a.python, str(tool), "check", "--receipt", a.receipt,
                            "--url", a.url, "--expect-model-path", a.model, *extra],
                           capture_output=True, text=True)
        state = None
        for line in r.stdout.splitlines()[::-1]:
            try:
                state = json.loads(line).get("state")
                break
            except ValueError:
                continue
        return {"rc": r.returncode, "state": state, "http_health": health()}

    def scheduler_state():
        try:
            st = Path(f"/proc/{a.scheduler_pid}/stat").read_text()
            return st[st.rindex(")") + 1:].split()[0]
        except OSError:
            return "gone"

    def own(pid):
        """The pid must be a direct child of the server from OUR receipt."""
        try:
            st = Path(f"/proc/{pid}/stat").read_text()
            return int(st[st.rindex(")") + 1:].split()[1]) == a.server_pid
        except (OSError, ValueError, IndexError):
            return False

    rows = []
    if not own(a.scheduler_pid):
        print(f"REFUSED: pid {a.scheduler_pid} is not a child of server {a.server_pid}")
        return 2
    rows.append({"control": "RG-01 healthy server", "expected": "READY rc 0", **ready()})
    can = subprocess.run([a.python, str(tool), "canary", "--url", a.url, "--out-dir",
                          str(Path(a.log_dir) / "rgc_canary"), "--timeout", "600"],
                         capture_output=True, text=True)
    try:
        crec = json.loads(can.stdout)
        rows.append({"control": "RG-02 real generation canary",
                     "expected": "decodable 48 kHz stereo audio, rc 0", "rc": can.returncode,
                     "ok": crec.get("ok"), "audio": crec.get("audio"),
                     "audio_seconds": crec.get("audio_seconds"), "reason": crec.get("reason")})
    except ValueError:
        rows.append({"control": "RG-02 real generation canary", "rc": can.returncode,
                     "raw": (can.stdout + can.stderr)[-400:]})
    rows.append({"control": "RG-03 wrong expected model path", "expected": "UNKNOWN rc 4",
                 **ready(["--expect-model-path", "/nonexistent/model"])})

    os.kill(a.scheduler_pid, signal.SIGSTOP)
    time.sleep(2)
    rows.append({"control": "RG-04 scheduler SIGSTOP (state T), /health still served",
                 "expected": "WORKER_DEAD rc 3", **ready(), "scheduler_state": scheduler_state()})
    os.kill(a.scheduler_pid, signal.SIGCONT)
    time.sleep(4)
    rows.append({"control": "RG-05 scheduler SIGCONT", "expected": "READY rc 0 again",
                 **ready(), "scheduler_state": scheduler_state()})

    os.kill(a.scheduler_pid, signal.SIGKILL)
    time.sleep(3)
    rows.append({"control": "RG-06 scheduler SIGKILL, /health still 200",
                 "expected": "WORKER_DEAD rc 3 (HTTP false health detected)",
                 **ready(), "scheduler_state": scheduler_state()})

    checks = {
        "RG-01": rows[0]["rc"] == 0 and rows[0]["state"] == "READY",
        "RG-02": (rows[1].get("rc") == 0 and rows[1].get("ok") is True
                  and (rows[1].get("audio") or {}).get("samplerate") == 48000
                  and (rows[1].get("audio") or {}).get("channels") == 2
                  and (rows[1].get("audio") or {}).get("finite") is True
                  and (rows[1].get("audio_seconds") or 0) >= 1.0),
        "RG-03": rows[2]["rc"] == 4 and rows[2]["state"] == "UNKNOWN",
        "RG-04": rows[3]["rc"] == 3 and rows[3]["state"] == "WORKER_DEAD" and rows[3]["http_health"] == 200,
        "RG-05": rows[4]["rc"] == 0 and rows[4]["state"] == "READY",
        "RG-06": rows[5]["rc"] == 3 and rows[5]["state"] == "WORKER_DEAD" and rows[5]["http_health"] == 200,
    }
    rep = {"schema": "yue2-rc5-real-gpu-controls/1",
           "gpu": "AMD Radeon PRO W7900D (gfx1100), real SGLang YuE2 server",
           "server_pid": a.server_pid, "scheduler_pid": a.scheduler_pid,
           "executed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rows": rows, "checks": checks, "passed": all(checks.values())}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rep, indent=1) + "\n")
    print(json.dumps(checks))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
