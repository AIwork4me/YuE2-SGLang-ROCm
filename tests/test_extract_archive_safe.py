"""extract_archive_safe.py regression tests — CPU only, synthetic archives."""
from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "scripts/campaign_ops/extract_archive_safe.py"


def run_tool(archive: Path, dest: Path, *extra):
    return subprocess.run(
        [sys.executable, str(TOOL), "--archive", str(archive),
         "--dest", str(dest), *extra],
        capture_output=True, text=True)


def make_tar(path: Path, builder):
    with tarfile.open(path, "w:gz") as tf:
        builder(tf)


def test_clean_archive_extracts(tmp_path):
    arc = tmp_path / "a.tar.gz"

    def build(tf):
        ti = tarfile.TarInfo("armA_wsb_full/songs/x/result.json")
        ti.size = 2
        tf.addfile(ti, __import__("io").BytesIO(b"{}"))
    make_tar(arc, build)
    dest = tmp_path / "out"
    r = run_tool(arc, dest, "--expect-top", "armA_wsb_full")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "armA_wsb_full/songs/x/result.json").read_bytes() == b"{}"
    assert (tmp_path / "out.extract_receipt.json").is_file()


def test_absolute_path_rejected(tmp_path):
    arc = tmp_path / "a.tar.gz"
    make_tar(arc, lambda tf: tf.addfile(
        tarfile.TarInfo("/etc/passwd"), __import__("io").BytesIO(b"x")))
    r = run_tool(arc, tmp_path / "out")
    assert r.returncode == 4
    assert "absolute path" in r.stdout


def test_traversal_rejected(tmp_path):
    arc = tmp_path / "a.tar.gz"
    make_tar(arc, lambda tf: tf.addfile(
        tarfile.TarInfo("../evil.sh"), __import__("io").BytesIO(b"x")))
    r = run_tool(arc, tmp_path / "out")
    assert r.returncode == 4
    assert "traversal" in r.stdout


def test_unsafe_symlink_rejected(tmp_path):
    arc = tmp_path / "a.tar.gz"

    def build(tf):
        ti = tarfile.TarInfo("armA_wsb_full/link")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "../../outside"
        tf.addfile(ti)
    make_tar(arc, build)
    r = run_tool(arc, tmp_path / "out")
    assert r.returncode == 4
    assert "unsafe link" in r.stdout


def test_no_clobber_nonempty_dest(tmp_path):
    arc = tmp_path / "a.tar.gz"
    make_tar(arc, lambda tf: tf.addfile(
        tarfile.TarInfo("armA_wsb_full/x"), __import__("io").BytesIO(b"1")))
    dest = tmp_path / "out"
    (dest / "existing").mkdir(parents=True)
    (dest / "existing/keep.txt").write_text("precious")
    r = run_tool(arc, dest)
    assert r.returncode == 3
    assert (dest / "existing/keep.txt").read_text() == "precious"


def test_wrong_top_level_rejected(tmp_path):
    arc = tmp_path / "a.tar.gz"
    make_tar(arc, lambda tf: tf.addfile(
        tarfile.TarInfo("other_top/x"), __import__("io").BytesIO(b"1")))
    r = run_tool(arc, tmp_path / "out", "--expect-top", "armA_wsb_full")
    assert r.returncode == 5


def test_corrupt_gzip_rejected(tmp_path):
    arc = tmp_path / "a.tar.gz"
    arc.write_bytes(b"\x1f\x8b" + b"\x00" * 64)  # gzip magic, garbage body
    r = run_tool(arc, tmp_path / "out")
    assert r.returncode == 2
    assert "gzip" in r.stdout
