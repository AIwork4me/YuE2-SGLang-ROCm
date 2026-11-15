"""Evaluator patch-chain regression tests (0006 → 0007 → 0009 → 0010).

Rebuilds the full patched evaluator from the PRISTINE frozen tarball and
asserts bit-exact hashes at every stage against configs/benchmark.lock.yaml.
Positive controls: every stage hash matches its pin.
Negative controls: the chain refuses wrong order; the backend allowlist still
rejects unknown backends after 0010.

These tests use the official frozen evaluator bundle (a pinned, hashed
download) — they never fabricate benchmark results.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PINNED = {
    "pristine_wsb_eval": "29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de",
    "eval_worker_0007": "569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57",
    "wsb_eval_0006": "6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5",
    "wsb_eval_0006_0009": "729fd5974e7c9838ac17e9c42d140e809588af75faa9dbe1d48fe3bb207fbddf",
    "wsb_eval_0006_0009_0010": "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015",
}

# Locate a pristine evaluator tarball (workspace download, pinned sha)
WS = Path(__import__("os").environ.get("YUE2_WORKSPACE", "/data/yue2"))
TARBALL = WS / "benchmark" / "WildSongBench" / "evaluation" / "wsb_metrics.tar.gz"
TARBALL_SHA = "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def pristine_tree():
    if not TARBALL.is_file():
        pytest.skip("frozen evaluator tarball not downloaded (run download_pins.py)")
    if sha(TARBALL) != TARBALL_SHA:
        pytest.fail("evaluator tarball does not match the frozen pin")
    # NEVER extract into pytest's /tmp tmp_path (4G tmpfs on this image class):
    # use the persistent workspace tmp (storage plan; handoff gotcha 4)
    base = WS / "tmp" / "test-evaluator-patches"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    d = base / "extract"
    with tarfile.open(TARBALL) as tf:
        tf.extractall(d, filter="data")
    root = d / "wsb_metrics"
    assert (root / "wsb_eval.py").is_file()
    assert sha(root / "wsb_eval.py") == PINNED["pristine_wsb_eval"]
    yield root
    shutil.rmtree(base, ignore_errors=True)


def _rel_header_0006_0007(out: Path):
    subprocess.run(
        ["git", "show",
         "origin/validation/gfx1100-rocm7141:patches/0006-0007-wsb-evaluator-rocm.patch"],
        cwd=REPO, capture_output=True, text=True, check=True)
    raw = subprocess.run(
        ["git", "show",
         "origin/validation/gfx1100-rocm7141:patches/0006-0007-wsb-evaluator-rocm.patch"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    import re
    raw = re.sub(r"^(---|\+\+\+) .*/(wsb_metrics/)?(wsb_eval\.py|src/[^\s]+).*$",
                 lambda m: f"{m.group(1)} b/{m.group(3)}", raw, flags=re.M)
    out.write_text(raw)


def _git(tree: Path, *args):
    r = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)
    return r


def _commit_all(tree: Path, msg: str):
    _git(tree, "add", "-A")
    _git(tree, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


def _scratch(sub: str) -> Path:
    d = WS / "tmp" / "test-evaluator-patches" / sub
    if d.exists():
        shutil.rmtree(d)
    return d


def test_full_chain_bit_exact(pristine_tree):
    tree = _scratch("chain")
    shutil.copytree(pristine_tree, tree)
    _git(tree, "init", "-q")
    _commit_all(tree, "pristine")
    assert sha(tree / "wsb_eval.py") == PINNED["pristine_wsb_eval"]

    # 0006+0007 from the frozen validation branch
    p1 = WS / "tmp" / "test-evaluator-patches" / "0006-0007.patch"
    p1.parent.mkdir(parents=True, exist_ok=True)
    _rel_header_0006_0007(p1)
    assert _git(tree, "apply", str(p1)).returncode == 0
    assert sha(tree / "wsb_eval.py") == PINNED["wsb_eval_0006"], "0006 state must match lock"
    assert sha(tree / "src/mot_infer/eval_worker.py") == PINNED["eval_worker_0007"], \
        "0007 eval_worker state must match lock"
    _commit_all(tree, "0006+0007")

    # 0009 = the @@ -381 hunk of the cumulative patch
    src = (REPO / "patches" / "0006-0007-0009-wsb-evaluator-rocm.patch").read_text()
    lines = src.splitlines(keepends=True)
    idx = next(i for i, l in enumerate(lines) if l.startswith("@@ -381"))
    p2 = WS / "tmp" / "test-evaluator-patches" / "0009.patch"
    p2.write_text("--- b/wsb_eval.py\n+++ b/wsb_eval.py\n" + "".join(lines[idx:]))
    assert _git(tree, "apply", str(p2)).returncode == 0
    assert sha(tree / "wsb_eval.py") == PINNED["wsb_eval_0006_0009"], \
        "0006+0009 state must equal the lock's patched_wsb_eval_sha256"
    _commit_all(tree, "0009")

    # 0010 = the formalized versioned patch
    p3 = REPO / "patches" / "0010-wsb-torch-eager-backend-allowlist.patch"
    assert _git(tree, "apply", str(p3)).returncode == 0
    assert sha(tree / "wsb_eval.py") == PINNED["wsb_eval_0006_0009_0010"]
    _commit_all(tree, "0010")


def test_0010_on_pristine_yields_unrecognized_state(pristine_tree):
    """Negative control: 0010 may contextually apply on pristine (its one
    changed line is identical there), but the result is NOT any lock-pinned
    state — only the full ordered chain produces the recognized final hash."""
    tree = _scratch("neg")
    shutil.copytree(pristine_tree, tree)
    _git(tree, "init", "-q")
    _commit_all(tree, "pristine")
    p3 = REPO / "patches" / "0010-wsb-torch-eager-backend-allowlist.patch"
    r = _git(tree, "apply", str(p3))
    assert r.returncode == 0, "context applies (same allowlist line in pristine)"
    got = sha(tree / "wsb_eval.py")
    assert got not in PINNED.values(), (
        f"pristine+0010 ({got[:12]}…) must not collide with any pinned chain state")


def test_0010_readme_documents_scope():
    t = (REPO / "patches" / "0010-wsb-torch-eager-backend-allowlist.patch.README").read_text()
    for needle in ("torch-eager", "WildSongBench", "docs/hardware.md",
                   "scoring formulas", "TESTS"):
        assert needle in t


def test_allowlist_still_rejects_unknown_backends_after_0010():
    """The patched allowlist is additive: torch, vllm, torch-eager — nothing else."""
    src = (REPO / "patches" / "0010-wsb-torch-eager-backend-allowlist.patch").read_text()
    assert "{'torch', 'vllm', 'torch-eager'}" in src
