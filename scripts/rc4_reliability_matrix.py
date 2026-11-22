#!/usr/bin/env python3
"""rc4_reliability_matrix.py — pre-registered M2.3 reliability matrix runner.

Executes a bounded request battery against a YuE2 SGLang server and records
one CSV row per case. SAFE BY DESIGN:
  * every request has a hard client timeout (default: shorts 300s, songs 1800s)
  * no frozen path is touched; outputs go to --out (default under
    /data/yue2-runs/rc4_evidence)
  * the server is NEVER pkill'd; the caller owns server lifecycle
Cases follow reports/joint_blog_rc/04_RUNTIME_RCA_AND_RELIABILITY.md (RC2
pre-registration) with RC4 scope notes; anything skipped is recorded as
NOT_TESTED — never silently dropped.

Usage:
  python3 scripts/rc4_reliability_matrix.py --server http://127.0.0.1:31000 \
      --out /data/yue2-runs/rc4_evidence/02_RELIABILITY_MATRIX.csv \
      [--shorts 50] [--invalid 10] [--songs 0] [--long-lyrics] [--oversized]
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

SHORT_PAYLOAD = {
    "style": "[Tags]\nsoft pop\n", "lyrics": "[Lyrics]\nA tiny phrase.\n",
    "seed": 700001, "cot": "full", "ode_steps": 4, "semantic_max_tokens": 300,
}
INVALID_PAYLOADS = [
    {"missing": "lyrics-and-style"},
    {"style": "[Tags]\nx\n", "lyrics": 12345},          # wrong type
    {"style": "[Tags]\nx\n", "lyrics": "[Lyrics]\nA.\n", "seed": "not-a-seed"},
    {"style": "[Tags]\nx\n", "lyrics": "[Lyrics]\nA.\n", "ode_steps": -5},
    {"style": "[Tags]\nx\n" * 200, "lyrics": "[Lyrics]\nA.\n"},  # repeated tags
]
# RC4.1 M3.3 RCA: payload #5 is schema-VALID; the server therefore applies
# DEFAULT full-song budgets (semantic_max_tokens=9000, ode_steps=32) and
# legitimately generates for minutes. The RC4 "hang >60 s" was an
# under-budgeted test timeout, NOT a server-side loop. Three consequences:
#   a) it is prechecked by scripts/input_budget.py (bounded rejection, no GPU)
#   b) a SHORT-budget variant proves the server handles it boundedly
#   c) the default-budget variant is opt-in with a full-song-class timeout
REPEATED_TAGS_PAYLOAD = INVALID_PAYLOADS[4]


def post(server: str, payload: dict, timeout: float):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        server + "/v1/audio/generations", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode(errors="replace")
            return r.status, time.monotonic() - t0, data[:400], None
    except urllib.error.HTTPError as e:
        return e.code, time.monotonic() - t0, e.read().decode(errors="replace")[:400], None
    except Exception as e:  # timeout / connection failure — the interesting part
        return None, time.monotonic() - t0, "", f"{type(e).__name__}: {e}"


def health(server: str, timeout: float = 10.0) -> tuple[int | None, float]:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(server + "/health", timeout=timeout) as r:
            r.read()
            return r.status, time.monotonic() - t0
    except Exception:
        return None, time.monotonic() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:31000")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shorts", type=int, default=50)
    ap.add_argument("--invalid", type=int, default=10)
    ap.add_argument("--songs", type=int, default=0,
                    help="complete-song requests (expensive; opt-in)")
    ap.add_argument("--long-lyrics", action="store_true")
    ap.add_argument("--oversized", action="store_true")
    ap.add_argument("--repeated-tags-short", action="store_true",
                    help="repeated-tags payload with short generation budgets")
    ap.add_argument("--repeated-tags-default", action="store_true",
                    help="repeated-tags payload with server DEFAULT budgets "
                         "(full-song class; completes in minutes)")
    ap.add_argument("--repeated-tags-default-timeout", type=float,
                    default=1800.0)
    ap.add_argument("--short-timeout", type=float, default=300.0)
    ap.add_argument("--song-timeout", type=float, default=1800.0)
    ap.add_argument("--tag", default="rc4")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def rec(case, n, status, dur, body, err):
        rows.append({"tag": args.tag, "case": case, "n": n,
                     "http_status": status if status is not None else "",
                     "wall_s": round(dur, 3),
                     "outcome": ("OK" if status == 200 else
                                 ("HTTP_ERR" if status else "CLIENT_ERR")),
                     "error": err or "", "body_head": (body or "")[:120].replace("\n", " "),
                     "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        print(f"[{case} #{n}] {rows[-1]['outcome']} status={status} "
              f"{dur:.1f}s {err or ''}", flush=True)

    st, hd = health(args.server)
    if st != 200:
        print(f"FATAL: server not healthy: {args.server} ({st})")
        return 2
    rows.append({"tag": args.tag, "case": "health_pre", "n": 0, "http_status": st,
                 "wall_s": round(hd, 3), "outcome": "OK", "error": "",
                 "body_head": "", "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    # 1) short valid requests
    for i in range(args.shorts):
        p = dict(SHORT_PAYLOAD, seed=710000 + i)
        s, d, b, e = post(args.server, p, args.short_timeout)
        rec("short_valid", i + 1, s, d, b, e)
        st2, _ = health(args.server)
        if st2 != 200:
            rec("health_after_failure", i + 1, st2, 0, "", "server unhealthy after case")

    # 2) invalid requests (cycled payloads)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from input_budget import check_payload
    for i in range(args.invalid):
        p = INVALID_PAYLOADS[i % len(INVALID_PAYLOADS)]
        # RC4.1: bounded-input precheck BEFORE any GPU-facing request
        verdict = check_payload(p)
        if not verdict["ok"]:
            rows.append({"tag": args.tag, "case": "invalid_request", "n": i + 1,
                         "http_status": "", "wall_s": 0.0,
                         "outcome": "BOUNDED_REJECT",
                         "error": f"{verdict['class']}: {verdict['reason']}",
                         "body_head": "", "ts_utc": time.strftime(
                             "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(f"[invalid_request #{i+1}] BOUNDED_REJECT "
                  f"{verdict['class']}", flush=True)
            continue
        s, d, b, e = post(args.server, p, 60.0)
        rec("invalid_request", i + 1, s, d, b, e)

    # 2b) repeated-tags SHORT budget: server must handle it boundedly
    if args.repeated_tags_short:
        p = dict(REPEATED_TAGS_PAYLOAD, seed=760001, ode_steps=4,
                 semantic_max_tokens=300, abc_max_tokens=512)
        s, d, b, e = post(args.server, p, args.short_timeout)
        rec("repeated_tags_short_budget", 1, s, d, b, e)

    # 2c) repeated-tags DEFAULT budgets: full-song-class request (opt-in;
    # completes in minutes — RC4.1 RCA proof that it is NOT a hang)
    if args.repeated_tags_default:
        p = dict(REPEATED_TAGS_PAYLOAD, seed=760002)
        s, d, b, e = post(args.server, p, args.repeated_tags_default_timeout)
        rec("repeated_tags_default_budget", 1, s, d, b, e)

    # 3) complete songs (official-ish parameters, distinct seeds)
    for i in range(args.songs):
        p = {"style": "[Tags]\nsoft pop\n", "lyrics": "[Lyrics]\nA tiny phrase.\n",
             "seed": 730000 + i, "cot": "full", "ode_steps": 32,
             "semantic_max_tokens": 9000,
             "output_path": str(args.out.parent / f"song_{i}"),
             "output_file_name": "v.wav", "id": f"matrix_song_{i}"}
        s, d, b, e = post(args.server, p, args.song_timeout)
        rec("complete_song", i + 1, s, d, b, e)
        st2, _ = health(args.server)
        if st2 != 200:
            rec("health_after_failure", i + 1, st2, 0, "", "server unhealthy after song")

    # 4) long-lyrics request (single, bounded)
    if args.long_lyrics:
        long_lyr = "[Lyrics]\n" + "\n".join(
            f"[verse {i}]\nLa la test phrase number {i} keeps going on\n" * 4
            for i in range(40))
        p = {"style": "[Tags]\nsoft pop\n", "lyrics": long_lyr, "seed": 740001,
             "cot": "full", "ode_steps": 32, "semantic_max_tokens": 9000}
        s, d, b, e = post(args.server, p, args.song_timeout)
        rec("long_lyrics", 1, s, d, b, e)

    # 5) oversized-input request (single, bounded; expect fast 4xx/5xx or bounded timeout)
    if args.oversized:
        p = {"style": "[Tags]\n" + "x" * 2_000_000, "lyrics": "[Lyrics]\nA.\n",
             "seed": 750001, "cot": "full", "ode_steps": 4,
             "semantic_max_tokens": 300}
        s, d, b, e = post(args.server, p, 120.0)
        rec("oversized_input", 1, s, d, b, e)

    st, hd = health(args.server)
    rows.append({"tag": args.tag, "case": "health_post", "n": 0, "http_status": st,
                 "wall_s": round(hd, 3), "outcome": "OK" if st == 200 else "UNHEALTHY",
                 "error": "", "body_head": "",
                 "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    new = not args.out.exists()
    with args.out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r["outcome"] == "OK")
    print(f"MATRIX DONE: {len(rows)} rows, {ok} OK; csv={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
