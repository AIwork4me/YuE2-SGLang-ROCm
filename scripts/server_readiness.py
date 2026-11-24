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

RC5 M1.3 — SEMANTIC CORRECTNESS OF "READY" (RC4.1 static review P1):
  * ``models_advertised_ok`` was recorded but never used: an HTTP-200 server
    advertising ANOTHER model was reported READY. It now gates the verdict.
  * the verified PID had no socket requirement: an HTTP-200 answer from a
    process other than the receipt's server (wrong process/port) was READY.
    The URL port must equal the receipt port and its LISTEN socket must be
    owned by the verified PID (UNKNOWN when ownership cannot be established).
  * a configured progress file that is MISSING was silently ignored. A
    missing progress file is now UNKNOWN (progress cannot be attested); a
    stale one escalates BUSY to rc 6 as before.
  * the canary accepted any file > 1024 bytes. It now DECODES the audio
    (48 kHz, stereo, finite, >= 1 s) and requires it to be freshly written.

Exit codes (check/watch/canary): 0 READY/BUSY · 3 worker-dead · 4 not-ready/
refused/UNKNOWN · 5 degraded/canary failure · 6 progress-timeout · 2 internal
error.

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
from server_identity import (IdentError, established_count,  # noqa: E402
                              list_pids, listen_inodes, load_receipt,
                              read_cmdline, read_starttime, read_state,
                              socket_owner, verify_process)

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


def url_port(url: str, default: int | None = None) -> int | None:
    from urllib.parse import urlsplit
    u = urlsplit(url)
    if u.port:
        return int(u.port)
    return default


def port_owner_state(proc_root, pid: int, port: int) -> tuple[str, set]:
    """OWNED: the verified pid alone holds every LISTEN socket of the port.
    FOREIGN/AMBIGUOUS: other pids hold it. UNVERIFIABLE: no socket table."""
    try:
        inos = listen_inodes(proc_root, port)
    except (OSError, ValueError) as e:
        return "UNVERIFIABLE", set()
    if not inos:
        return "NO_LISTENER", set()
    owners = set()
    for pids in socket_owner(proc_root, inos).values():
        owners |= {int(x) for x in pids}
    if owners == {int(pid)}:
        return "OWNED", owners
    if not owners:
        return "UNVERIFIABLE", owners
    return "FOREIGN", owners


def _decode_audio(path: Path) -> dict:
    """Decode the canary audio for real. Prefers soundfile; falls back to a
    minimal RIFF/WAVE reader (PCM 16/24/32 and IEEE float32) so the check
    also runs where soundfile is not installed."""
    import struct
    size = path.stat().st_size
    try:
        import numpy as np
        import soundfile as sf
        data, sr = sf.read(str(path), always_2d=True, dtype="float64")
        frames, ch = data.shape
        return {"decoder": "soundfile", "samplerate": int(sr),
                "channels": int(ch), "frames": int(frames),
                "finite": bool(np.isfinite(data).all()),
                "peak": float(np.abs(data).max()) if frames else 0.0,
                "rms": float(np.sqrt((data ** 2).mean())) if frames else 0.0,
                "bytes": size}
    except ImportError:
        pass
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        (csz,) = struct.unpack_from("<I", raw, pos + 4)
        body = raw[pos + 8:pos + 8 + csz]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack_from("<HHIIHH", body, 0)
            fmt = {"format_tag": tag, "channels": ch, "samplerate": sr,
                   "bits": bits}
        elif cid == b"data":
            pcm = body
        pos += 8 + csz + (csz & 1)
    if not fmt or pcm is None:
        raise ValueError("WAVE lacks fmt/data chunk")
    tag, ch, sr, bits = (fmt["format_tag"], fmt["channels"],
                         fmt["samplerate"], fmt["bits"])
    width = bits // 8
    if len(pcm) % (width * ch):
        raise ValueError("data chunk size is not a whole number of frames")
    n = len(pcm) // (width * ch)
    samples = struct.unpack(f"<{n * ch}f", pcm) if (tag == 3 and bits == 32) \
        else struct.unpack(f"<{n * ch}h", pcm) if (tag == 1 and bits == 16) \
        else None
    if samples is None:
        raise ValueError(f"unsupported WAVE encoding tag={tag} bits={bits}")
    vals = [x / 32768.0 if (tag == 1 and bits == 16) else float(x)
            for x in samples]
    finite = all(v == v and abs(v) != float("inf") for v in vals)
    peak = max((abs(v) for v in vals), default=0.0)
    rms = (sum(v * v for v in vals) / len(vals)) ** 0.5 if vals else 0.0
    return {"decoder": "riff-fallback", "samplerate": sr, "channels": ch,
            "frames": n, "finite": finite, "peak": peak, "rms": rms,
            "bytes": size}


