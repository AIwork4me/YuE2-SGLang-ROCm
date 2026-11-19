#!/usr/bin/env python3
"""C2.1 P1-B.3 mutation controls — run in an ISOLATED COPY, never the branch.

Five security-relevant mutations; the suite must FAIL for each (a mutation
that no test catches is an untested contract). Results table printed; exit 0
only if every mutation is KILLED by at least one test.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("M1-drop-symlink-guard",
     "scripts/run_wsb_torch.py",
     '    if path.is_symlink():\n        raise RuntimeError(f"worker snapshot is a SYMLINK (refused even if "\n                           f"target content matches): {path.name}")',
     ""),
    ("M2-noclobber-to-replace",
     "scripts/build_per_reference_package.py",
     "        try:\n            link_no_clobber(tmp, dst)\n        except PublishError as exc:\n            raise IdentityError(f\"destination collision at commit: {exc}\") from exc",
     "        os.replace(tmp, dst)"),
    ("M3-skip-mp3-sha-bind",
     "scripts/build_per_reference_package.py",
     '    if receipt.get("mp3_sha256") != row_sha:\n        raise IdentityError(f"{cid}: encoding.mp3_sha256 != receipt.audio_sha256")',
     ""),
    ("M4-skip-session-verification",
     "scripts/verify_provenance.py",
     '    if sid not in sessions_cache:\n        sessions_cache[sid] = _load_json(\n            prov / "driver_sessions" / f"{sid}.json", f"driver session {sid[:8]}…")',
     "    if sid not in sessions_cache:\n        sessions_cache[sid] = {\"session_id\": sid}  # MUTANT: trust the journal"),
    ("M5-skip-postcopy-sha",
     "scripts/build_per_reference_package.py",
     '        if after_src != before:\n            raise IdentityError(f"source mutated during copy: {src.name}")',
     "        pass  # MUTANT: no post-copy source check"),
]
TESTS = [
    "tests/test_c2_1_fail_closed.py",
    "tests/test_c2_provenance.py",
    "tests/test_c2_audio_identity.py",
]


def run(name: str) -> int:
    with tempfile.TemporaryDirectory(prefix="mutation-") as td:
        wt = Path(td) / "repo"
        shutil.copytree(SRC, wt, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        mut = next(m for m in MUTATIONS if m[0] == name)
        target = wt / mut[1]
        text = target.read_text()
        if mut[2] not in text:
            print(f"{name}: MUTATION ANCHOR NOT FOUND (stale?)")
            return 2
        target.write_text(text.replace(mut[2], mut[3], 1))
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-q", "-x"],
            cwd=wt, capture_output=True, text=True)
        killed = r.returncode != 0
        tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-1:]
        print(f"{'KILLED ' if killed else 'SURVIVED'} {name}: {tail}")
        if not killed:
            print(r.stdout[-2000:])
        return 0 if killed else 1


def main() -> int:
    bad = 0
    for name, *_ in MUTATIONS:
        rc = run(name)
        if rc != 0:
            bad += 1
    print(f"\n{'ALL MUTATIONS KILLED' if bad == 0 else f'{bad} MUTATIONS SURVIVED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
