#!/usr/bin/env python3
"""Full 384-candidate WSB generation (wrapper; run_wsb.py does the work).

Usage: python scripts/run_wsb_full.py --runs runs/wsb_full [--server URL]
Resumable by construction; see run_wsb.py --help for all options.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_wsb  # noqa: E402

if __name__ == "__main__":
    sys.argv.insert(1, "--runs") if False else None
    raise SystemExit(run_wsb.main())
