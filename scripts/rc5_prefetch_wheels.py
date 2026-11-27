#!/usr/bin/env python3
"""rc5_prefetch_wheels.py — fetch EXACTLY the locked artifacts with curl (RC5).

Why: behind this host's egress proxy uv/pip transfer PyPI wheels at
0.6–2.6 MB/s while curl reaches 15–22 MB/s. The artifacts are not chosen by
this tool's taste: for every `name==version` line of a lock file the PyPI
JSON API is asked for the file list and the artifact is selected with pip's
compatibility and preference rules for CPython 3.12 / manylinux x86_64:

    wheels beat sdists; cp312 beats cp38-abi3 beats py3;
    the most specific supported manylinux tag wins.

Every download is verified against the SHA256 published by PyPI. The result
is a flat wheel directory for `uv pip install --no-index --find-links DIR`
(the official evaluator `prepare` honours UV_NO_INDEX / UV_FIND_LINKS), so the
installed versions and artifacts are exactly the frozen lock's.

Usage:
  python scripts/rc5_prefetch_wheels.py --lock a.txt [--lock b.txt ...] \
      --dest /data/yue2/tmp/wheels [--manifest out.json] [--jobs 6]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = [3, 12]          # target CPython minor (set by --py)
GLIBC = (2, 39)
MANYLINUX_ALIASES = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}
WHEEL_RE = re.compile(
    r"^(?P<name>[^-]+)-(?P<ver>[^-]+)(-(?P<build>\d[^-]*))?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def py_ok(tag: str) -> int:
    """python-tag compatibility -> rank (0 = incompatible)."""
    minor = PY[1]
    if tag in (f"cp3{minor}", "py3"):
        return 3 if tag != "py3" else 1
    m = re.fullmatch(r"cp3(\d+)", tag)
    if m and int(m.group(1)) <= minor:
        return 2          # only with abi3 (checked together)
    if tag in ("py2.py3", "cp3", "pp3"):
        return 1 if tag == "py2.py3" else 0
    return 0


def plat_rank(tag: str) -> int:
    if tag == "any":
        return 1
    if tag == "linux_x86_64":
        return 2
    m = re.fullmatch(r"manylinux_2_(\d+)_x86_64", tag)
    if m and int(m.group(1)) <= GLIBC[1]:
        return 10 + int(m.group(1))
    base = tag[:-len("_x86_64")] if tag.endswith("_x86_64") else tag
    if base in MANYLINUX_ALIASES:
        return 10 + MANYLINUX_ALIASES[base][1]
    return 0


def wheel_score(filename: str):
    m = WHEEL_RE.match(filename)
    if not m:
        return None
    best = None
    for pt in m["py"].split("."):
        for abi in m["abi"].split("."):
            for plat in m["plat"].split("."):
                pr = py_ok(pt)
                if not pr or not plat_rank(plat):
                    continue
                minor = PY[1]
                if pt.startswith("cp3") and pt != f"cp3{minor}" and abi != "abi3":
                    continue
                if pt == f"cp3{minor}" and abi not in (f"cp3{minor}", "abi3", "none"):
                    continue
                if pt == "py3" and abi != "none":
                    continue
                abi_rank = {f"cp3{PY[1]}": 3, "abi3": 2, "none": 1}.get(abi, 0)
                key = (pr, abi_rank, plat_rank(plat))
                if best is None or key > best:
                    best = key
    return best


def pypi_files(name: str, version: str) -> list[dict]:
    url = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "yue2-rc5-prefetch/1"}), timeout=60) as r:
                return json.loads(r.read())["urls"]
        except Exception as e:  # noqa: BLE001
            if attempt == 5:
                raise
            print(f"  [pypi retry {attempt + 1}] {name}=={version}: {type(e).__name__}", flush=True)
            time.sleep(3 * (attempt + 1))
    return []


def choose(name: str, version: str) -> dict:
    files = pypi_files(name, version)   # the project/version endpoint lists only its own files
    best = None
    for f in files:
        if f["filename"].endswith(".whl"):      # PyPI reports wheels as bdist_wheel
            s = wheel_score(f["filename"])
            if s is None:
                continue
            key = (1, s)
            if best is None or key > best[0]:
                best = (key, f)
    if best is None:
        sd = [f for f in files if f["packagetype"] == "sdist"]
        if not sd:
            raise RuntimeError(f"no compatible artifact for {name}=={version}")
        return sd[0]
    return best[1]


def curl(url: str, dest: Path, sha: str) -> dict:
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
        return {"status": "cached", "bytes": dest.stat().st_size}
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(6):
        r = subprocess.run(["curl", "-sS", "-L", "--fail", "-m", "1800", "-o", str(tmp), url],
                           capture_output=True, text=True)
        if r.returncode == 0 and tmp.is_file():
            h = hashlib.sha256()
            with open(tmp, "rb") as f:
                for chunk in iter(lambda: f.read(8 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() == sha:
                os.replace(tmp, dest)
                return {"status": "downloaded", "bytes": dest.stat().st_size}
            print(f"  [sha mismatch retry {attempt + 1}] {dest.name}", flush=True)
        else:
            print(f"  [curl retry {attempt + 1}] {dest.name}: {r.stderr[-120:]}", flush=True)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", type=Path, action="append", required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--py", default="3.12", help="target CPython minor, e.g. 3.10")
    ap.add_argument("--files-host", default="https://files.pythonhosted.org",
                    help="mirror for the /packages/ path (same files, same PyPI SHA256)")
    a = ap.parse_args()
    PY[1] = int(a.py.split(".")[1])
    a.dest.mkdir(parents=True, exist_ok=True)
    reqs: dict[tuple[str, str], None] = {}
    for lock in a.lock:
        for line in lock.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, _, ver = line.partition("==")
            reqs[(name.strip(), ver.strip())] = None
    print(f"{len(reqs)} locked requirements from {len(a.lock)} lock file(s)")
    plan = []
    for i, (name, ver) in enumerate(sorted(reqs), 1):
        f = choose(name, ver)
        url = f["url"].replace("https://files.pythonhosted.org/", a.files_host.rstrip("/") + "/")
        plan.append({"name": name, "version": ver, "filename": f["filename"], "url": url,
                     "sha256": f["digests"]["sha256"], "bytes": f["size"],
                     "type": f["packagetype"], "yanked": f.get("yanked", False)})
        if i % 25 == 0:
            print(f"  resolved {i}/{len(reqs)}", flush=True)
    sdists = [p for p in plan if p["type"] == "sdist"]
    print(f"resolved: {len(plan)} artifacts ({len(sdists)} sdist), "
          f"{sum(p['bytes'] for p in plan)/1e9:.2f} GB")

    def fetch(p):
        dest = a.dest / p["filename"]
        t0 = time.time()
        res = curl(p["url"], dest, p["sha256"])
        return {**p, **res, "seconds": round(time.time() - t0, 1)}
    done = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for r in ex.map(fetch, plan):
            done.append(r)
            if r["status"] == "downloaded" and r["bytes"] > 50e6:
                print(f"  {r['filename'][:60]:60s} {r['bytes']/1e6:8.1f} MB in {r['seconds']}s", flush=True)
    manifest = {
        "schema": "yue2-rc5-prefetched-wheels/1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "locks": [str(x) for x in a.lock], "dest": str(a.dest),
        "selection": "PyPI JSON API; pip compatibility rules for CPython 3.12 / "
                     "manylinux x86_64 (glibc 2.39); SHA256 verified against PyPI",
        "files_host": a.files_host,
        "count": len(done), "total_bytes": sum(r["bytes"] for r in done),
        "files": sorted(done, key=lambda r: r["filename"]),
    }
    out = a.manifest or a.dest / "PREFETCH_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"OK {len(done)} artifacts, {manifest['total_bytes']/1e9:.2f} GB -> {a.dest}; manifest {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
