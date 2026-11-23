#!/usr/bin/env python3
"""input_budget.py — bounded input contract for YuE2 generation requests
(RC4.1 M3.5).

RC4 evidence: a ~2.6 KB repeated-tags payload was misclassified as a
"request-path hang". RCA: the payload is schema-VALID, so the server applied
DEFAULT full-song budgets (semantic_max_tokens=9000, ode_steps=32) — a
multi-minute legitimate generation that outlived the 60 s test budget. The
defect was in the test harness budget, not an infinite loop.

This module is the project-side prevention layer:
  * cheap, pure-CPU prechecks BEFORE any GPU work is requested
  * legitimate long lyrics (e.g. 40 verses) still PASS
  * degenerate structures (massively repeated tag sections) get a bounded,
    clearly-classified rejection instead of unbounded GPU spend
  * the frozen WildSongBench driver path (run_wsb.py, official manifest
    payloads) is intentionally NOT wired through this module — protocol
    isolation; official payloads pass these budgets anyway (verified by
    tests against the manifest shape).

Classifications (receipt field `class`):
  OK · TYPE_INVALID · STYLE_TOO_LARGE · LYRICS_TOO_LARGE ·
  STYLE_DEGENERATE_REPETITION · FIELD_UNSET

CLI exit codes: 0 OK · 4 rejected (bounded) · 2 usage/internal error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

DEFAULTS = {
    "style_max_bytes": 4096,        # WSB styles are ~100-300 bytes
    "lyrics_max_bytes": 65536,      # 40-verse lyrics ≈ 4-6 KB; huge margin
    "style_max_sections": 8,        # [Tags]-like section headers in style
    "style_repeat_limit": 16,       # identical consecutive tag-section cap
    "total_max_bytes": 131072,
}

SECTION_RE = re.compile(r"^\s*\[[^\]\n]{0,64}\]\s*$", re.M)


def _sections(text: str) -> list[str]:
    return [m.group(0).strip() for m in SECTION_RE.finditer(text)]


def check_payload(payload: dict, limits: dict | None = None) -> dict:
    """Return a bounded-verdict receipt for a request payload (pure CPU)."""
    L = {**DEFAULTS, **(limits or {})}
    receipt = {
        "receipt_type": "input_budget",
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "limits": L,
        "class": "OK",
        "ok": True,
        "reason": "",
        "measured": {},
    }

    def reject(cls, reason, **measured):
        receipt["class"] = cls
        receipt["ok"] = False
        receipt["reason"] = reason
        receipt["measured"].update(measured)

    if not isinstance(payload, dict):
        reject("TYPE_INVALID", "payload must be a JSON object")
        return receipt
    style = payload.get("style")
    lyrics = payload.get("lyrics", "")
    if style is None or not isinstance(style, str):
        reject("TYPE_INVALID", "style must be a string")
        return receipt
    if lyrics is None:
        lyrics = ""
    if not isinstance(lyrics, str):
        reject("TYPE_INVALID", "lyrics must be a string")
        return receipt
    try:
        style.encode("utf-8")
        lyrics.encode("utf-8")
    except UnicodeEncodeError as e:
        reject("TYPE_INVALID", f"not encodable as UTF-8: {e}")
        return receipt

    sb = len(style.encode("utf-8"))
    lb = len(lyrics.encode("utf-8"))
    receipt["measured"]["style_bytes"] = sb
    receipt["measured"]["lyrics_bytes"] = lb
    if sb > L["style_max_bytes"]:
        reject("STYLE_TOO_LARGE",
               f"style is {sb} bytes > budget {L['style_max_bytes']}",
               style_bytes=sb)
        return receipt
    if lb > L["lyrics_max_bytes"]:
        reject("LYRICS_TOO_LARGE",
               f"lyrics is {lb} bytes > budget {L['lyrics_max_bytes']}",
               lyrics_bytes=lb)
        return receipt
    if sb + lb > L["total_max_bytes"]:
        reject("STYLE_TOO_LARGE" if sb >= lb else "LYRICS_TOO_LARGE",
               f"total {sb + lb} bytes > budget {L['total_max_bytes']}")
        return receipt

    sections = _sections(style)
    receipt["measured"]["style_sections"] = len(sections)
    if len(sections) > L["style_max_sections"]:
        reject("STYLE_DEGENERATE_REPETITION",
               f"style carries {len(sections)} bracket sections "
               f"(budget {L['style_max_sections']}); degenerate repeated-tags "
               f"structure rejected BEFORE GPU work",
               style_sections=len(sections))
        return receipt
    if sections:
        run = max_run(sections)
        receipt["measured"]["style_max_identical_run"] = run
        if run > L["style_repeat_limit"]:
            reject("STYLE_DEGENERATE_REPETITION",
                   f"identical style section repeated {run}x "
                   f"(budget {L['style_repeat_limit']})",
                   style_max_identical_run=run)
            return receipt

    # seed sanity (same rule as SongRequest)
    seed = payload.get("seed", 831001)
    if type(seed) is not int or not 0 <= seed < 2**63:
        reject("TYPE_INVALID", "seed must be an integer in [0, 2^63)")
        return receipt
    return receipt


def max_run(items: list) -> int:
    best = run = 0
    prev = object()
    for it in items:
        run = run + 1 if it == prev else 1
        prev = it
        best = max(best, run)
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="bounded input precheck")
    ap.add_argument("payload", type=Path,
                    help="JSON file with the request payload")
    ap.add_argument("--limits", type=Path, default=None,
                    help="JSON file overriding budget limits")
    ap.add_argument("--receipt", type=Path, default=None)
    a = ap.parse_args(argv)
    try:
        payload = json.loads(a.payload.read_text())
        limits = json.loads(a.limits.read_text()) if a.limits else None
    except (OSError, ValueError) as e:
        print(json.dumps({"class": "TYPE_INVALID", "ok": False,
                          "reason": f"unreadable payload/limits: {e}"}))
        return 2
    r = check_payload(payload, limits)
    print(json.dumps(r, indent=1))
    if a.receipt:
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.write_text(json.dumps(r, indent=1) + "\n")
    return 0 if r["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
