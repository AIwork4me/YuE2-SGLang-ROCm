"""mission_chain.py stage-gate regression tests (C2/C3/C4) — CPU only.

These prove the chain cannot: launch a nonexistent old-image launcher path,
advance Arm B acceptance without real evidence, accept a scoring run that
exited 0 without a complete summary, or run two chain instances at once.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/campaign_ops"))
import mission_chain as M  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_machine_paths(tmp_path, monkeypatch):
    """Chain globals point at real machine paths (/data/yue2, ...); tests must
    not read or create them (CI has neither the dirs nor permissions).

    Isolation is done TWO ways, on purpose:
      * module attributes (WS/RUNS/STATE/LOG) -> tmp_path
      * the gpu_lock default-path ENVIRONMENT (YUE2_WORKSPACE/YUE2_GPU_LOCK)
        is scrubbed and pointed at tmp_path, because gpu_lock resolves its
        default lazily at call time. The original CI failure (PR #13 run
        44421080608: PermissionError '/data' in TestScoreGate) happened
        exactly because score() consulted gpu_lock's process-global default
        instead of an injected lock path.
    """
    monkeypatch.setattr(M, "WS", tmp_path)
    monkeypatch.setattr(M, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(M, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(M, "LOG", tmp_path / "logs" / "mission_chain.log")
    monkeypatch.setenv("YUE2_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("YUE2_GPU_LOCK", str(tmp_path / "gpu.lock"))


@pytest.fixture(autouse=True)
def _release_chain_lock():
    """Any chain lock fd acquired by a main()-running test must not leak into
    the next test (same-process flock would false-conflict)."""
    yield
    import fcntl
    if M._chain_lock_fd is not None:
        try:
            fcntl.flock(M._chain_lock_fd, fcntl.LOCK_UN)
            os.close(M._chain_lock_fd)
        except OSError:
            pass
        M._chain_lock_fd = None


# ---------------------------------------------------------------- C2
class TestLauncherPaths:
    def test_armA_launcher_is_repo_script_and_exists(self):
        assert M.LAUNCHER_A == REPO / "scripts/campaign_ops/run_armA_campaign.sh"
        assert M.LAUNCHER_A.is_file(), f"launcher missing: {M.LAUNCHER_A}"

    def test_no_stale_old_image_launcher_reference(self):
        src = (REPO / "scripts/campaign_ops/mission_chain.py").read_text()
        assert '"/data/yue2/run_armA_campaign.sh"' not in src
        assert "/data/yue2/run_armA_campaign.sh" not in src.replace(
            str(M.LAUNCHER_A), "")  # no occurrence outside the constant

    def test_armA_launcher_guards_env_and_single_instance(self):
        src = (REPO / "scripts/campaign_ops/run_armA_campaign.sh").read_text()
        assert "flock -n 9" in src
        assert "driver_alive.py" in src
        assert "already alive" in src or "already running" in src


# ---------------------------------------------------------------- C3
class TestChainSingleInstance:
    def test_second_lock_acquire_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "WS", tmp_path)
        (tmp_path).mkdir(parents=True, exist_ok=True)
        assert M.acquire_chain_lock() is True
        try:
            assert M.acquire_chain_lock() is False
        finally:
            import fcntl
            if M._chain_lock_fd is not None:
                fcntl.flock(M._chain_lock_fd, fcntl.LOCK_UN)
                os.close(M._chain_lock_fd)
                M._chain_lock_fd = None

    def test_launcher_missing_records_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "LAUNCHER_A", tmp_path / "nope.sh")
        monkeypatch.setattr(M, "STATE", tmp_path / "state.json")
        monkeypatch.setattr(M, "sleep",
                            lambda s: (_ for _ in ()).throw(KeyboardInterrupt))
        monkeypatch.setattr(M, "journal_complete", lambda rd: 5)
        monkeypatch.setattr(M, "armA_driver_alive", lambda rd: (False, []))
        calls = {}
        monkeypatch.setattr(M, "launch_detached",
                            lambda argv, err: calls.setdefault("argv", argv) or True)
        with pytest.raises(KeyboardInterrupt):
            M.main()
        s = json.loads((tmp_path / "state.json").read_text())
        assert s["blocked_reason"].startswith("launcher missing")

    def test_armA_campaign_launches_repo_launcher(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "LAUNCHER_A", tmp_path / "ok.sh")
        (tmp_path / "ok.sh").write_text("#!/bin/sh\nexit 0\n")
        monkeypatch.setattr(M, "STATE", tmp_path / "state.json")
        monkeypatch.setattr(M, "sleep", lambda s: (_ for _ in ()).throw(
            KeyboardInterrupt))
        monkeypatch.setattr(M, "journal_complete", lambda rd: 5)
        monkeypatch.setattr(M, "armA_driver_alive", lambda rd: (False, []))
        launched = {}
        monkeypatch.setattr(M, "launch_detached",
                            lambda argv, err: launched.setdefault("argv", argv) or True)
        with pytest.raises(KeyboardInterrupt):
            M.main()
        assert launched["argv"][-1] == str(tmp_path / "ok.sh")
        assert launched["argv"][0] == "setsid"


# ---------------------------------------------------------------- C4
class TestAuditGate:
    def _fake_run(self, verdict, rc=0):
        class R:
            returncode = rc
            stdout = f'"verdict": "{verdict}"'
            stderr = ""
        return R()

    def test_audit_requires_audit_json_full_verdict(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        monkeypatch.setattr(M.subprocess, "run",
                            lambda *a, **k: self._fake_run("FULL"))
        (run_dir / "audit.json").write_text(json.dumps({"verdict": "FULL"}))
        assert M.audit(run_dir) is True

    def test_audit_rejects_missing_audit_json(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        monkeypatch.setattr(M.subprocess, "run",
                            lambda *a, **k: self._fake_run("FULL"))
        assert M.audit(run_dir) is False

    def test_audit_rejects_rc0_with_partial_verdict(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        monkeypatch.setattr(M.subprocess, "run",
                            lambda *a, **k: self._fake_run("FULL"))
        (run_dir / "audit.json").write_text(json.dumps({"verdict": "PARTIAL"}))
        assert M.audit(run_dir) is False

    def test_audit_rejects_nonzero_rc_even_with_full_json(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        monkeypatch.setattr(M.subprocess, "run",
                            lambda *a, **k: self._fake_run("FULL", rc=1))
        (run_dir / "audit.json").write_text(json.dumps({"verdict": "FULL"}))
        assert M.audit(run_dir) is False


class TestScoreGate:
    def _run_scoring(self, tmp_path, monkeypatch, rc, complete):
        """Fake evaluator: writes summary.json itself, returns rc (realistic)."""
        run_dir = tmp_path / "run"
        out = run_dir / "out"
        out.mkdir(parents=True)

        class R:
            returncode = rc
            stdout = ""
            stderr = ""

        def fake_run(*a, **k):
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps({"complete": complete}))
            return R()

        monkeypatch.setattr(M.subprocess, "run", fake_run)
        monkeypatch.setattr(M, "WS", tmp_path)
        return M.score(run_dir, "per,songbench", "out", None, "logx")

    def test_rc0_complete_summary_passes(self, tmp_path, monkeypatch):
        assert self._run_scoring(tmp_path, monkeypatch, rc=0, complete=True) is True

    def test_rc0_incomplete_summary_fails(self, tmp_path, monkeypatch):
        assert self._run_scoring(tmp_path, monkeypatch, rc=0, complete=False) is False

    def test_rc0_missing_summary_fails(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; (run_dir / "out2").mkdir(parents=True)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: R())
        monkeypatch.setattr(M, "WS", tmp_path)
        assert M.score(run_dir, "per,songbench", "out2", None, "logx") is False

    def test_rc1_complete_summary_fails(self, tmp_path, monkeypatch):
        assert self._run_scoring(tmp_path, monkeypatch, rc=1, complete=True) is False

    def test_already_complete_summary_skips_rerun(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; (run_dir / "out3").mkdir(parents=True)
        (run_dir / "out3" / "summary.json").write_text(
            json.dumps({"complete": True}))
        called = []
        monkeypatch.setattr(M.subprocess, "run",
                            lambda *a, **k: called.append(1) or None)
        monkeypatch.setattr(M, "WS", tmp_path)
        assert M.score(run_dir, "per,songbench", "out3", None, "logx") is True
        assert called == []

    def test_partial_output_moved_aside_not_deleted(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; out = run_dir / "out4"
        out.mkdir(parents=True)
        (out / "summary.json").write_text(json.dumps({"complete": False}))
        (out / "evidence.txt").write_text("keep me")

        class R:
            returncode = 1
            stdout = ""
            stderr = ""
        monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: R())
        monkeypatch.setattr(M, "WS", tmp_path)
        assert M.score(run_dir, "per,songbench", "out4", None, "logx") is False
        asides = list(run_dir.glob("out4_partial_*"))
        assert len(asides) == 1
        assert (asides[0] / "evidence.txt").read_text() == "keep me"

    def test_lock_unavailable_fails_gate_without_running_evaluator(
            self, tmp_path, monkeypatch):
        """C4 + M1.1: if the GPU ownership lock cannot be acquired (bounded
        wait exhausted), the score gate must FAIL and the evaluator must not
        run — a lock failure can never produce a successful score gate."""
        import subprocess as sp
        import sys as _sys
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        holder = sp.Popen(
            [_sys.executable, "-c",
             "import fcntl,sys,time\n"
             "fd=open(sys.argv[1],'w')\n"
             "fcntl.flock(fd,fcntl.LOCK_EX)\n"
             "print('held',flush=True)\n"
             "time.sleep(30)\n",
             str(tmp_path / "gpu.lock")],
            stdout=sp.PIPE)
        try:
            assert holder.stdout.readline().strip() == b"held"
            called = []

            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            monkeypatch.setattr(
                M.subprocess, "run",
                lambda *a, **k: called.append(1) or R())
            monkeypatch.setattr(M, "WS", tmp_path)
            monkeypatch.setenv("YUE2_GPU_LOCK_WAIT_S", "0.3")
            assert M.score(run_dir, "per,songbench", "outx", None,
                           "lockx") is False
            assert called == []  # evaluator never launched
        finally:
            holder.kill()
            holder.wait(timeout=10)

    def test_score_lock_derived_from_chain_workspace_not_global_default(
            self, tmp_path, monkeypatch):
        """M1.1 root cause regression: score() must lock WS/gpu.lock (the
        chain's injected workspace), never gpu_lock's process-global default
        (which pointed at /data/yue2 on CI runners without /data)."""
        import sys as _sys
        sys.path.insert(0, str(REPO / "scripts"))
        import gpu_lock as G
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        seen = {}

        real_ownership = G.gpu_ownership

        def spy(who, **kw):
            seen["lock_path"] = kw.get("lock_path")
            return real_ownership(who, **kw)

        monkeypatch.setattr(M, "gpu_ownership", spy)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: R())
        monkeypatch.setattr(M, "WS", tmp_path)
        out = run_dir / "outy"
        out.mkdir()
        (out / "summary.json").write_text(json.dumps({"complete": False}))
        M.score(run_dir, "per,songbench", "outy", None, "logz")
        assert seen["lock_path"] == tmp_path / "gpu.lock"
        # and the global default was never touched (no /data access): the
        # injected tmp lock file exists afterwards
        assert (tmp_path / "gpu.lock").exists()


class TestArmBLauncherAndAcceptance:
    """Wiring checks for the real Arm B acceptance + campaign launcher."""

    def test_acceptance_script_exists_and_is_real(self):
        p = REPO / "scripts/campaign_ops/armB_acceptance.sh"
        assert p.is_file()
        src = p.read_text()
        for needle in ("gpu_lock.py", "serve_yue2_gfx1100.sh", "server_identity.py",
                       "/health", "ARMB_ACCEPTANCE_PASS"):
            assert needle in src, f"acceptance must exercise {needle}"

    def test_acceptance_uses_actual_identity_cli(self):
        src = (REPO / "scripts/campaign_ops/armB_acceptance.sh").read_text()
        assert "capture --run-state" in src
        # the old wrong flag must not linger (--out-dir of the acceptance
        # request helper is a different, valid flag)
        stripped = src.replace("--out-dir", "")
        assert " --out " not in stripped and '--out "' not in stripped \
            and "--out=" not in stripped

    def test_armB_launcher_exists_and_guards(self):
        p = REPO / "scripts/campaign_ops/run_armB_campaign.sh"
        assert p.is_file()
        src = p.read_text()
        for needle in ("flock -n 9", "driver_alive.py", "gpu_lock.py",
                       "server_identity.py", "run_wsb.py", "stop_server"):
            assert needle in src, f"launcher must include {needle}"

    def test_armB_launcher_resumes_existing_run_id(self):
        src = (REPO / "scripts/campaign_ops/run_armB_campaign.sh").read_text()
        assert "run_config.json" in src and "run_id" in src


class TestArmBAcceptanceGate:
    def test_no_command_configured_blocks(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YUE2_ARMB_ACCEPTANCE_CMD", raising=False)
        monkeypatch.setattr(M, "ARMB_ACCEPTANCE", tmp_path / "missing.sh")
        ok, why = M.run_armb_acceptance()
        assert ok is False
        assert "BLOCKED" in why and "refusing to advance" in why

    def test_passing_command_advances(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YUE2_ARMB_ACCEPTANCE_CMD", "exit 0")
        monkeypatch.setattr(M, "WS", tmp_path)
        ok, _ = M.run_armb_acceptance()
        assert ok is True

    def test_failing_command_blocks(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YUE2_ARMB_ACCEPTANCE_CMD", "exit 3")
        monkeypatch.setattr(M, "WS", tmp_path)
        ok, why = M.run_armb_acceptance()
        assert ok is False and "rc=3" in why

    def test_repo_script_used_when_present(self, tmp_path, monkeypatch):
        sh = tmp_path / "armB_acceptance.sh"
        sh.write_text("#!/bin/sh\nexit 0\n")
        monkeypatch.delenv("YUE2_ARMB_ACCEPTANCE_CMD", raising=False)
        monkeypatch.setattr(M, "ARMB_ACCEPTANCE", sh)
        monkeypatch.setattr(M, "WS", tmp_path)
        ok, _ = M.run_armb_acceptance()
        assert ok is True


# ------------------------------------------------- RC2 review regressions
class TestJournalCompleteCountsResumed:
    """RC2 R1-D1: a verified candidate resumed after journal-tail loss must
    still be counted by the chain's advancement gate."""

    def _write(self, run_dir, rows):
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "generation_manifest.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))

    def test_complete_and_complete_resumed_both_count(self, tmp_path):
        rd = tmp_path / "run"
        self._write(rd, [
            {"id": "a", "status": "complete"},
            {"id": "b", "status": "complete(resumed)"},
            {"id": "c", "status": "complete", "resumed": True},
            {"id": "d", "status": "generation_failed"},
            {"id": "e", "status": "finalize_failed"},
        ])
        assert M.journal_complete(rd) == 3

    def test_torn_tail_row_ignored(self, tmp_path):
        rd = tmp_path / "run"
        rd.mkdir(parents=True)
        (rd / "generation_manifest.jsonl").write_text(
            json.dumps({"id": "a", "status": "complete"}) + "\n"
            '{"id": "b", "status": "comp')  # torn tail
        assert M.journal_complete(rd) == 1

    def test_missing_manifest_is_zero(self, tmp_path):
        assert M.journal_complete(tmp_path / "none") == 0


class TestScoreBoundedExecution:
    def test_scoring_timeout_fails_gate(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir(parents=True)
        seen = {}

        def hang(*a, **k):
            seen["timeout"] = k.get("timeout")
            raise M.subprocess.TimeoutExpired(cmd="wsb_eval", timeout=7)

        monkeypatch.setattr(M.subprocess, "run", hang)
        monkeypatch.setattr(M, "WS", tmp_path)
        assert M.score(run_dir, "per,songbench", "out", None, "logx") is False
        # the evaluator invocation itself must carry a bounded timeout —
        # an unbounded subprocess.run is the mutation this pins
        assert seen.get("timeout"), "score() launched the evaluator WITHOUT a timeout"

    def test_audit_timeout_fails_not_crash(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir(parents=True)

        def hang(*a, **k):
            raise M.subprocess.TimeoutExpired(cmd="verify", timeout=7200)

        monkeypatch.setattr(M.subprocess, "run", hang)
        assert M.audit(run_dir) is False  # previously: uncaught -> chain death

    def test_acceptance_timeout_fails_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "ARMB_ACCEPTANCE", tmp_path / "acc.sh")
        (tmp_path / "acc.sh").write_text("#!/bin/sh\nexit 0\n")

        def hang(*a, **k):
            raise M.subprocess.TimeoutExpired(cmd="acc", timeout=7200)

        monkeypatch.setattr(M.subprocess, "run", hang)
        ok, why = M.run_armb_acceptance()
        assert ok is False and "timed out" in why


class TestScoreStageRetryBounds:
    def test_attempts_escalate_to_blocked(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir(parents=True)
        state = {"stage": "x", "history": [],
                 "score_attempts": {"logx": 8}}
        monkeypatch.setenv("YUE2_SCORE_MAX_ATTEMPTS", "8")
        launched = []
        monkeypatch.setattr(M, "score",
                            lambda *a, **k: launched.append(1) or False)
        assert M.score_stage(state, run_dir, "m", "o", None, "logx") is False
        assert launched == []  # evaluator NOT re-armed after the cap
        assert "YUE2_SCORE_MAX_ATTEMPTS" in state["blocked_reason"]

    def test_success_resets_counter(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir(parents=True)
        state = {"stage": "x", "history": [], "score_attempts": {"logx": 3}}
        monkeypatch.setattr(M, "score", lambda *a, **k: True)
        assert M.score_stage(state, run_dir, "m", "o", None, "logx") is True
        assert state["score_attempts"]["logx"] == 0

    def test_failure_increments_counter(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"; run_dir.mkdir(parents=True)
        state = {"stage": "x", "history": []}
        monkeypatch.setattr(M, "score", lambda *a, **k: False)
        assert M.score_stage(state, run_dir, "m", "o", None, "logx") is False
        assert state["score_attempts"]["logx"] == 1
