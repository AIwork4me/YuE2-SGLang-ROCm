#!/usr/bin/env python3
"""server_identity.py - run-owned generation-server identity receipt + safe stop.

Replaces the unsafe `pkill -f "sglang serve"` pattern in the WSB scoring
pipeline. A server may be signaled ONLY after every identity field has been
verified against /proc: PID liveness, non-zombie state, UID, process start
time, exact argv, and unique ownership of the run's listening endpoint.

Subcommands
-----------
capture   discover/verify the run-owned server and write an identity receipt
verify    re-verify an existing receipt against the live process table
stop      verify -> SIGINT -> (recheck) -> SIGTERM -> BLOCKED (never SIGKILL)

Design for testability: PROC_ROOT (default /proc) may point at a mocked
process tree; --dry-run performs full verification but sends no signal.

Exit codes (stop): 0 stopped | 2 verify-failed | 3 ambiguous | 4 refused |
                   5 blocked-alive | 6 requests-in-flight
Exit codes (capture/verify): 0 ok | 2 verify-failed | 3 ambiguous | 4 refused
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

PROC_ROOT_DEFAULT = "/proc"


def eprint(*a):
    print(*a, file=sys.stderr)


class IdentError(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _proc(root, pid):
    return Path(root) / str(pid)


def read_cmdline(root, pid):
    p = _proc(root, pid) / "cmdline"
    if not p.is_file():
        raise IdentError(4, f"pid {pid}: no cmdline (process gone)")
    raw = p.read_bytes()
    return [t.decode("utf-8", "replace") for t in raw.split(b"\0") if t != b""]


def read_starttime(root, pid):
    p = _proc(root, pid) / "stat"
    if not p.is_file():
        raise IdentError(4, f"pid {pid}: no stat (process gone)")
    # field 22 (1-based) = starttime; comm may contain spaces -> parse after ')'
    data = p.read_text()
    rest = data[data.rindex(")") + 1:].split()
    return rest[19]  # state=rest[0] is field 3; field22 - 3 + 1 -> index 19


def read_state(root, pid):
    p = _proc(root, pid) / "stat"
    if not p.is_file():
        raise IdentError(4, f"pid {pid}: no stat (process gone)")
    data = p.read_text()
    return data[data.rindex(")") + 1:].split()[0]


def read_uid(root, pid):
    p = _proc(root, pid) / "status"
    if not p.is_file():
        raise IdentError(4, f"pid {pid}: no status (process gone)")
    for line in p.read_text().splitlines():
        if line.startswith("Uid:"):
            fields = line.split()[1:5]
            return fields  # real, effective, saved, fs
    raise IdentError(4, f"pid {pid}: Uid line missing")


def list_pids(root):
    root = Path(root)
    return [int(x.name) for x in root.iterdir()
            if x.name.isdigit() and x.is_dir()]


def listen_inodes(root, port):
    """Return set of socket inodes LISTENING on port (any local address)."""
    inodes = set()
    port_hex = format(int(port), "04X")
    for fn in ("net/tcp", "net/tcp6"):
        f = Path(root) / fn
        if not f.is_file():
            continue
        for line in f.read_text().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            if parts[1].endswith(":" + port_hex) and parts[3] == "0A":
                inodes.add(parts[9])
    return inodes


def established_count(root, port):
    """Count ESTABLISHED sockets on port (driver/server traffic)."""
    n = 0
    port_hex = format(int(port), "04X")
    for fn in ("net/tcp", "net/tcp6"):
        f = Path(root) / fn
        if not f.is_file():
            continue
        for line in f.read_text().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue
            if (parts[1].endswith(":" + port_hex)
                    or parts[2].endswith(":" + port_hex)) and parts[3] == "01":
                n += 1
    return n


def socket_owner(root, inodes):
    """Map socket inodes -> set of pids holding them via /proc/<pid>/fd."""
    owners = {}
    import glob
    for fd in glob.glob(str(Path(root) / "[0-9]*" / "fd" / "*")):
        try:
            tgt = os.readlink(fd)
        except OSError:
            continue
        if tgt.startswith("socket:["):
            ino = tgt[8:-1]
            if ino in inodes:
                owners.setdefault(ino, set()).add(Path(fd).parts[-3])
    return owners


def argv_sha256(argv):
    return hashlib.sha256("\0".join(argv).encode()).hexdigest()


TEST_HOOKS_PROC_ROOTS = set()  # populated by main() from --proc-root


def hooks_allowed():
    """SI_* test hooks are honored ONLY against mocked proc trees, never
    against the live /proc (prevents a leaked env var from disabling real
    signals in production)."""
    return PROC_ROOT_DEFAULT not in TEST_HOOKS_PROC_ROOTS or \
        os.environ.get("SI_ALLOW_REAL_PROC_HOOKS") == "1-I-AM-A-TEST"


def send_signal(pid, sig):
    """Send a signal. Test override: SI_SIGNAL_CMD='{pid} {signum}' template
    executed via shell instead of a real kill (mocked proc trees only)."""
    import subprocess
    cmd = os.environ.get("SI_SIGNAL_CMD") if hooks_allowed() else None
    if cmd:
        subprocess.run(["bash", "-c", cmd.format(pid=int(pid), signum=int(sig))],
                       check=False)
        return
    os.kill(int(pid), sig)


def verify_process(proc_root, pid, *, expect_argv_sha, expect_uid,
                   expect_starttime, expect_port, allow_zombie=False,
                   require_socket=True):
    """Full identity verification of one PID against expected fields.

    Raises IdentError on any mismatch; returns dict of live facts."""
    pid = int(pid)
    if not _proc(proc_root, pid).is_dir():
        raise IdentError(2, f"pid {pid}: /proc entry gone")
    state = read_state(proc_root, pid)
    if state == "Z" and not allow_zombie:
        raise IdentError(2, f"pid {pid}: zombie (state Z) - not a live server")
    uids = read_uid(proc_root, pid)
    if expect_uid is not None and int(uids[0]) != int(expect_uid):
        raise IdentError(2, f"pid {pid}: uid {uids[0]} != expected {expect_uid}")
    st = read_starttime(proc_root, pid)
    if expect_starttime is not None and st != str(expect_starttime):
        raise IdentError(2, f"pid {pid}: starttime {st} != expected "
                            f"{expect_starttime} (PID reused?)")
    argv = read_cmdline(proc_root, pid)
    ash = argv_sha256(argv)
    if expect_argv_sha is not None and ash != expect_argv_sha:
        raise IdentError(2, f"pid {pid}: argv sha256 {ash[:12]}... != expected "
                            f"{expect_argv_sha[:12]}... (PID reused?)")
    facts = {"pid": pid, "state": state, "uid": uids[0], "starttime": st,
             "argv": argv, "argv_sha256": ash}
    if require_socket and expect_port is not None:
        inos = listen_inodes(proc_root, expect_port)
        owners = socket_owner(proc_root, inos)
        holder_pids = set()
        for ino, pids in owners.items():
            holder_pids |= {int(p) for p in pids}
        if holder_pids != {pid}:
            raise IdentError(3, f"port {expect_port} listen socket owners "
                                f"{sorted(holder_pids)} != {{{pid}}} "
                                f"(ambiguous or not owned)")
        facts["listen_inodes"] = sorted(inos)
    return facts


def discover(proc_root, model_path, host, port):
    """Find pids whose cmdline matches this run's server exactly.

    Match rule: argv contains 'serve', the exact --model-path value and the
    exact --port value; AND the pid uniquely owns the listen socket."""
    cands = []
    for pid in list_pids(proc_root):
        try:
            argv = read_cmdline(proc_root, pid)
        except IdentError:
            continue
        if len(argv) < 3:
            continue
        if "serve" not in argv:
            continue
        if model_path not in argv:
            continue
        if str(port) not in argv:
            continue
        cands.append(pid)
    if not cands:
        raise IdentError(4, f"no process matches model={model_path} port={port}")
    return cands


def cmd_capture(a):
    proc = a.proc_root
    cands = discover(proc, a.model, a.host, a.port)
    facts = None
    if a.pid:
        if int(a.pid) not in cands:
            raise IdentError(4, f"pid {a.pid} does not match this run's server "
                                f"(candidates: {cands})")
        facts = verify_process(proc, int(a.pid), expect_argv_sha=None,
                               expect_uid=os.getuid() if a.expect_uid is None else a.expect_uid,
                               expect_starttime=None, expect_port=a.port)
    else:
        oks, fails = [], []
        for pid in cands:
            try:
                f = verify_process(proc, pid, expect_argv_sha=None,
                                   expect_uid=os.getuid() if a.expect_uid is None else a.expect_uid,
                                   expect_starttime=None, expect_port=a.port)
                oks.append(f)
            except IdentError as e:
                fails.append(f"pid {pid}: {e.reason}")
        if len(oks) == 0:
            raise IdentError(4, "no candidate passed verification: " + "; ".join(fails))
        if len(oks) > 1:
            raise IdentError(3, f"ambiguous: {len(oks)} matching servers "
                                f"({[f['pid'] for f in oks]}) - refusing")
        facts = oks[0]
    run_cfg = {}
    cfg = Path(a.run_state).parent / "run_config.json"
    if cfg.is_file():
        try:
            run_cfg = json.loads(cfg.read_text())
        except Exception:
            run_cfg = {}
    receipt = {
        "receipt_type": "generation_server_identity",
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": facts["pid"],
        "uid": facts["uid"],
        "starttime": facts["starttime"],
        "state_at_capture": facts["state"],
        "argv": facts["argv"],
        "argv_sha256": facts["argv_sha256"],
        "model_path": a.model,
        "host": a.host,
        "port": a.port,
        "listen_inodes": facts.get("listen_inodes", []),
        "run_id": run_cfg.get("run_id"),
        "expect_uid": os.getuid() if a.expect_uid is None else a.expect_uid,
    }
    out = Path(a.run_state) / "server-identity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps({"status": "captured", "receipt": str(out),
                      "pid": receipt["pid"], "run_id": receipt["run_id"]}))
    return 0


def load_receipt(path):
    p = Path(path)
    if not p.is_file():
        raise IdentError(4, f"receipt missing: {p}")
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise IdentError(4, f"receipt unreadable: {e}")


def cmd_verify(a):
    r = load_receipt(a.receipt)
    facts = verify_process(a.proc_root, r["pid"],
                           expect_argv_sha=r["argv_sha256"],
                           expect_uid=r.get("expect_uid", r["uid"]),
                           expect_starttime=r["starttime"],
                           expect_port=None if r.get("skip_socket_check") else r["port"])
    print(json.dumps({"status": "verified", "pid": facts["pid"],
                      "state": facts["state"],
                      "starttime": facts["starttime"]}))
    return 0


def wait_gone(proc_root, pid, timeout, poll=None):
    if poll is None:
        poll = float(os.environ.get("SI_WAIT_POLL", "2.0")) if hooks_allowed() else 2.0
    if hooks_allowed():
        timeout = float(os.environ.get("SI_WAIT_TIMEOUT", str(timeout)))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _proc(proc_root, pid).is_dir():
            return "gone"
        try:
            if read_state(proc_root, pid) == "Z":
                return "zombie-reaped-pending"
        except IdentError:
            return "gone"
        time.sleep(poll)
    return "alive"


def cmd_stop(a):
    r = load_receipt(a.receipt)
    if a.require_idle:
        n = established_count(a.proc_root, r["port"])
        if n > 0 and not a.dry_run:
            raise IdentError(6, f"{n} ESTABLISHED connection(s) on port "
                                f"{r['port']} - generation still in flight")

    # identity re-check BEFORE any signal
    facts = verify_process(a.proc_root, r["pid"],
                           expect_argv_sha=r["argv_sha256"],
                           expect_uid=r.get("expect_uid", r["uid"]),
                           expect_starttime=r["starttime"],
                           expect_port=None if r.get("skip_socket_check") else r["port"])

    if a.dry_run:
        print(json.dumps({"status": "dry-run", "would_signal": r["pid"],
                          "signals": ["SIGINT", "SIGTERM (after recheck)"],
                          "verified": True}))
        return 0

    sig_order = [signal.SIGINT, signal.SIGTERM]
    for i, sig in enumerate(sig_order):
        # re-verify immediately before EACH signal (catches replacement)
        verify_process(a.proc_root, r["pid"], expect_argv_sha=r["argv_sha256"],
                       expect_uid=r.get("expect_uid", r["uid"]),
                       expect_starttime=r["starttime"],
                       expect_port=None if r.get("skip_socket_check") else r["port"])
        try:
            send_signal(r["pid"], sig)
        except ProcessLookupError:
            print(json.dumps({"status": "stopped", "pid": r["pid"],
                              "phase": f"pre-signal SIG{i+1}"}))
            return 0
        except PermissionError as e:
            raise IdentError(5, f"no permission to signal pid {r['pid']}: {e}")
        res = wait_gone(a.proc_root, r["pid"], a.timeout)
        if res != "alive":
            print(json.dumps({"status": "stopped", "pid": r["pid"],
                              "phase": f"after {sig.name}", "result": res}))
            return 0
        eprint(f"[server_identity] pid {r['pid']} still alive after "
               f"{sig.name} + {a.timeout}s")
    raise IdentError(5, f"BLOCKED: verified server pid {r['pid']} survived "
                        f"SIGINT and SIGTERM; refusing to SIGKILL. GPU may "
                        f"still be allocated - do not start scoring. Inspect "
                        f"manually: ps -p {r['pid']} -o stat,wchan,args; "
                        f"rocm-smi; then decide.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture")
    c.add_argument("--run-state", required=True,
                   help="run-owned sidecar dir for the receipt")
    c.add_argument("--model", required=True)
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, required=True)
    c.add_argument("--pid", type=int, default=None,
                   help="verify this specific pid instead of discovering")
    c.add_argument("--expect-uid", type=int, default=None,
                   help="default: current euid")
    c.add_argument("--proc-root", default=PROC_ROOT_DEFAULT)
    c.set_defaults(fn=cmd_capture)

    v = sub.add_parser("verify")
    v.add_argument("--receipt", required=True)
    v.add_argument("--proc-root", default=PROC_ROOT_DEFAULT)
    v.set_defaults(fn=cmd_verify)

    s = sub.add_parser("stop")
    s.add_argument("--receipt", required=True)
    s.add_argument("--timeout", type=float, default=120.0)
    s.add_argument("--require-idle", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--proc-root", default=PROC_ROOT_DEFAULT)
    s.set_defaults(fn=cmd_stop)

    a = ap.parse_args()
    TEST_HOOKS_PROC_ROOTS.add(a.proc_root)
    try:
        sys.exit(a.fn(a))
    except IdentError as e:
        eprint(f"[server_identity] REFUSED/FAILED (code {e.code}): {e.reason}")
        sys.exit(e.code)


if __name__ == "__main__":
    main()
