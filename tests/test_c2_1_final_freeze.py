"""PR #12 final-freeze regressions: synthetic data and CPU only.

Covers genuine legacy-prefix to new-format retry, stripped-new record
negative controls, result-only orphans, private staging and cleanup failures.
Never touches a running GPU campaign or downloads WildSongBench assets.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_per_reference_package as H
import run_wsb_torch as A

from test_c2_provenance import TestProvenanceVerifier as _ProvenanceFixture
from test_c2_audio_identity import make_run


def _rows(run):
    return [json.loads(line) for line in
            (run / "generation_manifest.jsonl").read_text().splitlines()
            if line.strip()]


def _put_rows(run, rows):
    (run / "generation_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows))


def _legacy_event(row):
    """The original pre-C2 journal schema, retaining candidate identity."""
    return {k: row[k] for k in
            ("id", "seed", "prompt_index", "candidate_index", "wall_s", "status")}


def _run_verifier(run):
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "verify_provenance.py"),
         "--runs", str(run)], capture_output=True, text=True)


def _run_packager(run, out):
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
         "--run", str(run), "--out", str(out), "--rights-confirmed"],
        capture_output=True, text=True)


class TestLegacyMixedHistory:
    def test_legacy_failed_then_new_format_retry_same_candidate_passes(self, tmp_path):
        run = _ProvenanceFixture().make_run(tmp_path)
        events = _rows(run)
        old = _legacy_event(events[0])
        old["status"] = "failed"
        _put_rows(run, [old] + events)
        result = _run_verifier(run)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout[:result.stdout.find("\nPASS:")])
        assert data["verdicts"]["LEGACY_PROVENANCE_INCOMPLETE"] == 1
        assert data["verdicts"]["PROVENANCE_VERIFIED"] == 2
        assert data["legacy_mixed_history_records"] == 1
        # Legacy remains UNKNOWN; newly generated attempt is verified.
        assert data["legacy_prefix_boundary"] == 1

    def test_unmarked_legacy_looking_event_after_cutover_is_violation(self, tmp_path):
        run = _ProvenanceFixture().make_run(tmp_path)
        events = _rows(run)
        _put_rows(run, events + [_legacy_event(events[0])])
        result = _run_verifier(run)
        assert result.returncode == 1
        assert "after new-format cutover" in result.stderr

    def test_stripped_new_event_not_downgraded_even_with_later_retry(self, tmp_path):
        run = _ProvenanceFixture().make_run(tmp_path)
        events = _rows(run)
        original = events[0]
        cid = original["id"]
        old_aid = original["attempt_id"]
        new_aid = uuid.uuid4().hex
        # New legitimate retry with its own launched + result receipts.
        attempt_dir = run / "provenance" / cid
        for phase in ("launched", "result"):
            source = attempt_dir / f"{old_aid}.{phase}.json"
            receipt = json.loads(source.read_text())
            receipt["attempt_id"] = new_aid
            A.write_provenance_receipt(
                attempt_dir / f"{new_aid}.{phase}.json", receipt)
        new_event = {**original, "attempt_id": new_aid}
        # Falsify the first NEW journal event by deleting its provenance keys.
        stripped = _legacy_event(original)
        _put_rows(run, [stripped, new_event, events[1]])
        result = _run_verifier(run)
        assert result.returncode == 1
        # The missing old journal link leaves a COMPLETE result orphan.
        assert "orphan COMPLETE" in result.stderr


class TestResultOnlyOrphans:
    @pytest.mark.parametrize("status", ["complete", "failed"])
    def test_unguarded_result_only_without_journal_is_violation(
            self, tmp_path, status):
        run = _ProvenanceFixture().make_run(tmp_path)
        isolated = run / "provenance" / "wsb_190_r1_s9000"
        isolated.mkdir()
        aid = uuid.uuid4().hex
        (isolated / f"{aid}.result.json").write_text(json.dumps(
            {"attempt_id": aid, "candidate_id": isolated.name, "status": status}))
        result = _run_verifier(run)
        assert result.returncode == 1
        assert "result-only orphan receipt" in result.stderr
        data = json.loads(result.stdout[:result.stdout.find("\nFAIL:")] if
                          "\nFAIL:" in result.stdout else result.stdout)
        assert data["orphan_result_only_attempts"] == 1

    def test_launched_only_orphan_is_reported_not_silently_verified(self, tmp_path):
        run = _ProvenanceFixture().make_run(tmp_path)
        isolated = run / "provenance" / "wsb_190_r1_s9000"
        isolated.mkdir()
        aid = uuid.uuid4().hex
        (isolated / f"{aid}.launched.json").write_text(json.dumps(
            {"attempt_id": aid, "candidate_id": isolated.name}))
        result = _run_verifier(run)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout[:result.stdout.find("\nPASS:")])
        assert data["orphan_launched_only_attempts"] == 1
        assert data["orphan_result_only_attempts"] == 0


class TestPrivateAtomicStaging:
    def test_published_directory_remains_private_0700(self, tmp_path):
        run, _ = make_run(tmp_path)
        out = tmp_path / "private-package"
        result = _run_packager(run, out)
        assert result.returncode == 0, result.stderr[-1000:]
        assert out.stat().st_mode & 0o077 == 0
        assert (out / "audio").stat().st_mode & 0o077 == 0
        assert not list(tmp_path.glob("private-package.staging-*"))

    def test_staging_cleanup_failure_is_visible_and_stays_private(
            self, tmp_path, monkeypatch):
        run, _ = make_run(tmp_path)
        out = tmp_path / "private-package"

        def identity_refusal(*args, **kwargs):
            raise H.IdentityError("synthetic candidate identity mismatch")

        def forbidden_cleanup(*args, **kwargs):
            raise PermissionError("synthetic refusal to remove staging")

        monkeypatch.setattr(H, "verify_audio_identity", identity_refusal)
        monkeypatch.setattr(shutil, "rmtree", forbidden_cleanup)
        previous_argv = sys.argv
        sys.argv = ["packager", "--run", str(run),
                    "--out", str(out), "--rights-confirmed"]
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), pytest.raises(SystemExit):
                H.main()
        finally:
            sys.argv = previous_argv
        assert "staging cleanup FAILED" in err.getvalue()
        assert "manual cleanup required" in err.getvalue()
        assert not os.path.lexists(out)
        staged = list(tmp_path.glob("private-package.staging-*"))
        assert len(staged) == 1
        assert staged[0].stat().st_mode & 0o077 == 0
        assert (staged[0] / "audio").stat().st_mode & 0o077 == 0

    def test_audit_write_failure_aborts_and_removes_private_stage(
            self, tmp_path, monkeypatch):
        run, _ = make_run(tmp_path)
        out = tmp_path / "private-package"
        real_dump = json.dump

        def failing_audit(obj, fp, *args, **kwargs):
            if Path(fp.name).name == ".package_audit.json":
                raise OSError(28, "synthetic ENOSPC while writing audit receipt")
            return real_dump(obj, fp, *args, **kwargs)

        monkeypatch.setattr(json, "dump", failing_audit)
        old_argv = sys.argv
        sys.argv = ["packager", "--run", str(run),
                    "--out", str(out), "--rights-confirmed"]
        try:
            with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
                H.main()
        finally:
            sys.argv = old_argv
        assert not os.path.lexists(out)
        assert not list(tmp_path.glob("private-package.staging-*"))
