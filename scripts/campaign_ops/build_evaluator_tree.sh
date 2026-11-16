#!/usr/bin/env bash
# build_evaluator_tree.sh — rebuild the PATCHED frozen evaluator (Env C tree).
#
# Phase B3 entry: evaluator_install.sh alone is NOT sufficient — the patched
# tree must be rebuilt from the PRISTINE pinned tarball through the frozen
# patch chain 0006+0007 → 0009 → 0010 with a hash gate at EVERY stage
# (configs/benchmark.lock.yaml; chain replicated bit-exactly by
# tests/test_evaluator_patches.py).
#
# Stages and pins:
#   pristine wsb_eval.py        29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de
#   +0006  wsb_eval.py          6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5
#   +0007  eval_worker.py       569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57
#   +0009  wsb_eval.py          729fd5974e7c9838ac17e9c42d140e809588af75faa9dbe1d48fe3bb207fbddf
#   +0010  wsb_eval.py          efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015
set -euo pipefail
WS=/data/yue2
REPO=/workspace/YuE2-SGLang-ROCm
TARBALL=$WS/benchmark/WildSongBench/evaluation/wsb_metrics.tar.gz
TARBALL_SHA=bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd
DEST=$WS/benchmark/WildSongBench/wsb_metrics
TMPD=$WS/tmp/evaluator_build
export TMPDIR=$WS/tmp

sha() { sha256sum "$1" | awk '{print $1}'; }
gate() { # gate <file> <expected> <stage>
  local got; got=$(sha "$1")
  if [ "$got" != "$2" ]; then
    echo "FATAL: stage $3 hash gate FAILED: $1 $got != $2"; exit 2
  fi
  echo "GATE-OK $3 $(basename "$1") ${got:0:16}..."
}

[ -f "$TARBALL" ] || { echo "FATAL: tarball missing (download_pins.py first)"; exit 2; }
gate "$TARBALL" "$TARBALL_SHA" tarball

if [ -f "$DEST/wsb_eval.py" ] && [ "$(sha "$DEST/wsb_eval.py")" = "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015" ]; then
  echo "ALREADY-BUILT: $DEST matches the final pinned state; nothing to do"; exit 0
fi

rm -rf "$TMPD"; mkdir -p "$TMPD"
echo "[1/6] extracting pristine tarball"
tar xzf "$TARBALL" -C "$TMPD"
mv "$TMPD/wsb_metrics" "$DEST"
gate "$DEST/wsb_eval.py" 29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de pristine

git -C "$DEST" init -q
git -C "$DEST" add -A
git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm pristine

echo "[2/6] 0006+0007 (validation branch, relative headers)"
git -C "$REPO" show origin/validation/gfx1100-rocm7141:patches/0006-0007-wsb-evaluator-rocm.patch \
  | sed -E 's@^(---|\+\+\+) .*/(wsb_metrics/)?(wsb_eval\.py|src/[^[:space:]]+).*$@\1 b/\3@' \
  > "$TMPD/0006-0007.patch"
git -C "$DEST" apply "$TMPD/0006-0007.patch"
gate "$DEST/wsb_eval.py" 6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5 0006
gate "$DEST/src/mot_infer/eval_worker.py" 569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57 0007
git -C "$DEST" add -A; git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm "0006+0007"

echo "[3/6] 0009 (@@ -381 hunk of the cumulative patch)"
python3 - "$REPO" "$TMPD" <<'PY'
import sys
from pathlib import Path
repo, tmpd = Path(sys.argv[1]), Path(sys.argv[2])
src = (repo / "patches/0006-0007-0009-wsb-evaluator-rocm.patch").read_text()
lines = src.splitlines(keepends=True)
idx = next(i for i, l in enumerate(lines) if l.startswith("@@ -381"))
(tmpd / "0009.patch").write_text("--- b/wsb_eval.py\n+++ b/wsb_eval.py\n" + "".join(lines[idx:]))
PY
git -C "$DEST" apply "$TMPD/0009.patch"
gate "$DEST/wsb_eval.py" 729fd5974e7c9838ac17e9c42d140e809588af75faa9dbe1d48fe3bb207fbddf 0009
git -C "$DEST" add -A; git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm "0009"

echo "[4/6] 0010 (torch-eager backend allowlist)"
git -C "$DEST" apply "$REPO/patches/0010-wsb-torch-eager-backend-allowlist.patch"
gate "$DEST/wsb_eval.py" efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015 0010
git -C "$DEST" add -A; git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm "0010"

echo "[5/6] release.json receipt"
python3 - "$DEST" <<'PY'
import json, sys, time
from pathlib import Path
dest = Path(sys.argv[1])
receipt = {
  "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "tarball_sha256": "bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd",
  "chain": [
    {"stage": "pristine", "wsb_eval": "29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de"},
    {"stage": "0006+0007", "wsb_eval": "6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5",
     "eval_worker": "569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57"},
    {"stage": "0009", "wsb_eval": "729fd5974e7c9838ac17e9c42d140e809588af75faa9dbe1d48fe3bb207fbddf"},
    {"stage": "0010", "wsb_eval": "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015"}],
  "tool": "scripts/campaign_ops/build_evaluator_tree.sh",
}
(dest / "release.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY

echo "[6/6] done — patched evaluator tree verified at every stage"
rm -rf "$TMPD"
