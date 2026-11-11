#!/usr/bin/env python3
"""yue2_workspace.py — single workspace resolution contract for all scripts.

The workspace (WS) is the directory that contains the campaign assets:
  benchmark/WildSongBench/   pinned dataset + evaluator (gitignored)
  models/                    pinned model snapshots (gitignored)
  environments/              Python virtual environments (gitignored)
  upstream/sglang/           pinned SGLang checkout (gitignored)
  runs/                      generation outputs (gitignored)
  logs/                      receipts

Historical layout (campaign machines):  <WS>/evidence/YuE2-SGLang-ROCm/scripts/x.py
Standalone clone layout:               <WS == repo root>/scripts/x.py

Resolution order:
  1. $YUE2_WORKSPACE if set (errors clearly if it does not look like a workspace)
  2. repository root, if it directly contains campaign assets
  3. historical nested layout (parents[2] of this file), if it contains assets
  4. otherwise: actionable error listing every candidate considered.

This replaces the previous unconditional ``parents[2]`` default, which silently
resolved one directory ABOVE a standalone clone and broke fresh checkouts.
"""
from __future__ import annotations

import os
from pathlib import Path

MARKERS = ("benchmark", "models", "environments", "upstream")


def _looks_like_workspace(path: Path) -> bool:
    """A workspace must contain at least the dataset pin plus one asset dir."""
    return (path / "benchmark" / "WildSongBench").is_dir() and any(
        (path / m).is_dir() for m in MARKERS
    )


def _candidates(script_file: Path):
    script_file = Path(script_file).resolve()
    repo_root = script_file.parents[1]          # <repo>/scripts/x.py -> <repo>
    yield ("repository root", repo_root)
    if len(script_file.parents) > 2:
        yield ("historical parents[2]", script_file.parents[2])


def resolve_workspace(script_file) -> Path:
    env = os.environ.get("YUE2_WORKSPACE")
    if env:
        ws = Path(env).expanduser().resolve()
        if not ws.is_dir():
            raise FileNotFoundError(
                f"YUE2_WORKSPACE={env} does not exist")
        if not _looks_like_workspace(ws):
            raise FileNotFoundError(
                f"YUE2_WORKSPACE={env} does not look like a YuE2 workspace "
                f"(expected benchmark/WildSongBench plus one of {MARKERS}). "
                f"Run scripts/download_pins.py --workspace <dir> first.")
        return ws
    searched = []
    for label, candidate in _candidates(script_file):
        if _looks_like_workspace(candidate):
            return candidate
        searched.append(f"{label}: {candidate}")
    raise FileNotFoundError(
        "Cannot locate the YuE2 workspace. Either:\n"
        "  * set YUE2_WORKSPACE=<workspace dir>, or\n"
        "  * place campaign assets in the repository root "
        "(scripts/download_pins.py --workspace <repo>), or\n"
        "  * keep the historical layout <workspace>/evidence/<this-repo>.\n"
        f"Candidates considered: {'; '.join(searched)}")


if __name__ == "__main__":  # pragma: no cover - manual diagnostic
    import sys
    try:
        print(resolve_workspace(Path(__file__)))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
