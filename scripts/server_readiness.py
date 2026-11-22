#!/usr/bin/env python3
"""server_readiness.py — GENERATION_READY is not HTTP_HEALTH (RC4.1 M2).

The RC4 fault-injection evidence showed a dead scheduler worker is invisible
to ``/health`` (stays 200 while in-flight requests hang). This tool drives a
fact-based FSM on top of the existing server-identity receipts:

  STARTING → READY → BUSY → DEGRADED → WORKER_DEAD → STOPPING → STOPPED
                                                              ↘ UNKNOWN

Facts collected per check (all through /proc + HTTP, no server changes):
  1. identity receipt verify (PID liveness, starttime, argv sha, uid)
  2. scheduler worker: descendant processes of the verified server PID whose
     comm/argv match the sglang diffusion scheduler signature
  3. HTTP /health + /v1/models (model advertisement)
  4. ESTABLISHED connections on the service port (BUSY hint)
  5. optional progress file mtime vs configured deadline (hang guard)

Level-2 canary (``canary``) is OPT-IN only: a real bounded short-budget
generation request (ode_steps=4, semantic_max_tokens=300) with hard client
timeout; never run automatically by ``check``/``watch``.

Exit codes (check/watch/canary): 0 READY/BUSY · 3 worker-dead · 4 not-ready/
refused · 5 degraded · 6 progress-timeout · 2 internal error.

Usage:
  server_readiness.py check --receipt R [--url http://127.0.0.1:31000] \
      [--expect-model YuE2] [--progress-file F --progress-deadline-s 3600]
  server_readiness.py watch --receipt R --until-ready-timeout-s 900 [...]
  server_readiness.py canary --url http://127.0.0.1:31000 --out-dir D \
      [--timeout 300]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server_identity import (IdentError, established_count, list_pids,  # noqa: E402
                             load_receipt, read_cmdline, read_starttime,
                             read_state, verify_process)

PROC_ROOT_DEFAULT = "/proc"
SCHEDULER_SIG = ("sgl_diffusion", "scheduler")

# safe default: a full official song takes P50 275 s / P95 430 s on this rig;
# 3600 s covers the observed max (1198.9 s) with margin. Configurable.
DEFAULT_PROGRESS_DEADLINE_S = float(os.environ.get(
    "YUE2_READINESS_PROGRESS_DEADLINE_S", "3600"))


def http_get(url: str, timeout: float = 5.0):
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(65536).decode(errors="replace")
            return r.status, time.monotonic() - t0, body
    except urllib.error.HTTPError as e:
        return e.code, time.monotonic() - t0, ""
    except Exception as e:
        return None, time.monotonic() - t0, f"{type(e).__name__}: {e}"


def _ppid_of(proc_root, pid: int) -> int | None:
    try:
        data = (Path(proc_root) / str(pid) / "stat").read_text()
        return int(data[data.rindex(")") + 1:].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _comm_of(proc_root, pid: int) -> str:
    try:
        return (Path(proc_root) / str(pid) / "comm").read_text().strip()
    except OSError:
        return ""


def descendants(proc_root, pid: int, max_depth: int = 3) -> dict[int, int]:
    """Map descendant_pid -> depth (1 = direct child) via /proc ppid links."""
    table = {}
    for p in list_pids(proc_root):
        pp = _ppid_of(proc_root, p)
        if pp is not None:
            table[p] = pp
    out: dict[int, int] = {}
    frontier = {pid}
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        nxt = {p for p, pp in table.items() if pp in frontier and p not in out}
        for p in nxt:
            out[p] = depth
        frontier = nxt
    return out


def find_scheduler_workers(proc_root, server_pid: int) -> list[dict]:
    """Descendant processes matching the sglang diffusion scheduler signature."""
    found = []
    for dpid, depth in descendants(proc_root, server_pid).items():
        try:
            argv = read_cmdline(proc_root, dpid)
        except IdentError:
            continue
        comm = _comm_of(proc_root, dpid)
        blob = " ".join(argv) + " " + comm
        if any(s in blob for s in SCHEDULER_SIG):
            found.append({
                "pid": dpid, "depth": depth, "comm": comm,
                "state": read_state(proc_root, dpid),
                "starttime": read_starttime(proc_root, dpid),
                "argv_head": " ".join(argv)[:160],
            })
    return found


def check(receipt_path: str, url: str, proc_root: str = PROC_ROOT_DEFAULT,
          expect_model: str | None = None, progress_file: str | None = None,
          progress_deadline_s: float = DEFAULT_PROGRESS_DEADLINE_S,
          skip_http: bool = False) -> tuple[str, dict]:
    """One readiness evaluation. Returns (state, facts). READY only on facts."""
    facts: dict = {"checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                   time.gmtime()),
                   "url": url, "receipt": receipt_path}
    try:
        r = load_receipt(receipt_path)
    except IdentError as e:
        facts["identity_error"] = e.reason
        # receipt unusable: try port facts for classification, fail closed
        st, _, _ = http_get(url + "/health") if not skip_http else (None, 0, "")
        facts["http_health"] = st
        facts["reason"] = "identity receipt unusable (fail-closed)"
        return ("UNKNOWN", facts) if st == 200 else ("STOPPED", facts)

    port = r["port"]
    facts["server_pid"] = r["pid"]
    ident_ok = True
    try:
        verify_process(proc_root, r["pid"], expect_argv_sha=r["argv_sha256"],
                       expect_uid=r.get("expect_uid", r["uid"]),
                       expect_starttime=r["starttime"], expect_port=None)
        facts["identity"] = "verified"
    except IdentError as e:
        ident_ok = False
        facts["identity"] = f"FAILED: {e.reason}"

    st, dt, body = http_get(url + "/health") if not skip_http else (None, 0, "")
    facts["http_health"] = st
    facts["http_health_latency_s"] = round(dt, 3)

    workers = find_scheduler_workers(proc_root, r["pid"]) if ident_ok else []
    live_workers = [w for w in workers if w["state"] != "Z"]
    facts["scheduler_workers"] = workers
    facts["scheduler_alive"] = bool(live_workers)

    conns = established_count(proc_root, port)
    facts["established_connections"] = conns

    if expect_model and st == 200:
        mst, _, mbody = http_get(url + "/v1/models", timeout=10.0)
        facts["models_advertised_ok"] = bool(
            mst == 200 and expect_model.lower() in mbody.lower())

    progress_stale = False
    if progress_file:
        pf = Path(progress_file)
        try:
            age = time.time() - pf.stat().st_mtime
            facts["progress_file_age_s"] = round(age, 1)
            progress_stale = age > progress_deadline_s
        except OSError:
            facts["progress_file_age_s"] = None

    # ---- fact-driven FSM ----------------------------------------------------
    if not ident_ok:
        # process gone or replaced: STOPPED if port is free, else UNKNOWN
        return ("STOPPED", facts) if conns == 0 and st != 200 \
            else ("UNKNOWN", facts)
    # identity verified from here
    if not facts["scheduler_alive"]:
        # THE RC4 blind spot: HTTP may still be 200 — never READY here
        return ("WORKER_DEAD", facts)
    if st != 200:
        return ("DEGRADED", facts)
    if progress_stale:
        return ("BUSY", facts)  # still working; caller escalates via rc 6
    return ("BUSY", facts) if conns > 0 else ("READY", facts)


EXIT_BY_STATE = {"READY": 0, "BUSY": 0, "WORKER_DEAD": 3, "DEGRADED": 5,
                 "STOPPED": 4, "UNKNOWN": 4, "STARTING": 4, "STOPPING": 4}

CANARY_PAYLOAD = {
    "style": "[Tags]\nsoft pop\n",
    "lyrics": "[Lyrics]\nA tiny readiness canary phrase.\n",
    "seed": 990001,
    "cot": "full",
    "ode_steps": 4,           # short budget by design — NOT official params
    "semantic_max_tokens": 300,
    "abc_max_tokens": 512,
}


def canary(url: str, out_dir: Path, timeout: float = 300.0,
           payload: dict | None = None) -> tuple[bool, dict]:
    """Level-2 readiness: one real bounded short-budget generation.

    Opt-in only; caller must hold the GPU lock and avoid racing an active
    full-song generation (check readiness==READY first)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pl = dict(payload or CANARY_PAYLOAD)
    pl.setdefault("output_path", str(out_dir))
    pl.setdefault("output_file_name", "readiness_canary.wav")
    pl.setdefault("id", "readiness_canary")
    req = urllib.request.Request(
        url + "/v1/audio/generations", data=json.dumps(pl).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        audio = body.get("audio") or ""
        wav = Path(audio) if audio else None
        ok = bool(wav and wav.is_file() and wav.stat().st_size > 1024)
        receipt = {"canary": "generation", "http_status": resp.status,
                   "wall_s": round(time.monotonic() - t0, 1),
                   "audio_path": str(wav) if wav else None,
                   "audio_bytes": wav.stat().st_size if wav and wav.is_file()
                   else 0,
                   "payload_budgets": {k: pl[k] for k in
                                       ("ode_steps", "semantic_max_tokens",
                                        "abc_max_tokens")}}
        receipt["ok"] = ok
        if not ok:
            receipt["reason"] = "response carried no decodable audio file"
        return ok, receipt
    except Exception as e:
        return False, {"canary": "generation", "ok": False,
                       "wall_s": round(time.monotonic() - t0, 1),
                       "reason": f"{type(e).__name__}: {e}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GENERATION_READY FSM checks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--receipt", required=True)
    common.add_argument("--url", default=os.environ.get(
        "YUE2_SERVER_URL", "http://127.0.0.1:31000"))
    common.add_argument("--expect-model", default="YuE2")
    common.add_argument("--proc-root", default=PROC_ROOT_DEFAULT)
    common.add_argument("--progress-file", default=None)
    common.add_argument("--progress-deadline-s", type=float,
                        default=DEFAULT_PROGRESS_DEADLINE_S)
    c = sub.add_parser("check", parents=[common])
    w = sub.add_parser("watch", parents=[common])
    w.add_argument("--until-ready-timeout-s", type=float, default=1800.0)
    w.add_argument("--poll-s", type=float, default=5.0)
    k = sub.add_parser("canary")
    k.add_argument("--url", default=os.environ.get(
        "YUE2_SERVER_URL", "http://127.0.0.1:31000"))
    k.add_argument("--out-dir", type=Path, required=True)
    k.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args(argv)

    if a.cmd == "canary":
        ok, receipt = canary(a.url, a.out_dir, timeout=a.timeout)
        print(json.dumps(receipt, indent=1))
        return 0 if ok else 5

    def one():
        state, facts = check(a.receipt, a.url, proc_root=a.proc_root,
                             expect_model=a.expect_model,
                             progress_file=a.progress_file,
                             progress_deadline_s=a.progress_deadline_s)
        line = {"state": state,
                "scheduler_alive": facts.get("scheduler_alive"),
                "http_health": facts.get("http_health"),
                "identity": facts.get("identity"),
                "established_connections": facts.get(
                    "established_connections")}
        print(json.dumps(line), flush=True)
        return state, facts

    if a.cmd == "check":
        state, facts = one()
        rc = EXIT_BY_STATE.get(state, 4)
        if (state == "BUSY" and a.progress_file
                and facts.get("progress_file_age_s") is not None
                and facts["progress_file_age_s"] > a.progress_deadline_s):
            rc = 6  # GPU_PROGRESS_TIMEOUT escalation
        return rc
    # watch
    deadline = time.monotonic() + a.until_ready_timeout_s
    last = "UNKNOWN"
    while time.monotonic() < deadline:
        last, _ = one()
        if last in ("READY", "WORKER_DEAD", "STOPPED"):
            return EXIT_BY_STATE.get(last, 4)
        time.sleep(a.poll_s)
    print(json.dumps({"state": last, "reason": "watch deadline exceeded"}))
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
