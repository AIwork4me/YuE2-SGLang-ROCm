#!/usr/bin/env python3
"""gpu_lifecycle.py — single-owner GPU server lifecycle supervisor (RC5 M1.1).

RC4.1 static review finding (P0, GPU Lock Lifecycle Atomicity): the launcher
held no lock itself. ``gpu_lock.py`` (the gateway) released the flock the
moment the inner flow returned, and only THEN did the outer EXIT trap run
``stop_server()``. A second job could acquire the GPU lock while the first
server still held VRAM — the exact interleaving that reproducibly triggers
``HIP error: an illegal memory access`` (RCA-7).

This supervisor is ONE process that owns the flock fd for its whole life and
performs every step itself, in this order and never differently::

    Acquire GPU Lock (refused while a BLOCKED marker exists)
        Verify GPU Identity            (fail-loud, hard-bounded compute probe)
        Verify GPU Idle                 (VRAM floor: nobody else on the device)
        Launch Owned Server             (spawn receipt: pid+starttime+session)
        Verify Server Identity          (pid / starttime / argv sha / uid / port)
        Verify Generation Readiness     (worker alive, HTTP, model, canary)
        Execute Generation Driver       (signals forwarded, bounded drain)
        Drain In-flight Requests
        Stop Verified Server            (identity receipt, else spawn receipt)
        Verify Process Tree Termination (session ownership proof only)
        Verify Port Release
        Verify GPU Resource Release     (VRAM/GTT back to the pre-boot baseline)
    Release GPU Lock

Ownership rule: a signal is only ever sent to (a) the verified server pid,
(b) processes proven to be in the session we created, (c) our own driver
child. Never by name/port match, never pkill/killall/fuser -k. A server that
survives SIGINT+SIGTERM is never SIGKILLed: the lifecycle ends BLOCKED, a
``<lock>.BLOCKED`` marker is written and every later acquisition is refused
until an operator runs ``gpu_lock.py unblock --yes``.

Residual (unavoidable): SIGKILL to this process releases the flock early.
The next start is still refused by the VRAM floor check while the orphan
holds memory; the operator stops it with ``server_identity.py stop``.

Exit codes: driver rc when the lifecycle closed cleanly; 128+sig on signals;
1 when the lifecycle itself failed (never hidden behind a zero driver rc).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gpu_lock  # noqa: E402
import server_identity as si  # noqa: E402

PROC_ROOT = "/proc"
PY = sys.executable
# child tools run under the SAME interpreter flags (a `-S` stub stack must
# stay free of a host torch; production venvs are unaffected)
PY_FLAGS = ["-S"] if sys.flags.no_site else []


def _proc_fields(pid: int) -> dict | None:
    try:
        return si.read_stat_fields(PROC_ROOT, pid)
    except si.IdentError:
        return None


def _http(url: str, timeout: float = 5.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(65536)
    except Exception as e:  # noqa: BLE001 - any failure is "not healthy"
        name = type(e).__name__
        return getattr(e, "code", None), f"{name}: {e}".encode()


def port_connects(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _write_durable(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        f.write(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def drm_card_for_bdf(bdf: str, sys_root: str = "/sys") -> str | None:
    """The drm card whose PCI device IS ``bdf`` (no 'first AMD GPU' guess)."""
    import gpu_identity
    for card in sorted(Path(sys_root, "class/drm").glob("card[0-9]*")):
        try:
            real = os.path.realpath(card / "device")
        except OSError:
            continue
        if gpu_identity.bdf_matches(bdf, os.path.basename(real)):
            return card.name
    return None


def read_vram_gtt(card: str, sys_root: str = "/sys") -> tuple[int, int] | None:
    d = Path(sys_root, "class/drm", card, "device")
    try:
        vram = int((d / "mem_info_vram_used").read_text().strip())
        gtt = int((d / "mem_info_gtt_used").read_text().strip())
        return vram, gtt
    except (OSError, ValueError):
        return None


class Lifecycle:
    def __init__(self, a):
        self.a = a
        self.who = a.who
        self.log_dir = Path(a.log_dir)
        self.url = f"http://{a.host}:{a.port}"
        self.steps: list[dict] = []
        self.t0 = time.time()
        self.spawn: dict | None = None
        self.server_proc: subprocess.Popen | None = None
        self.cmd_proc: subprocess.Popen | None = None
        self.pending_sig: int | None = None
        self.cmd_rc: int | None = None
        self.cpu_test_mode = False
        self.bdf: str | None = None
        self.card: str | None = None
        self.vram_baseline: tuple[int, int] | None = None
        self.blocked: list[dict] = []
        self.cleanup_state = "NOT_NEEDED"
        self.flow_error = None
        self.server_exit: int | None = None

    # ------------------------------------------------------------------ util
    def say(self, step: str, msg: str) -> None:
        print(f"[lifecycle] {step}: {msg}", flush=True)

    def record(self, step: str, status: str, t_start: float, **detail) -> dict:
        row = {"step": step, "status": status,
               "seconds": round(time.time() - t_start, 3), **detail}
        self.steps.append(row)
        return row

    def _identity_receipt(self) -> Path:
        return Path(self.a.receipt_dir) / "server-identity.json"

    def _spawn_receipt_path(self) -> Path:
        return Path(self.a.receipt_dir) / "server-spawn.json"

    # ---------------------------------------------------------------- signal
    def _on_signal(self, signum, _frame):
        if self.pending_sig is not None:
            self.say("signal", f"additional signal {signum} ignored (already "
                               "stopping)")
            return
        self.pending_sig = signum
        self.say("signal", f"received {signal.Signals(signum).name}: finishing "
                           "in-flight work, then cleanup")
        self._forward_to_driver(signum)

    def _forward_to_driver(self, signum: int) -> None:
        p = self.cmd_proc
        if p is None or p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signum)  # our own driver's process group
        except (ProcessLookupError, PermissionError):
            pass

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass

    # ------------------------------------------------------------------ steps
    def step_gpu_identity(self) -> bool:
        t = time.time()
        rdir = Path(self.a.identity_dir)
        rdir.mkdir(parents=True, exist_ok=True)
        receipt = rdir / "pre_boot_gpu_identity.json"
        cmd = [PY, *PY_FLAGS, str(HERE / "gpu_identity.py"), "verify",
               "--expect-arch", self.a.expect_arch,
               "--receipt", str(receipt),
               "--probe-budget-s", str(self.a.probe_budget_s)]
        if self.a.expect_bdf:
            cmd += ["--expect-bdf", self.a.expect_bdf]
        r = subprocess.run(cmd, capture_output=True, text=True)
        try:
            rec = json.loads(receipt.read_text())
        except (OSError, ValueError):
            rec = {"status": "GPU_UNAVAILABLE",
                   "reason": "no identity receipt written"}
        status = rec.get("status")
        self.cpu_test_mode = status == "CPU_TEST_MODE_AUTHORIZED"
        bound = (rec.get("device") or {}).get("pci_bdf")
        if status in ("GPU_EXECUTION_VERIFIED", "GPU_EXECUTION_UNVERIFIED") \
                and bound:
            self.bdf = bound
            self.card = drm_card_for_bdf(bound)
        self.record("gpu_identity", status or "GPU_UNAVAILABLE", t,
                    receipt=str(receipt), bdf=self.bdf, card=self.card,
                    gpu_execution="CPU_TEST_MODE" if self.cpu_test_mode
                    else ("VERIFIED" if status == "GPU_EXECUTION_VERIFIED"
                          else status), rc=r.returncode)
        if r.returncode != 0 or status not in gpu_identity_OK:
            self.say("gpu_identity", f"FAIL status={status} "
                                     f"reason={rec.get('reason')}")
            if r.stderr.strip():
                print(r.stderr.strip()[-800:], flush=True)
            return False
        self.say("gpu_identity", f"{status} device={rec.get('device', {}).get('name')} "
                                 f"bdf={self.bdf} vram_gib="
                                 f"{rec.get('device', {}).get('total_memory_gib')}")
        return True

    def step_gpu_idle(self) -> bool:
        t = time.time()
        if self.cpu_test_mode:
            self.record("gpu_idle", "NOT_APPLICABLE_CPU_TEST_MODE", t)
            return True
        if not self.card:
            self.record("gpu_idle", "UNVERIFIABLE", t,
                        reason="no drm card bound to the GPU BDF")
            return not self.a.require_gpu_release
        mem = read_vram_gtt(self.card)
        if mem is None:
            self.record("gpu_idle", "UNVERIFIABLE", t,
                        reason=f"cannot read mem_info for {self.card}")
            return not self.a.require_gpu_release
        self.vram_baseline = mem
        used_mib = mem[0] / 2**20
        ok = used_mib <= self.a.max_idle_vram_mib
        self.record("gpu_idle", "IDLE" if ok else "BUSY", t,
                    vram_used_bytes=mem[0], gtt_used_bytes=mem[1],
                    max_idle_vram_mib=self.a.max_idle_vram_mib)
        if not ok:
            self.say("gpu_idle", f"FAIL: {used_mib:.0f} MiB already in use on "
                                 f"{self.bdf} (> {self.a.max_idle_vram_mib} MiB); "
                                 "another process occupies the GPU — refusing "
                                 "to start a server on it")
        return ok

    def step_launch_server(self) -> bool:
        t = time.time()
        env = dict(os.environ)
        env.update({
            "YUE2_WORKSPACE": self.a.workspace,
            "YUE2_VENV": self.a.venv,
            "MODEL_PATH": self.a.model,
            "VAE_PATH": self.a.vae,
            "PORT": str(self.a.port),
            "HOST": self.a.host,
            "SERVER_LOG": self.a.server_log,
            "GPU_ID": str(self.a.gpu_id),
        })
        env.pop("LOG", None)  # legacy collision: LOG(dir) vs SERVER_LOG(file)
        boot_log = open(self.a.boot_log, "ab")
        try:
            self.server_proc = subprocess.Popen(
                [self.a.shell, self.a.serve_script], env=env,
                stdin=subprocess.DEVNULL, stdout=boot_log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True)
        finally:
            boot_log.close()
        pid = self.server_proc.pid
        f = None
        for _ in range(50):  # the child is ours; /proc appears immediately
            f = _proc_fields(pid)
            if f is not None:
                break
            time.sleep(0.02)
        if f is None:
            self.record("launch_server", "FAILED", t, pid=pid,
                        reason="spawned pid has no /proc entry")
            return False
        self.spawn = {"receipt_type": "generation_server_spawn",
                      "pid": pid, "uid": os.getuid(),
                      "starttime": f["starttime"], "session": f["session"],
                      "launched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                       time.gmtime()),
                      "serve_script": self.a.serve_script,
                      "supervisor_pid": os.getpid()}
        _write_durable(self._spawn_receipt_path(), self.spawn)
        self.record("launch_server", "LAUNCHED", t, pid=pid,
                    starttime=f["starttime"], session=f["session"])
        self.say("launch_server", f"pid={pid} session={f['session']} "
                                  f"(spawn receipt {self._spawn_receipt_path()})")
        return True

    def step_health(self) -> bool:
        t = time.time()
        deadline = time.monotonic() + self.a.health_timeout_s
        outcome = "TIMEOUT"
        while time.monotonic() < deadline:
            if self.pending_sig is not None:
                outcome = "SIGNAL"
                break
            rc = self.server_proc.poll()
            if rc is not None:
                self.server_exit = rc
                outcome = f"EXITED rc={rc}"
                break
            code, _ = _http(self.url + "/health", timeout=5.0)
            if code == 200:
                outcome = "HEALTHY"
                break
            time.sleep(self.a.health_poll_s)
        ok = outcome == "HEALTHY"
        self.record("health", outcome, t, url=self.url,
                    boot_log=self.a.boot_log)
        if not ok:
            self.say("health", f"FAIL: server unhealthy ({outcome}) after "
                               f"{self.a.health_timeout_s}s (boot log: "
                               f"{self.a.boot_log})")
        else:
            self.say("health", f"HTTP 200 on {self.url}")
        return ok

    def _tool(self, script: str, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([PY, *PY_FLAGS, str(HERE / script), *argv],
                              capture_output=True, text=True)

    def step_server_identity(self) -> bool:
        t = time.time()
        # --pid pins the capture to the process WE spawned: discovery by
        # argv+port alone could bind the receipt to a foreign process that
        # legitimately owns the port (found by the RC5 fault-injection tests)
        r = self._tool("server_identity.py", "capture",
                       "--run-state", self.a.receipt_dir,
                       "--model", self.a.model,
                       "--host", self.a.host, "--port", str(self.a.port),
                       "--pid", str(self.spawn["pid"]))
        if r.returncode != 0:
            self.record("server_identity", "CAPTURE_FAILED", t, rc=r.returncode,
                        stderr=r.stderr.strip()[-600:])
            self.say("server_identity", f"FAIL: identity capture failed "
                                        f"(rc={r.returncode}) {r.stderr.strip()[-300:]}")
            return False
        r2 = self._tool("server_identity.py", "verify",
                        "--receipt", str(self._identity_receipt()))
        # the captured pid must be the process WE spawned (ownership chain)
        chain_ok = False
        try:
            rec = si.load_receipt(self._identity_receipt())
            chain_ok = bool(self.spawn) and rec["pid"] == self.spawn["pid"] \
                and str(rec["starttime"]) == str(self.spawn["starttime"])
        except si.IdentError:
            chain_ok = False
        ok = r2.returncode == 0 and chain_ok
        self.record("server_identity", "VERIFIED" if ok else "FAILED", t,
                    rc=r2.returncode, spawned_pid=(self.spawn or {}).get("pid"),
                    verify_rc=r2.returncode, spawn_chain_ok=chain_ok)
        if not ok:
            self.say("server_identity", f"FAIL: identity verify failed "
                                        f"(verify rc={r2.returncode}, "
                                        f"spawn chain ok={chain_ok}) "
                                        f"{r2.stderr.strip()[-300:]}")
        return ok

    def step_readiness(self) -> bool:
        t = time.time()
        if not self.a.readiness_check:
            self.record("readiness", "SKIPPED_BY_FLAG", t)
            self.say("readiness", "check skipped (--readiness-check 0)")
            return True
        argv = ["check", "--receipt", str(self._identity_receipt()),
                "--url", self.url, "--expect-model-path", self.a.model]
        if self.a.progress_file:
            argv += ["--progress-file", self.a.progress_file,
                     "--progress-deadline-s", str(self.a.progress_deadline_s)]
        if self.a.canary_dir:
            argv += ["--canary-dir", self.a.canary_dir,
                     "--canary-timeout-s", str(self.a.canary_timeout_s)]
        r = self._tool("server_readiness.py", *argv)
        state = None
        for line in r.stdout.splitlines()[::-1]:
            try:
                state = json.loads(line).get("state")
                break
            except ValueError:
                continue
        ok = r.returncode == 0 and state in ("READY", "BUSY")
        self.record("readiness", state or "UNKNOWN", t, rc=r.returncode,
                    canary=bool(self.a.canary_dir))
        if not ok:
            self.say("readiness", f"FAIL: server not GENERATION_READY "
                                  f"(state={state}, rc={r.returncode})")
            print(r.stdout.strip()[-1200:], flush=True)
        else:
            self.say("readiness", f"{state}")
        return ok

    def step_command(self) -> int:
        t = time.time()
        self.say("command", "executing: " + " ".join(self.a.cmd))
        self.cmd_proc = subprocess.Popen(self.a.cmd, process_group=0)
        t_sig = None
        killed = False
        while True:
            try:
                self.cmd_rc = self.cmd_proc.wait(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                pass
            if self.pending_sig is not None:
                t_sig = t_sig or time.monotonic()
                if not killed and time.monotonic() - t_sig > self.a.cmd_drain_s:
                    killed = True
                    self.say("command", f"driver ignored {self.a.cmd_drain_s:.0f}s "
                                        "drain deadline; SIGKILL to OUR driver "
                                        "process group (server untouched)")
                    try:
                        os.killpg(self.cmd_proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
        if self.cmd_rc is not None and self.cmd_rc < 0:
            self.cmd_rc = 128 - self.cmd_rc
        self.record("command", "DONE", t, rc=self.cmd_rc,
                    killed_after_drain=killed,
                    interrupted=self.pending_sig is not None)
        self.say("command", f"rc={self.cmd_rc}")
        return self.cmd_rc

    # --------------------------------------------------------------- cleanup
    def _test_barrier(self) -> None:
        """Deterministic test hook: park inside the cleanup phase (lock held)
        until <barrier> appears, so a competing job can be started at exactly
        this point. Never active unless YUE2_LIFECYCLE_TEST_BARRIER is set."""
        barrier = os.environ.get("YUE2_LIFECYCLE_TEST_BARRIER")
        if not barrier:
            return
        Path(barrier + ".entered").write_text(str(os.getpid()))
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline and not Path(barrier).exists():
            time.sleep(0.05)

    def _drain(self) -> None:
        t = time.time()
        deadline = time.monotonic() + self.a.drain_s
        idle, last = 0, None
        while time.monotonic() < deadline:
            n = si.established_count(PROC_ROOT, self.a.port)
            last = n
            idle = idle + 1 if n == 0 else 0
            if idle >= 2:
                break
            time.sleep(1.0)
        self.record("drain", "IDLE" if idle >= 2 else "TIMEOUT", t,
                    established_last=last)

    def _reap_server(self) -> None:
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_exit = self.server_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass
        elif self.server_proc is not None and self.server_exit is None:
            self.server_exit = self.server_proc.returncode

    def _set_aside_stale_receipt(self) -> None:
        """A receipt left by an EARLIER session names a process this session
        did not spawn. Nobody may later use it to signal anything, so it is
        renamed (kept as evidence) before this session launches."""
        r = self._identity_receipt()
        if not r.is_file():
            return
        stale = r.with_name(f"server-identity.stale-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
        os.replace(r, stale)
        self.say("identity_receipt", f"stale receipt of an earlier session moved aside: {stale.name}")

    def _receipt_is_ours(self) -> bool:
        """The identity receipt may only be used to signal the process WE
        spawned (pid + starttime must equal the spawn receipt)."""
        try:
            rec = si.load_receipt(self._identity_receipt())
        except si.IdentError:
            return False
        return bool(self.spawn) and int(rec["pid"]) == int(self.spawn["pid"]) \
            and str(rec["starttime"]) == str(self.spawn["starttime"])

    def _stop_server(self) -> bool:
        t = time.time()
        if self._identity_receipt().is_file() and not self._receipt_is_ours():
            self.say("stop_server", "REFUSED: identity receipt does not match the "
                                    "process we spawned; it will not be used to "
                                    "signal anything")
            self.record("stop_server_refusal", "RECEIPT_NOT_OURS", t,
                        receipt=str(self._identity_receipt()))
        if self._identity_receipt().is_file() and self._receipt_is_ours():
            r = self._tool("server_identity.py", "stop", "--receipt",
                           str(self._identity_receipt()), "--timeout",
                           str(self.a.stop_timeout_s))
            ok = r.returncode in (0, 2)
            self.record("stop_server", "STOPPED" if ok else "BLOCKED", t,
                        basis="identity_receipt", rc=r.returncode,
                        detail=(r.stdout + r.stderr).strip()[-500:])
        else:
            self.say("stop_server", "no identity receipt (boot never completed); "
                                    "stopping the process WE spawned via the "
                                    "spawn receipt")
            try:
                res = si.stop_spawned(PROC_ROOT, self.spawn, self.a.stop_timeout_s)
                ok = res["status"] == "stopped"
                self.record("stop_server", "STOPPED" if ok else "BLOCKED", t,
                            basis="spawn_receipt", detail=res)
            except si.IdentError as e:
                ok = e.code == 2  # already gone
                self.record("stop_server", "STOPPED" if ok else "FAILED", t,
                            basis="spawn_receipt", rc=e.code, detail=e.reason)
        self._reap_server()
        if not ok:
            self.say("stop_server", "FAIL: verified server survived graceful "
                                    "stop — BLOCKED (never SIGKILL)")
        return ok

    def _verify_tree(self) -> bool:
        t = time.time()
        if not self.spawn:
            self.record("tree_termination", "NOT_APPLICABLE", t)
            return True
        members = si.session_processes(
            PROC_ROOT, self.spawn["session"],
            min_starttime=int(self.spawn["starttime"]),
            exclude={os.getpid()})
        live = [m for m in members if m.get("live")]
        if live:
            # proven ours (same session, same starttime floor): SIGTERM only
            for m in live:
                try:
                    os.kill(m["pid"], signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            deadline = time.monotonic() + self.a.stop_timeout_s
            while time.monotonic() < deadline and si.live_owned(members, PROC_ROOT):
                time.sleep(1.0)
            live = si.live_owned(members, PROC_ROOT)
        zombies = [m for m in members if not m.get("live")]
        ok = not live
        if not ok:
            self.blocked.extend({"pid": m["pid"], "starttime": m["starttime"],
                                 "role": "server-session-member"}
                                for m in live)
        self.record("tree_termination", "TERMINATED" if ok else "BLOCKED", t,
                    session=self.spawn["session"], live=live, zombies=len(zombies))
        if not ok:
            self.say("tree_termination", f"FAIL: {len(live)} process(es) of our "
                                          f"server session still alive")
        return ok

    def _verify_port(self) -> bool:
        t = time.time()
        deadline = time.monotonic() + self.a.port_release_timeout_s
        while True:
            connects = port_connects(self.a.port, self.a.host)
            inos = si.listen_inodes(PROC_ROOT, self.a.port)
            owners = set()
            if inos:
                for pids in si.socket_owner(PROC_ROOT, inos).values():
                    owners |= {int(p) for p in pids}
            if not connects and not inos:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(1.0)
        ok = not connects and not inos
        self.record("port_release", "RELEASED" if ok else "OCCUPIED", t,
                    port=self.a.port, connects=connects, listener_pids=sorted(owners))
        if not ok:
            self.say("port_release", f"FAIL: port {self.a.port} still answers "
                                     f"(listener pids {sorted(owners)}); foreign "
                                     "listeners are never signalled")
        return ok

    def _verify_gpu_release(self) -> bool:
        t = time.time()
        if self.cpu_test_mode:
            self.record("gpu_release", "NOT_APPLICABLE_CPU_TEST_MODE", t)
            return True
        if not self.card or self.vram_baseline is None:
            self.record("gpu_release", "UNVERIFIABLE", t, card=self.card)
            return not self.a.require_gpu_release
        deadline = time.monotonic() + self.a.gpu_release_timeout_s
        mem = None
        while True:
            mem = read_vram_gtt(self.card)
            if mem is not None and mem[0] <= self.vram_baseline[0] \
                    + self.a.gpu_release_tolerance_mib * 2**20:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(2.0)
        ok = mem is not None and mem[0] <= self.vram_baseline[0] \
            + self.a.gpu_release_tolerance_mib * 2**20
        self.record("gpu_release", "RELEASED" if ok else "NOT_RELEASED", t,
                    card=self.card, bdf=self.bdf,
                    vram_used_bytes=mem[0] if mem else None,
                    gtt_used_bytes=mem[1] if mem else None,
                    baseline_vram_bytes=self.vram_baseline[0])
        if not ok:
            self.say("gpu_release", f"FAIL: VRAM on {self.bdf} not back to the "
                                    f"pre-boot baseline "
                                    f"({mem[0] if mem else None} vs "
                                    f"{self.vram_baseline[0]} bytes)")
        return ok

    def cleanup(self) -> str:
        """Stop + verify, in order. Returns CLEAN | BLOCKED | FAILED."""
        self._test_barrier()
        checks = []
        self._drain()
        stopped = self._stop_server()
        checks.append(("stop_server", stopped))
        tree_ok = self._verify_tree()
        checks.append(("tree_termination", tree_ok))
        port_ok = self._verify_port()
        gpu_ok = self._verify_gpu_release()
        self._reap_server()
        if not stopped or not tree_ok:
            if self.spawn and not self.blocked:
                # leader itself survived
                self.blocked.append({"pid": self.spawn["pid"],
                                     "starttime": self.spawn["starttime"],
                                     "role": "server"})
            return "BLOCKED"
        if not port_ok or not gpu_ok:
            return "FAILED"
        return "CLEAN"

    # ------------------------------------------------------------------- flow
    def flow(self) -> int:
        launched = {"who": self.who, "pid": os.getpid(),
                    "starttime": (_proc_fields(os.getpid()) or {}).get("starttime"),
                    "cmdline": " ".join(sys.argv), "url": self.url,
                    "cmd": self.a.cmd,
                    "launched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime())}
        _write_durable(self.log_dir / "lifecycle-launched.json", launched)
        self._set_aside_stale_receipt()
        boot_ok = False
        try:
            if not self.step_gpu_identity():
                self.flow_error = "gpu_identity"
                return 1
            if not self.step_gpu_idle():
                self.flow_error = "gpu_busy"
                return 1
            if not self.step_launch_server():
                self.flow_error = "launch_server"
                return 1
            boot_ok = True
            if not self.step_health():
                self.flow_error = "health"
                return 1
            if not self.step_server_identity():
                self.flow_error = "server_identity"
                return 1
            if not self.step_readiness():
                self.flow_error = "readiness"
                return 1
            return int(self.step_command() or 0)
        finally:
            if self.spawn is not None:
                try:
                    self.cleanup_state = self.cleanup()
                except Exception as e:  # noqa: BLE001 - never hide a crash
                    self.cleanup_state = "FAILED"
                    self.steps.append({"step": "cleanup", "status": "CRASHED",
                                       "reason": f"{type(e).__name__}: {e}"})
                    print(f"[lifecycle] cleanup CRASHED: {type(e).__name__}: {e}",
                          flush=True)
            _write_durable(self.log_dir / "lifecycle-receipt.json", {
                "receipt_type": "gpu_lifecycle",
                "who": self.who, "url": self.url, "cmd": self.a.cmd,
                "supervisor_pid": os.getpid(),
                "spawn": self.spawn, "server_exit": self.server_exit,
                "cmd_rc": self.cmd_rc, "flow_error": self.flow_error,
                "signal": self.pending_sig, "cleanup_state": self.cleanup_state,
                "blocked_processes": self.blocked, "steps": self.steps,
                "wall_s": round(time.time() - self.t0, 3),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            del boot_ok

    def run(self) -> int:
        lock = Path(self.a.lock) if self.a.lock else None
        try:
            with gpu_lock.gpu_ownership(self.who, wait_s=self.a.wait_s,
                                        poll_s=self.a.poll_s, lock_path=lock):
                self.say("lock", f"acquired by {self.who} (pid {os.getpid()})")
                rc = self.flow()
        except TimeoutError as e:  # gpu_lock raises the builtin TimeoutError
            print(f"[lifecycle] FAIL: GPU ownership lock unavailable: {e}",
                  flush=True)
            return 1
        except gpu_lock.GpuBlockedError as e:
            print(f"[lifecycle] FAIL: {e}", flush=True)
            return 1
        if self.cleanup_state != "CLEAN" and self.cleanup_state != "NOT_NEEDED":
            if self.cleanup_state == "BLOCKED":
                marker = gpu_lock.mark_blocked(
                    lock, self.who, self.blocked,
                    reason=(f"server survived graceful stop "
                            f"(flow_error={self.flow_error}, "
                            f"signal={self.pending_sig})"),
                    url=self.url, log_dir=str(self.log_dir))
                print(f"[lifecycle] BLOCKED: {marker['reason']}; marker "
                      f"{gpu_lock.blocked_marker_path(lock)} — subsequent GPU "
                      "work is refused until `gpu_lock.py unblock --yes`",
                      flush=True)
            else:
                print(f"[lifecycle] FATAL: lifecycle did not close cleanly "
                      f"({self.cleanup_state})", flush=True)
            if rc == 0:
                rc = 1
        if self.pending_sig is not None:
            rc = 128 + int(self.pending_sig)
        if rc:
            print(f"[lifecycle] exit rc={rc} flow_error={self.flow_error} "
                  f"cleanup={self.cleanup_state}", flush=True)
        return rc


gpu_identity_OK = ("GPU_EXECUTION_VERIFIED", "GPU_EXECUTION_UNVERIFIED",
                   "CPU_TEST_MODE_AUTHORIZED")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--who", required=True)
    ap.add_argument("--lock", default=None)
    ap.add_argument("--wait-s", type=float, default=7200.0)
    ap.add_argument("--poll-s", type=float, default=2.0)
    ap.add_argument("--workspace", default=os.environ.get("YUE2_WORKSPACE", "/data/yue2"))
    ap.add_argument("--venv", default=None)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=31000)
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--receipt-dir", default=None)
    ap.add_argument("--identity-dir", default=None)
    ap.add_argument("--serve-script", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--vae", default=None)
    ap.add_argument("--server-log", default=None)
    ap.add_argument("--boot-log", default=None)
    ap.add_argument("--gpu-id", default="0")
    ap.add_argument("--shell", default="bash")
    ap.add_argument("--expect-arch", default=os.environ.get("YUE2_EXPECT_GPU_ARCH", "gfx1100"))
    ap.add_argument("--expect-bdf", default=os.environ.get("YUE2_EXPECT_GPU_BDF"))
    ap.add_argument("--probe-budget-s", type=float, default=60.0)
    ap.add_argument("--max-idle-vram-mib", type=float, default=2048.0)
    ap.add_argument("--health-timeout-s", type=float, default=1800.0)
    ap.add_argument("--health-poll-s", type=float, default=5.0)
    ap.add_argument("--readiness-check", default="1", choices=("0", "1"))
    ap.add_argument("--progress-file", default=None)
    ap.add_argument("--progress-deadline-s", type=float, default=3600.0)
    ap.add_argument("--canary-dir", default=None)
    ap.add_argument("--canary-timeout-s", type=float, default=600.0)
    ap.add_argument("--cmd-drain-s", type=float, default=1800.0)
    ap.add_argument("--drain-s", type=float, default=600.0)
    ap.add_argument("--stop-timeout-s", type=float, default=180.0)
    ap.add_argument("--port-release-timeout-s", type=float, default=60.0)
    ap.add_argument("--gpu-release-timeout-s", type=float, default=180.0)
    ap.add_argument("--gpu-release-tolerance-mib", type=float, default=512.0)
    ap.add_argument("--require-gpu-release", action="store_true", default=True)
    ap.add_argument("--allow-unverifiable-gpu-release", dest="require_gpu_release",
                    action="store_false",
                    help="explicit opt-out when VRAM sysfs is unreadable")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("no command given after --")
    a.cmd = cmd
    ws = Path(a.workspace)
    a.venv = a.venv or str(ws / "environments" / "yue2-gfx1100")
    a.receipt_dir = a.receipt_dir or str(Path(a.log_dir) / "server_identity")
    a.identity_dir = a.identity_dir or str(Path(a.log_dir) / "gpu_identity")
    a.vae = a.vae or str(ws / "models" / "YuE2-Vae-legacy")
    a.server_log = a.server_log or str(Path(a.log_dir) / "server_yue2_gfx1100.log")
    a.boot_log = a.boot_log or str(Path(a.log_dir) / "server_boot.log")
    Path(a.log_dir).mkdir(parents=True, exist_ok=True)
    sup = Lifecycle(a)
    sup.install_signal_handlers()
    return sup.run()


if __name__ == "__main__":
    raise SystemExit(main())
