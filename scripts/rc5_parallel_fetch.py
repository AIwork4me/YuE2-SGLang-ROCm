#!/usr/bin/env python3
"""rc5_parallel_fetch.py — multi-connection HTTP range download through a slow
egress proxy (RC5). Splits the file into N byte ranges fetched by concurrent
curl processes (each retrying with resume), concatenates them and checks the
total length against Content-Length. Nothing is trusted without the size
check; pass --sha256 to pin the content.

  python scripts/rc5_parallel_fetch.py URL DEST [--jobs 12] [--sha256 HEX]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def head_length(url: str) -> int:
    r = subprocess.run(["curl", "-sS", "-L", "-I", "-m", "120", url], capture_output=True, text=True)
    length = None
    for line in r.stdout.lower().splitlines():
        if line.startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    if not length:
        raise SystemExit(f"cannot determine Content-Length for {url}: {r.stdout[-300:]} {r.stderr[-200:]}")
    return length


def fetch_range(url: str, dest: Path, start: int, end: int) -> None:
    want = end - start + 1
    for attempt in range(40):
        have = dest.stat().st_size if dest.exists() else 0
        if have >= want:
            return
        r = subprocess.run(["curl", "-sS", "-L", "--fail", "-m", "3600", f"-r", f"{start + have}-{end}",
                            "-o", str(dest) + ".add", url], capture_output=True, text=True)
        if dest.with_name(dest.name + ".add").exists():
            with open(dest, "ab") as out, open(str(dest) + ".add", "rb") as add:
                while chunk := add.read(8 << 20):
                    out.write(chunk)
            dest.with_name(dest.name + ".add").unlink()
        if dest.exists() and dest.stat().st_size >= want:
            return
        time.sleep(min(60, 3 * (attempt + 1)))
    raise SystemExit(f"range {start}-{end} incomplete after retries: {dest} has "
                     f"{dest.stat().st_size if dest.exists() else 0}/{want}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("dest", type=Path)
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--sha256", default=None)
    a = ap.parse_args()
    total = head_length(a.url)
    a.dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.dest.with_name(a.dest.name + ".parts")
    tmp.mkdir(exist_ok=True)
    step = (total + a.jobs - 1) // a.jobs
    ranges = [(i, min(i + step - 1, total - 1)) for i in range(0, total, step)]
    t0 = time.time()
    print(f"{total/1e6:.1f} MB in {len(ranges)} ranges", flush=True)
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(lambda r: fetch_range(a.url, tmp / f"{r[0]:012d}.part", *r), ranges))
    h = hashlib.sha256()
    with open(a.dest, "wb") as out:
        for start, end in ranges:
            p = tmp / f"{start:012d}.part"
            with open(p, "rb") as f:
                while chunk := f.read(8 << 20):
                    h.update(chunk)
                    out.write(chunk)
    size = a.dest.stat().st_size
    ok = size == total and (not a.sha256 or h.hexdigest() == a.sha256)
    print(f"{'OK' if ok else 'FAILED'} {a.dest} {size} bytes sha256 {h.hexdigest()} "
          f"in {time.time() - t0:.0f}s", flush=True)
    if ok:
        for start, _ in ranges:
            (tmp / f"{start:012d}.part").unlink()
        tmp.rmdir()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
