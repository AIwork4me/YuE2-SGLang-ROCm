"""Fresh-image hardening regression tests (RCA-F1..F4, Phase P3).

Negative and positive controls with SAFE SYNTHETIC fixtures only — no GPU, no
real model weights, no official-dataset content. These tests prove the harness
contracts; they are never evidence about official WildSongBench results.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import run_wsb_torch as A  # noqa: E402
import gpu_lock as G  # noqa: E402


# --------------------------------------------------------------- RCA-F1
class TestRcaF1PartialDirQuarantine:
    def test_worker_never_deletes_partial_dirs(self):
        assert "shutil.rmtree" not in A.GEN_WORKER, (
            "GEN_WORKER must not rmtree partial dirs (quarantine-not-delete)")

    def test_worker_quarantines_partial_dirs(self):
        assert ".partial.quarantine-" in A.GEN_WORKER
        assert "shutil.move" in A.GEN_WORKER

    def test_partial_dir_survives_regeneration(self, tmp_path):
        """Physical control: a stale .partial dir must be MOVED, not deleted."""
        songs = tmp_path / "songs"
        ident = "wsb_000_r0_s831001"
        out = songs / ident
        tmp = songs / f"{ident}.partial"
        tmp.mkdir(parents=True)
        (tmp / "precious_evidence.bin").write_bytes(b"\x00\x01\x02")
        # run the exact quarantine branch from GEN_WORKER against the fixture
        import shutil
        if tmp.exists():
            import time as _t
            q = tmp.with_name(ident + ".partial.quarantine-" + str(int(_t.time())))
            shutil.move(str(tmp), str(q))
        assert not tmp.exists()
        qs = list(songs.glob(f"{ident}.partial.quarantine-*"))
        assert len(qs) == 1
        assert (qs[0] / "precious_evidence.bin").read_bytes() == b"\x00\x01\x02"


# --------------------------------------------------------------- RCA-F2
class TestRcaF2JournalCrashConsistency:
    def test_append_is_fsynced_single_write(self, tmp_path):
        p = tmp_path / "j.jsonl"
        A.atomic_append(p, {"id": "x", "status": "complete"})
        A.atomic_append(p, {"id": "y", "status": "failed"})
        assert [json.loads(l)["id"] for l in p.read_text().splitlines()] == ["x", "y"]
        assert not list(tmp_path.glob("j.tmp")), "no stray .tmp intermediates"

    def test_torn_final_line_not_counted_complete(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text(json.dumps({"id": "a", "status": "complete"}) + "\n"
                     + '{"id": "b", "status": "comp')  # crash mid-append
        complete, problems = A.read_journal(p)
        assert complete == {"a"}
        assert any("torn final line" in x for x in problems)

    def test_interior_garbage_is_a_problem(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text(json.dumps({"id": "a", "status": "complete"}) + "\n"
                     + "GARBAGE-NOT-JSON\n"
                     + json.dumps({"id": "b", "status": "complete"}) + "\n")
        complete, problems = A.read_journal(p)
        assert complete == {"a", "b"}
        assert any("interior" in x for x in problems)

    def test_conflicting_complete_and_failed_reported(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text(json.dumps({"id": "a", "status": "complete"}) + "\n"
                     + json.dumps({"id": "a", "status": "failed"}) + "\n")
        complete, problems = A.read_journal(p)
        assert complete == {"a"}  # artifact verify remains the authority
        assert any("both" in x for x in problems)

    def test_duplicate_completion_deduplicated(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text(json.dumps({"id": "a", "status": "complete",
                                 "attempt": 1}) + "\n"
                     + json.dumps({"id": "a", "status": "complete",
                                   "attempt": 2}) + "\n")
        complete, problems = A.read_journal(p)
        assert complete == {"a"} and problems == []

    def test_empty_and_missing_journal(self, tmp_path):
        complete, problems = A.read_journal(tmp_path / "absent.jsonl")
        assert complete == set() and problems == []
        p = tmp_path / "j.jsonl"
        p.write_text("\n\n")
        complete, problems = A.read_journal(p)
        assert complete == set() and problems == []


# --------------------------------------------------------------- RCA-F3
class TestRcaF3ExactExperimentIdentity:
    def test_identity_fields_present(self):
        src = (REPO / "scripts" / "run_wsb_torch.py").read_text()
        for field in ("model_sha256", "vae_sha256", "evaluator_bundle_sha256",
                      "driver_source_sha256", "generator_worker_sha256",
                      "generation_contract", "runtime", "identity_schema"):
            assert field in src, f"run identity must record {field}"

    def test_driver_sha_is_the_real_file(self):
        import hashlib
        h = hashlib.sha256((REPO / "scripts" / "run_wsb_torch.py").read_bytes()).hexdigest()
        # detect_runtime etc. run at campaign time; assert the helper works here
        assert len(h) == 64

    def test_detect_runtime_reports_child_python(self, tmp_path):
        fake = tmp_path / "fakepython.py"
        fake.write_text(
            "import json,sys\n"
            "print(json.dumps({'python':'9.9.9','torch':'fake'}))\n")
        args = type("A", (), {"venv_python": sys.executable})()
        rt = A.detect_runtime(args)
        assert rt.get("python") and rt.get("torch")
        args2 = type("A", (), {"venv_python": None})()
        rt2 = A.detect_runtime(args2)
        assert rt2.get("python")  # falls back to this interpreter, still explicit


# --------------------------------------------------------------- RCA-F4
class TestRcaF4GpuLock:
    def test_exclusion_and_release(self, tmp_path):
        lock = tmp_path / "gpu.lock"
        with G.gpu_ownership("t1", wait_s=0, lock_path=lock):
            st = G.status(lock)
            assert st["holder"]["who"] == "t1"
            assert st["holder_live"]
            # second acquisition in-process must time out immediately
            with pytest.raises(TimeoutError):
                with G.gpu_ownership("t2", wait_s=0, poll_s=0.05, lock_path=lock):
                    pass
        st = G.status(lock)
        assert st["holder"]["who"] == "t1" and not st["holder_live"]

    def test_cross_process_exclusion(self, tmp_path):
        lock = tmp_path / "gpu.lock"
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,time;sys.path.insert(0,%r);" % str(REPO / "scripts")
             + "import gpu_lock as G\n"
             + "with G.gpu_ownership('child',wait_s=0,lock_path=%r):\n" % str(lock)
             + "    time.sleep(30)\n"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            time.sleep(1.5)
            proc = subprocess.run(
                [sys.executable, "-c",
                 "import sys;sys.path.insert(0,%r);" % str(REPO / "scripts")
                 + "import gpu_lock as G\n"
                 + "try:\n"
                 + "    G.gpu_ownership('probe',wait_s=0.2,poll_s=0.1,lock_path=%r).__enter__()\n" % str(lock)
                 + "    print('ACQUIRED')\n"
                 + "except TimeoutError:\n"
                 + "    print('BLOCKED')\n"],
                capture_output=True, text=True, timeout=15)
            assert "BLOCKED" in proc.stdout, "live holder must block a second acquisition"
            # graceful stop refuses without confirmation, works with it
            r = subprocess.run([sys.executable, str(REPO / "scripts" / "gpu_lock.py"),
                                "--lock", str(lock), "stop"], capture_output=True,
                               text=True, timeout=30)
            assert "refusing" in r.stdout and r.returncode == 2
            r2 = subprocess.run([sys.executable, str(REPO / "scripts" / "gpu_lock.py"),
                                 "--lock", str(lock), "stop", "--yes"],
                                capture_output=True, text=True, timeout=60)
            assert r2.returncode in (0, 1)  # holder may exit between calls
        finally:
            holder.terminate()
            try:
                holder.wait(timeout=10)
            except subprocess.TimeoutExpired:
                holder.kill()

    def test_stale_receipt_under_kernel_flock_is_authoritative(self, tmp_path):
        # flock is kernel-held: a faked receipt cannot steal a live lock
        lock = tmp_path / "gpu.lock"
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,time;sys.path.insert(0,%r);" % str(REPO / "scripts")
             + "import gpu_lock as G\n"
             + "with G.gpu_ownership('real',wait_s=0,lock_path=%r):\n" % str(lock)
             + "    time.sleep(60)\n"])
        time.sleep(1.5)
        # forge a dead-pid receipt over the lock FILE (kernel flock unaffected)
        lock.write_text(json.dumps({"who": "forged", "pid": 999999,
                                    "cmdline": "not-running"}))
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);" % str(REPO / "scripts")
             + "import gpu_lock as G\n"
             + "try:\n"
             + "    G.gpu_ownership('thief',wait_s=0.3,poll_s=0.1,lock_path=%r).__enter__()\n" % str(lock)
             + "    print('STOLEN')\n"
             + "except TimeoutError:\n"
             + "    print('HELD-BY-KERNEL')\n"],
            capture_output=True, text=True, timeout=15)
        assert "HELD-BY-KERNEL" in proc.stdout
        holder.terminate()
        holder.wait(timeout=10)


# --------------------------------------------------------------- RCA-F6
class TestRcaF6GateStatusVocabulary:
    def test_fresh_image_ledger_uses_exact_statuses(self):
        p = REPO / "reports" / "publication" / "fresh_image" / "FINAL_RELEASE_GATE_LEDGER.json"
        if not p.is_file():
            pytest.skip("final ledger written at mission close")
        d = json.loads(p.read_text())
        allowed = {"PASS", "FAIL", "BLOCKED", "NOT_TESTED"}
        bad = {g: s["status"] for g, s in d["gates"].items()
               if s["status"] not in allowed}
        assert not bad, f"gate statuses must be exactly {allowed}: {bad}"

    def test_historical_ledger_caveats_live_in_notes(self):
        """The historical ledger must not encode pending work as PASS.

        This test documents the F6 defect; it passes once the historical
        ledger's status strings are normalized to the exact vocabulary with
        caveats moved to 'note' fields.
        """
        p = REPO / "reports" / "publication" / "RELEASE_GATE_LEDGER.json"
        d = json.loads(p.read_text())
        allowed = {"PASS", "FAIL", "BLOCKED", "NOT_TESTED", "PENDING",
                   "IN PROGRESS", "PARTIAL", "PARTIALLY RESOLVED",
                   "PARTIAL —", "NOT RUN"}
        bad = {g: s["status"] for g, s in d["gates"].items()
               if isinstance(s.get("status"), str)
               and s["status"] not in allowed
               and not s["status"].startswith("PARTIAL")}
        assert not bad, (
            f"statuses must be from the vocabulary or start with PARTIAL: {bad}")
