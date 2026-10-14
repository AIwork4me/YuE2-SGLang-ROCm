#!/usr/bin/env python3
"""test_scoring_stage_check.py - completeness-gate tests (review F1 regression).

Covers: per-only crash remnant MUST NOT skip stage 5; complete per+songbench
MUST skip; mulan-only remnant MUST NOT skip stage 6; complete additional MUST
skip; corrupt/partial JSON is not complete.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHK = HERE.parent / "scripts" / "scoring_stage_check.py"


def block(metric, scored=384):
    return {"expected": scored, "scored": scored, "failed": 0,
            "not_applicable": 0}


def write_summary(run, rel, metrics, *, complete=True, coverage=True,
                  rows=384, mode="standard"):
    s = {
        "schema": 1, "complete": complete, "mode": mode,
        "candidate_count": rows, "prompt_count": 192, "errors": [],
        "unselected_candidates": {
            "schema": 1, "complete": True, "samples": rows,
            "groups": {"all": {m: block(m) for m in metrics}},
            "metrics": list(metrics),
        },
    }
    if mode == "standard":
        s["full_192_standard_candidate_coverage"] = coverage and len(metrics) >= 2
    else:
        s["full_192_selected_coverage"] = coverage and len(metrics) >= 2
    p = run / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s))
    return s


def write_per_song(run, n=384):
    p = run / "scores" / "per_song.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for i in range(n):
            f.write(json.dumps({"id": f"wsb_{i:03d}_r0_s1"}) + "\n")


class StageCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stagechk-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_chk(self, what):
        return subprocess.run(
            [sys.executable, str(CHK), what, str(self.tmp)],
            capture_output=True, text=True)

    def test_per_only_crash_remnant_must_not_skip(self):
        write_summary(self.tmp, "scores/summary.json", ["per"],
                      coverage=True)
        write_per_song(self.tmp, 384)
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_complete_per_songbench_skips(self):
        write_summary(self.tmp, "scores/summary.json", ["per", "songbench"])
        write_per_song(self.tmp, 384)
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_incomplete_flag_must_not_skip(self):
        write_summary(self.tmp, "scores/summary.json",
                      ["per", "songbench"], complete=False)
        write_per_song(self.tmp, 384)
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 1)

    def test_short_per_song_must_not_skip(self):
        write_summary(self.tmp, "scores/summary.json", ["per", "songbench"])
        write_per_song(self.tmp, 200)
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 1)

    def test_mulan_only_remnant_must_not_skip_additional(self):
        write_summary(self.tmp, "additional/summary.json", ["mulan"],
                      mode="selected")
        r = self.run_chk("additional")
        self.assertEqual(r.returncode, 1)

    def test_complete_additional_skips(self):
        write_summary(self.tmp, "additional/summary.json",
                      ["mulan", "allmusiccaps"], mode="selected")
        r = self.run_chk("additional")
        self.assertEqual(r.returncode, 0)

    def test_corrupt_summary_not_complete(self):
        (self.tmp / "scores").mkdir(parents=True, exist_ok=True)
        (self.tmp / "scores" / "summary.json").write_text("{partial")
        write_per_song(self.tmp, 384)
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 1)

    def test_missing_everything_not_complete(self):
        r = self.run_chk("per")
        self.assertEqual(r.returncode, 1)
        r = self.run_chk("additional")
        self.assertEqual(r.returncode, 1)

    def test_per_song_rows_counter(self):
        write_per_song(self.tmp, 7)
        r = self.run_chk("per_song_rows")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "7")


if __name__ == "__main__":
    unittest.main(verbosity=2)
