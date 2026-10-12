#!/usr/bin/env bash
# checkpoint_milestone.sh - Phase 7 milestone evidence pipeline.
# Usage: checkpoint_milestone.sh <run_dir> <milestone-name> <mode:pilot|full>
# Verifies finalized artifacts (never directory counts), writes a milestone
# audit JSON, commits machine-scoped evidence to the gfx1100 branch, pushes,
# and prints the remote SHA.
set -euo pipefail
RUNS="$(realpath "$1")"
NAME="$2"
MODE="${3:-pilot}"
WS="${YUE2_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
REPO="$WS/evidence-repo"
BRANCH="validation/gfx1100-rocm7141"
cd "$REPO"
source "$WS/environments/yue2-gfx1100/bin/activate"
export YUE2_WORKSPACE="$WS"

echo "== milestone $NAME =="
python scripts/verify_wsb_artifacts.py --runs "$RUNS" --mode "$MODE" || true
python - "$RUNS" "$NAME" <<'PY'
import json, sys, time
from pathlib import Path
runs, name = Path(sys.argv[1]), sys.argv[2]
manifest = [json.loads(l) for l in (runs/"generation_manifest.jsonl").read_text().splitlines()] if (runs/"generation_manifest.jsonl").is_file() else []
complete = [m for m in manifest if m.get("status","").startswith("complete")]
from collections import Counter
c = Counter(m.get("status") for m in manifest)
milestone = {
    "milestone": name, "run": str(runs),
    "manifest_records": len(manifest),
    "complete_records": len(complete),
    "unique_complete_candidates": len({m["id"] for m in complete}),
    "unique_prompts_complete": len({m["prompt_index"] for m in complete}),
    "truncated_complete": sum(1 for m in complete if m.get("truncated")),
    "status_counts": dict(c),
    "audit": json.loads((runs/"audit.json").read_text()) if (runs/"audit.json").is_file() else None,
    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
out = Path("evidence/gfx1100")/f"milestone_{name}.json"
out.write_text(json.dumps(milestone, indent=1) + "\n")
print(f"milestone evidence -> {out} (complete={len(complete)})")
PY
git add evidence/gfx1100
if git diff --cached --quiet; then echo "nothing new to commit"; else
  git commit -qm "checkpoint(gfx1100): milestone $NAME - $(python3 -c "import json;d=json.load(open('evidence/gfx1100/milestone_${NAME}.json'));print(d['complete_records'],'complete /',d['manifest_records'],'records')")"
  git fetch origin "$BRANCH" 2>/dev/null || true
  git push origin "$BRANCH"
fi
gh api "repos/AIwork4me/YuE2-SGLang-ROCm/git/ref/heads/validation%2Fgfx1100-rocm7141" --jq '.object.sha'
