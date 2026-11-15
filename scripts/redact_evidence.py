#!/usr/bin/env python3
"""redact_evidence.py — produce lyric-redacted scientific receipts (P8/LQ-1).

Creates `<name>.redacted<ext>` siblings: metric values, identities, hashes and
counts are preserved VERBATIM; copyrighted dataset text (WildSongBench
reference lyrics) is replaced by its sha256 (12 hex) so cross-referencing the
restricted original remains possible without republishing it.

The tool NEVER deletes or modifies originals in place — the owner decides what
becomes public. Idempotent; skips rows already redacted.

Usage: python scripts/redact_evidence.py <file.jsonl|file.json> [more...]
       python scripts/redact_evidence.py --verify <file.redacted.jsonl> <orig>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

TEXT_KEYS = {"target", "reference_lyrics", "lyrics", "transcript",
             "control_prompt", "tags_full", "style_target", "genre_raw"}
TOKEN_KEYS = {"reference_tokens"}  # phoneme sequences derived from the lyrics
MIN_REAL = 50  # shorter strings are treated as already-redacted/metadata


def _digest(text: str) -> str:
    return "lyric-sha256:" + hashlib.sha256(text.encode()).hexdigest()[:12]


def redact_obj(o, path=""):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            p = f"{path}.{k}"
            if k in TEXT_KEYS and isinstance(v, str) and len(v) > MIN_REAL:
                out[k] = _digest(v)
            elif k in TOKEN_KEYS and isinstance(v, list) and v:
                out[k] = (f"phonemes-sha256:{hashlib.sha256(json.dumps(v, ensure_ascii=False).encode()).hexdigest()[:12]}"
                          f"({len(v)} tokens)")
            elif k == "text" and ".asr_repeats" in path and isinstance(v, str) and len(v) > MIN_REAL:
                # ASR transcripts of generated audio substantially reproduce the
                # copyrighted prompt lyrics (the model sings them) -> redact
                out[k] = _digest(v)
            elif k == "raw_chunks" and ".asr_repeats" in path and isinstance(v, list):
                out[k] = [redact_obj(c, p) for c in v]
            else:
                out[k] = redact_obj(v, p)
        return out
    if isinstance(o, list):
        return [redact_obj(x, path) for x in o]
    return o


def redact_file(p: Path) -> Path:
    out = p.with_name(p.name.replace(p.suffix, ".redacted" + p.suffix))
    if p.suffix == ".jsonl":
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        out.write_text("".join(json.dumps(redact_obj(r), ensure_ascii=False) + "\n"
                               for r in rows))
    else:
        out.write_text(json.dumps(redact_obj(json.loads(p.read_text())),
                                  ensure_ascii=False, indent=1))
    return out


def verify(redacted: Path, orig: Path) -> bool:
    """Round-trip identity: redact_obj(original) must equal the redacted file."""
    if redacted.suffix == ".jsonl":
        o = [json.loads(l) for l in orig.read_text().splitlines() if l.strip()]
        r = [json.loads(l) for l in redacted.read_text().splitlines() if l.strip()]
        if len(o) != len(r):
            return False
        return all(json.dumps(redact_obj(a), ensure_ascii=False, sort_keys=True)
                   == json.dumps(b, ensure_ascii=False, sort_keys=True)
                   for a, b in zip(o, r))
    return (json.dumps(redact_obj(json.loads(orig.read_text())),
                       ensure_ascii=False, sort_keys=True)
            == json.dumps(json.loads(redacted.read_text()),
                          ensure_ascii=False, sort_keys=True))


def main() -> int:
    if sys.argv[1] == "--verify":
        ok = verify(Path(sys.argv[2]), Path(sys.argv[3]))
        print("VERIFY", "OK" if ok else "MISMATCH")
        return 0 if ok else 1
    for arg in sys.argv[1:]:
        out = redact_file(Path(arg))
        print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
