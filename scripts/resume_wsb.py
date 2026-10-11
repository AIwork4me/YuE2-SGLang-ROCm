#!/usr/bin/env python3
"""Resume a WSB run: identical invocation semantics to the original driver.

run_wsb.py skips candidates whose artifacts pass the official verify_result
and regenerates only incomplete ones, so 'resume' is simply re-invoking the
driver with the same --runs directory. This wrapper makes that explicit and
audits the current state first.

Usage: python scripts/resume_wsb.py --runs runs/wsb_full
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "--runs":
        raise SystemExit("usage: resume_wsb.py --runs <dir> [extra run_wsb args]")
    runs = sys.argv[2]
    audit = subprocess.run([sys.executable, str(HERE / "verify_wsb_artifacts.py"),
                            "--runs", runs, "--mode", "full"], cwd=str(HERE.parent))
    print("audit exit:", audit.returncode, "(1 while the run is incomplete is expected)")
    raise SystemExit(subprocess.run([sys.executable, str(HERE / "run_wsb.py")] + sys.argv[1:],
                                    cwd=str(HERE.parent)).returncode)
