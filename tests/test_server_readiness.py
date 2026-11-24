"""server_readiness.py unit tests (RC4.1 M2.5 matrix → RC5 M1.3 semantic
readiness), mocked /proc trees — the REAL W7900 negative controls run on
hardware and land in reports/w7900_rc5/.

RC5 M1.3 adds the negative controls the RC4.1 static review found missing:
HTTP 200 + wrong model, HTTP 200 + wrong process/port, missing progress
file, and a canary that must DECODE audio instead of trusting file size.
"""
from __future__ import annotations

import importlib.util
import json
import os
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
    def __init__(self, tmp_path, port: int = 31000):
        self.port = port
        self.root = tmp_path / "proc"
        self.root.mkdir()
        write_proc(self.root, 1, 0, "systemd")
        # server pid 500 with scheduler child 501 and an http worker 502
        write_proc(self.root, 500, 1, "sglang",
                   argv=["python", "sglang", "serve", "--model-path",
                         "/ws/models/YuE2-3B", "--port", str(port)])
        write_proc(self.root, 501, 500, "sgl_diffusion::s",
                   argv=["sgl_diffusion::scheduler", "--worker"],
                   starttime="1001")
        write_proc(self.root, 502, 500, "uvicorn-worker")
        add_listener(self.root, port=port, owner_pid=500, inode="12345")

    def receipt(self, tmp_path) -> Path:
        r = tmp_path / "server-identity.json"
        r.write_text(json.dumps({
            "pid": 500, "uid": 0, "starttime": "1000",
            "argv_sha256": _argv_sha(["python", "sglang", "serve",
                                      "--model-path",
                                      "/ws/models/YuE2-3B", "--port",
                                      str(self.port)]),
            "port": self.port, "expect_uid": 0}))
        return r


def _argv_sha(argv):
    import hashlib
    return hashlib.sha256("\0".join(argv).encode()).hexdigest()


def add_listener(root: Path, port: int, owner_pid: int, inode: str = "12345"):
    """A LISTEN socket on ``port`` in the mock's socket table, held through a
    fd of ``owner_pid`` (what /proc/<pid>/fd/* socket:[ino] looks like)."""
    hexport = format(port, "04X")
    line = (f"  0 0100007F:{hexport} 00000000:0000 0A 00000000:00000000 "
            f"00:00000000 00000000     0        0 {inode} 2]\n")
    (root / "net").mkdir(exist_ok=True)
    with (root / "net/tcp").open("a") as f:
        f.write("  sl  local_address rem_address   st tx_queue rx_queue tr"
                " tm->when retrnsmt   uid  timeout inode\n")
        f.write(line)
    fddir = root / str(owner_pid) / "fd"
    fddir.mkdir(exist_ok=True)
    existing = sorted(int(x.name) for x in fddir.iterdir() if x.name.isdigit())
    os.symlink(f"socket:[{inode}]", fddir / str((existing[-1] + 1) if existing else 5))


MODELS_YUE2 = '{"object":"list","data":[{"id":"YuE2-3B"}]}'
MODELS_OTHER = '{"object":"list","data":[{"id":"Other-9B"}]}'


@pytest.fixture
def http_ok(monkeypatch):
    """HTTP 200 everywhere; /v1/models advertises the expected YuE2 model."""
    def get(url, timeout=5.0):
        if url.endswith("/v1/models"):
            return 200, 0.01, MODELS_YUE2
        if url.endswith("/models"):
            return 200, 0.01, '{"model_path":"/ws/models/YuE2-3B"}'
        return 200, 0.01, '{"status":"ok"}'
    monkeypatch.setattr(sr, "http_get", get)
    return None


def test_ready_with_live_scheduler(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "READY"
    assert facts["scheduler_alive"] is True
    assert facts["scheduler_workers"][0]["pid"] == 501


def test_busy_with_connections(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 2)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                        proc_root=str(tree.root))
    assert state == "BUSY"


def test_worker_dead_http_200_is_not_ready(tmp_path, http_ok, monkeypatch):
    """THE RC4 blind spot: scheduler SIGKILLed, /health still 200."""
    tree = FakeTree(tmp_path)
    # reaper already took the scheduler pid away
    import shutil
    shutil.rmtree(tree.root / "501")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "WORKER_DEAD"
    assert facts["http_health"] == 200
    assert facts["scheduler_alive"] is False


