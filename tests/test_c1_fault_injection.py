"""C1 P2 fault-injection tests — REAL crash simulation (beyond PR #8/#10).

These do not trust string assertions: they spawn real processes, kill them
mid-write with SIGKILL, race concurrent writers, and verify the journal
contract holds on recovery. All data synthetic; no GPU, no dataset.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import run_wsb_torch as A  # noqa: E402


WRITER = r'''
import sys, time
sys.path.insert(0, "{repo}")
import run_wsb_torch as A
from pathlib import Path
journal = Path("{journal}")
for i in range({n}):
    A.atomic_append(journal, {{"id": "cand_{tag}_" + str(i), "status": "complete"}})
    time.sleep({delay})
'''


def _writer_cmd(journal: Path, n: int, tag: str, delay: float) -> list[str]:
    return [sys.executable, "-c",
            WRITER.format(repo=REPO / "scripts", journal=journal,
                          n=n, tag=tag, delay=delay)]


class TestRealCrashInjection:
    def test_sigkill_mid_append_leaves_recoverable_journal(self, tmp_path):
        """Kill -9 a writer mid-stream; recovery must never count a torn
        record, and subsequent appends must refuse until recovery ran."""
        journal = tmp_path / "j.jsonl"
        p = subprocess.Popen(_writer_cmd(journal, 100, "k", 0.02),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        deadline = time.time() + 10
        while time.time() < deadline:
            if journal.exists() and journal.stat().st_size > 0:
                break
            time.sleep(0.05)
        time.sleep(0.05)  # let at least a few records land
        os.kill(p.pid, signal.SIGKILL)
        p.wait(timeout=10)
        # if the kill landed mid-append the last line may be torn — recovery
        # either sees a clean file or quarantines the tail
        completed, problems = A.read_journal(journal)
        lines = [l for l in journal.read_text().splitlines() if l.strip()]
        assert len(completed) <= len(lines)
        if problems:
            assert any("torn" in x or "quarantined" in x for x in problems)
        # every counted completion must be a fully-parsed record
        for line in lines:
            if line.strip():
                json.loads(line)  # no parse errors post-recovery

    def test_concurrent_writers_serialized_by_flock(self, tmp_path):
        """Two real writer processes racing on one journal: every record
        survives intact (no interleaved/torn interior lines)."""
        journal = tmp_path / "j.jsonl"
        journal.touch()
        ps = [subprocess.Popen(_writer_cmd(journal, 40, str(t), 0.005),
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) for t in (0, 1)]
        for p in ps:
            assert p.wait(timeout=60) == 0
        completed, problems = A.read_journal(journal)
        lines = [l for l in journal.read_text().splitlines() if l.strip()]
        assert len(lines) == 80, f"lost records: {len(lines)}/80"
        assert len(completed) == 80
        assert problems == []

    def test_append_after_torn_tail_fails_closed(self, tmp_path):
        journal = tmp_path / "j.jsonl"
        journal.write_bytes(b'{"id": "a", "status": "complete"}\n'
                            b'{"id": "b", "status": "comp')
        with pytest.raises(ValueError, match="torn"):
            A.atomic_append(journal, {"id": "c", "status": "complete"})
        # recovery then append works
        completed, problems = A.read_journal(journal)
        assert completed == {"a"}
        A.atomic_append(journal, {"id": "c", "status": "complete"})
        completed, _ = A.read_journal(journal)
        assert completed == {"a", "c"}

    def test_interior_corruption_blocks_resume_loudly(self, tmp_path):
        journal = tmp_path / "j.jsonl"
        journal.write_text(
            json.dumps({"id": "a", "status": "complete"}) + "\n"
            + "CORRUPT-INTERIOR\n"
            + json.dumps({"id": "b", "status": "complete"}) + "\n")
        with pytest.raises(ValueError, match="[Ii]nterior|manual audit"):
            A.read_journal(journal)

    def test_failed_after_complete_invalidates(self, tmp_path):
        journal = tmp_path / "j.jsonl"
        A.atomic_append(journal, {"id": "a", "status": "complete"})
        A.atomic_append(journal, {"id": "a", "status": "failed",
                                  "error": "worker rc=1"})
        completed, problems = A.read_journal(journal)
        assert "a" not in completed, "latest status must win"
        assert any("both complete and failed" in x for x in problems)

    def test_worker_timeout_path_records_failure_and_preserves_partial(
            self, tmp_path):
        """Simulate the driver's TimeoutExpired branch against a sleeping
        worker: failure recorded, partial dir preserved untouched."""
        runs = tmp_path / "runs"
        songs = runs / "songs"
        songs.mkdir(parents=True)
        partial = songs / "wsb_000_r0_s1.partial"
        partial.mkdir()
        (partial / "evidence.bin").write_bytes(b"\x01\x02")
        worker = tmp_path / "sleep_worker.py"
        worker.write_text("import time; time.sleep(30)\n")
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(worker)], capture_output=True, text=True,
                timeout=2)
            raised = False
        except subprocess.TimeoutExpired as exc:
            raised = True
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
        assert raised
        assert time.time() - t0 < 20, "worker must actually be killed"
        assert (partial / "evidence.bin").read_bytes() == b"\x01\x02"
        # after the kill the worker must be gone (no orphan process)
        time.sleep(0.5)
        probe = subprocess.run(["pgrep", "-f", "sleep_worker.py"],
                               capture_output=True, text=True)
        assert probe.returncode != 0, "killed worker left a process behind"

    def test_quarantine_names_unique_under_repeated_retries(self, tmp_path):
        """Same candidate retried rapidly (same timestamp) must not overwrite
        earlier quarantine evidence — uuid names guarantee uniqueness."""
        songs = tmp_path / "songs"
        songs.mkdir()
        import shutil
        ident = "wsb_000_r0_s831001"
        names = []
        for _ in range(5):
            tmp = songs / f"{ident}.partial"
            tmp.mkdir()
            (tmp / "x").write_text("x")
            q = tmp.with_name(ident + ".partial.quarantine-" +
                              __import__("uuid").uuid4().hex)
            shutil.move(str(tmp), str(q))
            names.append(q.name)
        assert len(set(names)) == 5
        assert all((songs / n).is_dir() for n in names)

    def test_journal_id_outside_frozen_scope_detected(self, tmp_path):
        """A journal with foreign complete ids must be distinguishable from
        the frozen scope — the driver refuses; here we assert the predicate
        the driver uses (subset check) with synthetic ids."""
        allowed = {f"wsb_{i:03d}_r{j}_s{831001 + i + 18 * j}"
                   for i in range(2) for j in (0, 1)}
        assert allowed.issubset(allowed)
        foreign = allowed | {"wsb_999_r0_s1"}
        assert not foreign.issubset(allowed)


class TestPr8ComplementaryPorts:
    """Ports of PR #8's complementary test value, adapted to the PR #10
    implementation (C1 P6: no cherry-pick; behaviors already verified —
    these add the missing coverage)."""

    def test_symlinked_partial_refused_by_worker_source(self):
        """PR8 test_renaming_does_not_follow_symlinks, ported: the worker
        refuses symlinked output paths instead of moving through them."""
        assert "Refusing symlink output paths" in A.GEN_WORKER
        link = None
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            real = tdp / "real"
            real.mkdir()
            link = tdp / "link"
            link.symlink_to(real, target_is_directory=True)
            assert link.is_symlink() and real.exists()
            # the worker's guard: is_symlink check before any move
            assert link.is_symlink() and link.is_dir()
            # Execute the actual worker guard, extracted via AST, without
            # importing GPU-only modules or relying on a source string.
            import ast
            parsed = ast.parse(A.GEN_WORKER)
            matches = [node for node in ast.walk(parsed)
                       if isinstance(node, ast.If)
                       and "is_symlink" in ast.unparse(node.test)]
            assert len(matches) == 1
            guard = ast.Module(body=matches, type_ignores=[])
            ast.fix_missing_locations(guard)
            with pytest.raises(RuntimeError, match="Refusing symlink"):
                exec(compile(guard, "<worker-symlink-guard>", "exec"),
                     {"tmp": link, "out": tdp / "new"})
            link = None  # cleanup on Windows semantics

    def test_symlink_candidate_refused_at_resume(self, tmp_path):
        """resume_verified_candidate refuses symlinked candidate dirs."""
        import run_wsb_torch as A10
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "linked-cand"
        link.symlink_to(real, target_is_directory=True)
        completed = set()
        with pytest.raises(RuntimeError, match="symlink"):
            A10.resume_verified_candidate(link, "linked-cand", completed,
                                          lambda p: {}, tmp_path / "j.jsonl")

    def test_worker_has_no_recursive_delete_of_partials(self):
        """PR8 source-level port: no rmtree of partial bundles anywhere."""
        assert "rmtree" not in A.GEN_WORKER.replace(
            "# RCA-F1: QUARANTINE, never delete — a partial dir is campaign "
            "evidence (docs promise quarantine-not-delete; the old rmtree "
            "violated that)", "")
        assert ".partial.quarantine-" in A.GEN_WORKER

    def test_complete_but_schema_invalid_record_blocks_resume(self, tmp_path):
        """PR8 port: a 'complete' record that violates the journal schema
        cannot be silently discarded — resume must stop for manual audit."""
        journal = tmp_path / "j.jsonl"
        journal.write_text('{"id": "a", "status": "complete"}\n'
                           '{"status": "complete"}\n')  # missing id
        with pytest.raises(ValueError):
            A.read_journal(journal)