def check(receipt_path: str, url: str, proc_root: str = PROC_ROOT_DEFAULT,
          expect_model: str | None = "YuE2", progress_file: str | None = None,
          progress_deadline_s: float = DEFAULT_PROGRESS_DEADLINE_S,
          skip_http: bool = False,
          expect_model_path: str | None = None) -> tuple[str, dict]:
    """One readiness evaluation. Returns (state, facts). READY only on facts:
    identity verified AND port owned by that pid AND worker alive AND HTTP
    200 AND the expected model advertised AND progress attested.
    ``expect_model`` defaults to "YuE2" (fail-closed); pass "" to disable the
    model gate explicitly."""
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
    # a zombie is dead; a job-control STOPPED worker (state T/t) is alive as a
    # process but can never serve a request — it is not a live worker either
    live_workers = [w for w in workers if w["state"] not in ("Z", "T", "t")]
    facts["scheduler_workers"] = workers
    facts["scheduler_alive"] = bool(live_workers)

    conns = established_count(proc_root, port)
    facts["established_connections"] = conns

    # ---- model advertisement (RC5 M1.3: part of the verdict) ---------------
    facts["models_advertised_ok"] = None
    if ident_ok and st == 200 and expect_model:
        want = (expect_model_path or "").lower()
        mst, _, mbody = http_get(url + "/v1/models", timeout=10.0)
        ok = False
        if mst == 200:
            try:
                obj = json.loads(mbody)
                ids = [str(d.get("id", "")) for d in obj.get("data", [])]
            except ValueError:
                ids = []
            facts["models_advertised_ids"] = ids
            low = [i.lower() for i in ids]
            name_ok = expect_model.lower() in " ".join(low)
            path_ok = bool(want) and any(i == want or i.endswith("/" + want)
                                         or want.endswith("/" + i) for i in low)
            # an EXPLICIT expected model path is binding: the loose default
            # name must not vouch for a different model that merely contains
            # the family name (found by the real-GPU control RG-03)
            ok = path_ok if want else name_ok
        if not ok:
            # OpenAI discovery unavailable: the server's own description must
            # name the model path / pipeline class we expect
            pst, _, pbody = http_get(url + "/models", timeout=10.0)
            if pst == 200:
                try:
                    obj = json.loads(pbody)
                except ValueError:
                    obj = {}
                mp = str(obj.get("model_path", ""))
                pc = str(obj.get("pipeline_class", ""))
                facts["models_endpoint_model_path"] = mp
                facts["models_endpoint_pipeline_class"] = pc
                if want:
                    ok = mp.lower() == want
                else:
                    ok = expect_model.lower() in mp.lower() or \
                        expect_model.lower() in pc.lower()
        facts["models_advertised_ok"] = ok

    # ---- port ownership (RC5 M1.3: the answer must come from OUR server) --
    up = url_port(url)
    port_state, port_owners = "UNVERIFIABLE", set()
    if ident_ok:
        if up is not None and int(up) != int(port):
            port_state = "PORT_MISMATCH"
        else:
            port_state, port_owners = port_owner_state(proc_root, r["pid"],
                                                       int(port))
    facts["url_port"] = up
    facts["port_owner_state"] = port_state
    facts["port_owner_pids"] = sorted(port_owners)

    # ---- progress attestation (RC5 M1.3: missing is not "fine") -----------
    progress_stale = False
    if progress_file:
        pf = Path(progress_file)
        try:
            age = time.time() - pf.stat().st_mtime
            facts["progress_file_age_s"] = round(age, 1)
            progress_stale = age > progress_deadline_s
        except OSError:
            facts["progress_file_age_s"] = None
            facts["progress_file_missing"] = True

    # ---- fact-driven FSM ----------------------------------------------------
    if not ident_ok:
        # process gone or replaced: STOPPED if port is free, else UNKNOWN
        return ("STOPPED", facts) if conns == 0 and st != 200 \
            else ("UNKNOWN", facts)
    if port_state in ("FOREIGN", "PORT_MISMATCH"):
        facts["reason"] = (f"HTTP answer on {url} is not owned by the receipt "
                           f"server (port owner state {port_state}, pids "
                           f"{sorted(port_owners)})")
        return ("UNKNOWN", facts)
    if port_state == "NO_LISTENER" and st == 200:
        facts["reason"] = "HTTP 200 but no LISTEN socket on the receipt port"
        return ("UNKNOWN", facts)
    # identity verified from here
    if not facts["scheduler_alive"]:
        # THE RC4 blind spot: HTTP may still be 200 — never READY here
        return ("WORKER_DEAD", facts)
    if st != 200:
        return ("DEGRADED", facts)
    if facts["models_advertised_ok"] is False:
        facts["reason"] = ("HTTP 200 but the expected model is not advertised "
                           "(wrong model on the port?)")
        return ("UNKNOWN", facts)
    if facts.get("progress_file_missing"):
        facts["reason"] = "configured progress file is missing (progress " \
                          "cannot be attested)"
        return ("UNKNOWN", facts)
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

CANARY_MIN_SECONDS = 1.0


