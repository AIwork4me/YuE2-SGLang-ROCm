#!/usr/bin/env python3
"""Pilot WSB generation over an explicitly listed subset of prompts.

Usage: python scripts/run_wsb_pilot.py --runs runs/wsb_pilot --indices 0 1 2 76 77
Pilot scope must be a subset of official rows; contents/seeds/budgets are
never modified (enforced by run_wsb.py against the frozen manifest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_wsb  # noqa: E402

if __name__ == "__main__":
    if "--indices" not in sys.argv:
        sys.argv += ["--indices", "0", "1", "2", "76", "77"]
    raise SystemExit(run_wsb.main())
