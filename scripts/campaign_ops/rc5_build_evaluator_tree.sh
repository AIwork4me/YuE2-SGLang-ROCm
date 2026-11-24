#!/usr/bin/env bash
# rc5_build_evaluator_tree.sh — rebuild the PATCHED frozen evaluator (RC5).
#
# Parameterized, self-contained version of build_evaluator_tree.sh (no
# hard-coded /workspace repo path, no dependency on a historical branch):
# every patch lives in this repo's patches/ directory and every stage is
# gated by the hash pinned in configs/benchmark.lock.yaml.
#
#   pristine wsb_eval.py        29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de
#   +0006  wsb_eval.py          6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5
#   +0007  eval_worker.py       569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57
#   +0009  wsb_eval.py          729fd5974e7c9838ac17e9c42d140e809588af75faa9dbe1d48fe3bb207fbddf
#   +0010  wsb_eval.py          efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015
#
# The patches only touch admission control (torch-family env exemption), the
# PER ASR engine construction (qwen_asr transformers backend, env-gated), the
# PER-reuse hash gate and the backend label allowlist. Phonemization,
# transcript normalization, repeat selection, PER math, candidate selection,
# aggregation, prompts and audio preprocessing are untouched.
set -euo pipefail

WS="${YUE2_WORKSPACE:-/data/yue2}"
REPO="${YUE2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TARBALL="${YUE2_EVALUATOR_TARBALL:-$WS/benchmark/WildSongBench/evaluation/wsb_metrics.tar.gz}"
TARBALL_SHA=bd550b36f1fc43cad3254a9897dd3a078e50c4eb9e8d4f295ac4b5e81d1fc4fd
DEST="${YUE2_EVALUATOR_TREE:-$WS/benchmark/wsb_metrics}"
TMPD="$WS/tmp/evaluator_build_rc5"
export TMPDIR="$WS/tmp"
mkdir -p "$TMPD"

sha() { sha256sum "$1" | awk '{print $1}'; }
gate() { # gate <file> <expected> <stage>
  local got; got=$(sha "$1")
  if [ "$got" != "$2" ]; then
    echo "FATAL: stage $3 hash gate FAILED: $1 $got != $2"; exit 2
  fi
  echo "GATE-OK $3 $(basename "$1") ${got:0:16}..."
}

[ -f "$TARBALL" ] || { echo "FATAL: tarball missing (download_pins.py first): $TARBALL"; exit 2; }
gate "$TARBALL" "$TARBALL_SHA" tarball

if [ -f "$DEST/wsb_eval.py" ] && [ "$(sha "$DEST/wsb_eval.py")" = "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015" ]; then
  echo "ALREADY-BUILT: $DEST matches the final pinned state; nothing to do"; exit 0
fi
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "FATAL: $DEST exists and is not in the final pinned state;" \
       "move it aside explicitly (never overwrite evidence)"; exit 2
fi

rm -rf "$TMPD"; mkdir -p "$TMPD"
echo "[1/6] extracting pristine tarball"
tar xzf "$TARBALL" -C "$TMPD"
mkdir -p "$(dirname "$DEST")"
mv "$TMPD/wsb_metrics" "$DEST"
gate "$DEST/wsb_eval.py" 29310259f0ad3663bc2625ab80bf89c70d9206b513bcb2b4de5f47cb53cad9de pristine

git -C "$DEST" init -q
git -C "$DEST" add -A
git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm pristine

echo "[2/6] 0006+0007 (admission control + qwen_asr transformers ASR, env-gated)"
sed -E 's@^(---|\+\+\+) .*/(wsb_metrics/)?(wsb_eval\.py|src/[^[:space:]]+).*$@\1 b/\3@' \
  "$REPO/patches/0006-0007-wsb-evaluator-rocm.patch" > "$TMPD/0006-0007.patch"
git -C "$DEST" apply "$TMPD/0006-0007.patch"
gate "$DEST/wsb_eval.py" 6a4a53ed6cdad548d1a727f0993ade349278b5c25704b6942d17d336af84c6e5 0006
gate "$DEST/src/mot_infer/eval_worker.py" 569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57 0007
git -C "$DEST" add -A; git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm "0006+0007"

echo "[3/6] 0009 (PER-reuse hash gate; @@ -381 hunk of the cumulative patch)"
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

echo "[4/6] 0010 (backend label allowlist)"
git -C "$DEST" apply "$REPO/patches/0010-wsb-torch-eager-backend-allowlist.patch"
gate "$DEST/wsb_eval.py" efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015 0010
git -C "$DEST" add -A; git -C "$DEST" -c user.email=t@t -c user.name=t commit -qm "0010"

echo "[5/6] release.json: record the two patched files (integrity chain kept, not bypassed)"
python3 - "$DEST" <<'PY'
import json, sys, time
from pathlib import Path
dest = Path(sys.argv[1])
rj = dest / "release.json"
d = json.loads(rj.read_text())
before = {k: d["code_files"].get(k) for k in ("wsb_eval.py", "src/mot_infer/eval_worker.py")}
d["code_files"]["wsb_eval.py"] = "efb890421c755c6e19fb841426a612dfa954f9b58a29eef2b8ce8ed7ff790015"
d["code_files"]["src/mot_infer/eval_worker.py"] = "569404c758b883e1d2d99724ea563524e06b2c07f2ecf418b1fa857a8ca79d57"
d["rocm_patch_disclosure"] = {
    "applied_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "patches": ["0006 torch-family env exemption", "0007 qwen_asr transformers ASR backend "
                "under WSB_ROCM_TORCH_OVERRIDE=1", "0009 PER-reuse hash gate",
                "0010 backend label allowlist"],
    "patched_files": {k: d["code_files"][k] for k in before},
    "pristine_hashes": before,
    "protocol_lock": "configs/benchmark.lock.yaml",
    "builder": "scripts/campaign_ops/rc5_build_evaluator_tree.sh"}
rj.write_text(json.dumps(d, indent=2) + "\n")
print(json.dumps({"release_json_before": before}))
PY

echo "[6/6] chain receipt"
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
  "release_json_amended": ["wsb_eval.py", "src/mot_infer/eval_worker.py"],
  "tool": "scripts/campaign_ops/rc5_build_evaluator_tree.sh"}
(dest / "release_chain_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
PY
rm -rf "$TMPD"
echo "patched evaluator tree verified at every stage: $DEST"