def test_zombie_scheduler_counts_as_dead(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 501, 500, "sgl_diffusion::s", state="Z",
               argv=["sgl_diffusion::scheduler"])
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                        proc_root=str(tree.root))
    assert state == "WORKER_DEAD"


def test_stopped_scheduler_is_not_a_live_worker(tmp_path, http_ok, monkeypatch):
    """SIGSTOPped worker: state T, /health still 200. It can never serve."""
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 501, 500, "sgl_diffusion::s", state="T",
               argv=["sgl_diffusion::scheduler"])
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "WORKER_DEAD"
    assert facts["http_health"] == 200 and facts["scheduler_alive"] is False
    assert facts["scheduler_workers"][0]["state"] == "T"   # disclosed, not hidden


def test_server_gone_stopped(tmp_path, monkeypatch):
    tree = FakeTree(tmp_path)
    import shutil
    shutil.rmtree(tree.root / "500")
    shutil.rmtree(tree.root / "501")
    shutil.rmtree(tree.root / "502")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                        proc_root=str(tree.root))
    assert state == "STOPPED"


def test_pid_reuse_unknown(tmp_path, http_ok, monkeypatch):
    """Same pid, different argv (reused PID) — identity fails, HTTP 200:
    UNKNOWN, fail-closed (never READY)."""
    tree = FakeTree(tmp_path)
    write_proc(tree.root, 500, 1, "not-sglang", argv=["unrelated", "prog"],
               starttime="9999")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 1)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                        proc_root=str(tree.root))
    assert state == "UNKNOWN"


def test_http_down_scheduler_alive_degraded(tmp_path, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "http_get",
                        lambda url, timeout=5.0: (None, 1.0, "refused"))
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, _ = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                        proc_root=str(tree.root))
    assert state == "DEGRADED"


def test_stale_receipt_fail_closed(tmp_path, http_ok):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    state, facts = sr.check(str(bad), "http://x:31000")
    assert state == "UNKNOWN"
    assert "fail-closed" in facts["reason"]


def test_progress_file_deadline(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 3)
    pf = tmp_path / "progress.json"
    pf.write_text("{}")
    old = time.time() - 7200
    os.utime(pf, (old, old))
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
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
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "READY" and facts["scheduler_alive"] is True


