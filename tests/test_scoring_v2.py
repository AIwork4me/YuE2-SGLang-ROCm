#!/usr/bin/env python3
"""test_scoring_v2.py - safety tests for run_wsb_scoring_v2.sh infrastructure.

Covers the required matrix using MOCKED process tables (fake /proc trees):
valid owned server, missing/invalid PID receipt, PID reuse, multiple matching
servers, unrelated SGLang instance, zombie PID, wrong UID, wrong model path,
wrong port, server-stop failure (BLOCKED, never SIGKILL), push failure
(LOCAL_COMPLETE_REMOTE_PENDING, never false COMPLETE), idempotent invocation.

Only ONE case sends real signals, and only to a `sleep` process spawned by
this test itself. No signals are ever sent to unrelated real processes.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "scripts" / "server_identity.py"
V2 = HERE.parent / "scripts" / "run_wsb_scoring_v2.sh"
PUSH = HERE.parent / "scripts" / "push_verify.sh"

MODEL = "/ws/models/YuE2-3B"
PORT = 31000
PORT_HEX = format(PORT, "04X")
UID = 0


def fake_proc(root, pid, argv, uid=UID, starttime=918563136, state="S",
              listen_port=None, inode=None, established=0):
    """Create a mocked /proc tree entry. Returns the pid dir."""
    d = Path(root) / str(pid)
    (d / "fd").mkdir(parents=True, exist_ok=True)
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    after = [state] + ["0"] * 18 + [str(starttime)] + ["0"] * 12
    (d / "stat").write_text(f"{pid} (sglang) " + " ".join(after) + "\n")
    (d / "status").write_text(
        f"Name:\tsglang\nState:\t{state}\nUid:\t{uid} {uid} {uid} {uid}\n")
    net = Path(root) / "net"
    net.mkdir(parents=True, exist_ok=True)
    if listen_port is not None:
        ph = format(listen_port, "04X")
        line = (f"  0: 0100007F:{ph} 00000000:0000 0A "
                f"0000000000000000 00 00 00 00000000 {inode} \n")
        tf = net / "tcp"
        if not tf.exists():
            tf.write_text("sl local rem st ...\n")
        with open(tf, "a") as f:
            f.write(line)
        fdlink = d / "fd" / "3"
        if not fdlink.exists():
            fdlink.symlink_to(f"socket:[{inode}]")
    if established:
        ph = format(listen_port or PORT, "04X")
        with open(net / "tcp", "a") as f:
            for i in range(established):
                f.write(f"  {i}: 0100007F:{ph} 0100007F:8{ i } 01 "
                        f"00 00 00 00000000 99999{i} \n")
    return d


def ensure_tcp_header(root):
    net = Path(root) / "net"
    net.mkdir(parents=True, exist_ok=True)
    tf = net / "tcp"
    if not tf.exists():
        tf.write_text("sl local rem st ...\n")


def run_tool(*args, env=None, cwd=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                          capture_output=True, text=True, env=e, cwd=cwd)


def base_tree(root, pid=487670, listen_port=PORT, uid=UID, starttime=918563136,
              state="S", model=MODEL, inode=1561116563):
    ensure_tcp_header(root)
    argv = ["/ws/env/bin/python", "/ws/env/bin/sglang", "serve",
            "--model-path", model, "--host", "127.0.0.1",
            "--port", str(listen_port), "--num-gpus", "1"]
    fake_proc(root, pid, argv, uid=uid, starttime=starttime, state=state,
              listen_port=listen_port, inode=inode)
    return argv


def make_receipt(tmppath, pid, argv, uid=UID, starttime=918563136, port=PORT,
                 extra=None):
    import hashlib
    r = {
        "receipt_type": "generation_server_identity",
        "pid": pid, "uid": str(uid), "expect_uid": uid,
        "starttime": str(starttime), "state_at_capture": "S",
        "argv": argv, "argv_sha256": hashlib.sha256(
            "\0".join(argv).encode()).hexdigest(),
        "model_path": MODEL, "host": "127.0.0.1", "port": port,
        "listen_inodes": ["1561116563"], "run_id": "testrun",
    }
    r.update(extra or {})
    p = Path(tmppath) / "server-identity.json"
    p.write_text(json.dumps(r, indent=1))
    return p


class CaptureVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="si-test-"))
        self.proc = self.tmp / "proc"
        self.proc.mkdir()
        self.state = self.tmp / "run-state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_owned_server_capture_verify_stop_dryrun(self):
        argv = base_tree(self.proc)
        r = run_tool("capture", "--run-state", self.state, "--model", MODEL,
                     "--host", "127.0.0.1", "--port", PORT,
                     "--expect-uid", "0", "--proc-root", self.proc)
        self.assertEqual(r.returncode, 0, r.stderr)
        rcpt = self.state / "server-identity.json"
        self.assertTrue(rcpt.is_file())
        data = json.loads(rcpt.read_text())
        self.assertEqual(data["pid"], 487670)
        v = run_tool("verify", "--receipt", rcpt, "--proc-root", self.proc)
        self.assertEqual(v.returncode, 0, v.stderr)
        s = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     "--dry-run")
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("would_signal", s.stdout)

    def test_missing_receipt(self):
        r = run_tool("verify", "--receipt", self.tmp / "nope.json",
                     "--proc-root", self.proc)
        self.assertEqual(r.returncode, 4)

    def test_invalid_receipt_json(self):
        bad = Path(self.tmp) / "bad.json"
        bad.write_text("{not json")
        r = run_tool("verify", "--receipt", bad, "--proc-root", self.proc)
        self.assertEqual(r.returncode, 4)

    def test_pid_reuse(self):
        argv = base_tree(self.proc)
        rcpt = make_receipt(self.tmp, 487670, argv, starttime=918563136)
        # tree now has a DIFFERENT starttime under the same pid -> reuse
        for f in (self.proc / "487670" / "stat").read_text().split("\n"):
            pass
        content = (self.proc / "487670" / "stat").read_text().split()
        content[21] = "999999999"
        (self.proc / "487670" / "stat").write_text(" ".join(content))
        r = run_tool("verify", "--receipt", rcpt, "--proc-root", self.proc)
        self.assertEqual(r.returncode, 2)
        self.assertIn("starttime", r.stderr)
        self.assertIn("PID reused", r.stderr)

    def test_pid_reuse_argv_swap(self):
        argv = base_tree(self.proc)
        rcpt = make_receipt(self.tmp, 487670, argv)
        # same pid, same starttime, but argv replaced (new binary)
        (self.proc / "487670" / "cmdline").write_bytes(
            b"\0".join([b"/usr/bin/python", b"-c", b"evil()"]) + b"\0")
        r = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("argv", r.stderr)

    def test_multiple_matching_servers_ambiguous(self):
        # two servers, each uniquely owning its OWN listen socket on the port
        base_tree(self.proc, pid=100, inode=111)
        base_tree(self.proc, pid=200, inode=222)
        r = run_tool("capture", "--run-state", self.tmp / "rs2",
                     "--model", MODEL, "--host", "127.0.0.1", "--port", PORT,
                     "--expect-uid", "0", "--proc-root", self.proc)
        self.assertIn(r.returncode, (3, 4), r.stderr)
        self.assertTrue("ambiguous" in r.stderr.lower() or "100" in r.stderr,
                        r.stderr)

    def test_unrelated_sglang_instance(self):
        # a DIFFERENT model+port (someone else's sglang)
        base_tree(self.proc, pid=300, listen_port=32000,
                  model="/opt/other/Qwen3-8B")
        r = run_tool("capture", "--run-state", self.tmp / "rs3",
                     "--model", MODEL, "--host", "127.0.0.1", "--port", PORT,
                     "--expect-uid", "0", "--proc-root", self.proc)
        self.assertEqual(r.returncode, 4)
        self.assertIn("no process matches", r.stderr)

    def test_zombie_pid(self):
        argv = base_tree(self.proc)
        rcpt = make_receipt(self.tmp, 487670, argv)
        (self.proc / "487670" / "stat").write_text(
            (self.proc / "487670" / "stat").read_text().replace(
                " (sglang) S ", " (sglang) Z ", 1))
        (self.proc / "487670" / "status").write_text(
            "Name:\tsglang\nState:\tZ (zombie)\nUid:\t0 0 0 0\n")
        r = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     "--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("zombie", r.stderr.lower())

    def test_wrong_uid(self):
        argv = base_tree(self.proc, uid=1000)
        r = run_tool("capture", "--run-state", self.tmp / "rs4",
                     "--model", MODEL, "--host", "127.0.0.1", "--port", PORT,
                     "--expect-uid", "0", "--proc-root", self.proc)
        # 1000-uid server holds the listen socket -> verify fails -> code 2/4
        self.assertIn(r.returncode, (2, 4))
        self.assertIn("uid", r.stderr.lower())

    def test_wrong_model_path_capture_refuses(self):
        base_tree(self.proc)
        r = run_tool("capture", "--run-state", self.tmp / "rs5",
                     "--model", "/ws/models/WRONG-MODEL", "--host", "127.0.0.1",
                     "--port", PORT, "--expect-uid", "0",
                     "--proc-root", self.proc)
        self.assertEqual(r.returncode, 4)

    def test_wrong_port_socket_ownership(self):
        argv = base_tree(self.proc)  # listens on 31000
        # receipt claims port 32000 -> socket ownership mismatch
        rcpt = make_receipt(self.tmp, 487670, argv, port=32000)
        r = run_tool("verify", "--receipt", rcpt, "--proc-root", self.proc)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("ambiguous or not owned", r.stderr)

    def test_gone_pid(self):
        argv = base_tree(self.proc)
        rcpt = make_receipt(self.tmp, 487670, argv)
        shutil.rmtree(self.proc / "487670")
        r = run_tool("verify", "--receipt", rcpt, "--proc-root", self.proc)
        self.assertEqual(r.returncode, 2)


class StopPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="si-stop-"))
        self.proc = self.tmp / "proc"
        self.proc.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _receipt(self, **kw):
        return base_tree(self.proc)

    def test_stop_graceful_sigint_mocked(self):
        argv = self._receipt()
        rcpt = make_receipt(self.tmp, 487670, argv)
        # signal hook: remove the fake pid dir (server exits after SIGINT)
        hook = f"rm -rf {self.proc}/487670"
        r = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     env={"SI_SIGNAL_CMD": hook, "SI_WAIT_TIMEOUT": "0.2",
                          "SI_WAIT_POLL": "0.05"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("stopped", r.stdout)

    def test_stop_failure_blocked_never_sigkill(self):
        argv = self._receipt()
        rcpt = make_receipt(self.tmp, 487670, argv)
        # signal hook: no-op - process "survives" SIGINT and SIGTERM
        r = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     env={"SI_SIGNAL_CMD": "true", "SI_WAIT_TIMEOUT": "0.2",
                          "SI_WAIT_POLL": "0.05"})
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("refusing to SIGKILL", r.stderr)

    def test_stop_refuses_when_requests_in_flight(self):
        argv = self._receipt()
        rcpt = make_receipt(self.tmp, 487670, argv)
        ensure_tcp_header(self.proc)
        with open(self.proc / "net" / "tcp", "a") as f:
            f.write(f"  9: 0100007F:{PORT_HEX} 0100007F:9999 01 00 00 00 00000000 888 \n")
        r = run_tool("stop", "--receipt", rcpt, "--proc-root", self.proc,
                     "--require-idle", env={"SI_SIGNAL_CMD": "true"})
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertIn("in flight", r.stderr)

    def test_real_signal_only_to_self_spawned_sleeper(self):
        """The ONLY real-signal test: signal a sleep we own, matched by its
        true argv ['sleep','300']. No unrelated process is touched."""
        sleeper = subprocess.Popen(["sleep", "300"])
        time.sleep(0.3)
        try:
            st = (Path("/proc") / str(sleeper.pid) / "stat").read_text()
            starttime = st[st.rindex(")") + 1:].split()[19]
            rcpt = make_receipt(self.tmp, sleeper.pid, ["sleep", "300"],
                                starttime=starttime, port=1,
                                extra={"skip_socket_check": True})
            r = run_tool("stop", "--receipt", rcpt, "--timeout", "10",
                         env={"SI_WAIT_POLL": "0.2",
                              "SI_ALLOW_REAL_PROC_HOOKS": "1-I-AM-A-TEST"})
            self.assertEqual(r.returncode, 0, r.stderr)
            rc = sleeper.poll()
            self.assertIsNotNone(rc, "sleeper should have exited after SIGINT")
        finally:
            if sleeper.poll() is None:
                sleeper.kill()
                sleeper.wait()


class SchedulerLogicTests(unittest.TestCase):
    """Lock / idempotency / push-verify behaviors of run_wsb_scoring_v2.sh."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v2-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_runs(self, complete=False):
        ws = Path(self.tmp)
        (ws / "evidence-repo").mkdir(exist_ok=True)
        (ws / "logs").mkdir(exist_ok=True)
        (ws / "scripts").mkdir(exist_ok=True)
        stub = ws / "scripts" / "checkpoint_milestone.sh"
        stub.write_text("#!/usr/bin/env bash\necho stub-checkpoint\n")
        stub.chmod(0o755)
        runs = ws / "wsb_full"
        (runs / "run-state").mkdir(parents=True, exist_ok=True)
        (runs / "run_config.json").write_text(json.dumps(
            {"run_id": "testrun", "model_revision": "m-a-p/YuE2-3B@x",
             "candidates": 2}))
        if complete:
            (runs / "run-state" / "scoring_v2_state.json").write_text(json.dumps(
                {"state": "PIPELINE_COMPLETE", "run_id": "testrun"}))
        return runs

    def test_idempotent_already_complete(self):
        runs = self._fake_runs(complete=True)
        r = subprocess.run(["bash", str(V2), str(runs)],
                           capture_output=True, text=True, timeout=60,
                           env=dict(os.environ,
                                    YUE2_WORKSPACE=self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already recorded", r.stdout + r.stderr)

    def test_duplicate_scheduler_refused(self):
        runs = self._fake_runs()
        lock = runs / "run-state" / "scoring_v2.lock"
        lock.mkdir(parents=True)
        me = os.getpid()
        (lock / "pid").write_text(str(me))
        r = subprocess.run(["bash", str(V2), str(runs)],
                           capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, YUE2_WORKSPACE=self.tmp))
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("refusing duplicate", r.stdout + r.stderr)

    def test_stale_lock_reclaimed(self):
        runs = self._fake_runs()
        lock = runs / "run-state" / "scoring_v2.lock"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("999999")  # not alive
        # will proceed into WAITING loop; kill it after a moment using a
        # manifest of 0 + no driver: it should hit driver-exit path exit 1
        r = subprocess.run(["bash", str(V2), str(runs)],
                           capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, YUE2_WORKSPACE=self.tmp))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("DRIVER EXITED below 384", r.stdout + r.stderr)
        self.assertFalse(lock.exists(), "lock must be cleaned on exit")

    def test_push_verify_failure_reports_pending(self):
        repo = Path(self.tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                        "-m", "init"], check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t",
                                GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                                GIT_COMMITTER_EMAIL="t@t"))
        # push to an invalid remote -> must exit 7, never 0
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "/nonexistent/remote.git"], check=True)
        logf = Path(self.tmp) / "push.log"
        r = subprocess.run(["bash", str(PUSH), "some-branch"],
                           capture_output=True, text=True, timeout=120,
                           cwd=str(repo),
                           env=dict(os.environ, PUSH_ATTEMPTS="1",
                                    PUSH_SLEEP="0", LSREMOTE_TIMEOUT="5",
                                    LOG=str(logf)))
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        self.assertIn("LOCAL_COMPLETE_REMOTE_PENDING", (logf).read_text())

    def test_push_verify_success_on_matching_sha(self):
        # local repo + bare "remote" that receives the push -> verified
        remote = Path(self.tmp) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        repo = Path(self.tmp) / "repo2"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                        "-m", "init"], check=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t",
                                GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                                GIT_COMMITTER_EMAIL="t@t"))
        subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"],
                       check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        str(remote)], check=True)
        logf = Path(self.tmp) / "push2.log"
        r = subprocess.run(["bash", str(PUSH), "main"],
                           capture_output=True, text=True, timeout=120,
                           cwd=str(repo),
                           env=dict(os.environ, PUSH_ATTEMPTS="2",
                                    PUSH_SLEEP="0", LSREMOTE_TIMEOUT="10",
                                    LOG=str(logf)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("verified", logf.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
