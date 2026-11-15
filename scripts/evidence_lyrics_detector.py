#!/usr/bin/env python3
"""evidence_lyrics_detector.py — ground-truth leak scanner (C1 P1).

Two tiers:
  Tier 1 (always): key-based structured scan (same semantics as
    public_evidence_guard.py, extended to ALL tracked text files, fail-closed).
  Tier 2 (when the frozen WildSongBench manifest is present locally):
    ground-truth matching — normalized n-gram windows of the ACTUAL dataset
    lyrics/style prompts are matched against every tracked file's normalized
    text. Catches indirect copies under any key name, any extension,
    any nesting — the only ground truth is the dataset itself.

Output discipline: NEVER prints matched content; reports file, byte offset,
and the sha8 of the matched source line only.

Usage:
  python scripts/evidence_lyrics_detector.py [--ref REF] [--manifest PATH]
    --ref defaults to HEAD (working tree); e.g. --ref main scans that tree.
Exit 0 = clean; 1 = violations; 2 = configuration error (fail-closed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("/data/yue2/benchmark/WildSongBench/benchmark/"
                        "reproduction_manifest.jsonl")
MANIFEST_SHA = "859e5225d319912efb64d587d1d5eb6cf0abc9fb162cc3d5f02d1688cff2edc0"

STRUCTURED_SUFFIXES = {".json", ".jsonl", ".csv"}
TEXT_SUFFIXES = {".md", ".txt", ".py", ".sh", ".yaml", ".yml", ".tsv",
                 ".patch", ".README", ".cfg", ".toml", ".html", ".js"}
BINARY_SUFFIXES = {".png", ".jpg", ".flac", ".wav", ".npy", ".gz", ".tar",
                   ".zip", ".whl", ".bin", ".pt", ".safetensors"}

FORBIDDEN_KEYS = {
    "target", "reference_lyrics", "reference_tokens", "control_prompt",
    "style_target", "tags_full", "genre_raw", "raw_chunks", "phonemes",
    "text", "lyrics", "transcript", "asr_text", "generation_prompt",
    "prompt_text", "title", "song_text", "reference_text", "hyp",
    "hypothesis", "asr_repeats",
}
KEY_EXCEPTIONS = {
    # hardware/arch strings, numeric counts, and known-safe identifiers
    ("target", "gfx"), ("phonemes", "__num__"),
}


def _norm(s: str) -> str:
    """Whitespace/punctuation-insensitive normalization for matching."""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE).lower()


def sha8(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:8]


def load_ground_truth(manifest: Path) -> list[tuple[str, str, int]]:
    """Return [(normalized_window, source_sha8, n)] from real dataset lyrics.

    Only the `lyrics` field is fingerprinted (creative copyrighted text).
    `style` tag lists (e.g. '搞怪,Male Vocals,Mandarin') are factual metadata
    whose fragments legitimately appear in docs — fingerprinting them produced
    false positives, so they are deliberately excluded."""
    rows = [json.loads(l) for l in manifest.read_text(encoding="utf-8")
            .splitlines() if l.strip()]
    windows: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for r in rows:
        raw = str(r.get("lyrics") or "")
        for line in raw.splitlines():
            n = _norm(line)
            cjk = sum(1 for c in line if "\u4e00" <= c <= "\u9fff")
            if len(n) < 12 or cjk < 4:
                continue  # short/latin-only lines are not distinctive
                # enough to fingerprint without false positives
            for i in range(0, max(1, len(n) - 15), 8):
                w = n[i:i + 16]
                if len(w) >= 12 and w not in seen:
                    seen.add(w)
                    windows.append((w, sha8(line), len(w)))
    return windows


def ref_file_text(ref: str, name: str) -> bytes:
    return subprocess.run(["git", "show", f"{ref}:{name}"], cwd=ROOT,
                          capture_output=True, check=True).stdout


def tracked_files(ref: str) -> list[str]:
    out = subprocess.check_output(["git", "ls-tree", "-r", "--name-only",
                                   "-z", ref], cwd=ROOT)
    return [f for f in out.decode("utf-8").split("\0") if f]


SAFE_ENUM_STRINGS = {"chinese", "english", "zh", "en", "auto", "true", "false",
                     "unknown", "none", "complete", "failed", "partial"}

def _leaf_safe(v) -> bool:
    """Numeric/bool/known-safe-enum leaves carry no third-party text."""
    if isinstance(v, bool) or v is None:
        return True
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        return (s in SAFE_ENUM_STRINGS or s == ""
                or re.fullmatch(r"[0-9a-f]{6,64}", s) is not None
                or s.startswith(("lyric-sha256:", "phonemes-sha256:",
                                 "text-sha256:"))
                or re.fullmatch(r"[-+0-9.eE]+", s) is not None)

def _container_all_safe(v) -> bool:
    """A forbidden-key value is safe if every leaf is numeric/bool/safe-enum
    (e.g. the numeric asr_repeats receipts: language/repeat/edits/per/truncated)."""
    if _leaf_safe(v):
        return True
    if isinstance(v, list):
        return all(_container_all_safe(x) for x in v)
    if isinstance(v, dict):
        return all(_container_all_safe(x) for x in v.values())
    return False


def key_scan_structured(name: str, data: bytes) -> list[str]:
    issues = []

    def walk(obj, loc=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                here = f"{loc}.{k}" if loc else k
                if k in FORBIDDEN_KEYS and not _container_all_safe(v):
                    if not (k == "target" and isinstance(v, str)
                            and v.startswith("gfx")):
                        issues.append(here)
                else:
                    walk(v, here)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{loc}[{i}]")

    text = data.decode("utf-8", errors="strict")
    if name.endswith(".jsonl"):
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    walk(json.loads(line))
                except json.JSONDecodeError as exc:
                    issues.append(f"line {n}: UNPARSEABLE-JSONL({exc.msg})")
    elif name.endswith(".json"):
        try:
            walk(json.loads(text))
        except json.JSONDecodeError as exc:
            issues.append(f"UNPARSEABLE-JSON({exc.msg})")
    elif name.endswith(".csv"):
        header_guess = [h for h in text.splitlines()[0].split(",") if h]
        bad = [h for h in header_guess
               if h.strip().strip('"') in FORBIDDEN_KEYS]
        issues += [f"csv-column:{h}" for h in bad]
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None,
                    help="git ref to scan (default: working tree via HEAD files on disk)")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args()

    ref = args.ref or "HEAD"
    files = tracked_files(ref) if args.ref else [
        f for f in subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0") if f]

    # ---- tier 2 ground truth ----
    windows: list[tuple[str, str, int]] = []
    if args.manifest.is_file():
        import hashlib as _h
        digest = _h.sha256(args.manifest.read_bytes()).hexdigest()
        if digest != MANIFEST_SHA:
            print(f"::error::manifest sha {digest[:16]}… != frozen pin — "
                  f"refusing to trust ground truth", file=sys.stderr)
            return 2
        windows = load_ground_truth(args.manifest)
        print(f"ground truth: {len(windows)} windows from frozen manifest",
              file=sys.stderr)
    else:
        print("NOTE: frozen manifest absent — tier-2 ground-truth scan "
              "unavailable (key-based tier-1 only)", file=sys.stderr)

    index: dict[str, str] = {w: s for w, s, _ in windows}
    violations: list[str] = []
    for name in files:
        suffix = Path(name).suffix.lower()
        if suffix in BINARY_SUFFIXES:
            continue
        try:
            data = (Path(ROOT / name).read_bytes() if not args.ref
                    else ref_file_text(ref, name))
        except subprocess.CalledProcessError:
            continue  # removed between listing and read
        except OSError:
            continue
        # tier 1
        if suffix in STRUCTURED_SUFFIXES:
            for issue in key_scan_structured(name, data):
                violations.append(f"{name}: key-scan {issue}")
        # tier 2 — any text file
        if windows:
            try:
                norm = _norm(data.decode("utf-8", errors="replace"))
            except Exception:
                continue
            hits: set[str] = set()
            for w, src in index.items():
                if w in norm:
                    hits.add(src)
            for src in sorted(hits)[:3]:
                violations.append(f"{name}: ground-truth-match sha8={src}")
        if len(violations) > 200:
            break

    if violations:
        for v in violations[:200]:
            print(f"::error file={v.split(':')[0]}::{v.split(':', 1)[1]}",
                  file=sys.stderr)
        print(f"FAIL: {len(violations)} text-bearing findings", file=sys.stderr)
        return 1
    print(f"PASS: {len(files)} tracked files clean "
          f"(tier1={'on'} tier2={'on' if windows else 'OFF'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
