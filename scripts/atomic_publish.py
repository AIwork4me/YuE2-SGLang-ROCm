#!/usr/bin/env python3
"""atomic_publish.py — race-free no-clobber publication primitives (C2.1).

Contracts:
  * publish_directory_no_clobber(staging, final): exactly-one-shot directory
    publication. Uses Linux renameat2(RENAME_NOREPLACE) — atomic, refuses any
    existing target (dir/file/symlink/dangling). On filesystems lacking the
    syscall we FAIL CLOSED (per mission: no silent degrade to clobbering
    os.rename). staging MUST be a sibling of final (same filesystem, enforced).
  * link_no_clobber(tmp, dst): file publication via hardlink — kernel
    guarantees EEXIST for any existing dst path form; tmp is unlinked after.
  * fsync_dir/fsync_file: durability helpers (data + directory entries).

No function here ever overwrites an existing destination. Ever.
"""
from __future__ import annotations

import ctypes
import errno
import os
import platform
from pathlib import Path

RENAME_NOREPLACE = 1
# renameat2 syscall numbers (glibc wrappers are not universally exposed)
_SYSCALL_RENAMEAT2 = {"x86_64": 316, "aarch64": 276, "ppc64le": 357,
                      "s390x": 347}


class PublishError(RuntimeError):
    """Fail-closed publication refusal."""


def _renameat2(old: Path, new: Path, flags: int) -> None:
    arch = platform.machine()
    nr = _SYSCALL_RENAMEAT2.get(arch)
    if nr is None:
        raise PublishError(f"renameat2 syscall number unknown on {arch} — "
                           f"failing closed (no clobbering fallback)")
    libc = ctypes.CDLL(None, use_errno=True)
    AT_FDCWD = -100
    r = libc.syscall(nr, AT_FDCWD, str(old).encode(),
                     AT_FDCWD, str(new).encode(), flags)
    if r != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


def fsync_file(p: Path) -> None:
    fd = os.open(p, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(p: Path) -> None:
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_directory_no_clobber(staging: Path, final: Path) -> None:
    """Publish the fully-built staging directory as final, exactly once.

    Pre-conditions (enforced): staging exists and is a real dir (not symlink);
    staging and final share a parent (same filesystem by construction);
    final does not exist in ANY form (a pre-existing final is a clean refusal
    before any staging work — also checked by callers, but re-checked here).
    """
    staging, final = Path(staging), Path(final)
    if staging.is_symlink() or not staging.is_dir():
        raise PublishError(f"staging must be a real directory: {staging}")
    if staging.parent.resolve() != final.parent.resolve():
        raise PublishError("staging must be a SIBLING of final "
                           "(same filesystem required for atomic rename)")
    if os.path.lexists(final):
        raise PublishError(f"final already exists ({final}) — refusing to "
                           f"publish over it")
    fsync_dir(staging)
    for child in sorted(staging.rglob("*")):
        if child.is_file():
            fsync_file(child)
    fsync_dir(staging / "audio") if (staging / "audio").is_dir() else None
    try:
        _renameat2(staging, final, RENAME_NOREPLACE)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            raise PublishError(f"concurrent publisher won: {final} exists") from exc
        if exc.errno in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise PublishError(
                f"filesystem does not support RENAME_NOREPLACE "
                f"(errno {exc.errno}) — failing CLOSED rather than risking "
                f"clobber") from exc
        raise
    fsync_dir(final.parent)


def link_no_clobber(tmp: Path, dst: Path) -> None:
    """Publish tmp as dst via hardlink. Atomic no-clobber: link(2) fails
    EEXIST for ANY existing dst (regular/symlink/dangling). tmp is removed
    after publication (the inode lives on as dst). Same-filesystem required
    (enforced by construction: tmp lives in dst's directory)."""
    tmp, dst = Path(tmp), Path(dst)
    if tmp.parent.resolve() != dst.parent.resolve():
        raise PublishError("tmp must be in dst's directory (same filesystem)")
    try:
        os.link(tmp, dst)
    except FileExistsError as exc:
        if os.path.lexists(tmp):
            tmp.unlink()
        raise PublishError(f"destination exists — refusing to clobber: "
                           f"{dst.name}") from exc
    except OSError as exc:
        if os.path.lexists(tmp):
            tmp.unlink()
        if exc.errno == errno.EXDEV:
            raise PublishError("cross-device link impossible (tmp not in "
                               "dst's directory?)") from exc
        raise
    tmp.unlink()
    fsync_dir(dst.parent)
