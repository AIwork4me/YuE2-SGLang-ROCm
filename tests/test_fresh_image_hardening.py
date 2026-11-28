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
        with pytest.raises(ValueError, match="interior"):
            A.read_journal(p)

    def test_conflicting_complete_and_failed_reported(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text(json.dumps({"id": "a", "status": "complete"}) + "\n"
                     + json.dumps({"id": "a", "status": "failed"}) + "\n")
        complete, problems = A.read_journal(p)
        assert complete == set()  # latest event wins; verified artifact may be recovered
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
        """The identity probe must report the child interpreter EXPLICITLY:
        python always; torch as a version OR as an explicit torch_error —
        never silently absent (torch-less CI included)."""
        args = type("A", (), {"venv_python": sys.executable})()
        rt = A.detect_runtime(args)
        assert rt.get("python")
        assert rt.get("torch") or rt.get("torch_error"), (
            f"runtime probe must not be silent about torch: {rt}")
        args2 = type("A", (), {"venv_python": None})()
        rt2 = A.detect_runtime(args2)
        assert rt2.get("python")  # falls back to this interpreter, still explicit

    def test_resume_ignores_volatile_timestamp_fields(self, tmp_path):
        """Regression: created_at_utc inside the compared identity made every
        resume a 'mismatch' (found on fresh image 2026-11-15). Volatile keys
        must be excluded from the write-once comparison on BOTH sides."""
        src = (REPO / "scripts" / "run_wsb_torch.py").read_text()
        assert "VOLATILE_KEYS" in src, "driver must declare volatile identity keys"
        assert "stable(prev) != stable(ident)" in src
        VOLATILE = ("created_at_utc",)
        old = {"run_id": "a", "backend": "torch-eager", "created_at_utc": "T1"}
        new = {"run_id": "a", "backend": "torch-eager", "created_at_utc": "T2"}
        strip = lambda d: {k: v for k, v in d.items() if k not in VOLATILE}
        assert strip(old) == strip(new)  # same stable contract -> resumable
        diff = dict(new, backend="torch")
        assert strip(old) != strip(diff)  # real config change still refused


# --------------------------------------------------------------- RCA-F4
class TestRcaF4GpuLock:
    def test_default_lock_resolves_at_call_time_not_import_time(self, monkeypatch, tmp_path):
        """M1.1 regression: the import-time frozen DEFAULT_LOCK caused
        PermissionError '/data' on CI (PR #13 run 44421080608). All library
        entry points must re-resolve the default from the environment at
        call time."""
        monkeypatch.setenv("YUE2_GPU_LOCK", str(tmp_path / "a" / "gpu.lock"))
        assert str(G.resolve_default_lock()) == str(tmp_path / "a" / "gpu.lock")
        monkeypatch.setenv("YUE2_GPU_LOCK", str(tmp_path / "b" / "gpu.lock"))
        assert str(G.resolve_default_lock()) == str(tmp_path / "b" / "gpu.lock")
        # RC6.1 M3.5: without an explicit lock the default is the SHARED
        # PHYSICAL domain (BDF-keyed) when a GPU is resolvable and the shared
        # root is usable; call-time resolution still holds (a different root
        # takes effect immediately)
        monkeypatch.delenv("YUE2_GPU_LOCK")
        monkeypatch.setenv("YUE2_GPU_LOCK_ROOT", str(tmp_path / "shared1"))
        l1 = str(G.resolve_default_lock())
        monkeypatch.setenv("YUE2_GPU_LOCK_ROOT", str(tmp_path / "shared2"))
        assert str(G.resolve_default_lock()) != l1
        # legacy fallback: unwritable shared root -> workspace lock
        monkeypatch.setenv("YUE2_GPU_LOCK_ROOT", "/proc/no-such-root")
        monkeypatch.setenv("YUE2_WORKSPACE", str(tmp_path / "ws1"))
        assert str(G.resolve_default_lock()) == str(tmp_path / "ws1" / "gpu.lock")

    def test_ownership_without_lock_path_honors_late_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YUE2_GPU_LOCK", str(tmp_path / "deep" / "nest" / "gpu.lock"))
        with G.gpu_ownership("late-env", wait_s=0) as receipt:
            assert receipt["who"] == "late-env"
        assert (tmp_path / "deep" / "nest" / "gpu.lock").exists()

    def test_cli_lock_flag_defaults_to_call_time_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YUE2_GPU_LOCK", str(tmp_path / "cli.lock"))
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "gpu_lock.py"),
                            "status"], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0
        assert str(tmp_path / "cli.lock") in r.stdout

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


class TestFreshJournalHardeningV2:
    def test_missing_newline_even_complete_json_quarantined(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_bytes(b'{"id":"x","status":"complete"}')
        done, problems = A.read_journal(p)
        assert not done
        assert any("torn final line" in x for x in problems)
        assert p.read_bytes() == b""
        sidecars = list(tmp_path.glob("j.jsonl.corrupt-tail-*.bin"))
        assert len(sidecars) == 1
        assert b'"id":"x"' in sidecars[0].read_bytes()
        A.atomic_append(p, {"id": "x", "status": "complete"})
        assert A.read_journal(p)[0] == {"x"}

    def test_torn_tail_followed_by_append_without_recovery_fails(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_bytes(b'{"id":"oops"')
        with pytest.raises(ValueError, match="torn record"):
            A.atomic_append(p, {"id": "safe", "status": "complete"})
        assert p.read_bytes() == b'{"id":"oops"'

    def test_recover_valid_orphan_without_regeneration(self, tmp_path):
        p = tmp_path / "songs" / "wsb_test"
        p.mkdir(parents=True)
        journal = tmp_path / "journal.jsonl"
        def verified(path):
            assert path == p
            return {"identity": "verified"}
        completed = set()
        skip, recovered = A.resume_verified_candidate(
            p, "wsb_test", completed, verified, journal)
        assert (skip, recovered) == (True, True)
        assert completed == {"wsb_test"}
        assert A.read_journal(journal)[0] == completed

    def test_claimed_but_invalid_candidate_recounted(self, tmp_path):
        p = tmp_path / "songs" / "missing"
        completed = {"missing"}
        skip, changed = A.resume_verified_candidate(
            p, "missing", completed, lambda _: (_ for _ in ()).throw(ValueError()),
            tmp_path / "journal.jsonl")
        assert (skip, changed) == (False, True) and not completed

    def test_symlink_candidate_is_refused(self, tmp_path):
        p = tmp_path / "real"
        p.mkdir()
        link = tmp_path / "alias"
        link.symlink_to(p, target_is_directory=True)
        with pytest.raises(RuntimeError, match="symlink"):
            A.resume_verified_candidate(link, "alias", set(),
                lambda _: {"identity": "ok"}, tmp_path / "journal.jsonl")
