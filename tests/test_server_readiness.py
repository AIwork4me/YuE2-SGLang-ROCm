"""server_readiness.py unit tests (RC4.1 M2.5 verification matrix, mocked
/proc trees — the REAL W7900 negative controls run on hardware and land in
reports/w7900_rc4_1/).
"""
from __future__ import annotations

import importlib.util
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "server_readiness_mod", REPO / "scripts" / "server_readiness.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


def write_proc(root: Path, pid: int, ppid: int, comm: str,
               argv: list[str] | None = None, state: str = "S",
               starttime: str = "1000"):
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    argv = argv or [comm]
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (d / "comm").write_text(comm + "\n")
    # /proc/<pid>/stat after the comm: state ppid ... field22=starttime sits
    # at rest[19] (state=rest[0], ppid=rest[1]) — 17 filler tokens between
    # ppid and starttime
    filler = "0 " * 17
    (d / "stat").write_text(
        f"{pid} ({comm}) {state} {ppid} {filler}{starttime} 0 0 0 0 0 0 0 0 "
        f"0 0 0 0 0 0 0 0 0 0\n")
    (d / "status").write_text(
        "Name:\t" + comm[:15] + "\nUid:\t0\t0\t0\t0\n")


class FakeTree:
    def __init__(self, tmp_path):
        self.root = tmp_path / "proc"
        self.root.mkdir()
        write_proc(self.root, 1, 0, "systemd")
        # server pid 500 with scheduler child 501 and an http worker 502
        write_proc(self.root, 500, 1, "sglang",
                   argv=["python", "sglang", "serve", "--model-path",
                         "/ws/models/YuE2-3B", "--port", "31000"])
        write_proc(self.root, 501, 500, "sgl_diffusion::s",
                   argv=["sgl_diffusion::scheduler", "--worker"],
                   starttime="1001")
        write_proc(self.root, 502, 500, "uvicorn-worker")

    def receipt(self, tmp_path) -> Path:
        r = tmp_path / "server-identity.json"
        r.write_text(json.dumps({
            "pid": 500, "uid": 0, "starttime": "1000",
            "argv_sha256": _argv_sha([ "python", "sglang", "serve",
                                       "--model-path",
                                       "/ws/models/YuE2-3B", "--port",
                                       "31000"]),
            "port": 31000, "expect_uid": 0}))
        return r


def _argv_sha(argv):
    import hashlib
    return hashlib.sha256("\0".join(argv).encode()).hexdigest()


@pytest.fixture
def http_ok(monkeypatch):
    monkeypatch.setattr(sr, "http_get",
                        lambda url, timeout=5.0: (200, 0.01, '{"status":"ok"}'))
    return None


def test_ready_with_live_scheduler(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x",
                            proc_root=str(tree.root))
    assert state == "READY"
    assert facts["scheduler_alive"] is True
    assert facts["scheduler_workers"][0]["pid"] == 501


def test_busy_with_connections(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 2)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x",
                        proc_root=str(tree.root))
    assert state == "BUSY"


def test_worker_dead_http_200_is_not_ready(tmp_path, http_ok, monkeypatch):
    """THE RC4 blind spot: scheduler SIGKILLed, /health still 200."""
    tree = FakeTree(tmp_path)
    # reaper already took the scheduler pid away
    import shutil
    shutil.rmtree(tree.root / "501")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x",
                            proc_root=str(tree.root))
    assert state == "WORKER_DEAD"
    assert facts["http_health"] == 200
    assert facts["scheduler_alive"] is False


def test_zombie_scheduler_counts_as_dead(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 501, 500, "sgl_diffusion::s", state="Z",
               argv=["sgl_diffusion::scheduler"])
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x",
                        proc_root=str(tree.root))
    assert state == "WORKER_DEAD"


def test_server_gone_stopped(tmp_path, monkeypatch):
    tree = FakeTree(tmp_path)
    import shutil
    shutil.rmtree(tree.root / "500")
    shutil.rmtree(tree.root / "501")
    shutil.rmtree(tree.root / "502")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x",
                        proc_root=str(tree.root))
    assert state == "STOPPED"


def test_pid_reuse_unknown(tmp_path, http_ok, monkeypatch):
    """Same pid, different argv (reused PID) — identity fails, HTTP 200:
    UNKNOWN, fail-closed (never READY)."""
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 500, 1, "not-sglang", argv=["unrelated", "prog"],
               starttime="9999")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 1)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x",
                        proc_root=str(tree.root))
    assert state == "UNKNOWN"


def test_http_down_scheduler_alive_degraded(tmp_path, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "http_get",
                        lambda url, timeout=5.0: (None, 1.0, "refused"))
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x",
                        proc_root=str(tree.root))
    assert state == "DEGRADED"


def test_stale_receipt_fail_closed(tmp_path, http_ok):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    state, facts = sr.check(str(bad), "http://x")
    assert state == "UNKNOWN"
    assert "fail-closed" in facts["reason"]


def test_progress_file_deadline(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 3)
    pf = tmp_path / "progress.json"
    pf.write_text("{}")
    old = time.time() - 7200
    import os
    os.utime(pf, (old, old))
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x",
                            proc_root=str(tree.root), progress_file=str(pf),
                            progress_deadline_s=3600)
    assert state == "BUSY"
    assert facts["progress_file_age_s"] > 3600


def test_scheduler_found_via_cmdline_fallback(tmp_path, http_ok, monkeypatch):
    """comm truncated but argv carries the scheduler signature."""
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 501, 500, "python3",
               argv=["python3", "-m", "sglang.srt.scheduler", "--worker"])
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x",
                            proc_root=str(tree.root))
    assert state == "READY" and facts["scheduler_alive"] is True


def test_exit_code_mapping(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    rcpt = str(tree.receipt(tmp_path))
    assert sr.main(["check", "--receipt", rcpt, "--url", "http://x",
                    "--proc-root", str(tree.root)]) == 0
    import shutil
    shutil.rmtree(tree.root / "501")
    assert sr.main(["check", "--receipt", rcpt, "--url", "http://x",
                    "--proc-root", str(tree.root)]) == 3


def test_canary_against_real_local_server(tmp_path):
    """Level-2 canary against a stub /v1/audio/generations: verifies the
    request/verify wiring end-to-end (no GPU)."""
    handler = _stub_handler(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        ok, receipt = sr.canary(url, tmp_path / "canary", timeout=30)
        assert ok is True
        assert receipt["audio_bytes"] > 1024
    finally:
        srv.shutdown()


def _stub_handler(tmp_path):
    wav_path = tmp_path / "canary.wav"
    wav_path.write_bytes(b"RIFF" + b"\0" * 4096)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            body = json.dumps({"audio": str(wav_path)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H
