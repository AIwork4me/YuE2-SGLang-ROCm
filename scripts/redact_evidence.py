#!/usr/bin/env python3
"""Publish numeric WildSongBench receipts without third-party text.

The raw evaluator outputs must remain in restricted, rights-cleared storage.
This tool produces a separate text-free artifact, checks retained numeric
fields exactly, and NEVER overwrites the original. The current-tree audit is
scripts/public_evidence_guard.py; Git history requires separate remediation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TEXT_FIELDS = frozenset({
    "target", "reference_lyrics", "reference_tokens", "control_prompt",
    "style_target", "tags_full", "genre_raw", "audio_path", "raw_chunks",
    "phonemes", "text", "lyrics", "transcript", "asr_text",
    "generation_prompt", "prompt_text", "title",
})


def redact_obj(obj):
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, dict):
        return {
            key: redact_obj(value)
            for key, value in obj.items()
            if key not in TEXT_FIELDS
            or (key == "target" and isinstance(value, str)
                and value.startswith("gfx"))
            or (key == "phonemes" and isinstance(value, (int, float))
                and not isinstance(value, bool))
        }
    return obj


def numeric_leaves(obj, location=""):
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from numeric_leaves(item, f"{location}[{i}]")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from numeric_leaves(value, f"{location}.{key}")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield location, obj


def load(path):
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError("Only .json and .jsonl are supported")


def dump(path, obj):
    if path.suffix == ".jsonl":
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in obj)
    else:
        content = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8") as out:
        out.write(content)


def redact_file(path: Path) -> Path:
    if ".redacted." in path.name:
        raise ValueError("Source must be the restricted original, not an earlier export")
    original = load(path)
    redacted = redact_obj(original)
    before, after = dict(numeric_leaves(original)), dict(numeric_leaves(redacted))
    if any(before[key] != value for key, value in after.items()):
        raise ValueError("Numerical scientific evidence changed")
    target = path.with_name(path.stem + ".redacted" + path.suffix)
    dump(target, redacted)
    return target


def verify(redacted: Path, original: Path) -> bool:
    return load(redacted) == redact_obj(load(original))


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--verify":
        if len(sys.argv) != 4:
            raise SystemExit("Usage: --verify <redacted.json[l]> <original.json[l]>")
        ok = verify(Path(sys.argv[2]), Path(sys.argv[3]))
        print("VERIFY", "OK" if ok else "MISMATCH")
        return 0 if ok else 1
    if len(sys.argv) < 2:
        raise SystemExit("Usage: redact_evidence.py <restricted.json[l]> [more...]")
    for name in sys.argv[1:]:
        p = redact_file(Path(name))
        print("WROTE PUBLIC RECEIPT", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
