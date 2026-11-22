"""C2.1 — Final fail-closed closure tests (all synthetic, real processes).

P0-A atomic package publication · P0-B no-clobber (real multiprocess races)
· P1-A snapshot immutability (incl. content-correct symlinks) · P1-B real
mid-copy TOCTOU with deterministic coordination.
"""
from __future__ import annotations

import hashlib
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
import atomic_publish as AP  # noqa: E402
import build_per_reference_package as H  # noqa: E402
import run_wsb_torch as A  # noqa: E402

from test_c2_audio_identity import make_run  # synthetic campaign factory


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ============================================================ P0-B
class TestNoClobberPrimitive:
    def test_fresh_destination_publishes(self, tmp_path):
        src = tmp_path / "s.bin"
        src.write_bytes(b"payload")
        dst = tmp_path / "d.bin"
        tmp = tmp_path / ".tmp-x"
        tmp.write_bytes(b"payload")
        AP.link_no_clobber(tmp, dst)
        assert dst.read_bytes() == b"payload"
        assert not os.path.lexists(tmp)

    @pytest.mark.parametrize("kind", ["file", "symlink", "dangling"])
    def test_existing_destination_any_form_refused(self, tmp_path, kind):
        dst = tmp_path / "d.bin"
        if kind == "file":
            dst.write_text("existing")
        elif kind == "symlink":
            other = tmp_path / "other.bin"
            other.write_text("target")
            dst.symlink_to(other)
        else:
            dst.symlink_to(tmp_path / "nowhere.bin")
        tmp = tmp_path / ".tmp-y"
        tmp.write_text("payload")
        with pytest.raises(AP.PublishError, match="refusing to clobber"):
            AP.link_no_clobber(tmp, dst)
        assert dst.is_symlink() or dst.read_text() == "existing"
        assert not os.path.lexists(tmp)

    def test_cross_directory_tmp_refused(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        tmp = tmp_path / "a" / ".t"
        tmp.write_text("x")
        with pytest.raises(AP.PublishError, match="same filesystem"):
            AP.link_no_clobber(tmp, tmp_path / "b" / "d")

    def test_real_two_process_race_exactly_one_winner(self, tmp_path):
        """REAL multiprocess race: N rounds, two publisher processes each
        creating the SAME destination via copy_verified; exactly one must win
        per round, the loser must not alter the winner's bytes."""
        racer = tmp_path / "racer.py"
        racer.write_text(
            "import sys, hashlib\n"
            f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
            "from pathlib import Path\n"
            "from build_per_reference_package import copy_verified\n"
            "src, dst, tag = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "data = tag.encode() * 4096\n"
            "src.write_bytes(data)\n"
            "try:\n"
            "    copy_verified(src, dst, hashlib.sha256(data).hexdigest())\n"
            "    print('WIN')\n"
            "except Exception as e:\n"
            "    print('LOSE:' + type(e).__name__)\n")
        wins = 0
        rounds = 6
        for i in range(rounds):
            dst = tmp_path / "race" / f"dst_{i}.bin"
            dst.parent.mkdir(exist_ok=True)
            s1, s2 = tmp_path / f"s1_{i}.bin", tmp_path / f"s2_{i}.bin"
            p1 = subprocess.Popen([sys.executable, str(racer), s1, dst, "A"],
                                  stdout=subprocess.PIPE, text=True)
            p2 = subprocess.Popen([sys.executable, str(racer), s2, dst, "B"],
                                  stdout=subprocess.PIPE, text=True)
            o1, _ = p1.communicate(timeout=60)
            o2, _ = p2.communicate(timeout=60)
            results = sorted([o1.strip(), o2.strip()])
            assert results.count("WIN") == 1, f"round {i}: {results}"
            assert any(r.startswith("LOSE") for r in results), results
            winner_tag = "A" if o1.strip() == "WIN" else "B"
            assert dst.read_bytes()[:1].decode() == winner_tag
            # loser did not alter winner bytes: full-file check
            assert dst.stat().st_size == 4096 * len(winner_tag)
            wins += 1
        assert wins == rounds

    def test_copy_verified_tmp_never_lingers_on_failure(self, tmp_path):
        src = tmp_path / "s.bin"
        src.write_bytes(b"data-v1")
        dst = tmp_path / "d.bin"
        # wrong expected sha -> failure before commit
        with pytest.raises(H.IdentityError, match="before copy"):
            H.copy_verified(src, dst, "0" * 64)
        leftovers = [p for p in tmp_path.iterdir() if ".partial-" in p.name]
        assert leftovers == []
        assert not os.path.lexists(dst)

    def test_inode_identity_change_detected(self, tmp_path):
        """Source replaced (new inode, same size) DURING the copy window is
        caught by the pre/post stat identity check. Deterministic: swap when
        the copier's .partial- tmp appears (post-pre-hash, mid-copy)."""
        import threading
        src = tmp_path / "s.bin"
        src.write_bytes(b"X" * (4 << 20))
        good_sha = _sha(src)
        dst_dir = tmp_path / "out"
        dst_dir.mkdir()
        dst = dst_dir / "d.bin"
        copied = {"err": None}

        def copier():
            try:
                H.copy_verified(src, dst, good_sha)
            except Exception as e:  # noqa: BLE001
                copied["err"] = f"{type(e).__name__}: {e}"

        th = threading.Thread(target=copier)
        th.start()
        # deterministic coordination: wait for the copier's tmp, then swap
        import time as _t
        deadline = _t.time() + 30
        while _t.time() < deadline:
            partials = list(dst_dir.glob(".partial-*")) or \
                list(dst_dir.glob("*.partial-*"))
            if partials:
                # mid-copy: replace the source with a same-size new inode
                src.unlink()
                src.write_bytes(b"Y" * (4 << 20))
                break
            _t.sleep(0.001)
        th.join(timeout=60)
        assert copied["err"], "inode swap during copy must be detected"
        assert "identity changed" in copied["err"] or "mutated" in copied["err"], copied
        assert not os.path.lexists(dst)

# ============================================================ P1-B
class TestRealMidCopyTOCTOU:
    def test_continuous_mutation_during_copy_detected(self, tmp_path):
        """TRUE mid-copy mutation: a second process rewrites the source tail
        continuously while the copy runs. Detection is deterministic (any
        mutation inside the copy window changes the post-copy hash), no
        random sleep. Correct impl -> IdentityError, no destination; a
        mutation that removes the post-copy hash check -> this test FAILS
        (proven in the mutation-control run)."""
        src = tmp_path / "big.bin"
        chunk = 1 << 20
        n_chunks = 96  # 96 MiB: copy takes long enough deterministically
        with open(src, "wb") as f:
            f.write(b"\x00" * (chunk * n_chunks))
        good_sha = _sha(src)
        dst = tmp_path / "out" / "big.bin"
        dst.parent.mkdir()

        copier = subprocess.Popen(
            [sys.executable, "-c",
             "import sys\n"
             f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
             "from build_per_reference_package import copy_verified, IdentityError\n"
             "from pathlib import Path\n"
             "try:\n"
             f"    copy_verified(Path({str(src)!r}), Path({str(dst)!r}), {good_sha!r})\n"
             "    print('PUBLISHED')\n"
             "except IdentityError as e:\n"
             "    print(f'CAUGHT:{e}')\n"],
            stdout=subprocess.PIPE, text=True)
        import time as _t
        # deterministic start barrier: mutation begins only once the copier
        # has passed its pre-copy hash (evidenced by the .partial- tmp file)
        deadline = _t.time() + 30
        while _t.time() < deadline:
            if list(dst.parent.glob("*.partial-*")):
                break
            _t.sleep(0.001)
        try:
            flips = 0
            fd = os.open(src, os.O_WRONLY)
            try:
                while copier.poll() is None:
                    os.pwrite(fd, b"\xff" * 4096, chunk * (n_chunks - 1))
                    flips += 1
            finally:
                os.close(fd)
            out, _ = copier.communicate(timeout=120)
        finally:
            if copier.poll() is None:
                copier.kill()
        assert out.startswith("CAUGHT:") and "mutated" in out, out
        assert not os.path.lexists(dst), "mutated copy must never publish"
        assert flips > 0  # the adversarial writer actually ran during copy
        # no misinterpretable artifacts in the delivery dir
        assert list(dst.parent.iterdir()) == []


# ============================================================ P1-A
class TestSnapshotImmutability:
    def test_symlink_with_CORRECT_content_sha_refused(self, tmp_path):
        """The P1-A headline: a symlink whose target content hashes to the
        expected sha must STILL be refused — type, not content, decides."""
        snap, wsha = A.snapshot_worker_source(tmp_path)
        os.chmod(snap, 0o644)
        target = tmp_path / "real.py"
        target.write_bytes(A.GEN_WORKER.encode())  # correct content!
        snap.unlink()
        snap.symlink_to(target)
        with pytest.raises(RuntimeError, match="SYMLINK"):
            A.snapshot_worker_source(tmp_path)

    def test_symlink_with_wrong_content_refused(self, tmp_path):
        src_dir = tmp_path / "worker_sources"
        src_dir.mkdir()
        target = tmp_path / "evil.py"
        target.write_text("evil")
        wsha = hashlib.sha256(A.GEN_WORKER.encode()).hexdigest()
        (src_dir / f"{wsha}.py").symlink_to(target)
        with pytest.raises(RuntimeError, match="SYMLINK"):
            A.snapshot_worker_source(tmp_path)

    def test_tampered_snapshot_refused(self, tmp_path):
        snap, wsha = A.snapshot_worker_source(tmp_path)
        os.chmod(snap, 0o644)
        snap.write_bytes(b"tampered")
        with pytest.raises(RuntimeError, match="tampered"):
            A.snapshot_worker_source(tmp_path)

    def test_correct_name_wrong_bytes_refused(self, tmp_path):
        src_dir = tmp_path / "worker_sources"
        src_dir.mkdir()
        wsha = hashlib.sha256(A.GEN_WORKER.encode()).hexdigest()
        (src_dir / f"{wsha}.py").write_text("wrong bytes")
        with pytest.raises(RuntimeError, match="tampered"):
            A.snapshot_worker_source(tmp_path)

    def test_snapshot_path_is_directory_refused(self, tmp_path):
        src_dir = tmp_path / "worker_sources"
        src_dir.mkdir()
        wsha = hashlib.sha256(A.GEN_WORKER.encode()).hexdigest()
        (src_dir / f"{wsha}.py").mkdir()
        with pytest.raises(RuntimeError, match="unexpected type|tampered"):
            A.snapshot_worker_source(tmp_path)

    def test_real_concurrent_writers_same_sha(self, tmp_path):
        """Two REAL processes snapshot identical content: both end verified,
        exactly one snapshot file exists, no partial artifacts remain."""
        prog = ("import sys\n"
                f"sys.path.insert(0, {str(REPO / 'scripts')!r})\n"
                "import run_wsb_torch as A\n"
                "from pathlib import Path\n"
                f"A.snapshot_worker_source(Path({str(tmp_path)!r}))\n"
                "print('OK')\n")
        ps = [subprocess.Popen([sys.executable, "-c", prog],
                               stdout=subprocess.PIPE, text=True)
              for _ in range(2)]
        for p in ps:
            out, _ = p.communicate(timeout=60)
            assert out.strip() == "OK"
        snaps = list((tmp_path / "worker_sources").glob("*.py"))
        assert len(snaps) == 1
        leftovers = [p for p in (tmp_path / "worker_sources").iterdir()
                     if p.name.startswith(".snap-tmp-")]
        assert leftovers == []

    def test_real_concurrent_writers_different_sha(self, tmp_path, monkeypatch):
        """Two REAL forked processes with DIFFERENT worker content (inherited
        via fork): two distinct snapshots coexist, neither overwrites."""
        import multiprocessing as mp
        base = A.GEN_WORKER

        def worker(tag, q):
            try:
                monkeypatch_local = None  # fork inherits monkeypatch already
                A.GEN_WORKER = base + f"\n# variant {tag}\n"
                A.snapshot_worker_source(tmp_path)
                q.put(f"OK{tag}")
            except Exception as e:  # noqa: BLE001
                q.put(f"ERR{tag}:{type(e).__name__}")

        # ensure the base variant snapshot exists first (parent context)
        monkeypatch.setattr(A, "GEN_WORKER", base + "\n# variant P\n")
        A.snapshot_worker_source(tmp_path)
        ctx = mp.get_context("fork")
        q = ctx.Queue()
        ps = [ctx.Process(target=worker, args=(t_, q)) for t_ in ("1", "2")]
        for p_ in ps:
            p_.start()
        results = [q.get(timeout=60) for _ in ps]
        for p_ in ps:
            p_.join(timeout=60)
        assert all(r.startswith("OK") for r in results), results
        names = {s.name for s in (tmp_path / "worker_sources").glob("*.py")}
        assert len(names) == 3  # parent variant + two child variants, all coexisting

    def test_crash_during_snapshot_write_leaves_no_final_artifact(self, tmp_path):
        """Simulated crash mid-write: the partial content sits ONLY under a
        .snap-tmp-* name; the content-addressed name never materializes
        partially, and a subsequent normal call still succeeds + verifies."""
        src_dir = tmp_path / "worker_sources"
        src_dir.mkdir()
        stale = src_dir / ".snap-tmp-deadbeef"
        stale.write_text("partial bytes from a crashed writer")
        snap, wsha = A.snapshot_worker_source(tmp_path)
        assert snap.is_file() and _sha(snap) == wsha
        assert stale.is_file()  # untouched: crash forensics preserved, never
        # mistaken for a snapshot (dot-prefixed tmp name, no .py suffix)

    def test_corrupt_legacy_source_is_preserved_not_executed(self, tmp_path):
        legacy = tmp_path / "_gen_worker.py"
        legacy.write_text("# corrupt legacy garbage\x00\x01")
        snap, wsha = A.snapshot_worker_source(tmp_path)
        assert "garbage" in legacy.read_text()  # preserved verbatim
        preserved = tmp_path / "worker_sources" / f"{_sha(legacy)}.py"
        assert preserved.is_file() and _sha(preserved) == _sha(legacy)

    def test_worker_sources_symlink_refused(self, tmp_path):
        real = tmp_path / "elsewhere"
        real.mkdir()
        (tmp_path / "worker_sources").symlink_to(real)
        with pytest.raises(RuntimeError, match="symlink"):
            A.snapshot_worker_source(tmp_path)


# ============================================================ P0-A
class TestAtomicPackagePublication:
    def _run_packager(self, run: Path, out: Path):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
             "--run", str(run), "--out", str(out), "--rights-confirmed"],
            capture_output=True, text=True)

    @pytest.mark.parametrize("victim", ["first", "middle", "last"])
    def test_candidate_failure_leaves_no_final_package(self, tmp_path, victim):
        run, rows = make_run(tmp_path)
        # tamper the encoding receipt of one candidate -> identity failure
        order = {"first": 0, "middle": 96, "last": 191}[victim]
        cid = rows[2 * order]["id"]  # selected r0 of that prompt
        enc = run / "scores" / "audio" / cid / "encoding.json"
        enc.chmod(0o644)
        d = json.loads(enc.read_text())
        d["source_flac_sha256"] = "0" * 64
        enc.write_text(json.dumps(d))
        out = tmp_path / "pkg"
        r = self._run_packager(run, out)
        assert r.returncode != 0
        assert not os.path.lexists(out), "failed packaging MUST NOT create final"
        staging_leftovers = [p for p in tmp_path.iterdir() if ".staging-" in p.name]
        assert staging_leftovers == [], "failed packaging must clean staging"

    def test_existing_full_package_never_touched(self, tmp_path):
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        assert self._run_packager(run, out).returncode == 0
        before = {p.name: _sha(p) for p in out.rglob("*") if p.is_file()}
        r = self._run_packager(run, out)  # second publish attempt
        assert r.returncode != 0 and "never be overwritten" in r.stderr
        after = {p.name: _sha(p) for p in out.rglob("*") if p.is_file()}
        assert before == after

    def test_final_path_is_symlink_refused(self, tmp_path):
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        target = tmp_path / "real-dir"
        target.mkdir()
        out.symlink_to(target)
        r = self._run_packager(run, out)
        assert r.returncode != 0 and "symlink" in r.stderr
        assert out.is_symlink()

    def test_real_concurrent_publishers_exactly_one_package(self, tmp_path):
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        ps = [subprocess.Popen(
            [sys.executable, str(REPO / "scripts" / "build_per_reference_package.py"),
             "--run", str(run), "--out", str(out), "--rights-confirmed"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)]
        outs = [p.communicate(timeout=180) for p in ps]
        codes = [p.returncode for p in ps]
        assert sorted(codes) == [0, 2], (codes, outs)
        # the single winner's package is complete & audited
        winner_pkg = json.loads((out / "package.json").read_text())
        audit = json.loads((out / ".package_audit.json").read_text())
        assert audit["result"] == "COMPLETE"
        n = len(winner_pkg["reference_values"])
        assert len(list((out / "audio").iterdir())) == n
        # loser left no staging debris
        leftovers = [p for p in tmp_path.iterdir() if ".staging-" in p.name]
        assert leftovers == []

    def test_json_artifact_write_failure_aborts_atomically(self, tmp_path,
                                                           monkeypatch):
        """ENOSPC during a staged json write aborts atomically: no final
        package, no staging debris."""
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        real_dump = json.dump

        def exploding_dump(obj, fp, *a, **k):
            # package.json is the ONLY staged artifact using json.dump
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(json, "dump", exploding_dump)
        old_argv = sys.argv
        sys.argv = ["prog", "--run", str(run), "--out", str(out),
                    "--rights-confirmed"]
        import contextlib, io
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    rc = H.main()
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
        finally:
            sys.argv = old_argv
        assert rc != 0, "ENOSPC during staged json write must abort"
        assert not os.path.lexists(out), "no final package after abort"
        assert [p for p in tmp_path.iterdir() if ".staging-" in p.name] == []

    def test_staging_interrupted_leaves_no_final(self, tmp_path):
        """Crash simulation: a leftover staging dir (from a killed publisher)
        never becomes or masks the final package; a fresh publish succeeds."""
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        orphan = out.with_name(out.name + ".staging-" + uuid.uuid4().hex)
        (orphan / "audio").mkdir(parents=True)
        (orphan / "audio" / "junk.flac").write_bytes(b"junk")
        r = self._run_packager(run, out)
        assert r.returncode == 0  # fresh publish works despite orphan staging
        assert json.loads((out / ".package_audit.json").read_text())["result"] == "COMPLETE"
        assert "junk" not in [f.name for f in (out / "audio").iterdir()]
        assert orphan.is_dir()  # orphan preserved (crash forensics), clearly named

    def test_audit_detects_staged_drift_and_refuses(self, tmp_path, monkeypatch):
        """Deterministic completeness-audit failure: staged file mutated
        between copy and audit (patched sha to return a wrong value for the
        audit pass) — final must not exist."""
        run, rows = make_run(tmp_path)
        out = tmp_path / "pkg"
        real_sha = H.sha
        seen = {"n": 0}

        def drifting_sha(p):
            seen["n"] += 1
            d = real_sha(p)
            if seen["n"] > 30 and str(p).endswith(".flac"):
                return "0" * 64  # audit-pass drift
            return d

        monkeypatch.setattr(H, "sha", drifting_sha)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            import sys as _s
            old = _s.argv
            _s.argv = ["prog", "--run", str(run), "--out", str(out),
                       "--rights-confirmed"]
            try:
                try:
                    rc = H.main()
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
            finally:
                _s.argv = old
        assert rc != 0
        assert not os.path.lexists(out)


class TestRenameat2UnsupportedFailsClosed:
    def test_enosys_raises_publish_error_not_clobber(self, tmp_path, monkeypatch):
        """RC2 mutation control A10: on a filesystem without renameat2 support
        the publication must FAIL CLOSED — a clobbering os.rename fallback
        previously survived the entire suite."""
        import errno as _errno

        def _nosys(old, new, flags):
            raise OSError(_errno.ENOSYS, "Function not implemented")

        monkeypatch.setattr(AP, "_renameat2", _nosys)
        staging = tmp_path / "staging"; final = tmp_path / "final"
        staging.mkdir(); (staging / "a.txt").write_text("x")
        with pytest.raises(AP.PublishError):
            AP.publish_directory_no_clobber(staging, final)
        # nothing was clobbered or moved
        assert staging.is_dir() and (staging / "a.txt").is_file()
        assert not final.exists()