def make_wav(path: Path, sr_hz: int = 48000, channels: int = 2, seconds: float = 2.0,
             silent: bool = False) -> None:
    import array
    import math
    import wave
    frames = int(seconds * sr_hz)
    buf = array.array("h", (0 if silent else
                            int(8000 * math.sin(2 * math.pi * 220 * i / sr_hz))
                            for i in range(frames * channels)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr_hz)
        w.writeframes(buf.tobytes())


def _run_stub(handler_factory):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.mark.parametrize("wav", ["valid", "garbage", "silence", "mono16k"])
def test_canary_decodes_audio_for_real(tmp_path, wav):
    """Level-2 canary against a stub /v1/audio/generations. The file is
    written BY the request. valid decodes; garbage (the RC4.1 stub: >1024
    zero bytes), digital silence and 16 kHz mono must all FAIL."""
    srv, url = _run_stub(_stub_handler(tmp_path, wav))
    try:
        ok, receipt = sr.canary(url, tmp_path / "canary", timeout=30)
    finally:
        srv.shutdown()
    if wav == "valid":
        assert ok is True, receipt
        assert receipt["audio"]["samplerate"] == 48000
        assert receipt["audio"]["channels"] == 2
        assert receipt["audio"]["finite"] is True
        assert receipt["audio_seconds"] >= sr.CANARY_MIN_SECONDS
        assert receipt["fresh"] is True
    else:
        assert ok is False, receipt
        assert "reason" in receipt
    if wav == "garbage":
        # decoder-dependent wording: soundfile -> LibsndfileError, fallback -> RIFF
        assert any(k in receipt["reason"] for k in ("RIFF/WAVE", "LibsndfileError", "Error opening"))


def test_canary_fallback_decoder_without_soundfile(tmp_path, monkeypatch):
    """The stdlib-only RIFF reader must agree that a valid file is valid and
    reject a truncated data chunk."""
    import builtins
    real_import = builtins.__import__

    def no_soundfile(name, *a, **k):
        if name == "soundfile":
            raise ImportError("No module named 'soundfile' (test)")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_soundfile)
    srv, url = _run_stub(_stub_handler(tmp_path, "valid"))
    try:
        ok, receipt = sr.canary(url, tmp_path / "canary", timeout=30)
    finally:
        srv.shutdown()
    assert ok is True, receipt
    assert receipt["audio"]["decoder"] == "riff-fallback"
    assert receipt["audio"]["frames"] > 0
    bad = tmp_path / "bad.wav"
    good = tmp_path / "canary.wav"
    make_wav(good)
    raw = bytearray(good.read_bytes())
    bad.write_bytes(raw[:len(raw) // 2])
    with pytest.raises(ValueError):
        sr._decode_audio(bad)


def test_canary_stale_leftover_file_is_not_success(tmp_path):
    """A leftover canary file from an earlier run must never satisfy the
    check when the server returns no audio."""
    out = tmp_path / "canary"
    out.mkdir()
    make_wav(out / "readiness_canary.wav")
    before = (out / "readiness_canary.wav").stat().st_mtime_ns
    time.sleep(0.02)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            body = json.dumps({"audio": ""}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv, url = _run_stub(H)
    try:
        ok, receipt = sr.canary(url, out, timeout=30)
    finally:
        srv.shutdown()
    assert ok is False
    assert not (out / "readiness_canary.wav").exists()  # removed up-front


def _stub_handler(tmp_path, wav: str = "valid"):
    import array
    import math
    import wave
    target = tmp_path / "canary.wav"

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            # written by the request, like a real server
            if wav == "garbage":
                target.write_bytes(b"RIFF" + b"\0" * 4096)
            elif wav == "silence":
                make_wav(target, silent=True)
            elif wav == "mono16k":
                make_wav(target, sr_hz=16000, channels=1)
            else:
                make_wav(target)
            body = json.dumps({"audio": str(target)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


# ------------------------------------------------ RC5 M1.3 semantic readiness
def test_wrong_model_advertised_is_not_ready(tmp_path, monkeypatch):
    """HTTP 200, worker alive, identity fine — but the port serves ANOTHER
    model. RC4.1 recorded models_advertised_ok=False and still said READY."""

    def get(url, timeout=5.0):
        if url.endswith("/v1/models"):
            return 200, 0.01, MODELS_OTHER
        if url.endswith("/models"):
            return 200, 0.01, '{"model_path":"/ws/models/Other-9B"}'
        return 200, 0.01, '{"status":"ok"}'
    monkeypatch.setattr(sr, "http_get", get)
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "UNKNOWN"
    assert facts["models_advertised_ok"] is False
    assert facts["http_health"] == 200 and facts["scheduler_alive"] is True
    rc = sr.main(["check", "--receipt", str(tree.receipt(tmp_path)),
                  "--url", "http://x:31000", "--proc-root", str(tree.root)])
    assert rc == 4


def test_models_endpoint_fallback_when_openai_discovery_is_absent(
        tmp_path, monkeypatch):
    def get(url, timeout=5.0):
        if url.endswith("/v1/models"):
            return 404, 0.01, ""
        if url.endswith("/models"):
            return 200, 0.01, '{"model_path":"/ws/models/YuE2-3B"}'
        return 200, 0.01, '{"status":"ok"}'
    monkeypatch.setattr(sr, "http_get", get)
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "READY"
    assert facts["models_advertised_ok"] is True


def test_models_fallback_requires_exact_model_path(tmp_path, monkeypatch):
    def get(url, timeout=5.0):
        if url.endswith("/v1/models"):
            return 404, 0.01, ""
        if url.endswith("/models"):
            return 200, 0.01, '{"model_path":"/ws/models/YuE2-3B-finetuned"}'
        return 200, 0.01, '{"status":"ok"}'
    monkeypatch.setattr(sr, "http_get", get)
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root),
                            expect_model_path="/ws/models/YuE2-3B")
    assert state == "UNKNOWN"


def test_explicit_model_path_is_binding_even_when_the_name_matches(tmp_path, monkeypatch):
    """Real-GPU control RG-03: the server advertises another YuE2 model
    (name contains 'YuE2'); the caller demanded an exact path."""
    def get(url, timeout=5.0):
        if url.endswith("/v1/models"):
            return 200, 0.01, '{"data":[{"id":"/ws/models/YuE2-3B-finetuned"}]}'
        if url.endswith("/models"):
            return 200, 0.01, '{"model_path":"/ws/models/YuE2-3B-finetuned"}'
        return 200, 0.01, '{"status":"ok"}'
    monkeypatch.setattr(sr, "http_get", get)
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    url = "http://x:31000"
    # name-only expectation (the default) is satisfied by the family name
    state, _ = sr.check(str(tree.receipt(tmp_path)), url, proc_root=str(tree.root))
    assert state == "READY"
    # an explicit path is binding
    state, facts = sr.check(str(tree.receipt(tmp_path)), url, proc_root=str(tree.root),
                            expect_model_path="/ws/models/YuE2-3B")
    assert state == "UNKNOWN" and facts["models_advertised_ok"] is False
    # and it is satisfied by the exact advertised path
    state, _ = sr.check(str(tree.receipt(tmp_path)), url, proc_root=str(tree.root),
                        expect_model_path="/ws/models/YuE2-3B-finetuned")
    assert state == "READY"


def test_foreign_port_owner_is_unknown(tmp_path, http_ok, monkeypatch):
    """HTTP 200 answered by a process that is NOT the receipt's server (the
    listen socket belongs to pid 999): never READY, never signalled."""
    tree = FakeTree(tmp_path)
    for f in (tree.root / "500/fd").iterdir():
        f.unlink()
    (tree.root / "net/tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr"
        " tm->when retrnsmt   uid  timeout inode\n"
        "  0 0100007F:7918 00000000:0000 0A 00000000:00000000 00:00000000"
        " 00000000     0        0 777 2\n")
    fd = tree.root / "999/fd"
    fd.mkdir(parents=True)
    (tree.root / "999/comm").write_text("intruder\n")
    os.symlink("socket:[777]", fd / "3")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "UNKNOWN"
    assert facts["port_owner_state"] == "FOREIGN"
    assert facts["port_owner_pids"] == [999]


def test_url_port_mismatch_is_unknown(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:32000",
                            proc_root=str(tree.root))
    assert state == "UNKNOWN"
    assert facts["port_owner_state"] == "PORT_MISMATCH"


def test_http_200_without_any_listener_is_unknown(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    (tree.root / "net/tcp").unlink()
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "UNKNOWN"
    assert facts["port_owner_state"] == "NO_LISTENER"


def test_port_ownership_recorded_on_the_happy_path(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root))
    assert state == "READY"
    assert facts["port_owner_state"] == "OWNED"
    assert facts["port_owner_pids"] == [500]


def test_progress_file_missing_is_unknown(tmp_path, http_ok, monkeypatch):
    """A configured progress file that does not exist: progress cannot be
    attested. RC4.1 silently treated this as fresh."""
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root),
                            progress_file=str(tmp_path / "absent.json"))
    assert state == "UNKNOWN"
    assert facts["progress_file_missing"] is True
    assert facts["http_health"] == 200 and facts["scheduler_alive"] is True


def test_progress_file_fresh_is_ready(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    pf = tmp_path / "progress.json"
    pf.write_text("{}")
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    state, facts = sr.check(str(tree.receipt(tmp_path)), "http://x:31000",
                            proc_root=str(tree.root), progress_file=str(pf),
                            progress_deadline_s=3600)
    assert state == "READY"
    assert facts["progress_file_age_s"] < 5


def test_check_with_canary_runs_level2(tmp_path, http_ok, monkeypatch):
    srv, stub_url = _run_stub(_stub_handler(tmp_path, "garbage"))
    port = int(stub_url.rsplit(":", 1)[1])
    tree = FakeTree(tmp_path, port=port)  # the receipt port IS the stub port
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    try:
        rc = sr.main(["check", "--receipt", str(tree.receipt(tmp_path)),
                      "--url", stub_url, "--proc-root", str(tree.root),
                      "--canary-dir", str(tmp_path / "canary")])
    finally:
        srv.shutdown()
    assert rc == 5  # level-1 READY, level-2 canary undecodable -> not ready


def test_exit_code_mapping(tmp_path, http_ok, monkeypatch):
    tree = FakeTree(tmp_path)
    monkeypatch.setattr(sr, "established_count", lambda root, port: 0)
    rcpt = str(tree.receipt(tmp_path))
    assert sr.main(["check", "--receipt", rcpt, "--url", "http://x:31000",
                    "--proc-root", str(tree.root)]) == 0
    import shutil
    shutil.rmtree(tree.root / "501")
    assert sr.main(["check", "--receipt", rcpt, "--url", "http://x:31000",
                    "--proc-root", str(tree.root)]) == 3
