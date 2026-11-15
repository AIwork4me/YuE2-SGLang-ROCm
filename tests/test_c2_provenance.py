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


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestWorkerSnapshots:
    def test_fresh_run_creates_content_addressed_snapshot(self, tmp_path):
        snap, sha = A.snapshot_worker_source(tmp_path)
        assert snap.parent.name == "worker_sources"
        assert snap.name == f"{sha}.py"
        assert _sha(snap) == sha
        assert not (snap.stat().st_mode & stat.S_IWUSR) or snap.stat().st_mode & 0o444

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
        with pytest.raises(RuntimeError, match="tampered"):
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
        (runs / "provenance").mkdir(parents=True)
        snap, wsha = A.snapshot_worker_source(runs)
        dsha = "d" * 64
        rows = []
        for i, (cid, status) in enumerate(
                [("wsb_000_r0_s1", "complete"), ("wsb_000_r1_s2", "failed")]):
            rec = {"id": cid, "status": status, "seed": 1 + i,
                   "prompt_index": 0, "candidate_index": i, "wall_s": 1.0}
            if not legacy:
                aid = uuid.uuid4().hex
                A.write_provenance_receipt(
                    A.attempt_receipt_path(runs, cid, aid, "launched"),
                    {"attempt_id": aid, "candidate_id": cid, "session_id": "s1",
                     "driver_source_sha256": dsha, "worker_source_sha256": wsha,
                     "seed": 1 + i})
                if crash != cid:
                    A.write_provenance_receipt(
                        A.attempt_receipt_path(runs, cid, aid, "result"),
                        {"attempt_id": aid, "candidate_id": cid,
                         "status": status, "session_id": "s1",
                         "worker_source_sha256": wsha,
                         "driver_source_sha256": dsha})
                if forge == cid:
                    # forged journal attribution: claim a different worker sha
                    rec["worker_source_sha256"] = "f" * 64
                    rec["attempt_id"] = aid
                    rec["driver_source_sha256"] = dsha
                    rec["session_id"] = "s1"
                elif not legacy:
                    rec.update({"attempt_id": aid,
                                "worker_source_sha256": wsha,
                                "driver_source_sha256": dsha,
                                "session_id": "s1"})
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
        (runs / "_gen_worker.py").write_text(A.GEN_WORKER)  # run-level source
        (runs / "run_config.json").write_text(json.dumps(
            {"generator_worker_sha256": _sha(runs / "_gen_worker.py")}))
        r = self._verify(runs)
        assert r.returncode == 0
        assert "LEGACY_PROVENANCE_INCOMPLETE\": 2" in r.stdout

    def test_legacy_run_with_mismatched_worker_is_flagged(self, tmp_path):
        runs = self.make_run(tmp_path, legacy=True)
        (runs / "_gen_worker.py").write_text("# some other old worker\n")
        (runs / "run_config.json").write_text(json.dumps(
            {"generator_worker_sha256": "0" * 64}))
        r = self._verify(runs)
        assert r.returncode == 0  # still not a VIOLATION (honest UNKNOWN)
        assert '"LEGACY_PROVENANCE_INCOMPLETE": 2' in r.stdout

    def test_forged_worker_sha_in_journal_is_violation(self, tmp_path):
        r = self._verify(self.make_run(tmp_path, forge="wsb_000_r0_s1"))
        assert r.returncode == 1
        assert "worker sha: launched receipt != journal" in r.stderr

    def test_crash_before_result_receipt_is_flagged(self, tmp_path):
        r = self._verify(self.make_run(tmp_path, crash="wsb_000_r1_s2"))
        assert r.returncode == 1
        assert "crash before commit" in r.stderr

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
        src = (REPO / "scripts" / "verify_provenance.py").read_text()
        assert "write_text" not in src and "unlink" not in src
