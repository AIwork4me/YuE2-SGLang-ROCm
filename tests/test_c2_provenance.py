"""C2 P3 — worker source snapshots + per-attempt provenance.

Real filesystem operations: write-once snapshots, tamper/symlink attacks,
crash windows (launched-without-result), forged receipts, journal↔receipt
consistency, and the full legacy-resume compatibility matrix (mission 5.5).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import run_wsb_torch as A  # noqa: E402

SESSION_ID = "c0ffee" * 5  # realistic uuid-length session id


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestWorkerSnapshots:
    def test_fresh_run_creates_content_addressed_snapshot(self, tmp_path):
        snap, sha = A.snapshot_worker_source(tmp_path)
        assert snap.parent.name == "worker_sources"
        assert snap.name == f"{sha}.py"
        assert _sha(snap) == sha
        # exact writability contract: owner/group/other write bits ALL clear
        assert snap.stat().st_mode & 0o222 == 0, oct(snap.stat().st_mode)

    def test_second_call_same_content_reuses_and_verifies(self, tmp_path):
        s1, sha1 = A.snapshot_worker_source(tmp_path)
        before = s1.read_bytes()
        s2, sha2 = A.snapshot_worker_source(tmp_path)
        assert s1 == s2 and sha1 == sha2 and s2.read_bytes() == before

    def test_tampered_snapshot_detected(self, tmp_path):
        snap, sha = A.snapshot_worker_source(tmp_path)
        os.chmod(snap, 0o644)
        snap.write_text("# tampered")
        with pytest.raises(RuntimeError, match="tampered"):
            A.snapshot_worker_source(tmp_path)

    def test_snapshot_is_never_overwritten_by_new_content(self, tmp_path,
                                                           monkeypatch):
        s1, sha1 = A.snapshot_worker_source(tmp_path)
        old_bytes = s1.read_bytes()
        monkeypatch.setattr(A, "GEN_WORKER", A.GEN_WORKER + "\n# v2 change\n")
        s2, sha2 = A.snapshot_worker_source(tmp_path)
        assert sha2 != sha1 and s2 != s1
        assert s1.read_bytes() == old_bytes  # old snapshot untouched
        # legacy mutable path preserved, not overwritten
        legacy = tmp_path / "_gen_worker.py"
        assert _sha(legacy) == sha1  # first-run writer wrote v1; still v1
        assert (tmp_path / "worker_sources" / f"{sha1}.py").is_file()

    def test_legacy_worker_with_different_content_is_preserved_not_replaced(
            self, tmp_path, monkeypatch):
        legacy = tmp_path / "_gen_worker.py"
        legacy.write_text("# legacy implementation\n")
        legacy_sha = _sha(legacy)
        monkeypatch.setattr(A, "GEN_WORKER", A.GEN_WORKER + "\n# upgraded\n")
        snap, new_sha = A.snapshot_worker_source(tmp_path)
        assert _sha(legacy) == legacy_sha  # untouched
        preserved = tmp_path / "worker_sources" / f"{legacy_sha}.py"
        assert preserved.is_file() and _sha(preserved) == legacy_sha

    def test_symlink_snapshot_slot_refused(self, tmp_path):
        src_dir = tmp_path / "worker_sources"
        src_dir.mkdir()
        target = tmp_path / "evil.py"
        target.write_text("evil")
        want = hashlib.sha256(A.GEN_WORKER.encode()).hexdigest()
        (src_dir / f"{want}.py").symlink_to(target)
        with pytest.raises(RuntimeError, match="SYMLINK"):
            A.snapshot_worker_source(tmp_path)


class TestAttemptReceipts:
    def test_write_once_receipts_refuse_duplicates(self, tmp_path):
        p = tmp_path / "r.json"
        A.write_provenance_receipt(p, {"a": 1})
        with pytest.raises(OSError):  # O_EXCL
            A.write_provenance_receipt(p, {"a": 2})
        assert json.loads(p.read_text())["a"] == 1

    def test_attempt_paths_isolate_per_candidate(self, tmp_path):
        p1 = A.attempt_receipt_path(tmp_path, "wsb_000_r0_s1", "att1", "launched")
        p2 = A.attempt_receipt_path(tmp_path, "wsb_000_r0_s1", "att2", "launched")
        p3 = A.attempt_receipt_path(tmp_path, "wsb_001_r0_s2", "att1", "launched")
        assert len({p1, p2, p3}) == 3
        assert p1.parent.name == "wsb_000_r0_s1"


class TestProvenanceVerifier:
    def make_run(self, tmp_path, legacy=False, forge=None, crash=None):
        runs = tmp_path / "run"
        (runs / "provenance" / "driver_sessions").mkdir(parents=True)
        snap, wsha = A.snapshot_worker_source(runs)
        dsha = "d" * 64
        # driver session receipt (runtime identity evidence)
        A.write_provenance_receipt(
            runs / "provenance" / "driver_sessions" / f"{SESSION_ID}.json",
            {"session_id": SESSION_ID, "driver_source_sha256": dsha,
             "worker_source_sha256": wsha,
             "runtime": {"python": "3.12.3", "torch": "test"}})
        rows = []
        for i, (cid, status) in enumerate(
                [("wsb_000_r0_s1", "complete"), ("wsb_000_r1_s2", "failed")]):
            rec = {"id": cid, "status": status, "seed": 1 + i,
                   "prompt_index": 0, "candidate_index": i, "wall_s": 1.0}
            if not legacy:
                aid = uuid.uuid4().hex
                A.write_provenance_receipt(
                    A.attempt_receipt_path(runs, cid, aid, "launched"),
                    {"attempt_id": aid, "candidate_id": cid, "session_id": SESSION_ID,
                     "driver_source_sha256": dsha, "worker_source_sha256": wsha,
                     "seed": 1 + i, "prompt_index": 0, "candidate_index": i})
                if crash != cid:
                    A.write_provenance_receipt(
                        A.attempt_receipt_path(runs, cid, aid, "result"),
                        {"attempt_id": aid, "candidate_id": cid,
                         "status": status, "session_id": SESSION_ID,
                         "worker_source_sha256": wsha,
                         "driver_source_sha256": dsha,
                         "seed": 1 + i, "prompt_index": 0, "candidate_index": i})
                if forge == cid:
                    # forged journal attribution: claim a different worker sha
                    rec["worker_source_sha256"] = "f" * 64
                    rec["attempt_id"] = aid
                    rec["driver_source_sha256"] = dsha
                    rec["session_id"] = SESSION_ID
                elif not legacy:
                    rec.update({"attempt_id": aid,
                                "worker_source_sha256": wsha,
                                "driver_source_sha256": dsha,
                                "session_id": SESSION_ID})
            rows.append(rec)
        (runs / "generation_manifest.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
        return runs

    def _verify(self, runs):
        import subprocess
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_provenance.py"),
             "--runs", str(runs)], capture_output=True, text=True)

    def test_clean_run_verifies(self, tmp_path):
        r = self._verify(self.make_run(tmp_path))
        assert r.returncode == 0, r.stderr
        assert "PROVENANCE_VERIFIED\": 2" in r.stdout

    def test_legacy_run_marked_incomplete_not_violation(self, tmp_path):
        runs = self.make_run(tmp_path, legacy=True)
        lw = runs / "_gen_worker.py"
        lw.chmod(0o644)
        lw.write_text(A.GEN_WORKER)  # run-level source
        (runs / "run_config.json").write_text(json.dumps(
            {"generator_worker_sha256": _sha(runs / "_gen_worker.py")}))
        r = self._verify(runs)
        assert r.returncode == 0
        assert "LEGACY_PROVENANCE_INCOMPLETE\": 2" in r.stdout

    def test_legacy_run_with_mismatched_worker_is_flagged(self, tmp_path):
        runs = self.make_run(tmp_path, legacy=True)
        lw = runs / "_gen_worker.py"
        lw.chmod(0o644)
        lw.write_text("# some other old worker\n")
        (runs / "run_config.json").write_text(json.dumps(
            {"generator_worker_sha256": "0" * 64}))
        r = self._verify(runs)
        assert r.returncode == 0  # still not a VIOLATION (honest UNKNOWN)
        assert '"LEGACY_PROVENANCE_INCOMPLETE": 2' in r.stdout

    def test_forged_worker_sha_in_journal_is_violation(self, tmp_path):
        r = self._verify(self.make_run(tmp_path, forge="wsb_000_r0_s1"))
        assert r.returncode == 1
        assert "worker_source_sha256 disagrees across receipts/journal" in r.stderr

    def test_crash_before_result_receipt_is_flagged(self, tmp_path):
        r = self._verify(self.make_run(tmp_path, crash="wsb_000_r1_s2"))
        assert r.returncode == 1
        assert "result receipt missing" in r.stderr

    def test_duplicate_attempt_ids_are_violation(self, tmp_path):
        runs = self.make_run(tmp_path)
        # re-append an existing record -> duplicate attempt id in journal
        jm = runs / "generation_manifest.jsonl"
        lines = jm.read_text().splitlines()
        jm.write_text("\n".join(lines + [lines[0]]) + "\n")
        r = self._verify(runs)
        assert r.returncode == 1
        assert "duplicate attempt_id" in r.stderr

    def test_missing_snapshot_is_violation(self, tmp_path):
        runs = self.make_run(tmp_path)
        for f in (runs / "worker_sources").glob("*.py"):
            f.unlink()
        r = self._verify(runs)
        assert r.returncode == 1
        assert "worker snapshot missing" in r.stderr


class TestStableVsImplementationIdentity:
    """Stable experiment identity is NOT implementation provenance; upgraded
    source never rewrites historical attribution (journal append-only)."""

    def test_journal_records_carry_provenance_fields(self):
        src = (REPO / "scripts" / "run_wsb_torch.py").read_text()
        for field in ('"attempt_id": attempt_id',
                      '"worker_source_sha256": worker_sha',
                      '"driver_source_sha256": driver_sha',
                      '"session_id": session_id'):
            assert field in src

    def test_worker_execution_uses_snapshot_not_mutable_path(self):
        src = (REPO / "scripts" / "run_wsb_torch.py").read_text()
        assert "snapshot_worker_source(args.runs)" in src
        assert 'args.runs / "_gen_worker.py"\n    worker_path.write_text' not in src

    def test_historical_records_never_rewritten(self):
        """verify_provenance only READS the journal; nothing in the tooling
        rewrites historical records with new shas."""
        import ast
        src = (REPO / "scripts" / "verify_provenance.py").read_text()
        tree = ast.parse(src)
        forbidden = {"write_text", "unlink", "chmod", "remove", "link",
                     "rename", "mkdir", "touch"}
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                if name:
                    calls.add(name)
        used = calls & forbidden
        assert not used, f"verifier mutates the run tree: {used}"
        assert '"rb"' in src or "open(p" in src  # hashes via read-only opens


class TestC21FullChainNegatives:
    """C2.1 P0-C: the mission's 20-case negative-control list — the cases not
    already covered above, each driving verify_provenance to VIOLATION (or
    honest LEGACY/UNKNOWN where history is genuinely unattributable)."""

    SESSION_ID = "c0ffee" * 5

    def _run(self, runs):
        import subprocess
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_provenance.py"),
             "--runs", str(runs)], capture_output=True, text=True)

    def base_run(self, tmp_path):
        return TestProvenanceVerifier().make_run(tmp_path)

    def _journal(self, runs):
        return [json.loads(l) for l in
                (runs / "generation_manifest.jsonl").read_text().splitlines() if l.strip()]

    def _write_journal(self, runs, rows):
        (runs / "generation_manifest.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))

    def test_missing_driver_session_receipt(self, tmp_path):
        runs = self.base_run(tmp_path)
        (runs / "provenance" / "driver_sessions" / f"{self.SESSION_ID}.json").chmod(0o644)
        (runs / "provenance" / "driver_sessions" / f"{self.SESSION_ID}.json").unlink()
        r = self._run(runs)
        assert r.returncode == 1
        assert "driver session" in r.stderr and "missing" in r.stderr

    def test_forged_session_id_in_journal(self, tmp_path):
        runs = self.base_run(tmp_path)
        rows = self._journal(runs)
        rows[0]["session_id"] = "f" * 32
        self._write_journal(runs, rows)
        r = self._run(runs)
        assert r.returncode == 1
        assert "session_id disagrees" in r.stderr or "driver session" in r.stderr

    def test_missing_attempt_id_with_new_format_markers_is_violation(self, tmp_path):
        runs = self.base_run(tmp_path)
        rows = self._journal(runs)
        del rows[0]["attempt_id"]  # but keeps worker/driver sha + session
        self._write_journal(runs, rows)
        r = self._run(runs)
        assert r.returncode == 1
        assert "missing attempt_id" in r.stderr and "not legacy" in r.stderr

    def test_missing_attempt_id_with_receipts_on_disk_is_violation(self, tmp_path):
        runs = self.base_run(tmp_path)
        rows = self._journal(runs)
        for k in ("attempt_id", "worker_source_sha256", "driver_source_sha256",
                  "session_id"):
            rows[0].pop(k, None)
        self._write_journal(runs, rows)  # receipts for this candidate exist
        r = self._run(runs)
        assert r.returncode == 1
        assert "receipts exist on disk" in r.stderr

    def test_result_attempt_id_mismatch(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        result_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.result.json"
        d = json.loads(result_p.read_text())
        result_p.chmod(0o644)
        d["attempt_id"] = "a" * 32
        result_p.write_text(json.dumps(d))
        r = self._run(runs)
        assert r.returncode == 1 and "result attempt_id" in r.stderr

    def test_result_candidate_id_mismatch(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        result_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.result.json"
        d = json.loads(result_p.read_text())
        result_p.chmod(0o644)
        d["candidate_id"] = "wsb_999_r0_s1"
        result_p.write_text(json.dumps(d))
        r = self._run(runs)
        assert r.returncode == 1 and "result candidate_id" in r.stderr

    def test_result_worker_sha_mismatch(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        result_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.result.json"
        d = json.loads(result_p.read_text())
        result_p.chmod(0o644)
        d["worker_source_sha256"] = "b" * 64
        result_p.write_text(json.dumps(d))
        r = self._run(runs)
        assert r.returncode == 1 and "worker_source_sha256 disagrees" in r.stderr

    def test_result_driver_sha_mismatch(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        result_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.result.json"
        d = json.loads(result_p.read_text())
        result_p.chmod(0o644)
        d["driver_source_sha256"] = "c" * 64
        result_p.write_text(json.dumps(d))
        r = self._run(runs)
        assert r.returncode == 1 and "driver_source_sha256 disagrees" in r.stderr

    @pytest.mark.parametrize("field,bad", [
        ("seed", 424242), ("prompt_index", 9), ("candidate_index", 7)])
    def test_coordinate_seed_mismatches(self, tmp_path, field, bad):
        runs = self.base_run(tmp_path)
        rows = self._journal(runs)
        rows[0][field] = bad
        self._write_journal(runs, rows)
        r = self._run(runs)
        assert r.returncode == 1 and field in r.stderr

    def test_status_flip_complete_vs_failed(self, tmp_path):
        runs = self.base_run(tmp_path)
        rows = self._journal(runs)
        rows[0]["status"] = "failed"  # journal says failed, receipt says complete
        self._write_journal(runs, rows)
        r = self._run(runs)
        assert r.returncode == 1 and "status" in r.stderr

    def test_corrupt_result_json(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        result_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.result.json"
        result_p.chmod(0o644)
        result_p.write_text('{"attempt_id": "trunc')  # interrupted write
        r = self._run(runs)
        assert r.returncode == 1 and "corrupt JSON" in r.stderr

    def test_symlinked_receipt_refused(self, tmp_path):
        runs = self.base_run(tmp_path)
        rec0 = self._journal(runs)[0]
        launched_p = runs / "provenance" / rec0["id"] / f"{rec0['attempt_id']}.launched.json"
        backup = launched_p.read_text()
        launched_p.chmod(0o644)
        launched_p.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text(backup)
        launched_p.symlink_to(outside)
        r = self._run(runs)
        assert r.returncode == 1 and "symlink" in r.stderr

    def test_crash_after_artifact_commit_orphan_complete(self, tmp_path):
        """Result receipt says complete, journal append never happened ->
        journal undercounts -> VIOLATION (crash-after-commit detected)."""
        runs = self.base_run(tmp_path)
        aid = uuid.uuid4().hex
        cid = "wsb_005_r0_s7005"
        A.write_provenance_receipt(
            A.attempt_receipt_path(runs, cid, aid, "launched"),
            {"attempt_id": aid, "candidate_id": cid,
             "session_id": self.SESSION_ID,
             "driver_source_sha256": "d" * 64,
             "worker_source_sha256": "w" * 64,
             "seed": 1, "prompt_index": 5, "candidate_index": 0})
        A.write_provenance_receipt(
            A.attempt_receipt_path(runs, cid, aid, "result"),
            {"attempt_id": aid, "candidate_id": cid, "status": "complete",
             "session_id": self.SESSION_ID,
             "worker_source_sha256": "w" * 64,
             "driver_source_sha256": "d" * 64,
             "seed": 1, "prompt_index": 5, "candidate_index": 0})
        r = self._run(runs)
        assert r.returncode == 1
        assert "orphan COMPLETE" in r.stderr

    def test_crash_before_journal_launched_only_orphan_reported_not_fatal(
            self, tmp_path):
        """Launched-but-no-result, journal record absent: honest crash
        forensics — reported in summary, exit still 0."""
        runs = self.base_run(tmp_path)
        aid = uuid.uuid4().hex
        cid = "wsb_006_r0_s7006"
        A.write_provenance_receipt(
            A.attempt_receipt_path(runs, cid, aid, "launched"),
            {"attempt_id": aid, "candidate_id": cid,
             "session_id": self.SESSION_ID,
             "driver_source_sha256": "d" * 64,
             "worker_source_sha256": "w" * 64,
             "seed": 1, "prompt_index": 6, "candidate_index": 0})
        r = self._run(runs)
        assert r.returncode == 0
        assert '"orphan_launched_only_attempts": 1' in r.stdout

    def test_session_runtime_absent_is_violation(self, tmp_path):
        runs = self.base_run(tmp_path)
        sp = runs / "provenance" / "driver_sessions" / f"{self.SESSION_ID}.json"
        d = json.loads(sp.read_text())
        sp.chmod(0o644)
        d["runtime"] = {}
        sp.write_text(json.dumps(d))
        r = self._run(runs)
        assert r.returncode == 1 and "runtime identity absent" in r.stderr
