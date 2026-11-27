#!/usr/bin/env python3
"""RC6.1 M3.1/M3.3 — pinned installation tests (synthetic upstream repos).

A18 upstream branch advances            -> still pinned to the frozen SHA
A19 already-applied patch                -> idempotent skip (no failure)
A20 dirty upstream worktree              -> REFUSED (never reset --hard)
    frozen SHA absent                    -> FATAL (no branch-head fallback)
    wrong existing HEAD (clean)          -> corrected by checkout, verified
    partially-applied patch              -> REFUSED
    fresh clone path                     -> pinned + patched

Fully offline: a local bare git repo plays the upstream remote.

Run:  python3 -m pytest tests/test_rc61_install.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import reference_cli as cli  # noqa: E402

FROZEN = "c67d541a40f8bf851e9fc1e925f5316638838cd6"
OTHER = "0" * 40


def git(cwd: Path, *args) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *[str(a) for a in args]],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def make_upstream(tmp: Path) -> tuple[Path, Path]:
    """A local 'remote' with branch add_yue2 carrying FROZEN + a later head,
    plus a real patch file that applies at FROZEN."""
    upstream = tmp / "upstream-remote"
    upstream.mkdir(parents=True)
    git(upstream, "init", "--quiet", "--initial-branch", "add_yue2")
    (upstream / "python").mkdir()
    (upstream / "python" / "sglang").mkdir()
    (upstream / "python" / "sglang" / "__init__.py").write_text("value = 0\n")
    (upstream / "README.md").write_text("remote\n")
    git(upstream, "add", "-A")
    git(upstream, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    git(upstream, "tag", "frozen-tag")
    # advance the branch (A18: the moving branch head is NOT our pin)
    (upstream / "python" / "sglang" / "__init__.py").write_text("value = 1\n")
    git(upstream, "add", "-A")
    git(upstream, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "advance")
    # a patch that applies cleanly at the frozen commit
    patch = tmp / "guard.patch"
    patch.write_text(
        "diff --git a/python/sglang/__init__.py b/python/sglang/__init__.py\n"
        "--- a/python/sglang/__init__.py\n"
        "+++ b/python/sglang/__init__.py\n"
        "@@ -1 +1,2 @@\n"
        " value = 0\n"
        "+import guards  # rc5-0001\n")
    return upstream, patch


def frozen_sha(upstream: Path) -> str:
    return git(upstream, "rev-list", "-n1", "frozen-tag")


def clone_at(tmp: Path, upstream: Path, rev: str | None = None) -> Path:
    sgl = tmp / "sgl"
    git(tmp, "clone", "--quiet", "--branch", "add_yue2", str(upstream), str(sgl))
    if rev:
        git(sgl, "checkout", "--quiet", rev)
    return sgl


def ensure(sgl: Path, patch: Path, frozen: str, remote: Path):
    return cli.ensure_frozen_upstream(sgl, patch, frozen, str(remote), dry=False,
                                      log=lambda *a: None)


def test_A18_branch_advances_pin_holds(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = clone_at(tmp_path, upstream, frozen)
    # advance the REMOTE branch after cloning (the moving-branch hazard)
    (upstream / "python" / "sglang" / "__init__.py").write_text("value = 2\n")
    git(upstream, "add", "-A")
    git(upstream, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "advance2")
    rc, summary = ensure(sgl, patch, frozen, upstream)
    assert rc == cli.EXIT_OK, summary
    assert git(sgl, "rev-parse", "HEAD") == frozen


def test_frozen_sha_absent_is_fatal_no_branch_fallback(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    sgl = clone_at(tmp_path, upstream)
    rc, summary = ensure(sgl, patch, OTHER, upstream)
    assert rc == cli.EXIT_FATAL, summary
    assert "NO fallback" in summary


def test_wrong_existing_head_corrected_and_verified(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = clone_at(tmp_path, upstream)          # at branch head, not frozen
    rc, summary = ensure(sgl, patch, frozen, upstream)
    assert rc == cli.EXIT_OK, summary
    assert git(sgl, "rev-parse", "HEAD") == frozen


def test_A20_dirty_worktree_refused_not_reset(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = clone_at(tmp_path, upstream)
    (sgl / "python" / "sglang" / "__init__.py").write_text("local user edit\n")
    rc, summary = ensure(sgl, patch, frozen, upstream)
    assert rc == cli.EXIT_REJECT, summary
    assert "unexpected local" in summary
    assert "local user edit" in (sgl / "python" / "sglang" / "__init__.py").read_text()


def test_A19_already_applied_patch_idempotent(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = clone_at(tmp_path, upstream, frozen)
    git(sgl, "apply", str(patch))               # applied manually beforehand
    rc, summary = ensure(sgl, patch, frozen, upstream)
    assert rc == cli.EXIT_OK, summary
    assert "already applied" in summary
    assert "guards" in (sgl / "python" / "sglang" / "__init__.py").read_text()


def test_fresh_clone_pinned_and_patched(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = tmp_path / "sgl"                      # ensure() clones it
    rc, summary = cli.ensure_frozen_upstream(sgl, patch, frozen, str(upstream),
                                             dry=False, log=lambda *a: None)
    assert rc == cli.EXIT_OK, summary
    assert git(sgl, "rev-parse", "HEAD") == frozen
    assert "guards" in (sgl / "python" / "sglang" / "__init__.py").read_text()


def test_partially_applied_patch_refused(tmp_path):
    upstream, patch = make_upstream(tmp_path)
    frozen = frozen_sha(upstream)
    sgl = clone_at(tmp_path, upstream, frozen)
    # an INTERRUPTED patch apply leaves the tree AT the frozen HEAD with
    # content the patch neither applies onto nor reverses from -> REFUSED by
    # the patch-state check (committed foreign changes cannot exist at the
    # frozen HEAD: a commit moves HEAD, and the pin step corrects that first).
    (sgl / "python" / "sglang" / "__init__.py").write_text("partial edit\n")
    rc, summary = ensure(sgl, patch, frozen, upstream)
    assert rc == cli.EXIT_REJECT, summary
    assert "neither applies" in summary
    # the user's partial work is NOT discarded
    assert "partial edit" in (sgl / "python" / "sglang" / "__init__.py").read_text()


# ------------------------------------------------------ CLI contract (M3.4)
def test_cli_dry_run_install_has_no_side_effects(tmp_path):
    """A24: dry-run must not clone, patch, download or install anything."""
    class Args:
        dry_run = True
        workspace = str(tmp_path / "ws")
    rc = cli.cmd_install(Args())
    assert rc == cli.EXIT_OK
    sgl = Path(Args.workspace) / "upstream/sglang-latest"
    assert not sgl.exists(), "dry-run must not clone the upstream"


def test_cli_generate_dry_run_creates_nothing(tmp_path):
    class Args:
        dry_run = True
        workspace = str(tmp_path / "ws")
        lyrics = str(tmp_path / "lyrics.txt")
        style = "x"
        seed = 1
        out_dir = str(tmp_path / "out")
        song_id = "s"
    (tmp_path / "lyrics.txt").write_text("la la\n")
    rc = cli.cmd_generate(Args())
    assert rc == cli.EXIT_OK
    assert not Path(Args.out_dir).exists(), "dry-run must not create the out dir"


def test_cli_generate_no_clobber(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "existing.txt").write_text("x")
    class Args:
        dry_run = False
        workspace = str(tmp_path / "ws")
        lyrics = str(tmp_path / "lyrics.txt")
        style = "x"
        seed = 1
        out_dir = str(out)
        song_id = "s"
    (tmp_path / "lyrics.txt").write_text("la la\n")
    rc = cli.cmd_generate(Args())
    assert rc == cli.EXIT_REJECT


def test_cli_works_from_any_cwd(tmp_path):
    """M3.4: all paths resolve from the repo root, not the caller's CWD."""
    p = subprocess.run([sys.executable, str(REPO / "scripts/reference_cli.py"),
                        "status", "--workspace", str(tmp_path)],
                       capture_output=True, text=True, cwd="/tmp")
    assert p.returncode == 0
    d = json.loads(p.stdout)
    assert d["workspace"] == str(tmp_path)