def canary(url: str, out_dir: Path, timeout: float = 300.0,
           payload: dict | None = None, expect_samplerate: int = 48000,
           expect_channels: int = 2) -> tuple[bool, dict]:
    """Level-2 readiness: one real bounded short-budget generation whose
    audio must actually DECODE (format, rate, channels, finite, duration)
    and be freshly written by this request.

    Opt-in only; caller must hold the GPU lock and avoid racing an active
    full-song generation (check readiness==READY first)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pl = dict(payload or CANARY_PAYLOAD)
    pl.setdefault("output_path", str(out_dir))
    pl.setdefault("output_file_name", "readiness_canary.wav")
    stale = out_dir / pl["output_file_name"]
    if stale.exists():
        stale.unlink()  # a leftover file must never satisfy the canary
    req = urllib.request.Request(
        url + "/v1/audio/generations", data=json.dumps(pl).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    receipt = {"canary": "generation",
               "payload_budgets": {k: pl[k] for k in
                                   ("ode_steps", "semantic_max_tokens",
                                    "abc_max_tokens")}}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        receipt["http_status"] = resp.status
        receipt["wall_s"] = round(time.monotonic() - t0, 1)
        audio = body.get("audio") or ""
        receipt["audio_path"] = audio or None
        wav = Path(audio) if audio else None
        if not wav or not wav.is_file():
            receipt["reason"] = "response carried no audio file"
            return False, receipt
        fresh = wav.stat().st_mtime >= t0 - 1.0
        receipt["fresh"] = fresh
        dec = _decode_audio(wav)
        receipt["audio"] = dec
        problems = []
        if not fresh:
            problems.append("audio file predates the request (stale)")
        if not dec["finite"]:
            problems.append("non-finite samples")
        if dec["samplerate"] != expect_samplerate:
            problems.append(f"samplerate {dec['samplerate']} != {expect_samplerate}")
        if dec["channels"] != expect_channels:
            problems.append(f"channels {dec['channels']} != {expect_channels}")
        seconds = dec["frames"] / dec["samplerate"] if dec["samplerate"] else 0.0
        receipt["audio_seconds"] = round(seconds, 3)
        if seconds < CANARY_MIN_SECONDS:
            problems.append(f"duration {seconds:.2f}s < {CANARY_MIN_SECONDS}s")
        if dec["peak"] <= 1e-6:
            problems.append("digital silence")
        if problems:
            receipt["reason"] = "; ".join(problems)
            return False, receipt
        return True, receipt
    except Exception as e:
        receipt["wall_s"] = round(time.monotonic() - t0, 1)
        receipt["reason"] = f"{type(e).__name__}: {e}"
        return False, receipt


def _run_canary(url: str, canary_dir: str, timeout_s: float) -> tuple[bool, dict]:
    return canary(url, Path(canary_dir), timeout=timeout_s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GENERATION_READY FSM checks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--receipt", required=True)
    common.add_argument("--url", default=os.environ.get(
        "YUE2_SERVER_URL", "http://127.0.0.1:31000"))
    common.add_argument("--expect-model", default="YuE2")
    common.add_argument("--expect-model-path", default=None,
                        help="exact model_path the server must report")
    common.add_argument("--proc-root", default=PROC_ROOT_DEFAULT)
    common.add_argument("--progress-file", default=None)
    common.add_argument("--progress-deadline-s", type=float,
                        default=DEFAULT_PROGRESS_DEADLINE_S)
    c = sub.add_parser("check", parents=[common])
    c.add_argument("--canary-dir", default=None,
                   help="opt-in level-2: run a real short generation into "
                        "this directory; audio must decode")
    c.add_argument("--canary-timeout-s", type=float, default=600.0)
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
        receipt["ok"] = ok
        print(json.dumps(receipt, indent=1))
        return 0 if ok else 5

    def one():
        state, facts = check(a.receipt, a.url, proc_root=a.proc_root,
                             expect_model=a.expect_model,
                             expect_model_path=a.expect_model_path,
                             progress_file=a.progress_file,
                             progress_deadline_s=a.progress_deadline_s)
        line = {"state": state,
                "scheduler_alive": facts.get("scheduler_alive"),
                "http_health": facts.get("http_health"),
                "identity": facts.get("identity"),
                "models_advertised_ok": facts.get("models_advertised_ok"),
                "port_owner_state": facts.get("port_owner_state"),
                "established_connections": facts.get(
                    "established_connections")}
        if facts.get("reason"):
            line["reason"] = facts["reason"]
        print(json.dumps(line), flush=True)
        return state, facts

    if a.cmd == "check":
        state, facts = one()
        rc = EXIT_BY_STATE.get(state, 4)
        if (state == "BUSY" and a.progress_file
                and facts.get("progress_file_age_s") is not None
                and facts["progress_file_age_s"] > a.progress_deadline_s):
            rc = 6  # GPU_PROGRESS_TIMEOUT escalation
        if rc == 0 and a.canary_dir:
            ok, creceipt = _run_canary(a.url, a.canary_dir, a.canary_timeout_s)
            print(json.dumps({"canary": creceipt}), flush=True)
            if not ok:
                rc = 5
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
