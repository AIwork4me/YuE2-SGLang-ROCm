#!/usr/bin/env python3
"""Block raw benchmark lyrics/transcripts from tracked public evidence.

This checks the working tree, not git history; historic objects require a
separate authorization-based remediation. No sensitive values are printed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "target", "reference_lyrics", "reference_tokens", "control_prompt",
    "style_target", "tags_full", "genre_raw", "audio_path",
    "raw_chunks", "phonemes", "text", "lyrics", "transcript",
    "asr_text", "generation_prompt", "prompt_text", "title",
}
NOT_PUBLIC = {"evidence/per_song.jsonl"}


def sensitive_paths(obj, location=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{location}.{key}" if location else key
            if key in FORBIDDEN and not (
                (key == "target" and isinstance(value, str) and value.startswith("gfx"))
                or (key == "phonemes" and isinstance(value, (int, float))
                    and not isinstance(value, bool))
            ):
                yield here
            else:
                yield from sensitive_paths(value, here)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from sensitive_paths(value, f"{location}[{i}]")


def inspect_file(path: Path):
    """Yield field locations only. Never print raw text or a full JSON row."""
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            for n, line in enumerate(stream, 1):
                if line.strip():
                    yield from (f"line {n}: {key}" for key in sensitive_paths(json.loads(line)))
    elif path.suffix == ".json":
        yield from sensitive_paths(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "evidence/"], cwd=ROOT
    ).decode("utf-8").split("\0")
    failures = []
    for name in sorted(filter(None, names)):
        if name in NOT_PUBLIC:
            failures.append((name, "prohibited raw evaluator artifact"))
            continue
        path = ROOT / name
        if path.suffix not in {".json", ".jsonl"} or not path.exists():
            continue
        try:
            for issue in inspect_file(path):
                failures.append((name, issue))
                if len(failures) >= 50:
                    break
        except (UnicodeError, json.JSONDecodeError) as exc:
            failures.append((name, f"invalid structured evidence: {type(exc).__name__}"))
        if len(failures) >= 50:
            break
    if failures:
        for path, problem in failures:
            print(f"::error file={path}::{problem}", file=sys.stderr)
        return 1
    print("PASS: tracked structured evidence contains no blocked text-bearing fields")
    print("NOTE: historical git objects are NOT scanned by this working-tree gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
